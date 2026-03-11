"""CLI commands for swoop: search and price."""

import click
import shlex
from rich.console import Console

from .utils import (
    CABIN_CHOICES,
    DATE,
    IATA_CODE,
    SORT_MAP,
    check_past_date,
)


def _err_console(no_color: bool = False) -> Console:
    return Console(stderr=True, no_color=no_color)


def _run_search(
    origin, destination, date, *,
    return_date, cabin, passengers, sort, nonstop, max_stops,
    airline, flight_number, include_basic,
    depart_after, depart_before, arrive_after, arrive_before,
    return_depart_after, return_depart_before,
    timeout, retries,
):
    """Run swoop.search() with the given parameters. Returns the result."""
    import swoop

    stops = max_stops
    if nonstop:
        stops = 0

    sort_val = SORT_MAP.get(sort, swoop.SORT_DEPARTURE_TIME)
    airlines = list(airline) if airline else None

    return swoop.search(
        origin,
        destination,
        date,
        return_date=return_date,
        cabin=cabin,
        adults=passengers,
        sort=sort_val,
        max_stops=stops,
        airlines=airlines,
        flight_number=flight_number,
        include_basic_economy=include_basic,
        earliest_departure=depart_after,
        latest_departure=depart_before,
        earliest_arrival=arrive_after,
        latest_arrival=arrive_before,
        return_earliest_departure=return_depart_after,
        return_latest_departure=return_depart_before,
        timeout=timeout,
        retries=retries,
    )


def _run_search_legs(
    legs,
    *,
    cabin,
    passengers,
    sort,
    nonstop,
    max_stops,
    airline,
    include_basic,
    timeout,
    retries,
):
    """Run swoop.search_legs() with global CLI filters applied to each leg."""
    import swoop

    stops = max_stops
    if nonstop:
        stops = 0

    sort_val = SORT_MAP.get(sort, swoop.SORT_DEPARTURE_TIME)
    airlines = list(airline) if airline else None
    search_legs = [
        swoop.SearchLeg(
            date=leg_date,
            from_airport=leg_origin,
            to_airport=leg_destination,
            max_stops=stops,
            airlines=airlines,
        )
        for leg_origin, leg_destination, leg_date in legs
    ]
    return swoop.search_legs(
        search_legs,
        cabin=cabin,
        adults=passengers,
        sort=sort_val,
        include_basic_economy=include_basic,
        timeout=timeout,
        retries=retries,
    )


def _price_trip_selector(selector, *, timeout, retries):
    """Price an already-selected trip exactly from its opaque selector."""
    from swoop._selection import price_trip_selector

    return price_trip_selector(selector, timeout=timeout, retries=retries)


def _shell_join(parts):
    """Shell-quote a command for copy/paste output."""
    return " ".join(shlex.quote(str(part)) for part in parts)


def _build_search_price_hint_command(
    *,
    origin,
    destination,
    date,
    leg,
    return_date,
    cabin,
    passengers,
    sort,
    nonstop,
    max_stops,
    airline,
    flight_number,
    include_basic,
    depart_after,
    depart_before,
    arrive_after,
    arrive_before,
    return_depart_after,
    return_depart_before,
) -> str:
    """Build a copy/paste rerun command for exact pricing of a search row."""
    command = ["swoop", "search"]

    if leg:
        for leg_origin, leg_destination, leg_date in leg:
            command.extend(["--leg", leg_origin, leg_destination, leg_date])
    else:
        command.extend([origin, destination, date])
        if return_date is not None:
            command.extend(["-r", return_date])

    if cabin != "economy":
        command.extend(["--cabin", cabin])
    if passengers != 1:
        command.extend(["--passengers", passengers])
    if sort != "departure":
        command.extend(["--sort", sort])
    if nonstop:
        command.append("--nonstop")
    elif max_stops is not None:
        command.extend(["--max-stops", max_stops])
    for carrier in airline:
        command.extend(["--airline", carrier])
    if flight_number is not None:
        command.extend(["--flight", flight_number])
    if include_basic:
        command.append("--include-basic")
    if depart_after is not None:
        command.extend(["--depart-after", depart_after])
    if depart_before is not None:
        command.extend(["--depart-before", depart_before])
    if arrive_after is not None:
        command.extend(["--arrive-after", arrive_after])
    if arrive_before is not None:
        command.extend(["--arrive-before", arrive_before])
    if return_depart_after is not None:
        command.extend(["--return-depart-after", return_depart_after])
    if return_depart_before is not None:
        command.extend(["--return-depart-before", return_depart_before])

    command.extend(["--price", "1"])
    return _shell_join(command)


