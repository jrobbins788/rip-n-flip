"""
Day 15 Testing: Backend Refactor + Battle CTA + Stripe Webhook Hardening

Tests for:
1. Subscription routes (moved to routes/subscription.py):
   - POST /api/subscription/checkout (requires auth, returns Stripe cs_test_ URL)
   - GET /api/subscription/status (auth, returns tier+trial info)
   - POST /api/subscription/cancel (auth, requires active sub)
   - GET /api/subscription/admin/info (admin only)
   - GET /api/subscription/webhook-mode (admin only)

2. Social routes (moved to routes/social.py):
   - GET /api/binders/public (gallery list)
   - GET /api/binders/public/{user_id} (single binder with privacy enforced)
   - PATCH /api/case/packs/{id}/visibility (owner-only)
   - POST /api/case/pulls/{id}/thumbs (cast vote)
   - GET /api/case/pulls/{id}/thumbs (read counter)

3. NEW Battle CTA endpoint:
   - GET /api/binders/public/{user_id}/battle-cta

4. Stripe webhook hardening:
   - POST /api/webhook/stripe-subscription (lenient mode + strict mode)
"""
import pytest
import requests
import os
import json
import uuid
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Admin credentials
ADMIN_EMAIL = "admin@flipnrip.com"
ADMIN_PASSWORD = "AdminPass123!"

# Known test user with public binders
TEST_USER_ID = "user_d87e752c00fd"


