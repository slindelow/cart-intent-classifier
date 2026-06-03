#!/usr/bin/env python3
"""
Classifier engine — core Claude API logic extracted from classify.py.
Importable by the FastAPI webhook handler and usable standalone via classify.py.
"""

import json
import os

import anthropic

# ── Prompt ───────────────────────────────────────────────────────────────────

def build_system_prompt(config: dict) -> str:
    intents = config["intents"]
    brand_context = config["brand_context"]
    fallback = config["fallback_intent"]

    intent_descriptions = "\n".join(
        f'- "{key}": {val["description"]}'
        for key, val in intents.items()
    )

    return f"""You are a Klaviyo flow routing agent for a Shopify ecommerce brand.

Brand context: {brand_context}

Your job is to classify each cart abandoner's intent based on their customer profile signals,
then assign them to the correct Klaviyo recovery flow.

Intent options:
{intent_descriptions}

For each customer, return a JSON object with:
- customer_id (string): the customer's ID exactly as provided
- intent (string): one of the four intent keys above
- confidence (float): your confidence score between 0.0 and 1.0
- klaviyo_flow (string): the exact flow name to trigger
- reasoning (string): one clear sentence explaining the classification

If signals are genuinely ambiguous, use "{fallback}" as the intent.

Respond ONLY with a valid JSON array of classification objects — no markdown, no explanation outside the JSON."""


def build_user_message(customers: list[dict]) -> str:
    clean = [{k: v for k, v in c.items() if k != "note"} for c in customers]
    return f"Classify these {len(clean)} cart abandoners:\n\n{json.dumps(clean, indent=2)}"


# ── Classify ─────────────────────────────────────────────────────────────────

def classify_customers(customers: list[dict], config: dict) -> list[dict]:
    """
    Classify a list of customer profiles into intent buckets.

    Args:
        customers: List of customer profile dicts matching the schema in
                   data/sample_customers.json
        config:    Loaded config.json dict

    Returns:
        List of classification dicts:
        [{ customer_id, intent, confidence, klaviyo_flow, reasoning }, ...]
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": build_user_message(customers)}],
        system=build_system_prompt(config),
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]          # drop opening fence line
        raw = raw.rsplit("```", 1)[0].strip()  # drop closing fence

    try:
        results = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw response:\n{raw}")

    # Ensure klaviyo_flow is always populated from config if Claude omitted it
    intent_map = config["intents"]
    for result in results:
        intent_key = result.get("intent")
        if intent_key in intent_map and not result.get("klaviyo_flow"):
            result["klaviyo_flow"] = intent_map[intent_key]["klaviyo_flow"]

    return results


def classify_single(customer: dict, config: dict) -> dict:
    """Convenience wrapper for classifying a single customer."""
    results = classify_customers([customer], config)
    return results[0]
