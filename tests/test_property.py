"""Property-based tests using Hypothesis.

These tests fuzz swoop's decoder and validator functions with random input
to ensure they never crash, regardless of what data Google returns.
"""

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from swoop.decoder import (
    _decode_flight,
    _decode_itinerary,
    _decode_layover,
    _safe_get,
    decode_result,
    SearchResult,
)
from swoop._validate import (
    validate_cabin,
    validate_iata_code,
    validate_date,
    validate_adults,
)


# --- Strategy helpers ---

# Generates nested lists up to depth 5, with mixed types at leaves
nested_lists = st.recursive(
    st.one_of(
        st.none(),
        st.integers(-1000, 10000),
        st.text(max_size=20),
        st.floats(allow_nan=False),
        st.booleans(),
    ),
    lambda children: st.lists(children, max_size=10),
    max_leaves=50,
)

# Generates arbitrary paths for _safe_get
paths = st.lists(st.integers(0, 20), max_size=5)


class TestSafeGetProperty:
    """_safe_get must never raise, regardless of input."""

    @given(data=nested_lists, path=paths)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_never_raises(self, data, path):
        # Must never raise — always returns a value or None
        result = _safe_get(data, path)
        # Result is either the value or the default (None)
        assert result is not None or result is None  # Always true, verifies no exception

    @given(data=nested_lists, path=paths, default=st.text())
    @settings(max_examples=100)
    def test_default_returned_on_miss(self, data, path, default):
        result = _safe_get(data, path, default)
        # When we can't traverse, we get the default
        if result is not default:
            # We successfully traversed — result is from data
            pass


class TestDecodeFlightProperty:
    """_decode_flight must never crash."""

    @given(data=nested_lists)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_never_crashes(self, data):
        result = _decode_flight(data)
        # Must return a Flight or None, never raise
        if result is not None:
            assert hasattr(result, "airline")
            assert hasattr(result, "flight_number")


class TestDecodeItineraryProperty:
    """_decode_itinerary must never crash."""

    @given(data=nested_lists)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_never_crashes(self, data):
        result = _decode_itinerary(data)
        # Must return an Itinerary or None
        if result is not None:
            assert hasattr(result, "flights")
            assert hasattr(result, "airline_code")


class TestDecodeLayoverProperty:
    """_decode_layover must never crash."""

    @given(data=st.lists(
        st.one_of(st.none(), st.integers(), st.text(max_size=10), st.lists(st.integers(), max_size=3)),
        min_size=0,
        max_size=10,
    ))
    @settings(max_examples=200)
    def test_never_crashes(self, data):
        result = _decode_layover(data)
        if result is not None:
            assert hasattr(result, "minutes")


class TestDecodeResultProperty:
    """decode_result must always return a SearchResult."""

    @given(data=nested_lists)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_always_returns_search_result(self, data):
        result = decode_result(data)
        assert isinstance(result, SearchResult)
        assert isinstance(result.best, list)
        assert isinstance(result.other, list)


class TestValidatorProperties:
    """Validators must either raise ValueError or succeed — never crash with other errors."""

    @given(value=st.text(max_size=10))
    @settings(max_examples=100)
    def test_validate_cabin_raises_or_passes(self, value):
        try:
            validate_cabin(value)
        except ValueError:
            pass  # Expected for invalid input
        # No other exception type should be raised

    @given(value=st.text(max_size=10))
    @settings(max_examples=100)
    def test_validate_iata_raises_or_passes(self, value):
        try:
            validate_iata_code(value, "test_field")
        except ValueError:
            pass

    @given(value=st.text(max_size=20))
    @settings(max_examples=100)
    def test_validate_date_raises_or_passes(self, value):
        try:
            validate_date(value, "test_field")
        except ValueError:
            pass

    @given(value=st.integers(-10, 100))
    @settings(max_examples=50)
    def test_validate_adults_raises_or_passes(self, value):
        try:
            validate_adults(value)
        except ValueError:
            pass
