"""Sold and in-checkout listings stay the record of the card that was offered.

A seller could PUT a new title and price onto a listing after a buyer started
checkout or after the sale completed. The transaction stores the listing id,
not a copy of the card, so that edit replaced the only description of what
was sold. DELETE did the same for a completed sale.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ripnflip_test")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))

import server  # noqa: E402


def _listing(**overrides):
    doc = {
        "listing_id": "listing_1",
        "user_id": "seller_1",
        "seller_name": "Seller",
        "title": "2023 Prizm Wembanyama Silver",
        "description": "Silver prizm, pulled last week",
        "sport": "NBA",
        "card_type": "Rookie",
        "player_name": "Victor Wembanyama",
        "team": "Spurs",
        "year": "2023",
        "brand": "Panini Prizm",
        "condition": "Near Mint",
        "price": 400.0,
        "is_tradeable": False,
        "images": ["https://example.com/wemby.jpg"],
        "status": "active",
        "created_at": "2026-10-01T00:00:00+00:00",
    }
    doc.update(overrides)
    return doc


def _edit(title="Bulk commons", price=5.0):
    return server.ListingCreate(
        title=title,
        description="changed after the buyer paid",
        sport="NBA",
        card_type="Base",
        player_name="Commons",
        condition="Good",
        price=price,
        images=["https://example.com/bulk.jpg"],
    )


class FakeListings:
    def __init__(self, doc, flip_to_sold_on_read=False):
        self.doc = doc
        self.flip_to_sold_on_read = flip_to_sold_on_read

    async def find_one(self, query, projection=None):
        if not self.doc or self.doc.get("listing_id") != query.get("listing_id"):
            return None
        snapshot = dict(self.doc)
        if self.flip_to_sold_on_read:
            self.doc["status"] = "sold"
            self.flip_to_sold_on_read = False
        return snapshot

    async def update_one(self, query, update):
        if not self.doc or self.doc.get("listing_id") != query.get("listing_id"):
            return SimpleNamespace(matched_count=0, modified_count=0)
        if query.get("user_id") and self.doc.get("user_id") != query["user_id"]:
            return SimpleNamespace(matched_count=0, modified_count=0)
        if query.get("status") and self.doc.get("status") != query["status"]:
            return SimpleNamespace(matched_count=0, modified_count=0)
        self.doc.update(update.get("$set") or {})
        return SimpleNamespace(matched_count=1, modified_count=1)

    async def delete_one(self, query):
        if not self.doc or self.doc.get("listing_id") != query.get("listing_id"):
            return SimpleNamespace(deleted_count=0)
        if query.get("user_id") and self.doc.get("user_id") != query["user_id"]:
            return SimpleNamespace(deleted_count=0)
        status = query.get("status")
        if isinstance(status, dict) and "$ne" in status and self.doc.get("status") == status["$ne"]:
            return SimpleNamespace(deleted_count=0)
        if isinstance(status, str) and self.doc.get("status") != status:
            return SimpleNamespace(deleted_count=0)
        self.doc = None
        return SimpleNamespace(deleted_count=1)


def _use(listings, user_id="seller_1"):
    async def require_auth(request):
        return {"user_id": user_id, "name": "Seller"}

    server.db = SimpleNamespace(
        listings=listings,
        trades=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        case_pulls=SimpleNamespace(update_one=AsyncMock()),
    )
    server.require_auth = require_auth


def test_sold_listing_keeps_the_card_the_buyer_paid_for():
    listings = FakeListings(_listing(status="sold"))

    async def scenario():
        _use(listings)
        with pytest.raises(server.HTTPException) as raised:
            await server.update_listing("listing_1", _edit(), SimpleNamespace())
        return raised.value

    import asyncio
    error = asyncio.run(scenario())

    assert error.status_code == 409
    assert listings.doc["title"] == "2023 Prizm Wembanyama Silver"
    assert listings.doc["price"] == 400.0
    assert listings.doc["status"] == "sold"
    assert listings.doc["images"] == ["https://example.com/wemby.jpg"]


def test_pending_checkout_keeps_the_card_the_buyer_is_paying_for():
    listings = FakeListings(_listing(status="pending"))

    async def scenario():
        _use(listings)
        with pytest.raises(server.HTTPException) as raised:
            await server.update_listing("listing_1", _edit(price=1), SimpleNamespace())
        return raised.value

    import asyncio
    error = asyncio.run(scenario())

    assert error.status_code == 409
    assert listings.doc["title"] == "2023 Prizm Wembanyama Silver"
    assert listings.doc["price"] == 400.0
    assert listings.doc["status"] == "pending"


def test_edit_that_lands_after_the_sale_does_not_overwrite_it():
    """The read saw active, then checkout marked the listing sold."""
    listings = FakeListings(_listing(status="active"), flip_to_sold_on_read=True)

    async def scenario():
        _use(listings)
        with pytest.raises(server.HTTPException) as raised:
            await server.update_listing("listing_1", _edit(), SimpleNamespace())
        return raised.value

    import asyncio
    error = asyncio.run(scenario())

    assert error.status_code == 409
    assert listings.doc["status"] == "sold"
    assert listings.doc["title"] == "2023 Prizm Wembanyama Silver"
    assert listings.doc["price"] == 400.0


def test_active_listing_can_still_be_edited_by_its_seller():
    listings = FakeListings(_listing(status="active"))

    async def scenario():
        _use(listings)
        return await server.update_listing("listing_1", _edit(title="Updated title", price=80), SimpleNamespace())

    import asyncio
    updated = asyncio.run(scenario())

    assert updated["title"] == "Updated title"
    assert updated["price"] == 80
    assert updated["status"] == "active"
    assert listings.doc["status"] == "active"


def test_other_seller_cannot_edit():
    listings = FakeListings(_listing(status="active"))

    async def scenario():
        _use(listings, user_id="buyer_1")
        with pytest.raises(server.HTTPException) as raised:
            await server.update_listing("listing_1", _edit(), SimpleNamespace())
        return raised.value

    import asyncio
    error = asyncio.run(scenario())

    assert error.status_code == 403
    assert listings.doc["title"] == "2023 Prizm Wembanyama Silver"


def test_sold_listing_cannot_be_deleted():
    listings = FakeListings(_listing(status="sold"))

    async def scenario():
        _use(listings)
        with pytest.raises(server.HTTPException) as raised:
            await server.delete_listing("listing_1", SimpleNamespace())
        return raised.value

    import asyncio
    error = asyncio.run(scenario())

    assert error.status_code == 409
    assert listings.doc is not None
    assert listings.doc["title"] == "2023 Prizm Wembanyama Silver"
    assert listings.doc["status"] == "sold"


def test_delete_that_lands_after_the_sale_does_not_remove_it():
    listings = FakeListings(_listing(status="active"), flip_to_sold_on_read=True)

    async def scenario():
        _use(listings)
        with pytest.raises(server.HTTPException) as raised:
            await server.delete_listing("listing_1", SimpleNamespace())
        return raised.value

    import asyncio
    error = asyncio.run(scenario())

    assert error.status_code == 409
    assert listings.doc["status"] == "sold"
    assert listings.doc["listing_id"] == "listing_1"


def test_active_listing_can_still_be_deleted():
    listings = FakeListings(_listing(status="active"))

    async def scenario():
        _use(listings)
        return await server.delete_listing("listing_1", SimpleNamespace())

    import asyncio
    result = asyncio.run(scenario())

    assert result == {"message": "Listing deleted"}
    assert listings.doc is None
