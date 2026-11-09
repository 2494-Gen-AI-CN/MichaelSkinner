-- One row per known order represented in the item fact, for order-level statistics.
-- Seller and product keys are deliberately excluded: one order may span multiple sellers/categories.
CREATE OR REPLACE VIEW `${PROJECT}.${WAREHOUSE}.order_delivery` AS
SELECT order_id, customer_key, purchase_date_key,
       purchase_date, delivered_date, estimated_delivery_date, order_status,
       is_delivered, is_late, days_late, lateness_bucket, delivery_days, promise_days,
       review_id, review_score, review_answer_timestamp,
       order_payment_value, payment_record_count, order_item_count,
       order_price_total, order_freight_total, order_freight_ratio
FROM `${PROJECT}.${WAREHOUSE}.fact_order_item`
WHERE NOT order_missing
QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_item_id) = 1;
