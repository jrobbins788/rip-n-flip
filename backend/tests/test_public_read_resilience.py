"""The public price, binder, and leaderboard reads must not 500 when Mongo is down.

Production (rip-n-flip-production.up.railway.app, Oct 16 2026) answered
GET /api/listings, /api/packs/price, /api/binders/public, and
/api/leaderboard/dub-streak with a plain "Internal Server Error" after
~30s, which is Motor/PyMongo's default server-selection timeout. Routes
that never touch Mongo returned 200 in under a second.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pymongo.errors import ServerSelectionTimeoutError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.db_guard import DatabaseUnavailable, await_db  # noqa: E402
from services.public_reads import (  # noqa: E402
    fetch_dub_streak,
    fetch_public_binders,
    resolve_pack_price,
)

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
TTL = timedelta(minutes=60)


class Agg:
    def __init__(self, rows=None, error=None, delay=0):
        self.rows = list(rows or [])
        self.error = error
        self.delay = delay
        self.pipelines = []

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        return self

    async def to_list(self, limit):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.rows[:limit]


class Users:
    def __init__(self, by_id=None, error=None):
        self.by_id = by_id or {}
        self.error = error

    async def find_one(self, query, projection=None):
        if self.error:
            raise self.error
        return self.by_id.get(query.get("user_id"))


class PriceCache:
    def __init__(self, doc=None, error=None, delay=0):
        self.doc = doc
        self.error = error
        self.delay = delay
        self.writes = []

    async def find_one(self, query, projection=None):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.doc

    async def update_one(self, filt, update, upsert=False):
        if self.error:
            raise self.error
        self.writes.append((filt, update, upsert))


class DB:
    def __init__(self):
        self.price_cache = PriceCache()
        self.case_packs = Agg()
        self.users = Users()
        self.pull_thumbs = Agg()
        self.case_pulls = Agg()


def _run(coro):
    return asyncio.run(coro)


async def _scrape(query, sold):
    return {
        "query": query,
        "sold_only": sold,
        "count": 2,
        "avg": 42.5,
        "min": 10,
        "max": 75,
        "median": 42.5,
        "listings": [{"title": "Prizm", "price": 42.5}],
        "blocked": False,
    }


def test_await_db_turns_server_selection_timeout_into_unavailable():
    async def boom():
        raise ServerSelectionTimeoutError("127.0.0.1:27017: connection refused")

    with pytest.raises(DatabaseUnavailable) as caught:
        _run(await_db(boom()))
    assert "connection refused" in str(caught.value)


def test_await_db_bounds_a_hang():
    import time

    async def hang():
        await asyncio.sleep(30)
        return "late"

    t0 = time.perf_counter()
    with pytest.raises(DatabaseUnavailable):
        _run(await_db(hang(), timeout=0.2))
    assert time.perf_counter() - t0 < 2


def test_price_skips_a_down_cache_and_returns_the_scrape():
    db = DB()
    db.price_cache.error = ServerSelectionTimeoutError("no primary available")

    async def scrape(query, sold):
        return await _scrape(query, sold)

    data = _run(resolve_pack_price(
        db=db, query="Panini Prizm Basketball Hobby", sold=False, refresh=False,
        scrape=scrape, now=NOW, ttl=TTL,
    ))
    assert data["count"] == 2
    assert data["avg"] == 42.5
    assert data["blocked"] is False
    assert data["cached"] is False
    assert data["listings"][0]["title"] == "Prizm"


def test_price_uses_a_fresh_cache_without_scraping():
    db = DB()
    db.price_cache.doc = {
        "data": {"query": "prizm", "count": 4, "avg": 19, "listings": [], "blocked": False, "sold_only": False},
        "fetched_at": (NOW - timedelta(minutes=5)).isoformat(),
    }
    called = {"n": 0}

    async def scrape(query, sold):
        called["n"] += 1
        return await _scrape(query, sold)

    data = _run(resolve_pack_price(
        db=db, query="prizm", sold=False, refresh=False,
        scrape=scrape, now=NOW, ttl=TTL,
    ))
    assert called["n"] == 0
    assert data["cached"] is True
    assert data["avg"] == 19


def test_price_ignores_a_corrupt_cache_document():
    db = DB()
    db.price_cache.doc = {"data": {"avg": 10}, "fetched_at": None}

    data = _run(resolve_pack_price(
        db=db, query="prizm", sold=False, refresh=False,
        scrape=_scrape, now=NOW, ttl=TTL,
    ))
    assert data["cached"] is False
    assert data["avg"] == 42.5
    assert len(db.price_cache.writes) == 1


def test_price_returns_blocked_payload_when_scrape_and_cache_fail():
    db = DB()
    db.price_cache.error = ServerSelectionTimeoutError("timeout")

    async def scrape(query, sold):
        raise RuntimeError("eBay down")

    data = _run(resolve_pack_price(
        db=db, query="prizm", sold=True, refresh=False,
        scrape=scrape, now=NOW, ttl=TTL,
    ))
    assert data["blocked"] is True
    assert data["count"] == 0
    assert data["avg"] is None
    assert data["listings"] == []
    assert data["sold_only"] is True
    assert "temporarily unavailable" in data["reason"]
    assert db.price_cache.writes == []


def test_price_still_returns_scrape_when_cache_write_fails():
    db = DB()

    async def update_one(*args, **kwargs):
        raise ServerSelectionTimeoutError("write failed")

    db.price_cache.update_one = update_one
    data = _run(resolve_pack_price(
        db=db, query="prizm", sold=False, refresh=True,
        scrape=_scrape, now=NOW, ttl=TTL,
    ))
    assert data["avg"] == 42.5
    assert data["cached"] is False


def test_public_binders_shape_and_sport_filter():
    db = DB()
    db.case_packs = Agg(rows=[{
        "_id": "user_1",
        "binder_count": 2,
        "pulls_total": 9,
        "sports": ["NBA", None],
        "latest": NOW,
    }])
    db.users = Users(by_id={"user_1": {"user_id": "user_1", "name": "Ada", "picture": None}})

    data = _run(fetch_public_binders(db, limit=24, sport="NBA"))
    assert data["count"] == 1
    assert data["binders"][0]["username"] == "Ada"
    assert data["binders"][0]["sports"] == ["NBA"]
    assert data["binders"][0]["latest"] == NOW.isoformat()
    assert "unavailable" not in data
    assert db.case_packs.pipelines[0][0]["$match"] == {"is_public": True, "sport": "NBA"}


def test_public_binders_with_no_rows_is_not_an_outage():
    data = _run(fetch_public_binders(DB(), limit=24, sport=None))
    assert data == {"binders": [], "count": 0}


def test_leaderboard_rejects_unknown_period(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:1")
    monkeypatch.setenv("DB_NAME", "ripnflip_test")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.leaderboard import router

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/api/leaderboard/dub-streak", params={"period": "foo"})
    assert response.status_code == 400
    assert response.json()["detail"] == "period must be 'week' or 'all'"


def test_public_binders_empty_when_mongo_is_down():
    db = DB()
    db.case_packs = Agg(error=ServerSelectionTimeoutError("no suitable server"))
    data = _run(fetch_public_binders(db, limit=24, sport=None))
    assert data == {
        "binders": [],
        "count": 0,
        "unavailable": True,
        "reason": "Public binders are temporarily unavailable.",
    }


def test_leaderboard_week_marks_only_first_place():
    db = DB()
    db.pull_thumbs = Agg(rows=[
        {"_id": "user_a", "thumbs_period": 5},
        {"_id": "user_b", "thumbs_period": 1},
    ])
    db.users = Users(by_id={
        "user_a": {"user_id": "user_a", "username": "Ace"},
        "user_b": {"user_id": "user_b", "name": "Bee"},
    })
    data = _run(fetch_dub_streak(db, period="week", limit=10))
    assert data["period"] == "week"
    assert data["count"] == 2
    assert data["entries"][0]["is_flame"] is True
    assert data["entries"][0]["username"] == "Ace"
    assert data["entries"][1]["is_flame"] is False
    assert "public_pulls" not in data["entries"][0]


def test_leaderboard_all_time_includes_public_pulls():
    db = DB()
    db.case_pulls = Agg(rows=[{"_id": "user_a", "thumbs_period": 3, "public_pulls": 8}])
    db.users = Users(by_id={"user_a": {"user_id": "user_a", "username": "Ace"}})
    data = _run(fetch_dub_streak(db, period="all", limit=10))
    assert data["entries"][0]["public_pulls"] == 8
    assert db.case_pulls.pipelines


def test_leaderboard_empty_when_mongo_hangs():
    db = DB()
    db.pull_thumbs = Agg(delay=5)

    async def run():
        return await fetch_dub_streak(db, period="week", limit=10)

    # Shrink the guard for this call by patching the helper's default via the row wait.
    import services.public_reads as reads

    original = reads.await_db

    async def fast_wait(awaitable, *, timeout=10):
        return await original(awaitable, timeout=0.2)

    reads.await_db = fast_wait
    try:
        data = _run(run())
    finally:
        reads.await_db = original
    assert data["period"] == "week"
    assert data["entries"] == []
    assert data["count"] == 0
    assert data["unavailable"] is True


def test_closed_mongo_port_returns_an_empty_gallery():
    """Local repro of the production failure: nothing is listening, so the
    driver raises ServerSelectionTimeoutError instead of an unhandled 500."""
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(
        "mongodb://127.0.0.1:1",
        serverSelectionTimeoutMS=400,
        connectTimeoutMS=400,
    )
    db = client["ripnflip_test"]
    try:
        data = _run(fetch_public_binders(db, limit=10, sport=None))
    finally:
        client.close()
    assert data["binders"] == []
    assert data["unavailable"] is True
    assert data["count"] == 0
