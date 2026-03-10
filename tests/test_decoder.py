"""Tests for the Google Flights decoder.

Uses synthetic fixture data that mirrors the nested list structure
returned by Google Flights' embedded JS data.
"""

import pytest
from swoop.decoder import (
    AmenityFlags,
    Codeshare,
    SearchResult,
    Flight,
    Itinerary,
    Layover,
    QualitySignals,
    _decode_amenities,
    _decode_codeshare,
    _decode_flight,
    _decode_itinerary,
    _decode_layover,
    _safe_get,
    _safe_tuple,
    decode_result,
)

from tests.factories import make_flight_segment, make_codeshare, make_itinerary_element, make_full_response


# --- _safe_get tests ---


class TestSafeGet:
    def test_simple_path(self):
        assert _safe_get([1, 2, 3], [1]) == 2

    def test_nested_path(self):
        assert _safe_get([[10, 20], [30, 40]], [1, 0]) == 30

    def test_out_of_bounds(self):
        assert _safe_get([1, 2], [5]) is None

    def test_out_of_bounds_default(self):
        assert _safe_get([1, 2], [5], "default") == "default"

    def test_none_data(self):
        assert _safe_get(None, [0]) is None

    def test_empty_path(self):
        data = [1, 2, 3]
        assert _safe_get(data, []) == data

    def test_non_list_intermediate(self):
        assert _safe_get([1, "hello", 3], [1, 0]) is None


class TestSafeTuple:
    def test_list_input(self):
        assert _safe_tuple([2026, 3, 15], 3, [0, 0, 0]) == (2026, 3, 15)

    def test_short_list(self):
        assert _safe_tuple([8], 2, [0, 0]) == (8, 0)

    def test_none_input(self):
        assert _safe_tuple(None, 3, [0, 0, 0]) == (0, 0, 0)


# --- Codeshare decoding ---


class TestDecodeCodeshare:
    def test_basic(self):
        cs = _decode_codeshare(["AA", "4567", None, "American Airlines"])
        assert cs.airline_code == "AA"
        assert cs.flight_number == "4567"
        assert cs.airline_name == "American Airlines"

    def test_missing_fields(self):
        cs = _decode_codeshare(["AA"])
        assert cs.airline_code == "AA"
        assert cs.flight_number == ""


# --- Flight decoding ---


