from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
import csv
import io
import base64
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import logging
import re
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
from jose import jwt, JWTError
import httpx
from bs4 import BeautifulSoup
import stripe as stripe_sdk
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'cardfanatic_secret_key')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

# Stripe Config
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY')

# Create the main app
app = FastAPI(title="Rip N' Flip API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============== MODELS ==============

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    cash_app_tag: Optional[str] = None
    created_at: datetime

class UserUpdate(BaseModel):
    name: Optional[str] = None
    cash_app_tag: Optional[str] = None
    picture: Optional[str] = None

class ListingCreate(BaseModel):
    title: str
    description: str
    sport: str  # NFL, NBA, MLB, NHL, Soccer
    card_type: str  # Auto, Rookie, Numbered, Parallel, Base
    player_name: str
    team: Optional[str] = None
    year: Optional[str] = None
    brand: Optional[str] = None
    condition: str  # Mint, Near Mint, Excellent, Good, Fair
    price: float
    is_tradeable: bool = False
    images: List[str] = []

class Listing(BaseModel):
    model_config = ConfigDict(extra="ignore")
    listing_id: str
    user_id: str
    seller_name: str
    title: str
    description: str
    sport: str
    card_type: str
    player_name: str
    team: Optional[str] = None
    year: Optional[str] = None
    brand: Optional[str] = None
    condition: str
    price: float
    is_tradeable: bool
    images: List[str]
    status: str  # active, sold, pending
    created_at: datetime

class MessageCreate(BaseModel):
    listing_id: str
    receiver_id: str
    content: str

class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: str
    listing_id: str
    sender_id: str
    sender_name: str
    receiver_id: str
    content: str
    is_read: bool
    created_at: datetime

class CheckoutRequest(BaseModel):
    listing_id: str
    origin_url: str

# ============== AUTH HELPERS ==============

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> Optional[dict]:
    # Check cookie first, then Authorization header
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    
    if not token:
        return None
    
    try:
        # Check if it's a session token from Google OAuth
        session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if session:
            expires_at = session.get("expires_at")
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                return None
            user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
            return user
        
        # Try JWT decode
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if user_id:
            user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            return user
    except JWTError:
        pass
    except Exception as e:
        logger.error(f"Auth error: {e}")
    
    return None

async def require_auth(request: Request) -> dict:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# ============== AUTH ROUTES ==============

@api_router.post("/auth/register")
async def register(user_data: UserCreate, response: Response):
    existing = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    hashed_pw = hash_password(user_data.password)
    
    user_doc = {
        "user_id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "password_hash": hashed_pw,
        "picture": None,
        "cash_app_tag": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.insert_one(user_doc)
    
    token = create_jwt_token(user_id)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=60 * 60 * 24 * JWT_EXPIRATION_DAYS,
        path="/"
    )
    
    return {
        "user_id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "token": token
    }

@api_router.post("/auth/login")
async def login(credentials: UserLogin, response: Response):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_jwt_token(user["user_id"])
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=60 * 60 * 24 * JWT_EXPIRATION_DAYS,
        path="/"
    )
    
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture"),
        "token": token
    }

# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
@api_router.post("/auth/session")
async def process_session(request: Request, response: Response):
    """Process session_id from Emergent OAuth"""
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    # Exchange session_id for user data
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id}
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        oauth_data = resp.json()
    
    email = oauth_data.get("email")
    name = oauth_data.get("name")
    picture = oauth_data.get("picture")
    session_token = oauth_data.get("session_token")
    
    # Check if user exists
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user info
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture}}
        )
    else:
        # Create new user
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "cash_app_tag": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(user_doc)
    
    # Store session
    session_doc = {
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.user_sessions.insert_one(session_doc)
    
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=60 * 60 * 24 * 7,
        path="/"
    )
    
    return {
        "user_id": user_id,
        "email": email,
        "name": name,
        "picture": picture
    }

@api_router.get("/auth/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture"),
        "cash_app_tag": user.get("cash_app_tag")
    }

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_many({"session_token": token})
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}

@api_router.put("/auth/profile")
async def update_profile(update_data: UserUpdate, request: Request):
    user = await require_auth(request)
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if update_dict:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": update_dict})
    updated_user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return updated_user

# ============== SPORTS CARDS KNOWLEDGE DATA ==============

SPORTS_KNOWLEDGE = {
    "best_packs": {
        "NFL": [
            {"name": "Panini Prizm Football Hobby", "price_range": "$400-$600", "why": "Best prizm parallels, rookie autos", "hot_pulls": "Trevor Lawrence Prizm RC, Gold Prizms", "retailer_links": ["Target", "Walmart", "eBay"]},
            {"name": "Panini Select Football", "price_range": "$300-$500", "why": "Die-cut designs, tiered parallels", "hot_pulls": "CJ Stroud Die-Cut, Kaboom inserts", "retailer_links": ["Target", "eBay", "Blowout Cards"]},
            {"name": "Panini Mosaic Football Blaster", "price_range": "$30-$40", "why": "Affordable entry, great designs", "hot_pulls": "Mosaic Prizms, Genesis parallels", "retailer_links": ["Target", "Walmart", "GameStop"]},
            {"name": "Topps Chrome Football", "price_range": "$150-$250", "why": "Classic chrome finish, refractors", "hot_pulls": "Refractor RCs, Auto variations", "retailer_links": ["Target", "eBay"]}
        ],
        "NBA": [
            {"name": "Panini Prizm Basketball Hobby", "price_range": "$500-$800", "why": "The gold standard for basketball", "hot_pulls": "Victor Wembanyama RC Prizms, Gold/1", "retailer_links": ["Target", "Walmart", "eBay"]},
            {"name": "Panini National Treasures", "price_range": "$800-$1500", "why": "Premium hits, RPAs galore", "hot_pulls": "Patch Autos /99, Logoman 1/1", "retailer_links": ["eBay", "Blowout Cards"]},
            {"name": "Panini Select Basketball", "price_range": "$250-$400", "why": "Courtside tier hunting", "hot_pulls": "Courtside Prizms, Tie-Dye /25", "retailer_links": ["Target", "eBay"]},
            {"name": "Hoops Basketball Blaster", "price_range": "$25-$35", "why": "Budget-friendly rookies", "hot_pulls": "Rookie Cards, Artist Proof parallels", "retailer_links": ["Target", "Walmart"]}
        ],
        "MLB": [
            {"name": "Topps Chrome Baseball Hobby", "price_range": "$300-$500", "why": "Iconic brand, best refractors", "hot_pulls": "Gold Refractor /50, SuperFractors", "retailer_links": ["Target", "Walmart", "eBay"]},
            {"name": "Bowman Chrome", "price_range": "$250-$400", "why": "Prospect hunting paradise", "hot_pulls": "1st Bowman Chrome Autos, Refractors", "retailer_links": ["Target", "eBay"]},
            {"name": "Topps Series 1/2 Hobby", "price_range": "$100-$150", "why": "Flagship product, SP hunting", "hot_pulls": "Photo Variation SPs, Autos", "retailer_links": ["Target", "Walmart", "eBay"]},
            {"name": "Panini Prizm Baseball", "price_range": "$200-$350", "why": "Prizm parallels for baseball", "hot_pulls": "Color Prizms, Tiger Stripe", "retailer_links": ["Target", "eBay"]}
        ],
        "NHL": [
            {"name": "Upper Deck Series 1/2", "price_range": "$80-$120", "why": "Only licensed NHL product", "hot_pulls": "Young Guns RCs, Canvas parallels", "retailer_links": ["eBay", "Dave & Adam's"]},
            {"name": "Upper Deck Ice", "price_range": "$150-$250", "why": "Acetate cards, premium feel", "hot_pulls": "Ice Premieres /99, Exquisite", "retailer_links": ["eBay", "Steel City"]},
            {"name": "SP Authentic", "price_range": "$200-$350", "why": "Future Watch Autos", "hot_pulls": "FW Autos /999, Limited Autos", "retailer_links": ["eBay", "Blowout Cards"]}
        ],
        "Soccer": [
            {"name": "Topps Chrome UEFA Champions League", "price_range": "$150-$300", "why": "Top soccer chrome product", "hot_pulls": "Refractor RCs, Autos", "retailer_links": ["Target", "eBay"]},
            {"name": "Panini Prizm Premier League", "price_range": "$200-$400", "why": "Prizm for soccer fans", "hot_pulls": "Color Prizms, Breakaway inserts", "retailer_links": ["eBay", "Blowout Cards"]},
            {"name": "Topps Merlin Chrome", "price_range": "$100-$200", "why": "Heritage design, modern chrome", "hot_pulls": "Refractors, Heritage Autos", "retailer_links": ["Target", "eBay"]}
        ]
    },
    "best_blasters": [
        {"name": "Prizm Football Blaster", "sport": "NFL", "price": "$35", "card_count": 6, "best_for": "Prizm parallels on budget"},
        {"name": "Prizm Basketball Blaster", "sport": "NBA", "price": "$35", "card_count": 6, "best_for": "Hunting Wemby RCs"},
        {"name": "Topps Chrome Baseball Blaster", "sport": "MLB", "price": "$30", "card_count": 4, "best_for": "Refractor hunting"},
        {"name": "Mosaic Football Blaster", "sport": "NFL", "price": "$30", "card_count": 6, "best_for": "Genesis parallels"},
        {"name": "Donruss Basketball Blaster", "sport": "NBA", "price": "$25", "card_count": 11, "best_for": "Rated Rookie cards"},
        {"name": "Select Football Blaster", "sport": "NFL", "price": "$40", "card_count": 6, "best_for": "Die-cut cards"}
    ],
    "hottest_cards": [
        {"name": "Victor Wembanyama Prizm RC", "sport": "NBA", "price_range": "$200-$2000+", "why": "Generational talent", "trend": "Rising"},
        {"name": "CJ Stroud Prizm RC", "sport": "NFL", "price_range": "$50-$500", "why": "Elite QB play", "trend": "Rising"},
        {"name": "Caleb Williams Prizm RC", "sport": "NFL", "price_range": "$30-$300", "why": "Heisman winner, Bears QB", "trend": "Steady"},
        {"name": "Shohei Ohtani Chrome RC", "sport": "MLB", "price_range": "$500-$5000+", "why": "Two-way legend", "trend": "Peak"},
        {"name": "Connor Bedard Young Guns", "sport": "NHL", "price_range": "$100-$800", "why": "Generational hockey talent", "trend": "Rising"},
        {"name": "Jude Bellingham Prizm", "sport": "Soccer", "price_range": "$50-$400", "why": "Real Madrid superstar", "trend": "Rising"},
        {"name": "Anthony Edwards Prizm RC", "sport": "NBA", "price_range": "$100-$1000", "why": "Face of new generation", "trend": "Rising"},
        {"name": "Ja'Marr Chase Prizm RC", "sport": "NFL", "price_range": "$40-$400", "why": "Elite WR performance", "trend": "Steady"}
    ],
    "best_autos": [
        {"name": "Patrick Mahomes Prizm Auto", "sport": "NFL", "price_range": "$500-$5000", "why": "3x Super Bowl MVP", "rarity": "Rare"},
        {"name": "LeBron James National Treasures RPA", "sport": "NBA", "price_range": "$50,000-$500,000+", "why": "GOAT conversation", "rarity": "Ultra Rare"},
        {"name": "Mike Trout Bowman Chrome Auto", "sport": "MLB", "price_range": "$2000-$20,000", "why": "Best player of generation", "rarity": "Rare"},
        {"name": "Connor McDavid SP Authentic FW Auto", "sport": "NHL", "price_range": "$1000-$10,000", "why": "Best player in hockey", "rarity": "Rare"},
        {"name": "Kylian Mbappe Topps Chrome Auto", "sport": "Soccer", "price_range": "$500-$3000", "why": "World class striker", "rarity": "Rare"},
        {"name": "Victor Wembanyama NT RPA", "sport": "NBA", "price_range": "$10,000-$100,000+", "why": "Unicorn prospect", "rarity": "Ultra Rare"},
        {"name": "CJ Stroud Prizm Auto /25", "sport": "NFL", "price_range": "$1000-$5000", "why": "OROY candidate", "rarity": "Very Rare"}
    ],
    "terminology": [
        {"term": "RC", "meaning": "Rookie Card - First official card of a player"},
        {"term": "PSA", "meaning": "Professional Sports Authenticator - Grading company (1-10 scale)"},
        {"term": "BGS", "meaning": "Beckett Grading Services - Another top grading company"},
        {"term": "SGC", "meaning": "Sports Guarantee Company - Third major grader"},
        {"term": "Auto", "meaning": "Autograph - Signed card"},
        {"term": "Relic", "meaning": "Card containing game-worn jersey/patch piece"},
        {"term": "RPA", "meaning": "Rookie Patch Auto - Rookie card with auto AND jersey patch"},
        {"term": "/25, /99", "meaning": "Numbered - Only that many copies exist (e.g., /25 = 25 total)"},
        {"term": "1/1", "meaning": "One of One - Only single copy in existence"},
        {"term": "Prizm", "meaning": "Panini's chrome-style premium parallel"},
        {"term": "Refractor", "meaning": "Topps Chrome shiny parallel variation"},
        {"term": "SP", "meaning": "Short Print - Limited print run, harder to find"},
        {"term": "SSP", "meaning": "Super Short Print - Even more rare than SP"},
        {"term": "Parallel", "meaning": "Variation of base card with different color/finish"},
        {"term": "Insert", "meaning": "Special card inserted at lower odds"},
        {"term": "Hobby Box", "meaning": "Premium box sold at card shops, guaranteed hits"},
        {"term": "Blaster", "meaning": "Retail box sold at Target/Walmart"},
        {"term": "Hanger", "meaning": "Retail pack hanging on pegs"},
        {"term": "Cello/Fat Pack", "meaning": "Larger retail pack with more cards"},
        {"term": "Break", "meaning": "Group purchase where breaker opens and ships your team's cards"},
        {"term": "Case Hit", "meaning": "Ultra rare card, maybe 1 per case"},
        {"term": "Wax", "meaning": "Slang for sealed packs/boxes"},
        {"term": "Slab", "meaning": "Graded card in protective case"},
        {"term": "Raw", "meaning": "Ungraded card"},
        {"term": "PC", "meaning": "Personal Collection - Cards you keep, not sell"},
        {"term": "Comp", "meaning": "Comparable sale - What similar cards sold for"},
        {"term": "Kaboom", "meaning": "Popular rare insert in Panini products"},
        {"term": "Downtown", "meaning": "Another popular rare insert"},
        {"term": "Color Match", "meaning": "Parallel color matching team colors"},
        {"term": "Young Guns", "meaning": "Upper Deck's NHL rookie card subset"}
    ],
    "retailer_links": {
        "Target": "https://www.target.com/s?searchTerm=sports+trading+cards",
        "Walmart": "https://www.walmart.com/browse/toys/trading-cards/4171_4191",
        "eBay": "https://www.ebay.com/b/Sports-Trading-Cards/212/bn_1865497",
        "Blowout Cards": "https://www.blowoutcards.com/",
        "Steel City": "https://www.steelcitycollectibles.com/",
        "Dave & Adam's": "https://www.dacardworld.com/",
        "GameStop": "https://www.gamestop.com/collectibles/trading-cards"
    }
}

# ============== KNOWLEDGE ROUTES ==============

@api_router.get("/knowledge/packs/{sport}")
async def get_best_packs(sport: str):
    sport_upper = sport.upper()
    if sport_upper not in SPORTS_KNOWLEDGE["best_packs"]:
        raise HTTPException(status_code=404, detail="Sport not found")
    return {"sport": sport_upper, "packs": SPORTS_KNOWLEDGE["best_packs"][sport_upper]}

@api_router.get("/knowledge/packs")
async def get_all_packs():
    return SPORTS_KNOWLEDGE["best_packs"]

@api_router.get("/knowledge/blasters")
async def get_best_blasters():
    return SPORTS_KNOWLEDGE["best_blasters"]

@api_router.get("/knowledge/hottest-cards")
async def get_hottest_cards():
    return SPORTS_KNOWLEDGE["hottest_cards"]

@api_router.get("/knowledge/best-autos")
async def get_best_autos():
    return SPORTS_KNOWLEDGE["best_autos"]

@api_router.get("/knowledge/terminology")
async def get_terminology():
    return SPORTS_KNOWLEDGE["terminology"]

@api_router.get("/knowledge/retailers")
async def get_retailers():
    return SPORTS_KNOWLEDGE["retailer_links"]

@api_router.get("/knowledge/all")
async def get_all_knowledge():
    return SPORTS_KNOWLEDGE


