"""Output formatters for the CLI — table, JSON, CSV, brief."""

import csv
import io
import json
import sys
from dataclasses import asdict
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .utils import format_date_display, format_duration, format_route, format_time


def _stderr_console(**kwargs) -> Console:
    """Console that writes to stderr (for non-data output)."""
    return Console(stderr=True, **kwargs)


def _stdout_console(**kwargs) -> Console:
    """Console that writes to stdout."""
    return Console(**kwargs)


# ---------------------------------------------------------------------------
# Search formatters
# ---------------------------------------------------------------------------


def _stops_text(itin) -> Text:
    """Colored stop count with layover details."""
    n = itin.stop_count if itin.stop_count is not None else len(itin.layovers)
    if n == 0:
        return Text("Nonstop", style="green")
    label = "1 stop" if n == 1 else f"{n} stops"
    style = "yellow" if n == 1 else "red"
    text = Text(label, style=style)
    for lay in itin.layovers:
        h, m = divmod(lay.minutes, 60)
        dur = f"{h}h" if not m else f"{h}h{m:02d}m" if h else f"{m}m"
        airport = lay.departure_airport or lay.arrival_airport
        text.append(f"\n{dur} {airport}", style="dim")
    return text


def _airline_names(itin) -> str:
    """Comma-separated airline names, truncated."""
    names = itin.airline_names or []
    if not names and itin.flights:
        names = list(dict.fromkeys(f.airline_name for f in itin.flights if f.airline_name))
    return ", ".join(names) if names else itin.airline_code or ""


def _price_text(price: Optional[int], cheapest: Optional[int]) -> Text:
    """Formatted price, cheapest highlighted green."""
    if price is None:
        return Text("—")
    text = Text(f"${price:,}", style="bold")
    if cheapest is not None and price == cheapest:
        text.stylize("green")
    return text


def format_search_table(
    result,
    *,
    origin: str,
    destination: str,
    date: str,
    cabin: str = "economy",
    adults: int = 1,
    return_date: Optional[str] = None,
    limit: Optional[int] = None,
    no_color: bool = False,
) -> None:
    """Render search results as a Rich table to stdout."""
    console = _stdout_console(no_color=no_color)
    all_itins = [*result.best, *result.other]

    if not all_itins:
        console.print("[yellow]No flights found.[/yellow]")
        return

    if limit:
        display_itins = all_itins[:limit]
    else:
        display_itins = all_itins

    # Header
    trip = f"{origin} -> {destination}"
    if return_date:
        trip += f" (roundtrip, return {format_date_display(return_date)})"
    date_display = format_date_display(date)
    cabin_display = cabin.replace("-", " ").title()
    pax = f"{adults} adult" if adults == 1 else f"{adults} adults"

    console.print()
    console.print(
        f" [bold]Flights: {trip} · {date_display} · {cabin_display} · {pax}[/bold]"
    )
    console.print()

    # Find cheapest for highlighting
    prices = [it.price for it in display_itins if it.price is not None]
    cheapest = min(prices) if prices else None

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Airlines", min_width=10)
    table.add_column("Route", min_width=12)
    table.add_column("Depart", justify="right", width=7)
    table.add_column("Arrive", justify="right", width=7)
    table.add_column("Duration", justify="right", width=8)
    table.add_column("Stops", min_width=8)
    table.add_column("Price", justify="right", width=8)

    for i, itin in enumerate(display_itins, 1):
        dep_h, dep_m = itin.departure_time
        arr_h, arr_m = itin.arrival_time
        airline = _airline_names(itin)
        if itin.is_budget_carrier:
            airline = Text(airline)
            airline.append(" *", style="dim")

        table.add_row(
            str(i),
            airline if isinstance(airline, Text) else str(airline),
            format_route(itin),
            format_time(dep_h, dep_m),
            format_time(arr_h, arr_m),
            format_duration(itin.travel_time),
            _stops_text(itin),
            _price_text(itin.price, cheapest),
        )

    console.print(table)
    console.print()

    # Footer
    total = len(all_itins)
    shown = len(display_itins)
    if result.price_range and result.price_range.low is not None:
        pr = result.price_range
        range_str = f"${pr.low:,}-${pr.high:,}" if pr.high else f"from ${pr.low:,}"
        console.print(f" [dim]Price range: {range_str} · {shown} of {total} results shown[/dim]")
    else:
        if prices:
            console.print(f" [dim]Price range: ${min(prices):,}-${max(prices):,} · {shown} of {total} results shown[/dim]")
        else:
            console.print(f" [dim]{shown} of {total} results shown[/dim]")

    console.print(
        f" [dim]Tip: swoop book 1 {origin} {destination} {date} "
        f"to see fare options for result #1[/dim]"
    )
    console.print()


