# Rip N' Flip — PRD

## Original Problem Statement
High-energy sports cards platform for Play Store launch. Core: **Pack Analyzer** (DUB/MID/TRASH verdict engine powered by an **Intelligence Loop** that blends live eBay market data with aggregated user pull data via tiered confidence thresholds), **Pack Predictor** (probabilistic rip simulator), **Display Case** (3D digital binder with solitaire spread, public/private toggle, every logged pull trains the Analyzer), **Public Binder Gallery** (social view of public binders — source pack hidden, thumbs-up engagement), **Marketplace** (P2P with Cash App + 2% fee), **$3.99/mo Pro tier** (10-day free trial). Bot is **Jesse SLM 1.0** (deferred — social-media teaser only).

## Architecture
- **Backend:** FastAPI + MongoDB (motor), httpx for eBay + Ollama
- **Frontend:** React + CRACO + Tailwind + framer-motion + shadcn — GPU-tuned 3D animations with prefers-reduced-motion fallback
- **Auth:** JWT cookie + Emergent Google OAuth
- **Payments:** Cash App deep-link (manual settlement, 2% platform fee) + Stripe for $3.99/mo subscription
- **AI Bot:** Jesse SLM 1.0 deferred — bot will live on social media as teaser until v1 launches
- **Card data:** Hybrid — local `cards` MongoDB collection (CSV imported via admin) + eBay Browse API fallback (cat 261328)
- **Intelligence Loop:** `internal_hit_rates` MongoDB collection aggregates per-pack pull counts + rarity buckets + per-card counts. Used by `_intelligence_adjust` to re-weight verdict EV with real pull data once thresholds are met.

## V1 Sprint Status

### ✅ Day 1 — Rebrand + Homepage
Card Fanatic → **FLIP n' RIP** everywhere. New `Landing.js` with hero, "RIP · CHASE · FLIP · REPEAT" marquee, **WHAT'S HOT RIGHT NOW** live feed (`HotPacksFeed.js` pulling 8 curated packs + live eBay prices), feature grid w/ COMING SOON badges, $3.99/mo Pro promo. Bot rebadged JESSE SLM 1.0 — COMING SOON.

### ✅ Day 2 — Pack Analyzer (Verdict Engine)
`GET /api/analyzer/{pack_id}` scoring: live eBay sealed avg vs MSRP + chase grail count + sport/format modifiers → 0-100 score → DUB (≥70) / MID (45-69) / TRASH (<45). Frontend `Analyzer.js` with pack picker, big verdict card (color-coded), live market panel with sample listings, tier-odds bar chart, chase cards 4-up grid, deep-linkable `?pack=<id>`.

### ✅ Day 3 — Pack Predictor (Animated Rip)
`POST /api/predictor/simulate` — weighted random pulls from analyzer's `tier_odds` + ±15% jitter (intentionally not perfectly accurate). Frontend `Predictor.js` — pack picker → glowing RIP button → 📦 wobble animation → cards reveal one-by-one with framer-motion 3D flip → recap (chase pulls, rare/auto, est value, vs MSRP). Tier counter: 2/day free, 5/day Pro.

### ✅ Day 4 — Card Database Backbone
- `POST /api/admin/cards/import` — flexible CSV upload, upserts on (set+year+card_number)
- `GET /api/admin/cards/sets` — distinct sets with counts
- `DELETE /api/admin/cards/clear` — admin clears all/filtered
- `GET /api/cards/search` — local DB first → eBay Browse API fallback (OAuth2 client_credentials flow with token cache, category 261328)
- Admin gating via `ADMIN_EMAILS` env var
- Frontend `/admin` page with CSV upload, sets list, card search test
- `EBAY_APP_ID`, `EBAY_CERT_ID`, `EBAY_DEV_ID`, `EBAY_BROWSE_CATEGORY=261328` env placeholders

### ✅ Day 5-7 — Display Case (Digital Binder)
- `POST /api/case/packs` (creates binder, free-tier limit: 2/7 days, 402 paywall)
- `GET /api/case/packs` (lists binders + tier)
- `DELETE /api/case/packs/{id}` (cascades to pulls)
- `POST /api/case/packs/{id}/pulls` — implements user's `logNewPull` logic: local DB lookup → eBay fallback → manual entry. Always stamps timestamp.
- `GET /api/case/packs/{id}/pulls`
- `DELETE /api/case/pulls/{id}`
- `GET /api/case/stats`
- Frontend `DisplayCase.js`: 3D-styled binder grid with hover-tilt, color spine + glow per sport, tap → solitaire spread modal where pulls fan out with -58px overlap + per-card rotation + lift-on-hover, AddPack modal, LogPull modal with Card # + year + parallel + auto-search preview + manual fallback. Pull cards show source badge (DB/eBay/manual), date stamp, parallel highlight.

