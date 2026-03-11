"""Swoop — Search Google Flights programmatically.

Calls Google Flights' internal RPC endpoints with TLS impersonation
and decodes the nested-list responses into typed Python dataclasses.

Basic usage::

    from swoop import search

    results = search("JFK", "LAX", "2026-06-01")
    for flight in results.best:
        print(f"${flight.price} — {flight.airline_names}")
"""

__version__ = "0.3.0"

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
from dataclasses import dataclass, field
from typing import Optional

from ._validate import parse_flight_number, validate_search_params
from .rpc import _build_selected_legs

logger = logging.getLogger(__name__)


def _correct_roundtrip_economy_prices(
    result: SearchResult,
    *,
    include_basic_economy: bool = False,
    timeout: int = 90,
    retries: int = 2,
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
    retries: int = 2,
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
            and jitter (default 2).

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
    return_date: Optional[str] = None,
    return_flight_number: Optional[str] = None,
    cabin: str = "economy",
    adults: int = 1,
    max_stops: Optional[int] = None,
    timeout: int = 90,
    retries: int = 2,
) -> Optional[Itinerary]:
    """Search for a specific flight by number.

    Searches Google Flights for the given route and filters to the matching
    flight number. This is a convenience wrapper around :func:`search`.

    For roundtrip searches, provide ``return_date``. If ``return_flight_number``
    is given, the return leg is also filtered by flight number.

    Args:
        flight_number: Flight number (e.g. ``"DL 171"``, ``"DL171"``,
            or ``"171"``).
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        date: Departure date as ``YYYY-MM-DD``.
        return_date: Return date for roundtrip (default ``None``).
        return_flight_number: Return flight number to filter (default ``None``).
        cabin: Cabin class (default ``"economy"``).
        adults: Number of adult passengers (default 1).
        max_stops: Maximum stops (default any).
        timeout: HTTP request timeout in seconds (default 90).
        retries: Number of retries on HTTP 429 (default 2).

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
        return_date=return_date,
        flight_number=flight_number,
        cabin=cabin,
        adults=adults,
        max_stops=max_stops,
        timeout=timeout,
        retries=retries,
    )

    if return_flight_number is not None and result is not None:
        ret_carrier, ret_number = parse_flight_number(return_flight_number)
        result = _filter_by_flight_number(result, ret_carrier, ret_number)

    if result is None:
        return None
    # Prefer best over other
    if result.best:
        return result.best[0]
    if result.other:
        return result.other[0]
    return None


# ---------------------------------------------------------------------------
# check_price() — targeted price lookup for a known flight.
# ---------------------------------------------------------------------------


@dataclass
class PriceResult:
    """Result of a targeted price check for a specific flight.

    Attributes:
        price: Total price in USD (integer).
        fare_brand: Fare brand label (e.g. ``"MAIN"``, ``"BASIC"``).
        is_basic_economy: Whether the price is for basic economy.
        booking_options: All available fare tiers from GetBookingResults.
        itinerary: The matched flight itinerary.
        rpc_calls: Number of RPC calls made (for observability).
    """
    price: int
    fare_brand: Optional[str] = None
    is_basic_economy: bool = False
    booking_options: list[BookingOption] = field(default_factory=list)
    itinerary: Optional[Itinerary] = None
    rpc_calls: int = 0


def check_price(
    flight_number: str,
    *,
    origin: str,
    destination: str,
    date: str,
    return_flight_number: Optional[str] = None,
    return_date: Optional[str] = None,
    cabin: str = "economy",
    adults: int = 1,
    max_stops: Optional[int] = None,
    include_basic_economy: bool = False,
    timeout: int = 90,
    retries: int = 2,
) -> Optional[PriceResult]:
    """Look up the current price for a specific flight.

    Unlike :func:`search` which returns all itineraries on a route,
    ``check_price`` is optimized for the "what does flight X cost today?"
    use case. It uses far fewer RPC calls:

    - **One-way**: 1 RPC (search with airline filter + exclude basic economy).
    - **Roundtrip**: 3 RPCs (outbound search, return expansion, booking results).

    Args:
        flight_number: Outbound flight number (e.g. ``"DL2300"``).
        origin: Origin airport IATA code.
        destination: Destination airport IATA code.
        date: Departure date as ``YYYY-MM-DD``.
        return_flight_number: Return flight number for roundtrip.
        return_date: Return date for roundtrip.
        cabin: Cabin class (default ``"economy"``).
        adults: Number of adult passengers (default 1).
        max_stops: Maximum stops (default any).
        include_basic_economy: Include basic economy fares (default ``False``).
        timeout: HTTP request timeout in seconds (default 90).
        retries: Number of retries on HTTP 429 (default 2).

    Returns:
        A :class:`PriceResult` with the price and matched itinerary,
        or ``None`` if the flight was not found.

    Example::

        from swoop import check_price

        # One-way
        result = check_price("DL2300", origin="JFK", destination="LAX", date="2026-06-15")
        if result:
            print(f"${result.price}")

        # Roundtrip
        result = check_price(
            "DL2300", origin="JFK", destination="LAX", date="2026-06-15",
            return_flight_number="DL2301", return_date="2026-06-22",
        )
        if result:
            print(f"${result.price} roundtrip")
    """
    # Parse outbound flight number for airline filter
    parsed_carrier, parsed_number = parse_flight_number(flight_number)
    airlines = [parsed_carrier] if parsed_carrier else None

    validate_search_params(
        origin, destination, date,
        return_date=return_date, cabin=cabin, adults=adults,
    )

    is_roundtrip = return_date is not None
    rpc_calls = 0

    # For one-way economy, exclude basic economy at the RPC level so
    # GetShoppingResults returns main cabin prices directly.
    exclude_basic = (
        cabin == "economy"
        and not is_roundtrip
        and not include_basic_economy
    )

    # Step 1: Search for outbound flights
    result = search_raw(
        origin=origin,
        destination=destination,
        date=date,
        cabin=cabin,
        adults=adults,
        sort=SORT_DEPARTURE_TIME,
        max_stops=max_stops,
        airlines=airlines,
        return_date=return_date if is_roundtrip else None,
        timeout=timeout,
        retries=retries,
        exclude_basic_economy=exclude_basic,
    )
    rpc_calls += 1

    if result is None:
        return None

    # Step 2: Find matching outbound itinerary
    filtered = _filter_by_flight_number(result, parsed_carrier, parsed_number)
    if filtered is None:
        return None

    outbound = filtered.best[0] if filtered.best else (filtered.other[0] if filtered.other else None)
    if outbound is None:
        return None

    # --- One-way path ---
    if not is_roundtrip:
        price = outbound.price
        if price is None or price <= 0:
            return None
        return PriceResult(
            price=price,
            itinerary=outbound,
            rpc_calls=rpc_calls,
        )

    # --- Roundtrip path ---
    # Step 2b: Build selected outbound legs for return expansion
    selected_outbound_legs = _build_selected_legs(outbound)
    if not selected_outbound_legs:
        return None

    # Step 3: Search for return flights with selected outbound
    return_result = search_raw(
        origin=origin,
        destination=destination,
        date=date,
        cabin=cabin,
        adults=adults,
        sort=SORT_DEPARTURE_TIME,
        max_stops=max_stops,
        airlines=None,
        return_date=return_date,
        selected_outbound_legs=selected_outbound_legs,
        timeout=timeout,
        retries=retries,
    )
    rpc_calls += 1

    if return_result is None:
        return None

    # Filter return results by return flight number if provided
    if return_flight_number is not None:
        ret_carrier, ret_number = parse_flight_number(return_flight_number)
        return_result = _filter_by_flight_number(return_result, ret_carrier, ret_number)
        if return_result is None:
            return None

    return_itin = (
        return_result.best[0] if return_result.best
        else (return_result.other[0] if return_result.other else None)
    )
    if return_itin is None:
        return None

    # Step 4: Get booking results for the return itinerary (roundtrip total)
    try:
        options = get_booking_results(
            return_itin,
            timeout=timeout,
            retries=retries,
        )
        rpc_calls += 1
    except Exception as exc:
        logger.debug("GetBookingResults failed for roundtrip: %s", exc)
        # Fall back to direct_price from return expansion
        price = return_itin.price
        if price is None or price <= 0:
            return None
        return PriceResult(
            price=price,
            itinerary=return_itin,
            rpc_calls=rpc_calls,
        )

    # Select the best non-basic option (or any option if include_basic)
    if include_basic_economy:
        eligible = [o for o in options if o.price > 0]
    else:
        eligible = [o for o in options if not o.is_basic and o.price > 0]

    if not eligible:
        # Fall back to direct_price
        price = return_itin.price
        if price is None or price <= 0:
            return None
        return PriceResult(
            price=price,
            itinerary=return_itin,
            booking_options=options,
            rpc_calls=rpc_calls,
        )

    best_option = min(eligible, key=lambda o: o.price)
    return PriceResult(
        price=best_option.price,
        fare_brand=best_option.brand_label or best_option.brand_code or None,
        is_basic_economy=best_option.is_basic,
        booking_options=options,
        itinerary=return_itin,
        rpc_calls=rpc_calls,
    )


__all__ = [
    # Functions
    "search",
    "search_flight",
    "check_price",
    "get_booking_results",
    "search_raw",
    "parse_flight_number",
    "itinerary_matches_flight",
    # Types
    "PriceResult",
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
