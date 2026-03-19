"""Chaos / corruption tests for decoder resilience.

Systematically corrupt valid responses at every index to verify the
decoder never crashes — it should gracefully degrade.
"""

import copy

import pytest

from swoop.decoder import (
    _decode_segment,
    _decode_itinerary,
    _decode_layover,
    decode_result,
    RawSearchResult,
)
from tests.factories import make_flight_segment, make_itinerary_element, make_full_response


class TestCorruptSegment:
    """Corrupt each of the 33 segment indices."""

    @pytest.fixture
    def valid_segment(self):
        return make_flight_segment()

    @pytest.mark.parametrize("index", range(33))
    def test_corrupt_with_none(self, valid_segment, index):
        corrupted = copy.deepcopy(valid_segment)
        corrupted[index] = None
        result = _decode_segment(corrupted)
        if result is not None:
            assert isinstance(result.codeshares, list)
            assert len(result.departure_date) == 3
            assert len(result.arrival_time) == 2
            assert result.travel_time >= 0

    @pytest.mark.parametrize("index", range(33))
    def test_corrupt_with_string(self, valid_segment, index):
        corrupted = copy.deepcopy(valid_segment)
        corrupted[index] = "corrupted"
        result = _decode_segment(corrupted)
        if result is not None:
            assert isinstance(result.codeshares, list)
            assert result.travel_time >= 0

    @pytest.mark.parametrize("index", range(33))
    def test_corrupt_with_empty_list(self, valid_segment, index):
        corrupted = copy.deepcopy(valid_segment)
        corrupted[index] = []
        result = _decode_segment(corrupted)
        if result is not None:
            assert isinstance(result.codeshares, list)
            assert result.travel_time >= 0


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
        if result is not None:
            assert isinstance(result.segments, list)
            assert isinstance(result.layovers, list)
            assert result.price is None or isinstance(result.price, int)

    @pytest.mark.parametrize("index", range(11))
    def test_corrupt_root_with_string(self, valid_element, index):
        corrupted = copy.deepcopy(valid_element)
        corrupted[index] = "bad"
        result = _decode_itinerary(corrupted)
        if result is not None:
            assert isinstance(result.segments, list)
            assert isinstance(result.layovers, list)

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
            assert result.segments == []

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
        assert isinstance(result, RawSearchResult)

    def test_best_list_is_string(self, valid_response):
        corrupted = copy.deepcopy(valid_response)
        corrupted[2] = "not a list"
        result = decode_result(corrupted)
        assert isinstance(result, RawSearchResult)
        assert result.best == []

    def test_best_list_is_empty(self, valid_response):
        corrupted = copy.deepcopy(valid_response)
        corrupted[2] = [[]]
        result = decode_result(corrupted)
        assert isinstance(result, RawSearchResult)
        assert result.best == []

    def test_all_none(self):
        result = decode_result([None, None, None, None])
        assert isinstance(result, RawSearchResult)
        assert result.best == []
        assert result.other == []

    def test_empty_list(self):
        result = decode_result([])
        assert isinstance(result, RawSearchResult)
        assert result.best == []

    def test_nested_nones(self):
        result = decode_result([None, None, [[None, None, None]], [[None]]])
        assert isinstance(result, RawSearchResult)


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
        if result is not None:
            assert result.minutes >= 0
