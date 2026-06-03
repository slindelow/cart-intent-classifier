#!/usr/bin/env python3
"""
Register required Shopify webhooks for the Cart Abandonment Intent Classifier.

Run this once after deploying to Railway (or any public URL) to wire up the
Shopify webhook subscriptions. Safe to re-run — existing webhooks are detected
and skipped.

Usage:
    python scripts/register_webhooks.py --url https://your-app.up.railway.app

Requirements:
    SHOPIFY_STORE_URL and SHOPIFY_ADMIN_API_KEY must be set in .env
"""

import argparse
import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# ── Webhooks to register ──────────────────────────────────────────────────────

WEBHOOKS = [
    {
        "topic": "checkouts/delete",
        "path": "/webhook/cart-abandoned",
        "description": "Fires when a Shopify checkout is abandoned",
    },
    {
        "topic": "checkouts/create",
        "path": "/webhook/session-event",
        "description": "Fires when a checkout is created (backup session init)",
    },
]

# ── Shopify client ────────────────────────────────────────────────────────────

def headers() -> dict:
    return {
        "X-Shopify-Access-Token": os.environ["SHOPIFY_ADMIN_API_KEY"],
        "Content-Type": "application/json",
    }


def base_url() -> str:
    store = os.environ["SHOPIFY_STORE_URL"]
    return f"https://{store}/admin/api/2024-01"


def get_existing_webhooks() -> list[dict]:
    resp = requests.get(f"{base_url()}/webhooks.json", headers=headers())
    resp.raise_for_status()
    return resp.json().get("webhooks", [])


def register_webhook(topic: str, address: str) -> dict:
    payload = {
        "webhook": {
            "topic": topic,
            "address": address,
            "format": "json",
        }
    }
    resp = requests.post(f"{base_url()}/webhooks.json", headers=headers(), json=payload)
    resp.raise_for_status()
    return resp.json()["webhook"]


def delete_webhook(webhook_id: int) -> None:
    resp = requests.delete(f"{base_url()}/webhooks/{webhook_id}.json", headers=headers())
    resp.raise_for_status()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Register Shopify webhooks")
    parser.add_argument(
        "--url", required=True,
        help="Public base URL of your deployed app (e.g. https://my-app.up.railway.app)"
    )
    parser.add_argument(
        "--delete-existing", action="store_true",
        help="Delete all existing webhooks for this store before registering"
    )
    args = parser.parse_args()

    base_app_url = args.url.rstrip("/")

    # Validate credentials
    for key in ("SHOPIFY_STORE_URL", "SHOPIFY_ADMIN_API_KEY"):
        if not os.getenv(key):
            print(f"Error: {key} not set in .env")
            sys.exit(1)

    print(f"\nStore: {os.environ['SHOPIFY_STORE_URL']}")
    print(f"App URL: {base_app_url}\n")

    # Fetch existing webhooks
    existing = get_existing_webhooks()
    print(f"Found {len(existing)} existing webhook(s):")
    for wh in existing:
        print(f"  [{wh['id']}] {wh['topic']} → {wh['address']}")

    if args.delete_existing and existing:
        print("\nDeleting existing webhooks...")
        for wh in existing:
            delete_webhook(wh["id"])
            print(f"  Deleted [{wh['id']}] {wh['topic']}")
        existing = []

    print()

    # Register webhooks
    existing_topics = {wh["topic"] for wh in existing}

    for webhook in WEBHOOKS:
        address = f"{base_app_url}{webhook['path']}"
        if webhook["topic"] in existing_topics:
            print(f"  ⏭  SKIPPED  {webhook['topic']} (already registered)")
            continue

        try:
            result = register_webhook(webhook["topic"], address)
            print(f"  ✅ REGISTERED  {webhook['topic']} → {address}  [id={result['id']}]")
        except requests.HTTPError as e:
            print(f"  ❌ FAILED      {webhook['topic']}: {e}")
            print(f"     Response: {e.response.text}")

    print("\nDone. Webhook secret for signature validation:")
    print("  Set SHOPIFY_WEBHOOK_SECRET in your .env and Railway environment variables.")
    print("  Get it from: Shopify Admin → Settings → Notifications → Webhooks\n")


if __name__ == "__main__":
    main()
