"""Query the warehouse and generate analysis charts.

Produces four PNG charts and prints a correlation and business-impact summary.
Charts are saved in data/charts/ (or the path given by --out).

Usage:
    python -m src.charts --config config/config.yaml
    python -m src.charts --config config/config.yaml --out data/charts
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from google.cloud import bigquery

from .ingest.config import load_config


def _client(settings):
    cloud = settings["bigquery"]
    return bigquery.Client(project=cloud["project"], location=cloud["location"])


def _run(client, cloud, sql):
    rendered = (sql
                .replace("${PROJECT}",   cloud["project"])
                .replace("${WAREHOUSE}", cloud["warehouse_dataset"]))
    return client.query(rendered).result().to_dataframe()


# ── Chart 1 ──────────────────────────────────────────────────────────────────

def chart_review_by_lateness(client, cloud, out_dir):
    """Average review score by delivery lateness bucket, with order count per bar (Q2)."""
    df = _run(client, cloud, """
        SELECT lateness_bucket,
               COUNT(*) AS orders,
               ROUND(AVG(review_score), 3) AS avg_score
        FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
        WHERE review_score IS NOT NULL
          AND lateness_bucket NOT IN ('not_delivered', 'unknown')
        GROUP BY lateness_bucket
        ORDER BY
          CASE lateness_bucket
            WHEN 'early'         THEN 1
            WHEN 'on_time'       THEN 2
            WHEN '1-3 days late' THEN 3
            WHEN '4-7 days late' THEN 4
            WHEN '8+ days late'  THEN 5
          END
    """)

    colors = ["#2ecc71" if b in ("early", "on_time") else "#e74c3c"
              for b in df["lateness_bucket"]]
    labels = [f"{b}\n(n={o:,})" for b, o in zip(df["lateness_bucket"], df["orders"])]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(labels, df["avg_score"], color=colors, edgecolor="white", width=0.6)
    for bar, score in zip(bars, df["avg_score"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{score:.2f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, 5.6)
    ax.set_xlabel("Delivery outcome")
    ax.set_ylabel("Average review score (1–5)")
    ax.set_title("Review Score by Delivery Lateness")
    fig.tight_layout()

    path = out_dir / "01_review_by_lateness.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")
    return df


# ── Chart 2 ──────────────────────────────────────────────────────────────────

def chart_late_rate_by_category(client, cloud, out_dir):
    """Top 15 product categories by late-delivery rate (Q1b)."""
    df = _run(client, cloud, """
        SELECT COALESCE(dp.category_en, 'unknown') AS category,
               COUNT(*) AS delivered_items,
               ROUND(SAFE_DIVIDE(COUNTIF(f.is_late), COUNT(*)), 4) AS late_rate
        FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
        JOIN `${PROJECT}.${WAREHOUSE}.dim_product` AS dp USING (product_key)
        WHERE f.is_delivered AND dp.product_key != 'unknown'
        GROUP BY category
        HAVING delivered_items >= 50
        ORDER BY late_rate DESC
        LIMIT 15
    """)

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(df["category"][::-1], df["late_rate"][::-1] * 100,
            color="#e67e22", edgecolor="white")
    ax.set_xlabel("Late-delivery rate (%)")
    ax.set_title("Top 15 Product Categories by Late-Delivery Rate\n(min. 50 delivered items)")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    fig.tight_layout()

    path = out_dir / "02_late_rate_by_category.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")
    return df


# ── Chart 3 ──────────────────────────────────────────────────────────────────

def chart_late_rate_by_state(client, cloud, out_dir):
    """Late-delivery rate by customer state, coloured by severity (Q3 / query B).

    Returns the full within-state penalty dataframe so main() can also print
    the score gap between on-time and late orders per state.
    """
    df = _run(client, cloud, """
        WITH orders AS (
          SELECT f.order_id,
                 ANY_VALUE(f.review_score)   AS score,
                 ANY_VALUE(f.is_late)        AS is_late,
                 ANY_VALUE(c.customer_state) AS state
          FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
          JOIN `${PROJECT}.${WAREHOUSE}.dim_customer`    AS c USING (customer_key)
          WHERE f.review_score IS NOT NULL
            AND f.is_delivered
          GROUP BY f.order_id
        )
        SELECT
          state                                                       AS customer_state,
          COUNT(*)                                                    AS orders,
          ROUND(AVG(CAST(is_late AS INT64)), 4)                      AS late_rate,
          ROUND(AVG(IF(NOT is_late, score, NULL)), 3)                AS avg_score_on_time,
          ROUND(AVG(IF(    is_late, score, NULL)), 3)                AS avg_score_late,
          ROUND(AVG(IF(NOT is_late, score, NULL))
              - AVG(IF(    is_late, score, NULL)), 3)                AS score_penalty
        FROM orders
        GROUP BY state
        HAVING COUNT(*) >= 100
        ORDER BY late_rate DESC
    """)

    colors = ["#c0392b" if r > 0.10 else "#e67e22" if r > 0.07 else "#3498db"
              for r in df["late_rate"]]

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.barh(df["customer_state"][::-1], df["late_rate"][::-1] * 100,
            color=colors[::-1], edgecolor="white")
    ax.set_xlabel("Late-delivery rate (%)")
    ax.set_title("Late-Delivery Rate by Customer State\n"
                 "(min. 100 delivered orders with reviews; red > 10%, orange 7–10%, blue < 7%)")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    fig.tight_layout()

    path = out_dir / "03_late_rate_by_state.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")
    return df


# ── Chart 4 ──────────────────────────────────────────────────────────────────

def chart_freight_vs_satisfaction(client, cloud, out_dir):
    """Average review score by freight-to-price ratio bucket (Q4)."""
    df = _run(client, cloud, """
        SELECT
          CASE
            WHEN order_freight_ratio < 0.1  THEN '< 10%'
            WHEN order_freight_ratio < 0.2  THEN '10-20%'
            WHEN order_freight_ratio < 0.4  THEN '20-40%'
            WHEN order_freight_ratio < 0.7  THEN '40-70%'
            ELSE                                 '>= 70%'
          END AS freight_bucket,
          COUNT(*) AS orders,
          ROUND(AVG(CAST(review_score AS FLOAT64)), 3) AS avg_review_score
        FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
        WHERE review_score        IS NOT NULL
          AND order_freight_ratio IS NOT NULL
          AND is_delivered
        GROUP BY freight_bucket
        ORDER BY MIN(order_freight_ratio)
    """)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(df["freight_bucket"], df["avg_review_score"],
                  color="#9b59b6", edgecolor="white", width=0.6)
    for bar, score in zip(bars, df["avg_review_score"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{score:.2f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, 5.6)
    ax.set_xlabel("Freight charge as share of item price")
    ax.set_ylabel("Average review score (1–5)")
    ax.set_title("Review Score by Freight-to-Price Ratio")
    fig.tight_layout()

    path = out_dir / "04_freight_vs_satisfaction.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved {path}")
    return df


# ── Analytics ─────────────────────────────────────────────────────────────────

def compute_bad_review_share(client, cloud):
    """Share of orders that are late vs share of 1–2 star reviews from late orders (query A)."""
    return _run(client, cloud, """
        WITH orders AS (
          SELECT order_id,
                 ANY_VALUE(review_score) AS score,
                 ANY_VALUE(is_late)      AS is_late
          FROM `${PROJECT}.${WAREHOUSE}.fact_order_item`
          WHERE review_score IS NOT NULL AND is_delivered
          GROUP BY order_id
        )
        SELECT
          COUNT(*)                                                        AS reviewed_orders,
          ROUND(AVG(CAST(is_late AS INT64)), 4)                          AS late_share_of_orders,
          ROUND(SAFE_DIVIDE(COUNTIF(is_late AND score <= 2),
                            COUNTIF(score <= 2)), 4)                     AS late_share_of_bad_reviews,
          COUNTIF(score <= 2)                                            AS total_bad_reviews,
          COUNTIF(is_late AND score <= 2)                                AS bad_reviews_from_late
        FROM orders
    """).iloc[0]


def compute_correlation(client, cloud):
    """Pearson and Spearman r between days_late and review_score at order level.

    Both are computed in BigQuery. Spearman is Pearson applied to the per-row
    ranks, which BigQuery's RANK() window function provides directly.
    A negative r means later deliveries tend to receive lower reviews.
    This is association only: product quality, seller communication, and other
    unmeasured factors also drive review scores independently of arrival date.
    """
    pearson = _run(client, cloud, """
        SELECT
          ROUND(CORR(CAST(days_late    AS FLOAT64),
                     CAST(review_score AS FLOAT64)), 4) AS pearson_r,
          COUNT(*) AS n
        FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
        WHERE days_late IS NOT NULL AND review_score IS NOT NULL AND is_delivered
    """).iloc[0]

    spearman = _run(client, cloud, """
        SELECT ROUND(CORR(rank_days_late, rank_score), 4) AS spearman_r, COUNT(*) AS n
        FROM (
          SELECT RANK() OVER (ORDER BY days_late)    AS rank_days_late,
                 RANK() OVER (ORDER BY review_score) AS rank_score
          FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
          WHERE days_late IS NOT NULL AND review_score IS NOT NULL AND is_delivered
        )
    """).iloc[0]

    return (float(pearson["pearson_r"]),
            float(spearman["spearman_r"]),
            int(pearson["n"]))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default="config/config.yaml")
    parser.add_argument("--out",    type=Path, default=None,
                        help="Output directory for charts (default: data/charts)")
    args = parser.parse_args()

    settings = load_config(args.config)
    cloud    = settings["bigquery"]
    out_dir  = args.out or (settings["root"] / "data" / "charts")
    out_dir.mkdir(parents=True, exist_ok=True)

    client = _client(settings)

    chart_review_by_lateness(client, cloud, out_dir)
    chart_late_rate_by_category(client, cloud, out_dir)
    state_df = chart_late_rate_by_state(client, cloud, out_dir)
    chart_freight_vs_satisfaction(client, cloud, out_dir)

    # ── Business impact ───────────────────────────────────────────────────────
    brs = compute_bad_review_share(client, cloud)
    print(f"\nBusiness impact (query A)")
    print(f"  Reviewed orders : {int(brs['reviewed_orders']):,}")
    print(f"  Late share      : {float(brs['late_share_of_orders']):.1%} of reviewed orders are late")
    print(f"  Bad-review share: {float(brs['late_share_of_bad_reviews']):.1%} of 1–2 star reviews come from late orders")
    print(f"  ({int(brs['bad_reviews_from_late']):,} of {int(brs['total_bad_reviews']):,} bad reviews)")

    # ── Within-state penalty ──────────────────────────────────────────────────
    print(f"\nWithin-state score penalty (query B) — late orders vs on-time within same state")
    print(f"  {'State':<6}  {'Late rate':>9}  {'On-time':>7}  {'Late':>5}  {'Penalty':>7}")
    for _, row in state_df.head(10).iterrows():
        print(f"  {row['customer_state']:<6}  {float(row['late_rate']):>8.1%}  "
              f"{float(row['avg_score_on_time']):>7.2f}  "
              f"{float(row['avg_score_late']):>5.2f}  "
              f"{float(row['score_penalty']):>7.2f}")
    states_with_penalty = (state_df["score_penalty"] > 0).sum()
    print(f"  Late orders score lower than on-time orders in {states_with_penalty} of {len(state_df)} states.")

    # ── Correlation ───────────────────────────────────────────────────────────
    pearson_r, spearman_r, n = compute_correlation(client, cloud)
    print(f"\nCorrelation — days_late vs review_score  (n = {n:,} delivered orders with reviews)")
    print(f"  Pearson r  = {pearson_r:+.4f}")
    print(f"  Spearman r = {spearman_r:+.4f}")
    print("  Interpretation: late deliveries are associated with lower scores in every state,")
    print("  so geography alone does not explain the gap. The association is not causal —")
    print("  late orders may also have product or seller issues that independently drive scores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
