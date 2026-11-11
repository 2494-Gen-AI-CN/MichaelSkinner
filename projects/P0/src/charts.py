"""Create five charts from BigQuery results and print the supporting statistics.

Run from projects/P0 with:
    python -m src.charts --config config/config.yaml

PNG charts and their plotted CSV data are saved in charts/ by default.
"""

import argparse
import os
from pathlib import Path

# Keep Matplotlib's generated cache with the ignored local project data.
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / ".matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from google.cloud import bigquery

from .ingest.config import load_config
from .build_warehouse import render_sql


TEAL = "#009E91"
BLUE = "#4C7DA7"
ORANGE = "#F07A40"
RED = "#D9555B"


def _client(settings):
    """Connect to the configured BigQuery project using the local Google login."""
    cloud = settings["bigquery"]
    return bigquery.Client(project=cloud["project"], location=cloud["location"])


def _run(client, cloud, sql):
    """Run a read-only query and turn its result rows into a pandas table."""
    sql = render_sql(sql, cloud)
    result = client.query(sql, location=cloud["location"]).result()
    # Use normal query results, without requiring the separate Storage Read API.
    return pd.DataFrame([dict(row) for row in result],
                        columns=[field.name for field in result.schema])


def _run_file(client, cloud, filename):
    """Run an existing analysis SQL file so charts and live queries share the same logic."""
    sql = (ROOT / "sql" / "analysis" / filename).read_text()
    return _run(client, cloud, sql)


def _save_chart(fig, df, out_dir, filename):
    """Save a PNG and the exact rows plotted in it for checking and reuse."""
    fig.tight_layout()
    fig.savefig(out_dir / filename, dpi=180)
    plt.close(fig)
    df.to_csv(out_dir / Path(filename).with_suffix(".csv"), index=False)
    print(f"Saved {out_dir / filename}")


def chart_late_rate_by_corridor(client, cloud, out_dir):
    """Show the twelve highest late-rate corridors with at least thirty delivered items."""
    df = _run_file(client, cloud, "01_late_rate_by_corridor.sql")
    # Calculate from counts before ranking; rounded rates can create artificial ties.
    df["late_rate"] = df["late_items"] / df["delivered_items"]
    df = df.sort_values(["late_rate", "seller_state", "customer_state"],
                        ascending=[False, True, True]).head(12).reset_index(drop=True)
    labels = [f"{row.seller_state} → {row.customer_state} (n={row.delivered_items:,})"
              for row in df.itertuples()]
    rates = df["late_rate"] * 100
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels, rates, color=BLUE)
    ax.invert_yaxis()
    ax.set_xlim(0, max(rates) * 1.18)
    for index, value in enumerate(rates):
        ax.text(value + 0.3, index, f"{value:.1f}%", va="center")
    ax.set_xlabel("Late delivered items (%) · minimum 30 items per corridor")
    ax.set_title("Highest late rates among eligible seller-to-customer corridors")
    _save_chart(fig, df, out_dir, "05_late_rate_by_corridor.png")
    return df


def chart_late_rate_by_category(client, cloud, out_dir):
    """Show fifteen high late-rate categories, retaining unknown category labels."""
    df = _run_file(client, cloud, "02_late_rate_by_category.sql")
    # The SQL excludes missing product references, but retains known products with no category.
    df["late_rate"] = df["late_items"] / df["delivered_items"]
    df = df.sort_values(["late_rate", "category"], ascending=[False, True]).head(15).reset_index(drop=True)
    labels = df["category"].str.replace("_", " ")
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(labels, df["late_rate"] * 100, color=ORANGE)
    ax.invert_yaxis()
    ax.set_xlabel("Late delivered items (%) · minimum 50 items per category")
    ax.set_title("Audio has the highest eligible category late rate")
    _save_chart(fig, df, out_dir, "02_late_rate_by_category.png")
    return df


