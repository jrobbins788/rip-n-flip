"""Binder pulls and marketplace listings must stay one-to-one.

A pull removed from the binder must not stay buyable, and two sells of the
same pull must not both create a live listing.
"""
import asyncio
import copy
import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "vendor"))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ripnflip_pull_listing_test")
os.environ.setdefault("JWT_SECRET", "test-secret")

import server  # noqa: E402


class _Result:
    def __init__(self, modified_count=0, matched_count=0, deleted_count=0):
        self.modified_count = modified_count
        self.matched_count = matched_count
        self.deleted_count = deleted_count


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, clause) for clause in expected):
                return False
            continue
        if expected is None:
            if key in doc and doc[key] is not None:
                return False
            continue
        if doc.get(key) != expected:
            return False
    return True


def _project(doc, projection):
    if not projection:
        return copy.deepcopy(doc)
    including = [k for k, v in projection.items() if v == 1 and k != "_id"]
    if including:
        return {k: copy.deepcopy(doc[k]) for k in including if k in doc}
    return {k: copy.deepcopy(v) for k, v in doc.items() if projection.get(k) != 0 and k != "_id"}


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query, projection=None):
        matched = [_project(doc, projection) for doc in self.docs if _matches(doc, query)]

        class _Cursor:
            def __init__(self, rows):
                self.rows = rows

            async def to_list(self, limit):
                return self.rows[:limit]

        return _Cursor(matched)

    async def insert_one(self, doc):
        stored = copy.deepcopy(doc)
        stored["_id"] = uuid.uuid4().hex
        self.docs.append(stored)
        return stored

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if not _matches(doc, query):
                continue
            before = copy.deepcopy(doc)
            for key, value in (update.get("$set") or {}).items():
                doc[key] = copy.deepcopy(value)
            for key in (update.get("$unset") or {}):
                doc.pop(key, None)
            for key, value in (update.get("$inc") or {}).items():
                doc[key] = doc.get(key, 0) + value
            changed = doc != before
            return _Result(modified_count=1 if changed else 0, matched_count=1)
        return _Result()

    async def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                self.docs.pop(index)
                return _Result(deleted_count=1)
        return _Result()

    async def delete_many(self, query):
        kept = []
        deleted = 0
        for doc in self.docs:
            if _matches(doc, query):
                deleted += 1
            else:
                kept.append(doc)
        self.docs = kept
        return _Result(deleted_count=deleted)


class FakeDB:
    def __init__(self):
        self.case_pulls = FakeCollection()
        self.listings = FakeCollection()
        self.case_packs = FakeCollection()