def _query_legs_from_price_result(result):
    """Build formatter query legs from a PriceResult."""
    return [
        {
            "flight_number": leg.flight_summary,
            "origin": leg.origin,
            "destination": leg.destination,
            "date": leg.date,
            "selection": leg.selection,
        }
        for leg in result.resolved_legs
    ]


# Shared search options decorator
def _search_options(f):
    """Apply common search filter options to a command."""
    options = [
        click.option("-r", "--return", "return_date", type=DATE, default=None, help="Return date (roundtrip)."),
        click.option("-c", "--cabin", type=click.Choice(CABIN_CHOICES, case_sensitive=False), default="economy", show_default=True, help="Cabin class."),
        click.option("-p", "--passengers", type=int, default=1, show_default=True, help="Number of adults."),
        click.option("-s", "--sort", type=click.Choice(list(SORT_MAP), case_sensitive=False), default="departure", show_default=True, help="Sort order."),
        click.option("-n", "--nonstop", is_flag=True, default=False, help="Nonstop flights only."),
        click.option("--max-stops", type=click.IntRange(0, 2), default=None, help="Max stops (0, 1, or 2)."),
        click.option("-a", "--airline", type=str, multiple=True, help="Filter by airline IATA code (repeatable)."),
        click.option("--flight", "flight_number", type=str, default=None, help="Filter to specific flight number."),
        click.option("--include-basic", is_flag=True, default=False, help="Include basic economy fares."),
        click.option("--depart-after", type=click.IntRange(0, 23), default=None, help="Earliest departure hour (0-23)."),
        click.option("--depart-before", type=click.IntRange(1, 24), default=None, help="Latest departure hour (1-24)."),
        click.option("--arrive-after", type=click.IntRange(0, 23), default=None, help="Earliest arrival hour (0-23)."),
        click.option("--arrive-before", type=click.IntRange(1, 24), default=None, help="Latest arrival hour (1-24)."),
        click.option("--return-depart-after", type=click.IntRange(0, 23), default=None, help="Return departure window start."),
        click.option("--return-depart-before", type=click.IntRange(1, 24), default=None, help="Return departure window end."),
        click.option("--timeout", type=int, default=90, show_default=True, help="HTTP timeout in seconds."),
        click.option("--retries", type=int, default=0, show_default=True, help="Retries on rate limit."),
    ]
    for option in reversed(options):
        f = option(f)
    return f


def _output_options(formats: list[str]):
    """Apply output format options to a command."""
    def decorator(f):
        options = [
            click.option("-o", "--output", "output_format", type=click.Choice(formats, case_sensitive=False), default=formats[0], show_default=True, help="Output format."),
            click.option("--no-color", is_flag=True, default=False, help="Disable color output."),
            click.option("-q", "--quiet", is_flag=True, default=False, help="Suppress spinners/headers (for piping)."),
        ]
        for option in reversed(options):
            f = option(f)
        return f
    return decorator


@click.command("search")
@click.argument("origin", type=IATA_CODE, required=False, default=None)
@click.argument("destination", type=IATA_CODE, required=False, default=None)
@click.argument("date", type=DATE, required=False, default=None)
@_search_options
@click.option("--leg", multiple=True, type=(IATA_CODE, IATA_CODE, DATE),
              help="Explicit leg: ORIGIN DEST DATE (repeatable).")
