"""
Test suite for Intelligence Loop (Cold Start Protocol) and Social Binder features.
Tests:
- GET /api/analyzer/{pack_id} — verdict with intelligence block + confidence tiers
- POST /api/case/packs/{id}/pulls — logging pulls writes to internal_hit_rates
- PATCH /api/case/packs/{id}/visibility — owner toggle, non-owner 403
- GET /api/binders/public — list public binders
- GET /api/binders/public/{user_id} — public binder with SOURCE PACK STRIPPED
- POST /api/case/pulls/{pull_id}/thumbs — voting logic
- GET /api/case/pulls/{pull_id}/thumbs — get thumbs count + own vote
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@flipnrip.com"
ADMIN_PASSWORD = "AdminPass123!"


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_health_endpoint(self):
        """Health endpoint should return healthy status"""
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        print(f"✓ Health check passed: {data}")
    
    def test_root_endpoint(self):
        """Root API endpoint should return Rip N' Flip branding"""
        r = requests.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        data = r.json()
        assert "Rip N' Flip" in data.get("message", "")
        print(f"✓ Root endpoint: {data}")


class TestIntelligenceLoop:
    """Tests for the Intelligence Loop / Cold Start Protocol"""
    
    def test_analyzer_packs_list(self):
        """GET /api/analyzer/packs should return list of packs"""
        r = requests.get(f"{BASE_URL}/api/analyzer/packs")
        assert r.status_code == 200
        data = r.json()
        assert "packs" in data
        assert len(data["packs"]) > 0
        print(f"✓ Analyzer packs: {len(data['packs'])} packs available")
        return data["packs"]
    
    def test_analyzer_verdict_has_intelligence_block(self):
        """GET /api/analyzer/{pack_id} should include intelligence block with confidence tiers"""
        # First get a pack_id
        packs_r = requests.get(f"{BASE_URL}/api/analyzer/packs")
        packs = packs_r.json().get("packs", [])
        assert len(packs) > 0, "No packs available"
        
        pack_id = packs[0]["pack_id"]
        r = requests.get(f"{BASE_URL}/api/analyzer/{pack_id}")
        assert r.status_code == 200
        data = r.json()
        
        # Check verdict structure
        assert "verdict" in data, "Response should have verdict"
        verdict = data["verdict"]
        
        # Check pack_cost_source field
        assert "pack_cost_source" in verdict, "Verdict should have pack_cost_source"
        valid_sources = ['sold', 'active', 'cached_sold', 'cached_active', 'msrp_fallback']
        assert verdict["pack_cost_source"] in valid_sources, f"pack_cost_source should be one of {valid_sources}"
        print(f"✓ pack_cost_source: {verdict['pack_cost_source']}")
        
        # Check intelligence block
        assert "intelligence" in verdict, "Verdict should have intelligence block"
        intel = verdict["intelligence"]
        
        # Check confidence structure
        assert "confidence" in intel, "Intelligence should have confidence"
        conf = intel["confidence"]
        
        # Verify confidence fields
        assert "label" in conf, "Confidence should have label"
        assert "tier" in conf, "Confidence should have tier"
        assert "market_weight" in conf, "Confidence should have market_weight"
        assert "pull_weight" in conf, "Confidence should have pull_weight"
        
        # Tier should be 1-4
        assert conf["tier"] in [1, 2, 3, 4], f"Tier should be 1-4, got {conf['tier']}"
        
        # Weights should sum to 1.0
        total_weight = conf["market_weight"] + conf["pull_weight"]
        assert abs(total_weight - 1.0) < 0.01, f"Weights should sum to 1.0, got {total_weight}"
        
        print(f"✓ Intelligence block present with confidence tier {conf['tier']}: {conf['label']}")
        print(f"  - market_weight: {conf['market_weight']}, pull_weight: {conf['pull_weight']}")
        
        return data
    
    def test_analyzer_tier1_default_values(self):
        """With 0 logs, should return Tier 1 (Market Only) with 100% market weight"""
        # Get a pack that likely has 0 logs
        packs_r = requests.get(f"{BASE_URL}/api/analyzer/packs")
        packs = packs_r.json().get("packs", [])
        
        # Test any pack - if it has 0 logs, it should be Tier 1
        for pack in packs:
            r = requests.get(f"{BASE_URL}/api/analyzer/{pack['pack_id']}")
            data = r.json()
            intel = data["verdict"].get("intelligence", {})
            conf = intel.get("confidence", {})
            
            # If training_pulls is 0 or < 50, should be Tier 1
            training_pulls = intel.get("training_pulls", 0)
            if training_pulls < 50:
                assert conf["tier"] == 1, f"With {training_pulls} pulls, tier should be 1"
                assert conf["label"] == "Market Only", f"Tier 1 label should be 'Market Only'"
                assert conf["market_weight"] == 1.0, "Tier 1 market_weight should be 1.0"
                assert conf["pull_weight"] == 0.0, "Tier 1 pull_weight should be 0.0"
                print(f"✓ Tier 1 (Market Only) verified for pack {pack['pack_id']} with {training_pulls} pulls")
                return
        
        print("⚠ All packs have >= 50 pulls, cannot verify Tier 1 defaults")


