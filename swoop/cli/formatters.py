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
        airport = lay.departure_airport_code or lay.arrival_airport_code
        text.append(f"\n{dur} {airport}", style="dim")
    return text


def _airline_names(itin) -> str:
    """Comma-separated airline names, truncated."""
    names = itin.airline_names or []
    if not names and itin.flights:
        names = list(dict.fromkeys(f.airline_name for f in itin.flights if f.airline_name))
    return ", ".join(names) if names else itin.airline_code or ""


def _flight_summary(itin) -> str:
    """Compact flight number summary for an itinerary.

    - Nonstop: "DL 2300"
    - 2 segments same carrier: "UA 1234 / 5678"
    - 2 segments diff carrier: "UA 1234 / AA 200"
    - 3+ segments: "UA 1234 +2"
    - No flights: ""
    """
    flights = itin.flights or []
    if not flights:
        return ""
    first = flights[0]
    first_str = f"{first.airline} {first.flight_number}" if first.airline and first.flight_number else str(first.flight_number or "")
    if len(flights) == 1:
        return first_str
    if len(flights) == 2:
        second = flights[1]
        if first.airline and second.airline and first.airline == second.airline:
            return f"{first.airline} {first.flight_number} / {second.flight_number}"
        second_str = f"{second.airline} {second.flight_number}" if second.airline and second.flight_number else str(second.flight_number or "")
        return f"{first_str} / {second_str}"
    return f"{first_str} +{len(flights) - 1}"


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
    table.add_column("Flights", min_width=10)
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
            _flight_summary(itin),
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

    if return_date:
        console.print(
            " [dim]Prices shown are roundtrip totals. Each row is an outbound selection.[/dim]"
        )

    console.print(
        " [dim]Tip: re-run with --price 1 to see fares for result #1[/dim]"
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
            "departure_airport_code": f.departure_airport_code,
            "arrival_airport_code": f.arrival_airport_code,
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
            "airport": lay.departure_airport_code or lay.arrival_airport_code,
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
        "flight_summary": _flight_summary(itin),
        "price_usd": itin.price,
        "airlines": _airline_names(itin) if isinstance(_airline_names(itin), str) else str(_airline_names(itin)),
        "departure_airport_code": itin.departure_airport_code,
        "arrival_airport_code": itin.arrival_airport_code,
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
        "index", "flight_summary", "airlines", "departure_airport_code", "arrival_airport_code",
        "departure_time", "arrival_time", "duration_minutes", "stops", "price_usd",
    ])
    for i, itin in enumerate(all_itins, 1):
        stops = itin.stop_count if itin.stop_count is not None else len(itin.layovers)
        writer.writerow([
            i,
            _flight_summary(itin),
            _airline_names(itin),
            itin.departure_airport_code,
            itin.arrival_airport_code,
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
        route = f"{itin.departure_airport_code}->{itin.arrival_airport_code}"
        fs = _flight_summary(itin)
        print(f"{i:<3} {fs:<14} {price:<8} {dur:<7} {stop_str:<8} {airline:<12} {route}  {dep}-{arr}")


# ---------------------------------------------------------------------------
# Price check formatters
# ---------------------------------------------------------------------------


def format_price_table(
    result,
    *,
    flight_number: str,
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
    no_color: bool = False,
) -> None:
    """Render a price check result as a Rich table to stdout."""
    console = _stdout_console(no_color=no_color)
    console.print()

    trip_type = "Roundtrip" if return_date else "One-way"
    trip = f"{origin} -> {destination}"
    if return_date:
        trip += f" (return {format_date_display(return_date)})"
    date_display = format_date_display(date)

    console.print(f" [bold]{flight_number} · {trip} · {date_display} · {trip_type}[/bold]")
    console.print()
    console.print(f" [bold green]Price: ${result.price:,}[/bold green]")

    if result.fare_brand:
        console.print(f" [dim]Fare: {result.fare_brand}[/dim]")
    if result.is_basic_economy:
        console.print(" [yellow]Basic Economy[/yellow]")

    console.print(f" [dim]RPC calls: {result.rpc_calls}[/dim]")

    if result.booking_options:
        console.print()
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Fare", min_width=16)
        table.add_column("Price", justify="right", width=8)
        table.add_column("Basic", width=6)

        for i, opt in enumerate(result.booking_options, 1):
            price = f"${opt.price:,}" if opt.price else "—"
            table.add_row(
                str(i),
                opt.brand_label or opt.brand_code or "—",
                price,
                "Yes" if opt.is_basic else "No",
            )
        console.print(table)

    console.print()


def format_price_json(
    result,
    *,
    flight_number: str,
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
) -> None:
    """Render a price check result as JSON to stdout."""
    output = {
        "query": {
            "flight_number": flight_number,
            "origin": origin,
            "destination": destination,
            "date": date,
            "return_date": return_date,
        },
        "price_usd": result.price,
        "fare_brand": result.fare_brand,
        "is_basic_economy": result.is_basic_economy,
        "rpc_calls": result.rpc_calls,
        "booking_options": [
            {
                "brand_label": opt.brand_label,
                "brand_code": opt.brand_code,
                "price_usd": opt.price,
                "is_basic": opt.is_basic,
            }
            for opt in result.booking_options
        ] if result.booking_options else [],
    }
    if result.itinerary:
        output["itinerary"] = _itin_to_dict(result.itinerary, 1)
    print(json.dumps(output, indent=2))


def format_price_brief(
    result,
    *,
    return_date: Optional[str] = None,
) -> None:
    """Render a price check result in compact format to stdout."""
    trip_type = "roundtrip" if return_date else "one-way"
    brand = f" ({result.fare_brand})" if result.fare_brand else ""
    print(f"${result.price:,}{brand} {trip_type} [{result.rpc_calls} RPCs]")