def _itin_to_dict(itin, index: int) -> dict:
    """Convert an itinerary to a JSON-serializable dict."""
    flights = []
    for f in itin.flights:
        flight_dict = {
            "airline": f.airline,
            "airline_name": f.airline_name,
            "flight_number": f.flight_number,
            "aircraft": f.aircraft,
            "departure_airport": f.departure_airport,
            "arrival_airport": f.arrival_airport,
            "departure_time": f"{f.departure_time[0]:02d}:{f.departure_time[1]:02d}",
            "arrival_time": f"{f.arrival_time[0]:02d}:{f.arrival_time[1]:02d}",
            "departure_date": f"{f.departure_date[0]:04d}-{f.departure_date[1]:02d}-{f.departure_date[2]:02d}" if f.departure_date != (0, 0, 0) else None,
            "arrival_date": f"{f.arrival_date[0]:04d}-{f.arrival_date[1]:02d}-{f.arrival_date[2]:02d}" if f.arrival_date != (0, 0, 0) else None,
            "duration_minutes": f.travel_time,
            "legroom": f.legroom or None,
            "co2_grams": f.co2_grams,
        }
        flights.append(flight_dict)

    layovers = []
    for lay in itin.layovers:
        layovers.append({
            "minutes": lay.minutes,
            "airport": lay.departure_airport or lay.arrival_airport,
            "is_overnight": lay.is_overnight,
        })

    emissions = None
    if itin.carbon_emissions:
        ce = itin.carbon_emissions
        emissions = {
            "this_flight_grams": ce.this_flight_grams,
            "typical_grams": ce.typical_for_route_grams,
            "difference_percent": ce.difference_percent,
        }

    return {
        "index": index,
        "price_usd": itin.price,
        "airlines": _airline_names(itin) if isinstance(_airline_names(itin), str) else str(_airline_names(itin)),
        "departure_airport": itin.departure_airport,
        "arrival_airport": itin.arrival_airport,
        "departure_time": f"{itin.departure_time[0]:02d}:{itin.departure_time[1]:02d}",
        "arrival_time": f"{itin.arrival_time[0]:02d}:{itin.arrival_time[1]:02d}",
        "duration_minutes": itin.travel_time,
        "stops": itin.stop_count if itin.stop_count is not None else len(itin.layovers),
        "is_budget_carrier": itin.is_budget_carrier,
        "flights": flights,
        "layovers": layovers,
        "carbon_emissions": emissions,
        "booking_token": itin.booking_token or None,
    }


