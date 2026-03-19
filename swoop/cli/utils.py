"""Shared helpers and custom Click parameter types for the CLI."""

import re
from datetime import date as _date, datetime

import click


class IATACodeType(click.ParamType):
    """Click parameter type for IATA airport codes.

    Uppercases input and validates it's exactly 3 letters.
    """

    name = "IATA"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        if isinstance(value, str):
            value = value.strip().upper()
        if not re.match(r"^[A-Z]{3}$", value):
            self.fail(
                f"'{value}' is not a valid IATA airport code. "
                "Codes are 3 uppercase letters (e.g. JFK, LAX).",
                param,
                ctx,
            )
        return value


class DateType(click.ParamType):
    """Click parameter type for dates in YYYY-MM-DD format."""

    name = "DATE"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        if isinstance(value, str):
            value = value.strip()
        try:
            _date.fromisoformat(value)
        except (ValueError, TypeError):
            self.fail(
                f"'{value}' is not a valid date. Use YYYY-MM-DD format.",
                param,
                ctx,
            )
        return value


IATA_CODE = IATACodeType()
DATE = DateType()

SORT_MAP = {
    "top": 1,       # SORT_TOP
    "cheapest": 2,  # SORT_CHEAPEST
    "departure": 3, # SORT_DEPARTURE_TIME
    "arrival": 4,   # SORT_ARRIVAL_TIME
    "duration": 5,  # SORT_DURATION
}

CABIN_CHOICES = ["economy", "premium-economy", "business", "first"]


def format_time(h: int | None, m: int | None) -> str:
    """Format hour/minute as '8:30a' or '12:00p'."""
    h = h or 0
    m = m or 0
    if h == 0 and m == 0:
        return "12:00a"
    period = "a" if h < 12 else "p"
    display_h = h % 12 or 12
    return f"{display_h}:{m:02d}{period}"


def format_duration(minutes: int) -> str:
    """Format minutes as '5h 15m'."""
    if minutes <= 0:
        return "0m"
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m:02d}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def format_date_display(date_str: str) -> str:
    """Format 'YYYY-MM-DD' as 'Sat Jun 15, 2026'."""
    try:
        d = _date.fromisoformat(date_str)
        return d.strftime("%a %b %d, %Y").replace(" 0", " ")
    except ValueError:
        return date_str


def _iata_or_short(code: str) -> str:
    """Return the code if it looks like an IATA code, else truncate."""
    if re.match(r"^[A-Z]{3}$", code):
        return code
    # Fallback: not an IATA code (might be full airport name)
    return code[:3].upper() if code else "???"


def format_route(itin) -> str:
    """Format itinerary route as 'JFK -> ORD -> LAX'."""
    # Prefer itinerary-level departure/arrival (always IATA codes)
    if len(itin.segments) <= 1:
        dep = itin.departure_airport_code or (itin.segments[0].departure_airport_code if itin.segments else "")
        arr = itin.arrival_airport_code or (itin.segments[0].arrival_airport_code if itin.segments else "")
        return f"{_iata_or_short(dep)} -> {_iata_or_short(arr)}"
    # Multi-segment: use itinerary endpoints + layover airports
    airports = [_iata_or_short(itin.departure_airport_code)]
    for lay in itin.layovers:
        airport = lay.departure_airport_code or lay.arrival_airport_code
        if airport:
            airports.append(_iata_or_short(airport))
    airports.append(_iata_or_short(itin.arrival_airport_code))
    return " -> ".join(airports)


def check_past_date(date_str: str) -> str | None:
    """Return a warning message if the date is in the past, else None."""
    try:
        d = _date.fromisoformat(date_str)
        if d < _date.today():
            return f"Warning: {date_str} is in the past."
    except ValueError:
        pass
    return None