class TestSubscriptionRoutes:
    """Tests for subscription routes moved to routes/subscription.py"""

    def test_subscription_checkout_requires_auth(self):
        """POST /api/subscription/checkout requires authentication"""
        response = requests.post(f"{BASE_URL}/api/subscription/checkout", json={
            "origin_url": "https://example.com"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/subscription/checkout requires auth (401)")

    def test_subscription_checkout_returns_stripe_url(self):
        """POST /api/subscription/checkout returns real Stripe cs_test_ session"""
        session = requests.Session()
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        checkout_response = session.post(f"{BASE_URL}/api/subscription/checkout", json={
            "origin_url": "https://sports-card-bot.preview.emergentagent.com/vault"
        })
        assert checkout_response.status_code == 200, f"Checkout failed: {checkout_response.text}"
        
        data = checkout_response.json()
        assert "url" in data, "Response missing 'url'"
        assert "session_id" in data, "Response missing 'session_id'"
        assert data["session_id"].startswith("cs_test_"), f"Session ID should start with 'cs_test_', got: {data['session_id']}"
        print(f"✓ /api/subscription/checkout returns Stripe URL: {data['session_id'][:30]}...")

    def test_subscription_status_requires_auth(self):
        """GET /api/subscription/status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/subscription/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/subscription/status requires auth (401)")

    def test_subscription_status_returns_tier_info(self):
        """GET /api/subscription/status returns tier and trial info"""
        session = requests.Session()
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        
        status_response = session.get(f"{BASE_URL}/api/subscription/status")
        assert status_response.status_code == 200, f"Status failed: {status_response.text}"
        
        data = status_response.json()
        assert "tier" in data, "Response missing 'tier'"
        assert "trial_days_left" in data, "Response missing 'trial_days_left'"
        assert "subscription_status" in data, "Response missing 'subscription_status'"
        print(f"✓ /api/subscription/status returns tier={data['tier']}, trial_days_left={data['trial_days_left']}")

    def test_subscription_cancel_requires_auth(self):
        """POST /api/subscription/cancel requires authentication"""
        response = requests.post(f"{BASE_URL}/api/subscription/cancel")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/subscription/cancel requires auth (401)")

    def test_subscription_admin_info_requires_admin(self):
        """GET /api/subscription/admin/info requires admin role"""
        # Anonymous
        response = requests.get(f"{BASE_URL}/api/subscription/admin/info")
        assert response.status_code == 401, f"Expected 401 for anonymous, got {response.status_code}"
        
        # Non-admin user
        unique_id = uuid.uuid4().hex[:8]
        test_email = f"TEST_nonadmin_{unique_id}@test.com"
        reg_response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "TestPass123!",
            "name": "Non Admin"
        })
        assert reg_response.status_code == 200
        token = reg_response.json()["token"]
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/subscription/admin/info", headers=headers)
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}"
        
        # Admin
        session = requests.Session()
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        
        admin_response = session.get(f"{BASE_URL}/api/subscription/admin/info")
        assert admin_response.status_code == 200, f"Admin info failed: {admin_response.text}"
        
        data = admin_response.json()
        assert "price_id" in data, "Response missing 'price_id'"
        assert "amount" in data, "Response missing 'amount'"
        print(f"✓ /api/subscription/admin/info: admin-only, returns price_id={data.get('price_id', 'N/A')[:20]}...")

    def test_subscription_webhook_mode_requires_admin(self):
        """GET /api/subscription/webhook-mode requires admin role"""
        # Anonymous
        response = requests.get(f"{BASE_URL}/api/subscription/webhook-mode")
        assert response.status_code == 401, f"Expected 401 for anonymous, got {response.status_code}"
        
        # Admin
        session = requests.Session()
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        
        mode_response = session.get(f"{BASE_URL}/api/subscription/webhook-mode")
        assert mode_response.status_code == 200, f"Webhook mode failed: {mode_response.text}"
        
        data = mode_response.json()
        assert "secret_configured" in data, "Response missing 'secret_configured'"
        assert "strict_mode" in data, "Response missing 'strict_mode'"
        assert data["secret_configured"] == True, "Expected secret_configured=true (whsec_ is set)"
        assert data["strict_mode"] == False, "Expected strict_mode=false (STRIPE_WEBHOOK_STRICT not set)"
        print(f"✓ /api/subscription/webhook-mode: secret_configured={data['secret_configured']}, strict_mode={data['strict_mode']}")


class TestSocialRoutes:
    """Tests for social routes moved to routes/social.py"""

    def test_binders_public_list(self):
        """GET /api/binders/public returns gallery list"""
        response = requests.get(f"{BASE_URL}/api/binders/public")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "binders" in data, "Response missing 'binders'"
        assert "count" in data, "Response missing 'count'"
        assert isinstance(data["binders"], list), "binders should be a list"
        print(f"✓ /api/binders/public returns {data['count']} binders")

    def test_binders_public_single_user(self):
        """GET /api/binders/public/{user_id} returns single user's binder"""
        response = requests.get(f"{BASE_URL}/api/binders/public/{TEST_USER_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user" in data, "Response missing 'user'"
        assert "stats" in data, "Response missing 'stats'"
        assert "pulls" in data, "Response missing 'pulls'"
        
        # Privacy check: pulls should NOT have case_pack_id or pack_type_id
        for pull in data.get("pulls", []):
            assert "case_pack_id" not in pull, f"Privacy violation: case_pack_id found in pull"
            assert "pack_type_id" not in pull, f"Privacy violation: pack_type_id found in pull"
            assert pull.get("source_pack") == "—", f"source_pack should be '—', got: {pull.get('source_pack')}"
        
        print(f"✓ /api/binders/public/{TEST_USER_ID} returns user binder with privacy enforced")

    def test_binders_public_nonexistent_user_404(self):
        """GET /api/binders/public/{user_id} returns 404 for non-existent user"""
        response = requests.get(f"{BASE_URL}/api/binders/public/user_nonexistent_xyz")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ /api/binders/public/{nonexistent} returns 404")

    def test_visibility_toggle_requires_auth(self):
        """PATCH /api/case/packs/{id}/visibility requires authentication"""
        response = requests.patch(
            f"{BASE_URL}/api/case/packs/some_pack_id/visibility",
            json={"is_public": True}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/case/packs/{id}/visibility requires auth (401)")

    def test_thumbs_vote_requires_auth(self):
        """POST /api/case/pulls/{id}/thumbs requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/case/pulls/some_pull_id/thumbs",
            json={"vote": "up"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/case/pulls/{id}/thumbs requires auth (401)")

    def test_thumbs_get_public(self):
        """GET /api/case/pulls/{id}/thumbs is public (returns 404 for invalid pull)"""
        response = requests.get(f"{BASE_URL}/api/case/pulls/nonexistent_pull/thumbs")
        # Should be 404 for non-existent pull, not 401
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ /api/case/pulls/{id}/thumbs GET is public (404 for invalid pull)")


class TestBattleCTAEndpoint:
    """Tests for NEW /api/binders/public/{user_id}/battle-cta endpoint"""

    def test_battle_cta_returns_champion_info(self):
        """GET /api/binders/public/{user_id}/battle-cta returns champion info"""
        response = requests.get(f"{BASE_URL}/api/binders/public/{TEST_USER_ID}/battle-cta")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Required fields
        assert "user_id" in data, "Response missing 'user_id'"
        assert "is_champion" in data, "Response missing 'is_champion'"
        assert "rank" in data, "Response missing 'rank'"
        assert "thumbs_week" in data, "Response missing 'thumbs_week'"
        assert "top_thumbs" in data, "Response missing 'top_thumbs'"
        assert "crown_holder" in data, "Response missing 'crown_holder'"
        
        # Type checks
        assert isinstance(data["is_champion"], bool), "is_champion should be boolean"
        assert isinstance(data["thumbs_week"], int), "thumbs_week should be int"
        assert isinstance(data["top_thumbs"], int), "top_thumbs should be int"
        
        print(f"✓ /api/binders/public/{TEST_USER_ID}/battle-cta: is_champion={data['is_champion']}, rank={data['rank']}, thumbs_week={data['thumbs_week']}")

    def test_battle_cta_nonexistent_user_404(self):
        """GET /api/binders/public/{user_id}/battle-cta returns 404 for non-existent user"""
        response = requests.get(f"{BASE_URL}/api/binders/public/user_nonexistent_xyz/battle-cta")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ /api/binders/public/{nonexistent}/battle-cta returns 404")

    def test_battle_cta_top3_is_champion(self):
        """Top-3 weekly thumbs-up users should have is_champion=true"""
        # Get the leaderboard to find top-3
        leaderboard_response = requests.get(f"{BASE_URL}/api/leaderboard/dub-streak?period=week&limit=10")
        assert leaderboard_response.status_code == 200
        
        entries = leaderboard_response.json().get("entries", [])
        
        # Check battle-cta for each top-3 user
        for entry in entries[:3]:
            if entry.get("thumbs_total", 0) > 0:
                user_id = entry["user_id"]
                cta_response = requests.get(f"{BASE_URL}/api/binders/public/{user_id}/battle-cta")
                if cta_response.status_code == 200:
                    cta_data = cta_response.json()
                    assert cta_data["is_champion"] == True, f"Top-3 user {user_id} should have is_champion=true"
                    print(f"✓ Top-{entry['rank']} user {user_id} has is_champion=true")
        
        # Check a user outside top-10 (if exists)
        if len(entries) > 3:
            outside_user = entries[-1]
            if outside_user.get("rank", 0) > 3:
                cta_response = requests.get(f"{BASE_URL}/api/binders/public/{outside_user['user_id']}/battle-cta")
                if cta_response.status_code == 200:
                    cta_data = cta_response.json()
                    # User outside top-3 should have is_champion=false
                    if cta_data.get("rank") and cta_data["rank"] > 3:
                        assert cta_data["is_champion"] == False, f"User outside top-3 should have is_champion=false"
                        print(f"✓ User outside top-3 has is_champion=false")


class TestStripeWebhookHardening:
    """Tests for Stripe webhook signature verification hardening"""

    def test_webhook_bad_json_returns_400(self):
        """POST /api/webhook/stripe-subscription with bad JSON returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/webhook/stripe-subscription",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert data.get("error") == "bad_json", f"Expected error='bad_json', got: {data}"
        print("✓ Webhook with bad JSON returns 400 bad_json")

    def test_webhook_empty_body_returns_400(self):
        """POST /api/webhook/stripe-subscription with empty body returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/webhook/stripe-subscription",
            data="",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Webhook with empty body returns 400")

    def test_webhook_lenient_mode_accepts_valid_json(self):
        """POST /api/webhook/stripe-subscription in lenient mode accepts valid JSON without signature"""
        # In lenient mode (STRIPE_WEBHOOK_STRICT not set), valid JSON should be accepted
        # even without a valid signature
        test_event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "customer": "cus_test_123",
                    "status": "active",
                    "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/webhook/stripe-subscription",
            json=test_event,
            headers={"Stripe-Signature": "invalid_signature"}
        )
        
        # In lenient mode, should return 200 with received=true, verified=false
        assert response.status_code == 200, f"Expected 200 in lenient mode, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("received") == True, "Expected received=true"
        # verified should be false since signature is invalid
        assert data.get("verified") == False, "Expected verified=false (invalid signature)"
        print("✓ Webhook in lenient mode accepts valid JSON with invalid signature (verified=false)")


class TestExistingEndpointsPostRefactor:
    """Sanity tests to ensure refactor didn't break existing endpoints"""

    def test_auth_login_works(self):
        """POST /api/auth/login still works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        assert "token" in data, "Response missing 'token'"
        assert "user_id" in data, "Response missing 'user_id'"
        print(f"✓ /api/auth/login works, user_id={data['user_id']}")

    def test_auth_me_works(self):
        """GET /api/auth/me still works"""
        session = requests.Session()
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200
        
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, f"Auth me failed: {me_response.text}"
        
        data = me_response.json()
        assert data.get("email") == ADMIN_EMAIL, f"Expected email={ADMIN_EMAIL}, got {data.get('email')}"
        print(f"✓ /api/auth/me works, email={data['email']}")

    def test_predictor_rip_works(self):
        """POST /api/predictor/rip still works"""
        response = requests.post(f"{BASE_URL}/api/predictor/rip", json={
            "pack_id": "prizm-bball-hobby",
            "num_cards": 8
        })
        assert response.status_code == 200, f"Predictor rip failed: {response.text}"
        
        data = response.json()
        assert "cards" in data, "Response missing 'cards'"
        assert len(data["cards"]) == 8, f"Expected 8 cards, got {len(data['cards'])}"
        print(f"✓ /api/predictor/rip works, returned {len(data['cards'])} cards")

    def test_leaderboard_dub_streak_works(self):
        """GET /api/leaderboard/dub-streak still works"""
        response = requests.get(f"{BASE_URL}/api/leaderboard/dub-streak?period=week")
        assert response.status_code == 200, f"Leaderboard failed: {response.text}"
        
        data = response.json()
        assert "entries" in data, "Response missing 'entries'"
        assert "period" in data, "Response missing 'period'"
        print(f"✓ /api/leaderboard/dub-streak works, {len(data['entries'])} entries")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
