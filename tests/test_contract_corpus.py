"""Offline contract corpus replay for shopping and booking payloads."""

from __future__ import annotations

import json
from pathlib import Path

from swoop._booking import _parse_booking_rpc_response
from swoop.decoder import decode_result


FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "contract_corpus_manifest.json").read_text())


def test_manifest_has_version_and_cases():
    assert MANIFEST["version"]
    assert MANIFEST["shopping"]
    assert MANIFEST["booking"]


def test_shopping_corpus_cases_decode_critical_fields():
    for case in MANIFEST["shopping"]:
        data = json.loads((FIXTURES / case["path"]).read_text())
        result = decode_result(data)

        assert len(result.best) == case["expected"]["best_count"]
        assert len(result.other) == case["expected"]["other_count"]
        if result.best:
            assert result.best[0].airline_code == case["expected"]["first_airline_code"]
            assert result.best[0].flights
            assert result.best[0].price is not None


def test_booking_corpus_cases_parse_critical_fields():
    for case in MANIFEST["booking"]:
        text = (FIXTURES / case["path"]).read_text()
        options = _parse_booking_rpc_response(text, registry_version=case["registry_version"])

        assert [option.price for option in options] == case["expected"]["prices"]
        assert [option.brand_label for option in options] == case["expected"]["brands"]
        assert [option._cabin_bucket for option in options] == case["expected"]["cabin_buckets"]
        assert [option._registry_version for option in options] == [case["registry_version"]] * len(options)
