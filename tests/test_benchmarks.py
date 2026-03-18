"""Performance benchmarks for critical swoop functions.

Run with: pytest tests/test_benchmarks.py --benchmark-only
Normal test runs skip this module unless --run-benchmarks is supplied.
"""

import json

import pytest

pytest.importorskip("pytest_benchmark")
pytestmark = pytest.mark.benchmark

from swoop.decoder import _decode_flight, _decode_itinerary, decode_result
from swoop.rpc import _build_filters_from_legs, _normalize_rpc_leg, _encode_f_req_payload
from tests.factories import make_flight_segment, make_itinerary_element, make_full_response


class TestDecoderBenchmarks:
    """Benchmark decoder performance."""

    def test_decode_single_flight(self, benchmark):
        segment = make_flight_segment()
        benchmark(_decode_flight, segment)

    def test_decode_single_itinerary(self, benchmark):
        segment = make_flight_segment()
        element = make_itinerary_element([segment])
        benchmark(_decode_itinerary, element)

    def test_decode_10_itineraries(self, benchmark):
        segments = [make_flight_segment(flight_number=str(i)) for i in range(10)]
        itins = [make_itinerary_element([seg]) for seg in segments]
        data = make_full_response(best_itins=itins[:5], other_itins=itins[5:])

        benchmark(decode_result, data)

    def test_decode_50_itineraries(self, benchmark):
        segments = [make_flight_segment(flight_number=str(i)) for i in range(50)]
        itins = [make_itinerary_element([seg]) for seg in segments]
        data = make_full_response(best_itins=itins[:25], other_itins=itins[25:])

        benchmark(decode_result, data)

    def test_decode_200_itineraries(self, benchmark):
        segments = [make_flight_segment(flight_number=str(i)) for i in range(200)]
        itins = [make_itinerary_element([seg]) for seg in segments]
        data = make_full_response(best_itins=itins[:100], other_itins=itins[100:])

        benchmark(decode_result, data)


class TestRpcBenchmarks:
    """Benchmark RPC request building."""

    def test_build_filters_oneway(self, benchmark):
        legs = [_normalize_rpc_leg("JFK", "LAX", "2026-03-15")]
        benchmark(lambda: _encode_f_req_payload(_build_filters_from_legs(legs)))

    def test_build_filters_roundtrip(self, benchmark):
        legs = [
            _normalize_rpc_leg("JFK", "LAX", "2026-03-15"),
            _normalize_rpc_leg("LAX", "JFK", "2026-03-22"),
        ]
        benchmark(lambda: _encode_f_req_payload(_build_filters_from_legs(legs)))

    def test_build_filters_with_options(self, benchmark):
        legs = [
            _normalize_rpc_leg(
                "JFK", "LAX", "2026-03-15",
                max_stops=1,
                airlines=["DL", "UA", "AA"],
                earliest_departure=6,
                latest_departure=18,
            ),
        ]
        benchmark(lambda: _encode_f_req_payload(
            _build_filters_from_legs(legs, cabin="business", adults=2)
        ))
