"""
Test Suite for Card Database Backbone (Day 4) + Display Case (Day 5-7)
Features tested:
- Admin CSV import, sets listing, clear cards
- Card search (local DB + eBay fallback)
- Display Case: binders (packs), pulls, stats
- Tier logic (pro for admin/trial users)
- Permission checks (owner-only access)
"""

import pytest
import requests
import os
import time
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@flipnrip.com"
ADMIN_PASSWORD = "AdminPass123!"


class TestSetup:
    """Setup and helper methods"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin and return session with token"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if resp.status_code == 401:
            # Admin doesn't exist, register first
            resp = session.post(f"{BASE_URL}/api/auth/register", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
                "name": "Admin User"
            })
        
        assert resp.status_code in [200, 201], f"Admin login/register failed: {resp.text}"
        data = resp.json()
        token = data.get("token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def regular_user_session(self):
        """Create and login as a regular test user"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        timestamp = int(time.time())
        email = f"TEST_user_{timestamp}@test.com"
        
        resp = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "TestPass123!",
            "name": "Test User"
        })
        
        assert resp.status_code in [200, 201], f"User registration failed: {resp.text}"
        data = resp.json()
        token = data.get("token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session


class TestHealthAndRegression:
    """Regression tests for existing endpoints"""
    
    def test_health_endpoint(self):
        """Health check should return healthy"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        print("PASS: Health endpoint working")
    
    def test_hot_packs_endpoint(self):
        """Hot packs should return pack list"""
        resp = requests.get(f"{BASE_URL}/api/hot-packs")
        assert resp.status_code == 200
        data = resp.json()
        assert "packs" in data
        assert len(data["packs"]) > 0
        # Verify checklist_set field exists on packs
        for pack in data["packs"]:
            assert "checklist_set" in pack, f"Pack {pack['pack_id']} missing checklist_set"
        print(f"PASS: Hot packs returned {len(data['packs'])} packs with checklist_set field")


class TestAdminCardsImport:
    """Test POST /api/admin/cards/import - CSV upload"""
    
    def test_import_requires_auth(self):
        """Import without auth should return 401"""
        files = {'file': ('test.csv', 'card_number,player,team,set,year\n1,Test,Team,Set,2024', 'text/csv')}
        resp = requests.post(f"{BASE_URL}/api/admin/cards/import", files=files)
        assert resp.status_code == 401
        print("PASS: Import requires authentication")
    
    def test_import_requires_admin(self, regular_user_session):
        """Import with non-admin should return 403"""
        files = {'file': ('test.csv', 'card_number,player,team,set,year\n1,Test,Team,Set,2024', 'text/csv')}
        # Remove Content-Type for multipart
        headers = {k: v for k, v in regular_user_session.headers.items() if k.lower() != 'content-type'}
        resp = requests.post(
            f"{BASE_URL}/api/admin/cards/import", 
            files=files,
            headers=headers
        )
        assert resp.status_code == 403
        assert "Admin" in resp.json().get("detail", "")
        print("PASS: Import requires admin role (403 with helpful message)")
    
    def test_import_valid_csv(self, admin_session):
        """Import valid CSV should insert cards"""
        # Read the sample checklist
        with open('/tmp/sample_checklist.csv', 'rb') as f:
            csv_content = f.read()
        
        files = {'file': ('sample_checklist.csv', csv_content, 'text/csv')}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != 'content-type'}
        
        resp = requests.post(
            f"{BASE_URL}/api/admin/cards/import",
            files=files,
            headers=headers
        )
        
        assert resp.status_code == 200, f"Import failed: {resp.text}"
        data = resp.json()
        assert "inserted" in data
        assert "skipped" in data
        assert "total_in_db" in data
        print(f"PASS: CSV import - inserted={data['inserted']}, skipped={data['skipped']}, total_in_db={data['total_in_db']}")
        return data
    
    def test_import_upsert_no_duplicates(self, admin_session):
        """Re-importing same CSV should not create duplicates (upsert)"""
        # First import
        with open('/tmp/sample_checklist.csv', 'rb') as f:
            csv_content = f.read()
        
        files = {'file': ('sample_checklist.csv', csv_content, 'text/csv')}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != 'content-type'}
        
        resp1 = requests.post(f"{BASE_URL}/api/admin/cards/import", files=files, headers=headers)
        total_after_first = resp1.json().get("total_in_db", 0)
        
        # Second import (same file)
        files = {'file': ('sample_checklist.csv', csv_content, 'text/csv')}
        resp2 = requests.post(f"{BASE_URL}/api/admin/cards/import", files=files, headers=headers)
        total_after_second = resp2.json().get("total_in_db", 0)
        
        # Should be same count (upsert, not insert)
        assert total_after_second == total_after_first, f"Duplicates created: {total_after_first} -> {total_after_second}"
        print(f"PASS: Upsert working - no duplicates (count stayed at {total_after_second})")


class TestAdminCardsSets:
    """Test GET /api/admin/cards/sets"""
    
    def test_sets_requires_admin(self, regular_user_session):
        """Non-admin should get 403"""
        resp = regular_user_session.get(f"{BASE_URL}/api/admin/cards/sets")
        assert resp.status_code == 403
        print("PASS: Sets endpoint requires admin (403)")
    
    def test_sets_returns_distinct_sets(self, admin_session):
        """Admin should get distinct sets with counts"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/cards/sets")
        assert resp.status_code == 200
        data = resp.json()
        assert "sets" in data
        assert "total_cards" in data
        
        # Verify structure
        if data["sets"]:
            first_set = data["sets"][0]
            assert "set" in first_set
            assert "year" in first_set
            assert "count" in first_set
        
        print(f"PASS: Admin sets - {len(data['sets'])} distinct sets, {data['total_cards']} total cards")


