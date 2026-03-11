"""CLI commands for swoop: search and price."""

import click
from rich.console import Console

from .utils import (
    CABIN_CHOICES,
    DATE,
    IATA_CODE,
    SORT_MAP,
    check_past_date,
    format_date_display,
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


def _price_search_result(
    itinerary,
    *,
    origin,
    destination,
    date,
    return_date,
    cabin,
    passengers,
    nonstop,
    max_stops,
    include_basic,
    timeout,
    retries,
):
    """Price an already-selected itinerary exactly."""
    import swoop

    stops = 0 if nonstop else max_stops
    return swoop._price_from_outbound_itinerary(
        itinerary,
        origin=origin,
        destination=destination,
        date=date,
        return_date=return_date,
        cabin=cabin,
        adults=passengers,
        max_stops=stops,
        include_basic_economy=include_basic,
        timeout=timeout,
        retries=retries,
        outbound_selection="explicit",
    )


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
@click.argument("origin", type=IATA_CODE)
@click.argument("destination", type=IATA_CODE)
@click.argument("date", type=DATE)
@_search_options
@click.option("-l", "--limit", type=int, default=None, help="Max results to display.")
@click.option("--price", "price_index", type=int, default=None,
              help="Show price + fares for search result #N.")
@_output_options(["table", "json", "csv", "brief"])
@click.pass_context
def search_cmd(
    ctx, origin, destination, date,
    return_date, cabin, passengers, sort, nonstop, max_stops,
    airline, flight_number, include_basic,
    depart_after, depart_before, arrive_after, arrive_before,
    return_depart_after, return_depart_before,
    timeout, retries, limit, price_index,
    output_format, no_color, quiet,
):
    """Search for flights.

    \b
    Examples:
      swoop search JFK LAX 2026-06-15
      swoop search JFK LAX 2026-06-15 --nonstop --sort cheapest
      swoop search JFK LAX 2026-06-15 -r 2026-06-22 --cabin business
      swoop search JFK LAX 2026-06-15 --price 1
      swoop search JFK LAX 2026-06-15 -o json -q | jq '.results[0]'
    """
    from swoop.exceptions import SwoopHTTPError, SwoopParseError, SwoopRateLimitError

    from .formatters import (
        format_search_brief,
        format_search_csv,
        format_search_json,
        format_search_table,
    )

    err = _err_console(no_color)

    # Validate --price incompatibilities
    if price_index is not None:
        if limit is not None:
            err.print("[red]Error: --price cannot be combined with --limit.[/red]")
            ctx.exit(2)
        if output_format == "csv":
            err.print("[red]Error: --price cannot be combined with -o csv.[/red]")
            ctx.exit(2)

    # Past date warning
    warning = check_past_date(date)
    if warning:
        err.print(f"[yellow]{warning}[/yellow]")

    # Spinner
    if not quiet and output_format == "table":
        with err.status("[bold]Searching flights...[/bold]"):
            try:
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

    if result is None or (not result.best and not result.other):
        err.print(
            f"[yellow]No flights found for {origin} -> {destination} "
            f"on {date}.[/yellow]"
        )
        ctx.exit(1)

    fmt_kwargs = dict(
        origin=origin, destination=destination, date=date,
        cabin=cabin, adults=passengers, return_date=return_date,
        limit=limit,
    )

    # If --price is set, drill down into that result
    if price_index is not None:
        from .formatters import format_price_brief, format_price_json, format_price_table

        all_itins = [*result.best, *result.other]
        if price_index < 1 or price_index > len(all_itins):
            err.print(
                f"[red]Error: --price {price_index} out of range. "
                f"Only {len(all_itins)} results available.[/red]"
            )
            ctx.exit(2)
            return

        itin = all_itins[price_index - 1]
        if not itin.flights:
            err.print("[red]Error: selected itinerary has no flight info.[/red]")
            ctx.exit(2)
            return

        try:
            if not quiet and output_format == "table":
                with err.status("[bold]Checking price...[/bold]"):
                    price_result = _price_search_result(
                        itin,
                        origin=origin,
                        destination=destination,
                        date=date,
                        return_date=return_date,
                        cabin=cabin,
                        passengers=passengers,
                        nonstop=nonstop,
                        max_stops=max_stops,
                        include_basic=include_basic,
                        timeout=timeout,
                        retries=retries,
                    )
            else:
                price_result = _price_search_result(
                    itin,
                    origin=origin,
                    destination=destination,
                    date=date,
                    return_date=return_date,
                    cabin=cabin,
                    passengers=passengers,
                    nonstop=nonstop,
                    max_stops=max_stops,
                    include_basic=include_basic,
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

        flight_label = (
            price_result.resolved_legs[0].flight_summary
            if price_result.resolved_legs
            else f"{itin.flights[0].airline}{itin.flights[0].flight_number}"
        )

        if output_format == "json":
            format_price_json(price_result, flight_number=flight_label, origin=origin,
                              destination=destination, date=date, return_date=return_date)
        elif output_format == "brief":
            format_price_brief(price_result, return_date=return_date)
        else:
            format_price_table(price_result, flight_number=flight_label, origin=origin,
                               destination=destination, date=date, return_date=return_date,
                               no_color=no_color)
        return

    if output_format == "table":
        format_search_table(result, no_color=no_color, **fmt_kwargs)
    elif output_format == "json":
        format_search_json(result, **fmt_kwargs)
    elif output_format == "csv":
        format_search_csv(result, limit=limit)
    elif output_format == "brief":
        format_search_brief(result, limit=limit)


@click.command("price")
@click.argument("flight_number", type=str, required=False, default=None)
@click.argument("origin", type=IATA_CODE, required=False, default=None)
@click.argument("destination", type=IATA_CODE, required=False, default=None)
@click.argument("date", type=DATE, required=False, default=None)
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
    Explicit leg syntax (--leg, up to 2 legs):
      swoop price --leg JFK LAX 2026-06-15 DL2300 --leg LAX JFK 2026-06-22 DL2301
    """
    import swoop
    from swoop.exceptions import SwoopHTTPError, SwoopParseError, SwoopRateLimitError

    from .formatters import format_price_brief, format_price_json, format_price_table

    err = _err_console(no_color)

    # Validate: positional args and --leg are mutually exclusive
    has_positional = flight_number is not None
    has_leg = len(leg) > 0

    if has_positional and has_leg:
        err.print("[red]Error: positional args and --leg cannot be used together.[/red]")
        ctx.exit(2)
        return

    if has_leg and (return_date is not None or return_flight is not None):
        err.print("[red]Error: --leg cannot be combined with --return-date or --return-flight.[/red]")
        ctx.exit(2)
        return

    if has_leg:
        # --leg syntax: each tuple is (origin, dest, date, flight_number)
        if len(leg) == 1:
            leg_origin, leg_dest, leg_date, leg_flight = leg[0]
            flight_number = leg_flight
            origin = leg_origin
            destination = leg_dest
            date = leg_date
        elif len(leg) == 2:
            leg_origin, leg_dest, leg_date, leg_flight = leg[0]
            ret_origin, ret_dest, ret_date, ret_flight = leg[1]
            flight_number = leg_flight
            origin = leg_origin
            destination = leg_dest
            date = leg_date
            return_date = ret_date
            return_flight = ret_flight
        else:
            err.print("[red]Error: at most 2 --leg options are supported.[/red]")
            ctx.exit(2)
            return
    elif not has_positional:
        err.print("[red]Error: provide FLIGHT ORIGIN DEST DATE or use --leg.[/red]")
        ctx.exit(2)
        return
    elif origin is None or destination is None or date is None:
        err.print("[red]Error: FLIGHT_NUMBER ORIGIN DESTINATION DATE are all required.[/red]")
        ctx.exit(2)
        return
    elif return_flight is not None and return_date is None:
        err.print("[red]Error: --return-flight requires --return-date.[/red]")
        ctx.exit(2)
        return

    warning = check_past_date(date)
    if warning:
        err.print(f"[yellow]{warning}[/yellow]")

    try:
        if not quiet and output_format == "table":
            with err.status("[bold]Checking price...[/bold]"):
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
        trip = f"{origin} -> {destination}"
        if return_date:
            trip += " (roundtrip)"
        err.print(
            f"[yellow]Flight {flight_number} not found on {trip} "
            f"on {date}.[/yellow]"
        )
        ctx.exit(1)

    if output_format == "json":
        format_price_json(result, flight_number=flight_number, origin=origin,
                          destination=destination, date=date, return_date=return_date)
    elif output_format == "brief":
        format_price_brief(result, return_date=return_date)
    else:
        format_price_table(result, flight_number=flight_number, origin=origin,
                           destination=destination, date=date, return_date=return_date,
                           no_color=no_color)
