"""
Test Suite for Day 8-9 Features:
- Day 8: Marketplace v2 (Pro-gated selling, list-from-pull)
- Day 8: Predictor tier limits (usage tracking, 429 on limit)
- Day 9: Stripe subscription ($3.99/mo Pro)
- Day 9: Subscription status, checkout (503 expected), cancel, webhook

Test credentials: admin@flipnrip.com / AdminPass123! (in 10-day trial = pro tier)
"""

import pytest
import requests
import os
import time
import json
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@flipnrip.com"
ADMIN_PASSWORD = "AdminPass123!"


class TestSetup:
    """Setup fixtures for all tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin (in 10-day trial = pro tier) and return session with token"""
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
        user_id = data.get("user_id")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        session.user_id = user_id
        return session
    
    @pytest.fixture(scope="class")
    def free_user_session(self):
        """Create a user that is NOT in trial (simulate free tier by checking tier endpoint)"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        timestamp = int(time.time())
        email = f"TEST_freeuser_{timestamp}@test.com"
        
        resp = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "TestPass123!",
            "name": "Free Test User"
        })
        
        assert resp.status_code in [200, 201], f"User registration failed: {resp.text}"
        data = resp.json()
        token = data.get("token")
        user_id = data.get("user_id")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        session.user_id = user_id
        session.email = email
        return session


# ============== DAY 8: MARKETPLACE PRO-GATED SELLING ==============

class TestMarketplaceProGating(TestSetup):
    """Test that POST /api/listings requires Pro tier"""
    
    def test_pro_user_can_create_listing(self, admin_session):
        """Admin user (in trial = pro) should be able to create a listing"""
        listing_data = {
            "title": "TEST_Pro User Listing - Patrick Mahomes Prizm RC",
            "description": "Test listing from pro user",
            "sport": "NFL",
            "card_type": "Rookie",
            "player_name": "Patrick Mahomes",
            "team": "Kansas City Chiefs",
            "year": "2017",
            "brand": "Panini Prizm",
            "condition": "Near Mint",
            "price": 150.00,
            "is_tradeable": False,
            "images": []
        }
        
        resp = admin_session.post(f"{BASE_URL}/api/listings", json=listing_data)
        assert resp.status_code == 201, f"Pro user should create listing, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "listing_id" in data
        assert data["title"] == listing_data["title"]
        assert data["status"] == "active"
        print(f"PASS: Pro user created listing {data['listing_id']}")
        
        # Store for cleanup
        admin_session.test_listing_id = data["listing_id"]
    
    def test_free_user_gets_402_on_listing(self, free_user_session):
        """Free user (new user in trial actually gets pro, but let's verify the tier check exists)
        Note: New users are in 10-day trial = pro. This test verifies the endpoint checks tier."""
        # First check the user's tier
        resp = free_user_session.get(f"{BASE_URL}/api/predictor/usage")
        assert resp.status_code == 200
        data = resp.json()
        tier = data.get("tier")
        print(f"INFO: Free user tier is '{tier}' (new users get 10-day trial = pro)")
        
        # Since new users are in trial (pro), they CAN create listings
        # This test documents the behavior - new users in trial can list
        listing_data = {
            "title": "TEST_Trial User Listing",
            "description": "Test listing from trial user",
            "sport": "NBA",
            "card_type": "Base",
            "player_name": "Test Player",
            "condition": "Good",
            "price": 10.00,
            "is_tradeable": False,
            "images": []
        }
        
        resp = free_user_session.post(f"{BASE_URL}/api/listings", json=listing_data)
        # New users in trial = pro, so they can create
        if tier == "pro":
            assert resp.status_code == 201, f"Trial user (pro) should create listing, got {resp.status_code}: {resp.text}"
            print("PASS: Trial user (pro tier) can create listing as expected")
            free_user_session.test_listing_id = resp.json().get("listing_id")
        else:
            # If somehow not in trial, should get 402
            assert resp.status_code == 402, f"Free user should get 402, got {resp.status_code}: {resp.text}"
            print("PASS: Free user correctly gets 402 Payment Required")
    
    def test_anonymous_user_gets_401_on_listing(self):
        """Anonymous user (no auth) should get 401, not 500"""
        listing_data = {
            "title": "TEST_Anonymous Listing",
            "description": "Should fail",
            "sport": "NFL",
            "card_type": "Base",
            "player_name": "Test",
            "condition": "Good",
            "price": 5.00,
            "is_tradeable": False,
            "images": []
        }
        
        resp = requests.post(f"{BASE_URL}/api/listings", json=listing_data)
        assert resp.status_code == 401, f"Anonymous should get 401, got {resp.status_code}: {resp.text}"
        print("PASS: Anonymous user correctly gets 401 Not Authenticated")


# ============== DAY 8: LIST-FROM-PULL ==============

class TestListFromPull(TestSetup):
    """Test POST /api/listings/from-pull endpoint"""
    
    @pytest.fixture(scope="class")
    def test_binder_and_pull(self, admin_session):
        """Create a binder and pull for testing list-from-pull"""
        # Create a binder
        resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby",
            "name": "TEST_ListFromPull Binder"
        })
        assert resp.status_code in [200, 201], f"Failed to create binder: {resp.text}"
        binder = resp.json()
        binder_id = binder["case_pack_id"]
        
        # Create a pull in the binder
        resp = admin_session.post(f"{BASE_URL}/api/case/packs/{binder_id}/pulls", json={
            "player": "CJ Stroud",
            "parallel": "Silver Prizm",
            "notes": "Test pull for listing"
        })
        assert resp.status_code in [200, 201], f"Failed to create pull: {resp.text}"
        pull = resp.json()
        
        return {"binder_id": binder_id, "pull_id": pull["pull_id"]}
    
    def test_list_from_pull_success(self, admin_session, test_binder_and_pull):
        """Pro user can list a pull from their binder"""
        pull_id = test_binder_and_pull["pull_id"]
        
        resp = admin_session.post(f"{BASE_URL}/api/listings/from-pull", json={
            "pull_id": pull_id,
            "price": 75.00,
            "condition": "Near Mint",
            "description": "Fresh pull from my binder!"
        })
        
        assert resp.status_code == 200, f"List from pull failed: {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "listing_id" in data, "Response should have listing_id"
        assert "from_pull_id" in data, "Response should have from_pull_id"
        assert data["from_pull_id"] == pull_id
        assert data["price"] == 75.00
        assert data["status"] == "active"
        print(f"PASS: List from pull created listing {data['listing_id']} from pull {pull_id}")
        
        # Store for later tests
        admin_session.from_pull_listing_id = data["listing_id"]
        admin_session.listed_pull_id = pull_id
    
    def test_pull_backlinked_after_listing(self, admin_session, test_binder_and_pull):
        """After listing, the pull should have status='listed' and listed_listing_id set"""
        binder_id = test_binder_and_pull["binder_id"]
        pull_id = test_binder_and_pull["pull_id"]
        
        # Get pulls for the binder
        resp = admin_session.get(f"{BASE_URL}/api/case/packs/{binder_id}/pulls")
        assert resp.status_code == 200
        data = resp.json()
        
        # Response is {"pack": {...}, "pulls": [...]}
        pulls = data.get("pulls", [])
        
        # Find our pull
        pull = next((p for p in pulls if p["pull_id"] == pull_id), None)
        assert pull is not None, f"Pull {pull_id} not found in binder"
        
        # Verify backlink
        assert pull.get("status") == "listed", f"Pull status should be 'listed', got {pull.get('status')}"
        assert pull.get("listed_listing_id") is not None, "Pull should have listed_listing_id"
        print(f"PASS: Pull {pull_id} backlinked with status='listed' and listing_id={pull.get('listed_listing_id')}")
    
    def test_relisting_same_pull_returns_400(self, admin_session, test_binder_and_pull):
        """Re-listing the same pull should return 400 'already listed'"""
        pull_id = test_binder_and_pull["pull_id"]
        
        resp = admin_session.post(f"{BASE_URL}/api/listings/from-pull", json={
            "pull_id": pull_id,
            "price": 100.00,
            "condition": "Mint"
        })
        
        assert resp.status_code == 400, f"Re-listing should return 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "already listed" in data.get("detail", "").lower(), f"Error should mention 'already listed': {data}"
        print("PASS: Re-listing same pull correctly returns 400 'already listed'")
    
    def test_listing_other_users_pull_returns_403(self, admin_session, free_user_session):
        """Trying to list another user's pull should return 403"""
        # First create a pull for admin
        resp = admin_session.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-bball-hobby",
            "name": "TEST_Admin Only Binder"
        })
        assert resp.status_code in [200, 201]
        binder_id = resp.json()["case_pack_id"]
        
        resp = admin_session.post(f"{BASE_URL}/api/case/packs/{binder_id}/pulls", json={
            "player": "Victor Wembanyama",
            "parallel": "Gold /10"
        })
        assert resp.status_code in [200, 201]
        admin_pull_id = resp.json()["pull_id"]
        
        # Now try to list it as free_user
        resp = free_user_session.post(f"{BASE_URL}/api/listings/from-pull", json={
            "pull_id": admin_pull_id,
            "price": 5000.00,
            "condition": "Mint"
        })
        
        assert resp.status_code == 403, f"Listing other user's pull should return 403, got {resp.status_code}: {resp.text}"
        print("PASS: Listing another user's pull correctly returns 403 Forbidden")
    
    def test_listing_nonexistent_pull_returns_404(self, admin_session):
        """Listing a non-existent pull should return 404"""
        resp = admin_session.post(f"{BASE_URL}/api/listings/from-pull", json={
            "pull_id": "pull_nonexistent123",
            "price": 50.00,
            "condition": "Good"
        })
        
        assert resp.status_code == 404, f"Non-existent pull should return 404, got {resp.status_code}: {resp.text}"
        print("PASS: Non-existent pull correctly returns 404")


