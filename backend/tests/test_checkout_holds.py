"""Abandoned Stripe checkouts must not leave listings pending forever."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checkout_holds import decide_pending_listing, reconcile_abandoned_checkouts


NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def _iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


def test_recent_checkout_keeps_the_hold():
    decision = decide_pending_listing(
        pending_since=_iso(-timedelta(minutes=5)),
        transactions=[{
            "session_id": "cs_fresh",
            "payment_status": "pending",
            "created_at": _iso(-timedelta(minutes=5)),
        }],
        session_states={},
        has_open_trade=False,
        now=NOW,
    )
    assert decision == "pending"


def test_expired_stripe_session_returns_listing_to_active():
    decision = decide_pending_listing(
        pending_since=_iso(-timedelta(hours=25)),
        transactions=[{
            "session_id": "cs_old",
            "payment_status": "pending",
            "created_at": _iso(-timedelta(hours=25)),
        }],
        session_states={"cs_old": ("expired", "unpaid")},
        has_open_trade=False,
        now=NOW,
    )
    assert decision == "active"


def test_unconfirmed_old_session_is_not_relisted():
    """A failed Stripe lookup must not put a card back on sale."""
    decision = decide_pending_listing(
        pending_since=_iso(-timedelta(hours=25)),
        transactions=[{
            "session_id": "cs_old",
            "payment_status": "pending",
            "created_at": _iso(-timedelta(hours=25)),
        }],
        session_states={},
        has_open_trade=False,
        now=NOW,
    )
    assert decision == "pending"


def test_paid_session_marks_listing_sold():
    decision = decide_pending_listing(
        pending_since=_iso(-timedelta(hours=25)),
        transactions=[{
            "session_id": "cs_paid",
            "payment_status": "pending",
            "created_at": _iso(-timedelta(hours=25)),
        }],
        session_states={"cs_paid": ("complete", "paid")},
        has_open_trade=False,
        now=NOW,
    )
    assert decision == "sold"


def test_open_trade_is_not_released_by_an_expired_checkout():
    decision = decide_pending_listing(
        pending_since=None,
        transactions=[{
            "session_id": "cs_old",
            "payment_status": "pending",
            "created_at": _iso(-timedelta(hours=25)),
        }],
        session_states={"cs_old": ("expired", "unpaid")},
        has_open_trade=True,
        now=NOW,
    )
    assert decision == "pending"


def test_fresh_checkout_keeps_hold_even_if_an_older_session_expired():
    decision = decide_pending_listing(
        pending_since=_iso(-timedelta(minutes=2)),
        transactions=[
            {
                "session_id": "cs_old",
                "payment_status": "pending",
                "created_at": _iso(-timedelta(hours=25)),
            },
            {
                "session_id": "cs_new",
                "payment_status": "pending",
                "created_at": _iso(-timedelta(minutes=2)),
            },
        ],
        session_states={"cs_old": ("expired", "unpaid")},
        has_open_trade=False,
        now=NOW,
    )
    assert decision == "pending"


def test_orphaned_claim_older_than_hold_is_released():
    decision = decide_pending_listing(
        pending_since=_iso(-timedelta(hours=25)),
        transactions=[],
        session_states={},
        has_open_trade=False,
        now=NOW,
    )
    assert decision == "active"


def test_fresh_claim_without_a_transaction_is_kept():
    decision = decide_pending_listing(
        pending_since=_iso(-timedelta(seconds=5)),
        transactions=[],
        session_states={},
        has_open_trade=False,
        now=NOW,
    )
    assert decision == "pending"


def _match_value(actual, expected, present: bool) -> bool:
    if isinstance(expected, dict):
        for op, operand in expected.items():
            if op == "$type":
                if operand == "string" and not isinstance(actual, str):
                    return False
            elif op == "$nin":
                if actual in operand:
                    return False
            elif op == "$ne":
                if actual == operand:
                    return False
            elif op == "$in":
                if actual not in operand:
                    return False
            elif op == "$exists":
                if present != bool(operand):
                    return False
            elif op == "$lt":
                if actual is None or not actual < operand:
                    return False
            elif op == "$lte":
                if actual is None or not actual <= operand:
                    return False
            elif op == "$gte":
                if actual is None or not actual >= operand:
                    return False
            else:
                raise AssertionError(f"unsupported operator {op}")
        return True
    return actual == expected


def _match(doc: dict, query: dict) -> bool:
    for key, expected in query.items():
        if key == "$or":
            if not any(_match(doc, clause) for clause in expected):
                return False
            continue
        if key == "$and":
            if not all(_match(doc, clause) for clause in expected):
                return False
            continue
        if not _match_value(doc.get(key), expected, key in doc):
            return False
    return True


def _apply(doc: dict, update: dict) -> None:
    for key, value in (update.get("$set") or {}).items():
        doc[key] = value
    for key in update.get("$unset") or {}:
        doc.pop(key, None)


class _Result:
    def __init__(self, count: int):
        self.modified_count = count


class _Cursor:
    def __init__(self, docs: list):
        self.docs = docs

    def limit(self, n: int):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n: int):
        return self.docs[:n]


class _Collection:
    def __init__(self):
        self.docs = []

    def find(self, query, projection=None):
        return _Cursor([doc for doc in self.docs if _match(doc, query)])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return doc
        return None

    async def update_one(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                _apply(doc, update)
                return _Result(1)
        return _Result(0)

    async def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            if _match(doc, query):
                _apply(doc, update)
                count += 1
        return _Result(count)


class _DB:
    def __init__(self):
        self.listings = _Collection()
        self.payment_transactions = _Collection()
        self.trades = _Collection()


def _seed_abandoned(db: _DB, *, payment_status="pending", listing_status="pending", hours_ago=25):
    created = _iso(-timedelta(hours=hours_ago))
    db.listings.docs.append({
        "listing_id": "listing_abandoned",
        "status": listing_status,
        "pending_since": created,
    })
    db.payment_transactions.docs.append({
        "session_id": "cs_abandoned",
        "listing_id": "listing_abandoned",
        "payment_status": payment_status,
        "created_at": created,
    })


@pytest.mark.asyncio
async def test_reconcile_puts_expired_checkout_back_on_sale():
    db = _DB()
    _seed_abandoned(db)

    def retrieve(_session_id):
        return {"status": "expired", "payment_status": "unpaid"}

    changed = await reconcile_abandoned_checkouts(db, retrieve, now=NOW)

    assert changed == ["listing_abandoned"]
    assert db.listings.docs[0]["status"] == "active"
    assert "pending_since" not in db.listings.docs[0]
    assert db.payment_transactions.docs[0]["payment_status"] == "expired"


@pytest.mark.asyncio
async def test_reconcile_marks_paid_session_sold():
    db = _DB()
    _seed_abandoned(db)

    def retrieve(_session_id):
        return {"status": "complete", "payment_status": "paid"}

    changed = await reconcile_abandoned_checkouts(db, retrieve, now=NOW)

    assert changed == ["listing_abandoned"]
    assert db.listings.docs[0]["status"] == "sold"
    assert db.payment_transactions.docs[0]["payment_status"] == "paid"


@pytest.mark.asyncio
async def test_reconcile_leaves_open_trade_pending():
    db = _DB()
    _seed_abandoned(db)
    db.trades.docs.append({
        "trade_id": "trade_1",
        "listing_id": "listing_abandoned",
        "status": "awaiting_payment",
    })

    def retrieve(_session_id):
        return {"status": "expired", "payment_status": "unpaid"}

    changed = await reconcile_abandoned_checkouts(db, retrieve, now=NOW)

    assert changed == []
    assert db.listings.docs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_reconcile_keeps_hold_when_stripe_lookup_fails():
    db = _DB()
    _seed_abandoned(db)

    def retrieve(_session_id):
        raise RuntimeError("stripe unavailable")

    changed = await reconcile_abandoned_checkouts(db, retrieve, now=NOW)

    assert changed == []
    assert db.listings.docs[0]["status"] == "pending"
    assert db.payment_transactions.docs[0]["payment_status"] == "pending"


@pytest.mark.asyncio
async def test_reconcile_does_not_touch_a_fresh_checkout():
    db = _DB()
    _seed_abandoned(db, hours_ago=1)

    def retrieve(_session_id):
        raise AssertionError("fresh checkouts must not call Stripe")

    changed = await reconcile_abandoned_checkouts(db, retrieve, now=NOW)

    assert changed == []
    assert db.listings.docs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_reconcile_releases_claim_that_never_got_a_transaction():
    db = _DB()
    db.listings.docs.append({
        "listing_id": "listing_orphan",
        "status": "pending",
        "pending_since": _iso(-timedelta(hours=25)),
    })

    changed = await reconcile_abandoned_checkouts(db, lambda _sid: (_ for _ in ()).throw(AssertionError("no session")), now=NOW)

    assert changed == ["listing_orphan"]
    assert db.listings.docs[0]["status"] == "active"


@pytest.mark.asyncio
async def test_reconcile_does_not_reopen_a_sold_listing():
    db = _DB()
    _seed_abandoned(db, listing_status="sold")

    def retrieve(_session_id):
        raise AssertionError("sold listings must not be rechecked via Stripe here")

    changed = await reconcile_abandoned_checkouts(db, retrieve, now=NOW)

    assert changed == []
    assert db.listings.docs[0]["status"] == "sold"


# --- route guards (import server only for these) ---

def _load_server():
    os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
    os.environ.setdefault("DB_NAME", "ripnflip_checkout_hold_test")
    os.environ.setdefault("JWT_SECRET", "checkout-hold-test-secret")
    os.environ.setdefault("DISABLE_SCHEDULER", "1")
    import server
    return server


def test_second_claim_does_not_open_a_second_checkout():
    server = _load_server()
    mock_db = SimpleNamespace(
        listings=SimpleNamespace(
            find_one=AsyncMock(return_value={
                "listing_id": "listing_1",
                "user_id": "seller",
                "price": 20,
                "status": "active",
            }),
            update_one=AsyncMock(return_value=SimpleNamespace(modified_count=0)),
        ),
        payment_transactions=SimpleNamespace(insert_one=AsyncMock()),
    )
    stripe_called = {"n": 0}

    class FakeStripe:
        def __init__(self, api_key, webhook_url):
            pass

        async def create_checkout_session(self, request):
            stripe_called["n"] += 1
            return SimpleNamespace(session_id="cs_should_not_exist", url="https://pay.example")

    async def buyer(_request):
        return {"user_id": "buyer", "name": "Buyer", "email": "buyer@example.com"}

    from fastapi.testclient import TestClient

    with patch.object(server, "db", mock_db), patch.object(
        server, "reconcile_abandoned_checkouts", new=AsyncMock(return_value=[])
    ), patch.object(server, "get_current_user", buyer), patch.object(
        server, "StripeCheckout", FakeStripe
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/payments/checkout",
            json={"listing_id": "listing_1", "origin_url": "https://app.example"},
        )

    assert resp.status_code == 400
    assert stripe_called["n"] == 0
    mock_db.payment_transactions.insert_one.assert_not_called()
    claim_query = mock_db.listings.update_one.await_args.args[0]
    assert claim_query == {"listing_id": "listing_1", "status": "active"}


def test_stripe_failure_releases_the_claim():
    server = _load_server()
    updates = []

    async def update_one(query, update):
        updates.append((query, update))
        return SimpleNamespace(modified_count=1)

    mock_db = SimpleNamespace(
        listings=SimpleNamespace(
            find_one=AsyncMock(return_value={
                "listing_id": "listing_1",
                "user_id": "seller",
                "price": 20,
                "status": "active",
            }),
            update_one=update_one,
        ),
        payment_transactions=SimpleNamespace(insert_one=AsyncMock()),
    )

    class FakeStripe:
        def __init__(self, api_key, webhook_url):
            pass

        async def create_checkout_session(self, request):
            raise RuntimeError("stripe down")

    async def buyer(_request):
        return {"user_id": "buyer", "name": "Buyer", "email": "buyer@example.com"}

    from fastapi.testclient import TestClient

    with patch.object(server, "db", mock_db), patch.object(
        server, "reconcile_abandoned_checkouts", new=AsyncMock(return_value=[])
    ), patch.object(server, "get_current_user", buyer), patch.object(
        server, "StripeCheckout", FakeStripe
    ), TestClient(server.app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/api/payments/checkout",
            json={"listing_id": "listing_1", "origin_url": "https://app.example"},
        )

    assert resp.status_code == 500
    assert updates[0][0] == {"listing_id": "listing_1", "status": "active"}
    assert updates[0][1]["$set"]["status"] == "pending"
    assert updates[1][1]["$set"]["status"] == "active"
    assert updates[1][0]["status"] == "pending"
    assert updates[1][0]["pending_since"] == updates[0][1]["$set"]["pending_since"]


def test_expired_status_poll_only_reopens_a_pending_listing():
    server = _load_server()
    mock_db = SimpleNamespace(
        payment_transactions=SimpleNamespace(
            find_one=AsyncMock(return_value={
                "session_id": "cs_expired",
                "listing_id": "listing_sold_later",
                "payment_status": "unpaid",
            }),
            update_one=AsyncMock(),
        ),
        listings=SimpleNamespace(update_one=AsyncMock()),
    )

    class FakeStripe:
        def __init__(self, api_key, webhook_url):
            pass

        async def get_checkout_status(self, session_id):
            return SimpleNamespace(status="expired", payment_status="unpaid", amount_total=20.0, currency="usd")

    from fastapi.testclient import TestClient

    with patch.object(server, "db", mock_db), patch.object(
        server, "StripeCheckout", FakeStripe
    ), TestClient(server.app) as client:
        resp = client.get("/api/payments/status/cs_expired")

    assert resp.status_code == 200
    mock_db.listings.update_one.assert_awaited_once_with(
        {"listing_id": "listing_sold_later", "status": "pending"},
        {"$set": {"status": "active"}, "$unset": {"pending_since": ""}},
    )
