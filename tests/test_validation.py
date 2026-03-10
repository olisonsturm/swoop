"""Tests for input validation module."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swoop._validate import (  # noqa: E402
    validate_adults,
    validate_cabin,
    validate_date,
    validate_iata_code,
    validate_search_params,
    validate_time_range,
)


class TestValidateIataCode:
    def test_valid_codes(self):
        for code in ("JFK", "LAX", "SFO", "NRT", "LHR"):
            validate_iata_code(code, "origin")  # should not raise

    def test_lowercase_rejected(self):
        with pytest.raises(ValueError, match="3-letter uppercase IATA"):
            validate_iata_code("jfk", "origin")

    def test_too_short(self):
        with pytest.raises(ValueError, match="3-letter uppercase IATA"):
            validate_iata_code("JF", "origin")

    def test_too_long(self):
        with pytest.raises(ValueError, match="3-letter uppercase IATA"):
            validate_iata_code("JFKX", "origin")

    def test_numeric_rejected(self):
        with pytest.raises(ValueError, match="3-letter uppercase IATA"):
            validate_iata_code("123", "origin")

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="3-letter uppercase IATA"):
            validate_iata_code("", "origin")

    def test_non_string_rejected(self):
        with pytest.raises(ValueError, match="3-letter uppercase IATA"):
            validate_iata_code(123, "origin")  # type: ignore[arg-type]

    def test_field_name_in_error(self):
        with pytest.raises(ValueError, match="destination"):
            validate_iata_code("bad", "destination")

    def test_airportsdata_present_valid(self):
        """When airportsdata is installed, known codes pass."""
        import swoop._validate as mod

        old_loaded, old_db = mod._iata_db_loaded, mod._iata_db
        try:
            mod._iata_db_loaded = True
            mod._iata_db = {"JFK": {}, "LAX": {}}
            validate_iata_code("JFK", "origin")  # should not raise
        finally:
            mod._iata_db_loaded, mod._iata_db = old_loaded, old_db

    def test_airportsdata_present_unknown(self):
        """When airportsdata is installed, unknown codes are rejected."""
        import swoop._validate as mod

        old_loaded, old_db = mod._iata_db_loaded, mod._iata_db
        try:
            mod._iata_db_loaded = True
            mod._iata_db = {"JFK": {}, "LAX": {}}
            with pytest.raises(ValueError, match="not a known IATA airport code"):
                validate_iata_code("ZZZ", "origin")
        finally:
            mod._iata_db_loaded, mod._iata_db = old_loaded, old_db

    def test_airportsdata_absent(self):
        """When airportsdata is not installed, format-valid codes pass."""
        import swoop._validate as mod

        old_loaded, old_db = mod._iata_db_loaded, mod._iata_db
        try:
            mod._iata_db_loaded = True
            mod._iata_db = None
            validate_iata_code("ZZZ", "origin")  # should not raise
        finally:
            mod._iata_db_loaded, mod._iata_db = old_loaded, old_db


class TestValidateDate:
    def test_valid_dates(self):
        for d in ("2026-06-01", "2025-01-15", "2024-12-31"):
            validate_date(d, "date")  # should not raise

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="valid YYYY-MM-DD"):
            validate_date("06/01/2026", "date")

    def test_invalid_date(self):
        with pytest.raises(ValueError, match="valid YYYY-MM-DD"):
            validate_date("2026-02-30", "date")

    def test_empty_string(self):
        with pytest.raises(ValueError, match="valid YYYY-MM-DD"):
            validate_date("", "date")

    def test_non_string(self):
        with pytest.raises(ValueError, match="must be a date string"):
            validate_date(20260601, "date")  # type: ignore[arg-type]

    def test_past_dates_allowed(self):
        """Past dates are allowed (tests use past dates)."""
        validate_date("2020-01-01", "date")  # should not raise


class TestValidateAdults:
    def test_valid(self):
        for n in (1, 2, 5, 9):
            validate_adults(n)  # should not raise

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="adults must be >= 1"):
            validate_adults(0)

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="adults must be >= 1"):
            validate_adults(-1)

    def test_non_int_rejected(self):
        with pytest.raises(ValueError, match="adults must be >= 1"):
            validate_adults(1.5)  # type: ignore[arg-type]


class TestValidateCabin:
    def test_valid_cabins(self):
        for c in ("economy", "premium-economy", "business", "first"):
            validate_cabin(c)  # should not raise

    def test_invalid_cabin(self):
        with pytest.raises(ValueError, match="Invalid cabin"):
            validate_cabin("coach")


class TestValidateTimeRange:
    def test_none_is_ok(self):
        validate_time_range(None, "earliest_departure", 0, 23)  # should not raise

    def test_valid_values(self):
        validate_time_range(0, "earliest_departure", 0, 23)
        validate_time_range(23, "earliest_departure", 0, 23)
        validate_time_range(1, "latest_departure", 1, 24)
        validate_time_range(24, "latest_departure", 1, 24)

    def test_below_min(self):
        with pytest.raises(ValueError, match="between 0 and 23"):
            validate_time_range(-1, "earliest_departure", 0, 23)

    def test_above_max(self):
        with pytest.raises(ValueError, match="between 1 and 24"):
            validate_time_range(25, "latest_departure", 1, 24)

    def test_non_int_rejected(self):
        with pytest.raises(ValueError, match="between"):
            validate_time_range("8", "earliest_departure", 0, 23)  # type: ignore[arg-type]


class TestValidateSearchParams:
    def test_valid_params(self):
        validate_search_params("JFK", "LAX", "2026-06-01")  # should not raise

    def test_valid_roundtrip(self):
        validate_search_params(
            "JFK", "LAX", "2026-06-01",
            return_date="2026-06-08",
            cabin="business",
            adults=2,
        )  # should not raise

    def test_bad_origin(self):
        with pytest.raises(ValueError, match="origin"):
            validate_search_params("jfk", "LAX", "2026-06-01")

    def test_bad_destination(self):
        with pytest.raises(ValueError, match="destination"):
            validate_search_params("JFK", "la", "2026-06-01")

    def test_bad_date(self):
        with pytest.raises(ValueError, match="date"):
            validate_search_params("JFK", "LAX", "not-a-date")

    def test_bad_return_date(self):
        with pytest.raises(ValueError, match="return_date"):
            validate_search_params("JFK", "LAX", "2026-06-01", return_date="bad")

    def test_bad_cabin(self):
        with pytest.raises(ValueError, match="Invalid cabin"):
            validate_search_params("JFK", "LAX", "2026-06-01", cabin="coach")

    def test_bad_adults(self):
        with pytest.raises(ValueError, match="adults"):
            validate_search_params("JFK", "LAX", "2026-06-01", adults=0)

    def test_bad_time_range(self):
        with pytest.raises(ValueError, match="earliest_departure"):
            validate_search_params("JFK", "LAX", "2026-06-01", earliest_departure=-1)

    def test_time_ranges_validated(self):
        with pytest.raises(ValueError, match="latest_departure"):
            validate_search_params("JFK", "LAX", "2026-06-01", latest_departure=25)
        with pytest.raises(ValueError, match="earliest_arrival"):
            validate_search_params("JFK", "LAX", "2026-06-01", earliest_arrival=24)
        with pytest.raises(ValueError, match="latest_arrival"):
            validate_search_params("JFK", "LAX", "2026-06-01", latest_arrival=0)
        with pytest.raises(ValueError, match="return_earliest_departure"):
            validate_search_params("JFK", "LAX", "2026-06-01", return_date="2026-06-08", return_earliest_departure=-1)
        with pytest.raises(ValueError, match="return_latest_departure"):
            validate_search_params("JFK", "LAX", "2026-06-01", return_date="2026-06-08", return_latest_departure=25)
