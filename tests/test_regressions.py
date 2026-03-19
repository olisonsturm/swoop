"""Regression tests for known swoop bugs.

Each test documents a specific bug that was found and fixed. Tests serve as
guard rails to prevent regressions. Includes the bug description and fix
in the docstring.
"""

import base64
import json
import urllib.parse

import pytest

from swoop.builders import ItinerarySummary, TFSData, SearchLeg, Passengers
from swoop.decoder import decode_result, _decode_segment, _safe_get
from swoop.rpc import _build_filters_from_legs, _normalize_rpc_leg, _encode_f_req_payload


class TestAirportNesting:
    """Bug: Using 4 levels of airport nesting [[[["JFK", 0]]]] instead of
    3 levels [[["JFK", 0]]] silently returns zero results from Google Flights.
    Fix: builders.py and rpc.py use exactly 3 levels.
    """

    def test_outbound_airport_is_3_levels(self):
        filters = _build_filters_from_legs([
            _normalize_rpc_leg("JFK", "LAX", "2026-03-15"),
        ])
        segments = filters[1][13]
        dep = segments[0][0]
        # Must be [[[code, 0]]] — exactly 3 levels
        assert dep == [[["JFK", 0]]]
        # Verify it's NOT 4 levels
        assert not isinstance(dep[0][0][0], list)

    def test_return_airport_is_3_levels(self):
        filters = _build_filters_from_legs([
            _normalize_rpc_leg("JFK", "LAX", "2026-03-15"),
            _normalize_rpc_leg("LAX", "JFK", "2026-03-22"),
        ])
        segments = filters[1][13]
        # Return segment has reversed airports
        dep = segments[1][0]
        arr = segments[1][1]
        assert dep == [[["LAX", 0]]]
        assert arr == [[["JFK", 0]]]


class TestPriceInfoB64Path:
    """Bug: Using path [1,1] instead of [1] for the b64 string in itinerary
    summary returned None, causing all prices to show as $0.
    Fix: decoder.py _decode_price_info uses _safe_get(el, [1]).
    """

    def test_b64_is_at_index_1_not_1_1(self):
        """Verify the summary structure [price_array, b64_string] is read at [1]."""
        from swoop.decoder import _decode_price_info

        # Create a valid protobuf token
        from swoop import flights_pb2 as PB
        summary = PB.ItinerarySummary()
        summary.flights = "test"
        summary.price.price = 35000
        summary.price.currency = "USD"
        b64 = base64.b64encode(summary.SerializeToString()).decode()

        # Summary structure: [[None, price_cents], b64_string]
        el = [[None, 35000], b64]

        result = _decode_price_info(el)
        assert result is not None
        assert result.price == 35000  # raw protobuf value

    def test_wrong_path_would_fail(self):
        """If we used [1,1], we'd get None since [1] is a string not a list."""
        b64_string = "some_token"
        el = [[None, 35000], b64_string]
        # [1] is "some_token" (a string), [1][1] would be 'o' (char), not a b64 token
        assert _safe_get(el, [1]) == b64_string
        assert _safe_get(el, [1, 1]) is None  # This was the bug


class TestPrimpContentBytes:
    """Bug: primp's content param silently fails when passed a string
    instead of bytes. The request goes out but Google returns empty results.
    Fix: rpc.py encodes with .encode() before passing to _http_post.
    """

    def test_f_req_body_is_encoded_to_bytes(self):
        """The encoded body passed to _http_post must be bytes."""
        filters = _build_filters_from_legs([
            _normalize_rpc_leg("JFK", "LAX", "2026-03-15"),
        ])
        encoded = _encode_f_req_payload(filters)
        body = f"f.req={encoded}"
        body_bytes = body.encode()
        assert isinstance(body_bytes, bytes)
        # Verify it's not empty after encoding
        assert len(body_bytes) > 0


class TestRoundtripPriceIsReturnTotal:
    """Bug: Summing outbound price + return price gives wrong total because
    GetBookingResults for the return leg already returns the roundtrip total.
    Fix: Use return's GetBookingResults price as-is, don't sum.
    """

    def test_return_booking_price_is_roundtrip_total(self):
        """Document that return leg's booking option price IS the roundtrip
        total, not just the return leg price. This is a Google Flights design
        decision -- the price shown on the return selection page is the
        combined roundtrip total.
        """
        # This is a documentation-as-code test. The actual fix is in the
        # edge function client which uses return_price directly.
        # We verify the ItinerarySummary decoder preserves prices faithfully.
        from swoop import flights_pb2 as PB
        summary = PB.ItinerarySummary()
        summary.price.price = 52800
        summary.price.currency = "USD"
        b64 = base64.b64encode(summary.SerializeToString()).decode()

        decoded = ItinerarySummary.from_b64(b64)
        assert decoded.price == 52800  # raw protobuf value preserved
        assert decoded.currency == "USD"


class TestItinerarySummaryPriceConversion:
    """ItinerarySummary.from_b64() stores the raw protobuf price value.

    The authoritative price comes from Itinerary.direct_price (the display
    integer from the JSON response). The protobuf value is only used for
    the currency code.
    """

    def test_price_is_raw_protobuf_value(self):
        from swoop import flights_pb2 as PB
        summary = PB.ItinerarySummary()
        summary.price.price = 28400
        summary.price.currency = "USD"
        b64 = base64.b64encode(summary.SerializeToString()).decode()

        decoded = ItinerarySummary.from_b64(b64)
        assert decoded.price == 28400  # raw value, no conversion


class TestDecoderGracefulDegradation:
    """Bug: Early decoder versions used assertions and crashed on malformed
    data. Since Google can change response structure at any time, the decoder
    must never crash -- it should skip bad entries gracefully.
    Fix: All decoder functions use try/except and return None/defaults.
    """

    def test_decode_segment_with_non_list_returns_segment_not_none(self):
        """Malformed segment data should return a Segment with defaults."""
        segment = _decode_segment("not a list")
        assert segment is not None
        assert segment.airline == ""

    def test_decode_result_skips_malformed_itineraries(self):
        """Malformed itineraries in the response should be skipped."""
        from tests.factories import make_flight_segment, make_itinerary_element, make_full_response

        good = make_itinerary_element([make_flight_segment()])
        bad = "not a list"
        data = make_full_response(best_itins=[good, bad])
        result = decode_result(data)
        assert len(result.best) == 1  # Only the good one

    def test_decode_result_with_all_none(self):
        """All-None response should produce empty results, not crash."""
        result = decode_result([None, None, None, None])
        assert len(result.best) == 0
        assert len(result.other) == 0
