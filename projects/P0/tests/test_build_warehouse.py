"""Test warehouse build orchestration without connecting to Google Cloud."""

from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.build_warehouse import run_build


@pytest.fixture
def build_settings(tmp_path):
    """Copy the SQL into a temporary project with harmless example cloud settings."""
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "sql/warehouse", tmp_path / "sql/warehouse")
    return {"root": tmp_path, "bigquery": {
        "project": "example-project", "staging_dataset": "p0_staging",
        "warehouse_dataset": "p0_warehouse", "location": "US",
    }}


def mock_client(passed=True):
    """Return an in-memory client whose last query produces a warehouse check result."""
    client = Mock()
    client.get_dataset.return_value = SimpleNamespace(location="US")
    jobs = []
    for index in range(9):
        job = Mock()
        job.result.return_value = [{"check_name": "example_check", "observed": 1, "expected": 1, "passed": passed}] if index == 8 else []
        jobs.append(job)
    client.query.side_effect = jobs
    return client


def test_render_only_does_not_use_cloud_client(build_settings):
    """Export SQL for the console without authenticating or touching cloud tables."""
    client = Mock()
    assert run_build(build_settings, render_only=True, client=client) == []
    client.query.assert_not_called()
    path = build_settings["root"] / "data/rendered_sql/07_fact_order_item.sql"
    assert "example-project.p0_warehouse.fact_order_item" in path.read_text()
    assert "${" not in path.read_text()


def test_build_runs_checks_last_and_saves_report(build_settings):
    """Run transformations in dependency order and preserve validation evidence."""
    client = mock_client()
    checks = run_build(build_settings, client=client)
    assert checks[0]["passed"]
    assert client.query.call_count == 9
    assert "fact_preserves_all_staging_items" in client.query.call_args.args[0]
    assert (build_settings["root"] / "data/warehouse_checks.csv").exists()


def test_failed_checks_stop_build_with_saved_evidence(build_settings):
    """Report a failed warehouse assertion instead of claiming a successful build."""
    with pytest.raises(RuntimeError, match="example_check"):
        run_build(build_settings, client=mock_client(passed=False))
    assert (build_settings["root"] / "data/warehouse_checks.csv").exists()


def test_mismatched_dataset_location_prevents_queries(build_settings):
    """Reject incompatible dataset locations before replacing any warehouse tables."""
    client = mock_client()
    client.get_dataset.return_value = SimpleNamespace(location="EU")
    with pytest.raises(ValueError, match="must be in US"):
        run_build(build_settings, client=client)
    client.query.assert_not_called()
