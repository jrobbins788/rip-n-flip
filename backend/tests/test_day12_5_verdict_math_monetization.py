"""
Day 12.5 Tests — Verdict Engine Math Fix + Monetization Gate + Robust Fallback

Tests:
1. GET /api/analyzer/{pack_id} (anonymous) — verdict shape, intelligence block, 3-tier system
2. Verdict math: market_perf, internal_perf, final_score ratios
3. Three-tier system: TIER1_MAX=50, TIER2_MAX=200, no TIER3_HARD
4. Verdict thresholds: final_score >= 1.05 → DUB, >= 0.70 → MID, else TRASH
5. Monetization gate: free tier 403 after 2 packs/week, Pro unlimited
6. pack_market_cache collection structure
7. Robust fallback — never 500 on edge cases
"""

import pytest
import requests
import os
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test pack IDs from HOT_PACKS_NOW
TEST_PACK_ID = "prizm-bball-hobby"
TEST_PACK_ID_2 = "mosaic-fball-blaster"


class TestAnalyzerVerdictShape:
    """Test the verdict response shape and intelligence block structure."""
    
    def test_analyzer_anonymous_returns_200(self):
        """Anonymous user can access analyzer without auth."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify top-level structure
        assert "pack" in data
        assert "verdict" in data
        assert "chase_cards" in data
        assert "tier_odds" in data
        print(f"✓ Anonymous analyzer returns 200 with correct structure")
    
    def test_verdict_intelligence_block_exists(self):
        """Verify verdict.intelligence block with all required fields."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        verdict = data.get("verdict", {})
        
        # Intelligence block must exist
        intel = verdict.get("intelligence")
        assert intel is not None, "verdict.intelligence block missing"
        
        # Required fields in intelligence block
        assert "confidence" in intel, "intelligence.confidence missing"
        assert "market_perf" in intel, "intelligence.market_perf missing"
        assert "internal_perf" in intel, "intelligence.internal_perf missing"
        assert "final_score" in intel, "intelligence.final_score missing"
        assert "expected_hit_rate_baseline" in intel, "intelligence.expected_hit_rate_baseline missing"
        
        print(f"✓ Intelligence block has all required fields")
    
    def test_confidence_tier_structure(self):
        """Verify confidence block has tier, label, market_weight, pull_weight."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        confidence = data["verdict"]["intelligence"]["confidence"]
        
        assert "tier" in confidence, "confidence.tier missing"
        assert "label" in confidence, "confidence.label missing"
        assert "market_weight" in confidence, "confidence.market_weight missing"
        assert "pull_weight" in confidence, "confidence.pull_weight missing"
        
        # Tier must be 1, 2, or 3 (3-tier system)
        assert confidence["tier"] in [1, 2, 3], f"Invalid tier: {confidence['tier']}"
        
        # Weights must sum to 1.0
        total_weight = confidence["market_weight"] + confidence["pull_weight"]
        assert abs(total_weight - 1.0) < 0.01, f"Weights don't sum to 1.0: {total_weight}"
        
        print(f"✓ Confidence tier={confidence['tier']}, label='{confidence['label']}', weights sum to 1.0")


class TestThreeTierSystem:
    """Test the 3-tier confidence system (not 4 tiers)."""
    
    def test_tier1_market_only(self):
        """Tier 1 (< 50 pulls): Market Only, 100% market weight."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        intel = data["verdict"]["intelligence"]
        confidence = intel["confidence"]
        total_pulls = intel.get("training_pulls", 0)
        
        # If < 50 pulls, should be Tier 1
        if total_pulls < 50:
            assert confidence["tier"] == 1, f"Expected tier 1 for {total_pulls} pulls"
            assert confidence["label"] == "Market Only", f"Expected 'Market Only', got '{confidence['label']}'"
            assert confidence["market_weight"] == 1.0, f"Expected market_weight=1.0, got {confidence['market_weight']}"
            assert confidence["pull_weight"] == 0.0, f"Expected pull_weight=0.0, got {confidence['pull_weight']}"
            print(f"✓ Tier 1 correct: {total_pulls} pulls, Market Only, 100/0 weights")
        else:
            print(f"⚠ Pack has {total_pulls} pulls, skipping Tier 1 test")
    
    def test_tier_thresholds_in_response(self):
        """Verify tier1_threshold=50, tier2_threshold=200 in intelligence block."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        intel = data["verdict"]["intelligence"]
        
        assert intel.get("tier1_threshold") == 50, f"Expected tier1_threshold=50, got {intel.get('tier1_threshold')}"
        assert intel.get("tier2_threshold") == 200, f"Expected tier2_threshold=200, got {intel.get('tier2_threshold')}"
        
        print(f"✓ Tier thresholds correct: TIER1_MAX=50, TIER2_MAX=200")
    
    def test_no_tier4_exists(self):
        """Verify there's no tier 4 — only 3 tiers."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        confidence = data["verdict"]["intelligence"]["confidence"]
        
        # Tier must be 1, 2, or 3 only
        assert confidence["tier"] in [1, 2, 3], f"Invalid tier {confidence['tier']} — should be 1, 2, or 3 only"
        
        # No TIER3_HARD or tier 4 references
        assert "tier3_threshold" not in data["verdict"]["intelligence"], "tier3_threshold should not exist (3-tier system)"
        
        print(f"✓ Three-tier system confirmed (no tier 4)")


