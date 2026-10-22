"""A listing can be claimed by only one Cash App trade at a time."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_trade_exclusivity")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import server


def _match_value(actual, expected) -> bool:
    if isinstance(expected, dict):
        for op, operand in expected.items():
            if op == "$in":
                if actual not in operand:
                    return False
            elif op == "$ne":
                if actual == operand:
                    return False
            else:
                raise AssertionError(f"unsupported operator {op}")
        return True
    return actual == expected


def _match(doc: dict, query: dict) -> bool:
    return all(_match_value(doc.get(key), expected) for key, expected in query.items())


class FakeCollection:
    """In-memory collection. Writes always see the real document.

    When stale_reads_after_write is set, finds keep returning the pre-write
    snapshot. That is the lost-update window: both buyers observed `active`.
    """

    def __init__(self, docs=None, *, stale_reads_after_write=False):
        self.docs = [dict(doc) for doc in (docs or [])]
        self.stale_reads_after_write = stale_reads_after_write
        self._stale = None
        self._frozen = False

    def _visible(self):
        if self._frozen and self._stale is not None:
            return self._stale
        return self.docs

    async def find_one(self, query, projection=None):
        for doc in self._visible():
            if _match(doc, query):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=1)

    async def update_one(self, query, update):
        if self.stale_reads_after_write and not self._frozen:
            self._stale = [dict(doc) for doc in self.docs]
        matched = next((doc for doc in self.docs if _match(doc, query)), None)
        if matched is None:
            return SimpleNamespace(modified_count=0, matched_count=0)
        before = dict(matched)
        matched.update(update.get("$set") or {})
        for key in (update.get("$unset") or {}):
            matched.pop(key, None)
        if self.stale_reads_after_write:
            self._frozen = True
        modified = 0 if matched == before else 1
        return SimpleNamespace(modified_count=modified, matched_count=1)

    async def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if _match(doc, query):
                self.docs.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class FakeDb:
    def __init__(self, listings, trades=None, users=None):
        self.listings = listings
        self.trades = trades if trades is not None else FakeCollection()
        self.users = users if users is not None else FakeCollection()


def _listing():
    return {
        "listing_id": "listing_1",
        "user_id": "seller_1",
        "seller_name": "Seller",
        "title": "Prizm RC",
        "price": 100.0,
        "status": "active",
    }


def _users():
    return FakeCollection([
        {"user_id": "seller_1", "name": "Seller", "cash_app_tag": "$seller"},
    ])


def _use(db, user):
    server.db = db

    async def _auth(request):
        return user

    server.require_auth = _auth


def _buyer(user_id, name):
    return {"user_id": user_id, "name": name}


async def _initiate(user_id, name):
    return await server.trade_initiate(
        server.TradeInitiate(listing_id="listing_1"),
        SimpleNamespace(),
    )


def test_second_buyer_loses_the_race_and_does_not_get_a_trade():
    """Both buyers still observe active. Only the conditional claim may win."""
    listings = FakeCollection([_listing()], stale_reads_after_write=True)
    trades = FakeCollection()
    db = FakeDb(listings, trades, _users())

    async def scenario():
        _use(db, _buyer("buyer_a", "Buyer A"))
        first = await _initiate("buyer_a", "Buyer A")
        _use(db, _buyer("buyer_b", "Buyer B"))
        with pytest.raises(HTTPException) as raised:
            await _initiate("buyer_b", "Buyer B")
        return first, raised.value

    import asyncio
    first, error = asyncio.run(scenario())

    assert error.status_code == 400
    assert listings.docs[0]["status"] == "pending"
    assert len(trades.docs) == 1
    assert trades.docs[0]["trade_id"] == first["trade_id"]
    assert trades.docs[0]["buyer_id"] == "buyer_a"
    assert trades.docs[0]["total_amount"] == 102.0


def test_cancel_releases_the_only_hold():
    listings = FakeCollection([_listing()])
    db = FakeDb(listings, FakeCollection(), _users())

    async def scenario():
        _use(db, _buyer("buyer_a", "Buyer A"))
        trade = await _initiate("buyer_a", "Buyer A")
        await server.trade_cancel(trade["trade_id"], SimpleNamespace())
        return trade

    import asyncio
    asyncio.run(scenario())
    assert listings.docs[0]["status"] == "active"


def test_cancel_does_not_reopen_a_listing_another_trade_still_holds():
    listings = FakeCollection([{**_listing(), "status": "pending"}])
    trades = FakeCollection([
        {
            "trade_id": "trade_a",
            "listing_id": "listing_1",
            "buyer_id": "buyer_a",
            "seller_id": "seller_1",
            "status": "awaiting_payment",
        },
        {
            "trade_id": "trade_b",
            "listing_id": "listing_1",
            "buyer_id": "buyer_b",
            "seller_id": "seller_1",
            "status": "awaiting_payment",
        },
    ])
    db = FakeDb(listings, trades, _users())

    async def scenario():
        _use(db, _buyer("buyer_a", "Buyer A"))
        await server.trade_cancel("trade_a", SimpleNamespace())

    import asyncio
    asyncio.run(scenario())

    assert listings.docs[0]["status"] == "pending"
    statuses = {doc["trade_id"]: doc["status"] for doc in trades.docs}
    assert statuses == {"trade_a": "canceled", "trade_b": "awaiting_payment"}


def test_second_confirm_does_not_complete_after_the_card_is_sold():
    listings = FakeCollection([{**_listing(), "status": "pending"}])
    trades = FakeCollection([
        {
            "trade_id": "trade_a",
            "listing_id": "listing_1",
            "buyer_id": "buyer_a",
            "seller_id": "seller_1",
            "status": "paid",
        },
        {
            "trade_id": "trade_b",
            "listing_id": "listing_1",
            "buyer_id": "buyer_b",
            "seller_id": "seller_1",
            "status": "awaiting_payment",
        },
    ])
    db = FakeDb(listings, trades, _users())

    async def scenario():
        _use(db, {"user_id": "seller_1", "name": "Seller"})
        first = await server.trade_confirm("trade_a", SimpleNamespace())
        with pytest.raises(HTTPException) as raised:
            await server.trade_confirm("trade_b", SimpleNamespace())
        return first, raised.value

    import asyncio
    first, error = asyncio.run(scenario())

    assert first["status"] == "completed"
    assert error.status_code == 409
    assert listings.docs[0]["status"] == "sold"
    statuses = {doc["trade_id"]: doc["status"] for doc in trades.docs}
    assert statuses["trade_a"] == "completed"
    assert statuses["trade_b"] == "awaiting_payment"


def test_failed_trade_insert_releases_the_claim():
    listings = FakeCollection([_listing()])
    trades = FakeCollection()

    async def boom(doc):
        raise RuntimeError("insert failed")

    trades.insert_one = boom
    db = FakeDb(listings, trades, _users())

    async def scenario():
        _use(db, _buyer("buyer_a", "Buyer A"))
        with pytest.raises(RuntimeError):
            await _initiate("buyer_a", "Buyer A")

    import asyncio
    asyncio.run(scenario())
    assert listings.docs[0]["status"] == "active"
    assert trades.docs == []


def test_delete_rejects_a_pending_listing_a_buyer_already_claimed():
    listings = FakeCollection([{**_listing(), "status": "pending"}])
    trades = FakeCollection([
        {
            "trade_id": "trade_a",
            "listing_id": "listing_1",
            "status": "awaiting_payment",
        },
    ])
    db = FakeDb(listings, trades, _users())

    async def scenario():
        _use(db, {"user_id": "seller_1", "name": "Seller"})
        with pytest.raises(HTTPException) as raised:
            await server.delete_listing("listing_1", SimpleNamespace())
        return raised.value

    import asyncio
    error = asyncio.run(scenario())
    assert error.status_code == 409
    assert len(listings.docs) == 1
    assert listings.docs[0]["status"] == "pending"


def test_cancel_does_not_clear_a_checkout_that_claimed_after_the_trade():
    listings = FakeCollection([_listing()])
    db = FakeDb(listings, FakeCollection(), _users())

    async def scenario():
        _use(db, _buyer("buyer_a", "Buyer A"))
        trade = await _initiate("buyer_a", "Buyer A")
        listings.docs[0]["pending_since"] = "2099-01-01T00:00:00+00:00"
        await server.trade_cancel(trade["trade_id"], SimpleNamespace())

    import asyncio
    asyncio.run(scenario())

    assert listings.docs[0]["status"] == "pending"
    assert listings.docs[0]["pending_since"] == "2099-01-01T00:00:00+00:00"


def test_second_cancel_does_not_clear_a_newer_hold():
    """Canceling an already-canceled trade must not put the card back on sale."""
    listings = FakeCollection([{**_listing(), "status": "pending"}])
    trades = FakeCollection([
        {
            "trade_id": "trade_a",
            "listing_id": "listing_1",
            "buyer_id": "buyer_a",
            "seller_id": "seller_1",
            "status": "canceled",
        },
        {
            "trade_id": "trade_b",
            "listing_id": "listing_1",
            "buyer_id": "buyer_b",
            "seller_id": "seller_1",
            "status": "awaiting_payment",
        },
    ])
    db = FakeDb(listings, trades, _users())

    async def scenario():
        _use(db, _buyer("buyer_a", "Buyer A"))
        with pytest.raises(HTTPException) as raised:
            await server.trade_cancel("trade_a", SimpleNamespace())
        return raised.value

    import asyncio
    error = asyncio.run(scenario())
    assert error.status_code == 400
    assert listings.docs[0]["status"] == "pending"
    assert trades.docs[1]["status"] == "awaiting_payment"
