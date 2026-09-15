#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime

class SportsCardsAPITester:
    def __init__(self, base_url="https://sports-card-bot.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details
        })

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=10)

            success = response.status_code == expected_status
            
            if success:
                self.log_test(name, True)
                try:
                    return True, response.json()
                except:
                    return True, response.text
            else:
                error_msg = f"Expected {expected_status}, got {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {response.text[:200]}"
                
                self.log_test(name, False, error_msg)
                return False, {}

        except requests.exceptions.RequestException as e:
            self.log_test(name, False, f"Request failed: {str(e)}")
            return False, {}
        except Exception as e:
            self.log_test(name, False, f"Error: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test basic health endpoints"""
        print("\n=== HEALTH CHECK TESTS ===")
        
        # Test root endpoint
        self.run_test("Root Endpoint", "GET", "", 200)
        
        # Test health endpoint
        self.run_test("Health Check", "GET", "health", 200)

    def test_knowledge_endpoints(self):
        """Test knowledge hub endpoints"""
        print("\n=== KNOWLEDGE HUB TESTS ===")
        
        # Test get all knowledge
        success, data = self.run_test("Get All Knowledge", "GET", "knowledge/all", 200)
        if success and data:
            # Verify structure
            required_keys = ['best_packs', 'best_blasters', 'hottest_cards', 'best_autos', 'terminology', 'retailer_links']
            missing_keys = [key for key in required_keys if key not in data]
            if missing_keys:
                self.log_test("Knowledge Data Structure", False, f"Missing keys: {missing_keys}")
            else:
                self.log_test("Knowledge Data Structure", True)
        
        # Test individual endpoints
        self.run_test("Get Best Packs", "GET", "knowledge/packs", 200)
        self.run_test("Get NFL Packs", "GET", "knowledge/packs/NFL", 200)
        self.run_test("Get NBA Packs", "GET", "knowledge/packs/NBA", 200)
        self.run_test("Get Invalid Sport Packs", "GET", "knowledge/packs/INVALID", 404)
        self.run_test("Get Best Blasters", "GET", "knowledge/blasters", 200)
        self.run_test("Get Hottest Cards", "GET", "knowledge/hottest-cards", 200)
        self.run_test("Get Best Autos", "GET", "knowledge/best-autos", 200)
        self.run_test("Get Terminology", "GET", "knowledge/terminology", 200)
        self.run_test("Get Retailers", "GET", "knowledge/retailers", 200)

    def test_auth_endpoints(self):
        """Test authentication endpoints"""
        print("\n=== AUTHENTICATION TESTS ===")
        
        # Generate unique test user
        timestamp = datetime.now().strftime("%H%M%S")
        test_email = f"test_user_{timestamp}@example.com"
        test_password = "TestPass123!"
        test_name = f"Test User {timestamp}"
        
        # Test registration
        register_data = {
            "email": test_email,
            "password": test_password,
            "name": test_name
        }
        
        success, response = self.run_test("User Registration", "POST", "auth/register", 200, register_data)
        if success and response:
            self.token = response.get('token')
            self.user_id = response.get('user_id')
            print(f"   Registered user: {self.user_id}")
        
        # Test login
        login_data = {
            "email": test_email,
            "password": test_password
        }
        
        success, response = self.run_test("User Login", "POST", "auth/login", 200, login_data)
        if success and response:
            self.token = response.get('token')
            print(f"   Login token: {self.token[:20]}...")
        
        # Test invalid login
        invalid_login = {
            "email": test_email,
            "password": "wrongpassword"
        }
        self.run_test("Invalid Login", "POST", "auth/login", 401, invalid_login)
        
        # Test get current user (requires auth)
        if self.token:
            self.run_test("Get Current User", "GET", "auth/me", 200)
        
        # Test logout
        if self.token:
            self.run_test("User Logout", "POST", "auth/logout", 200)

    def test_marketplace_endpoints(self):
        """Test marketplace endpoints"""
        print("\n=== MARKETPLACE TESTS ===")
        
        # Test get listings (public)
        self.run_test("Get All Listings", "GET", "listings", 200)
        
        # Test with filters
        self.run_test("Get NFL Listings", "GET", "listings?sport=NFL", 200)
        self.run_test("Get Auto Cards", "GET", "listings?card_type=Auto", 200)
        self.run_test("Get Price Range", "GET", "listings?min_price=10&max_price=100", 200)
        
        # Test authenticated endpoints (requires login)
        if self.token:
            # Test create listing
            listing_data = {
                "title": "Test Card Listing",
                "description": "This is a test card listing",
                "sport": "NFL",
                "card_type": "Rookie",
                "player_name": "Test Player",
                "team": "Test Team",
                "year": "2024",
                "brand": "Panini",
                "condition": "Mint",
                "price": 50.00,
                "is_tradeable": False,
                "images": []
            }
            
            success, response = self.run_test("Create Listing", "POST", "listings", 201, listing_data)
            
            if success and response:
                listing_id = response.get('listing_id')
                print(f"   Created listing: {listing_id}")
                
                # Test get specific listing
                self.run_test("Get Specific Listing", "GET", f"listings/{listing_id}", 200)
                
                # Test get my listings
                self.run_test("Get My Listings", "GET", "my-listings", 200)
                
                # Test update listing
                update_data = listing_data.copy()
                update_data['price'] = 75.00
                self.run_test("Update Listing", "PUT", f"listings/{listing_id}", 200, update_data)
                
                # Test delete listing
                self.run_test("Delete Listing", "DELETE", f"listings/{listing_id}", 200)
        else:
            print("   Skipping authenticated marketplace tests - no token")

    def test_messaging_endpoints(self):
        """Test messaging endpoints"""
        print("\n=== MESSAGING TESTS ===")
        
        if self.token:
            # Test get messages
            self.run_test("Get Messages", "GET", "messages", 200)
            
            # Test get conversation (with fake user)
            self.run_test("Get Conversation", "GET", "messages/conversation/fake_user_id", 200)
        else:
            print("   Skipping messaging tests - no token")

    def test_payment_endpoints(self):
        """Test payment endpoints"""
        print("\n=== PAYMENT TESTS ===")
        
        if self.token:
            # Test get transactions
            self.run_test("Get My Transactions", "GET", "my-transactions", 200)
        else:
            print("   Skipping payment tests - no token")

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Sports Cards API Tests")
        print(f"Testing against: {self.base_url}")
        
        try:
            self.test_health_check()
            self.test_knowledge_endpoints()
            self.test_auth_endpoints()
            self.test_marketplace_endpoints()
            self.test_messaging_endpoints()
            self.test_payment_endpoints()
            
        except KeyboardInterrupt:
            print("\n⚠️  Tests interrupted by user")
        except Exception as e:
            print(f"\n💥 Unexpected error: {e}")
        
        # Print summary
        print(f"\n📊 TEST SUMMARY")
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        # Print failed tests
        failed_tests = [result for result in self.test_results if not result['success']]
        if failed_tests:
            print(f"\n❌ FAILED TESTS ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   • {test['test']}: {test['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = SportsCardsAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())