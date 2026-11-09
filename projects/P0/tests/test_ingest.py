"""Test reruns and source errors without connecting to BigQuery."""

from types import SimpleNamespace

import pytest
import yaml

from src.ingest.config import load_config, source_fingerprint
from src.ingest.main import run_ingestion


class FakeStore:
    """Stand in for BigQuery during tests by keeping tables and logs in memory."""

    def __init__(self):
        """Start with empty tables and audit records."""
        self.tables = {}
        self.logs = []
        self.rejects = []
        self.writes = 0

    def prepare(self):
        """Do nothing because the test store does not need cloud setup."""

    def get_table(self, name):
        """Return the test table if it exists."""
        return self.tables.get(name)

    def last_load(self, name):
        """Find the latest successful load for this source."""
        for row in reversed(self.logs):
            if row["source"] == name and row["status"] == "loaded":
                return row
        return None

    def replace_source(self, source, frame):
        """Record a replacement table and a new version number."""
        self.writes += 1
        table = SimpleNamespace(etag=str(self.writes), num_rows=len(frame))
        self.tables[source["name"]] = table
        return table

    def append_rejects(self, rows):
        """Keep the rejected rows supplied by the ingestion job."""
        self.rejects.extend(rows)

    def append_log(self, row):
        """Keep a copy of each source result."""
        self.logs.append(row.copy())


@pytest.fixture
def settings(tmp_path, sources):
    """Create one small CSV source in a temporary project directory."""
    source = sources["category_translation"]
    source["path"] = "translation.csv"
    (tmp_path / source["path"]).write_text(
        "product_category_name,product_category_name_english\nbooks,Books\nmissing,\n")
    return {"root": tmp_path, "bigquery": {}, "sources": [source]}


def test_second_run_does_not_duplicate_data(settings):
    """Skip unchanged data while recording both runs in the load log."""
    store = FakeStore()
    first = run_ingestion(settings, store=store)
    second = run_ingestion(settings, store=store)
    assert first[0]["status"] == "loaded"
    assert second[0]["status"] == "skipped"
    assert second[0]["rows_loaded"] == 0
    assert store.writes == 1
    assert len(store.rejects) == 1
    assert len(store.logs) == 2


def test_expired_table_is_reloaded(settings):
    """Reload a source if its table has expired even when the file is unchanged."""
    store = FakeStore()
    run_ingestion(settings, store=store)
    store.tables.clear()
    assert run_ingestion(settings, store=store)[0]["status"] == "loaded"
    assert store.writes == 2


def test_changed_file_is_reloaded(settings):
    """Replace a source table when the CSV contents change."""
    store = FakeStore()
    run_ingestion(settings, store=store)
    (settings["root"] / "translation.csv").write_text(
        "product_category_name,product_category_name_english\nbooks,Books\ntoys,Toys\n")
    result = run_ingestion(settings, store=store)
    assert result[0]["rows_loaded"] == 2
    assert store.writes == 2


def test_missing_file_does_not_stop_the_next_source(settings):
    """Log a failed source and continue processing the remaining files."""
    missing = dict(settings["sources"][0], name="missing", path="absent.csv")
    settings["sources"].insert(0, missing)
    results = run_ingestion(settings, store=FakeStore())
    assert [row["status"] for row in results] == ["failed", "loaded"]


def test_dry_run_does_not_upload(settings):
    """Clean locally and report ready rows without writing cloud data."""
    store = FakeStore()
    result = run_ingestion(settings, dry_run=True, store=store)
    assert result[0]["rows_ready"] == 1
    assert result[0]["rows_loaded"] == 0
    assert store.writes == 0


def test_config_change_changes_the_fingerprint(settings):
    """Reload a file when its cleaning settings change even if its contents do not."""
    source = settings["sources"][0]
    path = settings["root"] / source["path"]
    first_hash, first_fingerprint = source_fingerprint(path, source)
    source["normalize"] = {"product_category_name_english": "lower"}
    second_hash, second_fingerprint = source_fingerprint(path, source)
    assert first_hash == second_hash
    assert first_fingerprint != second_fingerprint


def test_config_uses_local_project_id(tmp_path, monkeypatch, sources):
    """Read the project from the environment and protect the audit table names."""
    monkeypatch.setenv("GCP_PROJECT", "example-project")
    config = {"bigquery": {"project": "${GCP_PROJECT}", "staging_dataset": "p0_staging",
                           "warehouse_dataset": "p0_warehouse"}, "sources": [sources["products"]]}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    assert load_config(path)["bigquery"]["project"] == "example-project"
    config["sources"][0]["name"] = "rejects"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="reserved"):
        load_config(path)