### Tier System
- Free: 2 packs/7 days, 2 predictor rips/day, can't sell in marketplace
- Pro ($3.99/mo): unlimited slots, 5 predictor rips/day, can sell in marketplace
- New users get **10-day automatic Pro trial** (`_user_tier` returns 'pro' if registered <10d ago)
- Backend tier-limit enforcement: free-tier pack creation past 2/week → 402 Payment Required with upgrade message

### ✅ Day 10-11 — PWA + Mobile Polish + Capacitor Android Wrap (2026-02-09)
- **PWA manifest** at `/manifest.json` — name, icons, shortcuts, dark theme color, standalone display
- **Service worker** at `/sw.js` — network-first navigations w/ offline fallback, stale-while-revalidate for static, bypass for `/api/`
- **Branded PWA icons** generated from PIL (cyan square + lightning + pink dot): 192/384/512 + maskable + apple-touch + favicon.ico
- **Offline page** (`/offline.html`) with neon Rip N' Flip branding + auto-reload on reconnect
- **iOS / Android meta tags**: `theme-color` (cyan light, dark night), `apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style: black-translucent`, OG tags + Twitter card
- **Mobile polish CSS** (`index.css`): safe-area insets via `env(safe-area-inset-*)`, 16px iOS input font (no zoom), 44px touch targets on mobile, `-webkit-tap-highlight-color: transparent`, `:focus-visible` outlines, brand selection color, overscroll-behavior fixes
- **Install prompt helper** (`/src/lib/pwa.js`) — exposes `registerSW()`, `onInstallAvailability()`, `promptInstall()`, `isStandalone()`. Wired to `index.js` + Navbar — shows "INSTALL APP" button only when `beforeinstallprompt` fires and not already installed
- **Capacitor 7 Android wrap** scaffolded — `capacitor.config.json` (`com.ripnflip.app`, dark splash, locked status bar), deps installed (`@capacitor/cli|core|android|app|status-bar|splash-screen` v7), `yarn android:add | sync | open | run` scripts, full build playbook at `/app/CAPACITOR_BUILD.md`
- **SEO/social**: `robots.txt`, OG image, Twitter card meta

### ✅ Day 12 — Brand Rename + Intelligence Loop + Social Binder (2026-02-11)
- **Brand rename**: FLIP n' RIP → **Rip N' Flip** everywhere — index.html, manifest, capacitor (`com.ripnflip.app`), sw, offline page, navbar, login/register, footers, API title, Stripe product name, PRD, test_credentials.
- **Landing redesign**: Analyzer-first hero — "WHAT SHOULD I RIP TODAY?" headline, huge circular green `#39FF14` ANALYZE button with pulse-ring, top 3 recommended packs preview, Intelligence Loop callout section, Public Binder Gallery peek section. Secondary tools (Predictor / Binder / Marketplace) demoted below the fold.
- **Intelligence Loop (backend)**: New `internal_hit_rates` collection. Every `POST /api/case/packs/{id}/pulls` increments per-pack totals + rarity buckets + by_card counts via `_record_internal_hit_rate`. Rarity inferred via `_infer_rarity_tier` from parallel/notes/chase-name match.
- **Cold Start Protocol**: `_confidence_for_pulls(total)` returns 4 tiers — Tier 1 `<50` = Market Only (100% market), Tier 2 `50-200` = Market Verified (80/20), Tier 3 `200-500` = Community Confirmed (20%→50% linear ramp), Tier 4 `500+` = Community Hardened (50/50). `_intelligence_adjust` blends pull data into verdict EV per tier weight.
- **Analyzer UI**: `ConfidenceBadge` (4-dot tier indicator + label) inside the verdict card. `IntelligencePanel` below market grid with progress bar to next threshold + stats + nudge "Log this rip to build your binder & sharpen the verdict →".
- **Smart eBay pricing**: `_real_market_verdict` now uses live → cached → stale (≤7d) → MSRP fallback chain. `pack_cost_source` tagged as `sold` / `active` / `cached_sold` / `cached_active` / `msrp_fallback` so UI can show data freshness.
- **Public Binder Gallery** (`/binders`) — aggregated list of users with public binders, sport filter, opt-in via per-binder visibility toggle. New page `PublicGallery.js`.
- **Public Binder View** (`/binders/:userId`) — solitaire-style spread of pulls. PRIVACY RULE enforced: `case_pack_id` and `pack_type_id` stripped from response, `source_pack: '—'` displayed. Thumbs-up only counter visible; thumbs-down stays as private signal. Page `PublicBinder.js`.
- **Visibility toggle** on `DisplayCase` Binder cards — `PATCH /api/case/packs/{id}/visibility` flips `is_public`. Optimistic UI with rollback on error.
- **Thumbs voting** — `POST /api/case/pulls/{pull_id}/thumbs` with toggle/switch/self-vote-blocked/private-binder-blocked logic. `pull_thumbs` collection with `(pull_id, user_id)` uniqueness via upsert.
- **Animation perf pass**: SolitaireSpread rewritten with GPU-only transforms (translate3d/rotate/scale, no margin animation), deterministic 35ms stagger from a center "deal" position, tuned spring (stiffness 260 / damping 26), `will-change: transform` + `backfaceVisibility: hidden` on each card. `prefers-reduced-motion` fallback to simple fade. Binder card hover hits 60fps with reduced rotateY angle + scale.
- **Critical bug fix**: `_user_tier()` had a corrupted line (`tind` syntax error) that broke trial logic. Fixed — new users now correctly get tier='pro' for 10 days.
- **Bug fix from testing agent**: `public_binder` endpoint had wrong async-iterator pattern (`async for` on a `to_list()` Future). Fixed to `cursor = ...; await cursor.to_list()`.

