"""Check CSV uploads and skip decisions without making cloud requests."""

import csv
import gzip
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from src.ingest.load import BigQueryStore, should_skip


@pytest.fixture
def store(monkeypatch):
    """Replace the Google client with a mock so no test can upload data."""
    client = Mock()
    monkeypatch.setattr("src.ingest.load.bigquery.Client", Mock(return_value=client))
    return BigQueryStore({"project": "example-project", "staging_dataset": "p0_staging", "location": "US"})


def test_csv_upload_preserves_ids_nulls_and_multiline_comments(store):
    """Quote review text correctly and keep nullable integers and leading-zero IDs."""
    rows = [{"id": "001", "number": 1, "comment": 'First line\nSecond "quoted" line'},
            {"id": "002", "number": None, "comment": ""}]
    store.write_rows("example", rows, {"id": "string", "number": "int", "comment": "string"})
    args, kwargs = store.client.load_table_from_file.call_args
    content = gzip.decompress(args[0].getvalue()).decode("utf-8")
    decoded = list(csv.DictReader(io.StringIO(content)))
    assert decoded[0] == {"id": "001", "number": "1", "comment": rows[0]["comment"]}
    assert decoded[1]["number"] == ""
    assert kwargs["job_config"].allow_quoted_newlines
    assert kwargs["job_config"].write_disposition == "WRITE_TRUNCATE"
    store.client.load_table_from_file.return_value.result.assert_called_once()


def test_audit_upload_appends_rows(store):
    """Append audit records without replacing previous history."""
    store.write_rows("example", [{"id": "1"}], {"id": "string"}, append=True)
    config = store.client.load_table_from_file.call_args.kwargs["job_config"]
    assert config.write_disposition == "WRITE_APPEND"
    assert config.source_format == "CSV"


def test_missing_or_changed_table_is_not_skipped():
    """Reload a source when its previous destination table no longer matches."""
    previous = {"fingerprint": "file-1", "destination_etag": "version-1", "rows_loaded": 10}
    table = SimpleNamespace(etag="version-1", num_rows=10)
    assert should_skip(previous, "file-1", table)
    assert not should_skip(previous, "file-1", None)
    table.etag = "version-2"
    assert not should_skip(previous, "file-1", table)