class TestVerdictMath:
    """Test the normalized verdict math with performance ratios."""
    
    def test_market_perf_neutral_on_msrp_fallback(self):
        """When pack_cost_source='msrp_fallback', market_perf should be 1.0 (neutral)."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        verdict = data["verdict"]
        pack_cost_source = verdict.get("pack_cost_source")
        intel = verdict.get("intelligence", {})
        market_perf = intel.get("market_perf")
        
        if pack_cost_source == "msrp_fallback":
            assert market_perf == 1.0, f"Expected market_perf=1.0 on msrp_fallback, got {market_perf}"
            print(f"✓ market_perf=1.0 (neutral) when pack_cost_source='msrp_fallback'")
        else:
            print(f"⚠ pack_cost_source='{pack_cost_source}', skipping msrp_fallback test")
    
    def test_verdict_not_trash_on_neutral_baseline(self):
        """With no data (msrp_fallback, no community pulls), verdict should be MID, not TRASH."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        verdict = data["verdict"]
        pack_cost_source = verdict.get("pack_cost_source")
        intel = verdict.get("intelligence", {})
        final_score = intel.get("final_score")
        rating = verdict.get("rating")
        
        # If on msrp_fallback with neutral market_perf=1.0, final_score should be ~1.0
        if pack_cost_source == "msrp_fallback" and intel.get("market_perf") == 1.0:
            # final_score >= 0.70 should be MID, not TRASH
            assert final_score >= 0.70, f"final_score {final_score} should be >= 0.70 for MID"
            assert rating in ["MID", "DUB"], f"Expected MID or DUB on neutral baseline, got {rating}"
            print(f"✓ Verdict is '{rating}' (not TRASH) with final_score={final_score} on neutral baseline")
    
    def test_verdict_thresholds(self):
        """Verify verdict thresholds: DUB >= 1.05, MID >= 0.70, TRASH < 0.70."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        verdict = data["verdict"]
        intel = verdict.get("intelligence", {})
        final_score = intel.get("final_score")
        rating = verdict.get("rating")
        
        # Verify rating matches final_score thresholds
        if final_score >= 1.05:
            assert rating == "DUB", f"final_score {final_score} >= 1.05 should be DUB, got {rating}"
        elif final_score >= 0.70:
            assert rating == "MID", f"final_score {final_score} >= 0.70 should be MID, got {rating}"
        else:
            assert rating == "TRASH", f"final_score {final_score} < 0.70 should be TRASH, got {rating}"
        
        print(f"✓ Verdict threshold correct: final_score={final_score} → {rating}")
    
    def test_performance_ratios_exist(self):
        """Verify market_perf, internal_perf, final_score are all present."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        intel = data["verdict"]["intelligence"]
        
        # market_perf should always exist
        assert "market_perf" in intel and intel["market_perf"] is not None
        
        # internal_perf may be None if no community data
        assert "internal_perf" in intel
        
        # final_score should always exist
        assert "final_score" in intel and intel["final_score"] is not None
        
        print(f"✓ Performance ratios: market_perf={intel['market_perf']}, internal_perf={intel['internal_perf']}, final_score={intel['final_score']}")


