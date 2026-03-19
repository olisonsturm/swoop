"""Test that search() stays shopping-only while filtering by flight_number."""

from unittest.mock import patch

import swoop
from swoop import SearchResult, TripLeg, TripOption
from swoop.decoder import Segment, Itinerary


class TestSearchUsesShoppingPrices:
    """Verify search() does not run exact-price correction."""

    def test_roundtrip_search_skips_price_correction(self):
        """Roundtrip search should return shopping rows without correction."""
        matching_itin = Itinerary(
            segments=[Segment(airline="DL", flight_number="2300")],
            direct_price=342,
            booking_token="match-token",
        )
        other_itin = Itinerary(
            segments=[Segment(airline="UA", flight_number="1234")],
            direct_price=400,
            booking_token="other-token",
        )
        result = SearchResult(
            results=[
                TripOption(
                    selector="selector-1",
                    price=other_itin.price,
                    legs=[TripLeg(origin="JFK", destination="LAX", date="2026-06-15", itinerary=other_itin)],
                ),
                TripOption(
                    selector="selector-2",
                    price=matching_itin.price,
                    legs=[TripLeg(origin="JFK", destination="LAX", date="2026-06-15", itinerary=matching_itin)],
                ),
            ],
        )

        with (
            patch("swoop.search_trip_options", return_value=result) as mock_search_trip_options,
        ):
            output = swoop.search(
                "JFK", "LAX", "2026-06-15",
                return_date="2026-06-22",
                flight_number="DL2300",
            )

        assert mock_search_trip_options.call_args.kwargs["correct_prices"] is False
        assert [option.selector for option in output.results] == ["selector-2"]
