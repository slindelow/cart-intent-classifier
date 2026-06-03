#!/usr/bin/env python3
"""
Cart Abandonment Intent Classifier — CLI entry point.
Classification logic lives in src/classifier/engine.py.

Usage:
    python classify.py                          # uses data/sample_customers.json
    python classify.py --input path/to/file.json
    python classify.py --verbose
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)
if not os.getenv("ANTHROPIC_API_KEY"):
    load_dotenv(override=True)

import argparse

from src.classifier.engine import classify_customers

CONFIG_PATH = BASE_DIR / "config.json"
DATA_PATH   = BASE_DIR / "data" / "sample_customers.json"
OUTPUT_DIR  = BASE_DIR / "output"


# ── Load ──────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_customers(input_path: Path) -> list[dict]:
    with open(input_path) as f:
        return json.load(f)


# ── Output ────────────────────────────────────────────────────────────────────

INTENT_COLOURS = {
    "price_sensitive": "\033[93m",
    "trust_gap":       "\033[94m",
    "distracted":      "\033[92m",
    "research_phase":  "\033[95m",
}
RESET = "\033[0m"
BOLD  = "\033[1m"


def print_results(results: list[dict], run_timestamp: str) -> None:
    print(f"\n{BOLD}Cart Abandonment Intent Classifier — {run_timestamp}{RESET}\n")

    col_w = {"id": 10, "intent": 16, "confidence": 10, "flow": 38}
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
    with open(output_path, "w") as f:
        json.dump({"run": run_timestamp, "total_customers": len(results), "classifications": results}, f, indent=2)
    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify Shopify cart abandoners into Klaviyo flow buckets."
    )
    parser.add_argument("--input", "-i", type=Path, default=DATA_PATH)
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    config    = load_config()
    customers = load_customers(args.input)

    if args.verbose:
        print(f"Loaded {len(customers)} customer profiles from {args.input}")

    try:
        results = classify_customers(customers, config)
    except EnvironmentError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    output_path = save_results(results, run_timestamp)
    print_results(results, run_timestamp)
    print(f"Results saved → {output_path}\n")


if __name__ == "__main__":
    main()