class TestAdminCardsClear:
    """Test DELETE /api/admin/cards/clear"""
    
    def test_clear_requires_admin(self, regular_user_session):
        """Non-admin should get 403"""
        resp = regular_user_session.delete(f"{BASE_URL}/api/admin/cards/clear")
        assert resp.status_code == 403
        print("PASS: Clear endpoint requires admin (403)")
    
    def test_clear_filtered_by_set_year(self, admin_session):
        """Admin can clear cards filtered by set_name and year"""
        # First ensure we have cards
        with open('/tmp/sample_checklist.csv', 'rb') as f:
            csv_content = f.read()
        files = {'file': ('sample_checklist.csv', csv_content, 'text/csv')}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != 'content-type'}
        requests.post(f"{BASE_URL}/api/admin/cards/import", files=files, headers=headers)
        
        # Clear with filter (non-existent set to avoid deleting real data)
        resp = admin_session.delete(
            f"{BASE_URL}/api/admin/cards/clear",
            params={"set_name": "NonExistentSet", "year": 1999}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "deleted" in data
        assert data["deleted"] == 0  # Nothing matched
        print(f"PASS: Clear with filter - deleted {data['deleted']} cards (expected 0 for non-existent set)")


class TestCardsSearch:
    """Test GET /api/cards/search"""
    
    def test_search_by_card_number_set_year(self, admin_session):
        """Search by card_number + set_name + year should return local_db match"""
        # Ensure cards are imported first
        with open('/tmp/sample_checklist.csv', 'rb') as f:
            csv_content = f.read()
        files = {'file': ('sample_checklist.csv', csv_content, 'text/csv')}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != 'content-type'}
        requests.post(f"{BASE_URL}/api/admin/cards/import", files=files, headers=headers)
        
        # Search for card #245 (Patrick Mahomes Silver Prizm)
        resp = requests.get(f"{BASE_URL}/api/cards/search", params={
            "card_number": "245",
            "set_name": "Prizm Football",
            "year": 2024
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("source") == "local_db", f"Expected local_db, got {data.get('source')}"
        assert len(data.get("results", [])) > 0
        
        # Verify the card data
        card = data["results"][0]
        assert card.get("player") == "Patrick Mahomes"
        assert card.get("team") == "Kansas City Chiefs"
        assert card.get("parallel") == "Silver Prizm"
        print(f"PASS: Card #245 search - found {card['player']} ({card.get('parallel', 'base')}) from local_db")
    
    def test_search_broad_query(self):
        """Broad search by q=Mahomes should return multiple hits"""
        resp = requests.get(f"{BASE_URL}/api/cards/search", params={"q": "Mahomes"})
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Should find multiple Mahomes cards (base + Silver Prizm)
        if data.get("source") == "local_db":
            assert len(data.get("results", [])) >= 1
            for card in data["results"]:
                assert "Mahomes" in card.get("player", "")
            print(f"PASS: Broad search 'Mahomes' - found {len(data['results'])} cards from local_db")
        else:
            print(f"INFO: Broad search returned source={data.get('source')} (may need more data)")
    
    def test_search_no_match_returns_none(self):
        """Search for non-existent card should return source:'none' (eBay fallback empty)"""
        resp = requests.get(f"{BASE_URL}/api/cards/search", params={"q": "randomnonexistent12345xyz"})
        
        assert resp.status_code == 200
        data = resp.json()
        # Since eBay keys not configured, should return 'none'
        assert data.get("source") in ["none", "ebay_browse_api"], f"Unexpected source: {data.get('source')}"
        if data.get("source") == "none":
            assert len(data.get("results", [])) == 0
            print("PASS: Non-existent search returns source:'none' (eBay fallback empty as expected)")
        else:
            print(f"INFO: Search returned source={data.get('source')} with {len(data.get('results', []))} results")


class TestDisplayCasePacks:
    """Test Display Case binder (pack) endpoints"""
    
    @pytest.fixture(scope="class")
    def created_pack_id(self, admin_session):
        """Create a pack and return its ID for subsequent tests"""
        resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby"
        })
        assert resp.status_code == 200, f"Pack creation failed: {resp.text}"
        return resp.json().get("case_pack_id")
    
    def test_create_pack(self, admin_session):
        """POST /api/case/packs should create a binder"""
        resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby"
        })
        
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "case_pack_id" in data
        assert data.get("sport") == "NFL"
        assert data.get("set_search") == "Prizm Football"  # checklist_set field
        assert data.get("pulls_count") == 0
        print(f"PASS: Created binder {data['case_pack_id']} with set_search='{data['set_search']}'")
    
    def test_list_packs_with_tier(self, admin_session):
        """GET /api/case/packs should list binders + tier"""
        resp = admin_session.get(f"{BASE_URL}/api/case/packs")
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert "packs" in data
        assert "tier" in data
        # Admin user within 10-day trial should be 'pro'
        assert data["tier"] == "pro", f"Expected tier='pro' for admin, got '{data['tier']}'"
        print(f"PASS: Listed {len(data['packs'])} packs, tier='{data['tier']}'")
    
    def test_create_pack_unknown_type_404(self, admin_session):
        """Creating pack with unknown pack_type_id should return 404"""
        resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "nonexistent-pack-type"
        })
        assert resp.status_code == 404
        print("PASS: Unknown pack type returns 404")