@click.option("-l", "--limit", type=int, default=None, help="Max results to display.")
@click.option("--price", "price_index", type=int, default=None,
              help="Show price + fares for search result #N.")
@click.option("--price-selector", type=str, default=None,
              help="Show price + fares for an exact selector from search JSON.")
@_output_options(["table", "json", "csv", "brief"])
@click.pass_context
def search_cmd(
    ctx, origin, destination, date,
    leg,
    return_date, cabin, passengers, sort, nonstop, max_stops,
    airline, flight_number, include_basic,
    depart_after, depart_before, arrive_after, arrive_before,
    return_depart_after, return_depart_before,
    timeout, retries, limit, price_index, price_selector,
    output_format, no_color, quiet,
):
    """Search for flights.

    \b
    Examples:
      swoop search JFK LAX 2026-06-15
      swoop search JFK LAX 2026-06-15 --nonstop --sort cheapest
      swoop search JFK LAX 2026-06-15 -r 2026-06-22 --cabin business
      swoop search JFK LAX 2026-06-15 --price 1
      swoop search --leg JFK LAX 2026-06-15 --leg LAX SFO 2026-06-18
      swoop search JFK LAX 2026-06-15 -o json -q | jq '.results[0]'
    """
    from swoop.exceptions import SwoopHTTPError, SwoopParseError, SwoopRateLimitError

    from .formatters import (
        format_price_brief,
        format_price_json,
        format_price_table,
        format_search_brief,
        format_search_csv,
        format_search_json,
        format_search_table,
    )

    err = _err_console(no_color)
    has_positional = any(value is not None for value in (origin, destination, date))
    has_full_positional = all(value is not None for value in (origin, destination, date))
    has_leg = len(leg) > 0

    # Validate --price incompatibilities
    if price_index is not None or price_selector is not None:
        if limit is not None:
            err.print("[red]Error: --price/--price-selector cannot be combined with --limit.[/red]")
            ctx.exit(2)
        if output_format == "csv":
            err.print("[red]Error: --price/--price-selector cannot be combined with -o csv.[/red]")
            ctx.exit(2)
    if price_index is not None and price_selector is not None:
        err.print("[red]Error: --price and --price-selector cannot be combined.[/red]")
        ctx.exit(2)

    if price_selector is not None:
        if has_positional or has_leg or return_date is not None or flight_number is not None:
            err.print("[red]Error: --price-selector cannot be combined with search inputs.[/red]")
            ctx.exit(2)
        if any(value is not None for value in (
            depart_after, depart_before, arrive_after, arrive_before,
            return_depart_after, return_depart_before,
        )):
            err.print("[red]Error: --price-selector cannot be combined with time-window filters.[/red]")
            ctx.exit(2)
        if nonstop or max_stops is not None or airline or cabin != "economy" or passengers != 1 or include_basic:
            err.print("[red]Error: --price-selector is self-contained and cannot be combined with search filters.[/red]")
            ctx.exit(2)

        try:
            if not quiet and output_format == "table":
                with err.status("[bold]Checking price...[/bold]"):
                    price_result = _price_trip_selector(
                        price_selector,
                        timeout=timeout,
                        retries=retries,
                    )
            else:
                price_result = _price_trip_selector(
                    price_selector,
                    timeout=timeout,
                    retries=retries,
                )
        except (ValueError, SwoopHTTPError, SwoopParseError, SwoopRateLimitError) as e:
            err.print(f"[red]Error checking price: {e}[/red]")
            ctx.exit(3)
            return

        if price_result is None:
            err.print("[yellow]Could not get price for the selected itinerary.[/yellow]")
            ctx.exit(1)
            return

        query_legs = _query_legs_from_price_result(price_result)
        if output_format == "json":
            format_price_json(price_result, query_legs=query_legs)
        elif output_format == "brief":
            format_price_brief(price_result, query_legs=query_legs)
        else:
            format_price_table(price_result, query_legs=query_legs, no_color=no_color)
        return

    if has_leg and has_positional:
        err.print("[red]Error: positional args and --leg cannot be used together.[/red]")
        ctx.exit(2)
    if has_leg:
        if return_date is not None:
            err.print("[red]Error: --leg cannot be combined with --return.[/red]")
            ctx.exit(2)
        if flight_number is not None:
            err.print("[red]Error: --leg cannot be combined with --flight.[/red]")
            ctx.exit(2)
        if any(value is not None for value in (
            depart_after, depart_before, arrive_after, arrive_before,
            return_depart_after, return_depart_before,
        )):
            err.print("[red]Error: time-window filters are not supported with --leg searches.[/red]")
            ctx.exit(2)
    elif has_positional and not has_full_positional:
        err.print("[red]Error: ORIGIN DESTINATION DATE are all required.[/red]")
        ctx.exit(2)
    elif not has_full_positional:
        err.print("[red]Error: provide ORIGIN DESTINATION DATE or use --leg.[/red]")
        ctx.exit(2)

    if has_leg:
        for leg_origin, leg_destination, leg_date in leg:
            warning = check_past_date(leg_date)
            if warning:
                err.print(f"[yellow]{warning}[/yellow]")
                break
    else:
        warning = check_past_date(date)
        if warning:
            err.print(f"[yellow]{warning}[/yellow]")

    if not quiet and output_format == "table":
        with err.status("[bold]Searching flights...[/bold]"):
            try:
                if has_leg:
                    result = _run_search_legs(
                        leg,
                        cabin=cabin, passengers=passengers, sort=sort,
                        nonstop=nonstop, max_stops=max_stops,
                        airline=airline, include_basic=include_basic,
                        timeout=timeout, retries=retries,
                    )
                else:
                    result = _run_search(
                        origin, destination, date,
                        return_date=return_date, cabin=cabin, passengers=passengers,
                        sort=sort, nonstop=nonstop, max_stops=max_stops,
                        airline=airline, flight_number=flight_number,
                        include_basic=include_basic,
                        depart_after=depart_after, depart_before=depart_before,
                        arrive_after=arrive_after, arrive_before=arrive_before,
                        return_depart_after=return_depart_after,
                        return_depart_before=return_depart_before,
                        timeout=timeout, retries=retries,
                    )
            except ValueError as e:
                err.print(f"[red]Error: {e}[/red]")
                ctx.exit(2)
            except SwoopRateLimitError:
                err.print("[red]Rate limited. Wait a few minutes. Tip: use --retries 3[/red]")
                ctx.exit(3)
            except SwoopHTTPError as e:
                err.print(f"[red]Google Flights returned HTTP {e.status_code}[/red]")
                ctx.exit(3)
            except SwoopParseError:
                err.print("[red]Could not parse Google Flights response[/red]")
                ctx.exit(4)
    else:
        try:
            if has_leg:
                result = _run_search_legs(
                    leg,
                    cabin=cabin, passengers=passengers, sort=sort,
                    nonstop=nonstop, max_stops=max_stops,
                    airline=airline, include_basic=include_basic,
                    timeout=timeout, retries=retries,
                )
            else:
                result = _run_search(
                    origin, destination, date,
                    return_date=return_date, cabin=cabin, passengers=passengers,
                    sort=sort, nonstop=nonstop, max_stops=max_stops,
                    airline=airline, flight_number=flight_number,
                    include_basic=include_basic,
                    depart_after=depart_after, depart_before=depart_before,
                    arrive_after=arrive_after, arrive_before=arrive_before,
                    return_depart_after=return_depart_after,
                    return_depart_before=return_depart_before,
                    timeout=timeout, retries=retries,
                )
        except ValueError as e:
            err.print(f"[red]Error: {e}[/red]")
            ctx.exit(2)
        except SwoopRateLimitError:
            err.print("[red]Rate limited. Wait a few minutes. Tip: use --retries 3[/red]")
            ctx.exit(3)
        except SwoopHTTPError as e:
            err.print(f"[red]Google Flights returned HTTP {e.status_code}[/red]")
            ctx.exit(3)
        except SwoopParseError:
            err.print("[red]Could not parse Google Flights response[/red]")
            ctx.exit(4)

    if result is None or not result.results:
        if has_leg:
            err.print("[yellow]No flights found for the requested trip.[/yellow]")
        else:
            err.print(
                f"[yellow]No flights found for {origin} -> {destination} "
                f"on {date}.[/yellow]"
            )
        ctx.exit(1)

    display_origin = leg[0][0] if has_leg else origin
    display_destination = leg[-1][1] if has_leg else destination
    display_date = leg[0][2] if has_leg else date
    display_return_date = None if has_leg else return_date
    fmt_kwargs = dict(
        origin=display_origin, destination=display_destination, date=display_date,
        cabin=cabin, adults=passengers, return_date=display_return_date,
        legs=leg if has_leg else None,
        limit=limit,
        price_hint_command=_build_search_price_hint_command(
            origin=origin,
            destination=destination,
            date=date,
            leg=leg,
            return_date=return_date,
            cabin=cabin,
            passengers=passengers,
            sort=sort,
            nonstop=nonstop,
            max_stops=max_stops,
            airline=airline,
            flight_number=flight_number,
            include_basic=include_basic,
            depart_after=depart_after,
            depart_before=depart_before,
            arrive_after=arrive_after,
            arrive_before=arrive_before,
            return_depart_after=return_depart_after,
            return_depart_before=return_depart_before,
        ),
    )

    # If --price is set, drill down into that result
    if price_index is not None:
        if price_index < 1 or price_index > len(result.results):
            err.print(
                f"[red]Error: --price {price_index} out of range. "
                f"Only {len(result.results)} results available.[/red]"
            )
            ctx.exit(2)
            return

        option = result.results[price_index - 1]

        try:
            if not quiet and output_format == "table":
                with err.status("[bold]Checking price...[/bold]"):
                    price_result = _price_trip_selector(
                        option.selector,
                        timeout=timeout,
                        retries=retries,
                    )
            else:
                price_result = _price_trip_selector(
                    option.selector,
                    timeout=timeout,
                    retries=retries,
                )
        except (ValueError, SwoopHTTPError, SwoopParseError, SwoopRateLimitError) as e:
            err.print(f"[red]Error checking price: {e}[/red]")
            ctx.exit(3)
            return

        if price_result is None:
            err.print(f"[yellow]Could not get price for result #{price_index}.[/yellow]")
            ctx.exit(1)
            return

        query_legs = _query_legs_from_price_result(price_result)

        if output_format == "json":
            format_price_json(price_result, query_legs=query_legs)
        elif output_format == "brief":
            format_price_brief(price_result, query_legs=query_legs)
        else:
            format_price_table(price_result, query_legs=query_legs, no_color=no_color)
        return

    if output_format == "table":
        format_search_table(result, no_color=no_color, **fmt_kwargs)
    elif output_format == "json":
        format_search_json(result, **fmt_kwargs)
    elif output_format == "csv":
        format_search_csv(result, limit=limit)
    elif output_format == "brief":
        format_search_brief(
            result,
            limit=limit,
            price_hint_command=fmt_kwargs["price_hint_command"],
        )


