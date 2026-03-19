"""Currency propagation and formatting tests."""

import base64
import json

import pytest

from swoop import flights_pb2 as PB
from swoop.builders import ItinerarySummary
from swoop.cli.formatters import _format_price
from swoop.decoder import Itinerary
from swoop.models import PriceResult, SearchResult, TripLeg, TripOption


# ---------------------------------------------------------------------------
# Itinerary.currency property
# ---------------------------------------------------------------------------


class TestItineraryCurrency:
    def test_returns_currency_from_price_info(self):
        itin = Itinerary(
            price_info=ItinerarySummary(flights="", price=100.0, currency="GBP"),
        )
        assert itin.currency == "GBP"

    def test_returns_none_when_no_price_info(self):
        itin = Itinerary()
        assert itin.currency is None

    def test_returns_none_when_currency_empty(self):
        itin = Itinerary(
            price_info=ItinerarySummary(flights="", price=100.0, currency=""),
        )
        assert itin.currency is None

    def test_usd_currency(self):
        itin = Itinerary(
            price_info=ItinerarySummary(flights="", price=250.0, currency="USD"),
        )
        assert itin.currency == "USD"


# ---------------------------------------------------------------------------
# TripOption / SearchResult / PriceResult currency fields
# ---------------------------------------------------------------------------


class TestModelCurrencyFields:
    def test_trip_option_defaults_none(self):
        opt = TripOption(selector="test")
        assert opt.currency is None

    def test_trip_option_accepts_currency(self):
        opt = TripOption(selector="test", price=100, currency="EUR")
        assert opt.currency == "EUR"

    def test_search_result_defaults_none(self):
        sr = SearchResult()
        assert sr.currency is None

    def test_search_result_derives_currency_from_results(self):
        sr = SearchResult(results=[TripOption(selector="x", currency="GBP")])
        assert sr.currency == "GBP"

    def test_price_result_defaults_none(self):
        pr = PriceResult(price=100)
        assert pr.currency is None

    def test_price_result_accepts_currency(self):
        pr = PriceResult(price=5000, currency="JPY")
        assert pr.currency == "JPY"


# ---------------------------------------------------------------------------
# _build_trip_option currency propagation
# ---------------------------------------------------------------------------


class TestBuildTripOptionCurrency:
    def test_propagates_currency(self):
        from swoop._selection import _build_trip_option

        itin = Itinerary(
            direct_price=150,
            booking_token="tok",
            price_info=ItinerarySummary(flights="f", price=150.0, currency="GBP"),
            departure_airport_code="LHR",
            arrival_airport_code="CDG",
        )
        request_legs = [{"origin": "LHR", "destination": "CDG", "date": "2026-07-01"}]
        option = _build_trip_option(
            request_legs,
            [itin],
            cabin="economy",
            include_basic_economy=False,
        )
        assert option.currency == "GBP"
        assert option.price == 150

    def test_none_currency_when_no_price_info(self):
        from swoop._selection import _build_trip_option

        itin = Itinerary(
            direct_price=200,
            booking_token="tok",
            departure_airport_code="JFK",
            arrival_airport_code="LAX",
        )
        request_legs = [{"origin": "JFK", "destination": "LAX", "date": "2026-07-01"}]
        option = _build_trip_option(
            request_legs,
            [itin],
            cabin="economy",
            include_basic_economy=False,
        )
        assert option.currency is None


# ---------------------------------------------------------------------------
# _format_price
# ---------------------------------------------------------------------------


class TestFormatPrice:
    """Test _format_price.

    Assertions check symbol presence and numeric formatting.
    Symbols depend on the system locale, so we check contains rather than
    exact equality for non-USD currencies.
    """

    def test_usd(self):
        result = _format_price(250, "USD")
        assert "$250" == result

    def test_eur(self):
        result = _format_price(250, "EUR")
        assert "250" in result

    def test_gbp(self):
        result = _format_price(150, "GBP")
        assert "150" in result

    def test_jpy(self):
        result = _format_price(15000, "JPY")
        assert "15,000" in result

    def test_inr(self):
        result = _format_price(8500, "INR")
        assert "8,500" in result

    def test_none_price(self):
        assert _format_price(None) == "\u2014"  # em-dash

    def test_none_currency_shows_raw(self):
        assert _format_price(100) == "100"

    def test_zero_price(self):
        assert _format_price(0, "USD") == "$0"

    def test_large_price(self):
        assert _format_price(12345, "USD") == "$12,345"

    def test_unknown_currency_uses_code(self):
        result = _format_price(100, "XYZ")
        assert "100" in result
