"""Output formatters for the CLI — table, JSON, CSV, brief."""

import csv
import json
import sys
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .utils import format_date_display, format_duration, format_time


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


def _format_clock(value) -> Optional[str]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    hour, minute = value[0], value[1]
    if hour is None or minute is None:
        return None
    return f"{int(hour):02d}:{int(minute):02d}"


def _format_date_tuple(value) -> Optional[str]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    year, month, day = value[0], value[1], value[2]
    if not year or not month or not day:
        return None
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _trip_header(
    *,
    origin: Optional[str],
    destination: Optional[str],
    date: Optional[str],
    return_date: Optional[str],
    legs,
) -> str:
    if legs:
        parts = [f"{leg_origin} -> {leg_destination} ({format_date_display(leg_date)})" for leg_origin, leg_destination, leg_date in legs]
        return " / ".join(parts)
    trip = f"{origin} -> {destination}"
    if return_date:
        trip += f" (return {format_date_display(return_date)})"
    if date:
        trip += f" · {format_date_display(date)}"
    return trip


def _trip_leg_line(leg) -> str:
    itinerary = leg.itinerary
    if itinerary is None:
        return f"{leg.origin}->{leg.destination} ({leg.date})"
    dep = _format_clock(itinerary.departure_time)
    arr = _format_clock(itinerary.arrival_time)
    duration = format_duration(itinerary.travel_time)
    stops = itinerary.stop_count if itinerary.stop_count is not None else len(itinerary.layovers)
    stop_str = "Nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
    route = "->".join(
        [flight.departure_airport_code for flight in itinerary.flights] +
        ([itinerary.flights[-1].arrival_airport_code] if itinerary.flights else [])
    )
    return (
        f"{_flight_summary(itinerary)}  {route or f'{leg.origin}->{leg.destination}'}  "
        f"{dep or '?'}-{arr or '?'}  {duration}  {stop_str}"
    )


def _trip_lines(option) -> list[str]:
    return [f"Leg {index + 1}: {_trip_leg_line(leg)}" for index, leg in enumerate(option.legs)]


def _trip_summary(option) -> str:
    return " | ".join(
        _flight_summary(leg.itinerary) if leg.itinerary is not None else f"{leg.origin}->{leg.destination}"
        for leg in option.legs
    )


def _render_search_price_hint(console, price_commands: Optional[list[str]]) -> None:
    """Render the human pricing guidance for search output."""
    console.print(" [dim]Prices shown are shopping totals.[/dim]")
    if price_commands:
        console.print(" [dim]Bookable fare commands for shown rows:[/dim]")
        for index, command in enumerate(price_commands, 1):
            console.print(f" [bold cyan]{index}. {command}[/bold cyan]")
    else:
        console.print(" [dim]Use --show-price-commands for copy/paste `swoop price --selector ...` commands, or -o json to access selectors directly.[/dim]")


def format_search_table(
    result,
    *,
    origin: str,
    destination: str,
    date: str,
    cabin: str = "economy",
    adults: int = 1,
    return_date: Optional[str] = None,
    legs=None,
    limit: Optional[int] = None,
    price_commands: Optional[list[str]] = None,
    no_color: bool = False,
) -> None:
    """Render search results as a Rich table to stdout."""
    console = _stdout_console(no_color=no_color)
    all_options = list(result.results)

    if not all_options:
        console.print("[yellow]No flights found.[/yellow]")
        return

    if limit:
        display_options = all_options[:limit]
    else:
        display_options = all_options

    cabin_display = cabin.replace("-", " ").title()
    pax = f"{adults} adult" if adults == 1 else f"{adults} adults"

    console.print()
    console.print(
        f" [bold]Flights: {_trip_header(origin=origin, destination=destination, date=date, return_date=return_date, legs=legs)} · {cabin_display} · {pax}[/bold]"
    )
    console.print()

    prices = [option.price for option in display_options if option.price is not None]
    cheapest = min(prices) if prices else None

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Trip", min_width=36)
    table.add_column("Price", justify="right", width=8)

    for i, option in enumerate(display_options, 1):
        table.add_row(
            str(i),
            "\n".join(_trip_lines(option)),
            _price_text(option.price, cheapest),
        )

    console.print(table)
    console.print()

    total = len(all_options)
    shown = len(display_options)
    if result.price_range and result.price_range.low is not None:
        pr = result.price_range
        range_str = f"${pr.low:,}-${pr.high:,}" if pr.high else f"from ${pr.low:,}"
        console.print(f" [dim]Price range: {range_str} · {shown} of {total} results shown[/dim]")
    else:
        if prices:
            console.print(f" [dim]Price range: ${min(prices):,}-${max(prices):,} · {shown} of {total} results shown[/dim]")
        else:
            console.print(f" [dim]{shown} of {total} results shown[/dim]")

    if not result.is_complete:
        console.print(" [dim]Results are truncated to the best complete trips within the CLI expansion budget.[/dim]")

    _render_search_price_hint(console, price_commands)
    console.print()