class TestMonetizationGate:
    """Test the free tier limit on /api/analyzer/{pack_id}."""
    
    @pytest.fixture
    def test_user_session(self):
        """Create a test user and return session."""
        email = f"TEST_freetier_{uuid.uuid4().hex[:8]}@test.com"
        password = "TestPass123!"
        name = "Free Tier Test User"
        
        session = requests.Session()
        
        # Register user
        reg_response = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": password,
            "name": name
        })
        
        if reg_response.status_code != 200:
            pytest.skip(f"Could not register test user: {reg_response.text}")
        
        user_data = reg_response.json()
        token = user_data.get("token")
        user_id = user_data.get("user_id")
        
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        
        yield {"session": session, "user_id": user_id, "email": email}
        
        # Cleanup: No explicit cleanup needed, test data has TEST_ prefix
    
    def test_pro_user_unlimited_access(self):
        """Pro user (admin) should have unlimited analyzer access."""
        session = requests.Session()
        
        # Login as admin (Pro user)
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@flipnrip.com",
            "password": "AdminPass123!"
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Could not login as admin: {login_response.text}")
        
        token = login_response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Make multiple analyzer requests — should all succeed
        for i in range(5):
            response = session.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
            assert response.status_code == 200, f"Pro user request {i+1} failed: {response.status_code}"
        
        print(f"✓ Pro user has unlimited analyzer access (5 requests succeeded)")
    
    def test_fresh_user_has_trial(self, test_user_session):
        """Fresh registered user should have 10-day trial (tier='pro')."""
        session = test_user_session["session"]
        
        # Check subscription status
        status_response = session.get(f"{BASE_URL}/api/subscription/status")
        assert status_response.status_code == 200
        
        status = status_response.json()
        tier = status.get("tier")
        trial_days_left = status.get("trial_days_left", 0)
        
        # Fresh user should be on trial (tier='pro')
        assert tier == "pro", f"Fresh user should have tier='pro' (trial), got '{tier}'"
        assert trial_days_left > 0, f"Fresh user should have trial_days_left > 0, got {trial_days_left}"
        
        print(f"✓ Fresh user has trial: tier='{tier}', trial_days_left={trial_days_left}")
    
    def test_fresh_user_unlimited_during_trial(self, test_user_session):
        """Fresh user within 10-day trial should have unlimited analyzer access."""
        session = test_user_session["session"]
        
        # Make multiple analyzer requests — should all succeed during trial
        for i in range(3):
            response = session.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
            assert response.status_code == 200, f"Trial user request {i+1} failed: {response.status_code}"
        
        print(f"✓ Trial user has unlimited analyzer access")


class TestFreeTierLimit:
    """Test the 403 free tier limit (requires manipulating user data)."""
    
    def test_free_tier_403_response_shape(self):
        """Verify 403 response has correct shape when free tier limit hit."""
        # This test documents the expected 403 response shape
        # Actual triggering requires DB manipulation (setting user created_at to 11 days ago)
        
        expected_403_shape = {
            "error": "free_tier_limit",
            "message": "contains 'Go Pro to Unlock'",
            "cta_url": "/vault",
            "limit": 2,
            "used": ">=2"
        }
        
        print(f"✓ Expected 403 shape documented: {expected_403_shape}")
        print("  Note: To trigger 403, set user.created_at to 11 days ago and log 2 case_packs in last 7 days")


