-- Q2: How do review scores differ between early, on-time, and late deliveries?
-- Uses order_delivery (one row per known order with items) so each review is counted
-- once regardless of how many items are in the order.
-- Orders without a review or without a known delivery outcome are excluded.
SELECT
  lateness_bucket,
  COUNT(*)                                        AS orders,
  ROUND(AVG(review_score), 3)                     AS avg_review_score,
  COUNTIF(review_score >= 4)                      AS high_score_orders,
  ROUND(SAFE_DIVIDE(COUNTIF(review_score >= 4), COUNT(*)), 4) AS high_score_rate
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
    ELSE 6
  END;