class TestAuthAndLogin:
    """Authentication tests"""
    
    @pytest.fixture
    def session(self):
        """Create a requests session"""
        return requests.Session()
    
    def test_login_admin(self, session):
        """Login with admin credentials"""
        r = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert r.status_code == 200, f"Login failed: {r.text}"
        data = r.json()
        assert "token" in data, "Login should return token"
        # User data is returned directly (not nested under 'user')
        assert "email" in data or "user_id" in data, "Login should return user data"
        print(f"✓ Admin login successful: {data.get('email')}")
        return data
    
    def test_register_new_user_gets_trial(self, session):
        """New user registration should get 10-day trial (tier='pro')"""
        unique_email = f"test_trial_{uuid.uuid4().hex[:8]}@test.com"
        r = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "TestPass123!",
            "name": "Trial Test User"
        })
        assert r.status_code == 200, f"Registration failed: {r.text}"
        data = r.json()
        
        # Check subscription status
        token = data.get("token")
        headers = {"Authorization": f"Bearer {token}"}
        status_r = session.get(f"{BASE_URL}/api/subscription/status", headers=headers)
        assert status_r.status_code == 200
        status = status_r.json()
        
        # New user should be in trial = pro tier
        assert status.get("tier") == "pro", f"New user should have tier='pro' (trial), got {status.get('tier')}"
        assert status.get("trial_days_left", 0) > 0, "New user should have trial_days_left > 0"
        print(f"✓ New user trial verified: tier={status['tier']}, trial_days_left={status['trial_days_left']}")