def _itin_to_dict(itin) -> dict:
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
            "departure_time": _format_clock(f.departure_time),
            "arrival_time": _format_clock(f.arrival_time),
            "departure_date": _format_date_tuple(f.departure_date),
            "arrival_date": _format_date_tuple(f.arrival_date),
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
        "flight_summary": _flight_summary(itin),
        "price_usd": itin.price,
        "airlines": _airline_names(itin) if isinstance(_airline_names(itin), str) else str(_airline_names(itin)),
        "departure_airport_code": itin.departure_airport_code,
        "arrival_airport_code": itin.arrival_airport_code,
        "departure_time": _format_clock(itin.departure_time),
        "arrival_time": _format_clock(itin.arrival_time),
        "duration_minutes": itin.travel_time,
        "stops": itin.stop_count if itin.stop_count is not None else len(itin.layovers),
        "is_budget_carrier": itin.is_budget_carrier,
        "flights": flights,
        "layovers": layovers,
        "carbon_emissions": emissions,
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
    legs=None,
    limit: Optional[int] = None,
    price_commands: Optional[list[str]] = None,
) -> None:
    """Render search results as JSON to stdout."""
    all_options = list(result.results)
    if limit:
        all_options = all_options[:limit]

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
            "legs": [
                {"origin": leg_origin, "destination": leg_destination, "date": leg_date}
                for leg_origin, leg_destination, leg_date in (legs or [])
            ],
            "cabin": cabin,
            "adults": adults,
        },
        "price_source": "shopping",
        "price_range": price_range,
        "total_results": len(result.results),
        "is_complete": result.is_complete,
        "results": [
            {
                "index": index + 1,
                "selector": option.selector,
                "price_usd": option.price,
                "legs": [
                    {
                        "origin": leg.origin,
                        "destination": leg.destination,
                        "date": leg.date,
                        "itinerary": _itin_to_dict(leg.itinerary) if leg.itinerary else None,
                    }
                    for leg in option.legs
                ],
            }
            for index, option in enumerate(all_options)
        ],
    }
    print(json.dumps(output, indent=2))


def format_search_csv(
    result,
    *,
    limit: Optional[int] = None,
) -> None:
    """Render search results as CSV to stdout."""
    all_options = list(result.results)
    if limit:
        all_options = all_options[:limit]

    writer = csv.writer(sys.stdout)
    writer.writerow([
        "index", "selector", "price_usd", "leg_count", "summary",
    ])
    for i, option in enumerate(all_options, 1):
        writer.writerow([
            i,
            option.selector,
            option.price if option.price is not None else "",
            len(option.legs),
            _trip_summary(option),
        ])


def format_search_brief(
    result,
    *,
    limit: Optional[int] = None,
    price_commands: Optional[list[str]] = None,
) -> None:
    """Render search results in compact single-line format to stdout."""
    all_options = list(result.results)
    if limit:
        all_options = all_options[:limit]

    for i, option in enumerate(all_options, 1):
        price = f"${option.price:,}" if option.price is not None else "—"
        print(f"{i:<3} {price:<8} {_trip_summary(option)}")

    if all_options:
        console = _stdout_console()
        _render_search_price_hint(console, price_commands)


