"""Test that search() filters by flight_number before correcting roundtrip prices."""

from unittest.mock import patch

import swoop
from swoop.decoder import BookingOption, Flight, Itinerary, SearchResult


class TestFilterBeforeCorrectOrdering:
    """Verify filter-before-correct reduces RPC calls for roundtrip + flight_number."""

    def test_filter_before_correct_reduces_rpc_calls(self):
        """When flight_number is given, filtering happens before price correction."""
        matching_itin = Itinerary(
            flights=[Flight(airline="DL", flight_number="2300")],
            direct_price=342,
            booking_token="match-token",
        )
        other_itin = Itinerary(
            flights=[Flight(airline="UA", flight_number="1234")],
            direct_price=400,
            booking_token="other-token",
        )
        result = SearchResult(_raw=[], best=[matching_itin], other=[other_itin])

        booking_calls = []

        def mock_get_booking(itin_or_token, **kwargs):
            booking_calls.append(itin_or_token)
            return [BookingOption(price=342, is_basic=False)]

        with patch("swoop._search_from_legs", return_value=result), \
             patch("swoop.get_booking_results", side_effect=mock_get_booking):
            output = swoop.search(
                "JFK", "LAX", "2026-06-15",
                return_date="2026-06-22",
                flight_number="DL2300",
            )

        # Only the matching itinerary should have GetBookingResults called
        assert len(booking_calls) == 1
        assert booking_calls[0] is matching_itin