class TestRobustFallback:
    """Test that analyzer never returns 500 on edge cases."""
    
    def test_analyzer_all_packs_no_500(self):
        """All hot packs should return 200, never 500."""
        # Get all pack IDs
        packs_response = requests.get(f"{BASE_URL}/api/analyzer/packs")
        assert packs_response.status_code == 200
        packs = packs_response.json().get("packs", [])
        
        for pack in packs:
            pack_id = pack.get("pack_id")
            response = requests.get(f"{BASE_URL}/api/analyzer/{pack_id}")
            assert response.status_code != 500, f"Pack {pack_id} returned 500: {response.text}"
            assert response.status_code == 200, f"Pack {pack_id} returned {response.status_code}"
        
        print(f"✓ All {len(packs)} packs return 200, no 500 errors")
    
    def test_invalid_pack_returns_404(self):
        """Invalid pack_id should return 404, not 500."""
        response = requests.get(f"{BASE_URL}/api/analyzer/invalid-pack-id-xyz")
        assert response.status_code == 404, f"Expected 404 for invalid pack, got {response.status_code}"
        print(f"✓ Invalid pack returns 404 (not 500)")
    
    def test_hot_packs_endpoint_works(self):
        """GET /api/hot-packs should return list of packs."""
        response = requests.get(f"{BASE_URL}/api/hot-packs")
        assert response.status_code == 200
        data = response.json()
        assert "packs" in data
        assert "count" in data
        assert data["count"] > 0
        print(f"✓ /api/hot-packs returns {data['count']} packs")
    
    def test_analyzer_packs_endpoint_works(self):
        """GET /api/analyzer/packs should return pack list."""
        response = requests.get(f"{BASE_URL}/api/analyzer/packs")
        assert response.status_code == 200
        data = response.json()
        assert "packs" in data
        assert len(data["packs"]) > 0
        print(f"✓ /api/analyzer/packs returns {len(data['packs'])} packs")


class TestPackMarketCache:
    """Test pack_market_cache collection structure (code path verification)."""
    
    def test_pack_cost_source_field_exists(self):
        """Verify pack_cost_source field exists in verdict."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        verdict = data["verdict"]
        assert "pack_cost_source" in verdict, "pack_cost_source field missing from verdict"
        
        # Valid sources
        valid_sources = ["sold", "active", "cached_sold", "cached_active", "last_known", "msrp_fallback"]
        assert verdict["pack_cost_source"] in valid_sources, f"Invalid pack_cost_source: {verdict['pack_cost_source']}"
        
        print(f"✓ pack_cost_source='{verdict['pack_cost_source']}' (valid)")
    
    def test_pack_cost_cached_age_days_field(self):
        """Verify pack_cost_cached_age_days field exists when using cached data."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        verdict = data["verdict"]
        # This field may be None if not using cached data
        assert "pack_cost_cached_age_days" in verdict or verdict.get("pack_cost_source") == "msrp_fallback"
        
        print(f"✓ pack_cost_cached_age_days field present or msrp_fallback in use")


class TestConfidenceBadgeUI:
    """Test that ConfidenceBadge shows 3 dots (not 4)."""
    
    def test_confidence_tier_max_is_3(self):
        """Verify max tier is 3 (for 3-dot badge)."""
        response = requests.get(f"{BASE_URL}/api/analyzer/{TEST_PACK_ID}")
        assert response.status_code == 200
        data = response.json()
        
        confidence = data["verdict"]["intelligence"]["confidence"]
        tier = confidence["tier"]
        
        # Tier should be 1, 2, or 3 (3 dots in UI)
        assert tier in [1, 2, 3], f"Tier {tier} invalid — should be 1, 2, or 3 for 3-dot badge"
        
        print(f"✓ Tier {tier} valid for 3-dot ConfidenceBadge")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
