"""Test cleaning rules using small local records."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.ingest.clean import clean_source, read_source


def test_items_are_cleaned_and_all_rows_are_accounted_for(sources):
    """Keep valid items, reject bad prices and dates, and remove exact duplicates."""
    path = Path(__file__).parent / "fixtures/items.csv"
    result = clean_source(read_source(path, sources["order_items"]), sources["order_items"])
    assert len(result["clean"]) == 1
    assert result["clean"].iloc[0]["order_id"] == "001"
    assert result["clean"].iloc[0]["price"] == pytest.approx(10.10)
    assert len(result["rejects"]) == 3
    assert result["duplicates_removed"] == 1
    assert len(result["clean"]) + len(result["rejects"]) + result["duplicates_removed"] == 5


def test_reject_keeps_the_original_row(sources):
    """Keep raw invalid values so rejected records can be inspected later."""
    path = Path(__file__).parent / "fixtures/items.csv"
    raw = read_source(path, sources["order_items"]).iloc[:1].copy()
    raw.loc[0, "price"] = "not-a-price"
    result = clean_source(raw, sources["order_items"])
    assert len(result["rejects"]) == 1
    reject = result["rejects"][0]
    assert "price" in reject["reason"]
    assert json.loads(reject["raw_record"])["price"] == "not-a-price"
    assert reject["row_number"] == 2


def test_missing_columns_fail_the_source(sources):
    """Report a missing-column error instead of loading a partial schema."""
    with pytest.raises(ValueError, match="Missing columns"):
        clean_source(pd.DataFrame({"order_id": ["1"]}), sources["orders"])


def test_conflicting_keys_are_rejected(sources):
    """Reject different records with the same source key instead of guessing which is correct."""
    raw = pd.DataFrame([
        {"product_category_name": "books", "product_category_name_english": "Books"},
        {"product_category_name": "books", "product_category_name_english": "Other"},
    ])
    result = clean_source(raw, sources["category_translation"])
    assert result["clean"].empty
    assert len(result["rejects"]) == 2


def test_optional_product_values_can_be_missing(sources):
    """Keep products that have no category or physical measurements."""
    source = sources["products"]
    row = dict.fromkeys(source["schema"], "")
    row["product_id"] = "p1"
    result = clean_source(pd.DataFrame([row]), source)
    assert len(result["clean"]) == 1
    assert pd.isna(result["clean"].iloc[0]["product_category_name"])


def test_delivery_checks_depend_on_order_status(sources):
    """Allow missing dates on shipped orders but reject delivered orders without valid dates."""
    source = sources["orders"]
    base = dict.fromkeys(source["schema"], "")
    base.update(customer_id="c1", order_purchase_timestamp="2018-01-02 12:00:00",
                order_estimated_delivery_date="2018-01-10 00:00:00")
    raw = pd.DataFrame([
        dict(base, order_id="1", order_status=" SHIPPED "),
        dict(base, order_id="2", order_status="delivered"),
        dict(base, order_id="3", order_status="delivered", order_delivered_customer_date="2018-01-01 00:00:00"),
        dict(base, order_id="4", order_status="unknown"),
    ])
    result = clean_source(raw, source)
    assert list(result["clean"]["order_status"]) == ["shipped"]
    assert len(result["rejects"]) == 3


def test_review_ids_can_repeat_across_orders(sources):
    """Keep separate orders that share a review ID and reject out-of-range scores."""
    base = dict(review_id="r1", review_score="5", review_comment_title="", review_comment_message="",
                review_creation_date="2018-01-01 00:00:00", review_answer_timestamp="2018-01-02 00:00:00")
    raw = pd.DataFrame([dict(base, order_id="o1"), dict(base, order_id="o2"),
                        dict(base, order_id="o3", review_score="6")])
    result = clean_source(raw, sources["reviews"])
    assert len(result["clean"]) == 2
    assert len(result["rejects"]) == 1


def test_fractional_item_sequence_is_rejected(sources):
    """Reject an item sequence that is not a whole number."""
    path = Path(__file__).parent / "fixtures/items.csv"
    raw = read_source(path, sources["order_items"]).iloc[:1].copy()
    raw.loc[0, "order_item_id"] = "1.5"
    result = clean_source(raw, sources["order_items"])
    assert result["clean"].empty
    assert "order_item_id" in result["rejects"][0]["reason"]