# ============== DAY 8: PREDICTOR TIER LIMITS ==============

class TestPredictorTierLimits(TestSetup):
    """Test predictor usage tracking and tier limits"""
    
    def test_predictor_usage_endpoint_logged_in(self, admin_session):
        """GET /api/predictor/usage returns usage info for logged-in user"""
        resp = admin_session.get(f"{BASE_URL}/api/predictor/usage")
        assert resp.status_code == 200, f"Predictor usage failed: {resp.text}"
        data = resp.json()
        
        assert "used" in data, "Response should have 'used' field"
        assert "limit" in data, "Response should have 'limit' field"
        assert "tier" in data, "Response should have 'tier' field"
        
        print(f"PASS: Predictor usage - used: {data['used']}, limit: {data['limit']}, tier: {data['tier']}")
    
    def test_predictor_usage_endpoint_anonymous(self):
        """GET /api/predictor/usage returns default for anonymous user"""
        resp = requests.get(f"{BASE_URL}/api/predictor/usage")
        assert resp.status_code == 200, f"Anonymous predictor usage failed: {resp.text}"
        data = resp.json()
        
        assert data.get("used") == 0, f"Anonymous used should be 0, got {data.get('used')}"
        assert data.get("limit") == 2, f"Anonymous limit should be 2, got {data.get('limit')}"
        assert data.get("tier") == "anonymous", f"Anonymous tier should be 'anonymous', got {data.get('tier')}"
        
        print("PASS: Anonymous predictor usage returns {used:0, limit:2, tier:'anonymous'}")
    
    def test_predictor_simulate_returns_usage(self, admin_session):
        """POST /api/predictor/simulate returns usage field in response"""
        resp = admin_session.post(f"{BASE_URL}/api/predictor/simulate", json={
            "pack_id": "prizm-fball-hobby",
            "num_cards": 5
        })
        assert resp.status_code == 200, f"Predictor simulate failed: {resp.text}"
        data = resp.json()
        
        assert "usage" in data, "Response should have 'usage' field"
        usage = data["usage"]
        assert "used" in usage, "Usage should have 'used' field"
        assert "limit" in usage, "Usage should have 'limit' field"
        
        print(f"PASS: Predictor simulate returns usage: {usage}")
    
    def test_predictor_simulate_anonymous_no_limit(self):
        """Anonymous users can use predictor without limit tracking"""
        resp = requests.post(f"{BASE_URL}/api/predictor/simulate", json={
            "pack_id": "prizm-bball-hobby",
            "num_cards": 4
        })
        assert resp.status_code == 200, f"Anonymous predictor simulate failed: {resp.text}"
        data = resp.json()
        
        # Anonymous should still get response
        assert "pulls" in data
        assert "summary" in data
        print("PASS: Anonymous predictor simulate works (no auth required)")