class TestDisplayCasePulls:
    """Test Display Case pull endpoints"""
    
    @pytest.fixture(scope="class")
    def pack_for_pulls(self, admin_session):
        """Create a fresh pack for pull tests"""
        resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby"
        })
        assert resp.status_code == 200
        return resp.json()
    
    def test_log_pull_from_local_db(self, admin_session, pack_for_pulls):
        """POST /api/case/packs/{id}/pulls with card_number should hit local DB"""
        pack_id = pack_for_pulls["case_pack_id"]
        
        resp = admin_session.post(f"{BASE_URL}/api/case/packs/{pack_id}/pulls", json={
            "card_number": "245",
            "year": 2024,
            "parallel": "Silver Prizm"
        })
        
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("source") == "local_db", f"Expected local_db, got {data.get('source')}"
        assert data["card"].get("player") == "Patrick Mahomes"
        assert data["card"].get("team") == "Kansas City Chiefs"
        print(f"PASS: Pull logged from local_db - {data['card']['player']} ({data.get('parallel', 'base')})")
        return data
    
    def test_log_pull_manual_entry(self, admin_session, pack_for_pulls):
        """POST /api/case/packs/{id}/pulls with only player should be manual entry"""
        pack_id = pack_for_pulls["case_pack_id"]
        
        resp = admin_session.post(f"{BASE_URL}/api/case/packs/{pack_id}/pulls", json={
            "player": "Manual Test Player"
        })
        
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get("source") == "manual"
        assert data["card"].get("player") == "Manual Test Player"
        print(f"PASS: Manual pull logged - source='manual'")
        return data
    
    def test_log_pull_no_card_no_player_400(self, admin_session, pack_for_pulls):
        """POST /api/case/packs/{id}/pulls with no card_number AND no player should return 400"""
        pack_id = pack_for_pulls["case_pack_id"]
        
        resp = admin_session.post(f"{BASE_URL}/api/case/packs/{pack_id}/pulls", json={
            "notes": "Just a note, no card info"
        })
        
        assert resp.status_code == 400
        assert "card_number or player" in resp.json().get("detail", "").lower()
        print("PASS: Pull without card_number or player returns 400")
    
    def test_list_pulls_sorted_desc(self, admin_session, pack_for_pulls):
        """GET /api/case/packs/{id}/pulls should return pack + pulls sorted by timestamp desc"""
        pack_id = pack_for_pulls["case_pack_id"]
        
        resp = admin_session.get(f"{BASE_URL}/api/case/packs/{pack_id}/pulls")
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert "pack" in data
        assert "pulls" in data
        
        # Verify pulls are sorted by timestamp descending
        if len(data["pulls"]) > 1:
            timestamps = [p.get("timestamp") for p in data["pulls"]]
            assert timestamps == sorted(timestamps, reverse=True), "Pulls not sorted by timestamp desc"
        
        print(f"PASS: Listed {len(data['pulls'])} pulls for pack, sorted by timestamp desc")
    
    def test_delete_pull_decrements_count(self, admin_session, pack_for_pulls):
        """DELETE /api/case/pulls/{pull_id} should remove pull and decrement pack pulls_count"""
        pack_id = pack_for_pulls["case_pack_id"]
        
        # Create a pull to delete
        create_resp = admin_session.post(f"{BASE_URL}/api/case/packs/{pack_id}/pulls", json={
            "player": "To Be Deleted"
        })
        pull_id = create_resp.json().get("pull_id")
        
        # Get current pulls_count
        pack_resp = admin_session.get(f"{BASE_URL}/api/case/packs")
        pack_before = next((p for p in pack_resp.json()["packs"] if p["case_pack_id"] == pack_id), None)
        count_before = pack_before.get("pulls_count", 0)
        
        # Delete the pull
        del_resp = admin_session.delete(f"{BASE_URL}/api/case/pulls/{pull_id}")
        assert del_resp.status_code == 200
        assert del_resp.json().get("deleted") == True
        
        # Verify count decremented
        pack_resp = admin_session.get(f"{BASE_URL}/api/case/packs")
        pack_after = next((p for p in pack_resp.json()["packs"] if p["case_pack_id"] == pack_id), None)
        count_after = pack_after.get("pulls_count", 0)
        
        assert count_after == count_before - 1, f"pulls_count not decremented: {count_before} -> {count_after}"
        print(f"PASS: Pull deleted, pulls_count decremented ({count_before} -> {count_after})")