class TestDecodeFlight:
    def test_basic_flight(self):
        segment = make_flight_segment()
        flight = _decode_flight(segment)
        assert flight is not None
        assert flight.airline == "DL"
        assert flight.flight_number == "2300"
        assert flight.departure_airport == "JFK"
        assert flight.arrival_airport == "LAX"
        assert flight.travel_time == 315
        assert flight.aircraft == "Boeing 737-900"
        assert flight.departure_time == (8, 30)
        assert flight.arrival_time == (11, 45)

    def test_flight_with_codeshares(self):
        cs_data = [make_codeshare("AA", "4567"), make_codeshare("KL", "6123")]
        segment = make_flight_segment(codeshares=cs_data)
        flight = _decode_flight(segment)
        assert flight is not None
        assert len(flight.codeshares) == 2
        assert flight.codeshares[0].airline_code == "AA"
        assert flight.codeshares[0].flight_number == "4567"
        assert flight.codeshares[1].airline_code == "KL"

    def test_malformed_returns_empty_flight(self):
        # Hardened decoder returns a Flight with defaults rather than crashing
        flight = _decode_flight("not a list")
        assert flight is not None
        assert flight.airline == ""
        assert flight.flight_number == ""

    def test_empty_list(self):
        flight = _decode_flight([])
        assert flight is not None
        assert flight.airline == ""

    def test_premium_ife(self):
        segment = make_flight_segment(premium_ife=1)
        flight = _decode_flight(segment)
        assert flight is not None
        assert flight.has_premium_ife is True

    def test_no_premium_ife(self):
        segment = make_flight_segment(premium_ife=None)
        flight = _decode_flight(segment)
        assert flight is not None
        assert flight.has_premium_ife is False

    def test_amenity_flags(self):
        # Delta B767: power, on-demand video, free WiFi
        amenity_data = [None, True, None, None, None, None, None, None, None, True, None, 2]
        segment = make_flight_segment(amenities=amenity_data)
        flight = _decode_flight(segment)
        assert flight is not None
        assert flight.amenities is not None
        assert flight.amenities.has_power is True
        assert flight.amenities.has_on_demand_video is True
        assert flight.amenities.wifi == 2
        assert flight.amenities.has_live_tv is False
        assert flight.amenities.has_stream_media is False

    def test_amenities_with_live_tv(self):
        # JetBlue A320: power, live TV, free WiFi
        amenity_data = [None, True, None, None, None, None, None, None, True, None, None, 2]
        segment = make_flight_segment(amenities=amenity_data)
        flight = _decode_flight(segment)
        assert flight is not None
        assert flight.amenities.has_power is True
        assert flight.amenities.has_live_tv is True
        assert flight.amenities.has_on_demand_video is False

    def test_amenities_empty_array(self):
        # Budget carriers (Frontier) have empty amenity arrays
        segment = make_flight_segment(amenities=[])
        flight = _decode_flight(segment)
        assert flight is not None
        assert flight.amenities is None

    def test_amenities_none(self):
        segment = make_flight_segment(amenities=None)
        flight = _decode_flight(segment)
        assert flight is not None
        assert flight.amenities is None

    def test_seat_type_standard(self):
        segment = make_flight_segment(seat_type=1)
        flight = _decode_flight(segment)
        assert flight is not None
        assert flight.seat_type == 1

    def test_seat_type_below_average(self):
        segment = make_flight_segment(seat_type=2)
        flight = _decode_flight(segment)
        assert flight.seat_type == 2

    def test_seat_type_above_average(self):
        segment = make_flight_segment(seat_type=3)
        flight = _decode_flight(segment)
        assert flight.seat_type == 3

    def test_seat_type_none(self):
        segment = make_flight_segment(seat_type=None)
        flight = _decode_flight(segment)
        assert flight.seat_type is None

    def test_overnight_flag(self):
        segment = make_flight_segment(overnight=True)
        flight = _decode_flight(segment)
        assert flight.overnight is True

    def test_co2_grams(self):
        segment = make_flight_segment(co2_grams=145000)
        flight = _decode_flight(segment)
        assert flight.co2_grams == 145000

    def test_legroom(self):
        segment = make_flight_segment(legroom="28 inches")
        flight = _decode_flight(segment)
        assert flight.legroom == "28 inches"


@pytest.mark.parametrize("airline_code,airline_name", [
    ("DL", "Delta Air Lines"),
    ("AA", "American Airlines"),
    ("UA", "United Airlines"),
    ("B6", "JetBlue Airways"),
    ("F9", "Frontier Airlines"),
    ("WN", "Southwest Airlines"),
    ("NK", "Spirit Airlines"),
    ("AS", "Alaska Airlines"),
])
def test_decode_flight_various_airlines(airline_code, airline_name):
    segment = make_flight_segment(airline_code=airline_code, airline_name=airline_name)
    flight = _decode_flight(segment)
    assert flight is not None
    assert flight.airline == airline_code
    assert flight.airline_name == airline_name


@pytest.mark.parametrize("dep,arr", [
    ("JFK", "LAX"),
    ("SFO", "NRT"),
    ("LHR", "CDG"),
    ("ORD", "MIA"),
    ("ATL", "SEA"),
    ("DFW", "HNL"),
])
def test_decode_flight_various_airports(dep, arr):
    segment = make_flight_segment(dep_airport=dep, arr_airport=arr)
    flight = _decode_flight(segment)
    assert flight is not None
    assert flight.departure_airport == dep
    assert flight.arrival_airport == arr


# --- Layover decoding ---


