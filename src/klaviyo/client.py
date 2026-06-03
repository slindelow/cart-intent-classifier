#!/usr/bin/env python3
"""
Klaviyo API client.
Fetches profile engagement data and writes classification results back.

Credentials required in .env:
    KLAVIYO_PRIVATE_KEY    Private API key (starts with pk_)
"""

import os

import requests

# ── Auth ─────────────────────────────────────────────────────────────────────

KLAVIYO_BASE = "https://a.klaviyo.com/api"
API_VERSION = "2023-10-15"


def _headers() -> dict:
    key = os.getenv("KLAVIYO_PRIVATE_KEY")
    if not key:
        raise EnvironmentError("KLAVIYO_PRIVATE_KEY not set.")
    return {
        "Authorization": f"Klaviyo-API-Key {key}",
        "revision": API_VERSION,
        "Content-Type": "application/json",
    }


# ── Profile ──────────────────────────────────────────────────────────────────

def get_profile_by_email(email: str) -> dict | None:
    """
    Look up a Klaviyo profile by email address.
    Returns the profile dict or None if not found.
    """
    url = f"{KLAVIYO_BASE}/profiles/"
    params = {"filter": f"equals(email,\"{email}\")"}
    resp = requests.get(url, headers=_headers(), params=params)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0] if data else None


def get_profile_metrics(profile_id: str) -> dict:
    """
    Fetch engagement metrics for a Klaviyo profile.
    Returns dict with email_open_rate and predicted_ltv where available.
    """
    url = f"{KLAVIYO_BASE}/profiles/{profile_id}/"
    params = {"fields[profile]": "predicted_ltv,email_open_rate,properties"}
    resp = requests.get(url, headers=_headers(), params=params)
    resp.raise_for_status()
    attrs = resp.json()["data"]["attributes"]

    return {
        "predicted_ltv": attrs.get("predicted_ltv"),
        "email_open_rate": attrs.get("email_open_rate"),
    }


def update_profile_property(profile_id: str, key: str, value: str) -> None:
    """
    Write a custom property to a Klaviyo profile.
    Used to set abandoned_cart_intent = "trust_gap" etc.
    """
    url = f"{KLAVIYO_BASE}/profiles/{profile_id}/"
    payload = {
        "data": {
            "type": "profile",
            "id": profile_id,
            "attributes": {
                "properties": {key: value}
            }
        }
    }
    resp = requests.patch(url, headers=_headers(), json=payload)
    resp.raise_for_status()


def enrich_profile(profile: dict, email: str) -> dict:
    """
    Look up the Klaviyo profile for this customer and merge engagement
    metrics into the profile dict.

    Args:
        profile: Partial profile dict from shopify/client.py
        email:   Customer email address

    Returns:
        Profile dict with email_open_rate populated (or None if not found)
    """
    klaviyo_profile = get_profile_by_email(email)
    if not klaviyo_profile:
        return profile

    metrics = get_profile_metrics(klaviyo_profile["id"])
    profile["email_open_rate"] = metrics.get("email_open_rate")
    profile["_klaviyo_profile_id"] = klaviyo_profile["id"]  # stash for write-back

    return profile


def write_classification_result(profile: dict, intent: str, flow_name: str) -> None:
    """
    Write the classification result back to Klaviyo so the flow can trigger.

    Sets two properties on the profile:
        abandoned_cart_intent       = "trust_gap"
        abandoned_cart_flow         = "Abandoned Cart — Confidence Builder"

    The Klaviyo flows should be configured to trigger on
    the abandoned_cart_intent property value.
    """
    profile_id = profile.get("_klaviyo_profile_id")
    if not profile_id:
        raise ValueError("No Klaviyo profile ID on this profile. Run enrich_profile() first.")

    update_profile_property(profile_id, "abandoned_cart_intent", intent)
    update_profile_property(profile_id, "abandoned_cart_flow", flow_name)
