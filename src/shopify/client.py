#!/usr/bin/env python3
"""
Shopify Admin API client.
Fetches customer profile and order history needed for intent classification.

Credentials required in .env:
    SHOPIFY_STORE_URL       e.g. my-store.myshopify.com
    SHOPIFY_ADMIN_API_KEY   Admin API access token
"""

import os
from datetime import datetime, timezone

import requests

# ── Auth ─────────────────────────────────────────────────────────────────────

def _headers() -> dict:
    api_key = os.getenv("SHOPIFY_ADMIN_API_KEY")
    if not api_key:
        raise EnvironmentError("SHOPIFY_ADMIN_API_KEY not set.")
    return {
        "X-Shopify-Access-Token": api_key,
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    store = os.getenv("SHOPIFY_STORE_URL")
    if not store:
        raise EnvironmentError("SHOPIFY_STORE_URL not set.")
    return f"https://{store}/admin/api/2024-01"


# ── Customer ─────────────────────────────────────────────────────────────────

def get_customer(customer_id: str) -> dict:
    """
    Fetch a Shopify customer object.
    Returns raw Shopify customer dict.
    """
    url = f"{_base_url()}/customers/{customer_id}.json"
    resp = requests.get(url, headers=_headers())
    resp.raise_for_status()
    return resp.json()["customer"]


def get_order_history(customer_id: str, limit: int = 50) -> list[dict]:
    """
    Fetch recent orders for a customer.
    Returns list of Shopify order dicts.
    """
    url = f"{_base_url()}/orders.json"
    params = {
        "customer_id": customer_id,
        "limit": limit,
        "status": "any",
        "fields": "id,total_price,discount_codes,created_at,financial_status",
    }
    resp = requests.get(url, headers=_headers(), params=params)
    resp.raise_for_status()
    return resp.json()["orders"]


# ── Profile builder ───────────────────────────────────────────────────────────

def build_shopify_profile(customer_id: str) -> dict:
    """
    Fetch customer + orders and return a profile dict matching
    the schema expected by the classifier engine.

    Returns partial profile (session signals added by profile_builder.py).
    """
    customer = get_customer(customer_id)
    orders = get_order_history(customer_id)

    purchase_count = len(orders)
    total_spend = sum(float(o["total_price"]) for o in orders)
    avg_order_value = round(total_spend / purchase_count, 2) if purchase_count > 0 else None

    # Discount usage rate: what fraction of orders used a discount code
    orders_with_discount = sum(1 for o in orders if o.get("discount_codes"))
    discount_usage_rate = round(orders_with_discount / purchase_count, 2) if purchase_count > 0 else 0.0

    # Days since last purchase
    days_since_last_purchase = None
    if orders:
        last_order_date = datetime.fromisoformat(orders[0]["created_at"].replace("Z", "+00:00"))
        days_since_last_purchase = (datetime.now(timezone.utc) - last_order_date).days

    # Customer type
    customer_type = "returning" if purchase_count > 0 else "first_time"

    return {
        "customer_id": str(customer_id),
        "customer_type": customer_type,
        "purchase_count": purchase_count,
        "avg_order_value": avg_order_value,
        "discount_usage_rate": discount_usage_rate,
        "days_since_last_purchase": days_since_last_purchase,
        # Fields below populated by Klaviyo client and session store
        "email_open_rate": None,
        "cart_value": None,
        "cart_items": [],
        "visited_return_policy": False,
        "visited_shipping_info": False,
        "time_on_checkout_seconds": None,
        "items_added_and_removed": 0,
    }
