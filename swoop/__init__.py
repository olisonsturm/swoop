"""Swoop — Search Google Flights programmatically.

Calls Google Flights' internal RPC endpoints with TLS impersonation
and decodes the nested-list responses into typed Python dataclasses.

Basic usage::

    from swoop import search

    results = search("JFK", "LAX", "2026-06-01")
    for flight in results.best:
        print(f"${flight.price} — {flight.airline_names}")
"""

__version__ = "0.2.2"

from .decoder import (
    AmenityFlags,
    BookingOption,
    CarbonEmissions,
    Codeshare,
    SearchResult,
    Flight,
    Itinerary,
    Layover,
    PriceRange,
    QualitySignals,
    itinerary_matches_flight,
)
from .exceptions import SwoopError, SwoopHTTPError, SwoopParseError, SwoopRateLimitError
from .builders import ItinerarySummary
from .rpc import (
    SORT_ARRIVAL_TIME,
    SORT_CHEAPEST,
    SORT_DEPARTURE_TIME,
    SORT_DURATION,
    SORT_TOP,
    STOPS_ANY,
    STOPS_NONSTOP,
    STOPS_ONE_OR_FEWER,
    STOPS_TWO_OR_FEWER,
    get_booking_results,
    search_raw,
)

# ---------------------------------------------------------------------------
# search() — the primary entry point with friendlier parameter names.
# ---------------------------------------------------------------------------

import logging
from typing import Optional

from ._validate import parse_flight_number, validate_search_params

logger = logging.getLogger(__name__)


def _correct_roundtrip_economy_prices(
    result: SearchResult,
    *,
    include_basic_economy: bool = False,
    timeout: int = 90,
    retries: int = 0,
) -> None:
    """Patch itinerary prices with accurate GetBookingResults fares.

    Roundtrip expansion prices from GetShoppingResults are inflated vs actual
    bookable fares.  This calls GetBookingResults on each itinerary and
    replaces ``direct_price`` with the cheapest option.

    When *include_basic_economy* is ``False`` (default), only non-basic
    economy options are considered.  When ``True``, all options including
    basic economy are eligible.
    """
    for itinerary in [*result.best, *result.other]:
        if not itinerary.booking_token:
            continue
        try:
            options = get_booking_results(
                itinerary, timeout=timeout, retries=retries,
            )
        except Exception as exc:
            logger.debug("GetBookingResults failed, keeping original price: %s", exc)
            continue

        # Filter to eligible options
        if include_basic_economy:
            eligible = [o for o in options if o.price > 0]
        else:
            eligible = [o for o in options if not o.is_basic and o.price > 0]
        if not eligible:
            continue

        best_option = min(eligible, key=lambda o: o.price)
        itinerary.direct_price = best_option.price
        if itinerary.price_info is not None:
            itinerary.price_info = ItinerarySummary(
                flights=itinerary.price_info.flights,
                price=float(best_option.price),
                currency=itinerary.price_info.currency,
            )


def _filter_by_flight_number(
    result: Optional[SearchResult], carrier: Optional[str], number: str
) -> Optional[SearchResult]:
    """Filter a SearchResult to only itineraries matching a flight number."""
    if result is None:
        return None
    best = [it for it in result.best if itinerary_matches_flight(it, carrier, number)]
    other = [it for it in result.other if itinerary_matches_flight(it, carrier, number)]
    if not best and not other:
        return None
    return SearchResult(_raw=result._raw, best=best, other=other, price_range=result.price_range)


