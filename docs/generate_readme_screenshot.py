"""Generate the README search screenshot SVG.

Uses a deterministic sample search result so the asset doesn't depend on
live Google Flights output.
"""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from swoop.cli import formatters
from swoop.decoder import Flight, Itinerary, Layover, PriceRange
from swoop.models import SearchResult, TripLeg, TripOption

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "docs" / "screenshot.svg"
TITLE = "swoop search JFK LAX 2026-06-15"


def _flight(
    airline: str,
    airline_name: str,
    flight_number: str,
    origin: str,
    destination: str,
    departure_time: tuple[int, int],
    arrival_time: tuple[int, int],
    duration_minutes: int,
) -> Flight:
    return Flight(
        airline=airline,
        airline_name=airline_name,
        flight_number=flight_number,
        departure_airport_code=origin,
        arrival_airport_code=destination,
        departure_time=departure_time,
        arrival_time=arrival_time,
        travel_time=duration_minutes,
    )


def _sample_result() -> SearchResult:
    itineraries = [
        Itinerary(
            airline_code="DL",
            airline_names=["Delta"],
            flights=[
                _flight("DL", "Delta", "2300", "JFK", "LAX", (8, 30), (11, 45), 315),
            ],
            travel_time=315,
            departure_airport_code="JFK",
            arrival_airport_code="LAX",
            departure_time=(8, 30),
            arrival_time=(11, 45),
            direct_price=247,
            stop_count=0,
        ),
        Itinerary(
            airline_code="B6",
            airline_names=["JetBlue"],
            flights=[
                _flight("B6", "JetBlue", "524", "JFK", "LAX", (9, 0), (12, 30), 330),
            ],
            travel_time=330,
            departure_airport_code="JFK",
            arrival_airport_code="LAX",
            departure_time=(9, 0),
            arrival_time=(12, 30),
            direct_price=219,
            stop_count=0,
        ),
        Itinerary(
            airline_code="UA",
            airline_names=["United"],
            flights=[
                _flight("UA", "United", "12", "JFK", "ORD", (10, 15), (11, 55), 160),
                _flight("UA", "United", "34", "ORD", "LAX", (13, 30), (15, 20), 230),
            ],
            layovers=[
                Layover(minutes=95, departure_airport_code="ORD"),
            ],
            travel_time=485,
            departure_airport_code="JFK",
            arrival_airport_code="LAX",
            departure_time=(10, 15),
            arrival_time=(15, 20),
            direct_price=283,
            stop_count=1,
        ),
        Itinerary(
            airline_code="NK",
            airline_names=["Spirit"],
            flights=[
                _flight("NK", "Spirit", "80", "JFK", "ATL", (14, 5), (16, 30), 145),
                _flight("NK", "Spirit", "91", "ATL", "DFW", (17, 15), (18, 45), 150),
                _flight("NK", "Spirit", "12", "DFW", "LAX", (19, 40), (21, 5), 205),
            ],
            layovers=[
                Layover(minutes=45, departure_airport_code="ATL"),
                Layover(minutes=55, departure_airport_code="DFW"),
            ],
            travel_time=660,
            departure_airport_code="JFK",
            arrival_airport_code="LAX",
            departure_time=(14, 5),
            arrival_time=(21, 5),
            direct_price=239,
            stop_count=2,
            is_budget_carrier=True,
        ),
    ]
    options = [
        TripOption(
            selector=f"swoop:sel:1:sample{i}",
            price=itin.direct_price,
            legs=[TripLeg(origin="JFK", destination="LAX", date="2026-06-15", itinerary=itin)],
        )
        for i, itin in enumerate(itineraries)
    ]
    return SearchResult(
        results=options,
        price_range=PriceRange(low=219, high=283),
    )


def generate_svg() -> str:
    console = Console(
        record=True,
        width=118,
        color_system="truecolor",
        file=io.StringIO(),
    )
    result = _sample_result()
    original_stdout_console = formatters._stdout_console
    formatters._stdout_console = lambda **kwargs: console
    try:
        formatters.format_search_table(
            result,
            origin="JFK",
            destination="LAX",
            date="2026-06-15",
        )
    finally:
        formatters._stdout_console = original_stdout_console
    return console.export_svg(title=TITLE)


def main() -> None:
    OUTPUT_PATH.write_text(generate_svg(), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