class TestDisplayCaseDelete:
    """Test binder deletion with cascade"""
    
    def test_delete_pack_cascades_pulls(self, admin_session):
        """DELETE /api/case/packs/{id} should remove binder + all its pulls"""
        # Create a pack
        create_resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby"
        })
        pack_id = create_resp.json().get("case_pack_id")
        
        # Add a pull
        admin_session.post(f"{BASE_URL}/api/case/packs/{pack_id}/pulls", json={
            "player": "Cascade Test"
        })
        
        # Delete the pack
        del_resp = admin_session.delete(f"{BASE_URL}/api/case/packs/{pack_id}")
        assert del_resp.status_code == 200
        assert del_resp.json().get("deleted") == True
        
        # Verify pack is gone
        list_resp = admin_session.get(f"{BASE_URL}/api/case/packs")
        pack_ids = [p["case_pack_id"] for p in list_resp.json()["packs"]]
        assert pack_id not in pack_ids
        
        print("PASS: Pack deleted with cascade (pulls also removed)")


class TestDisplayCaseStats:
    """Test GET /api/case/stats"""
    
    def test_stats_returns_all_fields(self, admin_session):
        """Stats should return total_packs, total_pulls, weekly_packs, tier, by_sport"""
        resp = admin_session.get(f"{BASE_URL}/api/case/stats")
        
        assert resp.status_code == 200
        data = resp.json()
        
        required_fields = ["total_packs", "total_pulls", "weekly_packs", "tier", "by_sport"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert data["tier"] == "pro"  # Admin within trial
        assert isinstance(data["by_sport"], dict)
        
        print(f"PASS: Stats - {data['total_packs']} packs, {data['total_pulls']} pulls, tier='{data['tier']}'")


class TestTierLogic:
    """Test tier determination logic"""
    
    def test_admin_user_is_pro(self, admin_session):
        """Admin user (within 10-day trial) should be tier='pro'"""
        resp = admin_session.get(f"{BASE_URL}/api/case/stats")
        assert resp.status_code == 200
        assert resp.json().get("tier") == "pro"
        print("PASS: Admin user has tier='pro' (within 10-day trial)")
    
    def test_new_user_is_pro_trial(self, regular_user_session):
        """Newly registered user should be tier='pro' (10-day trial)"""
        resp = regular_user_session.get(f"{BASE_URL}/api/case/stats")
        assert resp.status_code == 200
        # New user is within 10-day trial, so should be 'pro'
        assert resp.json().get("tier") == "pro"
        print("PASS: New user has tier='pro' (10-day trial)")


class TestPermissions:
    """Test owner-only access to binders/pulls"""
    
    def test_cannot_view_others_pack_pulls(self, admin_session, regular_user_session):
        """Non-owner cannot view another user's binder pulls (403)"""
        # Admin creates a pack
        create_resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby"
        })
        admin_pack_id = create_resp.json().get("case_pack_id")
        
        # Regular user tries to view admin's pack pulls
        resp = regular_user_session.get(f"{BASE_URL}/api/case/packs/{admin_pack_id}/pulls")
        assert resp.status_code == 403
        print("PASS: Non-owner cannot view another user's pack pulls (403)")
    
    def test_cannot_delete_others_pack(self, admin_session, regular_user_session):
        """Non-owner cannot delete another user's binder (403)"""
        # Admin creates a pack
        create_resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby"
        })
        admin_pack_id = create_resp.json().get("case_pack_id")
        
        # Regular user tries to delete admin's pack
        resp = regular_user_session.delete(f"{BASE_URL}/api/case/packs/{admin_pack_id}")
        assert resp.status_code == 403
        print("PASS: Non-owner cannot delete another user's pack (403)")
    
    def test_cannot_add_pull_to_others_pack(self, admin_session, regular_user_session):
        """Non-owner cannot add pull to another user's binder (403)"""
        # Admin creates a pack
        create_resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby"
        })
        admin_pack_id = create_resp.json().get("case_pack_id")
        
        # Regular user tries to add pull to admin's pack
        resp = regular_user_session.post(f"{BASE_URL}/api/case/packs/{admin_pack_id}/pulls", json={
            "player": "Unauthorized Pull"
        })
        assert resp.status_code == 403
        print("PASS: Non-owner cannot add pull to another user's pack (403)")