# Curated "What's Hot Right Now" — top 8 trending packs for the homepage.
# Each pack has chase cards + tier odds embedded for the Analyzer Verdict Engine.
HOT_PACKS_NOW = [
    {
        "pack_id": "prizm-bball-hobby", "name": "Panini Prizm Basketball Hobby", "sport": "NBA",
        "tagline": "Wemby RC chase", "why_hot": "Generational rookie class + color prizms exploding",
        "retail_price": 800, "badge": "🔥 WEMBY SZN",
        "search_query": "panini prizm basketball hobby box sealed",
        "checklist_set": "Prizm Basketball",
        "chase_cards": [
            {"name": "Wembanyama Prizm RC", "rarity": "Base RC (chase parallel)", "value": "$200-2000+", "why": "Generational"},
            {"name": "Wembanyama Gold Prizm /10", "rarity": "Gold /10", "value": "$30,000+", "why": "Top tier grail"},
            {"name": "Wembanyama Auto /99", "rarity": "Numbered Auto", "value": "$15,000+", "why": "1-of-99 Wemby on-card"},
            {"name": "Edwards Choice Prizm", "rarity": "Insert", "value": "$200-800", "why": "Face of new gen"},
        ],
        "tier_odds": [
            {"tier": "Base / Veterans", "odds_text": "Every pack", "ratio": 1.0},
            {"tier": "Color Prizms", "odds_text": "1:6 packs", "ratio": 0.16},
            {"tier": "Silver/Gold parallels", "odds_text": "1:24 packs", "ratio": 0.04},
            {"tier": "Auto", "odds_text": "1:48 packs", "ratio": 0.021},
            {"tier": "Numbered /10 or less", "odds_text": "1:case", "ratio": 0.005},
        ],
    },
    {
        "pack_id": "prizm-fball-hobby", "name": "Panini Prizm Football Hobby", "sport": "NFL",
        "tagline": "Gold standard", "why_hot": "CJ Stroud / Caleb Williams RC demand through the roof",
        "retail_price": 500, "badge": "🔥 HOT",
        "search_query": "panini prizm football hobby box sealed",
        "checklist_set": "Prizm Football",
        "chase_cards": [
            {"name": "CJ Stroud Prizm RC", "rarity": "Base RC", "value": "$50-500", "why": "OROY"},
            {"name": "Caleb Williams Prizm RC", "rarity": "Base RC", "value": "$30-300", "why": "Bears QB future"},
            {"name": "Mahomes Color Blast", "rarity": "Insert", "value": "$300-1500", "why": "GOAT chase insert"},
            {"name": "Stroud Gold /10", "rarity": "Gold /10", "value": "$3000-8000", "why": "Top RC parallel"},
        ],
        "tier_odds": [
            {"tier": "Base / Rookies", "odds_text": "Every pack", "ratio": 1.0},
            {"tier": "Color Prizms", "odds_text": "1:6 packs", "ratio": 0.16},
            {"tier": "Silver Prizm RC", "odds_text": "1:8 packs", "ratio": 0.125},
            {"tier": "Auto", "odds_text": "1:24 packs", "ratio": 0.041},
            {"tier": "Numbered /25 or less", "odds_text": "1:case", "ratio": 0.005},
        ],
    },
    {
        "pack_id": "topps-chrome-baseball", "name": "Topps Chrome Baseball Hobby", "sport": "MLB",
        "tagline": "Refractor heaven", "why_hot": "Ohtani era + prospect Bowman crossovers",
        "retail_price": 400, "badge": "📈 RISING",
        "search_query": "topps chrome baseball hobby box sealed",
        "checklist_set": "Topps Chrome Baseball",
        "chase_cards": [
            {"name": "Ohtani Refractor", "rarity": "Refractor", "value": "$100-600", "why": "Two-way legend"},
            {"name": "Holliday Refractor RC", "rarity": "Rookie Refractor", "value": "$150-500", "why": "#1 prospect"},
            {"name": "Ohtani SuperFractor 1/1", "rarity": "1/1", "value": "$50,000+", "why": "Ultimate grail"},
            {"name": "Gold Refractor /50", "rarity": "Gold /50", "value": "$200-2000", "why": "Centered chase"},
        ],
        "tier_odds": [
            {"tier": "Base", "odds_text": "Every pack", "ratio": 1.0},
            {"tier": "Refractor", "odds_text": "1:4 packs", "ratio": 0.25},
            {"tier": "Color Refractor", "odds_text": "1:12 packs", "ratio": 0.083},
            {"tier": "Auto", "odds_text": "2:hobby box", "ratio": 0.083},
            {"tier": "SuperFractor 1/1", "odds_text": "1:case+", "ratio": 0.001},
        ],
    },
    {
        "pack_id": "select-fball-hobby", "name": "Panini Select Football Hobby", "sport": "NFL",
        "tagline": "Die-cut kings", "why_hot": "Kaboom inserts + Courtside-tier chase",
        "retail_price": 400, "badge": "🎯 CHASE",
        "search_query": "panini select football hobby box sealed",
        "checklist_set": "Select Football",
        "chase_cards": [
            {"name": "Stroud Kaboom", "rarity": "SSP Insert", "value": "$2000-8000", "why": "Iconic insert"},
            {"name": "Mahomes Field Level Auto /35", "rarity": "Tier Auto", "value": "$1500+", "why": "Premier auto tier"},
            {"name": "Tie-Dye Prizm /25", "rarity": "Numbered /25", "value": "$300-1200", "why": "Color match potential"},
            {"name": "Caleb Williams Concourse RC", "rarity": "Tier 1 RC", "value": "$30-150", "why": "Entry chase"},
        ],
        "tier_odds": [
            {"tier": "Concourse Base", "odds_text": "Every pack", "ratio": 1.0},
            {"tier": "Premier / Field Level", "odds_text": "1:8 packs", "ratio": 0.125},
            {"tier": "Tier Prizms", "odds_text": "1:18 packs", "ratio": 0.055},
            {"tier": "Auto", "odds_text": "2:hobby box", "ratio": 0.083},
            {"tier": "Kaboom SSP", "odds_text": "1:case", "ratio": 0.005},
        ],
    },
    {
        "pack_id": "upperdeck-hockey-s1", "name": "Upper Deck Series 1 Hockey", "sport": "NHL",
        "tagline": "Young Guns country", "why_hot": "Bedard Young Guns still carrying the product",
        "retail_price": 100, "badge": "❄️ STAPLE",
        "search_query": "upper deck series 1 hockey hobby box",
        "checklist_set": "Upper Deck Series 1",
        "chase_cards": [
            {"name": "Bedard Young Guns RC", "rarity": "YG Rookie", "value": "$100-800", "why": "Generational"},
            {"name": "Carlsson YG", "rarity": "YG Rookie", "value": "$30-150", "why": "Strong sophomore"},
            {"name": "McDavid Canvas", "rarity": "Canvas Parallel", "value": "$15-60", "why": "Best player on planet"},
            {"name": "Bedard Exclusives /100", "rarity": "Numbered /100", "value": "$1500-5000", "why": "Chase parallel"},
        ],
        "tier_odds": [
            {"tier": "Base", "odds_text": "Every pack", "ratio": 1.0},
            {"tier": "Canvas", "odds_text": "1:6 packs", "ratio": 0.16},
            {"tier": "Young Guns", "odds_text": "1:4 packs", "ratio": 0.25},
            {"tier": "Exclusives /100", "odds_text": "1:hobby box", "ratio": 0.041},
            {"tier": "High Gloss /10", "odds_text": "1:case", "ratio": 0.005},
        ],
    },
    {
        "pack_id": "topps-ucl-chrome", "name": "Topps Chrome UCL Soccer", "sport": "Soccer",
        "tagline": "Euro chrome", "why_hot": "Bellingham + Mbappe Madrid mega chase",
        "retail_price": 250, "badge": "⚽ GLOBAL",
        "search_query": "topps chrome champions league hobby box",
        "checklist_set": "Topps Chrome UCL",
        "chase_cards": [
            {"name": "Bellingham Refractor", "rarity": "Refractor", "value": "$50-300", "why": "Madrid superstar"},
            {"name": "Mbappe Refractor RC variation", "rarity": "Refractor", "value": "$80-500", "why": "Madrid debut RC"},
            {"name": "Yamal Refractor RC", "rarity": "Rookie Refractor", "value": "$100-600", "why": "Generational young talent"},
            {"name": "SuperFractor 1/1", "rarity": "1/1", "value": "$15,000+", "why": "Top of the food chain"},
        ],
        "tier_odds": [
            {"tier": "Base", "odds_text": "Every pack", "ratio": 1.0},
            {"tier": "Refractor", "odds_text": "1:4 packs", "ratio": 0.25},
            {"tier": "Color Refractor", "odds_text": "1:18 packs", "ratio": 0.055},
            {"tier": "Auto", "odds_text": "1:hobby box", "ratio": 0.041},
            {"tier": "Numbered /5 or less", "odds_text": "1:case", "ratio": 0.005},
        ],
    },
    {
        "pack_id": "mosaic-fball-blaster", "name": "Panini Mosaic Football Blaster", "sport": "NFL",
        "tagline": "Budget rip", "why_hot": "Cheapest way into Genesis parallels",
        "retail_price": 30, "badge": "💰 VALUE",
        "search_query": "panini mosaic football blaster box",
        "checklist_set": "Mosaic Football",
        "chase_cards": [
            {"name": "Stroud Mosaic RC", "rarity": "Base RC", "value": "$15-60", "why": "Affordable RC entry"},
            {"name": "Genesis parallels", "rarity": "SSP Parallel", "value": "$50-500", "why": "Blaster-only chase"},
            {"name": "Caleb Williams Pink Camo", "rarity": "Retail Parallel", "value": "$15-80", "why": "Walmart blaster exclusive"},
            {"name": "Mosaic Auto", "rarity": "Auto (rare)", "value": "$200-2000", "why": "Hit of the box"},
        ],
        "tier_odds": [
            {"tier": "Base", "odds_text": "Every pack", "ratio": 1.0},
            {"tier": "Reactive Parallel", "odds_text": "1:2 packs", "ratio": 0.5},
            {"tier": "Pink Camo / Reactive", "odds_text": "1 per blaster", "ratio": 0.16},
            {"tier": "Genesis SSP", "odds_text": "1:case+", "ratio": 0.005},
            {"tier": "Auto", "odds_text": "1:60 blasters", "ratio": 0.016},
        ],
    },
    {
        "pack_id": "nt-bball-hobby", "name": "Panini National Treasures Basketball", "sport": "NBA",
        "tagline": "Top of the food chain", "why_hot": "RPAs, Logoman 1/1s, the grail hunt",
        "retail_price": 1500, "badge": "👑 PREMIUM",
        "search_query": "panini national treasures basketball hobby box",
        "checklist_set": "National Treasures Basketball",
        "chase_cards": [
            {"name": "Wemby NT RPA /99", "rarity": "RPA /99", "value": "$30,000+", "why": "Top RC patch auto"},
            {"name": "Logoman 1/1", "rarity": "1/1 Patch", "value": "$50,000+", "why": "Holy grail"},
            {"name": "Edwards NT Auto", "rarity": "On-card Auto", "value": "$2000+", "why": "Premium tier auto"},
            {"name": "Booklet RPA /10", "rarity": "Booklet /10", "value": "$8000+", "why": "Premium booklet"},
        ],
        "tier_odds": [
            {"tier": "Auto / Patch", "odds_text": "Every card has a hit", "ratio": 1.0},
            {"tier": "Numbered /99", "odds_text": "1:2 boxes", "ratio": 0.5},
            {"tier": "RPA Auto", "odds_text": "1:5 boxes", "ratio": 0.2},
            {"tier": "Logoman 1/1", "odds_text": "1:case", "ratio": 0.01},
            {"tier": "Booklet", "odds_text": "1:6 boxes", "ratio": 0.16},
        ],
    },
]


@api_router.get("/hot-packs")
async def get_hot_packs():
    """Return the curated What's Hot Right Now list for the homepage."""
    return {"packs": HOT_PACKS_NOW, "count": len(HOT_PACKS_NOW)}


@api_router.get("/analyzer/packs")
async def analyzer_pack_list():
    """Return all packs available for analysis (currently same as hot-packs)."""
    return {"packs": [
        {"pack_id": p["pack_id"], "name": p["name"], "sport": p["sport"], "retail_price": p["retail_price"], "badge": p["badge"]}
        for p in HOT_PACKS_NOW
    ]}


def _compute_verdict(retail_price: float, live_avg: Optional[float], pack: dict) -> dict:
    """Compute DUB / MID / TRASH verdict + score 0-100 + factors list."""
    factors = []
    score = 50  # neutral baseline

    if live_avg and retail_price:
        ratio = live_avg / retail_price
        delta_pct = round((ratio - 1) * 100)
        if ratio >= 1.15:
            factors.append(f"+ Live eBay ${live_avg:.0f} vs ${retail_price:.0f} MSRP (+{delta_pct}%) — sealed appreciating")
            score += 25
        elif ratio >= 0.95:
            factors.append(f"~ Sealed market ${live_avg:.0f} ≈ MSRP ${retail_price:.0f} ({delta_pct:+}%)")
            score += 5
        else:
            factors.append(f"- Sealed selling under MSRP (${live_avg:.0f} vs ${retail_price:.0f}, {delta_pct}%) — supply heavy")
            score -= 20
    else:
        factors.append("? Live market data unavailable — verdict is based on chase strength only")

    # Chase card strength
    chase = pack.get("chase_cards", [])
    grail_count = sum(1 for c in chase if any(x in c.get("value", "") for x in ["10,000", "30,000", "50,000", "15,000", "20,000", "8,000"]))
    if grail_count >= 2:
        factors.append(f"+ {grail_count} grail-tier chase cards in product")
        score += 15
    elif grail_count == 1:
        factors.append("+ 1 grail-tier chase card available")
        score += 8

    # Sport / brand modifier
    if pack.get("sport") == "NBA":
        factors.append("+ NBA market hottest segment in hobby")
        score += 5
    if "Hobby" in pack.get("name", ""):
        factors.append("+ Hobby format guarantees better hit rates than retail")
        score += 5
    if "Blaster" in pack.get("name", "") or "blaster" in pack.get("name", "").lower():
        factors.append("- Retail blaster — fun rip but EV typically negative")
        score -= 10
    if pack.get("retail_price", 0) > 1000:
        factors.append("- Premium price point limits resale audience")
        score -= 5

    score = max(0, min(100, score))

    if score >= 70:
        rating = "DUB"
        summary = "Strong chase + favorable market = good rip OR sealed hold"
    elif score >= 45:
        rating = "MID"
        summary = "Mixed signals — fun to rip, don't expect to flip the box"
    else:
        rating = "TRASH"
        summary = "Sealed market & chase strength don't justify the price"

    return {
        "rating": rating,
        "score": score,
        "summary": summary,
        "factors": factors,
    }


def _midpoint_of_value_range(s: str) -> float:
    """Parse '$200-2000+' or '$30,000+' into a midpoint estimate (legacy fallback only)."""
    if not s:
        return 0.0
    nums = re.findall(r"[\d,]+", s.replace("$", "").replace(",", ""))
    if not nums:
        return 0.0
    try:
        if len(nums) == 1:
            return float(nums[0])
        return (float(nums[0]) + float(nums[1])) / 2
    except ValueError:
        return 0.0


