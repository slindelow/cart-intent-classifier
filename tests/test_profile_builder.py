"""
Tests for src/classifier/profile_builder.py
"""

import pytest
from src.classifier.profile_builder import build_profile, log_profile_quality


BASE_ARGS = dict(
    customer_id="cust_001",
    customer_email="test@example.com",
    cart_value=150.0,
    cart_items=["face serum", "moisturiser"],
)


class TestBuildProfile:
    def test_required_fields_always_present(self):
        profile = build_profile(**BASE_ARGS)
        required = [
            "customer_id", "cart_value", "cart_items",
            "customer_type", "purchase_count", "discount_usage_rate",
            "visited_return_policy", "visited_shipping_info",
            "items_added_and_removed",
        ]
        for field in required:
            assert field in profile, f"Missing field: {field}"

    def test_defaults_without_data_sources(self):
        profile = build_profile(**BASE_ARGS)
        assert profile["customer_type"] == "first_time"
        assert profile["purchase_count"] == 0
        assert profile["discount_usage_rate"] == 0.0
        assert profile["visited_return_policy"] is False
        assert profile["items_added_and_removed"] == 0

    def test_shopify_data_applied(self):
        shopify = {
            "customer_type": "returning",
            "purchase_count": 5,
            "avg_order_value": 95.0,
            "discount_usage_rate": 0.40,
            "days_since_last_purchase": 20,
        }
        profile = build_profile(**BASE_ARGS, shopify_data=shopify)
        assert profile["customer_type"] == "returning"
        assert profile["purchase_count"] == 5
        assert profile["avg_order_value"] == 95.0
        assert profile["discount_usage_rate"] == 0.40

    def test_klaviyo_data_applied(self):
        klaviyo = {"email_open_rate": 0.45, "profile_id": "kl_abc123"}
        profile = build_profile(**BASE_ARGS, klaviyo_data=klaviyo)
        assert profile["email_open_rate"] == 0.45
        assert profile["_klaviyo_profile_id"] == "kl_abc123"

    def test_session_data_applied(self):
        session = {
            "visited_return_policy": True,
            "visited_shipping_info": True,
            "items_added_and_removed": 2,
            "time_on_checkout_seconds": 180,
        }
        profile = build_profile(**BASE_ARGS, session=session)
        assert profile["visited_return_policy"] is True
        assert profile["visited_shipping_info"] is True
        assert profile["items_added_and_removed"] == 2
        assert profile["time_on_checkout_seconds"] == 180

    def test_all_sources_merged(self):
        shopify = {"customer_type": "returning", "purchase_count": 3,
                   "avg_order_value": 80.0, "discount_usage_rate": 0.33,
                   "days_since_last_purchase": 45}
        klaviyo = {"email_open_rate": 0.30, "profile_id": "kl_xyz"}
        session = {"visited_return_policy": True, "visited_shipping_info": False,
                   "items_added_and_removed": 1, "time_on_checkout_seconds": 90}

        profile = build_profile(**BASE_ARGS, shopify_data=shopify,
                                klaviyo_data=klaviyo, session=session)

        assert profile["customer_type"] == "returning"
        assert profile["email_open_rate"] == 0.30
        assert profile["visited_return_policy"] is True
        assert profile["time_on_checkout_seconds"] == 90

    def test_cart_value_and_items_preserved(self):
        profile = build_profile(**BASE_ARGS)
        assert profile["cart_value"] == 150.0
        assert profile["cart_items"] == ["face serum", "moisturiser"]

    def test_klaviyo_profile_id_not_set_without_klaviyo(self):
        profile = build_profile(**BASE_ARGS)
        assert "_klaviyo_profile_id" not in profile


class TestLogProfileQuality:
    def test_runs_without_error_on_full_profile(self):
        profile = build_profile(
            customer_id="c1",
            customer_email="x@x.com",
            cart_value=100.0,
            cart_items=["item"],
            shopify_data={"customer_type": "returning", "purchase_count": 2,
                          "avg_order_value": 80.0, "discount_usage_rate": 0.5,
                          "days_since_last_purchase": 10},
            klaviyo_data={"email_open_rate": 0.4},
            session={"time_on_checkout_seconds": 60, "visited_return_policy": True},
        )
        # Should not raise
        log_profile_quality(profile)

    def test_runs_without_error_on_empty_profile(self):
        profile = build_profile(customer_id="c1", customer_email="x@x.com",
                                cart_value=50.0, cart_items=[])
        log_profile_quality(profile)