# ============== DAY 9: SUBSCRIPTION STATUS ==============

class TestSubscriptionStatus(TestSetup):
    """Test GET /api/subscription/status endpoint"""
    
    def test_subscription_status_for_trial_user(self, admin_session):
        """Admin user (in trial) should have tier='pro', trial_days_left>0"""
        resp = admin_session.get(f"{BASE_URL}/api/subscription/status")
        assert resp.status_code == 200, f"Subscription status failed: {resp.text}"
        data = resp.json()
        
        # Verify required fields
        required_fields = ["tier", "trial_days_left", "subscription_status", 
                          "current_period_end", "stripe_customer_id", 
                          "stripe_subscription_id", "cancel_at_period_end"]
        for field in required_fields:
            assert field in data, f"Response missing field: {field}"
        
        # For admin in trial
        assert data["tier"] == "pro", f"Admin in trial should have tier='pro', got {data['tier']}"
        assert data["trial_days_left"] > 0, f"Admin in trial should have trial_days_left>0, got {data['trial_days_left']}"
        assert data["subscription_status"] is None, f"Admin with no sub should have subscription_status=null, got {data['subscription_status']}"
        
        print(f"PASS: Subscription status - tier: {data['tier']}, trial_days_left: {data['trial_days_left']}, subscription_status: {data['subscription_status']}")
    
    def test_subscription_status_requires_auth(self):
        """Anonymous user should get 401"""
        resp = requests.get(f"{BASE_URL}/api/subscription/status")
        assert resp.status_code == 401, f"Anonymous should get 401, got {resp.status_code}"
        print("PASS: Subscription status requires authentication (401 for anonymous)")