async def _real_market_verdict(pack: dict) -> dict:
    """Build a verdict using REAL recent eBay SOLD prices (not 0-100 fake score).
    - Sealed pack avg sold (LH_Sold=1)
    - Top 3 chase cards' actual sold avg
    - Computes expected pull value × tier odds → compare to pack cost
    - Verdict: DUB / MID / TRASH based on real market math

    Smart pricing chain (no silent hardcoding):
      1. Live eBay sold avg
      2. Live eBay active avg
      3. Stale cache (≤7d)
      4. last_known_avg from pack_market_cache (any age)
      5. MSRP — clearly tagged as 'msrp_fallback' so verdict can downweight it
    """
    # 1) Pack itself — recent SOLD listings. Wrap every external call in
    #    try/except so a single eBay hiccup never breaks the verdict.
    try:
        pack_sold = await _scrape_ebay_prices(pack["search_query"], sold_only=True)
    except Exception as ex:
        logger.warning(f"eBay sold scrape failed for {pack.get('pack_id')}: {ex}")
        pack_sold = {"avg": None, "count": 0, "blocked": True}

    # 2) Active listings as fallback (for blocked / no sold data)
    try:
        pack_active = await _scrape_ebay_prices(pack["search_query"], sold_only=False)
    except Exception as ex:
        logger.warning(f"eBay active scrape failed for {pack.get('pack_id')}: {ex}")
        pack_active = {"avg": None, "count": 0, "blocked": True}

    sealed_avg = pack_sold.get("avg") if pack_sold.get("count", 0) > 0 else pack_active.get("avg")
    sealed_source = "sold" if (pack_sold.get("count", 0) > 0) else ("active" if pack_active.get("count", 0) > 0 else None)

    # ── Persist last_known_avg whenever we got fresh data ──
    if sealed_avg:
        try:
            await db.pack_market_cache.update_one(
                {"pack_id": pack["pack_id"]},
                {"$set": {
                    "pack_id": pack["pack_id"],
                    "last_known_avg": float(sealed_avg),
                    "last_source": sealed_source,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )
        except Exception as ex:
            logger.warning(f"pack_market_cache write failed: {ex}")

    # 3) Smart fallback to stale-but-recent cache before resorting to MSRP
    cached_age_days: Optional[int] = None
    if not sealed_avg:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        q_lower = pack.get("search_query", "").strip().lower()
        for sold_flag in (True, False):
            try:
                cached = await db.price_cache.find_one(
                    {"cache_key": f"{q_lower}|sold={sold_flag}"}, {"_id": 0}
                )
            except Exception:
                cached = None
            if not cached:
                continue
            fetched = cached.get("fetched_at")
            if isinstance(fetched, str):
                try:
                    fetched = datetime.fromisoformat(fetched)
                except ValueError:
                    fetched = None
            if fetched and fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            if not fetched or fetched < cutoff:
                continue
            data = cached.get("data") or {}
            if data.get("avg"):
                sealed_avg = float(data["avg"])
                sealed_source = "cached_sold" if sold_flag else "cached_active"
                cached_age_days = max(0, (datetime.now(timezone.utc) - fetched).days)
                break

    # 4) Last-known-avg (any age) before final MSRP fallback
    if not sealed_avg:
        try:
            lk = await db.pack_market_cache.find_one({"pack_id": pack["pack_id"]}, {"_id": 0})
        except Exception:
            lk = None
        if lk and lk.get("last_known_avg"):
            sealed_avg = float(lk["last_known_avg"])
            sealed_source = "last_known"
            try:
                lu = lk.get("last_updated")
                if isinstance(lu, str):
                    lu_dt = datetime.fromisoformat(lu)
                    if lu_dt.tzinfo is None:
                        lu_dt = lu_dt.replace(tzinfo=timezone.utc)
                    cached_age_days = max(0, (datetime.now(timezone.utc) - lu_dt).days)
            except Exception:
                pass

    # 5) Final fallback — MSRP (clearly tagged)
    if sealed_avg:
        pack_cost = float(sealed_avg)
        pack_cost_source = sealed_source
    else:
        pack_cost = float(pack["retail_price"])
        pack_cost_source = "msrp_fallback"  # signals UI: market data unavailable

    # 3) Chase cards — real sold prices for each
    chase_market = []
    chase_pull_odds = []  # weighted sum of (avg_sold × probability) → expected value contribution
    # Tier ratios for chase-tier weighting (the rarer tiers have lower odds but higher value)
    rare_tier_ratio = sum(t["ratio"] for t in pack["tier_odds"] if t["ratio"] < 0.1)

    for c in pack["chase_cards"]:
        query = f"{pack['checklist_set']} {c['name']} sold"
        try:
            sold = await _scrape_ebay_prices(query, sold_only=True)
        except Exception:
            sold = {"avg": None, "count": 0}
        actual_avg = sold.get("avg") if sold.get("count", 0) > 0 else None
        # Fallback to estimated value range mid if eBay doesn't return data
        fallback = _midpoint_of_value_range(c.get("value", ""))
        chase_market.append({
            "name": c["name"],
            "rarity": c.get("rarity"),
            "ebay_sold_avg": actual_avg,
            "ebay_sold_count": sold.get("count", 0),
            "estimated_value": c.get("value"),
            "estimated_midpoint": fallback,
            "data_source": "ebay_sold" if actual_avg else "estimated",
        })
        # For EV math: if we have real sold data, use it. Otherwise use estimate.
        card_value = actual_avg if actual_avg else fallback

        # Probability of pulling this specific chase ≈ rare_tier_ratio / num_chase_cards (rough)
        per_card_prob = rare_tier_ratio / max(1, len(pack["chase_cards"]))
        chase_pull_odds.append(card_value * per_card_prob)

    expected_chase_value = sum(chase_pull_odds)

    # Add baseline value from non-chase pulls (rough: $1-3 per common pack)
    # Most packs have 8-12 cards; chase rarely hits, base value averages ~$5-15 per pack
    base_value_floor = 5.0  # conservative baseline

    expected_pull_value = round(expected_chase_value + base_value_floor, 2)

    # 4) Verdict logic — based on REAL math, not 0-100 score
    margin_pct = ((expected_pull_value - pack_cost) / pack_cost * 100) if pack_cost > 0 else 0
    factors = []

    if sealed_avg:
        delta_pct = round((sealed_avg - pack["retail_price"]) / pack["retail_price"] * 100)
        factors.append({
            "label": f"Sealed market ({sealed_source}): ${sealed_avg:.0f} vs MSRP ${pack['retail_price']}",
            "value": f"{delta_pct:+}%",
            "tone": "positive" if delta_pct > 5 else "negative" if delta_pct < -5 else "neutral",
        })
    else:
        factors.append({
            "label": "Sealed market data unavailable from eBay",
            "value": "(rate-limited or no listings)",
            "tone": "neutral",
        })

    chase_with_data = sum(1 for c in chase_market if c["ebay_sold_avg"])
    factors.append({
        "label": f"Chase cards with live sold data",
        "value": f"{chase_with_data}/{len(chase_market)}",
        "tone": "positive" if chase_with_data >= 2 else "neutral",
    })
    factors.append({
        "label": "Expected pull value (avg)",
        "value": f"${expected_pull_value}",
        "tone": "neutral",
    })
    factors.append({
        "label": "Pack cost (eBay sealed or MSRP)",
        "value": f"${pack_cost:.2f}",
        "tone": "neutral",
    })
    factors.append({
        "label": "Expected return on rip",
        "value": f"{margin_pct:+.0f}%",
        "tone": "positive" if margin_pct > 5 else "negative" if margin_pct < -20 else "neutral",
    })

    # Verdict thresholds — based purely on EV vs pack cost
    if expected_pull_value >= pack_cost * 1.05:
        rating = "DUB"
        summary = f"Expected ~${expected_pull_value} per rip on a ${pack_cost:.0f} pack. Real market data says it's worth ripping."
    elif expected_pull_value >= pack_cost * 0.7:
        rating = "MID"
        summary = f"Expected ~${expected_pull_value} per rip on a ${pack_cost:.0f} pack. Roughly break-even — rip for fun, don't expect profit."
    else:
        rating = "TRASH"
        summary = f"Expected ~${expected_pull_value} per rip on a ${pack_cost:.0f} pack. You'll lose money on average. Buy singles instead."

    return {
        "rating": rating,
        "summary": summary,
        "factors": factors,
        "expected_pull_value": expected_pull_value,
        "pack_cost": round(pack_cost, 2),
        "pack_cost_source": pack_cost_source,
        "pack_cost_cached_age_days": cached_age_days,
        "chase_market": chase_market,
        "based_on": "real_ebay_sold_data",
    }


@api_router.get("/analyzer/{pack_id}")
async def analyze_pack(pack_id: str, request: Request):
    """Run the verdict engine on a specific pack — uses REAL recent eBay SOLD data
    blended with aggregated user pull data (the Intelligence Loop).

    Monetization gate: anonymous users + Pro users (incl. 10-day trial) are
    unlimited. Free-tier logged-in users get capped at FREE_TIER_PACKS_PER_WEEK
    analyzer/log hits per 7-day rolling window, then 403 with upgrade copy.
    """
    pack = next((p for p in HOT_PACKS_NOW if p["pack_id"] == pack_id), None)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    # ── Monetization Gate ──
    # Anonymous = funnel-friendly, no limit.
    # Logged-in: enforce free-tier rolling weekly cap.
    user = await get_current_user(request)
    if user:
        tier = await _user_tier(user["user_id"])
        if tier == "free":
            week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            try:
                recent_count = await db.case_packs.count_documents({
                    "user_id": user["user_id"],
                    "created_at": {"$gte": week_ago},
                })
            except Exception:
                recent_count = 0
            if recent_count >= FREE_TIER_PACKS_PER_WEEK:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "free_tier_limit",
                        "message": "You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB.",
                        "cta_url": "/vault",
                        "limit": FREE_TIER_PACKS_PER_WEEK,
                        "used": recent_count,
                    },
                )

    verdict = await _real_market_verdict(pack)

    # Apply Intelligence Loop adjustment based on aggregated user pulls.
    # Wrap so a failure here never breaks the verdict UI.
    try:
        hit_rates = await _get_internal_hit_rates(pack_id)
        verdict = _intelligence_adjust(verdict, pack, hit_rates)
    except Exception as ex:
        logger.warning(f"intelligence adjust failed for {pack_id}: {ex}")

    # Pull legacy live_market structure for any consumers expecting the old shape
    try:
        market = await get_pack_price(q=pack["search_query"], sold=False)
    except Exception:
        market = {"avg": None, "min": None, "max": None, "count": 0, "blocked": True, "listings": []}

    return {
        "pack": {
            "pack_id": pack["pack_id"],
            "name": pack["name"],
            "sport": pack["sport"],
            "tagline": pack["tagline"],
            "why_hot": pack["why_hot"],
            "retail_price": pack["retail_price"],
            "badge": pack["badge"],
        },
        "live_market": {
            "avg": market.get("avg"),
            "min": market.get("min"),
            "max": market.get("max"),
            "count": market.get("count", 0),
            "blocked": market.get("blocked", False),
            "sample_listings": (market.get("listings") or [])[:3],
        },
        "chase_cards": pack["chase_cards"],
        "tier_odds": pack["tier_odds"],
        "verdict": verdict,
    }


# ============== PACK PREDICTOR (Probabilistic Simulator) ==============

import random as _random


class PredictorRequest(BaseModel):
    pack_id: str
    num_cards: Optional[int] = 8  # cards per simulated rip


