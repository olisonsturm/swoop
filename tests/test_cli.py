"""Tests for swoop CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from swoop.cli import main
from swoop import PriceResult, SearchResult, TripLeg, TripOption
from swoop.cli.commands import search_cmd, price_cmd
from swoop.cli.utils import format_time, format_duration, format_date_display, format_route, check_past_date, IATACodeType, DateType
from swoop.decoder import (
    BookingOption,
    CarbonEmissions,
    Flight,
    Itinerary,
    Layover,
    PriceRange,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_flight(**overrides) -> Flight:
    defaults = dict(
        airline="DL",
        airline_name="Delta Air Lines",
        flight_number="2300",
        departure_airport_code="JFK",
        arrival_airport_code="LAX",
        departure_time=(8, 30),
        arrival_time=(11, 45),
        departure_date=(2026, 6, 15),
        arrival_date=(2026, 6, 15),
        travel_time=315,
        aircraft="Boeing 737-900",
        legroom="32 inches",
    )
    defaults.update(overrides)
    return Flight(**defaults)


def _make_itinerary(**overrides) -> Itinerary:
    flight = _make_flight()
    defaults = dict(
        airline_code="DL",
        airline_names=["Delta Air Lines"],
        flights=[flight],
        layovers=[],
        travel_time=315,
        departure_airport_code="JFK",
        arrival_airport_code="LAX",
        departure_date=(2026, 6, 15),
        arrival_date=(2026, 6, 15),
        departure_time=(8, 30),
        arrival_time=(11, 45),
        direct_price=247,
        booking_token="token123",
        stop_count=0,
    )
    defaults.update(overrides)
    return Itinerary(**defaults)


def _make_connecting_itinerary() -> Itinerary:
    f1 = _make_flight(
        airline="UA", airline_name="United Airlines", flight_number="1234",
        departure_airport_code="JFK", arrival_airport_code="ORD",
        departure_time=(10, 15), arrival_time=(12, 20),
        travel_time=125,
    )
    f2 = _make_flight(
        airline="UA", airline_name="United Airlines", flight_number="5678",
        departure_airport_code="ORD", arrival_airport_code="LAX",
        departure_time=(14, 20), arrival_time=(15, 20),
        travel_time=180,
    )
    lay = Layover(
        minutes=120, departure_airport_code="ORD",
        departure_airport_name="O'Hare International Airport",
    )
    return Itinerary(
        airline_code="UA",
        airline_names=["United Airlines"],
        flights=[f1, f2],
        layovers=[lay],
        travel_time=485,
        departure_airport_code="JFK",
        arrival_airport_code="LAX",
        departure_date=(2026, 6, 15),
        arrival_date=(2026, 6, 15),
        departure_time=(10, 15),
        arrival_time=(15, 20),
        direct_price=183,
        booking_token="token456",
        stop_count=1,
    )


def _make_trip_option(itinerary: Itinerary, *, index: int) -> TripOption:
    return TripOption(
        selector=f"selector-{index}",
        price=itinerary.price,
        legs=[
            TripLeg(
                origin=itinerary.departure_airport_code,
                destination=itinerary.arrival_airport_code,
                date="2026-06-15",
                itinerary=itinerary,
            )
        ],
    )


def _make_search_result(n: int = 3) -> SearchResult:
    options = [_make_trip_option(_make_itinerary(), index=1)]
    if n >= 2:
        options.append(_make_trip_option(_make_itinerary(
            airline_code="B6",
            airline_names=["JetBlue"],
            direct_price=219,
            departure_time=(9, 0),
            arrival_time=(12, 30),
            travel_time=330,
            flights=[_make_flight(
                airline="B6", airline_name="JetBlue", flight_number="524",
                departure_time=(9, 0), arrival_time=(12, 30), travel_time=330,
            )],
        ), index=2))
    if n >= 3:
        options.append(_make_trip_option(_make_connecting_itinerary(), index=3))
    return SearchResult(
        results=options,
        price_range=PriceRange(low=127, high=450),
        is_complete=True,
    )


def _make_booking_options() -> list[BookingOption]:
    return [
        BookingOption(price=219, brand_label="Blue Basic", brand_code="BASIC", is_basic=True, fare_family="basic"),
        BookingOption(price=249, brand_label="Blue", brand_code="STANDARD", is_basic=False, fare_family="standard"),
        BookingOption(price=289, brand_label="Blue Plus", brand_code="ENHANCED", is_basic=False, fare_family="enhanced"),
    ]


# ---------------------------------------------------------------------------
# Utils tests
# ---------------------------------------------------------------------------


class TestFormatTime:
    def test_morning(self):
        assert format_time(8, 30) == "8:30a"

    def test_afternoon(self):
        assert format_time(14, 0) == "2:00p"

    def test_midnight(self):
        assert format_time(0, 0) == "12:00a"

    def test_noon(self):
        assert format_time(12, 0) == "12:00p"

    def test_single_digit_minutes(self):
        assert format_time(9, 5) == "9:05a"


class TestFormatDuration:
    def test_hours_and_minutes(self):
        assert format_duration(315) == "5h 15m"

    def test_hours_only(self):
        assert format_duration(120) == "2h"

    def test_minutes_only(self):
        assert format_duration(45) == "45m"

    def test_zero(self):
        assert format_duration(0) == "0m"


class TestFormatDateDisplay:
    def test_valid_date(self):
        result = format_date_display("2026-06-15")
        assert "Jun" in result
        assert "2026" in result

    def test_invalid_date(self):
        assert format_date_display("bad") == "bad"


class TestFormatRoute:
    def test_direct(self):
        itin = _make_itinerary()
        assert format_route(itin) == "JFK -> LAX"

    def test_connecting(self):
        itin = _make_connecting_itinerary()
        assert format_route(itin) == "JFK -> ORD -> LAX"


class TestCheckPastDate:
    def test_future_date(self):
        assert check_past_date("2099-01-01") is None

    def test_past_date(self):
        result = check_past_date("2020-01-01")
        assert result is not None
        assert "past" in result.lower()


class TestIATACodeType:
    def test_uppercases(self):
        t = IATACodeType()
        assert t.convert("jfk", None, None) == "JFK"

    def test_rejects_invalid(self):
        t = IATACodeType()
        with pytest.raises(Exception):
            t.convert("XY", None, None)


class TestDateType:
    def test_valid(self):
        t = DateType()
        assert t.convert("2026-06-15", None, None) == "2026-06-15"

    def test_invalid(self):
        t = DateType()
        with pytest.raises(Exception):
            t.convert("2026-13-45", None, None)


# ---------------------------------------------------------------------------
# CLI group tests
# ---------------------------------------------------------------------------


class TestMainGroup:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        assert "price" in result.output
        assert "book" not in result.output

    def test_no_subcommand_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "search" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Search command tests
# ---------------------------------------------------------------------------


class TestSearchCommand:
    @patch("swoop.cli.commands._run_search")
    def test_json_output(self, mock_search):
        mock_search.return_value = _make_search_result()
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-o", "json", "-q",
        ])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["query"]["origin"] == "JFK"
        assert data["price_source"] == "shopping"
        assert len(data["results"]) == 3
        assert data["results"][0]["price_usd"] == 247
        assert data["results"][0]["selector"] == "selector-1"
        assert data["results"][0]["legs"][0]["itinerary"]["flight_summary"] == "DL 2300"

    @patch("swoop.cli.commands._run_search")
    def test_table_output(self, mock_search):
        mock_search.return_value = _make_search_result()
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 0
        assert "DL 2300" in result.output  # flight_summary
        assert "Nonstop" in result.output
        assert "Prices shown are shopping totals" in result.output
        assert "--price 1" in result.output
        assert "swoop search JFK LAX 2026-06-15 --price 1" in result.output

    @patch("swoop.cli.commands._run_search")
    def test_csv_output(self, mock_search):
        mock_search.return_value = _make_search_result()
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-o", "csv", "-q",
        ])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert "index" in lines[0]  # header
        assert "selector" in lines[0]
        assert len(lines) == 4  # header + 3 results

    @patch("swoop.cli.commands._run_search")
    def test_brief_output(self, mock_search):
        mock_search.return_value = _make_search_result()
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-o", "brief", "-q",
        ])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) >= 5
        assert "$247" in lines[0]
        assert "DL 2300" in lines[0]
        assert "Prices shown are shopping totals." in result.output
        assert "swoop search JFK LAX 2026-06-15 --price 1" in result.output

    @patch("swoop.cli.commands._run_search")
    def test_limit(self, mock_search):
        mock_search.return_value = _make_search_result()
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-o", "json", "-q", "-l", "1",
        ])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert len(data["results"]) == 1

    @patch("swoop.cli.commands._run_search")
    def test_no_results(self, mock_search):
        mock_search.return_value = SearchResult(results=[])
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 1
        assert "No flights found" in result.stderr

    def test_bad_iata(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "XY", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 2
        assert "not a valid IATA" in result.stderr

    def test_bad_date(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-13-45", "-q",
        ])
        assert result.exit_code == 2
        assert "not a valid date" in result.stderr

    @patch("swoop.cli.commands._run_search")
    def test_nonstop_flag(self, mock_search):
        mock_search.return_value = _make_search_result(1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "--nonstop", "-o", "json", "-q",
        ])
        assert result.exit_code == 0
        # Verify nonstop was passed
        _, kwargs = mock_search.call_args
        assert kwargs["nonstop"] is True

    @patch("swoop.cli.commands._run_search")
    def test_roundtrip(self, mock_search):
        mock_search.return_value = _make_search_result(1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-r", "2026-06-22", "-o", "json", "-q",
        ])
        assert result.exit_code == 0
        _, kwargs = mock_search.call_args
        assert kwargs["return_date"] == "2026-06-22"

    @patch("swoop.cli.commands._run_search")
    def test_rate_limit_error(self, mock_search):
        from swoop.exceptions import SwoopRateLimitError
        mock_search.side_effect = SwoopRateLimitError()
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 3
        assert "Rate limited" in result.stderr

    @patch("swoop.cli.commands._run_search")
    def test_http_error(self, mock_search):
        from swoop.exceptions import SwoopHTTPError
        mock_search.side_effect = SwoopHTTPError(500)
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 3
        assert "HTTP 500" in result.stderr

    @patch("swoop.cli.commands._run_search")
    def test_parse_error(self, mock_search):
        from swoop.exceptions import SwoopParseError
        mock_search.side_effect = SwoopParseError("bad")
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 4
        assert "Could not parse" in result.stderr

    @patch("swoop.cli.commands._run_search")
    def test_validation_error(self, mock_search):
        mock_search.side_effect = ValueError("origin must be valid")
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 2
        assert "origin must be valid" in result.stderr

    @patch("swoop.cli.commands._run_search")
    def test_airline_filter(self, mock_search):
        mock_search.return_value = _make_search_result(1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-a", "DL", "-a", "UA", "-o", "json", "-q",
        ])
        assert result.exit_code == 0
        _, kwargs = mock_search.call_args
        assert kwargs["airline"] == ("DL", "UA")

    @patch("swoop.cli.commands._run_search")
    def test_case_insensitive_iata(self, mock_search):
        mock_search.return_value = _make_search_result(1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "jfk", "lax", "2026-06-15", "-o", "json", "-q",
        ])
        assert result.exit_code == 0
        # IATA should be uppercased
        args = mock_search.call_args[0]
        assert args[0] == "JFK"
        assert args[1] == "LAX"

    @patch("swoop.cli.commands._run_search")
    def test_roundtrip_labels_prices(self, mock_search):
        """Roundtrip search renders complete trip rows."""
        mock_search.return_value = _make_search_result(1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-r", "2026-06-22", "-q",
        ])
        assert result.exit_code == 0
        assert "JFK -> LAX" in result.output

    @patch("swoop.cli.commands._price_trip_selector")
    @patch("swoop.cli.commands._run_search")
    def test_price_drilldown(self, mock_search, mock_price_trip_selector):
        """--price N prices the exact selected itinerary."""
        mock_search.return_value = _make_search_result()
        mock_price_trip_selector.return_value = PriceResult(price=342, fare_brand="Main Cabin", rpc_calls=1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "--price", "1", "-q",
        ])
        assert result.exit_code == 0
        assert "$342" in result.output
        mock_price_trip_selector.assert_called_once()
        assert mock_price_trip_selector.call_args[0][0] == "selector-1"

    @patch("swoop.cli.commands._price_trip_selector")
    @patch("swoop.cli.commands._run_search")
    def test_price_drilldown_uses_selected_row(self, mock_search, mock_price_trip_selector):
        """Drilldown passes the selected row's opaque selector."""
        shared_first = _make_flight(airline="UA", airline_name="United Airlines", flight_number="1234")
        second_a = _make_flight(
            airline="UA",
            airline_name="United Airlines",
            flight_number="2001",
            departure_airport_code="ORD",
            arrival_airport_code="LAX",
            departure_time=(12, 45),
            arrival_time=(14, 55),
            travel_time=130,
        )
        second_b = _make_flight(
            airline="UA",
            airline_name="United Airlines",
            flight_number="2002",
            departure_airport_code="ORD",
            arrival_airport_code="SFO",
            departure_time=(13, 10),
            arrival_time=(15, 40),
            travel_time=150,
        )
        itin_a = _make_itinerary(
            flights=[shared_first, second_a],
            layovers=[Layover(minutes=90, departure_airport_code="ORD")],
            departure_airport_code="JFK",
            arrival_airport_code="LAX",
            direct_price=301,
            stop_count=1,
            travel_time=345,
        )
        itin_b = _make_itinerary(
            flights=[shared_first, second_b],
            layovers=[Layover(minutes=110, departure_airport_code="ORD")],
            departure_airport_code="JFK",
            arrival_airport_code="SFO",
            direct_price=355,
            stop_count=1,
            travel_time=390,
        )
        mock_search.return_value = SearchResult(results=[
            TripOption(selector="selector-a", price=301, legs=[TripLeg(origin="JFK", destination="LAX", date="2026-06-15", itinerary=itin_a)]),
            TripOption(selector="selector-b", price=355, legs=[TripLeg(origin="JFK", destination="SFO", date="2026-06-15", itinerary=itin_b)]),
        ])
        mock_price_trip_selector.return_value = PriceResult(price=355, fare_brand="Main Cabin", rpc_calls=0)

        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "--price", "2", "-q",
        ])
        assert result.exit_code == 0
        assert mock_price_trip_selector.call_args[0][0] == "selector-b"

    @patch("swoop.cli.commands._run_search")
    def test_price_drilldown_rejects_limit(self, mock_search):
        """--price cannot be combined with --limit."""
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "--price", "1", "-l", "5", "-q",
        ])
        assert result.exit_code == 2
        assert "--price/--price-selector cannot be combined with --limit" in result.stderr

    @patch("swoop.cli.commands._run_search")
    def test_price_drilldown_rejects_csv(self, mock_search):
        """--price cannot be combined with -o csv."""
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "--price", "1", "-o", "csv", "-q",
        ])
        assert result.exit_code == 2
        assert "--price/--price-selector cannot be combined with -o csv" in result.stderr

    @patch("swoop.cli.commands._run_search")
    def test_connecting_flight_table(self, mock_search):
        """Table output shows layover info for connecting flights."""
        mock_search.return_value = SearchResult(
            results=[_make_trip_option(_make_connecting_itinerary(), index=1)],
        )
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 0
        assert "stop" in result.output
        assert "ORD" in result.output

    @patch("swoop.cli.commands._run_search_legs")
    def test_leg_search_mode(self, mock_search_legs):
        mock_search_legs.return_value = _make_search_result(1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "--leg", "JFK", "LAX", "2026-06-15", "--leg", "LAX", "SFO", "2026-06-18", "-q",
        ])
        assert result.exit_code == 0
        mock_search_legs.assert_called_once()

    @patch("swoop.cli.commands._price_trip_selector")
    def test_price_selector_mode(self, mock_price_trip_selector):
        mock_price_trip_selector.return_value = PriceResult(price=342, fare_brand="Main Cabin", rpc_calls=1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "search", "--price-selector", "selector-1", "-q",
        ])
        assert result.exit_code == 0
        mock_price_trip_selector.assert_called_once_with("selector-1", timeout=90, retries=0)


