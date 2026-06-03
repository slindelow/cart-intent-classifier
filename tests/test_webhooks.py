"""
Tests for src/api/main.py webhook endpoints.

Run:  python -m pytest tests/ -v
"""

import base64
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, verify_shopify_webhook

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_shopify_signature(body: bytes, secret: str) -> str:
    """Generate a valid Shopify HMAC signature for test payloads."""
    return base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()


WEBHOOK_SECRET = "test_secret_abc123"

ABANDONED_CART_PAYLOAD = {
    "token": "session_abc",
    "email": "customer@example.com",
    "total_price": "145.00",
    "customer": {"id": 12345678},
    "line_items": [
        {"title": "Face Serum"},
        {"title": "Moisturiser"},
    ],
}


# ── Health endpoint ───────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_status_ok(self):
        resp = client.get("/health")
        assert resp.json()["status"] == "ok"

    def test_includes_timestamp(self):
        resp = client.get("/health")
        assert "timestamp" in resp.json()


# ── HMAC validation ───────────────────────────────────────────────────────────

class TestVerifyShopifyWebhook:
    def test_valid_signature_returns_true(self):
        body = b'{"test": "payload"}'
        sig = make_shopify_signature(body, WEBHOOK_SECRET)
        with patch.dict("os.environ", {"SHOPIFY_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            assert verify_shopify_webhook(body, sig) is True

    def test_invalid_signature_returns_false(self):
        body = b'{"test": "payload"}'
        with patch.dict("os.environ", {"SHOPIFY_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            assert verify_shopify_webhook(body, "invalid_sig") is False

    def test_tampered_body_returns_false(self):
        body = b'{"test": "payload"}'
        sig = make_shopify_signature(body, WEBHOOK_SECRET)
        tampered = b'{"test": "tampered"}'
        with patch.dict("os.environ", {"SHOPIFY_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            assert verify_shopify_webhook(tampered, sig) is False

    def test_no_secret_configured_returns_true(self):
        """Without a secret configured, validation is skipped (dev mode)."""
        body = b'anything'
        with patch.dict("os.environ", {}, clear=True):
            # Remove the key if present
            import os
            os.environ.pop("SHOPIFY_WEBHOOK_SECRET", None)
            assert verify_shopify_webhook(body, "any_sig") is True


# ── Session event endpoint ────────────────────────────────────────────────────

class TestSessionEvent:
    def test_returns_400_without_session_id(self):
        resp = client.post("/webhook/session-event", json={"event": "page_viewed"})
        assert resp.status_code == 400

    def test_accepts_page_viewed_event(self):
        resp = client.post("/webhook/session-event", json={
            "session_id": "sess_001",
            "event": "page_viewed",
            "url": "/products/serum",
            "timestamp": 1717000000,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_policy_page_sets_flag(self):
        session_id = "sess_policy_test"
        client.post("/webhook/session-event", json={
            "session_id": session_id,
            "event": "page_viewed",
            "url": "/policies/refund-policy",
            "timestamp": 1717000000,
        })
        from src.api.main import session_get
        session = session_get(session_id)
        assert session is not None
        assert session.get("visited_return_policy") is True

    def test_cart_removal_increments_counter(self):
        session_id = "sess_cart_test"
        for _ in range(2):
            client.post("/webhook/session-event", json={
                "session_id": session_id,
                "event": "cart_updated",
                "action": "removed",
                "timestamp": 1717000000,
            })
        from src.api.main import session_get
        session = session_get(session_id)
        assert session is not None
        assert session.get("items_added_and_removed") == 2

    def test_converted_session_is_flagged(self):
        session_id = "sess_converted"
        client.post("/webhook/session-event", json={
            "session_id": session_id,
            "event": "checkout_completed",
            "timestamp": 1717000000,
        })
        from src.api.main import session_get
        session = session_get(session_id)
        assert session is not None
        assert session.get("converted") is True

    def test_missing_session_returns_none(self):
        from src.api.main import session_get
        assert session_get("nonexistent_session_xyz") is None


# ── Cart abandoned endpoint ───────────────────────────────────────────────────

class TestCartAbandoned:
    def _post_webhook(self, payload: dict, secret: str = "") -> object:
        body = json.dumps(payload).encode()
        headers = {}
        if secret:
            headers["X-Shopify-Hmac-Sha256"] = make_shopify_signature(body, secret)
        return client.post(
            "/webhook/cart-abandoned",
            content=body,
            headers={"Content-Type": "application/json", **headers},
        )

    def test_returns_200_immediately(self):
        with patch("src.api.main.run_classification", new_callable=AsyncMock):
            resp = self._post_webhook(ABANDONED_CART_PAYLOAD)
        assert resp.status_code == 200

    def test_returns_queued_status(self):
        with patch("src.api.main.run_classification", new_callable=AsyncMock):
            resp = self._post_webhook(ABANDONED_CART_PAYLOAD)
        assert resp.json()["status"] == "queued"

    def test_rejects_invalid_signature(self):
        with patch.dict("os.environ", {"SHOPIFY_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            body = json.dumps(ABANDONED_CART_PAYLOAD).encode()
            resp = client.post(
                "/webhook/cart-abandoned",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Hmac-Sha256": "bad_signature",
                },
            )
        assert resp.status_code == 401

    def test_accepts_valid_signature(self):
        with patch.dict("os.environ", {"SHOPIFY_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            with patch("src.api.main.run_classification", new_callable=AsyncMock):
                resp = self._post_webhook(ABANDONED_CART_PAYLOAD, secret=WEBHOOK_SECRET)
        assert resp.status_code == 200
