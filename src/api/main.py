#!/usr/bin/env python3
"""
FastAPI backend — webhook receiver and classification orchestrator.

Endpoints:
    POST /webhook/cart-abandoned     Shopify native checkout abandonment webhook
    POST /webhook/session-event      Pixel event receiver
    GET  /health                     Uptime check

Deploy on Railway. Register Shopify webhooks pointing at your Railway URL.
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse

# Load env
BASE_DIR = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

from src.classifier.engine import classify_single
from src.shopify.client import build_shopify_profile
from src.klaviyo.client import enrich_profile, write_classification_result

# ── Setup ────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Cart Abandonment Intent Classifier")

CONFIG_PATH = BASE_DIR / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

# In-memory session store (replace with Redis in production — see Phase 5)
SESSION_STORE: dict[str, dict] = {}


# ── Webhook validation ────────────────────────────────────────────────────────

def verify_shopify_webhook(body: bytes, signature: str) -> bool:
    """
    Validate Shopify webhook HMAC signature.
    Shopify signs every webhook with your webhook secret.
    """
    secret = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
    computed = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


# ── Session event endpoint ────────────────────────────────────────────────────

@app.post("/webhook/session-event")
async def receive_session_event(request: Request):
    """
    Receives pixel events from pixel.js.
    Aggregates into a session snapshot keyed by session_id.

    Pixel sends:
    {
      "session_id": "abc123",
      "customer_id": "cust_001",    (if known — logged-in or identified customer)
      "event": "page_viewed",
      "url": "/policies/refund-policy",
      "timestamp": 1717000000
    }
    """
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    # Initialise session if new
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = {
            "customer_id": body.get("customer_id"),
            "visited_return_policy": False,
            "visited_shipping_info": False,
            "checkout_start_time": None,
            "time_on_checkout_seconds": None,
            "items_added_and_removed": 0,
            "page_views": [],
        }

    session = SESSION_STORE[session_id]

    event = body.get("event")
    url = body.get("url", "")

    if event == "page_viewed":
        session["page_views"].append(url)
        if "refund" in url or "return" in url:
            session["visited_return_policy"] = True
        if "shipping" in url:
            session["visited_shipping_info"] = True

    elif event == "checkout_started":
        session["checkout_start_time"] = body.get("timestamp")

    elif event == "cart_updated":
        action = body.get("action")  # "added" or "removed"
        if action == "removed":
            session["items_added_and_removed"] = session.get("items_added_and_removed", 0) + 1

    return {"status": "ok"}


# ── Cart abandoned endpoint ───────────────────────────────────────────────────

@app.post("/webhook/cart-abandoned")
async def cart_abandoned(request: Request, background_tasks: BackgroundTasks):
    """
    Shopify fires this when a checkout is abandoned.
    Returns 200 immediately — classification runs in the background.

    Register this URL in Shopify:
        Topic: checkouts/delete  (or use Abandoned Checkout flow)
        URL:   https://your-railway-url.up.railway.app/webhook/cart-abandoned
    """
    raw_body = await request.body()

    # Validate Shopify signature in production
    signature = request.headers.get("X-Shopify-Hmac-Sha256", "")
    if os.getenv("SHOPIFY_WEBHOOK_SECRET") and not verify_shopify_webhook(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(raw_body)
    customer_id = str(payload.get("customer", {}).get("id", ""))
    customer_email = payload.get("email", "")
    session_id = payload.get("token", "")  # Shopify checkout token doubles as session ID

    # Cart value and items from the webhook payload
    cart_value = float(payload.get("total_price", 0))
    line_items = payload.get("line_items", [])
    cart_items = [item.get("title", "") for item in line_items]

    logger.info(f"Cart abandoned — customer_id={customer_id} cart_value={cart_value}")

    # Enqueue classification as background task (keeps response < 5s for Shopify)
    background_tasks.add_task(
        run_classification,
        customer_id=customer_id,
        customer_email=customer_email,
        session_id=session_id,
        cart_value=cart_value,
        cart_items=cart_items,
    )

    return JSONResponse({"status": "queued"}, status_code=200)


# ── Classification task ───────────────────────────────────────────────────────

async def run_classification(
    customer_id: str,
    customer_email: str,
    session_id: str,
    cart_value: float,
    cart_items: list[str],
) -> None:
    """
    Full classification pipeline:
    1. Build profile from Shopify + Klaviyo
    2. Merge session signals
    3. Classify via Claude
    4. Write result back to Klaviyo
    """
    try:
        # 1. Shopify profile
        profile = build_shopify_profile(customer_id)

        # 2. Klaviyo enrichment
        if customer_email:
            profile = enrich_profile(profile, customer_email)

        # 3. Merge session signals
        profile["cart_value"] = cart_value
        profile["cart_items"] = cart_items

        session = SESSION_STORE.get(session_id, {})
        profile["visited_return_policy"]    = session.get("visited_return_policy", False)
        profile["visited_shipping_info"]    = session.get("visited_shipping_info", False)
        profile["items_added_and_removed"]  = session.get("items_added_and_removed", 0)

        # Calculate time on checkout if available
        checkout_start = session.get("checkout_start_time")
        if checkout_start:
            elapsed = datetime.now(timezone.utc).timestamp() - checkout_start
            profile["time_on_checkout_seconds"] = int(elapsed)

        # 4. Classify
        result = classify_single(profile, CONFIG)

        logger.info(
            f"Classified customer_id={customer_id} "
            f"intent={result['intent']} "
            f"confidence={result['confidence']:.2f}"
        )

        # 5. Write back to Klaviyo
        if customer_email and profile.get("_klaviyo_profile_id"):
            write_classification_result(profile, result["intent"], result["klaviyo_flow"])
            logger.info(f"Klaviyo updated — profile={profile['_klaviyo_profile_id']} flow={result['klaviyo_flow']}")

        # 6. Clean up session store
        if session_id in SESSION_STORE:
            del SESSION_STORE[session_id]

    except Exception as e:
        logger.error(f"Classification failed for customer_id={customer_id}: {e}", exc_info=True)
        # TODO Phase 5: write to failed_classifications table for retry


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
