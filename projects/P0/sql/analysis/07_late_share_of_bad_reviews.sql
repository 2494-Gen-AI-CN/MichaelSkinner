-- How big is the lateness problem? Late orders are a minority of all orders but
-- they produce a disproportionate share of 1–2 star reviews.
-- This single comparison makes the business case: fixing late deliveries removes
-- a share of bad reviews that is much larger than the late-order share itself.
-- Uses fact_order_item grouped by order_id so each review is counted once.
WITH orders AS (
  SELECT order_id,
         ANY_VALUE(review_score) AS score,
         ANY_VALUE(is_late)      AS is_late
  FROM `${PROJECT}.${WAREHOUSE}.fact_order_item`
  WHERE review_score IS NOT NULL
    AND is_delivered
  GROUP BY order_id
)
SELECT
  COUNT(*)                                                              AS reviewed_orders,
  ROUND(AVG(CAST(is_late AS INT64)), 4)                                AS late_share_of_orders,
  ROUND(SAFE_DIVIDE(COUNTIF(is_late AND score <= 2),
                    COUNTIF(score <= 2)), 4)                           AS late_share_of_bad_reviews,
  COUNTIF(score <= 2)                                                  AS total_bad_reviews,
  COUNTIF(is_late AND score <= 2)                                      AS bad_reviews_from_late
FROM orders;
