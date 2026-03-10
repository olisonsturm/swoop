"""Tests for flight number parsing, matching, and search_flight()."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import swoop  # noqa: E402
from swoop._validate import parse_flight_number  # noqa: E402
from swoop.decoder import (  # noqa: E402
    Codeshare,
    SearchResult,
    Flight,
    Itinerary,
    itinerary_matches_flight,
)

from tests.factories import make_itinerary, make_search_result  # noqa: E402


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
        itin = make_itinerary(Flight(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, "DL", "171") is True

    def test_operating_flight_wrong_number(self):
        itin = make_itinerary(Flight(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, "DL", "172") is False

    def test_operating_flight_wrong_carrier(self):
        itin = make_itinerary(Flight(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, "UA", "171") is False

    def test_carrier_none_matches_any(self):
        itin = make_itinerary(Flight(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, None, "171") is True

    def test_carrier_none_wrong_number(self):
        itin = make_itinerary(Flight(airline="DL", flight_number="171"))
        assert itinerary_matches_flight(itin, None, "172") is False

    def test_codeshare_match(self):
        itin = make_itinerary(
            Flight(
                airline="DL",
                flight_number="171",
                codeshares=[Codeshare(airline_code="KL", flight_number="6050")],
            )
        )
        assert itinerary_matches_flight(itin, "KL", "6050") is True

    def test_codeshare_carrier_none(self):
        itin = make_itinerary(
            Flight(
                airline="DL",
                flight_number="171",
                codeshares=[Codeshare(airline_code="KL", flight_number="6050")],
            )
        )
        assert itinerary_matches_flight(itin, None, "6050") is True

    def test_multi_segment_any_match(self):
        itin = make_itinerary(
            Flight(airline="AA", flight_number="100"),
            Flight(airline="AA", flight_number="200"),
        )
        assert itinerary_matches_flight(itin, "AA", "200") is True

    def test_multi_segment_no_match(self):
        itin = make_itinerary(
            Flight(airline="AA", flight_number="100"),
            Flight(airline="AA", flight_number="200"),
        )
        assert itinerary_matches_flight(itin, "AA", "300") is False

    def test_empty_flights(self):
        itin = make_itinerary()
        assert itinerary_matches_flight(itin, "DL", "171") is False


# ---------------------------------------------------------------------------
# search_flight() integration tests (monkeypatched search_raw)
# ---------------------------------------------------------------------------


class TestSearchFlight:
    def test_returns_matching_itinerary(self, monkeypatch):
        match = make_itinerary(Flight(airline="DL", flight_number="171"))
        no_match = make_itinerary(Flight(airline="UA", flight_number="500"))
        result = make_search_result(best=[no_match, match])

        monkeypatch.setattr(swoop, "search_raw", lambda **kw: result)
        itin = swoop.search_flight("DL 171", origin="JFK", destination="LAX", date="2026-06-01")
        assert itin is match

    def test_returns_none_on_no_match(self, monkeypatch):
        no_match = make_itinerary(Flight(airline="UA", flight_number="500"))
        result = make_search_result(best=[no_match])

        monkeypatch.setattr(swoop, "search_raw", lambda **kw: result)
        itin = swoop.search_flight("DL 171", origin="JFK", destination="LAX", date="2026-06-01")
        assert itin is None

    def test_returns_none_when_rpc_returns_none(self, monkeypatch):
        monkeypatch.setattr(swoop, "search_raw", lambda **kw: None)
        itin = swoop.search_flight("DL 171", origin="JFK", destination="LAX", date="2026-06-01")
        assert itin is None

    def test_prefers_best_over_other(self, monkeypatch):
        best_match = make_itinerary(Flight(airline="DL", flight_number="171"))
        other_match = make_itinerary(Flight(airline="DL", flight_number="171"))
        result = make_search_result(best=[best_match], other=[other_match])

        monkeypatch.setattr(swoop, "search_raw", lambda **kw: result)
        itin = swoop.search_flight("DL 171", origin="JFK", destination="LAX", date="2026-06-01")
        assert itin is best_match

    def test_falls_back_to_other(self, monkeypatch):
        other_match = make_itinerary(Flight(airline="DL", flight_number="171"))
        result = make_search_result(other=[other_match])

        monkeypatch.setattr(swoop, "search_raw", lambda **kw: result)
        itin = swoop.search_flight("DL 171", origin="JFK", destination="LAX", date="2026-06-01")
        assert itin is other_match

    def test_auto_carrier_filter(self, monkeypatch):
        captured = {}

        def fake_rpc(**kwargs):
            captured.update(kwargs)
            return None

        monkeypatch.setattr(swoop, "search_raw", fake_rpc)
        swoop.search_flight("DL 171", origin="JFK", destination="LAX", date="2026-06-01")
        assert captured["airlines"] == ["DL"]

    def test_number_only_no_carrier_filter(self, monkeypatch):
        captured = {}

        def fake_rpc(**kwargs):
            captured.update(kwargs)
            return None

        monkeypatch.setattr(swoop, "search_raw", fake_rpc)
        swoop.search_flight("171", origin="JFK", destination="LAX", date="2026-06-01")
        assert captured["airlines"] is None


# ---------------------------------------------------------------------------
# search() with flight_number param
# ---------------------------------------------------------------------------


class TestSearchFlightNumberParam:
    def test_filters_decoded_result(self, monkeypatch):
        match = make_itinerary(Flight(airline="DL", flight_number="171"))
        no_match = make_itinerary(Flight(airline="UA", flight_number="500"))
        result = make_search_result(best=[no_match], other=[match])

        monkeypatch.setattr(swoop, "search_raw", lambda **kw: result)
        filtered = swoop.search("JFK", "LAX", "2026-06-01", flight_number="DL 171")
        assert filtered is not None
        assert filtered.best == []
        assert filtered.other == [match]

    def test_returns_none_when_no_match(self, monkeypatch):
        no_match = make_itinerary(Flight(airline="UA", flight_number="500"))
        result = make_search_result(best=[no_match])

        monkeypatch.setattr(swoop, "search_raw", lambda **kw: result)
        filtered = swoop.search("JFK", "LAX", "2026-06-01", flight_number="DL 171")
        assert filtered is None

    def test_passes_carrier_to_airlines_filter(self, monkeypatch):
        captured = {}

        def fake_rpc(**kwargs):
            captured.update(kwargs)
            return None

        monkeypatch.setattr(swoop, "search_raw", fake_rpc)
        swoop.search("JFK", "LAX", "2026-06-01", flight_number="DL 171")
        assert captured["airlines"] == ["DL"]

    def test_preserves_existing_airlines_filter(self, monkeypatch):
        captured = {}

        def fake_rpc(**kwargs):
            captured.update(kwargs)
            return None

        monkeypatch.setattr(swoop, "search_raw", fake_rpc)
        swoop.search("JFK", "LAX", "2026-06-01", airlines=["UA"], flight_number="DL 171")
        assert "DL" in captured["airlines"]
        assert "UA" in captured["airlines"]

    def test_no_duplicate_carrier_in_airlines(self, monkeypatch):
        captured = {}

        def fake_rpc(**kwargs):
            captured.update(kwargs)
            return None

        monkeypatch.setattr(swoop, "search_raw", fake_rpc)
        swoop.search("JFK", "LAX", "2026-06-01", airlines=["DL"], flight_number="DL 171")
        assert captured["airlines"] == ["DL"]

    def test_without_flight_number_no_filter(self, monkeypatch):
        match = make_itinerary(Flight(airline="DL", flight_number="171"))
        result = make_search_result(best=[match])

        monkeypatch.setattr(swoop, "search_raw", lambda **kw: result)
        unfiltered = swoop.search("JFK", "LAX", "2026-06-01")
        assert unfiltered is result
