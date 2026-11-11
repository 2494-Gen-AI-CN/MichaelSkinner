-- Q5: How do seller outcomes compare across periods under the simulated watchlist policy?
-- Compare item-level outcomes under the tier valid at purchase to support seller reviews.
-- Review averages here are item-weighted. A seller can appear in both tier groups.
-- dim_seller records one row per seller per tier-change interval (SCD type 2).
-- fact_order_item already stores the seller_key bound to the version valid at purchase_date,
-- so joining via seller_key (not seller_id) gives the correct tier for each transaction.
-- Using seller_id alone would multiply rows across all history versions.
-- Watchlist tier is assigned for a quarter when the previous quarter had >= 20 delivered
-- items and a late rate of >= 15%.  Standard applies in all other cases including
-- quarters with insufficient prior data.  This is a project-defined simulation,
-- not an observed Olist intervention or evidence of a causal effect.
SELECT
  ds.perf_tier,
  COUNT(DISTINCT ds.seller_id)                              AS distinct_sellers,
  COUNT(*)                                                  AS delivered_items,
  COUNTIF(f.is_late)                                        AS late_items,
  ROUND(SAFE_DIVIDE(COUNTIF(f.is_late), COUNT(*)), 4)       AS late_rate,
  ROUND(AVG(CAST(f.review_score AS FLOAT64)), 3)            AS avg_review_score,
  ROUND(AVG(f.delivery_days), 1)                            AS avg_delivery_days
FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
JOIN `${PROJECT}.${WAREHOUSE}.dim_seller` AS ds USING (seller_key)
WHERE f.is_delivered
  AND ds.perf_tier IN ('Standard', 'Watchlist')
GROUP BY ds.perf_tier
ORDER BY ds.perf_tier;
