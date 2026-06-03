# Cart Abandonment Intent Classifier — Roadmap

**Prototype status:** ✅ Working MVP (`classify.py`) — classifies 12 customer profiles via Claude API, outputs clean table + JSON.

**Full product:** A real-time Shopify app that intercepts cart abandonment events, classifies intent using live session + profile data, and triggers the correct Klaviyo recovery flow automatically.

---

## Phase 1 — Data layer (mock → real)
Replace mocked JSON profiles with live data from Shopify + Klaviyo.

- [ ] `src/shopify/client.py` — Shopify Admin API wrapper
  - `get_customer(customer_id)` → purchase count, AOV, discount usage rate, days since last purchase
  - `get_order_history(customer_id)` → full order list for AOV + discount calculations
- [ ] `src/klaviyo/client.py` — Klaviyo API wrapper
  - `get_profile(email)` → email open rate, predicted LTV, historical flow engagement
  - `update_profile_property(profile_id, key, value)` → write `abandoned_cart_intent` after classification
  - `trigger_flow(profile_id, flow_id)` → fire the correct recovery flow
- [ ] `src/classifier/profile_builder.py` — merge Shopify + Klaviyo data into the profile schema `classify.py` expects
- [ ] Test end-to-end on a real Shopify test store

**Credentials needed:** `SHOPIFY_STORE_URL`, `SHOPIFY_ADMIN_API_KEY`, `KLAVIYO_PRIVATE_KEY`

---

## Phase 2 — Event trigger (manual → real-time)
Replace `python classify.py` with automatic classification on cart abandonment.

- [ ] `src/api/main.py` — FastAPI app
  - `POST /webhook/cart-abandoned` — Shopify webhook receiver
  - `GET /health` — uptime check
- [ ] Register Shopify `checkouts/delete` webhook pointing at `/webhook/cart-abandoned`
- [ ] Wire profile builder + classifier into webhook handler

---

## Phase 3 — Session signals (profile proxies → real behaviour)
Layer in live browser behaviour to make classifications precise.

- [ ] `src/pixel/pixel.js` — Shopify storefront pixel
  - Subscribes to: `page_viewed`, `checkout_started`, `checkout_abandoned`, `cart_updated`, `product_viewed`
  - Captures: policy page visits, time on checkout page, items added/removed, referral source
  - Sends events to `POST /webhook/session-event`
- [ ] `src/api/main.py` — add `POST /webhook/session-event` endpoint
- [ ] Session store (Redis or Postgres `sessions` table) — aggregate pixel events per session_id
- [ ] Update profile builder to merge session snapshot into classification payload

---

## Phase 4 — Klaviyo write-back
Close the loop: classification triggers the right flow automatically.

- [ ] On classification result, write `abandoned_cart_intent` property to Klaviyo profile
- [ ] Four Klaviyo flows to build (Lakehouse's domain — flows are triggered by the `abandoned_cart_intent` property value):
  - `price_sensitive` → Discount Offer flow (15% off, 24h expiry)
  - `trust_gap` → Confidence Builder flow (reviews, free returns, guarantee)
  - `distracted` → Simple Reminder flow (clean cart summary)
  - `research_phase` → Education flow (benefits, FAQ, comparison)
- [ ] End-to-end test: abandon cart → webhook fires → classify → Klaviyo updates → flow triggers

---

## Phase 5 — Reliability + observability
Production-grade error handling and monitoring.

- [ ] Job queue — move Claude API call to background worker (Celery + Redis or Inngest)
  - Webhook handler returns 200 immediately (Shopify times out at 5s)
  - Classification runs async in worker
- [ ] Retry logic — exponential backoff on Claude API + Klaviyo write failures
- [ ] `src/db/schema.sql` — Postgres tables:
  - `sessions` — pixel events per session
  - `classifications` — customer_id, intent, confidence, flow_triggered, latency_ms, timestamp
  - `failed_classifications` — retry queue
- [ ] Structured logging — log inputs, result, latency per classification
- [ ] Alerting — notify if failure rate > 5% in a 1h window

---

## Phase 6 — Shopify app packaging
Make it installable by any merchant.

- [ ] OAuth handshake — Shopify app OAuth flow so any merchant can install
  - Required scopes: `read_customers`, `read_orders`, `write_webhooks`
- [ ] Multi-tenant isolation — scope all DB queries + API calls by `shop_id`
- [ ] Onboarding flow — post-OAuth:
  1. Guide merchant to install pixel in theme
  2. Collect Klaviyo API key
  3. Verify the four Klaviyo flows exist (or prompt to create them)
- [ ] Deploy — Docker container on Railway or Fly.io

---

## What already exists (hand to engineer as-is)

| File | Status | Notes |
|---|---|---|
| `classify.py` | ✅ Working | Core classification logic — Claude API, prompt, output. Reuse in `src/classifier/engine.py` |
| `config.json` | ✅ Complete | Intent definitions, flow mappings, brand context. Configurable per merchant. |
| `data/sample_customers.json` | ✅ Complete | 12 profiles, all four buckets. Documents the exact data schema needed from real APIs. |
| `src/shopify/client.py` | 🏗 Scaffolded | Functions written, needs real credentials to test |
| `src/klaviyo/client.py` | 🏗 Scaffolded | Functions written, needs real credentials to test |
| `src/api/main.py` | 🏗 Scaffolded | FastAPI skeleton with webhook endpoint |
| `src/classifier/engine.py` | 🏗 Scaffolded | classify.py logic extracted into importable module |
| `src/pixel/pixel.js` | 🏗 Scaffolded | Shopify Pixel event subscriptions written |
| `src/db/schema.sql` | 🏗 Scaffolded | Postgres schema ready to run |
| `Dockerfile` | 🏗 Scaffolded | Ready for Railway deploy |

---

## Environment variables (full build)

```
# Core
ANTHROPIC_API_KEY=

# Shopify
SHOPIFY_STORE_URL=          # e.g. my-store.myshopify.com
SHOPIFY_ADMIN_API_KEY=      # Admin API access token
SHOPIFY_WEBHOOK_SECRET=     # For validating webhook signatures

# Klaviyo
KLAVIYO_PRIVATE_KEY=        # Private API key

# Database
DATABASE_URL=               # PostgreSQL connection string

# Redis (Phase 5 job queue)
REDIS_URL=
```
