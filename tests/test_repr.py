"""Tests for custom __repr__ methods on dataclasses."""

from swoop.decoder import (
    BookingOption,
    Segment,
    Itinerary,
    Layover,
    PriceRange,
    RawSearchResult,
)
from swoop.models import (
    PriceResult,
    ResolvedLeg,
    SearchResult,
    TripLeg,
    TripOption,
)
from tests.factories import make_simple_itinerary


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------


class TestSegmentRepr:
    def test_basic(self):
        f = Segment(
            airline="DL",
            flight_number="2300",
            departure_airport_code="JFK",
            arrival_airport_code="LAX",
            departure_time=(8, 30),
            arrival_time=(11, 45),
            travel_time=315,
        )
        assert repr(f) == "Segment(DL 2300 JFK->LAX 08:30-11:45 5h 15m)"

    def test_no_airline(self):
        f = Segment(
            flight_number="100",
            departure_airport_code="SFO",
            arrival_airport_code="ORD",
            departure_time=(14, 0),
            arrival_time=(20, 30),
            travel_time=390,
        )
        assert repr(f) == "Segment(100 SFO->ORD 14:00-20:30 6h 30m)"

    def test_defaults(self):
        f = Segment()
        assert repr(f) == "Segment(00:00-00:00 0m)"

    def test_midnight_time(self):
        f = Segment(
            airline="UA",
            flight_number="1",
            departure_airport_code="EWR",
            arrival_airport_code="LHR",
            departure_time=(0, 5),
            arrival_time=(12, 0),
            travel_time=415,
        )
        assert repr(f) == "Segment(UA 1 EWR->LHR 00:05-12:00 6h 55m)"


# ---------------------------------------------------------------------------
# Layover
# ---------------------------------------------------------------------------


class TestLayoverRepr:
    def test_basic(self):
        lay = Layover(minutes=90, departure_airport_code="ORD")
        assert repr(lay) == "Layover(1h 30m ORD)"

    def test_overnight(self):
        lay = Layover(minutes=120, departure_airport_code="ORD", is_overnight=True)
        assert repr(lay) == "Layover(2h ORD overnight)"

    def test_no_airport(self):
        lay = Layover(minutes=60)
        assert repr(lay) == "Layover(1h)"

    def test_zero_minutes(self):
        lay = Layover(minutes=0, departure_airport_code="ATL")
        assert repr(lay) == "Layover(0m ATL)"


# ---------------------------------------------------------------------------
# Itinerary
# ---------------------------------------------------------------------------


class TestItineraryRepr:
    def test_nonstop_with_price(self):
        itin = make_simple_itinerary(price=299)
        r = repr(itin)
        assert r == "Itinerary(DL 2300 JFK->LAX 08:00-11:15 3h 15m nonstop price=299)"

    def test_one_stop(self):
        f1 = Segment(airline="DL", flight_number="2300", departure_airport_code="JFK", arrival_airport_code="ORD")
        f2 = Segment(airline="DL", flight_number="2301", departure_airport_code="ORD", arrival_airport_code="LAX")
        lay = Layover(minutes=90, departure_airport_code="ORD")
        itin = Itinerary(
            segments=[f1, f2],
            layovers=[lay],
            departure_airport_code="JFK",
            arrival_airport_code="LAX",
            departure_time=(8, 30),
            arrival_time=(14, 45),
            travel_time=375,
        )
        assert "DL 2300 / 2301" in repr(itin)
        assert "1 stop" in repr(itin)

    def test_no_price(self):
        itin = make_simple_itinerary(price=299)
        itin.direct_price = None
        r = repr(itin)
        assert "price=" not in r

    def test_empty_itinerary(self):
        itin = Itinerary()
        r = repr(itin)
        assert r == "Itinerary(00:00-00:00 0m nonstop)"

    def test_multiple_stops(self):
        segments = [Segment(airline="UA", flight_number=str(i)) for i in range(3)]
        lays = [Layover(minutes=60), Layover(minutes=45)]
        itin = Itinerary(segments=segments, layovers=lays, travel_time=480)
        assert "2 stops" in repr(itin)


# ---------------------------------------------------------------------------
# BookingOption
# ---------------------------------------------------------------------------


class TestBookingOptionRepr:
    def test_basic(self):
        bo = BookingOption(price=249, brand_label="Blue Basic", is_basic=True)
        assert repr(bo) == "BookingOption(price=249 'Blue Basic' basic)"

    def test_no_basic(self):
        bo = BookingOption(price=289, brand_label="Blue Plus")
        assert repr(bo) == "BookingOption(price=289 'Blue Plus')"

    def test_no_brand(self):
        bo = BookingOption(price=199)
        assert repr(bo) == "BookingOption(price=199)"

    def test_hides_internal_fields(self):
        bo = BookingOption(
            price=300,
            brand_label="Main",
            _is_basic_by_flags=True,
            _token_price_raw=30000,
            _display_price_raw=30000,
            _context_segment_token="long_token_here",
        )
        r = repr(bo)
        assert "_is_basic_by_flags" not in r
        assert "_token_price_raw" not in r
        assert "_display_price_raw" not in r
        assert "_context_segment_token" not in r
        assert "long_token_here" not in r


# ---------------------------------------------------------------------------
# RawSearchResult
# ---------------------------------------------------------------------------