### ✅ Day 13 — DUB STREAK + Stripe Live (sk_test) + Refactor Foundation (2026-02-11)
- **🚨 Security alert**: User accidentally pasted a `sk_live_*` Stripe key in chat — flagged for immediate revoke. Only `sk_test_*` is in `backend/.env`.
- **Stripe wired**: `sk_test_51TVYQmGly...` + `pk_test_51TVYQmGly...` in `backend/.env`. `POST /api/subscription/checkout` confirmed creating real `cs_test_*` sessions for `Rip N' Flip Pro — $3.99/mo`.
- **🏆 DUB STREAK Leaderboard** at `GET /api/leaderboard/dub-streak?period=week|all&limit=N` — aggregates thumbs-up across public binders, ranks top users with `is_flame:true` on #1. Two windows: weekly (drives recurring engagement) + all-time (legacy flex).
- **Frontend `DubStreakLeaderboard`** on `/binders` page — gradient hero card with podium row (top 3 with neon-coloured borders + animated flame on #1), compact rows 4-10, period toggle. Drives Pro upgrades by showcasing trophy-binder energy.
- **Paywall messaging update** — `/api/analyzer/{pack_id}` 403 now reads: *"You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB."*
- **Refactor foundation laid**:
  - NEW `/app/backend/core.py` — singleton MongoDB client/db, JWT helpers, auth deps (`get_current_user` / `require_auth` / `user_tier`), tier constants, logger
  - NEW `/app/backend/routes/__init__.py` + `/app/backend/routes/leaderboard.py` — first extracted route module
  - `server.py` mounts via `from routes.leaderboard import router; app.include_router(router)`
  - Pattern proven: server.py drops route definitions, route modules import `from core` (absolute), no circular deps
- **Tests**: 16/16 pass — leaderboard shape, privacy enforcement, flame logic, Stripe checkout, paywall message, refactor sanity (no existing endpoint regression)

### ✅ Day 18 — eBay Browse API LIVE — MSRP fallback retired 🎯 (2026-06-05)
- **🔑 Production keys saved** to `backend/.env`: `EBAY_APP_ID=JesseRob-RipnFlip-PRD-…` + `EBAY_CERT_ID=PRD-…`. OAuth handshake verified, access token minted (~2h TTL, cached in-memory with 120s safety margin).
- **🧠 `_scrape_ebay_prices` upgraded to a smart router** in `server.py`:
  - When keys present + `sold_only=False` → uses Browse API directly (live, no Akamai blocks)
  - When `sold_only=True` → uses Browse active as `ebay_active_proxy` (Browse doesn't expose completed sales; Marketplace Insights is gated)
  - When keys missing or Browse fails → falls back to legacy HTML scraping (renamed `_ebay_html_scrape`)
  - 401 from Browse → cache invalidated + single retry per integration playbook
- **📊 NEW `_ebay_browse_aggregated`** computes `min/max/median/avg/count` from `itemSummaries`, filters by `conditions:{NEW}` + `buyingOptions:{FIXED_PRICE|BEST_OFFER|AUCTION}` + `category_ids=261328` (sports trading cards), sorted by price ASC for tight min estimation. Caps at 50 items per call to stay well under the 5000/day quota.
- **🧪 Verified live**: `GET /api/packs/price?q=Panini%20Prizm%20Basketball%20Hobby` returns 8 active listings, median $2,385, source `ebay_browse_api`. Analyzer verdict on `prizm-bball-hobby` now reads `based_on: 'ebay_market'` (was `msrp_fallback`) with `pack_cost_source: 'sold'` and live $2,274 sealed market price vs. $800 MSRP → **DUB** verdict.
- **📑 Playbook followed**: `integration_playbook_expert_v2` consulted for proper OAuth2 client_credentials flow, scope (`https://api.ebay.com/oauth/api_scope`), token caching (in-memory asyncio-safe), Browse search params, filter syntax, rate-limit awareness (5000 calls/day default), and explicit acknowledgment that Browse API does NOT provide sold/completed data — using active listings as a tagged proxy.

### ✅ Day 17 — Stripe Webhook STRICT Mode + E2E Verified (2026-02-13)
- **🔐 Stripe webhook signature verification flipped LIVE in STRICT mode**:
  - Real Stripe TEST keys provided by Jesse: `rk_test_*` restricted key + `whsec_test_*` webhook secret (saved to `backend/.env` as `STRIPE_RESTRICTED_TEST_KEY` and `STRIPE_WEBHOOK_SECRET`)
  - `STRIPE_WEBHOOK_STRICT=true` env flag set — backend now logs *"mode=STRICT (signature required)"* on boot
  - Verified via HMAC-SHA256 signed POSTs (Stripe CLI-equivalent):
    - ✅ Valid sig → `200 {received:true, verified:true}`
    - ✅ Bad sig → `400 {received:false, error:'invalid_signature'}`
    - ✅ Tampered body → `400 invalid_signature`
- **🧪 End-to-end subscription lifecycle proven**:
  - Created fresh test user, expired trial, seeded `stripe_customer_id`
  - `customer.subscription.created` webhook → user `tier: free → pro`, `pro_until` set to period_end, `pro_source: 'stripe_subscription'` ✅
  - `customer.subscription.deleted` webhook → user `tier: pro → free`, `subscription.status: 'canceled'` ✅
- **🚨 Security:** Jesse pasted `rk_live_*` four times this sprint. Lockdown held — only `_test_` keys touched `.env`. Live keys flagged for him to rotate in Stripe dashboard.

### ✅ Day 16 — Dethrone "Heart Attack" Push Nudge (Option D = Web Push + In-app) (2026-02-13)
- **🚨 Dethrone detector** (`services/dethrone.py`) — called from `routes/social.py` immediately after every successful upvote. Recomputes weekly #1 ranker via the same aggregation as the leaderboard, compares to `db.crown_state` (keyed `state_key='weekly'` + ISO week). When the holder changes: fires `send_notification(prev_top_user_id)` with verbatim copy *"You just lost the crown to @USERNAME. Beat them by Sunday or it's their Pro extension! 👑"* and updates crown_state. First-vote-of-week bootstraps state without firing.
- **🔔 Web Push infra** (`routes/push.py`) — VAPID keys generated via `py_vapid` (P-256 EC pair stored in `backend/.env` as `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY_PEM`, `VAPID_CONTACT`). Endpoints:
  - `GET  /api/push/vapid-public-key` (public — frontend calls to subscribe)
  - `POST /api/push/subscribe` (auth, idempotent upsert by `(user_id, endpoint)`)
  - `POST /api/push/unsubscribe`
  - `GET  /api/notifications?only_unread=true&limit=N` (in-app feed + unread count)
  - `POST /api/notifications/{id}/read`
  - `POST /api/notifications/read-all`
- **📨 Push fan-out** — `send_notification()` always inserts an in-app `notifications` doc and best-effort fires `pywebpush` to every registered subscription for that user. Expired endpoints (HTTP 404/410) are auto-pruned from `push_subscriptions`.
- **🎨 Frontend wiring**:
  - NEW `/app/frontend/src/lib/push.js` — `ensurePushSubscribed()` handles permission prompt + VAPID key fetch + `PushManager.subscribe()` + POST `/api/push/subscribe`. Silent failure (push is best-effort).
  - NEW `/app/frontend/src/components/DethroneBanner.js` — globally mounted in `App.js`; polls `/api/notifications?only_unread=true` every 60s; surfaces red-gradient sticky banner at top of page when a `dethrone` notification is unread, with "STRIKE BACK →" CTA linking to the new champion's binder. Auto-dismisses on click (marks read).
  - NEW `PushOptInButton` in `DisplayCase.js` next to ADD A PACK — three states: `ENABLE ALERTS` / `ENABLING…` / `ALERTS ON`. Toast confirmation on success: *"You'll get an alert the second someone takes your crown 👑"*.
  - **Service Worker** (`public/sw.js`) — added `push` event (renders OS-level notification with vibrate pattern, `requireInteraction: true` for dethrone type, icon, badge) + `notificationclick` event (focuses existing window or opens new one at `data.url`).
- **DB Collections Added**:
  - `push_subscriptions`: {user_id, endpoint, keys (p256dh, auth), user_agent, created_at, updated_at}
  - `notifications`: {notification_id, user_id, type, title, body, payload, url, read, read_at, created_at}
  - `crown_state`: {state_key: 'weekly', week_key, current_top_user_id, current_top_username, current_top_thumbs, updated_at, last_dethrone_at, last_dethroned_user_id}
- **Tests**: 73/73 pass (Day 13: 13 ✓, Day 14: 17 ✓, Day 15: 23 ✓, Day 16: 20 ✓). VAPID key validation, idempotent subscribe, 401 on notifications without auth, 404 on wrong-user notification mark-read, dethrone fires verbatim copy + updates crown_state, service worker has push handlers, frontend banner & opt-in button render correctly.


### ✅ Day 15 — Battle a Champion + Automated DUB STREAK Rewards + Refactor Phase 2 + Webhook Hardening (2026-02-13)
- **🥊 "Battle a Champion" CTA** — NEW `GET /api/binders/public/{user_id}/battle-cta` returns `{is_champion, rank, thumbs_week, top_thumbs, crown_holder}`. Frontend `PublicBinder.js` renders a neon-green banner on top-3 weekly winners' binders with copy *"Beat their [X] thumbs this week to take the crown 👑"* + "OPEN MY BINDER" CTA. Crown icon on #1, flame on #2/#3.
- **🤖 Automated weekly rewards (APScheduler)** — NEW `/app/backend/scheduler.py` runs an in-process `AsyncIOScheduler` cron job `dub_streak_weekly_award` every Monday 00:05 UTC. Reuses `compute_weekly_winners` + `_extend_pro_until` from `routes/rewards.py`; idempotent via ISO week key in `dub_streak_awards`. Misfire grace 60min; `DISABLE_SCHEDULER=true` env var disables for tests. Boot log: *"APScheduler started — DUB STREAK weekly award fires Mondays 00:05 UTC"*.
- **🔐 Stripe webhook hardening** — `/api/webhook/stripe-subscription` now supports three modes:
  - **Strict** (`STRIPE_WEBHOOK_STRICT=true`) — signature must verify or 400
  - **Lenient** (default when secret set) — verify signature, fall back to JSON parse on mismatch so test-key/live-secret combos don't break webhooks. Logs warning.
  - **Dev** (no secret) — JSON parse only, warning logged at boot
  - Webhook events now also write `tier`, `pro_until`, `pro_source='stripe_subscription'` onto `users` so `user_tier()` immediately honors a paid sub.
  - NEW `GET /api/subscription/webhook-mode` (admin-only) for runtime diagnostics — returns `{secret_configured, secret_prefix, strict_mode, api_key_type}`.
- **🧩 Backend refactor Phase 2** — extracted `server.py` (was 4052 lines) → `3646 lines` (-9%):
  - NEW `/app/backend/routes/subscription.py` — all `/api/subscription/*` + `/api/webhook/stripe-subscription` (with hardening)
  - NEW `/app/backend/routes/social.py` — binders public list/detail (privacy enforced), visibility toggle, thumbs vote (cast/get), `/battle-cta`
  - `core.py` upgraded — `get_current_user` now handles BOTH Emergent OAuth `user_sessions` AND JWT bearer/cookie (fixes route modules that needed full auth path). Added `is_admin()` + `require_admin()` shared deps.
  - Pattern: route module imports `from core import ...` (absolute), `server.py` mounts via `app.include_router()`.
- **Tests**: 53/53 pass (Day 13: 13 ✓, Day 14: 17 ✓, Day 15: 23 ✓). Privacy assertions (no `case_pack_id` / `pack_type_id` in public pulls), webhook strict-vs-lenient mode, battle-cta top-3 logic, scheduler boot all verified.


### ✅ Day 14 — Kingbuilt Predictor + DUB STREAK Rewards + Smarter Verdict UI (2026-02-12)
- **Kingbuilt `POST /api/predictor/rip`** — returns 8 cards with HIT placed at the climax slot (last position), 7 base/mystery fillers before it for full pack-feel deal animation. Mystery placeholders use 'Mystery [Tier] Card' naming. Tier-gated with verbatim copy: *"You hit the limit, kid. Go Pro or wait 'til next week to find your next DUB."* (HTTP 429). Legacy `/predictor/simulate` preserved for backward compat.
- **DUB STREAK Weekly Reward** — `POST /api/leaderboard/award-weekly` (admin-only, idempotent per ISO week) picks top-3 thumbs-up earners and extends each user's `pro_until` by 14 days. `GET /api/leaderboard/recent-awards` returns the audit log publicly. Reward is automatic Pro access — drives public-binder opt-in.
- **`_user_tier()` honors `pro_until`** in both server.py and core.py — Stripe-active sub OR active pro_until (DUB STREAK reward or manual grant) OR 10-day signup trial → 'pro'. Expired pro_until correctly falls back to 'free'.
- **"Verdict gets smarter" info-popover** — clicking the `ConfidenceBadge` opens a popover with: how-this-works tagline, 3-tier ladder (Market Only / Market Verified / Community Hardened) with done/active/locked state, and live "X more pulls" nudge to next threshold. Drives binder-log behavior transparently.
- **Predictor frontend rebuilt** — calls `/rip`, renders 8-card deal with HIT badge animation on climax slot, mystery-card slate styling, 429 paywall with verbatim copy, rip recap stats (Hit / Mystery Cards / Est. Value / vs MSRP / hit probability %).
- **Refactor progress**: `/app/backend/routes/rewards.py` added (DUB STREAK award + recent-awards). `routes/leaderboard.py` already in place. Pattern: route module → `from core import db, get_current_user, logger` (absolute imports), server.py mounts via `app.include_router()`.
- **Webhook signature verification** scaffolded — when `STRIPE_WEBHOOK_SECRET` is set in `backend/.env`, `stripe_sdk.Webhook.construct_event(body, sig, secret)` enforces HMAC SHA256. Falls back to raw JSON parse in dev mode.
- **Tests**: 14/14 pass (Kingbuilt rip shape + HIT climax + mystery + paywall, DUB STREAK 401/403/200/idempotent, pro_until honor, popover ladder, predictor animation).

## DB Collections Added
- `cards`: imported card master DB (set_key + card_number unique)
- `case_packs`: user's binders — now includes `is_public: bool`
- `case_pulls`: pulls within each binder — now includes `rarity_tier`, `thumbs_up_count`, `pack_type_id`
- `internal_hit_rates`: global aggregated pack pull data (Intelligence Loop training set)
- `pull_thumbs`: per-pull per-user vote records
- `pack_market_cache`: persistent `last_known_avg` per pack (no TTL) — last-ditch fallback before MSRP
- `chat_sessions`, `price_cache`, `trades` from earlier sprints

### ✅ Day 12.5 — Verdict Engine Math Fix + Monetization Gate (2026-02-11)
- **Math normalization (the "TRASH default" fix):**
  - `market_perf = ebay_avg / MSRP` (unitless ratio, e.g., 1.5×)
  - `internal_perf = actual_hit_rate / expected_hit_rate_baseline` (unitless ratio, e.g., 1.25×)
  - `final_score = market_perf × w_market + internal_perf × w_pull`
  - Rating now thresholds on `final_score` directly: `≥1.05 DUB`, `≥0.70 MID`, else `TRASH`
  - When `pack_cost_source=msrp_fallback`, `market_perf=1.0` (neutral) so verdict no longer biases to TRASH from no-data scenarios
- **Three-tier Cold Start (compressed):**
  - Tier 1 `<50` = Market Only (100/0)
  - Tier 2 `50-200` = Market Verified (80/20)
  - Tier 3 `≥200` = **Community Hardened** (50/50) — kicks in earlier to build user momentum
  - Removed Tier 3-ramp + Tier 4. UI `ConfidenceBadge` now 3 dots.
- **Fallback chain (no more silent crashes / hardcoded prices):**
  1. Live eBay sold avg (try/except)
  2. Live eBay active avg (try/except)
  3. Stale `price_cache` ≤7d
  4. `pack_market_cache.last_known_avg` (any age, persisted on every successful fetch)
  5. MSRP — tagged `pack_cost_source=msrp_fallback`
- **Monetization gate on `/api/analyzer/{pack_id}`:**
  - Anonymous → unlimited (lead funnel preserved)
  - Pro / 10-day trial → unlimited
  - Free past 2 packs/7d → `403 {error: 'free_tier_limit', message: 'Go Pro to Unlock...', cta_url: '/vault', limit, used}`
- **Frontend paywall block** renders on 403 with bright "GO PRO TO UNLOCK — $3.99/mo" CTA
- **IntelligencePanel** surfaces the 3 new ratios (Market perf, Hit-rate perf, Final score) for transparency

## Test Status
- Iteration 3: **32/32 backend tests PASSED** — Day 4-7 features fully validated
- Auth credentials: `admin@flipnrip.com / AdminPass123!` (in `/app/memory/test_credentials.md`)

### ✅ Day 19 — Share Verdict Card + Hero Arc Fix (2026-09-15)
- **SHARE THIS VERDICT** on Analyzer results: client-side 1080×1350 neon verdict PNG (logo, pack, giant DUB/MID/TRASH, price rows, `ripnflipapp.com` footer). Native share sheet on phones; SAVE + COPY LINK fallbacks. No engine internals in the card.
- **Hero logo**: `ANALYZE NOW` SVG arc moved **outside** the green ring with clear air above RIP N' FLIP lettering (no overlay/overflow at 390–1920px).

## Pending / Roadmap
- **Day 8:** Marketplace v2 ✅ done
- **Day 9 (PARTIAL):** Stripe sk_test_ wired, $3.99/mo checkout returning real cs_test_ sessions ✅. Webhook signature verification now lenient/strict-modes ✅ (Day 15). cancel-at-period-end edge case still pending end-to-end webhook validation in strict mode.
- **Day 10-11 (DONE):** PWA + Capacitor Android wrap scaffolded ✅
- **Day 12 (DONE):** Brand rename, Intelligence Loop, Social Binder ✅
- **Day 12.5 (DONE):** Verdict math fix + monetization gate + fallback chain ✅
- **Day 13 (DONE):** DUB STREAK leaderboard + Stripe live (test mode) + refactor foundation ✅
- **Day 14 (DONE):** Kingbuilt Predictor + manual weekly reward + webhook scaffolding ✅
- **Day 15 (DONE):** Battle a Champion CTA + Automated weekly rewards + Webhook hardening + Refactor Phase 2 ✅
- **Day 16 (DONE):** Dethrone "Heart Attack" Push Nudge — Web Push + In-app banner + dethrone detection hook ✅
- **Day 17 (NEXT):** Refactor Phase 3 — extract analyzer/marketplace/case routes from server.py; Stripe webhook verify end-to-end with Stripe CLI in strict mode (needs `rk_test_*` + `whsec_test_*` from user); live eBay Browse API once EBAY keys arrive.
- **Day 19 (DONE):** Share verdict card + hero ANALYZE NOW outside-arc ✅

## Awaiting User
- 🔴 **Roll the leaked `sk_live_*` key** in Stripe dashboard ASAP — it was pasted plaintext in chat
- 🟢 `EBAY_APP_ID` + `EBAY_CERT_ID` — user says "one more hour"
- 🟡 Predictor backend tier-limits logic spec — user said "sending in a few minutes"
- 🟢 Google Play Console account ($25) before Android upload

## Known Constraints
- Preview pod's outbound IP is Akamai-blocked by eBay scraping (works from production)
- Emergent standard deploy won't host Ollama — user owns that infra
- `craco.config.js` has `babel-metadata-plugin` disabled — DO NOT re-enable
