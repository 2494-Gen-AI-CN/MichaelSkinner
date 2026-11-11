"""Check chart populations and displayed rows without connecting to BigQuery."""

import pandas as pd
import sys

from src import charts


def test_render_analysis_without_google_login(tmp_path, monkeypatch):
    """Produce runnable analysis SQL locally without opening a cloud connection."""
    source = tmp_path / "sql/analysis"
    source.mkdir(parents=True)
    (source / "01_example.sql").write_text("SELECT * FROM `${PROJECT}.${WAREHOUSE}.fact_order_item`;")
    settings = {"root": tmp_path, "bigquery": {"project": "example-project",
                "staging_dataset": "stage", "warehouse_dataset": "warehouse"}}
    monkeypatch.setattr(charts, "load_config", lambda path: settings)
    monkeypatch.setattr(sys, "argv", ["charts", "--render-only"])

    def unexpected_client(settings):
        """Fail if local SQL rendering attempts to authenticate with Google."""
        raise AssertionError("Rendering SQL should not create a BigQuery client")

    monkeypatch.setattr(charts, "_client", unexpected_client)
    assert charts.main() == 0
    rendered = (tmp_path / "data/rendered_analysis/01_example.sql").read_text()
    assert "`example-project.warehouse.fact_order_item`" in rendered
    assert "${" not in rendered


def test_promise_chart_uses_all_deliveries_and_displays_eight_states(tmp_path, monkeypatch):
    """Use the promise query and display the highest late rates without requiring reviews."""
    rows = []
    for index in range(12):
        rows.append({"customer_state": f"S{index:02}", "delivered_orders": 100 + index,
                     "avg_promise_days": 30.0, "avg_delivery_days": 20.0,
                     "avg_days_late": -10.0, "late_rate": index / 100})

    def query_file(client, cloud, filename):
        """Supply a small all-delivery result instead of making a cloud request."""
        assert filename == "04_promise_realism_by_state.sql"
        return pd.DataFrame(rows)

    monkeypatch.setattr(charts, "_run_file", query_file)
    result = charts.chart_promise_vs_actual_by_state(None, {}, tmp_path)
    plotted = pd.read_csv(tmp_path / "03_promise_vs_actual_by_state.csv")
    assert len(result) == 12
    assert len(plotted) == 8
    assert plotted["customer_state"].tolist() == [f"S{index:02}" for index in range(11, 3, -1)]
    assert plotted["delivered_orders"].tolist() == list(range(111, 103, -1))
    assert "avg_promise_days" in plotted and "avg_delivery_days" in plotted
    assert (tmp_path / "03_promise_vs_actual_by_state.png").stat().st_size > 0


def test_corridor_ranking_uses_counts_before_rounding(tmp_path, monkeypatch):
    """Keep the true ordering when displayed four-decimal rates appear tied."""
    rows = []
    for index in range(15):
        late = 10001 + index
        rows.append({"seller_state": f"S{index:02}", "customer_state": "AL",
                     "delivered_items": 100000, "late_items": late,
                     "late_rate": round(late / 100000, 4)})

    def query_file(client, cloud, filename):
        """Supply corridor results with close rates instead of querying BigQuery."""
        assert filename == "01_late_rate_by_corridor.sql"
        return pd.DataFrame(rows)

    monkeypatch.setattr(charts, "_run_file", query_file)
    charts.chart_late_rate_by_corridor(None, {}, tmp_path)
    plotted = pd.read_csv(tmp_path / "05_late_rate_by_corridor.csv")
    assert len(plotted) == 12
    assert plotted.iloc[0]["seller_state"] == "S14"
    assert plotted.iloc[-1]["seller_state"] == "S03"
    assert plotted.iloc[0]["late_items"] == 10015
    assert (tmp_path / "05_late_rate_by_corridor.png").stat().st_size > 0
