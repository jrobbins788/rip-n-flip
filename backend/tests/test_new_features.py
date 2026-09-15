"""
Backend tests for Card Fanatic Hub - New Features (Iteration 2)
Tests: eBay price scraping, Cash App trades, Fanatic Bot (Ollama), and regression tests
"""
import pytest
import requests
import os
import time
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test user credentials - will be created during tests
TEST_BUYER_EMAIL = f"test_buyer_{int(time.time())}@test.com"
TEST_BUYER_PASSWORD = "TestPass123!"
TEST_BUYER_NAME = "Test Buyer"

TEST_SELLER_EMAIL = f"test_seller_{int(time.time())}@test.com"
TEST_SELLER_PASSWORD = "TestPass456!"
TEST_SELLER_NAME = "Test Seller"
TEST_SELLER_CASH_APP_TAG = "$TestSellerCashApp"


class TestHealthAndRegression:
    """Basic health checks and regression tests for existing endpoints"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ Health check passed: {data}")
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "Card Fanatic Hub" in data.get("message", "")
        print(f"✓ API root passed: {data}")
    
    def test_knowledge_packs(self):
        """Regression: Knowledge packs endpoint"""
        response = requests.get(f"{BASE_URL}/api/knowledge/packs")
        assert response.status_code == 200
        data = response.json()
        assert "NFL" in data or "NBA" in data
        print(f"✓ Knowledge packs endpoint working")
    
    def test_knowledge_blasters(self):
        """Regression: Knowledge blasters endpoint"""
        response = requests.get(f"{BASE_URL}/api/knowledge/blasters")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Knowledge blasters endpoint working")
    
    def test_knowledge_terminology(self):
        """Regression: Knowledge terminology endpoint"""
        response = requests.get(f"{BASE_URL}/api/knowledge/terminology")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Knowledge terminology endpoint working")
    
    def test_listings_get(self):
        """Regression: Get listings endpoint"""
        response = requests.get(f"{BASE_URL}/api/listings")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Listings GET endpoint working, found {len(data)} listings")


class TestFanaticBot:
    """Tests for Fanatic Bot (Ollama) endpoints - expect 503 when OLLAMA_BASE_URL unset"""
    
    def test_chat_health_ollama_offline(self):
        """GET /api/chat/health - should return ok:false when OLLAMA_BASE_URL unset"""
        response = requests.get(f"{BASE_URL}/api/chat/health")
        assert response.status_code == 200
        data = response.json()
        
        # Verify JSON shape
        assert "ok" in data
        assert "model" in data
        assert "base_url" in data
        
        # When OLLAMA_BASE_URL is empty, ok should be false
        assert data["ok"] == False, f"Expected ok=false when Ollama offline, got {data}"
        assert data["model"] == "huihui_ai/qwen2.5-abliterate:7b"
        assert data["base_url"] is None or data["base_url"] == ""
        assert "reason" in data
        print(f"✓ Chat health correctly reports Ollama offline: {data}")
    
    def test_chat_send_ollama_offline(self):
        """POST /api/chat/send - should return 503 when OLLAMA_BASE_URL unset"""
        response = requests.post(
            f"{BASE_URL}/api/chat/send",
            json={"message": "What's the best pack to buy?"}
        )
        assert response.status_code == 503, f"Expected 503, got {response.status_code}"
        data = response.json()
        assert "Fanatic Bot is offline" in data.get("detail", "")
        print(f"✓ Chat send correctly returns 503 when Ollama offline")
    
    def test_chat_stream_ollama_offline(self):
        """POST /api/chat/stream - should return 503 when OLLAMA_BASE_URL unset"""
        response = requests.post(
            f"{BASE_URL}/api/chat/stream",
            json={"message": "Tell me about Prizm cards"}
        )
        assert response.status_code == 503, f"Expected 503, got {response.status_code}"
        print(f"✓ Chat stream correctly returns 503 when Ollama offline")
    
    def test_chat_history_empty_session(self):
        """GET /api/chat/history/{session_id} - empty session returns empty messages"""
        session_id = f"test_session_{int(time.time())}"
        response = requests.get(f"{BASE_URL}/api/chat/history/{session_id}")
        assert response.status_code == 200
        data = response.json()
        
        assert "session_id" in data
        assert "messages" in data
        assert data["session_id"] == session_id
        assert data["messages"] == []
        print(f"✓ Chat history returns empty for non-existent session")
    
    def test_chat_history_clear(self):
        """DELETE /api/chat/history/{session_id} - returns cleared:true"""
        session_id = f"test_clear_session_{int(time.time())}"
        response = requests.delete(f"{BASE_URL}/api/chat/history/{session_id}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("cleared") == True
        print(f"✓ Chat history clear returns cleared:true")


class TestPriceScraping:
    """Tests for eBay price scraping - expect blocked:true from preview pod IP"""
    
    def test_price_scrape_json_shape(self):
        """GET /api/packs/price?q=<query> - verify JSON shape (expect blocked:true)"""
        response = requests.get(f"{BASE_URL}/api/packs/price", params={"q": "Prizm Football"})
        assert response.status_code == 200
        data = response.json()
        
        # Verify required JSON fields
        required_fields = ["query", "sold_only", "count", "avg", "min", "max", "median", "listings", "blocked"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify types
        assert isinstance(data["query"], str)
        assert isinstance(data["sold_only"], bool)
        assert isinstance(data["count"], int)
        assert isinstance(data["listings"], list)
        assert isinstance(data["blocked"], bool)
        
        # From preview pod, expect blocked:true
        if data["blocked"]:
            assert "reason" in data
            print(f"✓ Price scrape returns blocked:true (expected from preview pod): {data.get('reason', '')[:100]}")
        else:
            print(f"✓ Price scrape returned {data['count']} listings")
        
        # Verify fetched_at and cached fields
        assert "fetched_at" in data
        assert "cached" in data
        print(f"✓ Price scrape JSON shape is correct")
    
    def test_price_scrape_cache_behavior(self):
        """Verify cache behavior: first call sets cache, second returns cached:true"""
        query = f"test_cache_query_{int(time.time())}"
        
        # First call - should not be cached
        response1 = requests.get(f"{BASE_URL}/api/packs/price", params={"q": query})
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1.get("cached") == False, "First call should not be cached"
        print(f"✓ First call cached=false")
        
        # Second call - should be cached
        response2 = requests.get(f"{BASE_URL}/api/packs/price", params={"q": query})
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2.get("cached") == True, "Second call should be cached"
        print(f"✓ Second call cached=true")
    
    def test_price_scrape_refresh_bypass_cache(self):
        """Verify ?refresh=true bypasses cache"""
        query = f"test_refresh_query_{int(time.time())}"
        
        # First call to populate cache
        response1 = requests.get(f"{BASE_URL}/api/packs/price", params={"q": query})
        assert response1.status_code == 200
        
        # Call with refresh=true - should bypass cache
        response2 = requests.get(f"{BASE_URL}/api/packs/price", params={"q": query, "refresh": "true"})
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2.get("cached") == False, "refresh=true should bypass cache"
        print(f"✓ refresh=true bypasses cache correctly")
    
    def test_batch_prices(self):
        """POST /api/packs/prices/batch - batch fetch prices"""
        response = requests.post(
            f"{BASE_URL}/api/packs/prices/batch",
            json={"queries": ["Prizm Football", "Select Basketball"]}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "results" in data
        assert isinstance(data["results"], dict)
        assert "Prizm Football" in data["results"]
        assert "Select Basketball" in data["results"]
        print(f"✓ Batch prices endpoint working, returned {len(data['results'])} results")
    
    def test_price_scrape_empty_query(self):
        """GET /api/packs/price with empty query should return 400"""
        response = requests.get(f"{BASE_URL}/api/packs/price", params={"q": ""})
        assert response.status_code == 400
        print(f"✓ Empty query correctly returns 400")


class TestCashAppTrades:
    """Tests for Cash App trade lifecycle"""
    
    @pytest.fixture(scope="class")
    def buyer_session(self):
        """Create and authenticate buyer user"""
        session = requests.Session()
        
        # Register buyer
        response = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": TEST_BUYER_EMAIL,
            "password": TEST_BUYER_PASSWORD,
            "name": TEST_BUYER_NAME
        })
        
        if response.status_code == 400 and "already registered" in response.text:
            # Login instead
            response = session.post(f"{BASE_URL}/api/auth/login", json={
                "email": TEST_BUYER_EMAIL,
                "password": TEST_BUYER_PASSWORD
            })
        
        assert response.status_code in [200, 201], f"Buyer auth failed: {response.text}"
        data = response.json()
        token = data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        print(f"✓ Buyer authenticated: {data.get('user_id')}")
        return session, data
    
    @pytest.fixture(scope="class")
    def seller_session(self):
        """Create and authenticate seller user with cash_app_tag"""
        session = requests.Session()
        
        # Register seller
        response = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": TEST_SELLER_EMAIL,
            "password": TEST_SELLER_PASSWORD,
            "name": TEST_SELLER_NAME
        })
        
        if response.status_code == 400 and "already registered" in response.text:
            # Login instead
            response = session.post(f"{BASE_URL}/api/auth/login", json={
                "email": TEST_SELLER_EMAIL,
                "password": TEST_SELLER_PASSWORD
            })
        
        assert response.status_code in [200, 201], f"Seller auth failed: {response.text}"
        data = response.json()
        token = data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Set cash_app_tag for seller
        profile_response = session.put(f"{BASE_URL}/api/auth/profile", json={
            "cash_app_tag": TEST_SELLER_CASH_APP_TAG
        })
        assert profile_response.status_code == 200
        print(f"✓ Seller authenticated with cash_app_tag: {data.get('user_id')}")
        return session, data
    
    @pytest.fixture(scope="class")
    def test_listing(self, seller_session):
        """Create a test listing by seller"""
        session, seller_data = seller_session
        
        response = session.post(f"{BASE_URL}/api/listings", json={
            "title": "TEST_Trade_Card_Prizm_RC",
            "description": "Test card for trade testing",
            "sport": "NFL",
            "card_type": "Rookie",
            "player_name": "Test Player",
            "team": "Test Team",
            "year": "2024",
            "brand": "Panini Prizm",
            "condition": "Mint",
            "price": 100.00,
            "is_tradeable": True,
            "images": []
        })
        assert response.status_code == 201, f"Listing creation failed: {response.text}"
        listing = response.json()
        print(f"✓ Test listing created: {listing['listing_id']}")
        return listing
    
    def test_listing_includes_seller_cash_app_tag(self, test_listing):
        """GET /api/listings/{id} should include seller_cash_app_tag"""
        response = requests.get(f"{BASE_URL}/api/listings/{test_listing['listing_id']}")
        assert response.status_code == 200
        data = response.json()
        
        assert "seller_cash_app_tag" in data, "Missing seller_cash_app_tag field"
        # Cash app tag is stored as-is (with $ prefix if provided)
        assert data["seller_cash_app_tag"] == TEST_SELLER_CASH_APP_TAG or data["seller_cash_app_tag"] == TEST_SELLER_CASH_APP_TAG.lstrip("$")
        print(f"✓ Listing includes seller_cash_app_tag: {data['seller_cash_app_tag']}")
    
    def test_trade_initiate_success(self, buyer_session, test_listing):
        """POST /api/trades/initiate - buyer initiates trade"""
        session, buyer_data = buyer_session
        
        response = session.post(f"{BASE_URL}/api/trades/initiate", json={
            "listing_id": test_listing["listing_id"]
        })
        assert response.status_code == 200, f"Trade initiate failed: {response.text}"
        trade = response.json()
        
        # Verify trade structure
        assert "trade_id" in trade
        assert "cashapp_url" in trade
        assert "total_amount" in trade
        assert "status" in trade
        assert trade["status"] == "awaiting_payment"
        
        # Verify Cash App URL format
        assert trade["cashapp_url"].startswith("https://cash.app/$")
        
        # Verify platform fee (5%)
        base_price = test_listing["price"]
        expected_fee = round(base_price * 0.05, 2)
        expected_total = round(base_price + expected_fee, 2)
        assert trade["total_amount"] == expected_total, f"Expected total {expected_total}, got {trade['total_amount']}"
        assert trade["platform_fee"] == expected_fee
        
        print(f"✓ Trade initiated: {trade['trade_id']}, total: ${trade['total_amount']}, cashapp_url: {trade['cashapp_url']}")
        
        # Store trade_id for subsequent tests
        self.__class__.trade_id = trade["trade_id"]
        return trade
    
    def test_listing_status_pending_after_trade(self, test_listing):
        """Verify listing status changes to 'pending' after trade initiation"""
        response = requests.get(f"{BASE_URL}/api/listings/{test_listing['listing_id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending", f"Expected status 'pending', got {data['status']}"
        print(f"✓ Listing status is 'pending' after trade initiation")
    
    def test_trade_mark_paid(self, buyer_session):
        """POST /api/trades/{trade_id}/mark-paid - buyer marks paid"""
        session, _ = buyer_session
        trade_id = self.__class__.trade_id
        
        response = session.post(f"{BASE_URL}/api/trades/{trade_id}/mark-paid")
        assert response.status_code == 200, f"Mark paid failed: {response.text}"
        data = response.json()
        assert data["status"] == "paid"
        print(f"✓ Trade marked as paid: {trade_id}")
    
    def test_trade_confirm(self, seller_session):
        """POST /api/trades/{trade_id}/confirm - seller confirms receipt"""
        session, _ = seller_session
        trade_id = self.__class__.trade_id
        
        response = session.post(f"{BASE_URL}/api/trades/{trade_id}/confirm")
        assert response.status_code == 200, f"Confirm failed: {response.text}"
        data = response.json()
        assert data["status"] == "completed"
        print(f"✓ Trade confirmed/completed: {trade_id}")
    
    def test_listing_status_sold_after_confirm(self, test_listing):
        """Verify listing status changes to 'sold' after trade confirmation"""
        response = requests.get(f"{BASE_URL}/api/listings/{test_listing['listing_id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sold", f"Expected status 'sold', got {data['status']}"
        print(f"✓ Listing status is 'sold' after trade completion")
    
    def test_get_trades_as_buyer(self, buyer_session):
        """GET /api/trades - buyer can see their trades"""
        session, _ = buyer_session
        response = session.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        trades = response.json()
        assert isinstance(trades, list)
        assert len(trades) > 0
        print(f"✓ Buyer can see {len(trades)} trades")
    
    def test_get_trades_as_seller(self, seller_session):
        """GET /api/trades - seller can see their trades"""
        session, _ = seller_session
        response = session.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        trades = response.json()
        assert isinstance(trades, list)
        assert len(trades) > 0
        print(f"✓ Seller can see {len(trades)} trades")


class TestCashAppTradeErrors:
    """Error case tests for Cash App trades"""
    
    @pytest.fixture(scope="class")
    def user_no_cash_tag(self):
        """Create user without cash_app_tag"""
        session = requests.Session()
        email = f"test_no_tag_{int(time.time())}@test.com"
        
        response = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "TestPass789!",
            "name": "No Tag User"
        })
        assert response.status_code in [200, 201]
        data = response.json()
        token = data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, data
    
    @pytest.fixture(scope="class")
    def listing_no_cash_tag(self, user_no_cash_tag):
        """Create listing by user without cash_app_tag"""
        session, _ = user_no_cash_tag
        
        response = session.post(f"{BASE_URL}/api/listings", json={
            "title": "TEST_No_Tag_Listing",
            "description": "Listing by user without cash app tag",
            "sport": "NBA",
            "card_type": "Base",
            "player_name": "Test Player",
            "condition": "Good",
            "price": 50.00,
            "is_tradeable": True,
            "images": []
        })
        assert response.status_code == 201
        return response.json()
    
    def test_trade_initiate_seller_no_cash_tag(self, listing_no_cash_tag):
        """Initiate trade when seller has no cash_app_tag should return 400"""
        # Create a different buyer
        buyer_session = requests.Session()
        buyer_email = f"test_buyer_err_{int(time.time())}@test.com"
        
        response = buyer_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": buyer_email,
            "password": "TestPass000!",
            "name": "Error Test Buyer"
        })
        assert response.status_code in [200, 201]
        token = response.json().get("token")
        buyer_session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Try to initiate trade
        response = buyer_session.post(f"{BASE_URL}/api/trades/initiate", json={
            "listing_id": listing_no_cash_tag["listing_id"]
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "Cash App tag" in response.json().get("detail", "")
        print(f"✓ Trade initiate correctly returns 400 when seller has no cash_app_tag")
    
    def test_trade_initiate_own_listing(self, user_no_cash_tag, listing_no_cash_tag):
        """Initiate trade on own listing should return 400"""
        session, _ = user_no_cash_tag
        
        response = session.post(f"{BASE_URL}/api/trades/initiate", json={
            "listing_id": listing_no_cash_tag["listing_id"]
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "yourself" in response.json().get("detail", "").lower()
        print(f"✓ Trade initiate correctly returns 400 for own listing")
    
    def test_trade_get_unauthorized(self):
        """GET /api/trades/{trade_id} - non-party user should get 403"""
        # Create a third user
        session = requests.Session()
        email = f"test_third_{int(time.time())}@test.com"
        
        response = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "TestPass111!",
            "name": "Third User"
        })
        assert response.status_code in [200, 201]
        token = response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Try to access a trade they're not part of (use a fake trade_id)
        response = session.get(f"{BASE_URL}/api/trades/trade_nonexistent123")
        # Should be 404 (not found) or 403 (not authorized)
        assert response.status_code in [403, 404]
        print(f"✓ Non-party user correctly denied access to trade")


class TestTradeCancelFlow:
    """Test trade cancellation flow"""
    
    @pytest.fixture(scope="class")
    def cancel_test_setup(self):
        """Setup buyer, seller, listing, and trade for cancel test"""
        # Create seller with cash_app_tag
        seller_session = requests.Session()
        seller_email = f"test_cancel_seller_{int(time.time())}@test.com"
        
        response = seller_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": seller_email,
            "password": "TestPass222!",
            "name": "Cancel Test Seller"
        })
        assert response.status_code in [200, 201]
        seller_token = response.json().get("token")
        seller_session.headers.update({"Authorization": f"Bearer {seller_token}"})
        
        # Set cash_app_tag
        seller_session.put(f"{BASE_URL}/api/auth/profile", json={
            "cash_app_tag": "$CancelTestSeller"
        })
        
        # Create listing
        listing_response = seller_session.post(f"{BASE_URL}/api/listings", json={
            "title": "TEST_Cancel_Flow_Card",
            "description": "Card for cancel flow test",
            "sport": "MLB",
            "card_type": "Auto",
            "player_name": "Cancel Test Player",
            "condition": "Near Mint",
            "price": 75.00,
            "is_tradeable": True,
            "images": []
        })
        assert listing_response.status_code == 201
        listing = listing_response.json()
        
        # Create buyer
        buyer_session = requests.Session()
        buyer_email = f"test_cancel_buyer_{int(time.time())}@test.com"
        
        response = buyer_session.post(f"{BASE_URL}/api/auth/register", json={
            "email": buyer_email,
            "password": "TestPass333!",
            "name": "Cancel Test Buyer"
        })
        assert response.status_code in [200, 201]
        buyer_token = response.json().get("token")
        buyer_session.headers.update({"Authorization": f"Bearer {buyer_token}"})
        
        # Initiate trade
        trade_response = buyer_session.post(f"{BASE_URL}/api/trades/initiate", json={
            "listing_id": listing["listing_id"]
        })
        assert trade_response.status_code == 200
        trade = trade_response.json()
        
        return {
            "buyer_session": buyer_session,
            "seller_session": seller_session,
            "listing": listing,
            "trade": trade
        }
    
    def test_trade_cancel(self, cancel_test_setup):
        """POST /api/trades/{trade_id}/cancel - cancel trade and revert listing"""
        setup = cancel_test_setup
        buyer_session = setup["buyer_session"]
        trade = setup["trade"]
        listing = setup["listing"]
        
        # Cancel the trade
        response = buyer_session.post(f"{BASE_URL}/api/trades/{trade['trade_id']}/cancel")
        assert response.status_code == 200, f"Cancel failed: {response.text}"
        data = response.json()
        assert data["status"] == "canceled"
        print(f"✓ Trade canceled: {trade['trade_id']}")
        
        # Verify listing reverted to active
        listing_response = requests.get(f"{BASE_URL}/api/listings/{listing['listing_id']}")
        assert listing_response.status_code == 200
        listing_data = listing_response.json()
        assert listing_data["status"] == "active", f"Expected 'active', got {listing_data['status']}"
        print(f"✓ Listing reverted to 'active' after cancel")


class TestAuthRegression:
    """Regression tests for authentication"""
    
    def test_register_new_user(self):
        """Test user registration"""
        email = f"test_reg_{int(time.time())}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "TestRegPass123!",
            "name": "Test Registration User"
        })
        assert response.status_code in [200, 201], f"Registration failed: {response.text}"
        data = response.json()
        assert "user_id" in data
        assert "token" in data
        assert data["email"] == email
        print(f"✓ User registration working: {data['user_id']}")
    
    def test_login_user(self):
        """Test user login"""
        # First register
        email = f"test_login_{int(time.time())}@test.com"
        password = "TestLoginPass123!"
        
        requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": password,
            "name": "Test Login User"
        })
        
        # Then login
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        print(f"✓ User login working")
    
    def test_get_me_authenticated(self):
        """Test /api/auth/me with valid token"""
        # Register and get token
        email = f"test_me_{int(time.time())}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "TestMePass123!",
            "name": "Test Me User"
        })
        token = response.json().get("token")
        
        # Call /me
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == email
        assert "cash_app_tag" in data  # New field should be present
        print(f"✓ /api/auth/me working with cash_app_tag field")
    
    def test_update_profile_cash_app_tag(self):
        """Test updating cash_app_tag via PUT /api/auth/profile"""
        # Register
        email = f"test_profile_{int(time.time())}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "TestProfilePass123!",
            "name": "Test Profile User"
        })
        token = response.json().get("token")
        
        # Update profile with cash_app_tag
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={"cash_app_tag": "$TestProfileTag"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cash_app_tag"] == "$TestProfileTag"
        print(f"✓ Profile update with cash_app_tag working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
