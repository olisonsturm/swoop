"""Offline contract corpus replay for captured Google Flights responses."""

from __future__ import annotations

import json
from pathlib import Path

from swoop._booking import _parse_booking_rpc_response
from swoop.decoder import decode_result


FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURES / "contract_corpus_manifest.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text())


def _first_itinerary(result, section: str):
    bucket = result.best if section == "best" else result.other
    assert bucket, f"Expected at least one itinerary in {section}"
    return bucket[0]


def test_manifest_has_version_and_cases():
    assert MANIFEST["version"]
    assert MANIFEST["shopping"]
    assert MANIFEST["booking"]


def test_manifest_paths_exist():
    for group in ("shopping", "booking"):
        for case in MANIFEST[group]:
            assert (FIXTURES / case["path"]).exists(), f"Missing fixture for {case['id']}"


def test_shopping_corpus_cases_decode_critical_fields():
    for case in MANIFEST["shopping"]:
        data = json.loads((FIXTURES / case["path"]).read_text())
        result = decode_result(data)
        expected = case["expected"]
        first = _first_itinerary(result, expected["first_section"])

        assert len(result.best) == expected["best_count"]
        assert len(result.other) == expected["other_count"]
        assert first.airline_code == expected["first_airline_code"]
        assert first.departure_airport_code == expected["first_origin"]
        assert first.arrival_airport_code == expected["first_destination"]
        assert first.price == expected["first_price"]
        assert len(first.flights) == expected["first_flights"]


def test_booking_corpus_cases_parse_critical_fields():
    for case in MANIFEST["booking"]:
        text = (FIXTURES / case["path"]).read_text()
        expected = case["expected"]
        options = _parse_booking_rpc_response(text, registry_version=case["registry_version"])

        assert [option.price for option in options] == expected["prices"]
        assert [option.brand_label for option in options] == expected["brands"]
        assert [option._cabin_bucket for option in options] == expected["cabin_buckets"]
        assert [option.fare_family for option in options] == expected["fare_families"]
        assert [option._registry_version for option in options] == [case["registry_version"]] * len(options)