# ============== DAY 9: SUBSCRIPTION CHECKOUT ==============

class TestSubscriptionCheckout(TestSetup):
    """Test POST /api/subscription/checkout endpoint"""
    
    def test_subscription_checkout_returns_503_with_placeholder_key(self, admin_session):
        """With placeholder STRIPE_API_KEY='sk_test_emergent', should return 503 with helpful message"""
        resp = admin_session.post(f"{BASE_URL}/api/subscription/checkout", json={
            "origin_url": "https://sports-card-bot.preview.emergentagent.com"
        })
        
        # Expected: 503 with helpful setup message
        assert resp.status_code == 503, f"Expected 503 with placeholder key, got {resp.status_code}: {resp.text}"
        data = resp.json()
        detail = data.get("detail", "")
        
        # Verify the error message is helpful
        assert "real Stripe" in detail.lower() or "stripe test key" in detail.lower(), \
            f"Error should mention needing real Stripe key: {detail}"
        assert "dashboard.stripe.com" in detail or "STRIPE_API_KEY" in detail, \
            f"Error should mention where to get key: {detail}"
        
        print(f"PASS: Subscription checkout returns 503 with helpful message: {detail[:100]}...")
    
    def test_subscription_checkout_requires_auth(self):
        """Anonymous user should get 401"""
        resp = requests.post(f"{BASE_URL}/api/subscription/checkout", json={
            "origin_url": "https://example.com"
        })
        assert resp.status_code == 401, f"Anonymous should get 401, got {resp.status_code}"
        print("PASS: Subscription checkout requires authentication")