def format_search_json(
    result,
    *,
    origin: str,
    destination: str,
    date: str,
    cabin: str = "economy",
    adults: int = 1,
    return_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> None:
    """Render search results as JSON to stdout."""
    all_itins = [*result.best, *result.other]
    if limit:
        all_itins = all_itins[:limit]

    price_range = None
    if result.price_range and result.price_range.low is not None:
        price_range = {
            "low": result.price_range.low,
            "high": result.price_range.high,
        }

    output = {
        "query": {
            "origin": origin,
            "destination": destination,
            "date": date,
            "return_date": return_date,
            "cabin": cabin,
            "adults": adults,
        },
        "price_range": price_range,
        "total_results": len(result.best) + len(result.other),
        "results": [_itin_to_dict(it, i + 1) for i, it in enumerate(all_itins)],
    }
    print(json.dumps(output, indent=2))


def format_search_csv(
    result,
    *,
    limit: Optional[int] = None,
) -> None:
    """Render search results as CSV to stdout."""
    all_itins = [*result.best, *result.other]
    if limit:
        all_itins = all_itins[:limit]

    writer = csv.writer(sys.stdout)
    writer.writerow([
        "index", "airlines", "departure_airport", "arrival_airport",
        "departure_time", "arrival_time", "duration_minutes", "stops", "price_usd",
    ])
    for i, itin in enumerate(all_itins, 1):
        stops = itin.stop_count if itin.stop_count is not None else len(itin.layovers)
        writer.writerow([
            i,
            _airline_names(itin),
            itin.departure_airport,
            itin.arrival_airport,
            f"{itin.departure_time[0]:02d}:{itin.departure_time[1]:02d}",
            f"{itin.arrival_time[0]:02d}:{itin.arrival_time[1]:02d}",
            itin.travel_time,
            stops,
            itin.price if itin.price is not None else "",
        ])


def format_search_brief(
    result,
    *,
    limit: Optional[int] = None,
) -> None:
    """Render search results in compact single-line format to stdout."""
    all_itins = [*result.best, *result.other]
    if limit:
        all_itins = all_itins[:limit]

    for i, itin in enumerate(all_itins, 1):
        price = f"${itin.price:,}" if itin.price is not None else "—"
        dur = format_duration(itin.travel_time)
        stops = itin.stop_count if itin.stop_count is not None else len(itin.layovers)
        stop_str = "Nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
        airline = _airline_names(itin)
        dep = format_time(itin.departure_time[0], itin.departure_time[1])
        arr = format_time(itin.arrival_time[0], itin.arrival_time[1])
        route = f"{itin.departure_airport}->{itin.arrival_airport}"
        print(f"{i:<3} {price:<8} {dur:<7} {stop_str:<8} {airline:<12} {route}  {dep}-{arr}")


# ---------------------------------------------------------------------------
# Flight detail formatter
# ---------------------------------------------------------------------------


def format_flight_detail(
    itin,
    *,
    no_color: bool = False,
) -> None:
    """Render a single flight detail card to stdout."""
    console = _stdout_console(no_color=no_color)
    console.print()

    airline = _airline_names(itin)
    route = format_route(itin)
    console.print(f" [bold]{airline} · {route}[/bold]")
    console.print()

    for f in itin.flights:
        dep = format_time(f.departure_time[0], f.departure_time[1])
        arr = format_time(f.arrival_time[0], f.arrival_time[1])
        dur = format_duration(f.travel_time)
        flight_id = f"{f.airline} {f.flight_number}" if f.airline and f.flight_number else ""

        console.print(f"   [bold]{flight_id}[/bold]  {f.departure_airport} -> {f.arrival_airport}")
        console.print(f"   Depart: {dep}   Arrive: {arr}   Duration: {dur}")
        if f.aircraft:
            console.print(f"   Aircraft: {f.aircraft}")
        if f.legroom:
            console.print(f"   Legroom: {f.legroom}")
        if f.co2_grams:
            console.print(f"   CO2: {f.co2_grams:,}g")
        console.print()

    for lay in itin.layovers:
        h, m = divmod(lay.minutes, 60)
        dur = f"{h}h {m:02d}m" if m else f"{h}h"
        airport = lay.departure_airport or lay.arrival_airport
        console.print(f"   [dim]Layover: {dur} at {airport}[/dim]")
        console.print()

    if itin.price is not None:
        console.print(f" [bold green]Price: ${itin.price:,}[/bold green]")

    if itin.carbon_emissions and itin.carbon_emissions.this_flight_grams:
        ce = itin.carbon_emissions
        kg = ce.this_flight_grams / 1000
        console.print(f" [dim]Carbon: {kg:.0f} kg CO2[/dim]")

    console.print()


def format_flight_json(itin) -> None:
    """Render a single flight as JSON to stdout."""
    output = _itin_to_dict(itin, 1)
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Booking formatters
# ---------------------------------------------------------------------------


def format_booking_table(
    options: list,
    *,
    itin,
    no_color: bool = False,
) -> None:
    """Render fare options as a Rich table to stdout."""
    console = _stdout_console(no_color=no_color)

    airline = _airline_names(itin)
    route = format_route(itin)

    console.print()
    console.print(f" [bold]Fare options: {airline} {route}[/bold]")
    console.print()

    if not options:
        console.print(" [yellow]No fare options available.[/yellow]")
        console.print()
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Fare", min_width=16)
    table.add_column("Cabin", min_width=10)
    table.add_column("Price", justify="right", width=8)
    table.add_column("Rebookable", width=10)

    for i, opt in enumerate(options, 1):
        price = f"${opt.price:,}" if opt.price else "—"
        cabin = opt.fare_family or ("basic" if opt.is_basic else "standard")
        rebook = "No" if opt.is_basic else "Yes"
        if opt.rebookability_signal:
            rebook = opt.rebookability_signal

        table.add_row(
            str(i),
            opt.brand_label or opt.brand_code or "—",
            cabin,
            price,
            rebook,
        )

    console.print(table)
    console.print()


def format_booking_json(options: list, *, itin) -> None:
    """Render fare options as JSON to stdout."""
    output = {
        "itinerary": _itin_to_dict(itin, 1),
        "options": [
            {
                "index": i + 1,
                "brand_label": opt.brand_label,
                "brand_code": opt.brand_code,
                "fare_family": opt.fare_family,
                "price_usd": opt.price,
                "is_basic": opt.is_basic,
                "rebookability": opt.rebookability_signal or ("no" if opt.is_basic else "yes"),
            }
            for i, opt in enumerate(options)
        ],
    }
    print(json.dumps(output, indent=2))