@click.command("price")
@click.argument("flight_number", type=str, required=False, default=None)
@click.argument("origin", type=IATA_CODE, required=False, default=None)
@click.argument("destination", type=IATA_CODE, required=False, default=None)
@click.argument("date", type=DATE, required=False, default=None)
@click.option("--selector", type=str, default=None, help="Opaque itinerary selector from search JSON.")
@click.option("-r", "--return-date", type=DATE, default=None, help="Return date (roundtrip).")
@click.option("--return-flight", type=str, default=None, help="Return flight number.")
@click.option("--leg", multiple=True, type=(IATA_CODE, IATA_CODE, DATE, str),
              help="Explicit leg: ORIGIN DEST DATE FLIGHT (repeatable).")
@click.option("-c", "--cabin", type=click.Choice(CABIN_CHOICES, case_sensitive=False), default="economy", show_default=True)
@click.option("-p", "--passengers", type=int, default=1, show_default=True)
@click.option("--max-stops", type=click.IntRange(0, 2), default=None)
@click.option("--include-basic", is_flag=True, default=False, help="Include basic economy fares.")
@click.option("--timeout", type=int, default=90, show_default=True)
@click.option("--retries", type=int, default=2, show_default=True)
@_output_options(["table", "json", "brief"])
@click.pass_context
def price_cmd(
    ctx, flight_number, origin, destination, date,
    selector,
    return_date, return_flight, leg, cabin, passengers, max_stops,
    include_basic, timeout, retries,
    output_format, no_color, quiet,
):
    """Check the price of a specific flight.

    Uses minimal RPC calls (1 for one-way, 3 for roundtrip).

    \b
    Simple syntax (positional args):
      swoop price DL2300 JFK LAX 2026-06-15
      swoop price DL2300 JFK LAX 2026-06-15 -r 2026-06-22
      swoop price DL2300 JFK LAX 2026-06-15 -r 2026-06-22 --return-flight DL2301

    \b
    Explicit leg syntax (--leg):
      swoop price --leg JFK LAX 2026-06-15 DL2300 --leg LAX JFK 2026-06-22 DL2301
    """
    import swoop
    from swoop.exceptions import SwoopHTTPError, SwoopParseError, SwoopRateLimitError

    from .formatters import format_price_brief, format_price_json, format_price_table

    err = _err_console(no_color)

    # Validate: positional args and --leg are mutually exclusive
    has_positional = any(value is not None for value in (flight_number, origin, destination, date))
    has_full_positional = all(value is not None for value in (flight_number, origin, destination, date))
    has_leg = len(leg) > 0
    has_selector = selector is not None

    if has_positional and has_leg:
        err.print("[red]Error: positional args and --leg cannot be used together.[/red]")
        ctx.exit(2)
        return
    if has_selector and (has_positional or has_leg):
        err.print("[red]Error: --selector, positional args, and --leg are mutually exclusive.[/red]")
        ctx.exit(2)
        return

    if has_selector:
        if return_date is not None or return_flight is not None:
            err.print("[red]Error: --selector cannot be combined with --return-date or --return-flight.[/red]")
            ctx.exit(2)
            return
        if max_stops is not None or cabin != "economy" or passengers != 1 or include_basic:
            err.print("[red]Error: --selector is self-contained and cannot be combined with pricing overrides.[/red]")
            ctx.exit(2)
            return
    elif has_leg and max_stops is not None:
        err.print("[red]Error: --max-stops is not supported with explicit --leg pricing.[/red]")
        ctx.exit(2)
        return

    if has_leg and (return_date is not None or return_flight is not None):
        err.print("[red]Error: --leg cannot be combined with --return-date or --return-flight.[/red]")
        ctx.exit(2)
        return

    if has_leg:
        query_legs = [
            {
                "flight_number": leg_flight,
                "origin": leg_origin,
                "destination": leg_dest,
                "date": leg_date,
                "selection": "explicit",
            }
            for leg_origin, leg_dest, leg_date, leg_flight in leg
        ]
    elif not has_selector and not has_positional:
        err.print("[red]Error: provide FLIGHT ORIGIN DEST DATE or use --leg.[/red]")
        ctx.exit(2)
        return
    elif has_positional and not has_full_positional:
        err.print("[red]Error: FLIGHT_NUMBER ORIGIN DESTINATION DATE are all required.[/red]")
        ctx.exit(2)
        return
    elif has_positional and return_date is not None and return_flight is None:
        err.print("[red]Error: --return-date requires --return-flight for positional roundtrip pricing.[/red]")
        ctx.exit(2)
        return
    elif return_flight is not None and return_date is None:
        err.print("[red]Error: --return-flight requires --return-date.[/red]")
        ctx.exit(2)
        return

    if has_selector:
        query_legs = None
    elif has_leg:
        for _leg_origin, _leg_dest, leg_date, _leg_flight in leg:
            warning = check_past_date(leg_date)
            if warning:
                err.print(f"[yellow]{warning}[/yellow]")
                break
    else:
        warning = check_past_date(date)
        if warning:
            err.print(f"[yellow]{warning}[/yellow]")

    try:
        if not quiet and output_format == "table":
            with err.status("[bold]Checking price...[/bold]"):
                if has_selector:
                    result = _price_trip_selector(selector, timeout=timeout, retries=retries)
                elif has_leg:
                    result = swoop.price_legs(
                        [
                            swoop.SelectedLeg(
                                flight_number=leg_flight,
                                origin=leg_origin,
                                destination=leg_dest,
                                date=leg_date,
                            )
                            for leg_origin, leg_dest, leg_date, leg_flight in leg
                        ],
                        cabin=cabin,
                        adults=passengers,
                        include_basic_economy=include_basic,
                        timeout=timeout,
                        retries=retries,
                    )
                else:
                    result = swoop.check_price(
                        flight_number,
                        origin=origin,
                        destination=destination,
                        date=date,
                        return_flight_number=return_flight,
                        return_date=return_date,
                        cabin=cabin,
                        adults=passengers,
                        max_stops=max_stops,
                        include_basic_economy=include_basic,
                        timeout=timeout,
                        retries=retries,
                    )
        else:
            if has_selector:
                result = _price_trip_selector(selector, timeout=timeout, retries=retries)
            elif has_leg:
                result = swoop.price_legs(
                    [
                        swoop.SelectedLeg(
                            flight_number=leg_flight,
                            origin=leg_origin,
                            destination=leg_dest,
                            date=leg_date,
                        )
                        for leg_origin, leg_dest, leg_date, leg_flight in leg
                    ],
                    cabin=cabin,
                    adults=passengers,
                    include_basic_economy=include_basic,
                    timeout=timeout,
                    retries=retries,
                )
            else:
                result = swoop.check_price(
                    flight_number,
                    origin=origin,
                    destination=destination,
                    date=date,
                    return_flight_number=return_flight,
                    return_date=return_date,
                    cabin=cabin,
                    adults=passengers,
                    max_stops=max_stops,
                    include_basic_economy=include_basic,
                    timeout=timeout,
                    retries=retries,
                )
    except ValueError as e:
        err.print(f"[red]Error: {e}[/red]")
        ctx.exit(2)
    except SwoopRateLimitError:
        err.print("[red]Rate limited. Wait a few minutes. Tip: use --retries 3[/red]")
        ctx.exit(3)
    except SwoopHTTPError as e:
        err.print(f"[red]Google Flights returned HTTP {e.status_code}[/red]")
        ctx.exit(3)
    except SwoopParseError:
        err.print("[red]Could not parse Google Flights response[/red]")
        ctx.exit(4)

    if result is None:
        if has_selector:
            err.print("[yellow]Selected itinerary no longer exists.[/yellow]")
        elif has_leg:
            err.print("[yellow]Selected itinerary was not found for the requested trip.[/yellow]")
        else:
            trip = f"{origin} -> {destination}"
            if return_date:
                trip += " (roundtrip)"
            err.print(
                f"[yellow]Flight {flight_number} not found on {trip} "
                f"on {date}.[/yellow]"
            )
        ctx.exit(1)

    if not has_selector and not has_leg:
        query_legs = [
            {
                "flight_number": flight_number,
                "origin": origin,
                "destination": destination,
                "date": date,
                "selection": "explicit",
            }
        ]
        if return_date is not None:
            query_legs.append(
                {
                    "flight_number": return_flight or "",
                    "origin": destination,
                    "destination": origin,
                    "date": return_date,
                    "selection": "explicit" if return_flight else "auto",
                }
            )
    if query_legs is None:
        query_legs = _query_legs_from_price_result(result)

    if output_format == "json":
        format_price_json(result, query_legs=query_legs)
    elif output_format == "brief":
        format_price_brief(result, query_legs=query_legs)
    else:
        format_price_table(result, query_legs=query_legs, no_color=no_color)