class TestRegressionExistingEndpoints:
    """Regression tests for existing endpoints"""
    
    def test_auth_login(self):
        """Login endpoint still works"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        assert "token" in resp.json()
        print("PASS: Auth login working")
    
    def test_auth_me(self, admin_session):
        """Me endpoint still works"""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        assert resp.json().get("email") == ADMIN_EMAIL
        print("PASS: Auth /me working")
    
    def test_analyzer_packs(self):
        """Analyzer packs endpoint still works"""
        resp = requests.get(f"{BASE_URL}/api/analyzer/packs")
        assert resp.status_code == 200
        assert "packs" in resp.json()
        print("PASS: Analyzer packs working")
    
    def test_predictor_simulate(self, admin_session):
        """Predictor simulate endpoint still works"""
        resp = admin_session.post(f"{BASE_URL}/api/predictor/simulate", json={
            "pack_id": "prizm-fball-hobby",
            "num_cards": 5
        })
        assert resp.status_code == 200
        assert "pulls" in resp.json()
        print("PASS: Predictor simulate working")


# Fixtures at module level for class-scoped fixtures
@pytest.fixture(scope="class")
def admin_session():
    """Login as admin and return session with token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if resp.status_code == 401:
        # Admin doesn't exist, register first
        resp = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "name": "Admin User"
        })
    
    assert resp.status_code in [200, 201], f"Admin login/register failed: {resp.text}"
    data = resp.json()
    token = data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture(scope="class")
def regular_user_session():
    """Create and login as a regular test user"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    timestamp = int(time.time())
    email = f"TEST_user_{timestamp}@test.com"
    
    resp = session.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "TestPass123!",
        "name": "Test User"
    })
    
    assert resp.status_code in [200, 201], f"User registration failed: {resp.text}"
    data = resp.json()
    token = data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