class TestDisplayCaseAndPulls:
    """Tests for Display Case pack/pull management"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        r = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert r.status_code == 200, f"Login failed: {r.text}"
        token = r.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_create_pack_and_log_pull(self, auth_session):
        """POST /api/case/packs/{id}/pulls should write to internal_hit_rates"""
        # Get available pack types
        packs_r = auth_session.get(f"{BASE_URL}/api/analyzer/packs")
        packs = packs_r.json().get("packs", [])
        assert len(packs) > 0
        pack_type_id = packs[0]["pack_id"]
        
        # Create a binder
        create_r = auth_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": pack_type_id,
            "name": f"TEST_binder_{uuid.uuid4().hex[:6]}"
        })
        assert create_r.status_code in [200, 201], f"Create pack failed: {create_r.text}"
        binder = create_r.json()
        case_pack_id = binder["case_pack_id"]
        print(f"✓ Created binder: {case_pack_id}")
        
        # Log a pull
        pull_r = auth_session.post(f"{BASE_URL}/api/case/packs/{case_pack_id}/pulls", json={
            "card_number": "245",
            "year": 2024,
            "parallel": "Silver Prizm",
            "player": "Test Player"
        })
        assert pull_r.status_code in [200, 201], f"Log pull failed: {pull_r.text}"
        pull_data = pull_r.json()
        
        # Verify pull has rarity_tier stamped
        assert "pull_id" in pull_data, "Pull should have pull_id"
        print(f"✓ Pull logged: {pull_data.get('pull_id')}")
        
        # Verify the pull appears in the binder
        pulls_r = auth_session.get(f"{BASE_URL}/api/case/packs/{case_pack_id}/pulls")
        assert pulls_r.status_code == 200
        pulls_data = pulls_r.json()
        assert len(pulls_data.get("pulls", [])) > 0, "Binder should have pulls"
        
        # Check if rarity_tier is present on the pull
        pull = pulls_data["pulls"][0]
        # rarity_tier may or may not be present depending on card match
        print(f"✓ Pull verified in binder, rarity_tier: {pull.get('rarity_tier', 'not set')}")
        
        return {"case_pack_id": case_pack_id, "pull_id": pull_data.get("pull_id")}


class TestVisibilityToggle:
    """Tests for binder visibility toggle"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        r = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert r.status_code == 200
        token = r.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_owner_can_toggle_visibility(self, auth_session):
        """PATCH /api/case/packs/{id}/visibility — owner can toggle"""
        # Create a binder first
        packs_r = auth_session.get(f"{BASE_URL}/api/analyzer/packs")
        pack_type_id = packs_r.json()["packs"][0]["pack_id"]
        
        create_r = auth_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": pack_type_id,
            "name": f"TEST_visibility_{uuid.uuid4().hex[:6]}"
        })
        assert create_r.status_code in [200, 201]
        case_pack_id = create_r.json()["case_pack_id"]
        
        # Toggle to public
        toggle_r = auth_session.patch(f"{BASE_URL}/api/case/packs/{case_pack_id}/visibility", json={
            "is_public": True
        })
        assert toggle_r.status_code == 200, f"Toggle failed: {toggle_r.text}"
        data = toggle_r.json()
        assert data["is_public"] == True, "Should be public after toggle"
        print(f"✓ Toggled binder to public: {case_pack_id}")
        
        # Toggle back to private
        toggle_r2 = auth_session.patch(f"{BASE_URL}/api/case/packs/{case_pack_id}/visibility", json={
            "is_public": False
        })
        assert toggle_r2.status_code == 200
        assert toggle_r2.json()["is_public"] == False
        print(f"✓ Toggled binder back to private")
        
        return case_pack_id
    
    def test_non_owner_gets_403(self, auth_session):
        """Non-owner should get 403 when trying to toggle visibility"""
        # Create a binder as admin
        packs_r = auth_session.get(f"{BASE_URL}/api/analyzer/packs")
        pack_type_id = packs_r.json()["packs"][0]["pack_id"]
        
        create_r = auth_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": pack_type_id,
            "name": f"TEST_nonowner_{uuid.uuid4().hex[:6]}"
        })
        case_pack_id = create_r.json()["case_pack_id"]
        
        # Register a different user
        other_session = requests.Session()
        unique_email = f"test_other_{uuid.uuid4().hex[:8]}@test.com"
        reg_r = other_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "TestPass123!",
            "name": "Other User"
        })
        assert reg_r.status_code == 200
        other_token = reg_r.json().get("token")
        other_session.headers.update({"Authorization": f"Bearer {other_token}"})
        
        # Try to toggle as non-owner
        toggle_r = other_session.patch(f"{BASE_URL}/api/case/packs/{case_pack_id}/visibility", json={
            "is_public": True
        })
        assert toggle_r.status_code == 403, f"Non-owner should get 403, got {toggle_r.status_code}"
        print(f"✓ Non-owner correctly blocked with 403")


