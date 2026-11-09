-- Grain: exactly one row for each accepted staging (order_id, order_item_id).
-- LEFT JOINs retain items whose parent order failed cleaning; their order fields stay unknown.
-- Order-level payment/review fields repeat across items and must be deduplicated for analysis.
CREATE OR REPLACE TABLE `${PROJECT}.${WAREHOUSE}.fact_order_item` AS
WITH joined AS (
    SELECT TO_HEX(SHA256(CONCAT(i.order_id, '|', CAST(i.order_item_id AS STRING)))) AS order_item_key,
           i.order_id, i.order_item_id, i.product_id, i.seller_id,
           COALESCE(p.product_key, 'unknown') AS product_key,
           COALESCE(c.customer_key, 'unknown') AS customer_key,
           COALESCE(s.seller_key, 'unknown') AS seller_key,
           COALESCE(d.date_key, 0) AS purchase_date_key,
           i.price, i.freight_value, i.shipping_limit_date,
           SAFE_DIVIDE(i.freight_value, i.price) AS freight_ratio,
           o.purchase_date, o.delivered_date, o.estimated_delivery_date,
           o.order_status, o.is_delivered, o.order_id IS NULL AS order_missing,
           o.review_id, o.review_score, o.review_answer_timestamp,
           o.order_payment_value, o.payment_record_count, o.order_item_count,
           o.order_price_total, o.order_freight_total, o.order_freight_ratio,
           DATE_DIFF(o.estimated_delivery_date, o.purchase_date, DAY) AS promise_days,
           CASE WHEN o.is_delivered THEN DATE_DIFF(o.delivered_date, o.purchase_date, DAY) END AS delivery_days,
           CASE WHEN o.is_delivered THEN DATE_DIFF(o.delivered_date, o.estimated_delivery_date, DAY) END AS days_late
    FROM `${PROJECT}.${STAGING}.order_items` AS i
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.prepared_orders` AS o USING (order_id)
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.dim_product` AS p ON p.product_id = i.product_id
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.dim_customer` AS c ON c.customer_id = o.customer_id
    -- Bind the item to the seller version that existed when the order was purchased.
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.dim_seller` AS s
      ON s.seller_id = i.seller_id
     AND o.purchase_date >= s.effective_from AND o.purchase_date < s.effective_to
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.dim_date` AS d ON d.date = o.purchase_date
)
-- Delivery outcomes stay unknown until an order is actually delivered.
SELECT *,
       CASE WHEN is_delivered THEN days_late > 0 END AS is_late,
       CASE WHEN order_missing THEN 'unknown'
            WHEN NOT is_delivered THEN 'not_delivered'
            WHEN days_late < 0 THEN 'early'
            WHEN days_late = 0 THEN 'on_time'
            WHEN days_late <= 3 THEN '1-3 days late'
            WHEN days_late <= 7 THEN '4-7 days late'
            ELSE '8+ days late' END AS lateness_bucket
FROM joined;