class TestDecodeLayover:
    def test_basic_layover(self):
        el = [120, "ATL", "ATL", None, "Hartsfield-Jackson", "Atlanta", "Hartsfield-Jackson", "Atlanta"]
        layover = _decode_layover(el)
        assert layover is not None
        assert layover.minutes == 120
        assert layover.departure_airport == "ATL"
        assert layover.is_overnight is False

    def test_overnight_flag(self):
        el = [1431, "MCO", "MCO", [1], "Orlando International", "Orlando", "Orlando International", "Orlando"]
        layover = _decode_layover(el)
        assert layover is not None
        assert layover.is_overnight is True
        assert layover.minutes == 1431

    def test_overnight_flag_null(self):
        el = [60, "ORD", "ORD", None, "O'Hare", "Chicago", "O'Hare", "Chicago"]
        layover = _decode_layover(el)
        assert layover is not None
        assert layover.is_overnight is False


# --- Amenity decoding ---


class TestDecodeAmenities:
    def test_full_amenities(self):
        # AA domestic: power, stream media, free WiFi
        el = [None] * 33
        el[12] = [None, True, None, None, None, None, None, None, None, None, True, 2]
        result = _decode_amenities(el)
        assert result is not None
        assert result.has_power is True
        assert result.has_stream_media is True
        assert result.wifi == 2

    def test_international_wifi(self):
        # Intl carrier: WiFi value 3
        el = [None] * 33
        el[12] = [None, True, None, None, None, None, None, None, None, True, None, 3]
        result = _decode_amenities(el)
        assert result is not None
        assert result.wifi == 3

    def test_empty_array(self):
        el = [None] * 33
        el[12] = []
        result = _decode_amenities(el)
        assert result is None

    def test_none(self):
        el = [None] * 33
        el[12] = None
        result = _decode_amenities(el)
        assert result is None


# --- Itinerary decoding ---


