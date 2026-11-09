"""Load pandas tables into BigQuery and keep the ingestion audit history."""

import gzip
import io

from google.api_core.exceptions import NotFound
from google.cloud import bigquery
import pandas as pd


TYPE_MAP = {
    "string": "STRING", "int": "INTEGER", "float": "FLOAT",
    "numeric": "NUMERIC", "datetime": "DATETIME", "timestamp": "TIMESTAMP",
}
LOG_SCHEMA = {
    "run_id": "string", "source": "string", "started_at": "timestamp",
    "finished_at": "timestamp", "file_sha256": "string", "fingerprint": "string",
    "status": "string", "rows_read": "int", "rows_loaded": "int",
    "rows_rejected": "int", "duplicates_removed": "int", "destination_etag": "string",
    "error": "string",
}
REJECT_SCHEMA = {
    "run_id": "string", "source": "string", "rejected_at": "timestamp",
    "row_number": "int", "reason": "string", "raw_record": "string",
}


def should_skip(previous, fingerprint, table):
    """Skip a file only when its saved fingerprint and destination table still match."""
    if previous is None or table is None:
        return False
    # An etag is BigQuery's version ID for a table. It changes when the table changes.
    return (previous["fingerprint"] == fingerprint
            and previous["destination_etag"] == table.etag
            and previous["rows_loaded"] == table.num_rows)


class BigQueryStore:
    """Keep the BigQuery client and staging dataset settings in one place."""

    def __init__(self, settings):
        """Create a client using the Google login saved on this computer."""
        self.project = settings["project"]
        self.dataset = settings["staging_dataset"]
        self.location = settings["location"]
        self.client = bigquery.Client(project=self.project, location=self.location)

    def table_id(self, name):
        """Combine the project, dataset, and table name."""
        return f"{self.project}.{self.dataset}.{name}"

    def schema_fields(self, schema):
        """Convert the types in our configuration into BigQuery schema fields."""
        fields = []
        for name, kind in schema.items():
            fields.append(bigquery.SchemaField(name, TYPE_MAP[kind]))
        return fields

    def prepare(self):
        """Check the dataset location and create the log and rejects tables if missing."""
        dataset = self.client.get_dataset(f"{self.project}.{self.dataset}")
        if dataset.location.upper() != self.location.upper():
            raise ValueError("Staging dataset location does not match the config.")
        for name, schema in (("load_log", LOG_SCHEMA), ("rejects", REJECT_SCHEMA)):
            table = bigquery.Table(self.table_id(name), schema=self.schema_fields(schema))
            self.client.create_table(table, exists_ok=True)

    def get_table(self, name):
        """Return table metadata, or None when a table is missing or has expired."""
        try:
            return self.client.get_table(self.table_id(name))
        except NotFound:
            return None

    def last_load(self, name):
        """Find the latest successful load for one source."""
        sql = f"""
            SELECT fingerprint, destination_etag, rows_loaded
            FROM `{self.table_id('load_log')}`
            WHERE source = @source AND status = 'loaded'
            ORDER BY finished_at DESC LIMIT 1
        """
        config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("source", "STRING", name),
        ])
        rows = list(self.client.query(sql, job_config=config, location=self.location).result())
        return dict(rows[0]) if rows else None

    def write_rows(self, name, rows, schema, append=False):
        """Upload a table as compressed CSV using an explicit BigQuery schema."""
        frame = pd.DataFrame(rows, columns=list(schema))
        # Nullable integer columns must write 1 or an empty field, rather than 1.0.
        for column, kind in schema.items():
            if kind == "int":
                frame[column] = frame[column].astype("Int64")

        # pandas handles CSV quoting for review comments, including embedded newlines.
        # Compression keeps the real Olist uploads small enough to transfer quickly.
        payload = gzip.compress(frame.to_csv(index=False).encode("utf-8"))
        config = bigquery.LoadJobConfig(
            schema=self.schema_fields(schema), source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1, allow_quoted_newlines=True,
            write_disposition="WRITE_APPEND" if append else "WRITE_TRUNCATE",
        )
        self.client.load_table_from_file(
            io.BytesIO(payload), self.table_id(name), job_config=config,
            location=self.location, size=len(payload),
        ).result()

    def replace_source(self, source, frame):
        """Replace a source table with its current clean rows."""
        print(f"Uploading {source['name']}: {len(frame):,} rows", flush=True)
        self.write_rows(source["name"], frame, source["schema"])
        return self.get_table(source["name"])

    def append_rejects(self, rows):
        """Add rejected rows while keeping rejects from earlier runs."""
        if rows:
            self.write_rows("rejects", rows, REJECT_SCHEMA, append=True)

    def append_log(self, row):
        """Add one source's results to the load log."""
        self.write_rows("load_log", [row], LOG_SCHEMA, append=True)
