"""Unsigned marketplace webhooks must not mark arbitrary listings sold."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketplace_checkout import listing_id_to_mark_sold


def test_forged_unpaid_status_does_not_sell_listing():
    transaction = {"listing_id": "listing_victim", "payment_status": "pending"}
    assert listing_id_to_mark_sold(transaction, "unpaid", "listing_victim") is None
    assert listing_id_to_mark_sold(transaction, "paid_forged", "listing_victim") is None
    assert listing_id_to_mark_sold(transaction, None, "listing_victim") is None


def test_paid_session_sells_only_the_stored_listing():
    transaction = {"listing_id": "listing_real", "payment_status": "pending"}
    assert listing_id_to_mark_sold(transaction, "paid", "listing_real") == "listing_real"


def test_paid_session_ignores_mismatched_listing_metadata():
    """A paid session for listing A must not fulfill listing B."""
    transaction = {"listing_id": "listing_real", "payment_status": "pending"}
    assert listing_id_to_mark_sold(transaction, "paid", "listing_victim") is None


def test_paid_status_without_local_transaction_sells_nothing():
    assert listing_id_to_mark_sold(None, "paid", "listing_victim") is None
    assert listing_id_to_mark_sold({}, "paid", "listing_victim") is None
    assert listing_id_to_mark_sold({"payment_status": "paid"}, "paid") is None


def test_retry_still_returns_listing_when_transaction_already_paid():
    transaction = {"listing_id": "listing_real", "payment_status": "paid"}
    assert listing_id_to_mark_sold(transaction, "paid", "listing_real") == "listing_real"
