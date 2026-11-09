# Warehouse data dictionary

All objects are in the configured warehouse dataset, currently `olist-delivery-insights.p0_warehouse`. Money is denominated in Brazilian reais (BRL). Calendar dates come from the source's local DATETIME values; no timezone is inferred.

## fact_order_item

One row per `(order_id, order_item_id)`. All 112,650 accepted staging items are retained. Eight have rejected parent orders and are explicitly flagged. Keys described here are logical relationships verified by the build checks; database primary/foreign-key constraints are not declared.

| Field | BigQuery type | Meaning |
| --- | --- | --- |
| `order_item_key` | STRING | Stable SHA-256 fingerprint of order ID and item sequence; logical primary key |
| `order_id`, `order_item_id` | STRING, INT64 | Natural item key |
| `product_id`, `seller_id` | STRING | Original item identifiers for traceability |
| `product_key` | STRING | Join to `dim_product` |
| `customer_key` | STRING | Join to `dim_customer`; `unknown` if order/customer unavailable |
| `seller_key` | STRING | Join to the seller version valid on purchase date; `unknown` if date/version unavailable |
| `purchase_date_key` | INT64 | Join to `dim_date`; 0 for unknown |
| `price`, `freight_value` | NUMERIC | Item merchandise price and freight charge; additive across item rows |
| `shipping_limit_date` | DATETIME | Source seller shipping deadline |
| `freight_ratio` | NUMERIC | `freight_value / price`; ratios must not be summed |
| `purchase_date`, `delivered_date`, `estimated_delivery_date` | DATE | Calendar dates from the parent order |
| `order_status` | STRING | Cleaned source status, or null if order missing |
| `order_missing` | BOOL | True when no accepted staging order exists |
| `is_delivered` | BOOL | Known order has status `delivered` and a customer delivery timestamp; null if order missing |
| `delivery_days` | INT64 | Delivered date minus purchase date, only for completed delivered orders |
| `promise_days` | INT64 | Estimated delivery date minus purchase date for known orders |
| `days_late` | INT64 | Delivered date minus estimated date; negative means early; null without a completed delivery |
| `is_late` | BOOL | `days_late > 0`, or null when delivery outcome unknown |
| `lateness_bucket` | STRING | `early`, `on_time`, `1-3 days late`, `4-7 days late`, `8+ days late`, `not_delivered`, or `unknown` |
| `review_id`, `review_score` | STRING, INT64 | Latest review for this order, chosen before joining to items; nullable |
| `review_answer_timestamp` | DATETIME | Timestamp of that chosen review |
| `order_payment_value` | NUMERIC | Sum of this order's source payments; repeated on every item; null if no payment record |
| `payment_record_count` | INT64 | Number of payment records for the order; repeated on items |
| `order_item_count` | INT64 | Number of staging items in the order; repeated on items |
| `order_price_total`, `order_freight_total` | NUMERIC | Item-level amounts summed to order level; repeated on items |
| `order_freight_ratio` | NUMERIC | Order freight total divided by order merchandise total; repeated on items |

Delivery after midnight on the promised date is still on time if it arrives on that same calendar date. Undelivered orders have null delivery outcomes; they are not treated as on time.

### Aggregation rules

- Item price and freight are additive at item grain.
- Review score, payment totals, item count, and other order totals are **not** additive across item rows. Averaging review scores directly from the fact weights orders by item count.
- Use `order_delivery` for one row per known order with items, or deduplicate the relevant order fields after the required fact/dimension joins.
- `AVG(DISTINCT review_score)` is incorrect: it averages distinct score values rather than orders. `COUNT(DISTINCT order_id)` does not fix a separate repeated `SUM(order_payment_value)` or `AVG(review_score)`.
- A single order can span multiple sellers or categories. Define whether a group counts items, seller-order pairs, category-order pairs, or whole orders. Group totals can overlap and need not add to the number of unique orders.

## Dimensions

### dim_product

One row per source product plus the unknown member. `product_key` fingerprints the product ID. Fields include `product_id`, `category_original`, `category_en`, `weight_g`, `photos_qty`, `length_cm`, `height_cm`, `width_cm`, and `translation_missing`.

Missing categories are labelled `unknown`; missing physical measurements remain null. A category without an English translation keeps its original label and sets `translation_missing = TRUE`. This affects 13 products; 610 source products have missing categories. The extra unknown member covers missing product references and is not counted in those 610.

### dim_customer

One row per `customer_id`, plus the unknown member. Fields are `customer_key`, `customer_id`, `customer_unique_id`, `customer_state`, `customer_city`, and `customer_zip_code_prefix`.

`customer_unique_id` can identify the same person across multiple customer records; it is not the dimension's unique key. ZIP prefixes remain strings so leading zeros are preserved.

### dim_date

One row per day spanning the earliest purchase through the latest purchase, delivery, or estimated delivery date, plus an unknown member. Fields are `date_key`, `date`, `year`, `quarter`, `month`, `month_name`, `weekday_number`, and `weekday_name`.

`date_key` is the integer `YYYYMMDD`. Unknown is key 0 with null date. `weekday_number` follows BigQuery's Sunday=1 through Saturday=7 convention. The fact's date key refers to purchase date; other date roles can be joined using their DATE fields if needed.

### dim_seller

One row per seller/tier interval, plus an unknown member. Fields are `seller_key`, `seller_id`, `seller_state`, `seller_city`, `seller_zip_code_prefix`, `perf_tier`, `effective_from`, `effective_to`, and `is_current`.

The seller key fingerprints the seller ID and interval start, so several versions can share one natural seller ID. The fact is already bound to the version valid at purchase. Join it using `seller_key`, not `seller_id`, to preserve item counts. Filtering `is_current = TRUE` on historical fact joins would remove sales bound to older versions.

Intervals are `[effective_from, effective_to)`. The current interval ends at `9999-12-31`. The unknown member has null seller ID, tier `Unknown`, and is separate from the Standard tier.

`is_current` identifies the latest reconstructed version in the supplied history. It does not assert anything about the seller's present-day performance.

Seller location comes from a static source snapshot. Only `perf_tier` has reconstructed changes; the data does not provide actual seller address history.

## Supporting objects

| Object | Grain | Purpose |
| --- | --- | --- |
| `prepared_orders` | Accepted order | Order timestamps, payment totals, latest review, and item totals before the fact join |
| `order_delivery` | Accepted order with at least one item | Deduplicated order-level measures for statistics; excludes missing parents and itemless orders |
| `seller_quarterly_performance` | Seller and delivery quarter | Completed delivered item count, late item count, and late rate |

`prepared_orders` selects reviews by descending answer timestamp, then creation date, then review ID for deterministic ties. Payment records are summed before joining to orders. There is no multiplication from multi-payment or multi-review orders.

The performance table has fields `seller_id`, `performance_quarter`, `delivered_items`, `late_items`, and `late_rate`. A quarter is the start DATE of a calendar quarter. Completed items are grouped by **delivery date**, and the resulting policy decision applies to the **next** quarter. At least 20 completed items and a late rate of at least 0.15 produces Watchlist; otherwise Standard. A missing performance row means no completed delivered items, not an observed zero late rate.

The `order_delivery` view deliberately omits product and seller keys because an order can have multiple products and sellers. Use the fact for those questions and explicitly choose the grouping grain.
