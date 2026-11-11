-- Q6: What share of reviewed orders are late, and what share of low reviews do they account for?
-- A disproportionate share helps prioritise investigation; it does not prove that
-- eliminating lateness would eliminate those low reviews. Join purchase dates and
-- group by order_id so each reviewed delivered order is counted once.
WITH orders AS (
  SELECT f.order_id,
         ANY_VALUE(f.review_score) AS score,
         ANY_VALUE(f.is_late)      AS is_late
  FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
  JOIN `${PROJECT}.${WAREHOUSE}.dim_date` AS d ON d.date_key = f.purchase_date_key
  WHERE f.review_score IS NOT NULL AND f.is_delivered AND d.date IS NOT NULL
  GROUP BY f.order_id
)
SELECT
  COUNT(*)                                                              AS reviewed_orders,
  ROUND(AVG(CAST(is_late AS INT64)), 4)                                AS late_share_of_orders,
  ROUND(SAFE_DIVIDE(COUNTIF(is_late AND score <= 2),
                    COUNTIF(score <= 2)), 4)                           AS late_share_of_bad_reviews,
  COUNTIF(score <= 2)                                                  AS total_bad_reviews,
  COUNTIF(is_late AND score <= 2)                                      AS bad_reviews_from_late
FROM orders;
