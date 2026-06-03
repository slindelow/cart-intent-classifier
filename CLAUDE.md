# Cart Abandonment Intent Classifier

A prototype for classifying Shopify cart abandoners into intent-based Klaviyo flows.

## What this does
Reads Shopify customer profiles and classifies each cart abandoner's intent
into one of four buckets, then maps to the appropriate Klaviyo recovery flow.
Solves the problem of every abandoner getting the same generic email.

## Intent buckets
- `price_sensitive`  → Abandoned Cart — Discount Offer (15% off, 24h)
- `trust_gap`        → Abandoned Cart — Confidence Builder (reviews, returns, guarantee)
- `distracted`       → Abandoned Cart — Simple Reminder (clean cart summary)
- `research_phase`   → Abandoned Cart — Education (benefits, FAQ, comparison)

## Run it
```
pip install -r requirements.txt
cp .env.example .env          # add your ANTHROPIC_API_KEY
python classify.py            # uses data/sample_customers.json by default
python classify.py --input data/sample_customers.json --verbose
```

## Files
- `classify.py` — main script
- `config.json` — intent definitions + Klaviyo flow name mappings (edit per brand)
- `data/sample_customers.json` — mock profiles (proxies for live Shopify + Klaviyo data)
- `output/` — generated JSON results, one file per run (gitignored)

## Signal schema
Each customer profile uses attributes available from Shopify Admin API + Klaviyo:
- `customer_type`, `purchase_count`, `avg_order_value`, `cart_value`
- `discount_usage_rate`, `email_open_rate`, `days_since_last_purchase`
- `visited_return_policy`, `visited_shipping_info` (session signals, mocked here)
- `time_on_checkout_seconds`, `items_added_and_removed`, `cart_items`

## Full product roadmap
MVP uses mocked session signals. Full build adds:
1. Shopify Pixel — real session events (policy visits, checkout time, cart edits)
2. Shopify Admin API — live customer + order history
3. Klaviyo API — profile property update + flow trigger on classification
Backend: FastAPI on Railway. See architecture notes for full stack.
