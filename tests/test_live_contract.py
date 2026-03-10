"""Live contract smoke tests for Google Flights API.

These tests hit the real Google Flights endpoint and verify that the
response structure hasn't changed. Run with: pytest -m live

Deselected by default in CI. Run manually to detect API changes.
"""

import pytest

import swoop
from swoop.decoder import SearchResult, Itinerary, Flight


pytestmark = pytest.mark.live


class TestShoppingContract:
    """Verify GetShoppingResults response structure."""

    def test_oneway_returns_search_result(self):
        result = swoop.search("JFK", "LAX", "2026-06-15")
        assert result is None or isinstance(result, SearchResult)

    def test_oneway_itineraries_have_expected_fields(self):
        result = swoop.search("JFK", "LAX", "2026-06-15", max_stops=0)
        if result is None:
            pytest.skip("No results returned")

        all_itins = result.best + result.other
        assert len(all_itins) > 0, "Expected at least one itinerary"

        for itin in all_itins[:3]:  # Check first 3
            assert isinstance(itin, Itinerary)
            assert itin.airline_code != ""
            assert len(itin.flights) >= 1
            assert itin.departure_airport != ""
            assert itin.arrival_airport != ""
            assert itin.travel_time > 0

            for flight in itin.flights:
                assert isinstance(flight, Flight)
                assert flight.airline != ""
                assert flight.flight_number != ""
                assert flight.departure_airport != ""
                assert flight.arrival_airport != ""


class TestBookingContract:
    """Verify GetBookingResults response structure."""

    def test_booking_results_parseable(self):
        result = swoop.search("JFK", "LAX", "2026-06-15", max_stops=0)
        if result is None:
            pytest.skip("No results returned")

        all_itins = result.best + result.other
        if not all_itins:
            pytest.skip("No itineraries to check")

        # Try booking results for first itinerary
        itin = all_itins[0]
        if not itin.booking_token:
            pytest.skip("No booking token on first itinerary")

        options = swoop.get_booking_results(itin)
        # Should return a list (possibly empty)
        assert isinstance(options, list)

        for opt in options:
            assert hasattr(opt, "price")
            assert hasattr(opt, "brand_label")
            assert hasattr(opt, "brand_code")
            assert isinstance(opt.price, int)
