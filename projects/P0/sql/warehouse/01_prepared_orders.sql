-- Prepare one row per accepted order before joining to individual items.
-- Aggregate payments first and choose the latest review deterministically.
CREATE OR REPLACE VIEW `${PROJECT}.${WAREHOUSE}.prepared_orders` AS
WITH payment_totals AS (
    SELECT order_id, SUM(payment_value) AS order_payment_value,
           COUNT(*) AS payment_record_count
    FROM `${PROJECT}.${STAGING}.payments`
    GROUP BY order_id
), latest_review AS (
    -- Several reviews can belong to one order. Keep the most recently answered one.
    SELECT order_id, review_id, review_score, review_answer_timestamp
    FROM `${PROJECT}.${STAGING}.reviews`
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY order_id
        ORDER BY review_answer_timestamp DESC, review_creation_date DESC, review_id DESC
    ) = 1
), item_totals AS (
    -- These totals describe the whole order, rather than a single item.
    SELECT order_id, COUNT(*) AS order_item_count,
           SUM(price) AS order_price_total, SUM(freight_value) AS order_freight_total
    FROM `${PROJECT}.${STAGING}.order_items`
    GROUP BY order_id
)
-- Each helper above has at most one row per order, so these joins cannot multiply orders.
SELECT o.*,
       DATE(o.order_purchase_timestamp) AS purchase_date,
       DATE(o.order_delivered_customer_date) AS delivered_date,
       DATE(o.order_estimated_delivery_date) AS estimated_delivery_date,
       o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL AS is_delivered,
       p.order_payment_value, COALESCE(p.payment_record_count, 0) AS payment_record_count,
       r.review_id, r.review_score, r.review_answer_timestamp,
       COALESCE(i.order_item_count, 0) AS order_item_count,
       i.order_price_total, i.order_freight_total,
       SAFE_DIVIDE(i.order_freight_total, i.order_price_total) AS order_freight_ratio
FROM `${PROJECT}.${STAGING}.orders` AS o
LEFT JOIN payment_totals AS p USING (order_id)
LEFT JOIN latest_review AS r USING (order_id)
LEFT JOIN item_totals AS i USING (order_id);
