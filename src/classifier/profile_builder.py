#!/usr/bin/env python3
"""
Profile builder — assembles a complete customer profile for classification
by merging data from three sources:

    1. Shopify Admin API  (purchase history, AOV, discount usage)
    2. Klaviyo API        (email engagement, predicted LTV)
    3. Session store      (pixel events: policy visits, checkout time, cart edits)

The output dict matches the schema in data/sample_customers.json and is
passed directly to src/classifier/engine.classify_single().
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_profile(
    *,
    customer_id: str,
    customer_email: str,
    cart_value: float,
    cart_items: list[str],
    session: dict[str, Any] | None = None,
    shopify_data: dict[str, Any] | None = None,
    klaviyo_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Assemble a classification-ready profile from available data sources.

    All sources are optional — if a source is unavailable (API error, guest
    checkout, no session) the profile is built from whatever signals exist.
    The classifier handles sparse profiles gracefully via the fallback intent.

    Args:
        customer_id:    Shopify customer ID (string)
        customer_email: Customer email (used for Klaviyo lookup)
        cart_value:     Total cart value at abandonment (from webhook payload)
        cart_items:     List of product titles in the cart
        session:        Session snapshot from Redis (pixel events aggregated)
        shopify_data:   Pre-fetched Shopify profile dict (from shopify/client.py)
        klaviyo_data:   Pre-fetched Klaviyo metrics dict (from klaviyo/client.py)

    Returns:
        Profile dict matching the sample_customers.json schema.
    """
    profile: dict[str, Any] = {
        "customer_id": customer_id,
        "cart_value": cart_value,
        "cart_items": cart_items,
        # Defaults — overwritten by real data below
        "customer_type": "first_time",
        "purchase_count": 0,
        "avg_order_value": None,
        "discount_usage_rate": 0.0,
        "email_open_rate": None,
        "days_since_last_purchase": None,
        "visited_return_policy": False,
        "visited_shipping_info": False,
        "time_on_checkout_seconds": None,
        "items_added_and_removed": 0,
    }

    # ── Shopify data ──────────────────────────────────────────────────────────
    if shopify_data:
        profile.update({
            "customer_type":           shopify_data.get("customer_type", "first_time"),
            "purchase_count":          shopify_data.get("purchase_count", 0),
            "avg_order_value":         shopify_data.get("avg_order_value"),
            "discount_usage_rate":     shopify_data.get("discount_usage_rate", 0.0),
            "days_since_last_purchase": shopify_data.get("days_since_last_purchase"),
        })
        logger.debug(f"[{customer_id}] Shopify: {shopify_data.get('purchase_count')} orders, "
                     f"AOV={shopify_data.get('avg_order_value')}")
    else:
        logger.warning(f"[{customer_id}] No Shopify data — using defaults")

    # ── Klaviyo data ──────────────────────────────────────────────────────────
    if klaviyo_data:
        profile["email_open_rate"] = klaviyo_data.get("email_open_rate")
        # Stash profile ID for write-back after classification
        if klaviyo_data.get("profile_id"):
            profile["_klaviyo_profile_id"] = klaviyo_data["profile_id"]
        logger.debug(f"[{customer_id}] Klaviyo: open_rate={klaviyo_data.get('email_open_rate')}")
    else:
        logger.warning(f"[{customer_id}] No Klaviyo data — email signals unavailable")

    # ── Session signals ───────────────────────────────────────────────────────
    if session:
        profile.update({
            "visited_return_policy":   session.get("visited_return_policy", False),
            "visited_shipping_info":   session.get("visited_shipping_info", False),
            "items_added_and_removed": session.get("items_added_and_removed", 0),
            "time_on_checkout_seconds": session.get("time_on_checkout_seconds"),
        })
        logger.debug(f"[{customer_id}] Session: policy={session.get('visited_return_policy')}, "
                     f"checkout_time={session.get('time_on_checkout_seconds')}s")
    else:
        logger.warning(f"[{customer_id}] No session data — behavioural signals unavailable")

    return profile


def log_profile_quality(profile: dict[str, Any]) -> None:
    """
    Log a quality summary showing which signals came from real data sources
    vs. defaults. Useful for diagnosing classification accuracy.

    A signal "has real data" means it was actually populated by a source,
    not just left at a default value (0, False, 0.0, None).
    """
    # These fields have real data only when populated by their source.
    # Defaults are: purchase_count=0 (ambiguous), avg_order_value=None,
    # discount_usage_rate=0.0 (ambiguous), email_open_rate=None,
    # time_on_checkout_seconds=None, visited_return_policy=False (ambiguous)
    real_signals = {
        "purchase_history":     profile.get("avg_order_value") is not None,
        "discount_pattern":     profile.get("purchase_count", 0) > 0,
        "email_engagement":     profile.get("email_open_rate") is not None,
        "checkout_time":        profile.get("time_on_checkout_seconds") is not None,
        "policy_page_visits":   profile.get("visited_return_policy") is True
                                or profile.get("visited_shipping_info") is True,
        "cart_indecision":      profile.get("items_added_and_removed", 0) > 0,
        "lapsed_signal":        profile.get("days_since_last_purchase") is not None,
    }
    present = sum(real_signals.values())
    missing = [k for k, v in real_signals.items() if not v]

    logger.info(
        f"[{profile['customer_id']}] Profile quality: {present}/7 signals present"
        + (f" — missing: {', '.join(missing)}" if missing else "")
    )
