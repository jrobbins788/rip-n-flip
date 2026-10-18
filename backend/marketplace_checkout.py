"""Marketplace checkout fulfillment decisions.

Stripe webhook bodies are not a source of truth. Callers must pass the
payment status from Checkout Session.retrieve and the listing id stored on
our payment_transactions row.
"""
from __future__ import annotations

from typing import Optional


def listing_id_to_mark_sold(
    transaction: Optional[dict],
    stripe_payment_status: Optional[str],
    stripe_metadata_listing_id: Optional[str] = None,
) -> Optional[str]:
    """Return the listing id to mark sold, or None when fulfillment must not happen.

    `stripe_metadata_listing_id` is metadata from the Checkout Session Stripe
    returned, not from the webhook request body. A mismatch means this session
    was not created for the transaction we have on file.
    """
    if stripe_payment_status != "paid" or not isinstance(transaction, dict):
        return None
    listing_id = transaction.get("listing_id")
    if not isinstance(listing_id, str) or not listing_id:
        return None
    if stripe_metadata_listing_id and stripe_metadata_listing_id != listing_id:
        return None
    return listing_id