# ---------------------------------------------------------------------------
# Price command tests
# ---------------------------------------------------------------------------


class TestPriceCommand:
    @patch("swoop.check_price")
    def test_price_positional_args(self, mock_check):
        """Price command with positional FLIGHT ORIGIN DEST DATE."""
        mock_check.return_value = PriceResult(price=342, fare_brand="Main Cabin", rpc_calls=1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "price", "DL2300", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 0
        assert "$342" in result.output

    @patch("swoop.check_price")
    def test_price_json_output(self, mock_check):
        mock_check.return_value = PriceResult(price=342, fare_brand="Main Cabin", rpc_calls=1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "price", "DL2300", "JFK", "LAX", "2026-06-15",
            "-o", "json", "-q",
        ])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["price_usd"] == 342

    @patch("swoop.check_price")
    def test_price_brief_output(self, mock_check):
        mock_check.return_value = PriceResult(price=342, fare_brand="Main Cabin", rpc_calls=1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "price", "DL2300", "JFK", "LAX", "2026-06-15",
            "-o", "brief", "-q",
        ])
        assert result.exit_code == 0
        assert "$342" in result.output
        assert "1-leg" in result.output

    @patch("swoop.check_price")
    def test_price_not_found(self, mock_check):
        mock_check.return_value = None
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "price", "DL2300", "JFK", "LAX", "2026-06-15", "-q",
        ])
        assert result.exit_code == 1

    def test_price_missing_args(self):
        """Positional args missing should error."""
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, ["price", "DL2300"])
        assert result.exit_code == 2

    @patch("swoop.price_legs")
    def test_price_leg_syntax(self, mock_price_legs):
        """--leg repeated syntax works."""
        mock_price_legs.return_value = PriceResult(price=684, fare_brand="Main Cabin", rpc_calls=3)
        runner = CliRunner()
        result = runner.invoke(main, [
            "price",
            "--leg", "JFK", "LAX", "2026-06-15", "DL2300",
            "--leg", "LAX", "JFK", "2026-06-22", "DL2301",
            "-q",
        ])
        assert result.exit_code == 0
        assert "$684" in result.output
        call_args = mock_price_legs.call_args
        assert len(call_args[0][0]) == 2
        assert call_args[0][0][1].flight_number == "DL2301"

    def test_price_positional_and_leg_error(self):
        """Positional + --leg is an error."""
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "price", "DL2300", "JFK", "LAX", "2026-06-15",
            "--leg", "JFK", "LAX", "2026-06-15", "DL2300",
        ])
        assert result.exit_code == 2
        assert "cannot be used together" in result.stderr

    def test_price_return_flight_requires_return_date(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "price", "DL2300", "JFK", "LAX", "2026-06-15", "--return-flight", "DL2301",
        ])
        assert result.exit_code == 2
        assert "--return-flight requires --return-date" in result.stderr

    def test_price_return_date_requires_return_flight_for_positional_mode(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "price", "DL2300", "JFK", "LAX", "2026-06-15", "--return-date", "2026-06-22",
        ])
        assert result.exit_code == 2
        assert "--return-date requires --return-flight" in result.stderr

    def test_price_leg_conflicts_with_return_flags(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            "price",
            "--leg", "JFK", "LAX", "2026-06-15", "DL2300",
            "--return-date", "2026-06-22",
        ])
        assert result.exit_code == 2
        assert "--leg cannot be combined" in result.stderr

    @patch("swoop.cli.commands._price_trip_selector")
    def test_price_selector_mode(self, mock_price_trip_selector):
        mock_price_trip_selector.return_value = PriceResult(price=342, fare_brand="Main Cabin", rpc_calls=1)
        runner = CliRunner()
        result = runner.invoke(main, [
            "price", "--selector", "selector-1", "-q",
        ])
        assert result.exit_code == 0
        mock_price_trip_selector.assert_called_once_with("selector-1", timeout=90, retries=2)


# ---------------------------------------------------------------------------
# __main__ entry point
# ---------------------------------------------------------------------------


class TestMainModule:
    def test_python_m_swoop_help(self):
        """python -m swoop --help should work."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "swoop", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "search" in result.stdout
