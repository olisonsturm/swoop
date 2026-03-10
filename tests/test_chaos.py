"""Chaos / corruption tests for decoder resilience.

Systematically corrupt valid responses at every index to verify the
decoder never crashes — it should gracefully degrade.
"""

import copy

import pytest

from swoop.decoder import (
    _decode_flight,
    _decode_itinerary,
    _decode_layover,
    decode_result,
    SearchResult,
)
from tests.factories import make_flight_segment, make_itinerary_element, make_full_response


class TestCorruptFlightSegment:
    """Corrupt each of the 33 flight segment indices."""

    @pytest.fixture
    def valid_segment(self):
        return make_flight_segment()

    @pytest.mark.parametrize("index", range(33))
    def test_corrupt_with_none(self, valid_segment, index):
        corrupted = copy.deepcopy(valid_segment)
        corrupted[index] = None
        result = _decode_flight(corrupted)
        # Must not crash — returns Flight or None
        if result is not None:
            assert hasattr(result, "airline")

    @pytest.mark.parametrize("index", range(33))
    def test_corrupt_with_string(self, valid_segment, index):
        corrupted = copy.deepcopy(valid_segment)
        corrupted[index] = "corrupted"
        result = _decode_flight(corrupted)
        if result is not None:
            assert hasattr(result, "airline")

    @pytest.mark.parametrize("index", range(33))
    def test_corrupt_with_empty_list(self, valid_segment, index):
        corrupted = copy.deepcopy(valid_segment)
        corrupted[index] = []
        result = _decode_flight(corrupted)
        if result is not None:
            assert hasattr(result, "airline")


class TestCorruptItinerary:
    """Corrupt itinerary data at various depths."""

    @pytest.fixture
    def valid_element(self):
        seg = make_flight_segment()
        return make_itinerary_element([seg])

    @pytest.mark.parametrize("index", range(11))
    def test_corrupt_root_with_none(self, valid_element, index):
        corrupted = copy.deepcopy(valid_element)
        corrupted[index] = None
        result = _decode_itinerary(corrupted)
        # Must not crash

    @pytest.mark.parametrize("index", range(11))
    def test_corrupt_root_with_string(self, valid_element, index):
        corrupted = copy.deepcopy(valid_element)
        corrupted[index] = "bad"
        result = _decode_itinerary(corrupted)

    def test_itin_data_is_string(self, valid_element):
        corrupted = copy.deepcopy(valid_element)
        corrupted[0] = "not a list"
        assert _decode_itinerary(corrupted) is None

    def test_itin_data_is_empty_list(self, valid_element):
        corrupted = copy.deepcopy(valid_element)
        corrupted[0] = []
        result = _decode_itinerary(corrupted)
        # Empty itin_data may produce an itinerary with empty flights

    def test_flights_list_is_none(self, valid_element):
        corrupted = copy.deepcopy(valid_element)
        corrupted[0][2] = None
        result = _decode_itinerary(corrupted)
        if result is not None:
            assert result.flights == []

    def test_summary_is_none(self, valid_element):
        corrupted = copy.deepcopy(valid_element)
        corrupted[1] = None
        result = _decode_itinerary(corrupted)
        if result is not None:
            assert result.price_info is None


class TestCorruptFullResponse:
    """Corrupt full response at various levels."""

    @pytest.fixture
    def valid_response(self):
        seg = make_flight_segment()
        itin = make_itinerary_element([seg])
        return make_full_response(best_itins=[itin])

    @pytest.mark.parametrize("index", range(4))
    def test_corrupt_top_level_with_none(self, valid_response, index):
        corrupted = copy.deepcopy(valid_response)
        corrupted[index] = None
        result = decode_result(corrupted)
        assert isinstance(result, SearchResult)

    def test_best_list_is_string(self, valid_response):
        corrupted = copy.deepcopy(valid_response)
        corrupted[2] = "not a list"
        result = decode_result(corrupted)
        assert isinstance(result, SearchResult)
        assert result.best == []

    def test_best_list_is_empty(self, valid_response):
        corrupted = copy.deepcopy(valid_response)
        corrupted[2] = [[]]
        result = decode_result(corrupted)
        assert isinstance(result, SearchResult)
        assert result.best == []

    def test_all_none(self):
        result = decode_result([None, None, None, None])
        assert isinstance(result, SearchResult)
        assert result.best == []
        assert result.other == []

    def test_empty_list(self):
        result = decode_result([])
        assert isinstance(result, SearchResult)
        assert result.best == []

    def test_nested_nones(self):
        result = decode_result([None, None, [[None, None, None]], [[None]]])
        assert isinstance(result, SearchResult)


class TestCorruptLayover:
    """Corrupt layover data."""

    @pytest.mark.parametrize("data", [
        [],
        [None],
        "string",
        [None, None, None, None],
        [120],
        [120, None],
        [None, "ATL", "ATL", "not-a-list"],
    ])
    def test_various_malformed_layovers(self, data):
        result = _decode_layover(data)
        # Must not crash
        if result is not None:
            assert hasattr(result, "minutes")
