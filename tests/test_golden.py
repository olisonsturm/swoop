"""Golden file tests — decode fixture responses and verify structure."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from swoop.decoder import decode_result, SearchResult


FIXTURES = Path(__file__).parent / "fixtures" / "responses"


def _load_fixture(name: str) -> list:
    with open(FIXTURES / name) as f:
        return json.load(f)


class TestGoldenOneWay:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.data = _load_fixture("shopping_oneway.json")
        self.result = decode_result(self.data)

    def test_returns_search_result(self):
        assert isinstance(self.result, SearchResult)

    def test_best_count(self):
        assert len(self.result.best) == 2

    def test_other_count(self):
        assert len(self.result.other) == 2

    def test_all_itineraries_have_flights(self):
        for itin in self.result.best + self.result.other:
            assert len(itin.flights) >= 1

    def test_flight_fields_populated(self):
        flight = self.result.best[0].flights[0]
        assert flight.airline != ""
        assert flight.flight_number != ""
        assert flight.departure_airport != ""
        assert flight.arrival_airport != ""
        assert flight.travel_time > 0

    def test_itinerary_fields_populated(self):
        itin = self.result.best[0]
        assert itin.airline_code != ""
        assert itin.departure_airport != ""
        assert itin.arrival_airport != ""
        assert itin.travel_time > 0

    def test_connecting_flight_has_layover(self):
        """At least one itinerary should have a connecting flight with layover."""
        connecting = [it for it in self.result.best + self.result.other if len(it.flights) > 1]
        assert len(connecting) >= 1
        for it in connecting:
            assert len(it.layovers) == len(it.flights) - 1

    def test_codeshares_present(self):
        """At least one flight should have codeshares."""
        has_cs = any(
            f.codeshares
            for it in self.result.best + self.result.other
            for f in it.flights
        )
        assert has_cs

    def test_snapshot_stability(self):
        """Re-decoding the same data produces identical results."""
        result2 = decode_result(self.data)
        assert asdict(self.result) == asdict(result2)

    def test_specific_airline_codes(self):
        """Verify the specific airlines we put in the fixtures."""
        codes = {it.airline_code for it in self.result.best + self.result.other}
        assert codes == {"DL", "AA", "UA", "B6"}

    def test_carbon_emissions_decoded(self):
        """Carbon emissions data should be decoded for itineraries that have it."""
        itin = self.result.best[0]
        assert itin.carbon_emissions is not None
        assert itin.carbon_emissions.this_flight_grams == 185000
        assert itin.carbon_emissions.typical_for_route_grams == 210000
        assert itin.carbon_emissions.difference_percent == -12
        assert itin.carbon_emissions.emissions_rating == 1

    def test_budget_carrier_flag(self):
        """B6 itinerary should be marked as budget carrier."""
        b6 = [it for it in self.result.other if it.airline_code == "B6"][0]
        assert b6.is_budget_carrier is True
        # Non-budget carriers should not be flagged
        dl = self.result.best[0]
        assert dl.is_budget_carrier is False

    def test_quality_signals_decoded(self):
        """Quality signals should be decoded when present."""
        dl = self.result.best[0]
        assert dl.quality_signals is not None
        assert dl.quality_signals.quality_tier == 1
        assert dl.quality_signals.bag_flags == [0, 1]

    def test_connecting_itinerary_airports(self):
        """Connecting flight should have correct origin and destination."""
        aa = self.result.best[1]
        assert aa.departure_airport == "SFO"
        assert aa.arrival_airport == "MIA"
        assert aa.flights[0].departure_airport == "SFO"
        assert aa.flights[0].arrival_airport == "ORD"
        assert aa.flights[1].departure_airport == "ORD"
        assert aa.flights[1].arrival_airport == "MIA"

    def test_codeshare_details(self):
        """Codeshare on DL flight should have correct airline info."""
        dl_flight = self.result.best[0].flights[0]
        assert len(dl_flight.codeshares) == 1
        cs = dl_flight.codeshares[0]
        assert cs.airline_code == "VS"
        assert cs.flight_number == "5100"
        assert cs.airline_name == "Virgin Atlantic"


class TestGoldenRoundtrip:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.result = decode_result(_load_fixture("shopping_roundtrip.json"))

    def test_has_results(self):
        assert len(self.result.best) >= 1

    def test_flights_populated(self):
        for itin in self.result.best + self.result.other:
            for flight in itin.flights:
                assert flight.airline != ""

    def test_overnight_flag(self):
        """JFK->LHR evening flight should be marked overnight."""
        dl = self.result.best[0]
        assert dl.flights[0].overnight is True

    def test_different_airlines(self):
        """Best and other should have different airlines."""
        best_code = self.result.best[0].airline_code
        other_code = self.result.other[0].airline_code
        assert best_code != other_code

    def test_transatlantic_travel_time(self):
        """Travel times should reflect transatlantic flights."""
        for itin in self.result.best + self.result.other:
            assert itin.travel_time >= 400  # At least ~6.5 hours


class TestGoldenEmpty:
    def test_empty_response(self):
        result = decode_result(_load_fixture("shopping_empty.json"))
        assert len(result.best) == 0
        assert len(result.other) == 0

    def test_empty_returns_search_result(self):
        result = decode_result(_load_fixture("shopping_empty.json"))
        assert isinstance(result, SearchResult)

    def test_empty_price_range_is_none(self):
        result = decode_result(_load_fixture("shopping_empty.json"))
        assert result.price_range is None