class TestRawSearchResultRepr:
    def test_basic(self):
        result = RawSearchResult(_raw=[1, 2, 3], best=[Itinerary()] * 3, other=[Itinerary()] * 12)
        assert repr(result) == "RawSearchResult(best=3, other=12)"

    def test_empty(self):
        result = RawSearchResult(_raw=[], best=[], other=[])
        assert repr(result) == "RawSearchResult(best=0, other=0)"

    def test_hides_raw(self):
        result = RawSearchResult(_raw=["secret", "data"], best=[], other=[])
        r = repr(result)
        assert "secret" not in r
        assert "data" not in r


# ---------------------------------------------------------------------------
# TripLeg
# ---------------------------------------------------------------------------


class TestTripLegRepr:
    def test_without_itinerary(self):
        leg = TripLeg(origin="JFK", destination="LAX", date="2026-06-15")
        assert repr(leg) == "TripLeg(JFK->LAX 2026-06-15)"

    def test_with_itinerary(self):
        itin = make_simple_itinerary()
        leg = TripLeg(origin="JFK", destination="LAX", date="2026-06-15", itinerary=itin)
        assert repr(leg) == "TripLeg(JFK->LAX 2026-06-15 DL 2300)"

    def test_itinerary_no_segments(self):
        leg = TripLeg(origin="SFO", destination="ORD", date="2026-07-01", itinerary=Itinerary())
        assert repr(leg) == "TripLeg(SFO->ORD 2026-07-01)"


# ---------------------------------------------------------------------------
# TripOption
# ---------------------------------------------------------------------------


class TestTripOptionRepr:
    def test_single_leg(self):
        itin = make_simple_itinerary()
        leg = TripLeg(origin="JFK", destination="LAX", date="2026-06-15", itinerary=itin)
        opt = TripOption(selector="sel", price=299, legs=[leg])
        assert repr(opt) == "TripOption(price=299 JFK->LAX DL 2300)"

    def test_multi_leg(self):
        legs = [
            TripLeg(origin="JFK", destination="LAX", date="2026-06-15"),
            TripLeg(origin="LAX", destination="JFK", date="2026-06-22"),
        ]
        opt = TripOption(selector="sel", price=450, legs=legs)
        assert repr(opt) == "TripOption(price=450 2 legs)"

    def test_no_price(self):
        opt = TripOption(selector="sel")
        assert repr(opt) == "TripOption()"

    def test_no_legs(self):
        opt = TripOption(selector="sel", price=199)
        assert repr(opt) == "TripOption(price=199)"


# ---------------------------------------------------------------------------
# SearchResult
# ---------------------------------------------------------------------------


class TestSearchResultRepr:
    def test_with_results_and_range(self):
        opts = [TripOption(selector=f"s{i}") for i in range(5)]
        sr = SearchResult(results=opts, price_range=PriceRange(low=199, high=450))
        assert repr(sr) == "SearchResult(5 results, price_range=199-450)"

    def test_zero_results(self):
        sr = SearchResult()
        assert repr(sr) == "SearchResult(0 results)"

    def test_incomplete(self):
        sr = SearchResult(results=[TripOption(selector="s")], is_complete=False)
        assert repr(sr) == "SearchResult(1 result, incomplete)"

    def test_no_price_range(self):
        opts = [TripOption(selector="s")]
        sr = SearchResult(results=opts)
        assert repr(sr) == "SearchResult(1 result)"

    def test_partial_price_range(self):
        sr = SearchResult(results=[], price_range=PriceRange(low=100, high=None))
        assert repr(sr) == "SearchResult(0 results, price_range=100-?)"


# ---------------------------------------------------------------------------
# ResolvedLeg
# ---------------------------------------------------------------------------


class TestResolvedLegRepr:
    def test_basic(self):
        rl = ResolvedLeg(flight_summary="DL 2300", origin="JFK", destination="LAX", date="2026-06-15")
        assert repr(rl) == "ResolvedLeg(DL 2300 JFK->LAX 2026-06-15)"

    def test_empty_summary(self):
        rl = ResolvedLeg(flight_summary="", origin="SFO", destination="ORD", date="2026-07-01")
        assert repr(rl) == "ResolvedLeg(SFO->ORD 2026-07-01)"


# ---------------------------------------------------------------------------
# PriceResult
# ---------------------------------------------------------------------------


class TestPriceResultRepr:
    def test_with_brand_and_counts(self):
        legs = [ResolvedLeg(flight_summary="DL 2300", origin="JFK", destination="LAX", date="2026-06-15")]
        opts = [BookingOption(price=300), BookingOption(price=350), BookingOption(price=400)]
        pr = PriceResult(price=342, fare_brand="Main Cabin", resolved_legs=legs * 2, booking_options=opts)
        assert repr(pr) == "PriceResult(price=342 'Main Cabin' 2 legs, 3 options)"

    def test_basic_economy(self):
        pr = PriceResult(price=342, is_basic_economy=True)
        assert repr(pr) == "PriceResult(price=342 basic_economy)"

    def test_minimal(self):
        pr = PriceResult(price=200)
        assert repr(pr) == "PriceResult(price=200)"

    def test_fare_brand_takes_precedence(self):
        pr = PriceResult(price=400, fare_brand="Economy", is_basic_economy=True)
        assert repr(pr) == "PriceResult(price=400 'Economy')"
        assert "basic_economy" not in repr(pr)

    def test_single_leg_and_option(self):
        leg = ResolvedLeg(flight_summary="UA 100", origin="SFO", destination="JFK", date="2026-08-01")
        opt = BookingOption(price=500)
        pr = PriceResult(price=500, resolved_legs=[leg], booking_options=[opt])
        assert repr(pr) == "PriceResult(price=500 1 leg, 1 option)"
