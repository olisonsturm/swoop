"""Manual pre-release contract checks against live Google Flights responses.

These tests are intentionally marked ``live`` and excluded from normal runs.
Set ``SWOOP_UPDATE_LIVE_CORPUS=1`` to save fresh raw payloads alongside simple
metadata under ``tests/fixtures/live_corpus`` while running the suite.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path

import pytest

import swoop
import swoop.rpc as rpc
from swoop.decoder import Flight, Itinerary, SearchResult


pytestmark = pytest.mark.live

LIVE_FIXTURES = Path(__file__).parent / "fixtures" / "live_corpus"


def _future_date(days: int = 45) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _maybe_save_payload(name: str, text: str, metadata: dict[str, object]) -> None:
    if os.environ.get("SWOOP_UPDATE_LIVE_CORPUS") != "1":
        return
    LIVE_FIXTURES.mkdir(parents=True, exist_ok=True)
    (LIVE_FIXTURES / f"{name}.txt").write_text(text)
    (LIVE_FIXTURES / f"{name}.json").write_text(json.dumps(metadata, indent=2, sort_keys=True))


def _capture_shopping_response(origin: str, destination: str, query_date: str) -> str:
    encoded = rpc._build_f_req(origin, destination, query_date, max_stops=0)
    res = rpc._http_post(
        rpc.SHOPPING_RPC_URL,
        content=f"f.req={encoded}".encode(),
        timeout=30,
        retries=1,
    )
    return res.text


def _capture_booking_response(itinerary: Itinerary) -> str:
    selected_legs = rpc._build_selected_legs(itinerary)
    if not itinerary.booking_token or not selected_legs:
        return ""
    dep = itinerary.departure_date
    query_date = f"{dep[0]:04d}-{dep[1]:02d}-{dep[2]:02d}"
    filters = rpc._build_filters(
        origin=itinerary.departure_airport_code,
        destination=itinerary.arrival_airport_code,
        date=query_date,
        cabin="economy",
        adults=1,
        sort=rpc.SORT_DEPARTURE_TIME,
    )
    encoded = rpc._build_booking_f_req(itinerary.booking_token, filters[1], selected_legs)
    if not encoded:
        return ""
    res = rpc._http_post(
        rpc.BOOKING_RPC_URL,
        content=f"f.req={encoded}".encode(),
        timeout=30,
        retries=1,
    )
    return res.text


class TestShoppingContract:
    """Verify raw shopping responses still parse into expected decoded data."""

    def test_raw_shopping_response_decodes_and_can_be_saved(self):
        query_date = _future_date()
        text = _capture_shopping_response("JFK", "LAX", query_date)
        _maybe_save_payload(
            "shopping_jfk_lax",
            text,
            {
                "captured_at": date.today().isoformat(),
                "origin": "JFK",
                "destination": "LAX",
                "date": query_date,
                "kind": "shopping",
            },
        )

        result = rpc._parse_rpc_response(text)
        assert result is not None
        assert isinstance(result, SearchResult)
        assert len(result.best) + len(result.other) > 0

    def test_oneway_itineraries_have_expected_fields(self):
        query_date = _future_date()
        result = swoop.search("JFK", "LAX", query_date, max_stops=0)
        if result is None:
            pytest.skip("No results returned")

        all_itins = result.best + result.other
        assert len(all_itins) > 0, "Expected at least one itinerary"

        for itin in all_itins[:3]:
            assert isinstance(itin, Itinerary)
            assert itin.airline_code != ""
            assert len(itin.flights) >= 1
            assert itin.departure_airport_code != ""
            assert itin.arrival_airport_code != ""
            assert itin.travel_time > 0
            assert itin.price is not None

            for flight in itin.flights:
                assert isinstance(flight, Flight)
                assert flight.airline != ""
                assert flight.flight_number != ""
                assert flight.departure_airport_code != ""
                assert flight.arrival_airport_code != ""


class TestBookingContract:
    """Verify raw booking responses still parse into usable fare options."""

    def test_booking_results_parseable_and_can_be_saved(self):
        query_date = _future_date()
        result = swoop.search("JFK", "LAX", query_date, max_stops=0)
        if result is None:
            pytest.skip("No results returned")

        all_itins = result.best + result.other
        if not all_itins:
            pytest.skip("No itineraries to check")

        itinerary = next((itin for itin in all_itins if itin.booking_token and rpc._build_selected_legs(itin)), None)
        if itinerary is None:
            pytest.skip("No itinerary with booking token + selected legs")

        text = _capture_booking_response(itinerary)
        if not text:
            pytest.skip("Could not capture booking response")

        _maybe_save_payload(
            "booking_jfk_lax",
            text,
            {
                "captured_at": date.today().isoformat(),
                "origin": itinerary.departure_airport_code,
                "destination": itinerary.arrival_airport_code,
                "date": query_date,
                "kind": "booking",
            },
        )

        options = rpc._parse_booking_rpc_response(text)
        assert isinstance(options, list)
        if not options:
            pytest.skip("No booking options returned")

        for option in options[:3]:
            assert option.price > 0
            assert option.brand_label or option.brand_code
            assert option.fare_family in {"basic", "standard", "enhanced", "premium", "unknown"}
            assert option._cabin_bucket in {"economy", "premium-economy", "business", "first", "unknown"}