def _pull(**overrides):
    doc = {
        "pull_id": "pull_1",
        "case_pack_id": "binder_1",
        "user_id": "user_1",
        "card": {"player": "CJ Stroud", "year": 2024, "set": "Prizm"},
        "timestamp": "2026-10-15T12:00:00+00:00",
        "status": "in_collection",
        "notes": "fresh",
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.case_packs.docs.append({"case_pack_id": "binder_1", "user_id": "user_1", "pulls_count": 1})
    monkeypatch.setattr(server, "db", fake)

    async def auth(_request):
        return {"user_id": "user_1", "name": "Seller"}

    async def pro(_user_id):
        return "pro"

    monkeypatch.setattr(server, "require_auth", auth)
    monkeypatch.setattr(server, "_user_tier", pro)
    return fake


def _run(coro):
    return asyncio.run(coro)


def test_listing_a_pull_claims_it_before_the_listing_exists(db):
    db.case_pulls.docs.append(_pull())

    created = _run(server.listings_from_pull(
        server.ListFromPullRequest(pull_id="pull_1", price=40),
        None,
    ))

    assert created["status"] == "active"
    assert created["from_pull_id"] == "pull_1"
    assert len(db.listings.docs) == 1
    assert db.case_pulls.docs[0]["listed_listing_id"] == created["listing_id"]
    assert db.case_pulls.docs[0]["status"] == "listed"


def test_second_sell_of_the_same_pull_does_not_create_another_listing(db):
    db.case_pulls.docs.append(_pull())
    _run(server.listings_from_pull(server.ListFromPullRequest(pull_id="pull_1", price=40), None))

    with pytest.raises(HTTPException) as raised:
        _run(server.listings_from_pull(server.ListFromPullRequest(pull_id="pull_1", price=90), None))

    assert raised.value.status_code == 400
    assert len(db.listings.docs) == 1


def test_stale_read_cannot_list_a_pull_another_request_already_claimed(db):
    db.case_pulls.docs.append(_pull())
    original_find = db.case_pulls.find_one

    async def stale_find(query, projection=None):
        snapshot = await original_find(query, projection)
        if snapshot and set(query.keys()) == {"pull_id"}:
            db.case_pulls.docs[0]["listed_listing_id"] = "listing_other"
            db.case_pulls.docs[0]["status"] = "listed"
            snapshot.pop("listed_listing_id", None)
            snapshot["status"] = "in_collection"
        return snapshot

    db.case_pulls.find_one = stale_find

    with pytest.raises(HTTPException) as raised:
        _run(server.listings_from_pull(server.ListFromPullRequest(pull_id="pull_1", price=40), None))

    assert raised.value.status_code == 400
    assert db.listings.docs == []
    assert db.case_pulls.docs[0]["listed_listing_id"] == "listing_other"


def test_failed_listing_insert_releases_the_claim(db):
    db.case_pulls.docs.append(_pull())

    async def boom(_doc):
        raise RuntimeError("insert failed")

    db.listings.insert_one = boom

    with pytest.raises(RuntimeError):
        _run(server.listings_from_pull(server.ListFromPullRequest(pull_id="pull_1", price=40), None))

    assert "listed_listing_id" not in db.case_pulls.docs[0]
    assert db.case_pulls.docs[0]["status"] == "in_collection"


def test_zero_price_is_rejected(db):
    db.case_pulls.docs.append(_pull())

    with pytest.raises(HTTPException) as raised:
        _run(server.listings_from_pull(server.ListFromPullRequest(pull_id="pull_1", price=0), None))

    assert raised.value.status_code == 400
    assert db.listings.docs == []
    assert "listed_listing_id" not in db.case_pulls.docs[0]


def test_deleting_a_listed_pull_removes_the_active_listing(db):
    db.case_pulls.docs.append(_pull(listed_listing_id="listing_live", status="listed"))
    db.listings.docs.append({"listing_id": "listing_live", "status": "active", "price": 40})

    result = _run(server.case_delete_pull("pull_1", None))

    assert result == {"deleted": True}
    assert db.case_pulls.docs == []
    assert db.listings.docs == []
    assert db.case_packs.docs[0]["pulls_count"] == 0


def test_deleting_a_pull_in_checkout_keeps_the_card_and_the_listing(db):
    db.case_pulls.docs.append(_pull(listed_listing_id="listing_hold", status="listed"))
    db.listings.docs.append({"listing_id": "listing_hold", "status": "pending", "price": 40})

    with pytest.raises(HTTPException) as raised:
        _run(server.case_delete_pull("pull_1", None))

    assert raised.value.status_code == 409
    assert len(db.case_pulls.docs) == 1
    assert db.listings.docs[0]["status"] == "pending"
    assert db.case_packs.docs[0]["pulls_count"] == 1


def test_deleting_a_sold_pull_keeps_the_sale_record(db):
    db.case_pulls.docs.append(_pull(listed_listing_id="listing_sold", status="listed"))
    db.listings.docs.append({"listing_id": "listing_sold", "status": "sold", "price": 40})

    _run(server.case_delete_pull("pull_1", None))

    assert db.case_pulls.docs == []
    assert db.listings.docs[0]["status"] == "sold"


def test_deleting_a_binder_withdraws_active_listings(db):
    db.case_pulls.docs.extend([
        _pull(pull_id="pull_1", listed_listing_id="listing_live", status="listed"),
        _pull(pull_id="pull_2"),
    ])
    db.listings.docs.append({"listing_id": "listing_live", "status": "active", "price": 25})

    result = _run(server.case_delete_pack("binder_1", None))

    assert result == {"deleted": True}
    assert db.case_packs.docs == []
    assert db.case_pulls.docs == []
    assert db.listings.docs == []


def test_deleting_a_binder_with_a_pending_sale_is_rejected(db):
    db.case_pulls.docs.append(_pull(listed_listing_id="listing_hold", status="listed"))
    db.listings.docs.append({"listing_id": "listing_hold", "status": "pending", "price": 25})

    with pytest.raises(HTTPException) as raised:
        _run(server.case_delete_pack("binder_1", None))

    assert raised.value.status_code == 409
    assert len(db.case_packs.docs) == 1
    assert len(db.case_pulls.docs) == 1
    assert db.listings.docs[0]["status"] == "pending"