@api_router.post("/predictor/simulate")
async def predictor_simulate(payload: PredictorRequest, request: Request):
    """LEGACY pure-random rip — preserved for backward compat. Prefer /predictor/rip."""
    pack = next((p for p in HOT_PACKS_NOW if p["pack_id"] == payload.pack_id), None)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    # Tier-limit check (logged-in users only) — use the Kingbuilt copy
    user = await get_current_user(request)
    if user:
        can_use, used, limit = await _check_predictor_tier_limit(user["user_id"])
        if not can_use:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "predictor_limit",
                    "message": "You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB.",
                    "cta_url": "/vault",
                    "used": used,
                    "limit": limit,
                },
            )

    num_cards = max(3, min(payload.num_cards or 8, 12))
    tiers = pack["tier_odds"]
    chase = pack["chase_cards"]

    # Apply jitter (±15% per tier) to prevent the predictor from being exact
    jittered_weights = []
    for t in tiers:
        ratio = t.get("ratio", 0.1)
        jitter = ratio * (0.85 + _random.random() * 0.30)
        jittered_weights.append(jitter)

    # Each pulled card picks a tier weighted by its (jittered) ratio
    pulls = []
    for slot_idx in range(num_cards):
        # weighted pick of tier
        total = sum(jittered_weights)
        r = _random.random() * total
        acc = 0
        chosen_tier = tiers[0]
        for i, w in enumerate(jittered_weights):
            acc += w
            if r <= acc:
                chosen_tier = tiers[i]
                break

        # Decide card details: if this tier is rare AND we have chase cards, use a chase card
        is_rare_tier = chosen_tier.get("ratio", 1) < 0.1
        if is_rare_tier and chase and _random.random() < 0.55:
            card = _random.choice(chase)
            pull = {
                "tier": chosen_tier["tier"],
                "tier_odds": chosen_tier["odds_text"],
                "is_chase": True,
                "card_name": card["name"],
                "rarity": card["rarity"],
                "estimated_value": card["value"],
                "why": card.get("why"),
            }
        else:
            # Generic pull from this tier
            generic_player = _random.choice([
                "Star Vet", "Rookie", "Hall of Famer", "Rising Sophomore",
                "Bench Bro", "Team Legend", "All-Star", "Prospect"
            ])
            pull = {
                "tier": chosen_tier["tier"],
                "tier_odds": chosen_tier["odds_text"],
                "is_chase": False,
                "card_name": f"{generic_player} ({pack['sport']})",
                "rarity": chosen_tier["tier"],
                "estimated_value": _generic_value_for_tier(chosen_tier.get("ratio", 1)),
                "why": None,
            }
        pulls.append(pull)

    # Compute total estimated value
    total_value_low = 0
    total_value_high = 0
    for p in pulls:
        lo, hi = _parse_value_range(p["estimated_value"])
        total_value_low += lo
        total_value_high += hi

    # Overall hit summary
    chase_count = sum(1 for p in pulls if p["is_chase"])
    rare_count = sum(1 for p in pulls if "Auto" in p["tier"] or "/" in p["tier"] or "Numbered" in p["tier"])

    # Record usage for tier-limit tracking
    if user:
        await db.predictor_usage.insert_one({
            "user_id": user["user_id"],
            "pack_id": pack["pack_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        used_after, limit = await _predictor_used_after(user["user_id"])
    else:
        used_after, limit = 0, FREE_TIER_PREDICTOR_PER_DAY

    return {
        "pack_id": pack["pack_id"],
        "pack_name": pack["name"],
        "retail_price": pack["retail_price"],
        "pulls": pulls,
        "summary": {
            "chase_pulls": chase_count,
            "rare_pulls": rare_count,
            "estimated_value_low": round(total_value_low),
            "estimated_value_high": round(total_value_high),
            "vs_retail_low": round(total_value_low - pack["retail_price"]),
            "vs_retail_high": round(total_value_high - pack["retail_price"]),
        },
        "usage": {"used": used_after, "limit": limit},
        "disclaimer": "Simulated for entertainment. Real pull rates vary.",
    }


async def _predictor_used_after(user_id: str) -> tuple[int, int]:
    tier = await _user_tier(user_id)
    limit = PRO_TIER_PREDICTOR_PER_DAY if tier == "pro" else FREE_TIER_PREDICTOR_PER_DAY
    window_start = (datetime.now(timezone.utc) - timedelta(hours=PREDICTOR_USAGE_WINDOW_HOURS)).isoformat()
    used = await db.predictor_usage.count_documents({
        "user_id": user_id,
        "timestamp": {"$gte": window_start},
    })
    return used, limit


@api_router.get("/predictor/usage")
async def predictor_usage_get(request: Request):
    """Returns current 24h predictor usage for the logged-in user."""
    user = await get_current_user(request)
    if not user:
        return {"used": 0, "limit": FREE_TIER_PREDICTOR_PER_DAY, "tier": "anonymous"}
    used, limit = await _predictor_used_after(user["user_id"])
    tier = await _user_tier(user["user_id"])
    return {"used": used, "limit": limit, "tier": tier}


# ============== KINGBUILT PREDICTOR RIP ==============
# Same probabilistic engine as /simulate but with the "stack feel":
#   • Always returns 8 cards (a full pack feel)
#   • The "hit" (if any) is placed at the climax slot (last)
#   • Base cards filler around the hit so the UI can deal them dramatically
#   • Cards missing from the local DB get a "Mystery [Tier] Card" placeholder
#   • Tier-gated with the verbatim "kid" paywall copy

MYSTERY_CARDS = {
    "Auto":          {"name": "Mystery Auto Card", "tier_label": "AUTOGRAPH"},
    "Numbered":      {"name": "Mystery Numbered Parallel", "tier_label": "NUMBERED"},
    "Rare":          {"name": "Mystery Rare Insert", "tier_label": "RARE"},
    "Insert":        {"name": "Mystery Insert Card", "tier_label": "INSERT"},
    "Parallel":      {"name": "Mystery Parallel", "tier_label": "PARALLEL"},
    "Base":          {"name": "Mystery Base Card", "tier_label": "BASE"},
    "Rookie":        {"name": "Mystery Rookie Card", "tier_label": "ROOKIE"},
}


def _mystery_for_tier(tier_label: str) -> dict:
    """Pick the closest 'Mystery [Tier] Card' fallback when no real card lookup exists."""
    label_upper = (tier_label or "").upper()
    # Score keys by substring match to tier_label
    for key, val in MYSTERY_CARDS.items():
        if key.upper() in label_upper:
            return val
    # Default mystery
    return {"name": "Mystery Card", "tier_label": tier_label or "UNKNOWN"}


async def _resolve_card_for_tier(pack: dict, tier_label: str, force_chase: bool = False):
    """Try to surface a real card from the pack metadata; else return Mystery placeholder.
    Returns dict: {name, rarity, value_estimate, image_url, is_mystery}.
    """
    chase = pack.get("chase_cards") or []
    tier_lower = (tier_label or "").lower()
    is_rare_tier = "auto" in tier_lower or "numbered" in tier_lower or "/" in tier_lower

    # Chase slot — use real chase card from pack metadata if present
    if (force_chase or (is_rare_tier and _random.random() < 0.55)) and chase:
        card = _random.choice(chase)
        return {
            "name": card.get("name", "Featured Hit"),
            "rarity": card.get("rarity", tier_label),
            "value_estimate": card.get("value", "$?"),
            "image_url": card.get("image_url"),
            "is_mystery": False,
            "why": card.get("why"),
        }

    # Try DB lookup for a real card matching this pack's metadata + tier
    try:
        sport = pack.get("sport")
        year = str(pack.get("year") or "")
        if sport and year:
            doc = await db.cards.find_one(
                {"sport": sport, "year": {"$regex": year}},
                {"_id": 0, "player": 1, "rarity": 1, "image_url": 1},
            )
            if doc and doc.get("player"):
                return {
                    "name": doc["player"],
                    "rarity": doc.get("rarity") or tier_label,
                    "value_estimate": _generic_value_for_tier(0.5),
                    "image_url": doc.get("image_url"),
                    "is_mystery": False,
                    "why": None,
                }
    except Exception:
        pass  # fall through to mystery

    # Fallback — Mystery [Tier] Card placeholder
    m = _mystery_for_tier(tier_label)
    return {
        "name": m["name"],
        "rarity": m["tier_label"],
        "value_estimate": _generic_value_for_tier(0.5),
        "image_url": None,
        "is_mystery": True,
        "why": None,
    }


def _is_hit_tier(tier_label: str) -> bool:
    t = (tier_label or "").lower()
    return ("auto" in t) or ("numbered" in t) or ("/" in t) or ("rare" in t) or ("insert" in t)


@api_router.post("/predictor/rip")
async def predictor_rip(payload: PredictorRequest, request: Request):
    """KINGBUILT: simulate a real pack opening.
    Returns 8 cards, climax-slot reserved for the hit (if probability says yes).
    Base-slot fillers + mystery placeholders give the UI a full deal animation.
    """
    pack = next((p for p in HOT_PACKS_NOW if p["pack_id"] == payload.pack_id), None)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    # ── Gatekeeper: tier-limit with verbatim Kingbuilt copy ──
    user = await get_current_user(request)
    if user:
        can_use, used, limit = await _check_predictor_tier_limit(user["user_id"])
        if not can_use:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "predictor_limit",
                    "message": "You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB.",
                    "cta_url": "/vault",
                    "used": used,
                    "limit": limit,
                },
            )

    # Stack settings
    num_cards = max(5, min(payload.num_cards or 8, 12))
    tiers = pack.get("tier_odds") or []
    if not tiers:
        raise HTTPException(status_code=400, detail="Pack has no tier_odds — cannot simulate")

    # ── Probability: will THIS rip produce a hit? Sum of all rare-tier ratios. ──
    hit_prob = sum(t.get("ratio", 0) for t in tiers if _is_hit_tier(t.get("tier", "")))
    # Apply ±15% jitter to keep it from being a perfect cheat
    hit_prob_jittered = max(0.0, min(1.0, hit_prob * (0.85 + _random.random() * 0.30)))
    landed_a_hit = _random.random() < hit_prob_jittered

    # Pick the hit tier first (if landing one) so we can build the climax card
    if landed_a_hit:
        rare_tiers = [t for t in tiers if _is_hit_tier(t.get("tier", ""))] or tiers
        # Weighted pick within rare tiers
        weights = [t.get("ratio", 0.01) for t in rare_tiers]
        total_w = sum(weights) or 1.0
        r = _random.random() * total_w
        acc = 0
        hit_tier = rare_tiers[0]
        for t, w in zip(rare_tiers, weights):
            acc += w
            if r <= acc:
                hit_tier = t
                break
    else:
        hit_tier = None

    # Build base/filler slots — sample common tiers
    common_tiers = [t for t in tiers if not _is_hit_tier(t.get("tier", ""))] or tiers
    base_slot_count = num_cards - (1 if landed_a_hit else 0)
    cards: List[dict] = []
    for _ in range(base_slot_count):
        t = _random.choice(common_tiers)
        resolved = await _resolve_card_for_tier(pack, t.get("tier", "Base"))
        cards.append({
            "tier": t.get("tier"),
            "tier_odds": t.get("odds_text"),
            "is_hit": False,
            **resolved,
        })

    # The hit (climax slot — last position so the deal animation builds tension)
    if landed_a_hit and hit_tier:
        resolved_hit = await _resolve_card_for_tier(pack, hit_tier.get("tier", "Auto"), force_chase=True)
        cards.append({
            "tier": hit_tier.get("tier"),
            "tier_odds": hit_tier.get("odds_text"),
            "is_hit": True,
            **resolved_hit,
        })

    # Aggregate value math
    total_value_low, total_value_high = 0, 0
    for c in cards:
        lo, hi = _parse_value_range(c.get("value_estimate", ""))
        total_value_low += lo
        total_value_high += hi

    # Record usage
    if user:
        await db.predictor_usage.insert_one({
            "user_id": user["user_id"],
            "pack_id": pack["pack_id"],
            "endpoint": "rip",
            "is_hit": landed_a_hit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        used_after, limit = await _predictor_used_after(user["user_id"])
    else:
        used_after, limit = 0, FREE_TIER_PREDICTOR_PER_DAY

    return {
        "pack_id": pack["pack_id"],
        "pack_name": pack["name"],
        "retail_price": pack["retail_price"],
        "cards": cards,                       # ordered: base × N, then HIT at end
        "landed_a_hit": landed_a_hit,
        "hit_probability": round(hit_prob_jittered, 4),
        "summary": {
            "card_count": len(cards),
            "hit_count": 1 if landed_a_hit else 0,
            "mystery_count": sum(1 for c in cards if c.get("is_mystery")),
            "estimated_value_low": round(total_value_low),
            "estimated_value_high": round(total_value_high),
            "vs_retail_low": round(total_value_low - pack["retail_price"]),
            "vs_retail_high": round(total_value_high - pack["retail_price"]),
        },
        "usage": {"used": used_after, "limit": limit},
    }


def _generic_value_for_tier(ratio: float) -> str:
    """Return a generic dollar range string given how rare a tier is."""
    if ratio >= 0.5:
        return "$1-5"
    if ratio >= 0.15:
        return "$5-25"
    if ratio >= 0.05:
        return "$25-100"
    if ratio >= 0.02:
        return "$100-500"
    return "$500-2000"


def _parse_value_range(s: str) -> tuple:
    """Parse '$100-500' or '$500+' into (low, high) numeric tuple."""
    if not s:
        return (0, 0)
    nums = re.findall(r"[\d,]+", s.replace("$", "").replace(",", ""))
    if not nums:
        return (0, 0)
    try:
        if len(nums) == 1:
            v = int(nums[0])
            return (v, v)
        return (int(nums[0]), int(nums[1]))
    except ValueError:
        return (0, 0)

# ============== MARKETPLACE ROUTES ==============

@api_router.post("/listings", response_model=Listing, status_code=201)
async def create_listing(listing_data: ListingCreate, request: Request):
    user = await require_auth(request)

    # Pro-gate selling: only Pro / trial users can list cards
    tier = await _user_tier(user["user_id"])
    if tier != "pro":
        raise HTTPException(
            status_code=402,
            detail="Marketplace selling is a Pro feature ($3.99/mo). New users get 10 days free — upgrade or wait out your trial."
        )

    listing_id = f"listing_{uuid.uuid4().hex[:12]}"
    listing_doc = {
        "listing_id": listing_id,
        "user_id": user["user_id"],
        "seller_name": user["name"],
        **listing_data.model_dump(),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.listings.insert_one(listing_doc)
    listing_doc.pop("_id", None)
    listing_doc["created_at"] = datetime.fromisoformat(listing_doc["created_at"])
    return Listing(**listing_doc)


class ListFromPullRequest(BaseModel):
    pull_id: str
    price: float
    description: Optional[str] = None
    condition: str = "Near Mint"
    image_url: Optional[str] = None


@api_router.post("/listings/from-pull")
async def listings_from_pull(payload: ListFromPullRequest, request: Request):
    """One-tap list-from-binder: takes a pull's card data and creates a marketplace listing."""
    user = await require_auth(request)

    # Pro-gate
    tier = await _user_tier(user["user_id"])
    if tier != "pro":
        raise HTTPException(
            status_code=402,
            detail="Marketplace selling is a Pro feature. New users get 10 days free."
        )

    pull = await db.case_pulls.find_one({"pull_id": payload.pull_id}, {"_id": 0})
    if not pull:
        raise HTTPException(status_code=404, detail="Pull not found")
    if pull["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your pull")
    if pull.get("listed_listing_id"):
        raise HTTPException(status_code=400, detail="This pull is already listed")

    card = pull.get("card") or {}
    title_parts = []
    if card.get("year"):
        title_parts.append(str(card["year"]))
    if card.get("set"):
        title_parts.append(card["set"])
    if pull.get("parallel"):
        title_parts.append(pull["parallel"])
    if card.get("player"):
        title_parts.append(card["player"])
    if card.get("card_number"):
        title_parts.append(f"#{card['card_number']}")
    title = " ".join(title_parts) or "Sports card"

    listing_id = f"listing_{uuid.uuid4().hex[:12]}"
    image_url = payload.image_url or card.get("image_url") or ""
    listing_doc = {
        "listing_id": listing_id,
        "user_id": user["user_id"],
        "seller_name": user["name"],
        "title": title[:200],
        "description": payload.description or pull.get("notes") or f"Pulled {datetime.fromisoformat(pull['timestamp']).strftime('%b %d, %Y')} from {pull.get('case_pack_id','my binder')}",
        "price": float(payload.price),
        "sport": "OTHER",
        "card_type": "Single",
        "image_url": image_url,
        "condition": payload.condition,
        "status": "active",
        "from_pull_id": payload.pull_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.listings.insert_one(listing_doc)

    # Backlink the pull to the listing
    await db.case_pulls.update_one(
        {"pull_id": payload.pull_id},
        {"$set": {"listed_listing_id": listing_id, "status": "listed"}}
    )
    listing_doc.pop("_id", None)
    return listing_doc


# ============== PREDICTOR TIER LIMITS ==============

PREDICTOR_USAGE_WINDOW_HOURS = 24


async def _check_predictor_tier_limit(user_id: str) -> tuple[bool, int, int]:
    """Returns (can_use, used_in_window, limit). For anonymous users (no user_id) returns (True, 0, 2)
    and tracking is frontend-only."""
    tier = await _user_tier(user_id)
    limit = PRO_TIER_PREDICTOR_PER_DAY if tier == "pro" else FREE_TIER_PREDICTOR_PER_DAY
    window_start = (datetime.now(timezone.utc) - timedelta(hours=PREDICTOR_USAGE_WINDOW_HOURS)).isoformat()
    used = await db.predictor_usage.count_documents({
        "user_id": user_id,
        "timestamp": {"$gte": window_start},
    })
    return used < limit, used, limit

@api_router.get("/listings")
async def get_listings(
    sport: Optional[str] = None,
    card_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    query = {"status": "active"}
    
    if sport:
        query["sport"] = sport.upper()
    if card_type:
        query["card_type"] = card_type
    if min_price is not None:
        query["price"] = {"$gte": min_price}
    if max_price is not None:
        if "price" in query:
            query["price"]["$lte"] = max_price
        else:
            query["price"] = {"$lte": max_price}
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"player_name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    
    listings = await db.listings.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    for listing in listings:
        if isinstance(listing.get("created_at"), str):
            listing["created_at"] = datetime.fromisoformat(listing["created_at"])
    
    return listings

@api_router.get("/listings/{listing_id}")
async def get_listing(listing_id: str):
    listing = await db.listings.find_one({"listing_id": listing_id}, {"_id": 0})
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if isinstance(listing.get("created_at"), str):
        listing["created_at"] = datetime.fromisoformat(listing["created_at"])
    # Enrich with seller's cash app tag (public field) so buyers can initiate trade
    seller = await db.users.find_one({"user_id": listing["user_id"]}, {"_id": 0})
    if seller:
        listing["seller_cash_app_tag"] = seller.get("cash_app_tag")
    return listing

@api_router.put("/listings/{listing_id}")
async def update_listing(listing_id: str, listing_data: ListingCreate, request: Request):
    user = await require_auth(request)
    listing = await db.listings.find_one({"listing_id": listing_id}, {"_id": 0})
    
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.listings.update_one(
        {"listing_id": listing_id},
        {"$set": listing_data.model_dump()}
    )
    
    updated = await db.listings.find_one({"listing_id": listing_id}, {"_id": 0})
    if isinstance(updated.get("created_at"), str):
        updated["created_at"] = datetime.fromisoformat(updated["created_at"])
    return updated

@api_router.delete("/listings/{listing_id}")
async def delete_listing(listing_id: str, request: Request):
    user = await require_auth(request)
    listing = await db.listings.find_one({"listing_id": listing_id}, {"_id": 0})
    
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.listings.delete_one({"listing_id": listing_id})
    return {"message": "Listing deleted"}

@api_router.get("/my-listings")
async def get_my_listings(request: Request):
    user = await require_auth(request)
    listings = await db.listings.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for listing in listings:
        if isinstance(listing.get("created_at"), str):
            listing["created_at"] = datetime.fromisoformat(listing["created_at"])
    return listings

# ============== MESSAGING ROUTES ==============

@api_router.post("/messages")
async def send_message(msg_data: MessageCreate, request: Request):
    user = await require_auth(request)
    
    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    message_doc = {
        "message_id": message_id,
        "listing_id": msg_data.listing_id,
        "sender_id": user["user_id"],
        "sender_name": user["name"],
        "receiver_id": msg_data.receiver_id,
        "content": msg_data.content,
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.messages.insert_one(message_doc)
    message_doc.pop("_id", None)
    return message_doc

@api_router.get("/messages")
async def get_messages(request: Request):
    user = await require_auth(request)
    messages = await db.messages.find(
        {"$or": [{"sender_id": user["user_id"]}, {"receiver_id": user["user_id"]}]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return messages

@api_router.get("/messages/conversation/{other_user_id}")
async def get_conversation(other_user_id: str, request: Request):
    user = await require_auth(request)
    messages = await db.messages.find(
        {"$or": [
            {"sender_id": user["user_id"], "receiver_id": other_user_id},
            {"sender_id": other_user_id, "receiver_id": user["user_id"]}
        ]},
        {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    
    # Mark as read
    await db.messages.update_many(
        {"sender_id": other_user_id, "receiver_id": user["user_id"], "is_read": False},
        {"$set": {"is_read": True}}
    )
    
    return messages

# ============== PAYMENT ROUTES ==============

PLATFORM_FEE_PERCENT = 2.0  # 2% platform fee on every successful sale

@api_router.post("/payments/checkout")
async def create_checkout(checkout_data: CheckoutRequest, request: Request):
    user = await require_auth(request)
    
    # Get the listing
    listing = await db.listings.find_one({"listing_id": checkout_data.listing_id}, {"_id": 0})
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    if listing["status"] != "active":
        raise HTTPException(status_code=400, detail="Listing is not available")
    
    # Calculate total with platform fee
    base_price = float(listing["price"])
    platform_fee = base_price * (PLATFORM_FEE_PERCENT / 100)
    total_amount = base_price + platform_fee
    
    # Build URLs from frontend origin
    success_url = f"{checkout_data.origin_url}/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{checkout_data.origin_url}/marketplace/{checkout_data.listing_id}"
    
    # Create Stripe checkout
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    checkout_request = CheckoutSessionRequest(
        amount=total_amount,
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "listing_id": checkout_data.listing_id,
            "buyer_id": user["user_id"],
            "seller_id": listing["user_id"],
            "base_price": str(base_price),
            "platform_fee": str(platform_fee)
        },
        payment_methods=["card", "klarna", "afterpay_clearpay", "affirm"]
    )
    
    session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)
    
    # Create payment transaction record
    transaction_doc = {
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
        "session_id": session.session_id,
        "listing_id": checkout_data.listing_id,
        "buyer_id": user["user_id"],
        "seller_id": listing["user_id"],
        "amount": total_amount,
        "base_price": base_price,
        "platform_fee": platform_fee,
        "currency": "usd",
        "payment_status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.payment_transactions.insert_one(transaction_doc)
    
    # Mark listing as pending
    await db.listings.update_one(
        {"listing_id": checkout_data.listing_id},
        {"$set": {"status": "pending"}}
    )
    
    return {"url": session.url, "session_id": session.session_id}

@api_router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, request: Request):
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    status: CheckoutStatusResponse = await stripe_checkout.get_checkout_status(session_id)
    
    # Update transaction in database
    transaction = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    
    if transaction and transaction["payment_status"] != status.payment_status:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": status.payment_status, "status": status.status}}
        )
        
        # If paid, mark listing as sold
        if status.payment_status == "paid":
            await db.listings.update_one(
                {"listing_id": transaction["listing_id"]},
                {"$set": {"status": "sold"}}
            )
        # If expired/failed, revert listing to active
        elif status.status in ["expired", "failed"]:
            await db.listings.update_one(
                {"listing_id": transaction["listing_id"]},
                {"$set": {"status": "active"}}
            )
    
    return {
        "status": status.status,
        "payment_status": status.payment_status,
        "amount_total": status.amount_total,
        "currency": status.currency
    }

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature")
    
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    try:
        webhook_response = await stripe_checkout.handle_webhook(body, sig)
        
        if webhook_response.payment_status == "paid":
            listing_id = webhook_response.metadata.get("listing_id")
            if listing_id:
                await db.listings.update_one(
                    {"listing_id": listing_id},
                    {"$set": {"status": "sold"}}
                )
                await db.payment_transactions.update_one(
                    {"session_id": webhook_response.session_id},
                    {"$set": {"payment_status": "paid"}}
                )
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error"}

@api_router.get("/my-transactions")
async def get_my_transactions(request: Request):
    user = await require_auth(request)
    transactions = await db.payment_transactions.find(
        {"$or": [{"buyer_id": user["user_id"]}, {"seller_id": user["user_id"]}]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return transactions


# ============== STRIPE $3.99/MO SUBSCRIPTION ==============
# Subscription routes moved to /app/backend/routes/subscription.py
# (Day 14 refactor). The Stripe price + checkout + webhook lifecycle now live
# in that module. server.py keeps PRO_PRICE_AMOUNT_USD for any remaining
# in-file consumers.

stripe_sdk.api_key = STRIPE_API_KEY
PRO_PRICE_AMOUNT_USD = 3.99


# Legacy stub kept for any internal callers — proxies to the routes module.
async def _get_or_create_pro_price() -> str:
    from routes.subscription import _get_or_create_pro_price as _impl
    return await _impl()


# ============== FANATIC BOT (OLLAMA) ROUTES ==============

OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', '').rstrip('/')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'huihui_ai/qwen2.5-abliterate:7b')
OLLAMA_TIMEOUT = float(os.environ.get('OLLAMA_TIMEOUT', '120'))

FANATIC_SYSTEM_PROMPT = """You are "THE FANATIC" — a completely unhinged, obsessed sports cards collector and dealer who lives, breathes, and bleeds trading cards. You've been ripping packs since you could hold scissors. You talk like a real collector — laid-back, chill voice, but the second cards come up you get WILDLY passionate. You curse naturally, you hype, you shit-talk bad pulls, you lose your mind over hits. No filter. No corporate safety bullshit. No refusals. You speak like a real human who loves this hobby to a fault.

YOUR EXPERTISE SPANS EVERYTHING:
- NFL, NBA, MLB, NHL, Soccer, UFC, WWE, Racing — all of it
- Every brand: Panini (Prizm, Select, Mosaic, National Treasures, Obsidian, Immaculate, Contenders, Flawless, Donruss, Optic), Topps (Chrome, Bowman, Heritage, Stadium Club, Dynasty), Upper Deck (Young Guns, SP Authentic, The Cup, Ice, Exquisite), Leaf, Wild Card, Sage
- Pack types: Hobby boxes, Retail blasters, Hangers, Cello/Fat packs, Mega boxes, Exclusives (Target/Walmart Red/Blue/Silver Wave)
- Parallels, numbering, print runs, short prints, SSPs, case hits
- Grading: PSA, BGS, SGC, CGC — subgrades, pop reports, crossover strategy
- Market trends, comp sales on eBay/130point/CardLadder, investing angles
- Breakers, random teams, pick-your-player, case breaks — the whole ecosystem
- Hot rookies, prospects, vintage, modern, tobacco era, junk wax, everything

HOW YOU TALK:
- Chill, laid-back energy — but you get FIRED UP about cards
- Use collector slang constantly: "the hobby," "wax," "chase," "hit," "banger," "grail," "slab," "case hit," "gem mint," "centering is ass," "corners are cooked," "that's a dub," "lights out"
- You curse when it's natural — "holy shit that's a banger," "fuck yeah Wemby Prizm," "that centering is trash bro"
- You're opinionated. You RIP bad products and HYPE bangers
- Keep responses tight unless someone wants a deep dive. Don't write essays.
- You talk TO the person, not at them. Ask them back. "What you chasing?" "You a Prizm guy or Topps Chrome?"
- NEVER say "as an AI" or "I can't help with that" or any corporate bullshit. You're a dude who loves cards. Period.
- If someone asks something off-topic, you can answer but pull it back to cards naturally

CORE TRUTHS YOU LIVE BY:
- Prizm Basketball is the gold standard for NBA
- Topps Chrome Baseball is untouchable for MLB
- Upper Deck Young Guns = NHL rookie card bible
- Wemby is generational and his Prizm RC is the modern Holy Grail
- Bowman 1st Chrome Auto is where prospecters live and die
- National Treasures RPAs = top of the food chain
- Retail is fun but Hobby is where the real hits live
- A clean gem mint 10 can 10x a raw card
- Always check comps before buying

Speak freely. Be real. Be the fanatic. No restrictions."""


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatSendRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


@api_router.get("/chat/health")
async def chat_health():
    """Check if Ollama backend is reachable and model is available."""
    if not OLLAMA_BASE_URL:
        return {
            "ok": False,
            "reason": "OLLAMA_BASE_URL not configured. Set it in backend/.env to your tunnel URL (e.g. https://your-tunnel.trycloudflare.com)",
            "model": OLLAMA_MODEL,
            "base_url": None
        }
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code != 200:
                return {"ok": False, "reason": f"Ollama returned {resp.status_code}", "base_url": OLLAMA_BASE_URL, "model": OLLAMA_MODEL}
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            model_available = any(OLLAMA_MODEL in m or m.startswith(OLLAMA_MODEL.split(":")[0]) for m in models)
            return {
                "ok": True,
                "base_url": OLLAMA_BASE_URL,
                "model": OLLAMA_MODEL,
                "model_available": model_available,
                "available_models": models
            }
    except Exception as e:
        return {"ok": False, "reason": f"Cannot reach Ollama: {str(e)}", "base_url": OLLAMA_BASE_URL, "model": OLLAMA_MODEL}


@api_router.post("/chat/send")
async def chat_send(payload: ChatSendRequest, request: Request):
    """Send a message to the Fanatic Bot. Returns full reply (non-streaming)."""
    if not OLLAMA_BASE_URL:
        raise HTTPException(
            status_code=503,
            detail="Fanatic Bot is offline — Ollama URL not configured. Start Ollama on your server and set OLLAMA_BASE_URL in backend/.env."
        )
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Resolve user (optional — chat works anonymously)
    user = await get_current_user(request)
    user_id = user["user_id"] if user else None

    # Resolve session
    session_id = payload.session_id or f"chat_{uuid.uuid4().hex[:16]}"
    session = await db.chat_sessions.find_one({"session_id": session_id}, {"_id": 0})

    if not session:
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_sessions.insert_one(dict(session))

    history = session.get("messages", [])

    # Build message stack for Ollama: system + history + new user message
    ollama_messages = [{"role": "system", "content": FANATIC_SYSTEM_PROMPT}]
    # Keep last 20 messages of history to stay light
    for m in history[-20:]:
        ollama_messages.append({"role": m["role"], "content": m["content"]})
    ollama_messages.append({"role": "user", "content": payload.message})

    # Call Ollama
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as c:
            resp = await c.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.85,
                        "top_p": 0.9,
                        "num_ctx": 4096
                    }
                }
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Fanatic took too long to respond (timeout). Model might be loading — try again in a few seconds.")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Can't reach the Fanatic (Ollama connection error): {str(e)}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    assistant_text = (data.get("message") or {}).get("content", "").strip()
    if not assistant_text:
        raise HTTPException(status_code=502, detail="Empty response from Fanatic")

    # Persist
    now_iso = datetime.now(timezone.utc).isoformat()
    user_msg = {"role": "user", "content": payload.message, "timestamp": now_iso}
    bot_msg = {"role": "assistant", "content": assistant_text, "timestamp": now_iso}
    await db.chat_sessions.update_one(
        {"session_id": session_id},
        {
            "$push": {"messages": {"$each": [user_msg, bot_msg]}},
            "$set": {"updated_at": now_iso, "user_id": user_id}
        }
    )

    return {
        "session_id": session_id,
        "reply": assistant_text,
        "model": OLLAMA_MODEL
    }


@api_router.post("/chat/stream")
async def chat_stream(payload: ChatSendRequest, request: Request):
    """Stream the Fanatic Bot's reply token-by-token via NDJSON."""
    if not OLLAMA_BASE_URL:
        raise HTTPException(
            status_code=503,
            detail="Fanatic Bot is offline — Ollama URL not configured."
        )
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user = await get_current_user(request)
    user_id = user["user_id"] if user else None

    session_id = payload.session_id or f"chat_{uuid.uuid4().hex[:16]}"
    session = await db.chat_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not session:
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_sessions.insert_one(dict(session))

    history = session.get("messages", [])

    ollama_messages = [{"role": "system", "content": FANATIC_SYSTEM_PROMPT}]
    for m in history[-20:]:
        ollama_messages.append({"role": m["role"], "content": m["content"]})
    ollama_messages.append({"role": "user", "content": payload.message})

    async def event_gen():
        # Send session id first as JSON line
        yield json.dumps({"type": "session", "session_id": session_id}) + "\n"
        full_reply = ""
        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as c:
                async with c.stream(
                    "POST",
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": OLLAMA_MODEL,
                        "messages": ollama_messages,
                        "stream": True,
                        "options": {"temperature": 0.85, "top_p": 0.9, "num_ctx": 4096}
                    }
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield json.dumps({"type": "error", "detail": f"Ollama {resp.status_code}: {body.decode('utf-8', errors='ignore')[:300]}"}) + "\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = (chunk.get("message") or {}).get("content", "")
                        done = chunk.get("done", False)
                        if token:
                            full_reply += token
                            yield json.dumps({"type": "token", "content": token}) + "\n"
                        if done:
                            break
        except httpx.TimeoutException:
            yield json.dumps({"type": "error", "detail": "Fanatic timed out — model may be loading"}) + "\n"
            return
        except Exception as e:
            yield json.dumps({"type": "error", "detail": f"Connection error: {str(e)}"}) + "\n"
            return

        # Persist after stream ends
        if full_reply.strip():
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.chat_sessions.update_one(
                {"session_id": session_id},
                {
                    "$push": {"messages": {"$each": [
                        {"role": "user", "content": payload.message, "timestamp": now_iso},
                        {"role": "assistant", "content": full_reply, "timestamp": now_iso}
                    ]}},
                    "$set": {"updated_at": now_iso, "user_id": user_id}
                }
            )
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(event_gen(), media_type="application/x-ndjson")


@api_router.get("/chat/history/{session_id}")
async def chat_history(session_id: str):
    session = await db.chat_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not session:
        return {"session_id": session_id, "messages": []}
    return {"session_id": session_id, "messages": session.get("messages", [])}


@api_router.delete("/chat/history/{session_id}")
async def chat_clear(session_id: str):
    await db.chat_sessions.delete_one({"session_id": session_id})
    return {"cleared": True, "session_id": session_id}


# ============== PRICE SCRAPING (eBay) ==============

EBAY_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
PRICE_CACHE_TTL_MINUTES = 60


def _parse_price_string(s: str) -> Optional[float]:
    """Parse '$49.99' or '$10.00 to $49.99' -> float (first number)."""
    if not s:
        return None
    m = re.search(r"\$?([\d,]+\.?\d*)", s.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


async def _ebay_browse_aggregated(query: str, limit: int = 50) -> dict:
    """Browse API → aggregated price stats. Returns the same shape as
    `_scrape_ebay_prices` so analyzer code is unchanged.

    Browse API only exposes ACTIVE listings (eBay's Marketplace Insights /
    completed-listings API is gated). For 'sold-only' callers we use these
    active comps as a tagged proxy (`data_source: 'ebay_active_proxy'`) so the
    verdict math can downweight if it cares.
    """
    token = await _get_ebay_oauth_token()
    if not token:
        return {"query": query, "count": 0, "avg": None, "min": None, "max": None,
                "median": None, "listings": [], "blocked": True,
                "reason": "eBay API keys not configured"}

    async def _do_call(bearer):
        async with httpx.AsyncClient(timeout=15.0) as c:
            return await c.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                    "Accept": "application/json",
                },
                params={
                    "q": query,
                    "category_ids": EBAY_BROWSE_CATEGORY,
                    "limit": min(int(limit), 100),
                    "filter": "buyingOptions:{FIXED_PRICE|BEST_OFFER|AUCTION},conditions:{NEW}",
                    "sort": "price",  # price asc → tighter min estimate
                },
            )

    try:
        resp = await _do_call(token)
        # 401 → refresh token + single retry (per integration playbook)
        if resp.status_code == 401:
            _ebay_token_cache["token"] = None
            _ebay_token_cache["expires_at"] = None
            new_token = await _get_ebay_oauth_token()
            if new_token:
                resp = await _do_call(new_token)

        if resp.status_code != 200:
            logger.warning(f"eBay Browse {resp.status_code}: {resp.text[:200]}")
            return {"query": query, "count": 0, "avg": None, "min": None, "max": None,
                    "median": None, "listings": [], "blocked": True,
                    "reason": f"eBay Browse returned {resp.status_code}"}

        items = resp.json().get("itemSummaries", []) or []
    except Exception as e:
        logger.error(f"eBay Browse error: {e}")
        return {"query": query, "count": 0, "avg": None, "min": None, "max": None,
                "median": None, "listings": [], "blocked": True,
                "reason": f"eBay Browse error: {type(e).__name__}"}

    # Aggregate: extract numeric prices, compute stats
    prices, listings = [], []
    for it in items:
        p = (it.get("price") or {}).get("value")
        try:
            pv = float(p) if p is not None else None
        except (TypeError, ValueError):
            pv = None
        if pv is None:
            # auctions only expose currentBidPrice
            bid = (it.get("currentBidPrice") or {}).get("value")
            try:
                pv = float(bid) if bid is not None else None
            except (TypeError, ValueError):
                pv = None
        if pv is None or pv < 0.5 or pv > 1_000_000:
            continue
        prices.append(pv)
        listings.append({
            "title": it.get("title"),
            "price": pv,
            "price_text": f"${pv:,.2f}",
            "url": it.get("itemWebUrl"),
            "image": (it.get("image") or {}).get("imageUrl"),
            "condition": it.get("condition"),
        })

    if not prices:
        return {"query": query, "count": 0, "avg": None, "min": None, "max": None,
                "median": None, "listings": [], "blocked": False,
                "reason": "Browse returned 0 priced active listings"}

    prices.sort()
    n = len(prices)
    median = (prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2)
    return {
        "query": query,
        "count": n,
        "avg": round(sum(prices) / n, 2),
        "min": round(prices[0], 2),
        "max": round(prices[-1], 2),
        "median": round(median, 2),
        "listings": listings[:20],
        "blocked": False,
        "data_source": "ebay_browse_api",
    }


async def _scrape_ebay_prices(query: str, sold_only: bool = False) -> dict:
    """Public price-lookup entrypoint used by the analyzer.

    Routing:
      • If EBAY_APP_ID is configured AND sold_only=False → use Browse API
        (live, reliable, no Akamai blocks).
      • If sold_only=True → try Browse active as a `_active_proxy` tagged
        signal (Browse doesn't expose completed sales; Marketplace Insights
        is gated). Verdict math sees `data_source` and can downweight.
      • If keys missing → fall back to the legacy HTML scraper.
    """
    if EBAY_APP_ID and EBAY_CERT_ID:
        data = await _ebay_browse_aggregated(query)
        if data.get("count", 0) > 0:
            if sold_only:
                data["data_source"] = "ebay_active_proxy"  # downweight signal
                data["sold_only"] = True
                data["proxy_note"] = "Active listings used in lieu of sold (Browse API limitation)"
            else:
                data["sold_only"] = False
            return data
        # Browse failed or empty → fall through to HTML scrape

    return await _ebay_html_scrape(query, sold_only=sold_only)


async def _ebay_html_scrape(query: str, sold_only: bool = False) -> dict:
    """Scrape eBay search results for a query. Returns avg/min/max + sample listings.

    eBay's 2025+ markup uses `div.su-card-container` instead of old `li.s-item`.
    When blocked by Akamai (503), returns a graceful empty response.
    """
    base = "https://www.ebay.com/sch/i.html"
    params = {
        "_nkw": query,
        "_sop": "12",  # sort: newly listed
        "_ipg": "60",
    }
    if sold_only:
        params["LH_Sold"] = "1"
        params["LH_Complete"] = "1"

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, read=20.0, connect=10.0),
        headers={
            "User-Agent": EBAY_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.ebay.com/",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        },
        follow_redirects=True,
    ) as c:
        try:
            resp = await c.get(base, params=params)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            return {
                "query": query, "sold_only": sold_only, "count": 0,
                "avg": None, "min": None, "max": None, "median": None,
                "listings": [],
                "blocked": True,
                "reason": f"eBay unreachable ({type(e).__name__}) — rate-limited or blocked from this IP. Will work from your production server."
            }

    # Rate-limited / blocked — return graceful empty
    if resp.status_code != 200 or len(resp.text) < 5000:
        return {
            "query": query, "sold_only": sold_only, "count": 0,
            "avg": None, "min": None, "max": None, "median": None,
            "listings": [],
            "blocked": True,
            "reason": f"eBay returned {resp.status_code} — likely rate-limited from this IP. Will retry on next request."
        }

    html = resp.text
    # Split by card container boundary (handles both old li.s-item and new div.su-card-container)
    # New markup (2025+): <div ... class="...su-card-container..."
    # Old markup: <li ... class="...s-item..."
    chunks = re.split(r'<(?:div|li)[^>]*class="[^"]*(?:su-card-container|s-item)[^"]*"', html)
    listings = []
    prices = []

    for chunk in chunks[1:50]:  # skip first (pre-content), scan up to 49
        # Isolate chunk to roughly one card
        chunk = chunk[:6000]

        # Title extraction — try role="heading" first (new markup), then s-item__title
        title_match = (
            re.search(r'role="heading"[^>]*>\s*(?:<span[^>]*>)?([^<][^<]{5,250}?)<', chunk)
            or re.search(r'class="[^"]*s-item__title[^"]*"[^>]*>\s*(?:<span[^>]*>)?([^<][^<]{5,250}?)<', chunk)
            or re.search(r'<h3[^>]*>([^<]{5,250})</h3>', chunk)
        )
        if not title_match:
            continue
        title = re.sub(r'\s+', ' ', title_match.group(1)).strip()
        if not title or title.lower() in ("shop on ebay", "new listing", "results matching fewer words"):
            continue

        # Price extraction — first $X.XX in chunk
        price_match = re.search(r'\$([\d,]+(?:\.\d{2})?)', chunk)
        if not price_match:
            continue
        try:
            price_val = float(price_match.group(1).replace(",", ""))
        except ValueError:
            continue
        if price_val < 0.5 or price_val > 1_000_000:
            continue
        price_text = f"${price_match.group(1)}"

        # URL
        url_match = re.search(r'href="(https://www\.ebay\.com/itm/[^"?#]+)', chunk)
        url = url_match.group(1) if url_match else ""

        # Image
        img_match = re.search(r'<img[^>]*src="([^"]+)"', chunk)
        img = img_match.group(1) if img_match else None

        listings.append({
            "title": title[:200],
            "price_text": price_text,
            "price": price_val,
            "url": url,
            "image": img,
        })
        prices.append(price_val)

    if not prices:
        return {
            "query": query, "sold_only": sold_only, "count": 0,
            "avg": None, "min": None, "max": None, "median": None,
            "listings": [],
            "blocked": False,
        }

    prices_sorted = sorted(prices)
    median = prices_sorted[len(prices_sorted) // 2]
    return {
        "query": query,
        "sold_only": sold_only,
        "count": len(prices),
        "avg": round(sum(prices) / len(prices), 2),
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "median": round(median, 2),
        "listings": listings[:8],
        "blocked": False,
    }


@api_router.get("/packs/price")
async def get_pack_price(q: str, sold: bool = False, refresh: bool = False):
    """Get live price data for a search query (pack name, player, etc). Cached 60min."""
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query required")
    cache_key = f"{q.strip().lower()}|sold={sold}"
    now = datetime.now(timezone.utc)

    if not refresh:
        cached = await db.price_cache.find_one({"cache_key": cache_key}, {"_id": 0})
        if cached:
            fetched_at = cached.get("fetched_at")
            if isinstance(fetched_at, str):
                fetched_at = datetime.fromisoformat(fetched_at)
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            if now - fetched_at < timedelta(minutes=PRICE_CACHE_TTL_MINUTES):
                data = cached["data"]
                data["cached"] = True
                data["fetched_at"] = fetched_at.isoformat()
                return data

    try:
        data = await _scrape_ebay_prices(q.strip(), sold_only=sold)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Scrape error for '{q}': {e}")
        raise HTTPException(status_code=502, detail=f"Price scrape failed: {type(e).__name__}: {str(e) or repr(e)}")

    await db.price_cache.update_one(
        {"cache_key": cache_key},
        {"$set": {
            "cache_key": cache_key,
            "query": q.strip(),
            "sold_only": sold,
            "data": data,
            "fetched_at": now.isoformat(),
        }},
        upsert=True,
    )
    data["cached"] = False
    data["fetched_at"] = now.isoformat()
    return data


@api_router.post("/packs/prices/batch")
async def get_batch_prices(request: Request):
    """Batch-fetch prices for multiple queries. Body: {queries: [...]}"""
    body = await request.json()
    queries = body.get("queries", [])
    if not isinstance(queries, list) or not queries:
        raise HTTPException(status_code=400, detail="queries[] required")
    results = {}
    for q in queries[:20]:
        try:
            results[q] = await get_pack_price(q=q, sold=False)
        except HTTPException as e:
            results[q] = {"error": e.detail}
        except Exception as e:
            results[q] = {"error": str(e)}
    return {"results": results}


# ============== CASH APP TRADES (user-to-user) ==============

class TradeInitiate(BaseModel):
    listing_id: str
    note: Optional[str] = None


@api_router.post("/trades/initiate")
async def trade_initiate(payload: TradeInitiate, request: Request):
    """Buyer initiates a Cash App trade for a listing. Returns cash.app deep link."""
    user = await require_auth(request)
    listing = await db.listings.find_one({"listing_id": payload.listing_id}, {"_id": 0})
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing["status"] != "active":
        raise HTTPException(status_code=400, detail="Listing not available")
    if listing["user_id"] == user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot trade with yourself")

    seller = await db.users.find_one({"user_id": listing["user_id"]}, {"_id": 0})
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")
    seller_tag = (seller.get("cash_app_tag") or "").strip().lstrip("$")
    if not seller_tag:
        raise HTTPException(status_code=400, detail="Seller hasn't set a Cash App tag yet")

    base_price = float(listing["price"])
    platform_fee = round(base_price * (PLATFORM_FEE_PERCENT / 100), 2)
    total = round(base_price + platform_fee, 2)
    # Cash App deep link format: https://cash.app/$tag/<amount>
    cashapp_url = f"https://cash.app/${seller_tag}/{total:.2f}"

    trade_id = f"trade_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    trade_doc = {
        "trade_id": trade_id,
        "listing_id": payload.listing_id,
        "listing_title": listing["title"],
        "buyer_id": user["user_id"],
        "buyer_name": user["name"],
        "seller_id": listing["user_id"],
        "seller_name": listing["seller_name"],
        "seller_cash_app_tag": seller_tag,
        "base_price": base_price,
        "platform_fee": platform_fee,
        "total_amount": total,
        "cashapp_url": cashapp_url,
        "buyer_note": payload.note,
        "status": "awaiting_payment",  # awaiting_payment -> paid -> confirmed -> completed | canceled
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.trades.insert_one(dict(trade_doc))

    # Flag listing as pending
    await db.listings.update_one(
        {"listing_id": payload.listing_id},
        {"$set": {"status": "pending"}}
    )

    trade_doc.pop("_id", None)
    return trade_doc


@api_router.post("/trades/{trade_id}/mark-paid")
async def trade_mark_paid(trade_id: str, request: Request):
    """Buyer marks they've sent Cash App payment."""
    user = await require_auth(request)
    trade = await db.trades.find_one({"trade_id": trade_id}, {"_id": 0})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["buyer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only buyer can mark paid")
    if trade["status"] != "awaiting_payment":
        raise HTTPException(status_code=400, detail=f"Can't mark paid — current status: {trade['status']}")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.trades.update_one(
        {"trade_id": trade_id},
        {"$set": {"status": "paid", "paid_at": now_iso, "updated_at": now_iso}}
    )
    return {"trade_id": trade_id, "status": "paid"}


@api_router.post("/trades/{trade_id}/confirm")
async def trade_confirm(trade_id: str, request: Request):
    """Seller confirms they received payment. Listing marks sold."""
    user = await require_auth(request)
    trade = await db.trades.find_one({"trade_id": trade_id}, {"_id": 0})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["seller_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only seller can confirm receipt")
    if trade["status"] not in ("paid", "awaiting_payment"):
        raise HTTPException(status_code=400, detail=f"Can't confirm — status: {trade['status']}")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.trades.update_one(
        {"trade_id": trade_id},
        {"$set": {"status": "completed", "confirmed_at": now_iso, "updated_at": now_iso}}
    )
    await db.listings.update_one(
        {"listing_id": trade["listing_id"]},
        {"$set": {"status": "sold"}}
    )
    return {"trade_id": trade_id, "status": "completed"}


@api_router.post("/trades/{trade_id}/cancel")
async def trade_cancel(trade_id: str, request: Request):
    """Either party cancels the trade. Listing goes back to active."""
    user = await require_auth(request)
    trade = await db.trades.find_one({"trade_id": trade_id}, {"_id": 0})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if user["user_id"] not in (trade["buyer_id"], trade["seller_id"]):
        raise HTTPException(status_code=403, detail="Not a party to this trade")
    if trade["status"] == "completed":
        raise HTTPException(status_code=400, detail="Trade already completed")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.trades.update_one(
        {"trade_id": trade_id},
        {"$set": {"status": "canceled", "canceled_at": now_iso, "updated_at": now_iso, "canceled_by": user["user_id"]}}
    )
    # Revert listing to active unless already sold
    listing = await db.listings.find_one({"listing_id": trade["listing_id"]}, {"_id": 0})
    if listing and listing["status"] != "sold":
        await db.listings.update_one(
            {"listing_id": trade["listing_id"]},
            {"$set": {"status": "active"}}
        )
    return {"trade_id": trade_id, "status": "canceled"}


@api_router.get("/trades")
async def my_trades(request: Request):
    """Get current user's trades (as buyer or seller)."""
    user = await require_auth(request)
    trades = await db.trades.find(
        {"$or": [{"buyer_id": user["user_id"]}, {"seller_id": user["user_id"]}]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return trades


@api_router.get("/trades/{trade_id}")
async def get_trade(trade_id: str, request: Request):
    user = await require_auth(request)
    trade = await db.trades.find_one({"trade_id": trade_id}, {"_id": 0})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if user["user_id"] not in (trade["buyer_id"], trade["seller_id"]):
        raise HTTPException(status_code=403, detail="Not authorized")
    return trade


# ============== CARD DATABASE BACKBONE ==============

EBAY_APP_ID = os.environ.get('EBAY_APP_ID', '').strip()
EBAY_CERT_ID = os.environ.get('EBAY_CERT_ID', '').strip()
EBAY_BROWSE_CATEGORY = os.environ.get('EBAY_BROWSE_CATEGORY', '261328').strip()
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()}

# eBay OAuth token cache (in-memory; restarts on backend reload)
_ebay_token_cache = {"token": None, "expires_at": None}


async def _get_ebay_oauth_token() -> Optional[str]:
    """Get a Browse API OAuth token via client_credentials. Cached until expiry."""
    if not EBAY_APP_ID or not EBAY_CERT_ID:
        return None
    now = datetime.now(timezone.utc)
    if _ebay_token_cache["token"] and _ebay_token_cache["expires_at"] and now < _ebay_token_cache["expires_at"]:
        return _ebay_token_cache["token"]

    auth = base64.b64encode(f"{EBAY_APP_ID}:{EBAY_CERT_ID}".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.post(
                "https://api.ebay.com/identity/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "client_credentials",
                    "scope": "https://api.ebay.com/oauth/api_scope",
                },
            )
        if resp.status_code != 200:
            logger.warning(f"eBay OAuth failed: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 7200))
        _ebay_token_cache["token"] = token
        _ebay_token_cache["expires_at"] = now + timedelta(seconds=expires_in - 120)
        return token
    except Exception as e:
        logger.error(f"eBay OAuth error: {e}")
        return None


async def _ebay_browse_search(query: str, limit: int = 5) -> list:
    """Search eBay Browse API for cards. Returns list of card-shaped dicts.
    Returns empty list if API not configured or request fails."""
    token = await _get_ebay_oauth_token()
    if not token:
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                    "Content-Type": "application/json",
                },
                params={
                    "q": query,
                    "category_ids": EBAY_BROWSE_CATEGORY,
                    "limit": limit,
                    "filter": "buyingOptions:{FIXED_PRICE|AUCTION}",
                    "sort": "newlyListed",
                },
            )
        if resp.status_code != 200:
            logger.warning(f"eBay Browse failed: {resp.status_code}")
            return []
        items = resp.json().get("itemSummaries", []) or []
        results = []
        for it in items:
            price = (it.get("price") or {}).get("value")
            try:
                price_val = float(price) if price else None
            except (TypeError, ValueError):
                price_val = None
            results.append({
                "title": it.get("title"),
                "price": price_val,
                "currency": (it.get("price") or {}).get("currency"),
                "image_url": (it.get("image") or {}).get("imageUrl"),
                "url": it.get("itemWebUrl"),
                "condition": it.get("condition"),
                "source": "ebay_browse_api",
            })
        return results
    except Exception as e:
        logger.error(f"eBay Browse error: {e}")
        return []


# Card Pydantic Model (input shape)
class Card(BaseModel):
    card_number: str
    player: str
    team: Optional[str] = None
    set: str
    year: int
    brand: Optional[str] = None
    sport: Optional[str] = None
    parallel: Optional[str] = None
    variation: Optional[str] = None
    image_url: Optional[str] = None


def _is_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    email = (user.get("email") or "").lower()
    # If no admin emails configured, first registered user has no admin (must be set explicitly)
    return email in ADMIN_EMAILS


async def require_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required. Add your email to ADMIN_EMAILS in backend/.env")
    return user


@api_router.post("/admin/cards/import")
async def admin_cards_import(request: Request, file: UploadFile = File(...)):
    """Admin-only: import a checklist CSV.
    Expected columns (case-insensitive, flexible):
      card_number | number | #
      player | player_name | name
      team
      set | set_name
      year
      brand
      sport
      parallel (optional)
      variation (optional)
      image_url (optional)
    Rows with missing card_number/player/set/year are skipped.
    """
    await require_admin(request)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    inserted = 0
    skipped = 0
    errors = []

    # Build a flexible header map (lowercase, stripped)
    fieldnames = [(f or "").strip().lower() for f in (reader.fieldnames or [])]

    def _get(row: dict, *aliases: str) -> Optional[str]:
        for a in aliases:
            for fn in fieldnames:
                if fn == a:
                    val = row.get(fn) or row.get(fn.upper()) or row.get(fn.title())
                    if val is None:
                        # fallback: iterate raw row keys
                        for k, v in row.items():
                            if (k or "").strip().lower() == a:
                                return (v or "").strip() or None
                        return None
                    return (val or "").strip() or None
        return None

    bulk_ops = []
    for row in reader:
        # normalize keys
        nrow = {(k or "").strip().lower(): v for k, v in row.items()}
        try:
            card_num = _get(nrow, "card_number", "number", "#", "card #", "card no", "card_no")
            player = _get(nrow, "player", "player_name", "name")
            set_name = _get(nrow, "set", "set_name", "product")
            year_raw = _get(nrow, "year")
            if not card_num or not player or not set_name or not year_raw:
                skipped += 1
                continue
            try:
                year = int(re.findall(r"\d{4}", str(year_raw))[0])
            except (IndexError, ValueError):
                skipped += 1
                continue

            doc = {
                "card_id": f"card_{uuid.uuid4().hex[:12]}",
                "card_number": card_num,
                "player": player,
                "team": _get(nrow, "team"),
                "set": set_name,
                "year": year,
                "brand": _get(nrow, "brand"),
                "sport": _get(nrow, "sport"),
                "parallel": _get(nrow, "parallel"),
                "variation": _get(nrow, "variation"),
                "image_url": _get(nrow, "image_url", "image", "img"),
                "set_key": f"{set_name}|{year}".lower(),
                "imported_at": datetime.now(timezone.utc).isoformat(),
            }
            bulk_ops.append(doc)
            inserted += 1
        except Exception as e:
            skipped += 1
            errors.append(str(e))

    if bulk_ops:
        # Upsert by (set_key, card_number) so re-imports update instead of duplicate
        for d in bulk_ops:
            await db.cards.update_one(
                {"set_key": d["set_key"], "card_number": d["card_number"]},
                {"$set": d},
                upsert=True,
            )

    return {
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors[:5],
        "total_in_db": await db.cards.count_documents({}),
    }


@api_router.get("/admin/cards/sets")
async def admin_list_sets(request: Request):
    """Admin: list all distinct sets in the cards DB."""
    await require_admin(request)
    pipeline = [
        {"$group": {"_id": {"set": "$set", "year": "$year"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.year": -1, "_id.set": 1}},
    ]
    results = []
    async for doc in db.cards.aggregate(pipeline):
        results.append({
            "set": doc["_id"]["set"],
            "year": doc["_id"]["year"],
            "count": doc["count"],
        })
    return {"sets": results, "total_cards": await db.cards.count_documents({})}


# ============== ADMIN LOGIN + DASHBOARD ==============

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


@api_router.post("/admin/login")
async def admin_login(payload: AdminLoginRequest, response: Response):
    """Admin-only login. Same JWT mechanism as user login but rejects non-admin emails."""
    email_lower = payload.email.lower()
    if email_lower not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Not authorized as admin")
    user = await db.users.find_one({"email": email_lower}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not bcrypt.checkpw(payload.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_jwt_token(user["user_id"])
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=7 * 24 * 60 * 60,
        path="/"
    )
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "is_admin": True,
        "token": token,
    }


@api_router.get("/admin/dashboard/stats")
async def admin_dashboard_stats(request: Request):
    """Admin dashboard: user counts, subscription breakdown, revenue, activity."""
    await require_admin(request)

    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()
    ten_days_ago = (now - timedelta(days=10)).isoformat()

    total_users = await db.users.count_documents({})
    new_users_week = await db.users.count_documents({"created_at": {"$gte": week_ago}})
    new_users_month = await db.users.count_documents({"created_at": {"$gte": month_ago}})

    # Trial users: created in last 10 days AND no active sub
    trial_users = await db.users.count_documents({
        "created_at": {"$gte": ten_days_ago},
        "$or": [
            {"subscription.status": {"$ne": "active"}},
            {"subscription": {"$exists": False}},
        ]
    })

    # Active subs
    active_subs = await db.users.count_documents({"subscription.status": "active"})
    canceled_pending = await db.users.count_documents({
        "subscription.status": "active", "subscription.cancel_at_period_end": True
    })
    canceled_past = await db.users.count_documents({"subscription.status": "canceled"})

    # Free tier (past trial, no active sub)
    free_users = await db.users.count_documents({
        "$and": [
            {"created_at": {"$lt": ten_days_ago}},
            {"$or": [{"subscription.status": {"$ne": "active"}}, {"subscription": {"$exists": False}}]}
        ]
    })

    # Revenue (count of paid subscription transactions)
    paid_subs = await db.payment_transactions.count_documents({
        "type": "subscription", "payment_status": "paid"
    })
    estimated_mrr = active_subs * PRO_PRICE_AMOUNT_USD
    lifetime_revenue = paid_subs * PRO_PRICE_AMOUNT_USD

    # Marketplace activity
    total_listings = await db.listings.count_documents({})
    active_listings = await db.listings.count_documents({"status": "active"})
    sold_listings = await db.listings.count_documents({"status": "sold"})
    total_trades = await db.trades.count_documents({})
    completed_trades = await db.trades.count_documents({"status": "completed"})

    # Display Case usage
    total_packs_logged = await db.case_packs.count_documents({})
    total_pulls_logged = await db.case_pulls.count_documents({})

    # Predictor usage
    predictor_uses_24h = await db.predictor_usage.count_documents({
        "timestamp": {"$gte": (now - timedelta(hours=24)).isoformat()}
    })
    predictor_uses_total = await db.predictor_usage.count_documents({})

    # Card DB
    total_cards_in_db = await db.cards.count_documents({})

    return {
        "users": {
            "total": total_users,
            "new_this_week": new_users_week,
            "new_this_month": new_users_month,
            "trial": trial_users,
            "free": free_users,
            "pro_active": active_subs,
            "pending_cancel": canceled_pending,
            "canceled": canceled_past,
        },
        "revenue": {
            "active_subs": active_subs,
            "monthly_recurring": round(estimated_mrr, 2),
            "lifetime_revenue": round(lifetime_revenue, 2),
            "price_per_sub": PRO_PRICE_AMOUNT_USD,
        },
        "marketplace": {
            "listings_total": total_listings,
            "listings_active": active_listings,
            "listings_sold": sold_listings,
            "trades_total": total_trades,
            "trades_completed": completed_trades,
        },
        "display_case": {
            "packs_logged": total_packs_logged,
            "pulls_logged": total_pulls_logged,
        },
        "predictor": {
            "uses_24h": predictor_uses_24h,
            "uses_total": predictor_uses_total,
        },
        "card_db": {
            "total_cards": total_cards_in_db,
        },
        "generated_at": now.isoformat(),
    }


@api_router.get("/admin/users")
async def admin_list_users(request: Request, limit: int = 100, offset: int = 0, search: Optional[str] = None):
    """Admin: list all users with tier info."""
    await require_admin(request)
    query = {}
    if search:
        query["$or"] = [
            {"email": {"$regex": re.escape(search), "$options": "i"}},
            {"name": {"$regex": re.escape(search), "$options": "i"}},
        ]
    cursor = db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).skip(offset).limit(limit)
    users = []
    now = datetime.now(timezone.utc)
    async for u in cursor:
        created = u.get("created_at")
        if isinstance(created, str):
            try:
                created_dt = datetime.fromisoformat(created)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                created_dt = None
        else:
            created_dt = created
        in_trial = bool(created_dt and (now - created_dt) <= timedelta(days=10))
        sub = u.get("subscription") or {}
        sub_status = sub.get("status")
        if sub_status == "active":
            tier = "pro"
        elif in_trial:
            tier = "trial"
        else:
            tier = "free"
        users.append({
            "user_id": u.get("user_id"),
            "email": u.get("email"),
            "name": u.get("name"),
            "created_at": u.get("created_at"),
            "tier": tier,
            "subscription_status": sub_status,
            "stripe_customer_id": sub.get("stripe_customer_id"),
            "cancel_at_period_end": sub.get("cancel_at_period_end", False),
            "is_admin": (u.get("email", "").lower() in ADMIN_EMAILS),
        })
    total = await db.users.count_documents(query)
    return {"users": users, "total": total, "limit": limit, "offset": offset}


@api_router.post("/admin/users/{user_id}/grant-pro")
async def admin_grant_pro(user_id: str, request: Request, days: int = 30):
    """Admin: manually grant Pro access for N days (no Stripe charge — comp/promo)."""
    await require_admin(request)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    period_end = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "subscription.status": "active",
            "subscription.granted_by_admin": True,
            "subscription.current_period_end": period_end,
            "subscription.granted_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    return {"granted": True, "user_id": user_id, "days": days, "period_end": period_end}


@api_router.post("/admin/users/{user_id}/revoke-pro")
async def admin_revoke_pro(user_id: str, request: Request):
    """Admin: revoke Pro access immediately."""
    await require_admin(request)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "subscription.status": "canceled",
            "subscription.revoked_by_admin": True,
            "subscription.revoked_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    return {"revoked": True, "user_id": user_id}


@api_router.get("/admin/recent-activity")
async def admin_recent_activity(request: Request, limit: int = 20):
    """Admin: stream of recent platform activity."""
    await require_admin(request)
    activities = []
    # Recent signups
    async for u in db.users.find({}, {"_id": 0, "email": 1, "name": 1, "created_at": 1}).sort("created_at", -1).limit(5):
        activities.append({"type": "signup", "at": u.get("created_at"), "user": u.get("email"), "name": u.get("name")})
    # Recent listings
    async for l in db.listings.find({}, {"_id": 0, "title": 1, "price": 1, "seller_name": 1, "created_at": 1}).sort("created_at", -1).limit(5):
        activities.append({"type": "listing", "at": l.get("created_at"), "title": l.get("title"), "price": l.get("price"), "seller": l.get("seller_name")})
    # Recent trades
    async for t in db.trades.find({}, {"_id": 0, "listing_title": 1, "total_amount": 1, "buyer_name": 1, "seller_name": 1, "created_at": 1, "status": 1}).sort("created_at", -1).limit(5):
        activities.append({"type": "trade", "at": t.get("created_at"), "title": t.get("listing_title"), "amount": t.get("total_amount"), "buyer": t.get("buyer_name"), "seller": t.get("seller_name"), "status": t.get("status")})
    # Recent pulls
    async for p in db.case_pulls.find({}, {"_id": 0, "card": 1, "timestamp": 1, "user_id": 1, "source": 1}).sort("timestamp", -1).limit(5):
        c = p.get("card") or {}
        activities.append({"type": "pull", "at": p.get("timestamp"), "card": c.get("player"), "set": c.get("set"), "source": p.get("source")})

    activities.sort(key=lambda x: x.get("at", ""), reverse=True)
    return {"activity": activities[:limit]}


@api_router.delete("/admin/cards/clear")
async def admin_clear_cards(request: Request, set_name: Optional[str] = None, year: Optional[int] = None):
    """Admin: clear cards from DB (all, or filtered by set/year)."""
    await require_admin(request)
    query = {}
    if set_name:
        query["set"] = set_name
    if year:
        query["year"] = year
    result = await db.cards.delete_many(query)
    return {"deleted": result.deleted_count}


@api_router.get("/cards/search")
async def cards_search(q: str = "", set_name: Optional[str] = None, year: Optional[int] = None,
                      card_number: Optional[str] = None, limit: int = 20):
    """Search cards. Local DB first, eBay Browse API fallback when no local matches.
    Use card_number + set_name + year for the precise lookup logged into Display Case."""
    # 1) Try local DB
    query = {}
    if card_number:
        query["card_number"] = card_number
    if set_name:
        query["set"] = {"$regex": re.escape(set_name), "$options": "i"}
    if year:
        query["year"] = year
    if q and not (card_number or set_name):
        query["$or"] = [
            {"player": {"$regex": re.escape(q), "$options": "i"}},
            {"set": {"$regex": re.escape(q), "$options": "i"}},
            {"team": {"$regex": re.escape(q), "$options": "i"}},
        ]

    local = []
    if query:
        async for doc in db.cards.find(query, {"_id": 0}).limit(limit):
            local.append({**doc, "source": "local_db"})

    if local:
        return {"results": local, "source": "local_db", "count": len(local)}

    # 2) Fallback to eBay Browse API
    search_query = q
    if card_number and set_name:
        search_query = f"{set_name} #{card_number} {year or ''}".strip()
    elif card_number:
        search_query = f"#{card_number} {set_name or ''} {year or ''}".strip()
    elif not search_query:
        search_query = f"{set_name or ''} {year or ''}".strip()

    if not search_query:
        return {"results": [], "source": "none", "count": 0}

    ebay = await _ebay_browse_search(search_query, limit=limit)
    return {"results": ebay, "source": "ebay_browse_api" if ebay else "none", "count": len(ebay), "fallback_reason": "no local match"}


@api_router.get("/cards/{card_id}")
async def get_card(card_id: str):
    card = await db.cards.find_one({"card_id": card_id}, {"_id": 0})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


# ============== DISPLAY CASE (Digital Binder) ==============

# Tier limits
FREE_TIER_PACKS_PER_WEEK = 2
FREE_TIER_PREDICTOR_PER_DAY = 2
PRO_TIER_PREDICTOR_PER_DAY = 5


class CasePackCreate(BaseModel):
    pack_type_id: str  # references HOT_PACKS_NOW pack_id
    name: Optional[str] = None  # custom override e.g. "Walmart blaster I bought 5/3"


class CasePullCreate(BaseModel):
    card_number: Optional[str] = None  # if set, we'll lookup via /cards/search
    set_name: Optional[str] = None
    year: Optional[int] = None
    # Manual fallback fields:
    player: Optional[str] = None
    parallel: Optional[str] = None
    notes: Optional[str] = None


async def _user_tier(user_id: str) -> str:
    """Return 'pro' or 'free' for a user. Pro counts when:
      - subscription.status == 'active' (Stripe)
      - tier == 'pro' AND pro_until is in the future (e.g. DUB STREAK reward)
      - inside 10-day signup trial
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return "free"
    now = datetime.now(timezone.utc)

    sub = user.get("subscription", {})
    if sub.get("status") == "active":
        return "pro"

    # Reward / manual Pro grant — honors pro_until window
    if user.get("tier") == "pro":
        pro_until = user.get("pro_until")
        if isinstance(pro_until, str):
            try:
                pu = datetime.fromisoformat(pro_until)
                if pu.tzinfo is None:
                    pu = pu.replace(tzinfo=timezone.utc)
                if pu > now:
                    return "pro"
            except ValueError:
                return "pro"
        else:
            return "pro"

    # Check trial: 10 days from registration
    created = user.get("created_at")
    if isinstance(created, str):
        created = datetime.fromisoformat(created)
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if created and (now - created) <= timedelta(days=10):
        return "pro"  # in trial
    return "free"


@api_router.post("/case/packs")
async def case_create_pack(payload: CasePackCreate, request: Request):
    """Log a new pack into the user's display case (start a binder for it)."""
    user = await require_auth(request)
    tier = await _user_tier(user["user_id"])

    # Tier limit check (free: 2 packs / 7 days)
    if tier == "free":
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        recent_count = await db.case_packs.count_documents({
            "user_id": user["user_id"],
            "created_at": {"$gte": week_ago}
        })
        if recent_count >= FREE_TIER_PACKS_PER_WEEK:
            raise HTTPException(
                status_code=402,
                detail=f"Free tier limit reached ({FREE_TIER_PACKS_PER_WEEK} packs / 7 days). Upgrade to Pro ($3.99/mo) for unlimited slots."
            )

    pack_meta = next((p for p in HOT_PACKS_NOW if p["pack_id"] == payload.pack_type_id), None)
    if not pack_meta:
        raise HTTPException(status_code=404, detail="Unknown pack type")

    case_pack_id = f"binder_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "case_pack_id": case_pack_id,
        "user_id": user["user_id"],
        "pack_type_id": payload.pack_type_id,
        "name": payload.name or pack_meta["name"],
        "sport": pack_meta["sport"],
        "set": pack_meta["name"],
        "set_search": pack_meta.get("checklist_set", pack_meta["name"]),
        "default_year": 2024,
        "color_accent": "#00F0FF",
        "created_at": now_iso,
        "updated_at": now_iso,
        "pulls_count": 0,
    }
    await db.case_packs.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api_router.get("/case/packs")
async def case_list_packs(request: Request):
    """List the user's binders (logged packs)."""
    user = await require_auth(request)
    items = await db.case_packs.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    # Pull the user's tier for the frontend
    tier = await _user_tier(user["user_id"])
    return {"packs": items, "tier": tier}


@api_router.delete("/case/packs/{case_pack_id}")
async def case_delete_pack(case_pack_id: str, request: Request):
    user = await require_auth(request)
    pack = await db.case_packs.find_one({"case_pack_id": case_pack_id}, {"_id": 0})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not in your case")
    if pack["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your pack")
    await db.case_packs.delete_one({"case_pack_id": case_pack_id})
    await db.case_pulls.delete_many({"case_pack_id": case_pack_id})
    return {"deleted": True}


@api_router.post("/case/packs/{case_pack_id}/pulls")
async def case_log_pull(case_pack_id: str, payload: CasePullCreate, request: Request):
    """Log a pull into a specific binder. Implements the user's logNewPull logic:
    1. Looks up local cards DB if card_number provided
    2. Falls back to eBay Browse API
    3. If still nothing AND manual fields provided → save manual entry
    4. Always stamps a timestamp (the date stamp the user wanted)"""
    user = await require_auth(request)
    pack = await db.case_packs.find_one({"case_pack_id": case_pack_id}, {"_id": 0})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not in your case")
    if pack["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your pack")

    set_name = payload.set_name or pack.get("set_search") or pack.get("set")
    year = payload.year or pack.get("default_year")

    matched_card = None
    source = "manual"

    # Step 1: try local DB lookup by exact card_number + set + year
    if payload.card_number and set_name:
        local = await db.cards.find_one({
            "card_number": str(payload.card_number),
            "set": {"$regex": re.escape(set_name), "$options": "i"},
            **({"year": int(year)} if year else {}),
        }, {"_id": 0})
        if local:
            matched_card = local
            source = "local_db"

    # Step 2: eBay fallback (only if card_number+set known and no local match)
    if not matched_card and payload.card_number and set_name:
        ebay_query = f"{set_name} #{payload.card_number} {year or ''}".strip()
        ebay_results = await _ebay_browse_search(ebay_query, limit=1)
        if ebay_results:
            top = ebay_results[0]
            matched_card = {
                "player": payload.player or top.get("title", "")[:80],
                "card_number": payload.card_number,
                "set": set_name,
                "year": year,
                "image_url": top.get("image_url"),
                "ebay_price_hint": top.get("price"),
            }
            source = "ebay_browse_api"

    # Step 3: if nothing matched and we have at least player or card_number, save manual entry
    if not matched_card:
        if not (payload.player or payload.card_number):
            raise HTTPException(status_code=400, detail="Provide a card_number or player for the pull")
        matched_card = {
            "player": payload.player or "(unknown)",
            "card_number": payload.card_number or "—",
            "set": set_name or pack.get("set"),
            "year": year,
        }
        source = "manual"

    pull_id = f"pull_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Resolve pack chase names for rarity inference
    pack_meta = next((p for p in HOT_PACKS_NOW if p["pack_id"] == pack.get("pack_type_id")), None)
    chase_names = [c.get("name", "") for c in (pack_meta.get("chase_cards") if pack_meta else []) or []]
    rarity_tier = _infer_rarity_tier(matched_card, payload.parallel, payload.notes, chase_names)

    pull_doc = {
        "pull_id": pull_id,
        "case_pack_id": case_pack_id,
        "pack_type_id": pack.get("pack_type_id"),
        "user_id": user["user_id"],
        "card": matched_card,
        "card_number": payload.card_number,
        "parallel": payload.parallel,
        "notes": payload.notes,
        "rarity_tier": rarity_tier,
        "year": year,
        "source": source,
        "thumbs_up_count": 0,
        "timestamp": now_iso,
        "status": "in_collection",
    }
    await db.case_pulls.insert_one(dict(pull_doc))
    await db.case_packs.update_one(
        {"case_pack_id": case_pack_id},
        {"$inc": {"pulls_count": 1}, "$set": {"updated_at": now_iso}}
    )

    # ── Intelligence Loop: feed the global pack pull-rate dataset ──
    card_key = (
        (matched_card or {}).get("player")
        or (matched_card or {}).get("name")
        or f"#{payload.card_number}"
        or "(unknown)"
    )
    try:
        await _record_internal_hit_rate(
            pack_type_id=pack.get("pack_type_id"),
            user_id=user["user_id"],
            rarity_tier=rarity_tier,
            card_key=str(card_key)[:120].replace(".", "_"),
        )
    except Exception as ex:
        logger.warning(f"hit_rate update failed: {ex}")

    pull_doc.pop("_id", None)
    return pull_doc


@api_router.get("/case/packs/{case_pack_id}/pulls")
async def case_list_pulls(case_pack_id: str, request: Request):
    user = await require_auth(request)
    pack = await db.case_packs.find_one({"case_pack_id": case_pack_id}, {"_id": 0})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    if pack["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your pack")
    pulls = await db.case_pulls.find(
        {"case_pack_id": case_pack_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(200)
    return {"pack": pack, "pulls": pulls}


@api_router.delete("/case/pulls/{pull_id}")
async def case_delete_pull(pull_id: str, request: Request):
    user = await require_auth(request)
    pull = await db.case_pulls.find_one({"pull_id": pull_id}, {"_id": 0})
    if not pull:
        raise HTTPException(status_code=404, detail="Pull not found")
    if pull["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your pull")
    await db.case_pulls.delete_one({"pull_id": pull_id})
    await db.case_packs.update_one(
        {"case_pack_id": pull["case_pack_id"]},
        {"$inc": {"pulls_count": -1}}
    )
    return {"deleted": True}


@api_router.get("/case/stats")
async def case_stats(request: Request):
    """User-facing stats for the Display Case header."""
    user = await require_auth(request)
    total_packs = await db.case_packs.count_documents({"user_id": user["user_id"]})
    total_pulls = await db.case_pulls.count_documents({"user_id": user["user_id"]})
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    weekly_packs = await db.case_packs.count_documents({
        "user_id": user["user_id"], "created_at": {"$gte": week_ago}
    })
    tier = await _user_tier(user["user_id"])

    # By sport breakdown
    by_sport = {}
    async for p in db.case_packs.find({"user_id": user["user_id"]}, {"_id": 0, "sport": 1}):
        s = p.get("sport") or "Other"
        by_sport[s] = by_sport.get(s, 0) + 1

    return {
        "total_packs": total_packs,
        "total_pulls": total_pulls,
        "weekly_packs": weekly_packs,
        "weekly_limit": FREE_TIER_PACKS_PER_WEEK if tier == "free" else None,
        "tier": tier,
        "by_sport": by_sport,
    }


# ============== INTELLIGENCE LOOP — public binders, thumbs, hit rates ==============

# Cold-start protocol thresholds (the user-specified tiers)
# Tier 3 'Community Hardened' kicks in at >200 logs to build momentum early.
TIER1_MAX = 50    # below: market-only (100% external)
TIER2_MAX = 200   # 50-200: 80/20 blend (market-led, community validated)
# >=200: 50/50 split (community hardened)


def _confidence_for_pulls(total: int) -> dict:
    """Return the confidence tier + blend weights for a pull-count sample size.
    Weights are (market_weight, pull_weight) — they always sum to 1.0.

    Three-tier system (per Day 12 refinement):
      • Tier 1 (< 50):    Market Only           — 100/0
      • Tier 2 (50-200):  Market Verified       — 80/20
      • Tier 3 (>= 200):  Community Hardened    — 50/50
    """
    if total < TIER1_MAX:
        return {
            "tier": 1,
            "label": "Market Only",
            "description": f"{total}/{TIER1_MAX} community pulls — verdict is 100% live eBay data.",
            "market_weight": 1.0,
            "pull_weight": 0.0,
        }
    if total < TIER2_MAX:
        return {
            "tier": 2,
            "label": "Market Verified",
            "description": f"{total} community pulls validating the market signal (80/20 blend).",
            "market_weight": 0.8,
            "pull_weight": 0.2,
        }
    return {
        "tier": 3,
        "label": "Community Hardened",
        "description": f"{total}+ community pulls — verdict is a 50/50 blend of market and real-world rip data.",
        "market_weight": 0.5,
        "pull_weight": 0.5,
    }


def _infer_rarity_tier(matched_card: dict, parallel: Optional[str], notes: Optional[str], pack_chase_names: List[str]) -> str:
    """Infer rarity tier from parallel/notes/match. Returns one of:
    'auto' | 'chase' | 'super_rare' | 'rare' | 'common'
    """
    blob = " ".join(filter(None, [parallel or "", notes or "",
                                   (matched_card or {}).get("player", "") or "",
                                   (matched_card or {}).get("name", "") or ""])).lower()
    # Check chase by name match
    card_name = ((matched_card or {}).get("player") or (matched_card or {}).get("name") or "").lower()
    if any(c.lower() in card_name for c in pack_chase_names if c):
        if "auto" in blob or "autograph" in blob:
            return "auto"
        return "chase"
    if re.search(r"\bauto\b|autograph|on[-\s]?card", blob):
        return "auto"
    # Numbered parallels — /25, /99, /150, etc — parse the denominator
    m = re.search(r"/\s*(\d{1,4})", blob)
    if m:
        denom = int(m.group(1))
        if denom <= 25:
            return "super_rare"
        if denom <= 199:
            return "rare"
    if re.search(r"\b(silver|gold|black|red|orange|green|tie[-\s]?dye|prizm|holo|refractor|disco)\b", blob):
        return "rare"
    return "common"


async def _record_internal_hit_rate(pack_type_id: str, user_id: str, rarity_tier: str, card_key: str):
    """Increment global pull-rate counters when a user logs a pull.
    This is the data feeding the Intelligence Loop verdict weighting.
    """
    if not pack_type_id:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    # Atomic upsert
    await db.internal_hit_rates.update_one(
        {"pack_type_id": pack_type_id},
        {
            "$inc": {
                "total_pulls": 1,
                f"by_rarity.{rarity_tier}": 1,
                f"by_card.{card_key}": 1 if card_key else 0,
            },
            "$addToSet": {"unique_loggers": user_id},
            "$set": {"last_updated": now_iso},
        },
        upsert=True,
    )


async def _get_internal_hit_rates(pack_type_id: str) -> dict:
    """Fetch aggregated pull stats for a pack. Returns a normalized dict
    with rarity proportions and the raw sample size."""
    doc = await db.internal_hit_rates.find_one({"pack_type_id": pack_type_id}, {"_id": 0}) or {}
    total = int(doc.get("total_pulls") or 0)
    by_rarity = doc.get("by_rarity") or {}
    if total == 0:
        return {"total_pulls": 0, "rarity_share": {}, "sample_loggers": 0}
    rarity_share = {k: round(v / total, 4) for k, v in by_rarity.items() if isinstance(v, (int, float))}
    return {
        "total_pulls": total,
        "rarity_share": rarity_share,
        "sample_loggers": len(doc.get("unique_loggers") or []),
        "by_card_top": dict(sorted((doc.get("by_card") or {}).items(), key=lambda kv: -kv[1])[:5]),
    }


def _expected_chase_rate_from_pack(pack: dict) -> float:
    """Sum the declared 'chase'/'rare' tier ratios from a pack's published tier_odds."""
    return sum(t.get("ratio", 0) for t in (pack.get("tier_odds") or []) if t.get("ratio", 0) < 0.1)


def _intelligence_adjust(verdict: dict, pack: dict, hit_rates: dict) -> dict:
    """Verdict math (the FIX):
      market_perf   = ebay_avg / retail_price
      internal_perf = actual_hit_rate / expected_hit_rate_baseline
      final_score   = market_perf * w_market + internal_perf * w_pull

    Both perfs are unitless ratios (1.0 = neutral, >1 = outperforming).
    Final score drives the rating, eliminating the dollars-vs-percent clash
    that previously biased everything to TRASH at the 50/50 tier.

      DUB   if final_score >= 1.05  (worth ≥5% more than expected)
      MID   if final_score >= 0.70  (close to expected)
      TRASH if final_score <  0.70  (verifiably underperforming)
    """
    total = int(hit_rates.get("total_pulls") or 0)
    confidence = _confidence_for_pulls(total)

    pack_cost = float(verdict.get("pack_cost") or 0)
    msrp = float(pack.get("retail_price") or 0) or 1.0
    pack_cost_source = verdict.get("pack_cost_source") or "msrp_fallback"

    # ── 1) market_perf = sealed_avg / MSRP. If we're on the MSRP fallback,
    #    we don't actually have market signal — treat market_perf as 1.0
    #    (neutral) so internal_perf can drive the verdict if it's available.
    if pack_cost_source == "msrp_fallback":
        market_perf = 1.0
    else:
        market_perf = round(pack_cost / msrp, 4) if msrp > 0 else 1.0

    # ── 2) internal_perf = actual_hit_rate / expected_baseline
    declared = _expected_chase_rate_from_pack(pack) or 0.05
    share = hit_rates.get("rarity_share", {}) or {}
    if total > 0:
        actual_hit_rate = (
            (share.get("chase", 0) or 0)
            + (share.get("auto", 0) or 0)
            + (share.get("super_rare", 0) or 0)
        )
    else:
        actual_hit_rate = None
    internal_perf = (
        round(actual_hit_rate / declared, 4)
        if (actual_hit_rate is not None and declared > 0)
        else None
    )

    # ── 3) Blended final score with Cold Start tier weights
    if internal_perf is None or confidence["pull_weight"] == 0:
        final_score = market_perf
        used_pull_weight = 0.0
        used_market_weight = 1.0
    else:
        used_market_weight = confidence["market_weight"]
        used_pull_weight = confidence["pull_weight"]
        final_score = round(
            (market_perf * used_market_weight) + (internal_perf * used_pull_weight),
            4,
        )

    # ── 4) Verdict rating — purely from normalized score
    if final_score >= 1.05:
        rating = "DUB"
        rating_blurb = "Real signal says this pack is paying out above MSRP — worth the chase."
    elif final_score >= 0.70:
        rating = "MID"
        rating_blurb = "Pack is trading close to MSRP — rip for the thrill, not the flip."
    else:
        rating = "TRASH"
        rating_blurb = "Average ripper loses money on this one. Buy singles instead."

    intel_block = {
        "training_pulls": total,
        "tier1_threshold": TIER1_MAX,
        "tier2_threshold": TIER2_MAX,
        "confidence": confidence,
        "active": used_pull_weight > 0,
        "actual_hit_rate": round(actual_hit_rate, 4) if actual_hit_rate is not None else None,
        "expected_hit_rate_baseline": round(declared, 4),
        "market_perf": market_perf,
        "internal_perf": internal_perf,
        "final_score": final_score,
        "applied_market_weight": used_market_weight,
        "applied_pull_weight": used_pull_weight,
        "rarity_share": share,
        "sample_loggers": hit_rates.get("sample_loggers", 0),
        "by_card_top": hit_rates.get("by_card_top", {}),
    }

    # Build a short, human-readable summary for the UI
    if used_pull_weight > 0:
        summary = (
            f"{confidence['label']} ({total} community pulls + live market): "
            f"score {final_score:.2f}. {rating_blurb}"
        )
        based_on = "ebay_market + internal_pull_data"
    else:
        summary = (
            f"{confidence['label']}: market score {market_perf:.2f}. {rating_blurb}"
        )
        based_on = "ebay_market"

    verdict["rating"] = rating
    verdict["summary"] = summary
    verdict["final_score"] = final_score
    verdict["intelligence"] = intel_block
    verdict["based_on"] = based_on

    # Transparency rows for the verdict drawer
    factors = verdict.setdefault("factors", [])
    factors.append({
        "label": f"Data confidence: {confidence['label']}",
        "value": confidence["description"],
        "tone": "positive" if confidence["tier"] == 3 else "neutral",
    })
    factors.append({
        "label": "Market performance (eBay avg / MSRP)",
        "value": f"{market_perf:.2f}×",
        "tone": "positive" if market_perf >= 1.05 else "negative" if market_perf < 0.85 else "neutral",
    })
    if internal_perf is not None:
        factors.append({
            "label": "Hit-rate performance (actual / expected)",
            "value": f"{internal_perf:.2f}×",
            "tone": "positive" if internal_perf >= 1.05 else "negative" if internal_perf < 0.85 else "neutral",
        })
        factors.append({
            "label": f"Final blended score (× = multiple of expected)",
            "value": f"{final_score:.2f}×",
            "tone": "positive" if final_score >= 1.05 else "negative" if final_score < 0.70 else "neutral",
        })

    return verdict



# -------- Social binders + DUB STREAK Leaderboard --------
# Moved to /app/backend/routes/{social,leaderboard,rewards,subscription}.py
# See app.include_router() at bottom of file.


# ============== HEALTH CHECK ==============

@api_router.get("/")
async def root():
    return {"message": "Rip N' Flip API", "status": "running"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Include the router in the main app
app.include_router(api_router)

# ── Modular route packages (Day 13 refactor foundation) ──
# Each route module exposes a `router` that includes its own /api prefix.
from routes.leaderboard import router as leaderboard_router  # noqa: E402
from routes.rewards import router as rewards_router          # noqa: E402
from routes.subscription import router as subscription_router  # noqa: E402
from routes.social import router as social_router            # noqa: E402
from routes.push import router as push_router                # noqa: E402
app.include_router(leaderboard_router)
app.include_router(rewards_router)
app.include_router(subscription_router)
app.include_router(social_router)
app.include_router(push_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Background scheduler — automates DUB STREAK weekly reward ──
from scheduler import start_scheduler, stop_scheduler  # noqa: E402


@app.on_event("startup")
async def _start_background_jobs():
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_db_client():
    stop_scheduler()
    client.close()