def search(
    origin: str,
    destination: str,
    date: str,
    *,
    return_date: Optional[str] = None,
    cabin: str = "economy",
    adults: int = 1,
    max_stops: Optional[int] = None,
    sort: int = SORT_DEPARTURE_TIME,
    airlines: Optional[list[str]] = None,
    flight_number: Optional[str] = None,
    include_basic_economy: bool = False,
    earliest_departure: Optional[int] = None,
    latest_departure: Optional[int] = None,
    earliest_arrival: Optional[int] = None,
    latest_arrival: Optional[int] = None,
    return_earliest_departure: Optional[int] = None,
    return_latest_departure: Optional[int] = None,
    timeout: int = 90,
    retries: int = 0,
) -> Optional[SearchResult]:
    """Search Google Flights and return decoded results.

    Args:
        origin: Origin airport IATA code (e.g. ``"JFK"``).
        destination: Destination airport IATA code (e.g. ``"LAX"``).
        date: Departure date as ``YYYY-MM-DD``.
        return_date: Return date for roundtrip searches. Omit for one-way.
        cabin: Cabin class — ``"economy"``, ``"premium-economy"``,
            ``"business"``, or ``"first"``.
        adults: Number of adult passengers (default 1).
        max_stops: Maximum stops. ``None`` = any, ``0`` = nonstop,
            ``1`` = one stop, ``2`` = two stops.
        sort: Sort order. Use ``SORT_TOP``, ``SORT_CHEAPEST``,
            ``SORT_DEPARTURE_TIME``, ``SORT_ARRIVAL_TIME``, or ``SORT_DURATION``.
        airlines: Filter to specific airline IATA codes (e.g. ``["DL", "UA"]``).
        flight_number: Filter results to a specific flight number (e.g.
            ``"DL 171"``, ``"DL171"``, or ``"171"``). When a carrier is
            included, it is also added to the RPC airline filter.
        include_basic_economy: When ``False`` (default), basic economy fares
            are excluded so prices reflect Main Cabin.  Set ``True`` to
            include basic economy fares.
        earliest_departure: Earliest departure hour (0–23).
        latest_departure: Latest departure hour (1–24).
        earliest_arrival: Earliest arrival hour (0–23).
        latest_arrival: Latest arrival hour (1–24).
        return_earliest_departure: Earliest return departure hour (0–23).
        return_latest_departure: Latest return departure hour (1–24).
        timeout: HTTP request timeout in seconds (default 90).
        retries: Number of retries on HTTP 429 with exponential backoff
            (default 0 — no retries).

    Returns:
        A :class:`SearchResult` with ``best`` and ``other`` itinerary
        lists, or ``None`` if no results found.

    Raises:
        SwoopHTTPError: If Google Flights returns a non-200 response.
        SwoopRateLimitError: If Google Flights returns HTTP 429.
        SwoopParseError: If the response cannot be parsed.

    Example::

        from swoop import search

        # One-way search
        results = search("SFO", "JFK", "2026-06-15")

        # Roundtrip search
        results = search("SFO", "JFK", "2026-06-15", return_date="2026-06-22")

        # Business class, nonstop only
        results = search("LAX", "NRT", "2026-06-15", cabin="business", max_stops=0)
    """
    # Parse flight number filter if provided
    parsed_carrier = None
    parsed_number = None
    if flight_number is not None:
        parsed_carrier, parsed_number = parse_flight_number(flight_number)
        # Auto-add carrier to airline filter for RPC-level narrowing
        if parsed_carrier is not None:
            if airlines is None:
                airlines = [parsed_carrier]
            elif parsed_carrier not in airlines:
                airlines = list(airlines) + [parsed_carrier]

    validate_search_params(
        origin,
        destination,
        date,
        return_date=return_date,
        cabin=cabin,
        adults=adults,
        earliest_departure=earliest_departure,
        latest_departure=latest_departure,
        earliest_arrival=earliest_arrival,
        latest_arrival=latest_arrival,
        return_earliest_departure=return_earliest_departure,
        return_latest_departure=return_latest_departure,
    )
    # For one-way economy, exclude basic economy at the RPC level unless the
    # caller opted into basic fares.  This flag inflates roundtrip expansion
    # prices, so we only set it for one-way.
    exclude_basic = (
        cabin == "economy"
        and return_date is None
        and not include_basic_economy
    )

    result = search_raw(
        origin=origin,
        destination=destination,
        date=date,
        cabin=cabin,
        adults=adults,
        sort=sort,
        max_stops=max_stops,
        airlines=airlines,
        earliest_departure=earliest_departure,
        latest_departure=latest_departure,
        earliest_arrival=earliest_arrival,
        latest_arrival=latest_arrival,
        return_date=return_date,
        return_earliest_departure=return_earliest_departure,
        return_latest_departure=return_latest_departure,
        timeout=timeout,
        retries=retries,
        exclude_basic_economy=exclude_basic,
    )

    # When a flight_number filter is provided, filter BEFORE correcting
    # roundtrip prices. This avoids calling GetBookingResults on every
    # itinerary only to discard most of them — turning N+1 RPCs into 2.
    if parsed_number is not None:
        result = _filter_by_flight_number(result, parsed_carrier, parsed_number)

    # For roundtrip economy, correct inflated expansion prices by fetching
    # actual bookable fares via GetBookingResults.
    if result is not None and return_date is not None and cabin == "economy":
        _correct_roundtrip_economy_prices(
            result,
            include_basic_economy=include_basic_economy,
            timeout=timeout,
            retries=retries,
        )

    return result


def search_flight(
    flight_number: str,
    *,
    origin: str,
    destination: str,
    date: str,
    cabin: str = "economy",
    adults: int = 1,
    max_stops: Optional[int] = None,
    timeout: int = 90,
    retries: int = 0,
) -> Optional[Itinerary]:
    """Search for a specific flight by number.

    Searches Google Flights for the given route and filters to the matching
    flight number. This is a convenience wrapper around :func:`search`.

    Args:
        flight_number: Flight number (e.g. ``"DL 171"``, ``"DL171"``,
            or ``"171"``).
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        date: Departure date as ``YYYY-MM-DD``.
        cabin: Cabin class (default ``"economy"``).
        adults: Number of adult passengers (default 1).
        max_stops: Maximum stops (default any).
        timeout: HTTP request timeout in seconds (default 90).
        retries: Number of retries on HTTP 429 (default 0).

    Returns:
        The matching :class:`Itinerary`, or ``None`` if not found.

    Example::

        from swoop import search_flight

        itin = search_flight("DL 171", origin="JFK", destination="LAX", date="2026-06-15")
        if itin:
            print(f"${itin.price}")
    """
    result = search(
        origin,
        destination,
        date,
        flight_number=flight_number,
        cabin=cabin,
        adults=adults,
        max_stops=max_stops,
        timeout=timeout,
        retries=retries,
    )
    if result is None:
        return None
    # Prefer best over other
    if result.best:
        return result.best[0]
    if result.other:
        return result.other[0]
    return None


__all__ = [
    # Functions
    "search",
    "search_flight",
    "get_booking_results",
    "search_raw",
    "parse_flight_number",
    "itinerary_matches_flight",
    # Types
    "SearchResult",
    "Itinerary",
    "Flight",
    "BookingOption",
    "Codeshare",
    "Layover",
    "CarbonEmissions",
    "PriceRange",
    "AmenityFlags",
    "QualitySignals",
    # Exceptions
    "SwoopError",
    "SwoopHTTPError",
    "SwoopParseError",
    "SwoopRateLimitError",
    # Constants
    "SORT_TOP",
    "SORT_CHEAPEST",
    "SORT_DEPARTURE_TIME",
    "SORT_ARRIVAL_TIME",
    "SORT_DURATION",
    "STOPS_ANY",
    "STOPS_NONSTOP",
    "STOPS_ONE_OR_FEWER",
    "STOPS_TWO_OR_FEWER",
]
