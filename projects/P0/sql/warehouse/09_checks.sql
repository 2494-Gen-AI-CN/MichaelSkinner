-- Return build assertions as rows; the Python builder fails if any passed value is false.
WITH fact_counts AS (
    SELECT COUNT(*) AS fact_rows, COUNT(DISTINCT order_item_key) AS keys,
           COUNT(DISTINCT CONCAT(order_id, '|', CAST(order_item_id AS STRING))) AS natural_keys,
           COUNTIF(order_missing) AS missing_orders
    FROM `${PROJECT}.${WAREHOUSE}.fact_order_item`
), periods AS (
    -- Compare consecutive seller versions to catch overlaps or gaps.
    SELECT *, LAG(effective_to) OVER (PARTITION BY seller_id ORDER BY effective_from) AS previous_end
    FROM `${PROJECT}.${WAREHOUSE}.dim_seller`
    WHERE seller_id IS NOT NULL
), checks AS (
    -- Each SELECT produces one named check with an observed and expected count.
    SELECT 'fact_preserves_all_staging_items' AS check_name,
           (SELECT fact_rows FROM fact_counts) AS observed,
           (SELECT COUNT(*) FROM `${PROJECT}.${STAGING}.order_items`) AS expected
    UNION ALL
    SELECT 'fact_surrogate_keys_unique', (SELECT keys FROM fact_counts), (SELECT fact_rows FROM fact_counts)
    UNION ALL
    SELECT 'fact_grain_unique', (SELECT natural_keys FROM fact_counts), (SELECT fact_rows FROM fact_counts)
    UNION ALL
    SELECT 'product_keys_unique', COUNT(DISTINCT product_key), COUNT(*) FROM `${PROJECT}.${WAREHOUSE}.dim_product`
    UNION ALL
    SELECT 'customer_keys_unique', COUNT(DISTINCT customer_key), COUNT(*) FROM `${PROJECT}.${WAREHOUSE}.dim_customer`
    UNION ALL
    SELECT 'seller_keys_unique', COUNT(DISTINCT seller_key), COUNT(*) FROM `${PROJECT}.${WAREHOUSE}.dim_seller`
    UNION ALL
    SELECT 'date_keys_unique', COUNT(DISTINCT date_key), COUNT(*) FROM `${PROJECT}.${WAREHOUSE}.dim_date`
    UNION ALL
    SELECT 'all_fact_dimension_links_resolve', COUNT(*), 0
    FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.dim_product` AS p USING (product_key)
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.dim_customer` AS c USING (customer_key)
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.dim_seller` AS s USING (seller_key)
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.dim_date` AS d ON d.date_key = f.purchase_date_key
    WHERE p.product_key IS NULL OR c.customer_key IS NULL OR s.seller_key IS NULL OR d.date_key IS NULL
    UNION ALL
    SELECT 'one_current_version_per_seller', COUNT(*), 0 FROM (
        SELECT seller_id FROM periods GROUP BY seller_id HAVING COUNTIF(is_current) != 1
    )
    UNION ALL
    SELECT 'seller_periods_have_positive_length', COUNTIF(effective_from >= effective_to), 0 FROM periods
    UNION ALL
    SELECT 'seller_periods_are_contiguous', COUNTIF(previous_end IS NOT NULL AND previous_end != effective_from), 0 FROM periods
    UNION ALL
    SELECT 'seller_current_flags_match_open_period',
           COUNTIF(is_current != (effective_to = DATE '9999-12-31')), 0 FROM periods
    UNION ALL
    SELECT 'seller_versions_match_purchase_date', COUNT(*), 0
    FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
    JOIN `${PROJECT}.${WAREHOUSE}.dim_seller` AS s USING (seller_key)
    WHERE NOT f.order_missing AND (
        s.seller_id IS NULL OR s.seller_id != f.seller_id
        OR f.purchase_date < s.effective_from OR f.purchase_date >= s.effective_to
    )
    UNION ALL
    SELECT 'orphan_order_items_are_accounted_for', (SELECT missing_orders FROM fact_counts), COUNT(*)
    FROM `${PROJECT}.${STAGING}.order_items` AS i
    LEFT JOIN `${PROJECT}.${STAGING}.orders` AS o USING (order_id)
    WHERE o.order_id IS NULL
    UNION ALL
    SELECT 'orphan_order_fields_stay_unknown', COUNT(*), 0
    FROM `${PROJECT}.${WAREHOUSE}.fact_order_item`
    WHERE order_missing AND (
        customer_key != 'unknown' OR seller_key != 'unknown' OR purchase_date_key != 0
        OR is_delivered IS NOT NULL OR is_late IS NOT NULL OR days_late IS NOT NULL
        OR review_score IS NOT NULL OR order_payment_value IS NOT NULL
    )
    UNION ALL
    SELECT 'order_view_has_one_row_per_known_order', COUNT(*), COUNT(DISTINCT order_id)
    FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
    UNION ALL
    SELECT 'order_view_covers_known_fact_orders',
           (SELECT COUNT(*) FROM `${PROJECT}.${WAREHOUSE}.order_delivery`),
           COUNT(DISTINCT order_id)
    FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` WHERE NOT order_missing
    UNION ALL
    SELECT 'late_flags_match_signed_day_difference', COUNT(*), 0
    FROM `${PROJECT}.${WAREHOUSE}.fact_order_item`
    WHERE is_late IS DISTINCT FROM (days_late > 0)
    UNION ALL
    SELECT 'undelivered_orders_have_no_delivery_outcome', COUNT(*), 0
    FROM `${PROJECT}.${WAREHOUSE}.fact_order_item`
    WHERE NOT is_delivered AND (is_late IS NOT NULL OR days_late IS NOT NULL OR delivery_days IS NOT NULL)
    UNION ALL
    SELECT 'seller_tiers_use_only_previous_delivery_quarter', COUNT(*), 0
    FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
    JOIN `${PROJECT}.${WAREHOUSE}.dim_seller` AS s USING (seller_key)
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.seller_quarterly_performance` AS p
      ON p.seller_id = f.seller_id
     AND p.performance_quarter = DATE_SUB(DATE_TRUNC(f.purchase_date, QUARTER), INTERVAL 3 MONTH)
    WHERE NOT f.order_missing
      AND s.perf_tier != CASE WHEN p.delivered_items >= 20 AND p.late_rate >= 0.15
                             THEN 'Watchlist' ELSE 'Standard' END
)
SELECT check_name, observed, expected, observed = expected AS passed
FROM checks
ORDER BY check_name;
