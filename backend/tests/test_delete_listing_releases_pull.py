"""Deleting an unsold from-pull listing must unlock the binder card.

Otherwise the pull stays status=listed with a dangling listed_listing_id, the
sell button stays hidden, and POST /listings/from-pull returns 400 forever.
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ripnflip_unit")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))

import server  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _db(listing):
    listings = AsyncMock()
    listings.find_one.return_value = listing
    listings.delete_one.return_value = SimpleNamespace(deleted_count=1)
    pulls = AsyncMock()
    trades = AsyncMock()
    trades.find_one.return_value = None
    db = SimpleNamespace(listings=listings, case_pulls=pulls, trades=trades)
    return db, listings, pulls


def test_delete_active_from_pull_listing_releases_binder_card(monkeypatch):
    listing = {
        "listing_id": "listing_abc",
        "user_id": "user_1",
        "status": "active",
        "from_pull_id": "pull_1",
    }
    db, listings, pulls = _db(listing)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "require_auth", AsyncMock(return_value={"user_id": "user_1"}))

    result = _run(server.delete_listing("listing_abc", MagicMock()))

    assert result == {"message": "Listing deleted"}
    pulls.update_one.assert_awaited_once_with(
        {"pull_id": "pull_1", "listed_listing_id": "listing_abc"},
        {"$set": {"status": "in_collection"}, "$unset": {"listed_listing_id": ""}},
    )
    listings.delete_one.assert_awaited_once_with({
        "listing_id": "listing_abc",
        "user_id": "user_1",
        "status": "active",
    })


def test_delete_sold_from_pull_listing_keeps_pull_locked(monkeypatch):
    listing = {
        "listing_id": "listing_sold",
        "user_id": "user_1",
        "status": "sold",
        "from_pull_id": "pull_1",
    }
    db, listings, pulls = _db(listing)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "require_auth", AsyncMock(return_value={"user_id": "user_1"}))

    with pytest.raises(HTTPException) as exc:
        _run(server.delete_listing("listing_sold", MagicMock()))

    assert exc.value.status_code == 409
    pulls.update_one.assert_not_awaited()
    listings.delete_one.assert_not_awaited()


def test_delete_manual_listing_does_not_touch_pulls(monkeypatch):
    listing = {
        "listing_id": "listing_manual",
        "user_id": "user_1",
        "status": "active",
    }
    db, listings, pulls = _db(listing)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "require_auth", AsyncMock(return_value={"user_id": "user_1"}))

    _run(server.delete_listing("listing_manual", MagicMock()))

    pulls.update_one.assert_not_awaited()
    listings.delete_one.assert_awaited_once()


def test_delete_listing_rejects_non_owner_before_release(monkeypatch):
    listing = {
        "listing_id": "listing_abc",
        "user_id": "user_1",
        "status": "active",
        "from_pull_id": "pull_1",
    }
    db, listings, pulls = _db(listing)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "require_auth", AsyncMock(return_value={"user_id": "user_2"}))

    with pytest.raises(HTTPException) as exc:
        _run(server.delete_listing("listing_abc", MagicMock()))

    assert exc.value.status_code == 403
    pulls.update_one.assert_not_awaited()
    listings.delete_one.assert_not_awaited()