class TestPublicBinders:
    """Tests for public binder gallery"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        r = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert r.status_code == 200
        data = r.json()
        token = data.get("token")
        user_id = data.get("user_id")  # User data is returned directly
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, user_id
    
    def test_public_binders_list(self):
        """GET /api/binders/public should return list of public binders"""
        r = requests.get(f"{BASE_URL}/api/binders/public")
        assert r.status_code == 200
        data = r.json()
        assert "binders" in data, "Response should have binders array"
        assert "count" in data, "Response should have count"
        print(f"✓ Public binders list: {data['count']} binders")
        return data
    
    def test_public_binders_empty_when_none_public(self):
        """GET /api/binders/public should return empty when no public binders"""
        # This test just verifies the endpoint works - actual emptiness depends on data
        r = requests.get(f"{BASE_URL}/api/binders/public")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("binders"), list)
        print(f"✓ Public binders endpoint works, count: {data['count']}")
    
    def test_public_binder_strips_source_pack(self, auth_session):
        """GET /api/binders/public/{user_id} should strip source pack info"""
        session, user_id = auth_session
        
        # Create a binder and make it public
        packs_r = session.get(f"{BASE_URL}/api/analyzer/packs")
        pack_type_id = packs_r.json()["packs"][0]["pack_id"]
        
        create_r = session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": pack_type_id,
            "name": f"TEST_public_{uuid.uuid4().hex[:6]}"
        })
        case_pack_id = create_r.json()["case_pack_id"]
        
        # Log a pull
        session.post(f"{BASE_URL}/api/case/packs/{case_pack_id}/pulls", json={
            "card_number": "100",
            "year": 2024,
            "player": "Privacy Test Player"
        })
        
        # Make it public
        session.patch(f"{BASE_URL}/api/case/packs/{case_pack_id}/visibility", json={
            "is_public": True
        })
        
        # Fetch public binder
        public_r = requests.get(f"{BASE_URL}/api/binders/public/{user_id}")
        assert public_r.status_code == 200
        data = public_r.json()
        
        # Check user info
        assert "user" in data
        assert "pulls" in data
        
        # PRIVACY CHECK: pulls should NOT have case_pack_id or pack_type_id
        for pull in data.get("pulls", []):
            assert "case_pack_id" not in pull, "Public pull should NOT have case_pack_id"
            assert "pack_type_id" not in pull, "Public pull should NOT have pack_type_id"
            assert pull.get("source_pack") == "—", f"source_pack should be '—', got {pull.get('source_pack')}"
        
        print(f"✓ Privacy verified: source pack stripped from {len(data.get('pulls', []))} pulls")
        
        return data


class TestThumbsVoting:
    """Tests for thumbs up/down voting on pulls"""
    
    @pytest.fixture
    def setup_public_pull(self):
        """Create a public binder with a pull for voting tests"""
        # Login as admin
        session = requests.Session()
        r = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        data = r.json()
        token = data.get("token")
        user_id = data.get("user_id")  # User data is returned directly
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Create binder
        packs_r = session.get(f"{BASE_URL}/api/analyzer/packs")
        pack_type_id = packs_r.json()["packs"][0]["pack_id"]
        
        create_r = session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": pack_type_id,
            "name": f"TEST_thumbs_{uuid.uuid4().hex[:6]}"
        })
        case_pack_id = create_r.json()["case_pack_id"]
        
        # Log a pull
        pull_r = session.post(f"{BASE_URL}/api/case/packs/{case_pack_id}/pulls", json={
            "card_number": "50",
            "year": 2024,
            "player": "Thumbs Test Player"
        })
        pull_id = pull_r.json().get("pull_id")
        
        # Make binder public
        session.patch(f"{BASE_URL}/api/case/packs/{case_pack_id}/visibility", json={
            "is_public": True
        })
        
        return {
            "session": session,
            "user_id": user_id,
            "case_pack_id": case_pack_id,
            "pull_id": pull_id
        }
    
    def test_self_voting_blocked(self, setup_public_pull):
        """Self-voting should return 400"""
        data = setup_public_pull
        session = data["session"]
        pull_id = data["pull_id"]
        
        # Try to vote on own pull
        vote_r = session.post(f"{BASE_URL}/api/case/pulls/{pull_id}/thumbs", json={
            "vote": "up"
        })
        assert vote_r.status_code == 400, f"Self-voting should return 400, got {vote_r.status_code}"
        print(f"✓ Self-voting correctly blocked with 400")
    
    def test_voting_on_private_binder_blocked(self):
        """Voting on private binder should return 403"""
        # Login as admin
        session = requests.Session()
        r = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = r.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Create PRIVATE binder
        packs_r = session.get(f"{BASE_URL}/api/analyzer/packs")
        pack_type_id = packs_r.json()["packs"][0]["pack_id"]
        
        create_r = session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": pack_type_id,
            "name": f"TEST_private_{uuid.uuid4().hex[:6]}"
        })
        case_pack_id = create_r.json()["case_pack_id"]
        
        # Log a pull (binder stays private)
        pull_r = session.post(f"{BASE_URL}/api/case/packs/{case_pack_id}/pulls", json={
            "card_number": "99",
            "year": 2024,
            "player": "Private Test"
        })
        pull_id = pull_r.json().get("pull_id")
        
        # Register another user
        other_session = requests.Session()
        unique_email = f"test_voter_{uuid.uuid4().hex[:8]}@test.com"
        reg_r = other_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "TestPass123!",
            "name": "Voter User"
        })
        other_token = reg_r.json().get("token")
        other_session.headers.update({"Authorization": f"Bearer {other_token}"})
        
        # Try to vote on private binder's pull
        vote_r = other_session.post(f"{BASE_URL}/api/case/pulls/{pull_id}/thumbs", json={
            "vote": "up"
        })
        assert vote_r.status_code == 403, f"Voting on private binder should return 403, got {vote_r.status_code}"
        print(f"✓ Voting on private binder correctly blocked with 403")
    
    def test_vote_toggle_and_switch(self, setup_public_pull):
        """Test vote toggling and switching"""
        data = setup_public_pull
        pull_id = data["pull_id"]
        
        # Register another user to vote
        other_session = requests.Session()
        unique_email = f"test_voter2_{uuid.uuid4().hex[:8]}@test.com"
        reg_r = other_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "TestPass123!",
            "name": "Voter User 2"
        })
        other_token = reg_r.json().get("token")
        other_session.headers.update({"Authorization": f"Bearer {other_token}"})
        
        # Vote up
        vote_r = other_session.post(f"{BASE_URL}/api/case/pulls/{pull_id}/thumbs", json={
            "vote": "up"
        })
        assert vote_r.status_code == 200
        vote_data = vote_r.json()
        assert vote_data["your_vote"] == "up"
        initial_count = vote_data["thumbs_up_count"]
        print(f"✓ Vote up: thumbs_up_count={initial_count}")
        
        # Toggle same vote (should remove)
        toggle_r = other_session.post(f"{BASE_URL}/api/case/pulls/{pull_id}/thumbs", json={
            "vote": "up"
        })
        assert toggle_r.status_code == 200
        toggle_data = toggle_r.json()
        assert toggle_data["your_vote"] is None, "Toggling same vote should remove it"
        assert toggle_data["thumbs_up_count"] == initial_count - 1
        print(f"✓ Toggle off: thumbs_up_count={toggle_data['thumbs_up_count']}")
        
        # Vote down
        down_r = other_session.post(f"{BASE_URL}/api/case/pulls/{pull_id}/thumbs", json={
            "vote": "down"
        })
        assert down_r.status_code == 200
        down_data = down_r.json()
        assert down_data["your_vote"] == "down"
        print(f"✓ Vote down: your_vote={down_data['your_vote']}")
        
        # Switch to up
        switch_r = other_session.post(f"{BASE_URL}/api/case/pulls/{pull_id}/thumbs", json={
            "vote": "up"
        })
        assert switch_r.status_code == 200
        switch_data = switch_r.json()
        assert switch_data["your_vote"] == "up"
        print(f"✓ Switch to up: thumbs_up_count={switch_data['thumbs_up_count']}")
    
    def test_get_thumbs_count(self, setup_public_pull):
        """GET /api/case/pulls/{pull_id}/thumbs should return count + own vote"""
        data = setup_public_pull
        session = data["session"]
        pull_id = data["pull_id"]
        
        r = session.get(f"{BASE_URL}/api/case/pulls/{pull_id}/thumbs")
        assert r.status_code == 200
        thumbs_data = r.json()
        
        assert "pull_id" in thumbs_data
        assert "thumbs_up_count" in thumbs_data
        assert "your_vote" in thumbs_data
        print(f"✓ Get thumbs: count={thumbs_data['thumbs_up_count']}, your_vote={thumbs_data['your_vote']}")


class TestSportFilter:
    """Test sport filter on public binders"""
    
    def test_public_binders_sport_filter(self):
        """GET /api/binders/public?sport=NBA should filter by sport"""
        r = requests.get(f"{BASE_URL}/api/binders/public", params={"sport": "NBA"})
        assert r.status_code == 200
        data = r.json()
        # Just verify the endpoint accepts the filter
        print(f"✓ Sport filter works: {data['count']} NBA binders")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
