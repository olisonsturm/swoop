"""Tests for flight number parsing, matching, and search() flight_number param."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import swoop  # noqa: E402
from swoop._validate import parse_flight_number  # noqa: E402
from swoop import SearchResult, TripLeg, TripOption  # noqa: E402
from swoop.decoder import (  # noqa: E402
    Codeshare,
    Segment,
    Itinerary,
    itinerary_matches_flight,
)

from tests.factories import make_itinerary  # noqa: E402


# ---------------------------------------------------------------------------
# parse_flight_number
# ---------------------------------------------------------------------------


class TestParseFlightNumber:
    def test_carrier_space_number(self):
        assert parse_flight_number("DL 171") == ("DL", "171")

    def test_carrier_no_space(self):
        assert parse_flight_number("DL171") == ("DL", "171")

    def test_digit_letter_carrier(self):
        assert parse_flight_number("9W 302") == ("9W", "302")

    def test_digit_letter_carrier_no_space(self):
        assert parse_flight_number("9W302") == ("9W", "302")

    def test_letter_digit_carrier(self):
        assert parse_flight_number("G4 100") == ("G4", "100")

    def test_letter_digit_carrier_no_space(self):
        assert parse_flight_number("G4100") == ("G4", "100")

    def test_number_only(self):
        assert parse_flight_number("171") == (None, "171")

    def test_single_digit(self):
        assert parse_flight_number("1") == (None, "1")

    def test_four_digit_number(self):
        assert parse_flight_number("1234") == (None, "1234")

    def test_lowercase_normalized(self):
        assert parse_flight_number("dl 171") == ("DL", "171")
        assert parse_flight_number("dl171") == ("DL", "171")

    def test_leading_zeros_stripped(self):
        assert parse_flight_number("DL 0171") == ("DL", "171")
        assert parse_flight_number("0171") == (None, "171")

    def test_all_zeros(self):
        assert parse_flight_number("DL 0000") == ("DL", "0")
        assert parse_flight_number("0000") == (None, "0")

    def test_with_whitespace(self):
        assert parse_flight_number("  DL 171  ") == ("DL", "171")

    def test_suffix_ignored_in_match(self):
        # Operational suffix like "A" (delayed past midnight) is accepted
        assert parse_flight_number("DL171A") == ("DL", "171")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_flight_number("")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="must be a string"):
            parse_flight_number(171)  # type: ignore[arg-type]

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_flight_number("not-a-flight")

    def test_too_many_digits_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_flight_number("DL 12345")

    def test_double_digit_carrier_rejected(self):
        # DD pattern is not valid IATA airline code
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_flight_number("12 345")


# ---------------------------------------------------------------------------
# itinerary_matches_flight
# ---------------------------------------------------------------------------


class TestItineraryMatchesFlight:
    def test_operating_flight_match(self):
        itin = make_itinerary(Segment(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, "DL", "171") is True

    def test_operating_flight_wrong_number(self):
        itin = make_itinerary(Segment(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, "DL", "172") is False

    def test_operating_flight_wrong_carrier(self):
        itin = make_itinerary(Segment(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, "UA", "171") is False

    def test_carrier_none_matches_any(self):
        itin = make_itinerary(Segment(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, None, "171") is True

    def test_carrier_none_wrong_number(self):
        itin = make_itinerary(Segment(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, None, "172") is False

    def test_codeshare_match(self):
        itin = make_itinerary(
            Segment(
                airline="DL",
                flight_number="171",
                codeshares=[Codeshare(airline_code="KL", flight_number="6050")],
            )
        )
        assert itinerary_matches_flight(itin, "KL", "6050") is True

    def test_codeshare_carrier_none(self):
        itin = make_itinerary(
            Segment(
                airline="DL",
                flight_number="171",
                codeshares=[Codeshare(airline_code="KL", flight_number="6050")],
            )
        )
        assert itinerary_matches_flight(itin, None, "6050") is True

    def test_multi_segment_any_match(self):
        itin = make_itinerary(
            Segment(airline="AA", flight_number="100"),
            Segment(airline="AA", flight_number="200"),
        )
        assert itinerary_matches_flight(itin, "AA", "200") is True

    def test_multi_segment_no_match(self):
        itin = make_itinerary(
            Segment(airline="AA", flight_number="100"),
            Segment(airline="AA", flight_number="200"),
        )
        assert itinerary_matches_flight(itin, "AA", "300") is False

    def test_empty_flights(self):
        itin = make_itinerary()
        assert itinerary_matches_flight(itin, "DL", "171") is False


# ---------------------------------------------------------------------------
# search() with flight_number param
# ---------------------------------------------------------------------------


class TestSearchFlightNumberParam:
    @staticmethod
    def _trip_option(itinerary: Itinerary, selector: str) -> TripOption:
        return TripOption(
            selector=selector,
            price=itinerary.price,
            legs=[
                TripLeg(
                    origin="JFK",
                    destination="LAX",
                    date="2026-06-01",
                    itinerary=itinerary,
                )
            ],
        )

    def test_filters_decoded_result(self, monkeypatch):
        match = make_itinerary(Segment(airline="DL", flight_number="171"))
        no_match = make_itinerary(Segment(airline="UA", flight_number="500"))
        result = SearchResult(
            results=[
                self._trip_option(no_match, "selector-1"),
                self._trip_option(match, "selector-2"),
            ]
        )

        monkeypatch.setattr(swoop, "search_trip_options", lambda legs, **kw: result)
        filtered = swoop.search("JFK", "LAX", "2026-06-01", flight_number="DL 171")
        assert isinstance(filtered, SearchResult)
        assert filtered.results == [result.results[1]]

    def test_returns_none_when_no_match(self, monkeypatch):
        no_match = make_itinerary(Segment(airline="UA", flight_number="500"))
        result = SearchResult(results=[self._trip_option(no_match, "selector-1")])

        monkeypatch.setattr(swoop, "search_trip_options", lambda legs, **kw: result)
        filtered = swoop.search("JFK", "LAX", "2026-06-01", flight_number="DL 171")
        assert isinstance(filtered, SearchResult)
        assert filtered.results == []

    def test_passes_carrier_to_airlines_filter(self, monkeypatch):
        captured = {}

        def fake_search_trip_options(legs, **kwargs):
            captured["legs"] = legs
            captured.update(kwargs)
            return SearchResult()

        monkeypatch.setattr(swoop, "search_trip_options", fake_search_trip_options)
        swoop.search("JFK", "LAX", "2026-06-01", flight_number="DL 171")
        assert captured["legs"][0]["airlines"] == ["DL"]

    def test_preserves_existing_airlines_filter(self, monkeypatch):
        captured = {}

        def fake_search_trip_options(legs, **kwargs):
            captured["legs"] = legs
            captured.update(kwargs)
            return SearchResult()

        monkeypatch.setattr(swoop, "search_trip_options", fake_search_trip_options)
        swoop.search("JFK", "LAX", "2026-06-01", airlines=["UA"], flight_number="DL 171")
        assert "DL" in captured["legs"][0]["airlines"]
        assert "UA" in captured["legs"][0]["airlines"]

    def test_no_duplicate_carrier_in_airlines(self, monkeypatch):
        captured = {}

        def fake_search_trip_options(legs, **kwargs):
            captured["legs"] = legs
            captured.update(kwargs)
            return SearchResult()

        monkeypatch.setattr(swoop, "search_trip_options", fake_search_trip_options)
        swoop.search("JFK", "LAX", "2026-06-01", airlines=["DL"], flight_number="DL 171")
        assert captured["legs"][0]["airlines"] == ["DL"]

    def test_without_flight_number_no_filter(self, monkeypatch):
        match = make_itinerary(Segment(airline="DL", flight_number="171"))
        result = SearchResult(results=[self._trip_option(match, "selector-1")])

        monkeypatch.setattr(swoop, "search_trip_options", lambda legs, **kw: result)
        unfiltered = swoop.search("JFK", "LAX", "2026-06-01")
        assert unfiltered is result
