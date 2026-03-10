"""Error message quality tests.

Every user-facing error message should include the bad input value and
field name so developers can diagnose issues quickly.
"""

import pytest

from swoop._validate import (
    validate_cabin,
    validate_iata_code,
    validate_date,
    validate_adults,
    validate_time_range,
    parse_flight_number,
)
from swoop.exceptions import SwoopHTTPError, SwoopRateLimitError, SwoopParseError


class TestValidationErrorMessages:
    """Validation errors include bad value and field name."""

    def test_iata_includes_bad_value(self):
        with pytest.raises(ValueError, match="jfk"):
            validate_iata_code("jfk", "origin")

    def test_iata_includes_field_name(self):
        with pytest.raises(ValueError, match="destination"):
            validate_iata_code("bad", "destination")

    def test_date_includes_bad_value(self):
        with pytest.raises(ValueError, match="not-a-date"):
            validate_date("not-a-date", "date")

    def test_date_includes_field_name(self):
        with pytest.raises(ValueError, match="return_date"):
            validate_date("bad", "return_date")

    def test_cabin_includes_bad_value(self):
        with pytest.raises(ValueError, match="coach"):
            validate_cabin("coach")

    def test_cabin_lists_valid_options(self):
        with pytest.raises(ValueError, match="economy"):
            validate_cabin("bad")

    def test_adults_includes_bad_value(self):
        with pytest.raises(ValueError, match="0"):
            validate_adults(0)

    def test_time_range_includes_field_name(self):
        with pytest.raises(ValueError, match="earliest_departure"):
            validate_time_range(-1, "earliest_departure", 0, 23)

    def test_time_range_includes_bounds(self):
        with pytest.raises(ValueError, match="0.*23"):
            validate_time_range(-1, "earliest_departure", 0, 23)

    def test_flight_number_empty_message(self):
        with pytest.raises(ValueError, match="must not be empty"):
            parse_flight_number("")

    def test_flight_number_non_string_message(self):
        with pytest.raises(ValueError, match="must be a string"):
            parse_flight_number(123)  # type: ignore[arg-type]

    def test_flight_number_garbage_includes_value(self):
        with pytest.raises(ValueError, match="not-a-flight"):
            parse_flight_number("not-a-flight")


class TestExceptionMessages:
    """Exception messages include relevant details."""

    def test_http_error_includes_status_code(self):
        err = SwoopHTTPError(503)
        assert "503" in str(err)

    def test_http_error_stores_status_code(self):
        err = SwoopHTTPError(503)
        assert err.status_code == 503

    def test_rate_limit_mentions_429(self):
        err = SwoopRateLimitError()
        assert "429" in str(err)

    def test_parse_error_includes_detail(self):
        err = SwoopParseError("Failed to decode protobuf")
        assert "protobuf" in str(err)

    def test_custom_http_message(self):
        err = SwoopHTTPError(500, "Internal server error")
        assert err.status_code == 500
        assert "Internal server error" in str(err)
