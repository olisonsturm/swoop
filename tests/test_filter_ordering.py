"""Test that search() filters by flight_number before correcting roundtrip prices."""

from unittest.mock import patch

import swoop
from swoop import SearchResult, TripLeg, TripOption
from swoop.decoder import Flight, Itinerary


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

        corrected_selectors = []

        def mock_correct_trip_option_prices(filtered_result, **kwargs):
            corrected_selectors.extend(option.selector for option in filtered_result.results)

        with (
            patch("swoop.search_trip_options", return_value=result) as mock_search_trip_options,
            patch("swoop.correct_trip_option_prices", side_effect=mock_correct_trip_option_prices),
        ):
            output = swoop.search(
                "JFK", "LAX", "2026-06-15",
                return_date="2026-06-22",
                flight_number="DL2300",
            )

        assert mock_search_trip_options.call_args.kwargs["correct_prices"] is False
        assert [option.selector for option in output.results] == ["selector-2"]
        assert corrected_selectors == ["selector-2"]