def chart_review_by_lateness(client, cloud, out_dir):
    """Compare review averages using one reviewed delivered order per observation."""
    df = _run_file(client, cloud, "03_review_by_lateness.sql")
    labels = [f"{row.lateness_bucket.replace('on_time', 'on time')}\n(n={row.orders:,})"
              for row in df.itertuples()]
    colors = [TEAL if bucket in ("early", "on_time") else RED for bucket in df["lateness_bucket"]]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(labels, df["avg_review_score"], color=colors, width=0.65)
    for bar, value in zip(bars, df["avg_review_score"]):
        ax.text(bar.get_x() + bar.get_width()/2, value + 0.06, f"{value:.2f}", ha="center")
    ax.set_ylim(0, 5.4)
    ax.set_ylabel("Average review score (1–5)")
    ax.set_title("Lower reviews accompany longer delivery delays")
    _save_chart(fig, df, out_dir, "01_review_by_lateness.png")
    return df


def chart_promise_vs_actual_by_state(client, cloud, out_dir):
    """Compare promised and actual durations for the eight highest-late-rate eligible states."""
    df = _run_file(client, cloud, "04_promise_realism_by_state.sql")
    df = df.sort_values(["late_rate", "customer_state"], ascending=[False, True]).reset_index(drop=True)
    # Include all delivered orders, not only reviewed orders, as required by the promise question.
    plotted = df.head(8).copy()
    labels = [f"{row.customer_state} ({row.late_rate:.1%} late)" for row in plotted.itertuples()]
    positions = np.arange(len(plotted))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(positions - 0.18, plotted["avg_promise_days"], 0.33, label="Promised", color=BLUE)
    ax.barh(positions + 0.18, plotted["avg_delivery_days"], 0.33, label="Actual", color=TEAL)
    ax.set_yticks(positions, labels=labels)
    ax.invert_yaxis()
    ax.set_xlabel("Average calendar days from purchase")
    ax.set_title("Average delivery is earlier than the promise", pad=40)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2, frameon=False, borderaxespad=0)
    fig.text(0.5, 0.01, "Eight highest-late-rate states shown; minimum 100 delivered orders, including orders without reviews.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    # Keep the footer space when saving this figure.
    fig.savefig(out_dir / "03_promise_vs_actual_by_state.png", dpi=180)
    plt.close(fig)
    plotted.to_csv(out_dir / "03_promise_vs_actual_by_state.csv", index=False)
    print(f"Saved {out_dir / '03_promise_vs_actual_by_state.png'}")
    return df


def chart_freight_vs_satisfaction(client, cloud, out_dir):
    """Compare order-level review scores across order freight-to-merchandise ratios."""
    df = _run(client, cloud, """
        SELECT CASE
                 WHEN order_freight_ratio < 0.1 THEN '< 10%'
                 WHEN order_freight_ratio < 0.2 THEN '10-20%'
                 WHEN order_freight_ratio < 0.4 THEN '20-40%'
                 WHEN order_freight_ratio < 0.7 THEN '40-70%'
                 ELSE '>= 70%'
               END AS freight_bucket,
               COUNT(*) AS orders,
               ROUND(AVG(CAST(review_score AS FLOAT64)), 3) AS avg_review_score
        FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
        WHERE review_score IS NOT NULL AND order_freight_ratio IS NOT NULL AND is_delivered
        GROUP BY freight_bucket
        ORDER BY MIN(order_freight_ratio)
    """)
    labels = [f"{row.freight_bucket}\n(n={row.orders:,})" for row in df.itertuples()]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(labels, df["avg_review_score"], color="#8265AF", width=0.65)
    for bar, value in zip(bars, df["avg_review_score"]):
        ax.text(bar.get_x() + bar.get_width()/2, value + 0.06, f"{value:.2f}", ha="center")
    ax.set_ylim(0, 5.4)
    ax.set_xlabel("Order freight charge / order merchandise value")
    ax.set_ylabel("Average review score (1–5)")
    ax.set_title("Review differences across freight shares are small")
    _save_chart(fig, df, out_dir, "04_freight_vs_satisfaction.png")
    return df


def compute_correlation(client, cloud):
    """Calculate order-level correlations, using average tied ranks for Spearman."""
    # RANK gives a tie group's first position. Adding (group_size - 1) / 2
    # assigns the average position, which is the standard tie handling for Spearman.
    result = _run(client, cloud, """
        WITH ranked AS (
          SELECT days_late, review_score,
                 RANK() OVER (ORDER BY days_late)
                   + (COUNT(*) OVER (PARTITION BY days_late) - 1) / 2.0 AS rank_days,
                 RANK() OVER (ORDER BY review_score)
                   + (COUNT(*) OVER (PARTITION BY review_score) - 1) / 2.0 AS rank_score
          FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
          WHERE days_late IS NOT NULL AND review_score IS NOT NULL AND is_delivered
        )
        SELECT ROUND(CORR(CAST(days_late AS FLOAT64), CAST(review_score AS FLOAT64)), 4) AS pearson_r,
               ROUND(CORR(rank_days, rank_score), 4) AS spearman_r,
               COUNT(*) AS n
        FROM ranked
    """).iloc[0]
    return float(result["pearson_r"]), float(result["spearman_r"]), int(result["n"])


def main():
    """Generate the five presentation charts and print their supporting statistics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default="config/config.yaml")
    parser.add_argument("--out", type=Path, help="Chart directory (default: charts)")
    parser.add_argument("--render-only", action="store_true", help="Save analysis SQL with project placeholders filled in, without querying BigQuery.")
    args = parser.parse_args()
    settings = load_config(args.config)
    cloud = settings["bigquery"]
    if args.render_only:
        output = settings["root"] / "data/rendered_analysis"
        output.mkdir(parents=True, exist_ok=True)
        for path in sorted((settings["root"] / "sql/analysis").glob("*.sql")):
            (output / path.name).write_text(render_sql(path.read_text(), cloud))
        print(f"Analysis SQL saved in {output}. No BigQuery requests were made.")
        return 0
    out_dir = args.out or settings["root"] / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = _client(settings)

    # Each exported CSV contains exactly the rows shown in its corresponding PNG.
    chart_late_rate_by_corridor(client, cloud, out_dir)
    chart_late_rate_by_category(client, cloud, out_dir)
    chart_review_by_lateness(client, cloud, out_dir)
    promises = chart_promise_vs_actual_by_state(client, cloud, out_dir)
    chart_freight_vs_satisfaction(client, cloud, out_dir)
    early_states = (promises["avg_delivery_days"] < promises["avg_promise_days"]).sum()
    print(f"Average delivery is earlier than promised in {early_states} of {len(promises)} eligible states.")

    # Review comparisons deliberately use a different population: reviewed delivered orders.
    impact = _run_file(client, cloud, "07_late_share_of_bad_reviews.sql").iloc[0]
    print(f"Reviewed delivered orders: {int(impact['reviewed_orders']):,}")
    print(f"Late share: {float(impact['late_share_of_orders']):.1%}")
    print(f"Share of 1–2 star reviews from late orders: {float(impact['late_share_of_bad_reviews']):.1%}")
    states = _run_file(client, cloud, "08_within_state_penalty.sql")
    lower_scores = (states["score_penalty"] > 0).sum()
    print(f"Late orders score lower in {lower_scores} of {len(states)} states with at least 100 reviewed delivered orders.")

    pearson, spearman, count = compute_correlation(client, cloud)
    print(f"Days late vs review score (n={count:,}; early deliveries retain negative days):")
    print(f"  Pearson r = {pearson:+.4f}")
    print(f"  Spearman rho = {spearman:+.4f} (average tied ranks)")
    freight = _run_file(client, cloud, "05_freight_vs_satisfaction.sql").iloc[0]
    print(f"Freight ratio vs review score: Pearson r = {float(freight['pearson_r']):+.4f}")
    print("These are descriptive associations; state comparisons do not control for all other factors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
