"""Additional CLI branch coverage for validation and error handling."""

from unittest.mock import patch

from click.testing import CliRunner

from swoop import PriceResult
from swoop.cli import main


class TestSearchCommandBranches:
    def test_rejects_positional_and_leg_together(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            main,
            [
                "search",
                "JFK",
                "LAX",
                "2026-06-15",
                "--leg",
                "JFK",
                "LAX",
                "2026-06-15",
            ],
        )
        assert result.exit_code == 2
        assert "positional args and --leg cannot be used together" in result.stderr

    def test_rejects_leg_with_return(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            main,
            [
                "search",
                "--leg",
                "JFK",
                "LAX",
                "2026-06-15",
                "--return",
                "2026-06-22",
            ],
        )
        assert result.exit_code == 2
        assert "--leg cannot be combined with --return" in result.stderr

    def test_rejects_leg_with_flight_filter(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            main,
            [
                "search",
                "--leg",
                "JFK",
                "LAX",
                "2026-06-15",
                "--flight",
                "DL2300",
            ],
        )
        assert result.exit_code == 2
        assert "--leg cannot be combined with --flight" in result.stderr

    def test_rejects_leg_with_time_windows(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            main,
            [
                "search",
                "--leg",
                "JFK",
                "LAX",
                "2026-06-15",
                "--depart-after",
                "8",
            ],
        )
        assert result.exit_code == 2
        assert "time-window filters are not supported with --leg searches" in result.stderr

    def test_requires_complete_positional_triplet(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, ["search", "JFK", "LAX"])
        assert result.exit_code == 2
        assert "ORIGIN DESTINATION DATE are all required" in result.stderr


class TestPriceCommandBranches:
    def test_selector_is_mutually_exclusive_with_shorthand(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            main,
            [
                "price",
                "JFK",
                "LAX",
                "--depart",
                "2026-06-15",
                "DL2300",
                "--selector",
                "selector-1",
            ],
        )
        assert result.exit_code == 2
        assert "mutually exclusive" in result.stderr

    def test_selector_rejects_pricing_overrides(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            main,
            [
                "price",
                "--selector",
                "selector-1",
                "--cabin",
                "business",
            ],
        )
        assert result.exit_code == 2
        assert "self-contained and cannot be combined with pricing" in result.stderr.replace("\n", " ")

    def test_leg_pricing_rejects_max_stops(self):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(
            main,
            [
                "price",
                "--leg",
                "JFK",
                "LAX",
                "2026-06-15",
                "DL2300",
                "--max-stops",
                "1",
            ],
        )
        assert result.exit_code == 2
        assert "--max-stops is not supported with explicit --leg pricing" in result.stderr

    @patch("swoop.price_selector")
    def test_selector_not_found_message_is_specific(self, mock_price_selector):
        mock_price_selector.return_value = None
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, ["price", "--selector", "selector-1", "-q"])
        assert result.exit_code == 1
        assert "Selected itinerary no longer exists" in result.stderr

    @patch("swoop.price_selector")
    def test_selector_mode_renders_table_for_found_result(self, mock_price_selector):
        mock_price_selector.return_value = PriceResult(price=342, fare_brand="Main Cabin", rpc_calls=1)
        runner = CliRunner()
        result = runner.invoke(main, ["price", "--selector", "selector-1", "-q"])
        assert result.exit_code == 0
        assert "$342" in result.output
