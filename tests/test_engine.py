"""
Tests for src/classifier/engine.py

Run:  python -m pytest tests/ -v
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BASE_DIR = Path(__file__).parent.parent


def load_config() -> dict:
    with open(BASE_DIR / "config.json") as f:
        return json.load(f)


def load_sample_customers() -> list[dict]:
    with open(BASE_DIR / "data" / "sample_customers.json") as f:
        return json.load(f)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def sample_customers():
    return load_sample_customers()


@pytest.fixture
def single_trust_gap_customer():
    return {
        "customer_id": "test_001",
        "customer_type": "first_time",
        "cart_value": 200.00,
        "avg_order_value": None,
        "purchase_count": 0,
        "discount_usage_rate": 0.0,
        "email_open_rate": None,
        "days_since_last_purchase": None,
        "cart_items": ["premium serum"],
        "visited_return_policy": True,
        "visited_shipping_info": True,
        "time_on_checkout_seconds": 300,
        "items_added_and_removed": 0,
    }


@pytest.fixture
def single_price_sensitive_customer():
    return {
        "customer_id": "test_002",
        "customer_type": "returning",
        "cart_value": 250.00,
        "avg_order_value": 90.00,
        "purchase_count": 5,
        "discount_usage_rate": 0.80,
        "email_open_rate": 0.60,
        "days_since_last_purchase": 30,
        "cart_items": ["bundle pack"],
        "visited_return_policy": False,
        "visited_shipping_info": False,
        "time_on_checkout_seconds": 40,
        "items_added_and_removed": 0,
    }


# ── Prompt builder tests ──────────────────────────────────────────────────────

class TestBuildSystemPrompt:
    def test_includes_all_intent_keys(self, config):
        from src.classifier.engine import build_system_prompt
        prompt = build_system_prompt(config)
        for key in config["intents"]:
            assert key in prompt

    def test_includes_brand_context(self, config):
        from src.classifier.engine import build_system_prompt
        prompt = build_system_prompt(config)
        assert config["brand_context"] in prompt

    def test_includes_fallback_intent(self, config):
        from src.classifier.engine import build_system_prompt
        prompt = build_system_prompt(config)
        assert config["fallback_intent"] in prompt

    def test_instructs_json_only_response(self, config):
        from src.classifier.engine import build_system_prompt
        prompt = build_system_prompt(config)
        assert "JSON" in prompt
        assert "markdown" in prompt.lower() or "no markdown" in prompt.lower()


class TestBuildUserMessage:
    def test_strips_note_field(self):
        from src.classifier.engine import build_user_message
        customers = [{"customer_id": "x", "cart_value": 100, "note": "internal note"}]
        msg = build_user_message(customers)
        assert "note" not in msg
        assert "internal note" not in msg

    def test_includes_customer_count(self):
        from src.classifier.engine import build_user_message
        customers = [{"customer_id": f"c{i}"} for i in range(5)]
        msg = build_user_message(customers)
        assert "5" in msg

    def test_valid_json_in_message(self):
        from src.classifier.engine import build_user_message
        customers = [{"customer_id": "c1", "cart_value": 50.0}]
        msg = build_user_message(customers)
        # The JSON portion should be parseable
        json_part = msg.split("\n\n", 1)[-1]
        parsed = json.loads(json_part)
        assert parsed[0]["customer_id"] == "c1"


# ── Classifier tests (with mocked Claude API) ─────────────────────────────────

MOCK_RESPONSE = [
    {
        "customer_id": "test_001",
        "intent": "trust_gap",
        "confidence": 0.92,
        "klaviyo_flow": "cart_abandonment_trust_builder",
        "reasoning": "First-time buyer, high cart, visited policy pages.",
    }
]


def make_mock_message(content: list[dict]) -> MagicMock:
    """Create a mock Anthropic message response."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(content))]
    return mock_msg


@pytest.fixture(autouse=False)
def fake_api_key(monkeypatch):
    """Set a fake API key so the env guard doesn't fire in mocked tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key-for-mocking")


class TestClassifyCustomers:
    @patch("src.classifier.engine.anthropic.Anthropic")
    def test_returns_list_of_results(self, mock_anthropic, fake_api_key, config, single_trust_gap_customer):
        from src.classifier.engine import classify_customers
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = make_mock_message(MOCK_RESPONSE)

        results = classify_customers([single_trust_gap_customer], config)
        assert isinstance(results, list)
        assert len(results) == 1

    @patch("src.classifier.engine.anthropic.Anthropic")
    def test_result_has_required_fields(self, mock_anthropic, fake_api_key, config, single_trust_gap_customer):
        from src.classifier.engine import classify_customers
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = make_mock_message(MOCK_RESPONSE)

        results = classify_customers([single_trust_gap_customer], config)
        r = results[0]
        assert "customer_id" in r
        assert "intent" in r
        assert "confidence" in r
        assert "klaviyo_flow" in r
        assert "reasoning" in r

    @patch("src.classifier.engine.anthropic.Anthropic")
    def test_intent_is_valid_bucket(self, mock_anthropic, fake_api_key, config, single_trust_gap_customer):
        from src.classifier.engine import classify_customers
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = make_mock_message(MOCK_RESPONSE)

        results = classify_customers([single_trust_gap_customer], config)
        valid_intents = set(config["intents"].keys())
        assert results[0]["intent"] in valid_intents

    @patch("src.classifier.engine.anthropic.Anthropic")
    def test_strips_markdown_fences(self, mock_anthropic, fake_api_key, config, single_trust_gap_customer):
        from src.classifier.engine import classify_customers
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        fenced = MagicMock()
        fenced.content = [MagicMock(text=f"```json\n{json.dumps(MOCK_RESPONSE)}\n```")]
        mock_client.messages.create.return_value = fenced

        results = classify_customers([single_trust_gap_customer], config)
        assert results[0]["intent"] == "trust_gap"

    @patch("src.classifier.engine.anthropic.Anthropic")
    def test_raises_on_invalid_json(self, mock_anthropic, fake_api_key, config, single_trust_gap_customer):
        from src.classifier.engine import classify_customers
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        broken = MagicMock()
        broken.content = [MagicMock(text="this is not json")]
        mock_client.messages.create.return_value = broken

        with pytest.raises(ValueError, match="invalid JSON"):
            classify_customers([single_trust_gap_customer], config)

    def test_raises_without_api_key(self, config, single_trust_gap_customer, monkeypatch):
        from src.classifier.engine import classify_customers
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            classify_customers([single_trust_gap_customer], config)
