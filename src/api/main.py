#!/usr/bin/env python3
"""
FastAPI backend — webhook receiver and classification orchestrator.

Endpoints:
    POST /webhook/cart-abandoned     Shopify native checkout abandonment webhook
    POST /webhook/session-event      Pixel event receiver
    GET  /health                     Uptime check

Deploy on Railway. Register Shopify webhooks pointing at your Railway URL.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import redis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

from src.classifier.engine import classify_single
from src.classifier.profile_builder import build_profile, log_profile_quality
from src.shopify.client import build_shopify_profile
from src.klaviyo.client import enrich_profile, write_classification_result

# ── Setup ─────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Cart Abandonment Intent Classifier")

CONFIG_PATH = BASE_DIR / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)


# ── Session store (Redis) ─────────────────────────────────────────────────────
# Falls back to an in-memory dict if REDIS_URL is not set (local dev only).
# In production, always set REDIS_URL — the in-memory store does not survive
# restarts or scale across multiple instances.

SESSION_TTL_SECONDS = 3600  # sessions expire after 1 hour

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    global _redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    if _redis_client is None:
        _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client


_memory_store: dict[str, dict] = {}  # fallback for local dev


def session_get(session_id: str) -> dict:
    r = get_redis()
    if r:
        raw = r.get(f"session:{session_id}")
        return json.loads(raw) if raw else {}
    return _memory_store.get(session_id, {})


def session_set(session_id: str, data: dict) -> None:
    r = get_redis()
    if r:
        r.setex(f"session:{session_id}", SESSION_TTL_SECONDS, json.dumps(data))
    else:
        _memory_store[session_id] = data


def session_delete(session_id: str) -> None:
    r = get_redis()
    if r:
        r.delete(f"session:{session_id}")
    else:
        _memory_store.pop(session_id, None)


# ── Webhook validation ────────────────────────────────────────────────────────

def verify_shopify_webhook(body: bytes, signature_header: str) -> bool:
    """
    Validate Shopify webhook HMAC-SHA256 signature.

    Shopify sends the signature as a base64-encoded HMAC in the
    X-Shopify-Hmac-Sha256 header. We compute the HMAC of the raw
    request body and compare using a constant-time comparison.

    NOTE: The previous implementation used .hexdigest() which would
    always fail — Shopify sends base64, not hex.
    """
    secret = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("SHOPIFY_WEBHOOK_SECRET not set — skipping webhook validation")
        return True

    computed = base64.b64encode(
        hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode()

    return hmac.compare_digest(computed, signature_header)


# ── Session event endpoint ────────────────────────────────────────────────────

@app.post("/webhook/session-event")
async def receive_session_event(request: Request):
    """
    Receives pixel events from pixel.js.
    Aggregates into a session snapshot keyed by Shopify checkout token.

    Expected payload:
    {
      "session_id": "<checkout token>",
      "customer_id": "123456",         (optional — only if customer is identified)
      "event": "page_viewed",
      "url": "/policies/refund-policy",
      "timestamp": 1717000000
    }
    """
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    session = session_get(session_id) or {
        "customer_id": body.get("customer_id"),
        "visited_return_policy": False,
        "visited_shipping_info": False,
        "checkout_start_time": None,
        "time_on_checkout_seconds": None,
        "items_added_and_removed": 0,
        "page_views": [],
    }

    event = body.get("event")
    url   = body.get("url", "")

    if event == "page_viewed":
        session["page_views"].append(url)
        if "refund" in url or "return" in url:
            session["visited_return_policy"] = True
        if "shipping" in url:
            session["visited_shipping_info"] = True

    elif event == "checkout_started":
        session["checkout_start_time"] = body.get("timestamp")

    elif event == "cart_updated":
        if body.get("action") == "removed":
            session["items_added_and_removed"] = session.get("items_added_and_removed", 0) + 1

    elif event == "checkout_completed":
        # Customer converted — mark session so we skip classification
        session["converted"] = True

    session_set(session_id, session)
    return {"status": "ok"}


# ── Cart abandoned endpoint ───────────────────────────────────────────────────

@app.post("/webhook/cart-abandoned")
async def cart_abandoned(request: Request, background_tasks: BackgroundTasks):
    """
    Shopify fires this when a checkout is abandoned.
    Returns 200 immediately — classification runs as a background task.

    Register in Shopify Admin:
        Topic: checkouts/delete
        URL:   https://<your-railway-url>/webhook/cart-abandoned
    """
    raw_body = await request.body()

    signature = request.headers.get("X-Shopify-Hmac-Sha256", "")
    if not verify_shopify_webhook(raw_body, signature):
        logger.warning("Rejected webhook — invalid HMAC signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload       = json.loads(raw_body)
    customer_id   = str(payload.get("customer", {}).get("id", ""))
    customer_email = payload.get("email", "")
    session_id    = payload.get("token", "")
    cart_value    = float(payload.get("total_price", 0))
    cart_items    = [item.get("title", "") for item in payload.get("line_items", [])]

    logger.info(f"Cart abandoned — customer_id={customer_id} value={cart_value}")

    background_tasks.add_task(
        run_classification,
        customer_id=customer_id,
        customer_email=customer_email,
        session_id=session_id,
        cart_value=cart_value,
        cart_items=cart_items,
    )

    return JSONResponse({"status": "queued"}, status_code=200)


# ── Classification pipeline ───────────────────────────────────────────────────

async def run_classification(
    customer_id: str,
    customer_email: str,
    session_id: str,
    cart_value: float,
    cart_items: list[str],
) -> None:
    """
    Full classification pipeline:
    1. Fetch Shopify + Klaviyo data
    2. Load session signals from Redis
    3. Build profile via profile_builder
    4. Classify via Claude
    5. Write result back to Klaviyo
    """
    try:
        # Skip if customer converted in this session
        session = session_get(session_id)
        if session.get("converted"):
            logger.info(f"Skipping classification — customer {customer_id} converted")
            return

        # 1. Fetch data sources
        shopify_data = None
        klaviyo_data = None

        if customer_id:
            try:
                shopify_data = build_shopify_profile(customer_id)
            except Exception as e:
                logger.warning(f"Shopify fetch failed for {customer_id}: {e}")

        if customer_email:
            try:
                enriched = enrich_profile({}, customer_email)
                klaviyo_data = {
                    "email_open_rate": enriched.get("email_open_rate"),
                    "profile_id": enriched.get("_klaviyo_profile_id"),
                }
            except Exception as e:
                logger.warning(f"Klaviyo fetch failed for {customer_email}: {e}")

        # 2. Calculate checkout time from session
        if session.get("checkout_start_time"):
            elapsed = datetime.now(timezone.utc).timestamp() - session["checkout_start_time"]
            session["time_on_checkout_seconds"] = int(elapsed)

        # 3. Build profile
        profile = build_profile(
            customer_id=customer_id,
            customer_email=customer_email,
            cart_value=cart_value,
            cart_items=cart_items,
            session=session or None,
            shopify_data=shopify_data,
            klaviyo_data=klaviyo_data,
        )
        log_profile_quality(profile)

        # 4. Classify
        result = classify_single(profile, CONFIG)
        logger.info(
            f"Classified {customer_id}: intent={result['intent']} "
            f"confidence={result['confidence']:.2f}"
        )

        # 5. Write back to Klaviyo
        if profile.get("_klaviyo_profile_id"):
            write_classification_result(profile, result["intent"], result["klaviyo_flow"])
            logger.info(f"Klaviyo updated for profile {profile['_klaviyo_profile_id']}")

        # 6. Clean up session
        session_delete(session_id)

    except Exception as e:
        logger.error(f"Classification failed for {customer_id}: {e}", exc_info=True)
        # TODO Phase 5: persist to failed_classifications for retry


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    redis_ok = False
    try:
        r = get_redis()
        if r:
            r.ping()
            redis_ok = True
    except Exception:
        pass

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "redis": "connected" if redis_ok else "not configured (using memory store)",
    }
