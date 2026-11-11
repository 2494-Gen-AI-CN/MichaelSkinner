-- Q2: How do review scores differ between early, on-time, and late deliveries?
-- Lower average scores in late groups identify a customer-satisfaction association,
-- not a causal effect. Join the purchase-date dimension and then deduplicate orders
-- so multi-item orders do not receive extra weight. Use known delivered, reviewed orders.
WITH orders AS (
  SELECT DISTINCT f.order_id, f.lateness_bucket, f.review_score
  FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
  JOIN `${PROJECT}.${WAREHOUSE}.dim_date` AS d ON d.date_key = f.purchase_date_key
  WHERE f.is_delivered AND f.review_score IS NOT NULL AND d.date IS NOT NULL
)
SELECT
  lateness_bucket,
  COUNT(*)                                        AS orders,
  ROUND(AVG(review_score), 3)                     AS avg_review_score,
  COUNTIF(review_score >= 4)                      AS high_score_orders,
  ROUND(SAFE_DIVIDE(COUNTIF(review_score >= 4), COUNT(*)), 4) AS high_score_rate
FROM orders
GROUP BY lateness_bucket
ORDER BY
  CASE lateness_bucket
    WHEN 'early'         THEN 1
    WHEN 'on_time'       THEN 2
    WHEN '1-3 days late' THEN 3
    WHEN '4-7 days late' THEN 4
    WHEN '8+ days late'  THEN 5
    ELSE 6
  END;