class TestDecodeItinerary:
    def test_basic_itinerary(self):
        segment = make_flight_segment()
        itin_el = make_itinerary_element([segment])
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert len(itin.flights) == 1
        assert itin.flights[0].airline == "DL"
        assert itin.flights[0].flight_number == "2300"
        assert itin.airline_code == "DL"
        assert itin.travel_time == 315

    def test_connecting_flight(self):
        seg1 = make_flight_segment(
            dep_airport="JFK", arr_airport="ATL",
            dep_time=(8, 30), arr_time=(11, 0), travel_time=150,
        )
        seg2 = make_flight_segment(
            dep_airport="ATL", arr_airport="LAX",
            dep_time=(12, 0), arr_time=(14, 30), travel_time=270,
            flight_number="1845",
        )
        itin_el = make_itinerary_element([seg1, seg2], travel_time=420)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert len(itin.flights) == 2

    def test_malformed_returns_none(self):
        assert _decode_itinerary("not a list") is None

    def test_none_itin_data(self):
        assert _decode_itinerary([None, None]) is None

    def test_preserves_booking_token_from_summary(self):
        segment = make_flight_segment()
        itin_el = make_itinerary_element([segment], summary_data=[[None, 35000], "booking-token-123"])
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.booking_token == "booking-token-123"

    def test_budget_carrier_flag_true(self):
        segment = make_flight_segment(airline_code="F9", airline_name="Frontier Airlines")
        itin_el = make_itinerary_element([segment], airline_code="F9", is_budget=True)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.is_budget_carrier is True

    def test_budget_carrier_flag_false(self):
        segment = make_flight_segment()
        itin_el = make_itinerary_element([segment], is_budget=False)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.is_budget_carrier is False

    def test_quality_signals_standard(self):
        segment = make_flight_segment()
        qs = [None, None, 3, None, 1, False, [0, 1]]
        itin_el = make_itinerary_element([segment], quality_signals=qs)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.quality_signals is not None
        assert itin.quality_signals.quality_tier == 1
        assert itin.quality_signals.bag_flags == [0, 1]

    def test_quality_signals_budget(self):
        segment = make_flight_segment(airline_code="F9")
        qs = [None, None, 3, None, 3, False, [0, 0]]
        itin_el = make_itinerary_element([segment], airline_code="F9", is_budget=True, quality_signals=qs)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.quality_signals.quality_tier == 3
        assert itin.quality_signals.bag_flags == [0, 0]

    def test_quality_signals_business(self):
        segment = make_flight_segment()
        qs = [None, None, None, None, 1, None, [None, 1]]
        itin_el = make_itinerary_element([segment], quality_signals=qs)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.quality_signals.quality_tier == 1
        assert itin.quality_signals.bag_flags == [None, 1]

    def test_quality_signals_none(self):
        segment = make_flight_segment()
        itin_el = make_itinerary_element([segment], quality_signals=None)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.quality_signals is None

    def test_emissions_rating(self):
        segment = make_flight_segment()
        # carbon_data: [2]=rating, [3]=diff%, [7]=this_flight, [8]=typical
        carbon = [None, None, 1, -22, None, True, True, 150000, 192000]
        itin_el = make_itinerary_element([segment], carbon_data=carbon)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.carbon_emissions is not None
        assert itin.carbon_emissions.emissions_rating == 1
        assert itin.carbon_emissions.difference_percent == -22
        assert itin.carbon_emissions.this_flight_grams == 150000

    def test_emissions_rating_above_average(self):
        segment = make_flight_segment()
        carbon = [None, None, 3, 19, None, True, True, 230000, 192000]
        itin_el = make_itinerary_element([segment], carbon_data=carbon)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert itin.carbon_emissions.emissions_rating == 3
        assert itin.carbon_emissions.difference_percent == 19

    def test_overnight_layover_in_itinerary(self):
        seg1 = make_flight_segment(dep_airport="JFK", arr_airport="ATL")
        seg2 = make_flight_segment(dep_airport="ATL", arr_airport="LAX", flight_number="1845")
        layover_data = [[1431, "ATL", "ATL", [1], "Hartsfield-Jackson", "Atlanta", "Hartsfield-Jackson", "Atlanta"]]
        itin_el = make_itinerary_element([seg1, seg2], layovers_data=layover_data, travel_time=600)
        itin = _decode_itinerary(itin_el)
        assert itin is not None
        assert len(itin.layovers) == 1
        assert itin.layovers[0].is_overnight is True


# --- Full decode_result ---


class TestDecodeResult:
    def test_empty_response(self):
        result = decode_result([None, None, None, None])
        assert isinstance(result, SearchResult)
        assert len(result.best) == 0
        assert len(result.other) == 0

    def test_best_and_other(self):
        seg1 = make_flight_segment(flight_number="2300")
        seg2 = make_flight_segment(flight_number="1845", airline_code="AA", airline_name="American Airlines")
        best_itin = make_itinerary_element([seg1])
        other_itin = make_itinerary_element([seg2], airline_code="AA")

        data = make_full_response(best_itins=[best_itin], other_itins=[other_itin])
        result = decode_result(data)

        assert len(result.best) == 1
        assert len(result.other) == 1
        assert result.best[0].flights[0].flight_number == "2300"
        assert result.other[0].flights[0].airline == "AA"

    def test_multiple_best_flights(self):
        segments = [
            make_flight_segment(flight_number=str(i))
            for i in range(3)
        ]
        itins = [make_itinerary_element([seg]) for seg in segments]
        data = make_full_response(best_itins=itins)
        result = decode_result(data)
        assert len(result.best) == 3

    def test_skips_malformed_itineraries(self):
        good_seg = make_flight_segment()
        good_itin = make_itinerary_element([good_seg])
        bad_itin = "not a list"
        data = make_full_response(best_itins=[good_itin, bad_itin])
        result = decode_result(data)
        assert len(result.best) == 1

    def test_preserves_raw(self):
        data = make_full_response()
        result = decode_result(data)
        assert result._raw is data
