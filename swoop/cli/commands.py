"""CLI commands for swoop: search, flight, book."""

import sys

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
@_output_options(["table", "json", "csv", "brief"])
@click.pass_context
def search_cmd(
    ctx, origin, destination, date,
    return_date, cabin, passengers, sort, nonstop, max_stops,
    airline, flight_number, include_basic,
    depart_after, depart_before, arrive_after, arrive_before,
    return_depart_after, return_depart_before,
    timeout, retries, limit,
    output_format, no_color, quiet,
):
    """Search for flights.

    \b
    Examples:
      swoop search JFK LAX 2026-06-15
      swoop search JFK LAX 2026-06-15 --nonstop --sort cheapest
      swoop search JFK LAX 2026-06-15 -r 2026-06-22 --cabin business
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

    if output_format == "table":
        format_search_table(result, no_color=no_color, **fmt_kwargs)
    elif output_format == "json":
        format_search_json(result, **fmt_kwargs)
    elif output_format == "csv":
        format_search_csv(result, limit=limit)
    elif output_format == "brief":
        format_search_brief(result, limit=limit)


@click.command("flight")
@click.argument("flight_number", type=str)
@click.option("-f", "--from", "origin", type=IATA_CODE, required=True, help="Departure airport.")
@click.option("-t", "--to", "destination", type=IATA_CODE, required=True, help="Arrival airport.")
@click.option("-d", "--date", type=DATE, required=True, help="Departure date.")
@click.option("-c", "--cabin", type=click.Choice(CABIN_CHOICES, case_sensitive=False), default="economy", show_default=True)
@click.option("-p", "--passengers", type=int, default=1, show_default=True)
@click.option("--max-stops", type=click.IntRange(0, 2), default=None)
@click.option("--timeout", type=int, default=90, show_default=True)
@click.option("--retries", type=int, default=0, show_default=True)
@_output_options(["table", "json"])
@click.pass_context
def flight_cmd(
    ctx, flight_number, origin, destination, date,
    cabin, passengers, max_stops, timeout, retries,
    output_format, no_color, quiet,
):
    """Look up a specific flight.

    \b
    Examples:
      swoop flight DL2300 -f JFK -t LAX -d 2026-06-15
      swoop flight UA1234 -f SFO -t JFK -d 2026-06-15 -o json
    """
    import swoop
    from swoop.exceptions import SwoopHTTPError, SwoopParseError, SwoopRateLimitError

    from .formatters import format_flight_detail, format_flight_json

    err = _err_console(no_color)

    warning = check_past_date(date)
    if warning:
        err.print(f"[yellow]{warning}[/yellow]")

    try:
        if not quiet and output_format == "table":
            with err.status("[bold]Searching flight...[/bold]"):
                itin = swoop.search_flight(
                    flight_number,
                    origin=origin,
                    destination=destination,
                    date=date,
                    cabin=cabin,
                    adults=passengers,
                    max_stops=max_stops,
                    timeout=timeout,
                    retries=retries,
                )
        else:
            itin = swoop.search_flight(
                flight_number,
                origin=origin,
                destination=destination,
                date=date,
                cabin=cabin,
                adults=passengers,
                max_stops=max_stops,
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

    if itin is None:
        err.print(
            f"[yellow]Flight {flight_number} not found on {origin} -> "
            f"{destination} on {date}.[/yellow]"
        )
        ctx.exit(1)

    if output_format == "json":
        format_flight_json(itin)
    else:
        format_flight_detail(itin, no_color=no_color)


@click.command("book")
@click.argument("index", type=int)
@click.argument("origin", type=IATA_CODE)
@click.argument("destination", type=IATA_CODE)
@click.argument("date", type=DATE)
@_search_options
@_output_options(["table", "json"])
@click.pass_context
def book_cmd(
    ctx, index, origin, destination, date,
    return_date, cabin, passengers, sort, nonstop, max_stops,
    airline, flight_number, include_basic,
    depart_after, depart_before, arrive_after, arrive_before,
    return_depart_after, return_depart_before,
    timeout, retries,
    output_format, no_color, quiet,
):
    """Show fare tiers for a search result.

    Re-runs the search, picks result #INDEX, and shows booking options.

    \b
    Examples:
      swoop book 1 JFK LAX 2026-06-15
      swoop book 2 JFK LAX 2026-06-15 --nonstop -o json
    """
    import swoop
    from swoop.exceptions import SwoopHTTPError, SwoopParseError, SwoopRateLimitError

    from .formatters import format_booking_json, format_booking_table

    err = _err_console(no_color)

    if index < 1:
        err.print("[red]Error: INDEX must be >= 1.[/red]")
        ctx.exit(2)

    warning = check_past_date(date)
    if warning:
        err.print(f"[yellow]{warning}[/yellow]")

    # Re-run search
    try:
        if not quiet and output_format == "table":
            with err.status("[bold]Searching flights...[/bold]"):
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

    if result is None or (not result.best and not result.other):
        err.print(
            f"[yellow]No flights found for {origin} -> {destination} "
            f"on {date}.[/yellow]"
        )
        ctx.exit(1)

    all_itins = [*result.best, *result.other]
    if index > len(all_itins):
        err.print(
            f"[red]Error: INDEX {index} out of range. "
            f"Only {len(all_itins)} results available.[/red]"
        )
        ctx.exit(2)

    itin = all_itins[index - 1]

    if not itin.booking_token:
        err.print("[yellow]No booking token available for this itinerary.[/yellow]")
        ctx.exit(1)

    # Fetch booking options
    try:
        if not quiet and output_format == "table":
            with err.status("[bold]Fetching fare options...[/bold]"):
                options = swoop.get_booking_results(
                    itin, timeout=timeout, retries=retries,
                )
        else:
            options = swoop.get_booking_results(
                itin, timeout=timeout, retries=retries,
            )
    except SwoopRateLimitError:
        err.print("[red]Rate limited. Wait a few minutes. Tip: use --retries 3[/red]")
        ctx.exit(3)
    except SwoopHTTPError as e:
        err.print(f"[red]Google Flights returned HTTP {e.status_code}[/red]")
        ctx.exit(3)
    except SwoopParseError:
        err.print("[red]Could not parse Google Flights response[/red]")
        ctx.exit(4)
    except Exception as e:
        err.print(f"[red]Error fetching booking options: {e}[/red]")
        ctx.exit(4)

    if output_format == "json":
        format_booking_json(options, itin=itin)
    else:
        format_booking_table(options, itin=itin, no_color=no_color)
