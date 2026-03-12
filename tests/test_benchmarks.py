"""Performance benchmarks for critical swoop functions.

Run with: pytest tests/test_benchmarks.py --benchmark-only
Normal test runs skip this module unless --run-benchmarks is supplied.
"""

import json

import pytest

pytest.importorskip("pytest_benchmark")
pytestmark = pytest.mark.benchmark

from swoop.decoder import _decode_flight, _decode_itinerary, decode_result
from swoop.rpc import _build_f_req
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

    def test_build_f_req_oneway(self, benchmark):
        benchmark(_build_f_req, "JFK", "LAX", "2026-03-15")

    def test_build_f_req_roundtrip(self, benchmark):
        benchmark(
            _build_f_req,
            "JFK", "LAX", "2026-03-15",
            return_date="2026-03-22",
        )

    def test_build_f_req_with_filters(self, benchmark):
        benchmark(
            _build_f_req,
            "JFK", "LAX", "2026-03-15",
            cabin="business",
            adults=2,
            max_stops=1,
            airlines=["DL", "UA", "AA"],
            earliest_departure=6,
            latest_departure=18,
        )
