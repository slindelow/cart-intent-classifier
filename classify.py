#!/usr/bin/env python3
"""
Cart Abandonment Intent Classifier
Classifies Shopify cart abandoners into intent buckets and maps to Klaviyo flows.
Prototype — June 2026.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# ── Config ──────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

# Fallback: try loading from current working directory too
if not os.getenv("ANTHROPIC_API_KEY"):
    load_dotenv(override=True)
CONFIG_PATH = BASE_DIR / "config.json"
DATA_PATH = BASE_DIR / "data" / "sample_customers.json"
OUTPUT_DIR = BASE_DIR / "output"


# ── Load ─────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_customers(input_path: Path) -> list[dict]:
    with open(input_path) as f:
        return json.load(f)


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
    # Strip notes from customer data before sending to Claude
    clean = [{k: v for k, v in c.items() if k != "note"} for c in customers]
    return f"Classify these {len(clean)} cart abandoners:\n\n{json.dumps(clean, indent=2)}"


# ── Classify ─────────────────────────────────────────────────────────────────

def classify(customers: list[dict], config: dict, verbose: bool = False) -> list[dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    if verbose:
        print(f"  Sending {len(customers)} profiles to Claude...\n")

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": build_user_message(customers)
            }
        ],
        system=build_system_prompt(config)
    )

    raw = message.content[0].text.strip()

    try:
        results = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error parsing Claude response: {e}")
        print("Raw response:")
        print(raw)
        sys.exit(1)

    # Attach the Klaviyo flow name from config if Claude used the intent key
    intent_map = config["intents"]
    for result in results:
        intent_key = result.get("intent")
        if intent_key in intent_map and not result.get("klaviyo_flow"):
            result["klaviyo_flow"] = intent_map[intent_key]["klaviyo_flow"]

    return results


# ── Output ───────────────────────────────────────────────────────────────────

INTENT_COLOURS = {
    "price_sensitive": "\033[93m",   # yellow
    "trust_gap":       "\033[94m",   # blue
    "distracted":      "\033[92m",   # green
    "research_phase":  "\033[95m",   # magenta
}
RESET = "\033[0m"
BOLD  = "\033[1m"


def print_results(results: list[dict], run_timestamp: str) -> None:
    print(f"\n{BOLD}Cart Abandonment Intent Classifier — {run_timestamp}{RESET}\n")

    col_w = {
        "id":         10,
        "intent":     16,
        "confidence": 10,
        "flow":       38,
        "reasoning":  0,   # fills the rest
    }

    header = (
        f"  {'ID':<{col_w['id']}}"
        f"{'INTENT':<{col_w['intent']}}"
        f"{'CONF':<{col_w['confidence']}}"
        f"{'KLAVIYO FLOW':<{col_w['flow']}}"
        f"REASONING"
    )
    print(BOLD + header + RESET)
    print("  " + "─" * (len(header) - 2))

    for r in results:
        intent    = r.get("intent", "unknown")
        colour    = INTENT_COLOURS.get(intent, "")
        conf      = r.get("confidence", 0.0)
        flow      = r.get("klaviyo_flow", "—")
        reasoning = r.get("reasoning", "—")

        # Truncate flow name if too long for the column
        if len(flow) > col_w["flow"] - 2:
            flow = flow[:col_w["flow"] - 5] + "..."

        print(
            f"  {r.get('customer_id', '?'):<{col_w['id']}}"
            f"{colour}{intent:<{col_w['intent']}}{RESET}"
            f"{conf:<{col_w['confidence']}.2f}"
            f"{flow:<{col_w['flow']}}"
            f"{reasoning}"
        )

    print()

    # Summary counts
    from collections import Counter
    counts = Counter(r.get("intent") for r in results)
    print(f"{BOLD}Summary:{RESET}")
    for intent, count in sorted(counts.items()):
        colour = INTENT_COLOURS.get(intent, "")
        print(f"  {colour}{intent:<20}{RESET} {count} customer{'s' if count != 1 else ''}")
    print()


def save_results(results: list[dict], run_timestamp: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = f"{run_timestamp.replace(':', '-').replace(' ', '_')}.json"
    output_path = OUTPUT_DIR / filename

    payload = {
        "run": run_timestamp,
        "total_customers": len(results),
        "classifications": results
    }

    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)

    return output_path


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify Shopify cart abandoners into Klaviyo flow buckets using Claude."
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=DATA_PATH,
        help=f"Path to customer JSON file (default: {DATA_PATH})"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show extra output during processing"
    )
    return parser.parse_args()


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    config    = load_config()
    customers = load_customers(args.input)

    if args.verbose:
        print(f"Loaded {len(customers)} customer profiles from {args.input}")

    results      = classify(customers, config, verbose=args.verbose)
    output_path  = save_results(results, run_timestamp)

    print_results(results, run_timestamp)
    print(f"Results saved → {output_path}\n")


if __name__ == "__main__":
    main()
