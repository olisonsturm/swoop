"""API surface stability tests.

These tests freeze the public API surface of swoop to catch accidental
additions, removals, or renames that would break downstream consumers.
"""

import inspect
from dataclasses import fields

import pytest

import swoop
from swoop.decoder import (
    BookingOption,
    CarbonEmissions,
    Codeshare,
    Flight,
    Itinerary,
    Layover,
    PriceRange,
    QualitySignals,
    SearchResult,
    AmenityFlags,
)
from swoop.exceptions import (
    SwoopError,
    SwoopHTTPError,
    SwoopParseError,
    SwoopRateLimitError,
)


class TestFrozenExports:
    """Verify swoop.__all__ is exactly the expected set."""

    EXPECTED_ALL = {
        # Functions
        "search",
        "search_flight",
        "check_price",
        "get_booking_results",
        "search_raw",
        "parse_flight_number",
        "itinerary_matches_flight",
        # Types
        "PriceResult",
        "SearchResult",
        "Itinerary",
        "Flight",
        "BookingOption",
        "Codeshare",
        "Layover",
        "CarbonEmissions",
        "PriceRange",
        "AmenityFlags",
        "QualitySignals",
        # Exceptions
        "SwoopError",
        "SwoopHTTPError",
        "SwoopParseError",
        "SwoopRateLimitError",
        # Constants
        "SORT_TOP",
        "SORT_CHEAPEST",
        "SORT_DEPARTURE_TIME",
        "SORT_ARRIVAL_TIME",
        "SORT_DURATION",
        "STOPS_ANY",
        "STOPS_NONSTOP",
        "STOPS_ONE_OR_FEWER",
        "STOPS_TWO_OR_FEWER",
    }

    def test_all_matches_expected(self):
        actual = set(swoop.__all__)
        assert actual == self.EXPECTED_ALL

    def test_no_unexpected_additions(self):
        actual = set(swoop.__all__)
        extra = actual - self.EXPECTED_ALL
        assert extra == set(), f"Unexpected exports added: {extra}"

    def test_no_unexpected_removals(self):
        actual = set(swoop.__all__)
        missing = self.EXPECTED_ALL - actual
        assert missing == set(), f"Exports removed: {missing}"

    def test_all_exports_importable(self):
        for name in swoop.__all__:
            assert hasattr(swoop, name), f"swoop.__all__ lists {name!r} but it's not importable"


class TestFrozenDataclassFields:
    """Verify dataclass field names haven't changed."""

    @staticmethod
    def _field_names(cls):
        return {f.name for f in fields(cls)}

    def test_flight_fields(self):
        expected = {
            "airline", "airline_name", "flight_number", "operator",
            "codeshares", "aircraft",
            "departure_airport_code", "departure_airport_name",
            "arrival_airport_code", "arrival_airport_name",
            "departure_date", "arrival_date",
            "departure_time", "arrival_time",
            "travel_time", "seat_pitch_short", "legroom", "co2_grams",
            "overnight", "has_premium_ife", "amenities", "seat_type",
        }
        assert self._field_names(Flight) == expected

    def test_itinerary_fields(self):
        expected = {
            "airline_code", "airline_names", "flights", "layovers",
            "travel_time", "departure_airport_code", "arrival_airport_code",
            "departure_date", "arrival_date", "departure_time", "arrival_time",
            "price_info", "direct_price", "booking_token", "carbon_emissions",
            "stop_count", "is_budget_carrier", "quality_signals",
        }
        assert self._field_names(Itinerary) == expected

    def test_search_result_fields(self):
        expected = {"_raw", "best", "other", "price_range"}
        assert self._field_names(SearchResult) == expected

    def test_booking_option_fields(self):
        expected = {
            "price", "brand_label", "brand_code",
            "is_basic", "fare_family", "rebookability_signal",
            "_is_basic_by_flags", "_is_basic_by_text",
            "_option_index", "_token_price_cents", "_display_price_cents",
            "_price_delta_cents", "_context_segment_token",
            "_context_origin_iata", "_context_destination_iata",
            "_context_departure_local_iso", "_context_arrival_local_iso",
            "_context_carrier_code", "_context_flight_number",
            "_context_aircraft_code",
            "_brand_attribute_vector", "_registry_version",
        }
        assert self._field_names(BookingOption) == expected

    def test_codeshare_fields(self):
        expected = {"airline_code", "flight_number", "airline_name"}
        assert self._field_names(Codeshare) == expected

    def test_layover_fields(self):
        expected = {
            "minutes", "departure_airport_code", "departure_airport_name",
            "departure_airport_city", "arrival_airport_code",
            "arrival_airport_name", "arrival_airport_city", "is_overnight",
        }
        assert self._field_names(Layover) == expected

    def test_carbon_emissions_fields(self):
        expected = {
            "this_flight_grams", "typical_for_route_grams",
            "difference_percent", "emissions_rating",
        }
        assert self._field_names(CarbonEmissions) == expected

    def test_amenity_flags_fields(self):
        expected = {
            "has_power", "has_live_tv", "has_on_demand_video",
            "has_stream_media", "wifi",
        }
        assert self._field_names(AmenityFlags) == expected

    def test_quality_signals_fields(self):
        expected = {"quality_tier", "bag_flags"}
        assert self._field_names(QualitySignals) == expected

    def test_price_range_fields(self):
        expected = {"low", "high"}
        assert self._field_names(PriceRange) == expected


