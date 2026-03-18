#!/usr/bin/env python3
"""Capture live Google Flights responses for different countries/currencies.

Saves the decoded inner JSON (same format as existing fixtures in
tests/fixtures/responses/) so tests can replay through decode_result().

Usage:
    python scripts/capture_currency_fixtures.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "responses"

# Routes chosen for short/cheap domestic flights in each country
CAPTURES = [
    {
        "name": "shopping_oneway_gb",
        "country": "GB",
        "origin": "LHR",
        "destination": "EDI",
        "date": "2026-07-15",
        "expected_currency": "GBP",
    },
    {
        "name": "shopping_oneway_jp",
        "country": "JP",
        "origin": "NRT",
        "destination": "KIX",
        "date": "2026-07-15",
        "expected_currency": "JPY",
    },
    {
        "name": "shopping_oneway_in",
        "country": "IN",
        "origin": "DEL",
        "destination": "BOM",
        "date": "2026-07-15",
        "expected_currency": "INR",
    },
]


def main():
    import swoop
    from swoop.rpc import _parse_rpc_response, _search_from_legs, _normalize_rpc_leg

    for capture in CAPTURES:
        name = capture["name"]
        print(f"\n{'='*60}")
        print(f"Capturing: {name} ({capture['origin']}->{capture['destination']}, country={capture['country']})")
        print(f"{'='*60}")

        try:
            result = swoop.search_raw(
                capture["origin"],
                capture["destination"],
                capture["date"],
                country=capture["country"],
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        if result is None or (not result.best and not result.other):
            print(f"  No results returned")
            continue

        # Save the raw decoded data (same format as existing fixtures)
        fixture_path = FIXTURES_DIR / f"{name}.json"
        with open(fixture_path, "w") as f:
            json.dump(result._raw, f, indent=2, ensure_ascii=False)
        print(f"  Saved to {fixture_path}")

        # Print diagnostic info
        all_itins = result.best + result.other
        print(f"  {len(result.best)} best + {len(result.other)} other itineraries")

        for i, itin in enumerate(all_itins[:3]):
            price = itin.price
            direct = itin.direct_price
            pb_price = itin.price_info.price if itin.price_info else None
            currency = itin.price_info.currency if itin.price_info else None
            airline = itin.airline_code
            flights_str = " -> ".join(
                f"{f.departure_airport_code}-{f.arrival_airport_code}"
                for f in itin.flights
            )
            print(f"  [{i}] {airline} {flights_str}")
            print(f"      price={price}, direct_price={direct}, pb_price={pb_price}, currency={currency}")

        # Validate currency
        currencies = {
            itin.price_info.currency
            for itin in all_itins
            if itin.price_info and itin.price_info.currency
        }
        expected = capture["expected_currency"]
        if expected in currencies:
            print(f"  CURRENCY OK: found {expected}")
        else:
            print(f"  CURRENCY MISMATCH: expected {expected}, got {currencies}")

    print("\nDone.")


if __name__ == "__main__":
    main()