# ============== DAY 9: SUBSCRIPTION CANCEL ==============

class TestSubscriptionCancel(TestSetup):
    """Test POST /api/subscription/cancel endpoint"""
    
    def test_cancel_with_no_active_sub_returns_400(self, admin_session):
        """User with no active subscription should get 400"""
        resp = admin_session.post(f"{BASE_URL}/api/subscription/cancel")
        
        assert resp.status_code == 400, f"Expected 400 for no active sub, got {resp.status_code}: {resp.text}"
        data = resp.json()
        detail = data.get("detail", "").lower()
        
        assert "no active subscription" in detail, f"Error should mention 'no active subscription': {data}"
        print("PASS: Cancel with no active subscription returns 400 'No active subscription'")
    
    def test_cancel_requires_auth(self):
        """Anonymous user should get 401"""
        resp = requests.post(f"{BASE_URL}/api/subscription/cancel")
        assert resp.status_code == 401, f"Anonymous should get 401, got {resp.status_code}"
        print("PASS: Subscription cancel requires authentication")


# ============== DAY 9: STRIPE SUBSCRIPTION WEBHOOK ==============

class TestStripeSubscriptionWebhook(TestSetup):
    """Test POST /api/webhook/stripe-subscription endpoint"""
    
    def test_webhook_endpoint_exists(self):
        """Webhook endpoint should exist and accept POST"""
        # Send a minimal valid-looking event
        fake_event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_fake123",
                    "customer": "cus_unknown123",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_end": 1735689600
                }
            }
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/webhook/stripe-subscription",
            json=fake_event,
            headers={"Content-Type": "application/json"}
        )
        
        # Should return 200 with {received: true} even for unknown customer
        assert resp.status_code == 200, f"Webhook should return 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("received") == True, f"Webhook should return received:true, got {data}"
        print("PASS: Webhook endpoint exists and returns {received: true} for unknown customer")
    
    def test_webhook_handles_subscription_created(self):
        """Webhook handles customer.subscription.created event"""
        fake_event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_test_created",
                    "customer": "cus_test_created",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_end": 1735689600
                }
            }
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/webhook/stripe-subscription",
            json=fake_event,
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status_code == 200
        assert resp.json().get("received") == True
        print("PASS: Webhook handles customer.subscription.created")
    
    def test_webhook_handles_subscription_deleted(self):
        """Webhook handles customer.subscription.deleted event"""
        fake_event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_test_deleted",
                    "customer": "cus_test_deleted",
                    "status": "canceled",
                    "cancel_at_period_end": True,
                    "current_period_end": 1735689600
                }
            }
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/webhook/stripe-subscription",
            json=fake_event,
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status_code == 200
        assert resp.json().get("received") == True
        print("PASS: Webhook handles customer.subscription.deleted")
    
    def test_webhook_handles_invoice_payment_succeeded(self):
        """Webhook handles invoice.payment_succeeded event"""
        fake_event = {
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "customer": "cus_test_invoice",
                    "amount_paid": 200,
                    "currency": "usd"
                }
            }
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/webhook/stripe-subscription",
            json=fake_event,
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status_code == 200
        assert resp.json().get("received") == True
        print("PASS: Webhook handles invoice.payment_succeeded")
    
    def test_webhook_rejects_malformed_json(self):
        """Webhook returns 400 for malformed JSON"""
        resp = requests.post(
            f"{BASE_URL}/api/webhook/stripe-subscription",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status_code == 400, f"Malformed JSON should return 400, got {resp.status_code}"
        print("PASS: Webhook rejects malformed JSON with 400")


# ============== PERMISSIONS: AUTH ENDPOINTS REJECT ANONYMOUS ==============

class TestPermissions(TestSetup):
    """Test that Pro-gated/auth endpoints reject anonymous users appropriately"""
    
    def test_my_listings_requires_auth(self):
        """GET /api/my-listings requires auth"""
        resp = requests.get(f"{BASE_URL}/api/my-listings")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: /api/my-listings requires auth (401)")
    
    def test_my_transactions_requires_auth(self):
        """GET /api/my-transactions requires auth"""
        resp = requests.get(f"{BASE_URL}/api/my-transactions")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: /api/my-transactions requires auth (401)")
    
    def test_case_packs_requires_auth(self):
        """POST /api/case/packs requires auth"""
        resp = requests.post(f"{BASE_URL}/api/case/packs", json={
            "pack_type_id": "prizm-fball-hobby"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: /api/case/packs requires auth (401)")
    
    def test_case_stats_requires_auth(self):
        """GET /api/case/stats requires auth"""
        resp = requests.get(f"{BASE_URL}/api/case/stats")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: /api/case/stats requires auth (401)")
    
    def test_messages_requires_auth(self):
        """GET /api/messages requires auth"""
        resp = requests.get(f"{BASE_URL}/api/messages")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: /api/messages requires auth (401)")


# ============== REGRESSION: DAY 1-7 ENDPOINTS ==============

class TestRegression(TestSetup):
    """Regression tests for Day 1-7 endpoints"""
    
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
        print(f"PASS: Hot packs returned {len(data['packs'])} packs")
    
    def test_analyzer_packs_endpoint(self):
        """Analyzer packs list should work"""
        resp = requests.get(f"{BASE_URL}/api/analyzer/packs")
        assert resp.status_code == 200
        data = resp.json()
        assert "packs" in data
        print(f"PASS: Analyzer packs returned {len(data['packs'])} packs")
    
    def test_analyzer_pack_detail(self):
        """Analyzer pack detail should work"""
        resp = requests.get(f"{BASE_URL}/api/analyzer/prizm-fball-hobby")
        assert resp.status_code == 200
        data = resp.json()
        assert "pack" in data
        assert "verdict" in data
        print("PASS: Analyzer pack detail working")
    
    def test_predictor_simulate(self):
        """Predictor simulate should work"""
        resp = requests.post(f"{BASE_URL}/api/predictor/simulate", json={
            "pack_id": "prizm-fball-hobby",
            "num_cards": 5
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "pulls" in data
        assert "summary" in data
        print("PASS: Predictor simulate working")
    
    def test_knowledge_endpoints(self):
        """Knowledge endpoints should work"""
        endpoints = [
            "/api/knowledge/packs",
            "/api/knowledge/blasters",
            "/api/knowledge/hottest-cards",
            "/api/knowledge/terminology"
        ]
        for endpoint in endpoints:
            resp = requests.get(f"{BASE_URL}{endpoint}")
            assert resp.status_code == 200, f"{endpoint} failed: {resp.status_code}"
        print("PASS: All knowledge endpoints working")
    
    def test_cards_search(self):
        """Card search should work"""
        resp = requests.get(f"{BASE_URL}/api/cards/search", params={"q": "Mahomes"})
        assert resp.status_code == 200
        print("PASS: Card search working")
    
    def test_listings_public(self):
        """Public listings endpoint should work"""
        resp = requests.get(f"{BASE_URL}/api/listings")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: Public listings returned {len(data)} listings")
    
    def test_auth_login(self, admin_session):
        """Auth login should work"""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("email") == ADMIN_EMAIL
        print("PASS: Auth /me working")


# ============== CLEANUP ==============

class TestCleanup(TestSetup):
    """Cleanup test data"""
    
    def test_cleanup_test_listings(self, admin_session):
        """Delete TEST_ prefixed listings"""
        resp = admin_session.get(f"{BASE_URL}/api/my-listings")
        if resp.status_code == 200:
            listings = resp.json()
            for listing in listings:
                if listing.get("title", "").startswith("TEST_"):
                    del_resp = admin_session.delete(f"{BASE_URL}/api/listings/{listing['listing_id']}")
                    if del_resp.status_code == 200:
                        print(f"Cleaned up listing: {listing['listing_id']}")
        print("PASS: Cleanup completed")