class TestSearchSignature:
    """Verify search() accepts the expected parameters."""

    def test_search_params(self):
        sig = inspect.signature(swoop.search)
        param_names = list(sig.parameters.keys())
        expected = [
            "origin", "destination", "date",
            "return_date", "cabin", "adults", "max_stops", "sort",
            "airlines", "flight_number", "include_basic_economy",
            "earliest_departure", "latest_departure",
            "earliest_arrival", "latest_arrival",
            "return_earliest_departure", "return_latest_departure",
            "timeout", "retries",
        ]
        assert param_names == expected

    def test_search_raw_params(self):
        sig = inspect.signature(swoop.search_raw)
        param_names = list(sig.parameters.keys())
        expected = [
            "origin", "destination", "date",
            "cabin", "adults", "sort", "max_stops", "airlines",
            "earliest_departure", "latest_departure",
            "earliest_arrival", "latest_arrival",
            "return_date", "return_earliest_departure", "return_latest_departure",
            "selected_outbound_legs",
            "timeout", "retries",
            "exclude_basic_economy",
        ]
        assert param_names == expected

    def test_search_flight_params(self):
        sig = inspect.signature(swoop.search_flight)
        param_names = list(sig.parameters.keys())
        expected = [
            "flight_number", "origin", "destination", "date",
            "return_date", "return_flight_number",
            "cabin", "adults", "max_stops", "timeout", "retries",
        ]
        assert param_names == expected


class TestItineraryPrice:
    """Verify the canonical ``price`` property on Itinerary."""

    def test_prefers_direct_price(self):
        from swoop.builders import ItinerarySummary
        itin = Itinerary(
            direct_price=299,
            price_info=ItinerarySummary(flights="", price=298.0, currency="USD"),
        )
        assert itin.price == 299

    def test_falls_back_to_price_info(self):
        from swoop.builders import ItinerarySummary
        itin = Itinerary(
            direct_price=None,
            price_info=ItinerarySummary(flights="", price=298.7, currency="USD"),
        )
        assert itin.price == 299  # rounded

    def test_none_when_no_price(self):
        itin = Itinerary()
        assert itin.price is None


class TestExceptionHierarchy:
    """Verify exception class relationships are stable."""

    def test_swoop_error_is_base(self):
        assert issubclass(SwoopHTTPError, SwoopError)
        assert issubclass(SwoopParseError, SwoopError)
        assert issubclass(SwoopRateLimitError, SwoopError)

    def test_rate_limit_is_http_error(self):
        assert issubclass(SwoopRateLimitError, SwoopHTTPError)

    def test_http_error_has_status_code(self):
        err = SwoopHTTPError(503)
        assert err.status_code == 503

    def test_rate_limit_has_429(self):
        err = SwoopRateLimitError()
        assert err.status_code == 429

    def test_all_inherit_from_exception(self):
        for cls in (SwoopError, SwoopHTTPError, SwoopParseError, SwoopRateLimitError):
            assert issubclass(cls, Exception)


class TestConstants:
    """Verify sort and stop constants are stable."""

    def test_sort_constants(self):
        assert swoop.SORT_TOP == 1
        assert swoop.SORT_CHEAPEST == 2
        assert swoop.SORT_DEPARTURE_TIME == 3
        assert swoop.SORT_ARRIVAL_TIME == 4
        assert swoop.SORT_DURATION == 5

    def test_stop_constants(self):
        assert swoop.STOPS_ANY == 0
        assert swoop.STOPS_NONSTOP == 1
        assert swoop.STOPS_ONE_OR_FEWER == 2
        assert swoop.STOPS_TWO_OR_FEWER == 3

    def test_cabin_class_map_importable(self):
        """CABIN_CLASS_MAP is no longer in __all__ but still importable."""
        from swoop.rpc import CABIN_CLASS_MAP
        assert CABIN_CLASS_MAP == {
            "economy": 1,
            "premium-economy": 2,
            "business": 3,
            "first": 4,
        }
