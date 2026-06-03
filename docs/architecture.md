# Architecture

## Full production flow

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                          SHOPIFY STOREFRONT                                  ║
║                                                                              ║
║   Customer browses → adds to cart → reaches checkout → abandons             ║
║                                                                              ║
║   ┌─────────────────────────────────────────────────────────────────────┐   ║
║   │  pixel.js (Shopify Pixel API — runs in sandboxed browser context)   │   ║
║   │                                                                     │   ║
║   │  Events captured:                                                   │   ║
║   │  • page_viewed          → was /policies/refund-policy visited?      │   ║
║   │  • checkout_started     → timestamp (start timer)                  │   ║
║   │  • cart_updated         → items added / removed count              │   ║
║   │  • checkout_abandoned   → timestamp (end timer, fire webhook)      │   ║
║   └──────────────────────────────┬──────────────────────────────────────┘   ║
╚═════════════════════════════════|════════════════════════════════════════════╝
                                  │ POST /webhook/session-event
                                  │ POST /webhook/cart-abandoned (Shopify native)
                                  ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                         FASTAPI BACKEND (Railway)                            ║
║                                                                              ║
║  ┌──────────────────────┐    ┌──────────────────────────────────────────┐   ║
║  │  /webhook/           │    │  PROFILE BUILDER                         │   ║
║  │  session-event       │───▶│                                          │   ║
║  │                      │    │  1. Fetch from Shopify Admin API:        │   ║
║  │  Aggregates pixel    │    │     • purchase_count                     │   ║
║  │  events into Redis   │    │     • avg_order_value                    │   ║
║  │  session store,      │    │     • discount_usage_rate                │   ║
║  │  keyed by session_id │    │     • days_since_last_purchase           │   ║
║  └──────────────────────┘    │                                          │   ║
║                               │  2. Fetch from Klaviyo API:             │   ║
║  ┌──────────────────────┐    │     • email_open_rate                    │   ║
║  │  /webhook/           │    │     • predicted_ltv                      │   ║
║  │  cart-abandoned      │───▶│                                          │   ║
║  │                      │    │  3. Merge with session snapshot:         │   ║
║  │  Shopify native      │    │     • visited_return_policy              │   ║
║  │  webhook fires on    │    │     • time_on_checkout_seconds           │   ║
║  │  checkout abandon    │    │     • items_added_and_removed            │   ║
║  │                      │    └──────────────────┬───────────────────────┘   ║
║  │  Returns 200         │                       │ merged profile             ║
║  │  immediately →       │                       ▼                           ║
║  │  enqueues job        │    ┌──────────────────────────────────────────┐   ║
║  └──────────────────────┘    │  CLASSIFIER ENGINE (classify.py logic)   │   ║
║                               │                                          │   ║
║                               │  Claude API call:                        │   ║
║                               │  • System: intent definitions +          │   ║
║                               │    brand context + config               │   ║
║                               │  • User: merged profile                 │   ║
║                               │                                          │   ║
║                               │  Returns:                                │   ║
║                               │  { intent, confidence, reasoning }      │   ║
║                               └──────────────────┬───────────────────────┘   ║
╚═════════════════════════════════════════════════|════════════════════════════╝
                                                  │
                    ┌─────────────────────────────┼─────────────────────────┐
                    │                             │                         │
                    ▼                             ▼                         ▼
           ┌──────────────┐           ┌──────────────────┐       ┌──────────────────┐
           │   POSTGRES   │           │     KLAVIYO      │       │   ANTHROPIC API  │
           │              │           │                  │       │                  │
           │ classifications           │ PATCH /profiles  │       │ claude-3-5-sonnet│
           │ sessions     │           │ → abandoned_cart │       │                  │
           │ failed_jobs  │           │   _intent: "X"   │       │ ~$0.02-0.08      │
           └──────────────┘           │                  │       │ per customer     │
                                      │ Flow triggers    │       └──────────────────┘
                                      │ automatically    │
                                      │ on property set  │
                                      └──────────────────┘
                                               │
                          ┌────────────────────┼────────────────────┐
                          │                    │                    │
                          ▼                    ▼                    ▼
               ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
               │  DISCOUNT OFFER │  │ CONFIDENCE BUILD │  │  SIMPLE REMINDER │
               │  price_sensitive│  │  trust_gap       │  │  distracted      │
               │                 │  │                  │  │                  │
               │  15% off code   │  │  Reviews +       │  │  Clean cart      │
               │  24h expiry     │  │  free returns +  │  │  summary, 1      │
               │  1 email        │  │  guarantee       │  │  email, 1hr      │
               └─────────────────┘  │  2 emails        │  └──────────────────┘
                                    └──────────────────┘
                                    ┌──────────────────┐
                                    │  EDUCATION       │
                                    │  research_phase  │
                                    │                  │
                                    │  Benefits + FAQ  │
                                    │  + comparison    │
                                    │  3 emails / 5d   │
                                    └──────────────────┘
```

## Data flow summary

```
abandon event
    │
    ├── session snapshot (Redis, from pixel)
    │       └── visited_return_policy, time_on_checkout, cart_edits
    │
    ├── Shopify profile (Admin API)
    │       └── purchase_count, AOV, discount_usage_rate, days_since_last
    │
    └── Klaviyo profile (Klaviyo API)
            └── email_open_rate, predicted_ltv
                    │
                    ▼
            MERGED PROFILE → Claude → intent + confidence + reasoning
                                            │
                                            ├── write to Postgres (classifications)
                                            └── write to Klaviyo profile → triggers flow
```

## MVP vs full build

| Layer | MVP (✅ built) | Full build |
|---|---|---|
| Data source | `sample_customers.json` | Shopify API + Klaviyo API + Pixel |
| Trigger | `python classify.py` (manual) | Shopify cart abandonment webhook |
| Session signals | Mocked (boolean flags) | Real browser events via Shopify Pixel |
| Output | Terminal table + JSON file | Klaviyo profile write + flow trigger |
| Infrastructure | Local Python script | FastAPI + Postgres + Redis + Railway |
