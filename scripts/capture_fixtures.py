#!/usr/bin/env python3
"""Capture live Google Flights responses and generate test fixtures + manifest.

Runs a predefined set of search scenarios against the live API, saves the
decoded response JSON, and generates a manifest with expected values
extracted from the actual data. The manifest drives the offline replay
tests in test_contract_corpus.py.

Usage:
    python scripts/capture_fixtures.py              # capture all scenarios
    python scripts/capture_fixtures.py --only us_oneway,gb_oneway  # capture specific ones

The script is idempotent — re-running it refreshes fixtures and manifest
entries for all captured scenarios.
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
RESPONSES_DIR = FIXTURES_DIR / "responses"
MANIFEST_PATH = FIXTURES_DIR / "contract_corpus_manifest.json"


def _future_date(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS = [
    # --- Domestic US (USD) ---
    {
        "id": "shopping_domestic_oneway_v2",
        "label": "US domestic one-way (USD)",
        "filename": "shopping_oneway_us.json",
        "search": {
            "origin": "JFK",
            "destination": "LAX",
            "date_offset": 60,
        },
        "expected_currency": "USD",
    },
    {
        "id": "shopping_domestic_roundtrip_v2",
        "label": "US domestic roundtrip (USD)",
        "filename": "shopping_roundtrip_us.json",
        "search": {
            "origin": "JFK",
            "destination": "LAX",
            "date_offset": 60,
            "return_offset": 67,
        },
        "expected_currency": "USD",
    },
    # --- UK (GBP) ---
    {
        "id": "shopping_gb_oneway_v1",
        "label": "UK domestic one-way (GBP)",
        "filename": "shopping_oneway_gb.json",
        "search": {
            "origin": "LHR",
            "destination": "EDI",
            "date_offset": 60,
            "country": "GB",
        },
        "expected_currency": "GBP",
    },
    # --- Japan (JPY) ---
    {
        "id": "shopping_jp_oneway_v1",
        "label": "Japan domestic one-way (JPY)",
        "filename": "shopping_oneway_jp.json",
        "search": {
            "origin": "NRT",
            "destination": "KIX",
            "date_offset": 60,
            "country": "JP",
        },
        "expected_currency": "JPY",
    },
    # --- India (INR) ---
    {
        "id": "shopping_in_oneway_v1",
        "label": "India domestic one-way (INR)",
        "filename": "shopping_oneway_in.json",
        "search": {
            "origin": "DEL",
            "destination": "BOM",
            "date_offset": 60,
            "country": "IN",
        },
        "expected_currency": "INR",
    },
    # --- Europe (EUR) ---
    {
        "id": "shopping_eu_oneway_v1",
        "label": "Europe one-way (EUR)",
        "filename": "shopping_oneway_eu.json",
        "search": {
            "origin": "CDG",
            "destination": "FCO",
            "date_offset": 60,
            "country": "FR",
        },
        "expected_currency": "EUR",
    },
    # --- Transatlantic (USD) ---
    {
        "id": "shopping_transatlantic_oneway_v1",
        "label": "Transatlantic one-way (USD)",
        "filename": "shopping_oneway_transatlantic.json",
        "search": {
            "origin": "JFK",
            "destination": "LHR",
            "date_offset": 60,
        },
        "expected_currency": "USD",
    },
    # --- South Korea (KRW) ---
    {
        "id": "shopping_kr_oneway_v1",
        "label": "Korea domestic one-way (KRW)",
        "filename": "shopping_oneway_kr.json",
        "search": {
            "origin": "ICN",
            "destination": "CJU",
            "date_offset": 60,
            "country": "KR",
        },
        "expected_currency": "KRW",
    },
    # --- Canada (CAD) ---
    {
        "id": "shopping_ca_oneway_v1",
        "label": "Canada domestic one-way (CAD)",
        "filename": "shopping_oneway_ca.json",
        "search": {
            "origin": "YYZ",
            "destination": "YVR",
            "date_offset": 60,
            "country": "CA",
        },
        "expected_currency": "CAD",
    },
    # --- Australia (AUD) ---
    {
        "id": "shopping_au_oneway_v1",
        "label": "Australia domestic one-way (AUD)",
        "filename": "shopping_oneway_au.json",
        "search": {
            "origin": "SYD",
            "destination": "MEL",
            "date_offset": 60,
            "country": "AU",
        },
        "expected_currency": "AUD",
    },
    # --- Brazil (BRL) ---
    {
        "id": "shopping_br_oneway_v1",
        "label": "Brazil domestic one-way (BRL)",
        "filename": "shopping_oneway_br.json",
        "search": {
            "origin": "GRU",
            "destination": "GIG",
            "date_offset": 60,
            "country": "BR",
        },
        "expected_currency": "BRL",
    },
]


def _run_search(scenario: dict) -> dict | None:
    """Run a live search and return the raw decoded data + metadata."""
    import swoop

    search_params = scenario["search"]
    origin = search_params["origin"]
    destination = search_params["destination"]
    search_date = _future_date(search_params["date_offset"])
    country = search_params.get("country")
    return_date = _future_date(search_params["return_offset"]) if "return_offset" in search_params else None

    kwargs = {
        "country": country,
    }
    if return_date:
        kwargs["return_date"] = return_date

    try:
        result = swoop.search_raw(origin, destination, search_date, **kwargs)
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

    if result is None or (not result.best and not result.other):
        print(f"  No results returned")
        return None

    return {
        "raw": result._raw,
        "result": result,
        "search_date": search_date,
        "return_date": return_date,
    }


def _extract_manifest_entry(scenario: dict, result) -> dict:
    """Build a manifest entry from a scenario + live result."""
    all_itins = result.best + result.other
    first_section = "best" if result.best else "other"
    first = result.best[0] if result.best else result.other[0]

    # Extract currency from first itinerary with price_info
    first_currency = None
    for itin in all_itins:
        if itin.price_info and itin.price_info.currency:
            first_currency = itin.price_info.currency
            break

    return {
        "id": scenario["id"],
        "path": f"responses/{scenario['filename']}",
        "expected": {
            "best_count": len(result.best),
            "other_count": len(result.other),
            "first_section": first_section,
            "first_airline_code": first.airline_code,
            "first_origin": first.departure_airport_code,
            "first_destination": first.arrival_airport_code,
            "first_price": first.price,
            "first_flights": len(first.flights),
            "currency": first_currency,
        },
    }


def capture(scenarios: list[dict]) -> None:
    """Capture all scenarios and update manifest."""
    # Load existing manifest
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())
    else:
        manifest = {"version": date.today().isoformat(), "shopping": [], "booking": []}

    # Index existing entries by id
    existing_shopping = {e["id"]: e for e in manifest.get("shopping", [])}

    captured_count = 0
    for scenario in scenarios:
        sid = scenario["id"]
        label = scenario["label"]
        filename = scenario["filename"]
        print(f"\n{'='*60}")
        print(f"[{sid}] {label}")
        print(f"  {scenario['search']['origin']} -> {scenario['search']['destination']}")
        print(f"{'='*60}")

        data = _run_search(scenario)
        if data is None:
            continue

        # Save fixture
        fixture_path = RESPONSES_DIR / filename
        with open(fixture_path, "w") as f:
            json.dump(data["raw"], f, indent=2, ensure_ascii=False)
        print(f"  Saved fixture: {fixture_path.relative_to(FIXTURES_DIR.parent.parent)}")

        # Build manifest entry
        entry = _extract_manifest_entry(scenario, data["result"])
        existing_shopping[sid] = entry
        captured_count += 1

        # Print diagnostics
        result = data["result"]
        all_itins = result.best + result.other
        for i, itin in enumerate(all_itins[:3]):
            currency = itin.price_info.currency if itin.price_info else "?"
            print(f"  [{i}] {itin.airline_code} price={itin.price} currency={currency}")

    # Rebuild manifest shopping list preserving order
    manifest["shopping"] = list(existing_shopping.values())
    manifest["version"] = date.today().isoformat()

    # Write manifest
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nManifest updated: {MANIFEST_PATH.relative_to(FIXTURES_DIR.parent.parent)}")
    print(f"Captured {captured_count}/{len(scenarios)} scenarios")


def main():
    parser = argparse.ArgumentParser(description="Capture live Google Flights fixtures")
    parser.add_argument(
        "--only",
        help="Comma-separated scenario ID substrings to capture (e.g. 'gb,jp')",
    )
    args = parser.parse_args()

    scenarios = SCENARIOS
    if args.only:
        filters = [f.strip() for f in args.only.split(",")]
        scenarios = [s for s in SCENARIOS if any(f in s["id"] for f in filters)]
        if not scenarios:
            print(f"No scenarios match: {args.only}")
            print(f"Available: {', '.join(s['id'] for s in SCENARIOS)}")
            sys.exit(1)

    capture(scenarios)


if __name__ == "__main__":
    main()