# ---------------------------------------------------------------------------
# Price check formatters
# ---------------------------------------------------------------------------


def _render_resolved_legs(console, resolved_legs) -> None:
    """Render resolved flight details for each leg."""
    leg_labels = ["Outbound", "Return"]
    for idx, leg in enumerate(resolved_legs):
        label = leg_labels[idx] if idx < len(leg_labels) else f"Leg {idx + 1}"
        console.print(f"  [bold]{label}[/bold] · {leg.selection}")

        itin = leg.itinerary
        if itin and itin.flights:
            for fi, flight in enumerate(itin.flights):
                fid = f"{flight.airline} {flight.flight_number}" if flight.airline else str(flight.flight_number or "")
                dep = format_time(flight.departure_time[0], flight.departure_time[1])
                arr = format_time(flight.arrival_time[0], flight.arrival_time[1])
                dur = format_duration(flight.travel_time) if flight.travel_time else ""
                route = f"{flight.departure_airport_code} -> {flight.arrival_airport_code}"
                console.print(f"  {fid}  {route}")
                console.print(f"  Depart: {dep}   Arrive: {arr}   Duration: {dur}")
                details = []
                if flight.aircraft:
                    details.append(f"Aircraft: {flight.aircraft}")
                if flight.legroom:
                    details.append(f"Legroom: {flight.legroom}")
                if details:
                    console.print(f"  [dim]{' · '.join(details)}[/dim]")

                # Show layover after this segment (if not last segment)
                if fi < len(itin.layovers):
                    lay = itin.layovers[fi]
                    h, m = divmod(lay.minutes, 60)
                    lay_dur = f"{h}h {m:02d}m" if h and m else (f"{h}h" if h else f"{m}m")
                    airport = lay.departure_airport_code or lay.arrival_airport_code or ""
                    console.print(f"  [dim]  Layover: {lay_dur} {airport}[/dim]")
        else:
            console.print(f"  {leg.flight_summary}  {leg.origin} -> {leg.destination}")
        console.print()


def _query_trip_title(query_legs) -> str:
    if not query_legs:
        return "Trip"
    return " / ".join(
        f"{leg['origin']} -> {leg['destination']} ({format_date_display(leg['date'])})"
        for leg in query_legs
    )


def format_price_table(
    result,
    *,
    query_legs=None,
    no_color: bool = False,
) -> None:
    """Render a price check result as a Rich table to stdout."""
    console = _stdout_console(no_color=no_color)
    console.print()

    trip_type = f"{len(query_legs or result.resolved_legs or [])}-leg" if (query_legs or result.resolved_legs) else "Trip"
    console.print(f" [bold]{_query_trip_title(query_legs or [])} · {trip_type}[/bold]")
    console.print()

    # Resolved flight details
    if result.resolved_legs:
        _render_resolved_legs(console, result.resolved_legs)

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
    query_legs=None,
) -> None:
    """Render a price check result as JSON to stdout."""
    output = {
        "query": {
            "legs": list(query_legs or []),
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
        output["itinerary"] = _itin_to_dict(result.itinerary)
    if result.resolved_legs:
        output["resolved_legs"] = [
            {
                "flight_summary": leg.flight_summary,
                "origin": leg.origin,
                "destination": leg.destination,
                "date": leg.date,
                "selection": leg.selection,
                "itinerary": _itin_to_dict(leg.itinerary) if leg.itinerary else None,
            }
            for leg in result.resolved_legs
        ]
    print(json.dumps(output, indent=2))


def format_price_brief(
    result,
    *,
    query_legs=None,
) -> None:
    """Render a price check result in compact format to stdout."""
    trip_type = f"{len(query_legs or result.resolved_legs or [])}-leg"
    brand = f" ({result.fare_brand})" if result.fare_brand else ""
    print(f"${result.price:,}{brand} {trip_type} [{result.rpc_calls} RPCs]")
