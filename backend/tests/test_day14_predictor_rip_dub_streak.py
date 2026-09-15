"""
Day 14 Testing: Kingbuilt /predictor/rip + DUB STREAK weekly reward + pro_until honor

Tests:
1. POST /api/predictor/rip — returns 8 cards with HIT at climax slot + Mystery placeholders
2. POST /api/predictor/rip with invalid pack_id → 404
3. POST /api/predictor/rip rate-limited → 429 with exact paywall copy
4. POST /api/leaderboard/award-weekly — admin-only, idempotent per ISO week
5. GET /api/leaderboard/recent-awards — public endpoint
6. _user_tier honors pro_until field correctly
"""
import pytest
import requests
import os
from datetime import datetime, timezone, timedelta
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@flipnrip.com"
ADMIN_PASSWORD = "AdminPass123!"


class TestPredictorRipEndpoint:
    """Tests for POST /api/predictor/rip — Kingbuilt pack simulator"""

    def test_rip_anonymous_returns_8_cards(self):
        """Anonymous user can rip a pack and get 8 cards"""
        response = requests.post(
            f"{BASE_URL}/api/predictor/rip",
            json={"pack_id": "prizm-fball-hobby", "num_cards": 8}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "cards" in data, "Response must have 'cards' array"
        assert len(data["cards"]) == 8, f"Expected 8 cards, got {len(data['cards'])}"
        assert "landed_a_hit" in data, "Response must have 'landed_a_hit'"
        assert "hit_probability" in data, "Response must have 'hit_probability'"
        assert "summary" in data, "Response must have 'summary'"
        assert "usage" in data, "Response must have 'usage'"
        
        # Verify summary structure
        summary = data["summary"]
        assert "card_count" in summary and summary["card_count"] == 8
        assert "hit_count" in summary
        assert "mystery_count" in summary
        assert "estimated_value_low" in summary
        assert "estimated_value_high" in summary
        assert "vs_retail_low" in summary
        assert "vs_retail_high" in summary
        
        print(f"✓ Anonymous rip returned {len(data['cards'])} cards, landed_a_hit={data['landed_a_hit']}")

    def test_rip_hit_at_climax_slot(self):
        """If landed_a_hit=true, the HIT card should be at the last position (climax slot)"""
        # Run multiple rips to find one with a hit
        for _ in range(10):
            response = requests.post(
                f"{BASE_URL}/api/predictor/rip",
                json={"pack_id": "prizm-bball-hobby", "num_cards": 8}
            )
            assert response.status_code == 200
            data = response.json()
            
            if data["landed_a_hit"]:
                cards = data["cards"]
                # The last card should be the hit
                last_card = cards[-1]
                assert last_card.get("is_hit") == True, f"Last card should be the HIT, got: {last_card}"
                
                # Base cards (0-6) should NOT be hits
                for i, card in enumerate(cards[:-1]):
                    assert card.get("is_hit") != True, f"Card at index {i} should not be a hit"
                
                print(f"✓ HIT card correctly placed at climax slot (last position)")
                return
        
        # If no hit in 10 tries, that's still valid (probabilistic)
        print("✓ No hit landed in 10 tries (probabilistic - valid behavior)")

    def test_rip_mystery_placeholders(self):
        """Cards without real data should have is_mystery=true and 'Mystery X Card' names"""
        response = requests.post(
            f"{BASE_URL}/api/predictor/rip",
            json={"pack_id": "prizm-fball-hobby", "num_cards": 8}
        )
        assert response.status_code == 200
        data = response.json()
        
        mystery_count = sum(1 for c in data["cards"] if c.get("is_mystery"))
        assert data["summary"]["mystery_count"] == mystery_count, "Summary mystery_count should match actual mystery cards"
        
        # Check mystery cards have proper naming
        for card in data["cards"]:
            if card.get("is_mystery"):
                assert "Mystery" in card.get("name", ""), f"Mystery card should have 'Mystery' in name: {card}"
        
        print(f"✓ Mystery placeholders working, {mystery_count} mystery cards in this rip")

    def test_rip_invalid_pack_id_returns_404(self):
        """POST /api/predictor/rip with invalid pack_id returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/predictor/rip",
            json={"pack_id": "nonexistent-pack-xyz", "num_cards": 8}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "Pack not found" in str(data.get("detail", "")), f"Expected 'Pack not found' in detail: {data}"
        print("✓ Invalid pack_id correctly returns 404 'Pack not found'")


class TestPredictorRateLimit:
    """Tests for predictor rate limiting with exact paywall copy"""

    def test_rate_limit_exact_paywall_copy(self):
        """
        Free user past daily limit gets 429 with exact message:
        "You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB."
        """
        # Create a test user with created_at 11 days ago (past trial)
        unique_id = uuid.uuid4().hex[:8]
        test_email = f"TEST_ratelimit_{unique_id}@test.com"
        test_password = "TestPass123!"
        
        # Register user
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": test_password, "name": "Rate Limit Test"}
        )
        assert reg_response.status_code == 200, f"Registration failed: {reg_response.text}"
        user_data = reg_response.json()
        user_id = user_data["user_id"]
        token = user_data["token"]
        
        # Directly manipulate DB to set created_at 11 days ago (past trial)
        from pymongo import MongoClient
        mongo_client = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = mongo_client[os.environ.get('DB_NAME', 'test_database')]
        
        past_date = (datetime.now(timezone.utc) - timedelta(days=11)).isoformat()
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"created_at": past_date, "tier": "free"}}
        )
        
        # Insert FREE_TIER_PREDICTOR_PER_DAY (2) usage records with recent timestamps
        for i in range(3):  # Insert 3 to exceed the limit of 2
            db.predictor_usage.insert_one({
                "user_id": user_id,
                "pack_id": "prizm-fball-hobby",
                "endpoint": "rip",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        
        # Now try to rip - should get 429
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(
            f"{BASE_URL}/api/predictor/rip",
            json={"pack_id": "prizm-fball-hobby", "num_cards": 8},
            headers=headers
        )
        
        assert response.status_code == 429, f"Expected 429, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        
        # Check exact paywall message (with curly apostrophe 'til)
        expected_message = "You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB."
        actual_message = detail.get("message", "")
        assert actual_message == expected_message, f"Expected exact message:\n'{expected_message}'\nGot:\n'{actual_message}'"
        
        assert detail.get("error") == "predictor_limit"
        assert detail.get("cta_url") == "/vault"
        
        print(f"✓ Rate limit returns 429 with exact paywall copy")
        
        # Cleanup
        db.users.delete_one({"user_id": user_id})
        db.predictor_usage.delete_many({"user_id": user_id})
        mongo_client.close()


class TestAwardWeeklyEndpoint:
    """Tests for POST /api/leaderboard/award-weekly — admin-only, idempotent"""

    def test_award_weekly_anonymous_returns_401(self):
        """Anonymous user gets 401"""
        response = requests.post(f"{BASE_URL}/api/leaderboard/award-weekly")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Anonymous user correctly gets 401 on award-weekly")

    def test_award_weekly_non_admin_returns_403(self):
        """Non-admin logged-in user gets 403"""
        # Create a regular user
        unique_id = uuid.uuid4().hex[:8]
        test_email = f"TEST_nonadmin_{unique_id}@test.com"
        
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": "TestPass123!", "name": "Non Admin Test"}
        )
        assert reg_response.status_code == 200
        token = reg_response.json()["token"]
        user_id = reg_response.json()["user_id"]
        
        # Try to call award-weekly
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(
            f"{BASE_URL}/api/leaderboard/award-weekly",
            headers=headers
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Non-admin user correctly gets 403 on award-weekly")
        
        # Cleanup
        from pymongo import MongoClient
        mongo_client = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = mongo_client[os.environ.get('DB_NAME', 'test_database')]
        db.users.delete_one({"user_id": user_id})
        mongo_client.close()

    def test_award_weekly_admin_success(self):
        """Admin can call award-weekly and get proper response structure"""
        # Login as admin
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        token = login_response.json()["token"]
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(
            f"{BASE_URL}/api/leaderboard/award-weekly",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "week_key" in data, "Response must have 'week_key'"
        assert "winners" in data, "Response must have 'winners'"
        
        # If not already_awarded, check full structure
        if not data.get("already_awarded"):
            assert "reward_days" in data
            assert data["reward_days"] == 14, f"Expected reward_days=14, got {data['reward_days']}"
            assert "already_awarded" in data
            assert data["already_awarded"] == False
            
            # Winners array structure (may be empty if no thumbs)
            for winner in data.get("winners", []):
                assert "rank" in winner
                assert "user_id" in winner
                assert "username" in winner
                assert "thumbs_total" in winner
                assert "pro_until" in winner
                assert "reward_days" in winner and winner["reward_days"] == 14
        
        print(f"✓ Admin award-weekly returned: week_key={data['week_key']}, winners={len(data.get('winners', []))}")
        return data

    def test_award_weekly_idempotent(self):
        """Calling award-weekly twice in same week returns already_awarded=true"""
        # Login as admin
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        token = login_response.json()["token"]
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # First call
        response1 = requests.post(
            f"{BASE_URL}/api/leaderboard/award-weekly",
            headers=headers
        )
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Second call - should be idempotent
        response2 = requests.post(
            f"{BASE_URL}/api/leaderboard/award-weekly",
            headers=headers
        )
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Second call should have already_awarded=true
        assert data2.get("already_awarded") == True, f"Second call should have already_awarded=true: {data2}"
        assert data2.get("week_key") == data1.get("week_key"), "Week key should match"
        
        print(f"✓ award-weekly is idempotent: second call returns already_awarded=true")


class TestRecentAwardsEndpoint:
    """Tests for GET /api/leaderboard/recent-awards — public endpoint"""

    def test_recent_awards_public_access(self):
        """Anonymous user can access recent-awards"""
        response = requests.get(f"{BASE_URL}/api/leaderboard/recent-awards?limit=8")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "awards" in data, "Response must have 'awards' array"
        assert "count" in data, "Response must have 'count'"
        assert isinstance(data["awards"], list), "awards must be a list"
        
        print(f"✓ recent-awards public access works, returned {data['count']} awards")

    def test_recent_awards_limit_parameter(self):
        """limit parameter caps the results"""
        response = requests.get(f"{BASE_URL}/api/leaderboard/recent-awards?limit=3")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["awards"]) <= 3, f"Expected max 3 awards, got {len(data['awards'])}"
        print(f"✓ recent-awards respects limit parameter")


class TestProUntilHonor:
    """Tests for _user_tier honoring pro_until field correctly"""

    def test_pro_until_in_future_returns_pro(self):
        """User with tier='pro' and pro_until in future should be treated as 'pro'"""
        # Create a test user
        unique_id = uuid.uuid4().hex[:8]
        test_email = f"TEST_prountil_future_{unique_id}@test.com"
        
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": "TestPass123!", "name": "Pro Until Future Test"}
        )
        assert reg_response.status_code == 200
        user_data = reg_response.json()
        user_id = user_data["user_id"]
        token = user_data["token"]
        
        # Set user to pro with pro_until in future, but created_at in past (past trial)
        from pymongo import MongoClient
        mongo_client = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = mongo_client[os.environ.get('DB_NAME', 'test_database')]
        
        past_date = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "created_at": past_date,
                "tier": "pro",
                "pro_until": future_date,
                "pro_source": "dub_streak_reward"
            }}
        )
        
        # Check tier via predictor/usage endpoint
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/api/predictor/usage",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("tier") == "pro", f"Expected tier='pro', got {data.get('tier')}"
        print(f"✓ User with pro_until in future correctly returns tier='pro'")
        
        # Cleanup
        db.users.delete_one({"user_id": user_id})
        mongo_client.close()

    def test_pro_until_in_past_returns_free(self):
        """User with tier='pro' but pro_until in past should be treated as 'free'"""
        # Create a test user
        unique_id = uuid.uuid4().hex[:8]
        test_email = f"TEST_prountil_past_{unique_id}@test.com"
        
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": "TestPass123!", "name": "Pro Until Past Test"}
        )
        assert reg_response.status_code == 200
        user_data = reg_response.json()
        user_id = user_data["user_id"]
        token = user_data["token"]
        
        # Set user to pro with pro_until in PAST, and created_at also in past (past trial)
        from pymongo import MongoClient
        mongo_client = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
        db = mongo_client[os.environ.get('DB_NAME', 'test_database')]
        
        past_created = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        past_pro_until = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "created_at": past_created,
                "tier": "pro",
                "pro_until": past_pro_until,
                "pro_source": "dub_streak_reward"
            }}
        )
        
        # Check tier via predictor/usage endpoint
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/api/predictor/usage",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("tier") == "free", f"Expected tier='free' (expired pro_until), got {data.get('tier')}"
        print(f"✓ User with pro_until in past correctly returns tier='free'")
        
        # Cleanup
        db.users.delete_one({"user_id": user_id})
        mongo_client.close()


class TestLegacySimulateEndpoint:
    """Verify /predictor/simulate still works for backward compat"""

    def test_simulate_still_works(self):
        """Legacy /predictor/simulate endpoint should still function"""
        response = requests.post(
            f"{BASE_URL}/api/predictor/simulate",
            json={"pack_id": "prizm-fball-hobby", "num_cards": 8}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pulls" in data, "Legacy simulate should have 'pulls' array"
        assert "summary" in data, "Legacy simulate should have 'summary'"
        
        print(f"✓ Legacy /predictor/simulate still works")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
