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
from .builders import ItinerarySummary, SearchLeg
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

from ._validate import (
    parse_flight_number,
    validate_adults,
    validate_cabin,
    validate_date,
    validate_iata_code,
    validate_search_params,
    validate_time_range,
)
from .rpc import _build_selected_legs, _normalize_rpc_leg, _search_from_legs

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
        except (SwoopHTTPError, SwoopParseError) as exc:
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


def _validate_leg_search_inputs(
    legs: list[SearchLeg],
    *,
    cabin: str,
    adults: int,
    leg_time_windows: Optional[list[dict[str, Optional[int]]]] = None,
) -> None:
    """Validate a list of explicit search legs."""
    if not legs:
        raise ValueError("at least one leg is required")
    if len(legs) > 2:
        raise ValueError("multi-city search is not yet supported")

    validate_cabin(cabin)
    validate_adults(adults)

    for idx, leg in enumerate(legs):
        validate_iata_code(leg.from_airport, f"legs[{idx}].from_airport")
        validate_iata_code(leg.to_airport, f"legs[{idx}].to_airport")
        validate_date(leg.date, f"legs[{idx}].date")

    if leg_time_windows:
        for idx, window in enumerate(leg_time_windows):
            validate_time_range(window.get("earliest_departure"), f"legs[{idx}].earliest_departure", 0, 23)
            validate_time_range(window.get("latest_departure"), f"legs[{idx}].latest_departure", 1, 24)
            validate_time_range(window.get("earliest_arrival"), f"legs[{idx}].earliest_arrival", 0, 23)
            validate_time_range(window.get("latest_arrival"), f"legs[{idx}].latest_arrival", 1, 24)


def _search_with_normalized_legs(
    request_legs: list[dict[str, object]],
    *,
    cabin: str = "economy",
    adults: int = 1,
    sort: int = SORT_DEPARTURE_TIME,
    include_basic_economy: bool = False,
    timeout: int = 90,
    retries: int = 2,
    correct_roundtrip_prices: bool = True,
) -> Optional[SearchResult]:
    """Execute a search from normalized leg definitions."""
    is_roundtrip = len(request_legs) == 2
    exclude_basic = (
        cabin == "economy"
        and not is_roundtrip
        and not include_basic_economy
    )

    result = _search_from_legs(
        request_legs,
        cabin=cabin,
        adults=adults,
        sort=sort,
        timeout=timeout,
        retries=retries,
        exclude_basic_economy=exclude_basic,
    )

    if (
        result is not None
        and is_roundtrip
        and cabin == "economy"
        and correct_roundtrip_prices
    ):
        _correct_roundtrip_economy_prices(
            result,
            include_basic_economy=include_basic_economy,
            timeout=timeout,
            retries=retries,
        )

    return result


def search_legs(
    legs: list[SearchLeg],
    *,
    cabin: str = "economy",
    adults: int = 1,
    sort: int = SORT_DEPARTURE_TIME,
    include_basic_economy: bool = False,
    timeout: int = 90,
    retries: int = 2,
) -> Optional[SearchResult]:
    """Search Google Flights using explicit leg definitions.

    Trip type is determined from ``len(legs)``: 1=one-way, 2=roundtrip.
    Per-leg ``max_stops`` and ``airlines`` come from each :class:`SearchLeg`.

    Args:
        legs: List of :class:`SearchLeg` objects (1 or 2).
        cabin: Cabin class (default ``"economy"``).
        adults: Number of adult passengers (default 1).
        sort: Sort order constant (default ``SORT_DEPARTURE_TIME``).
        include_basic_economy: Include basic economy fares (default ``False``).
        timeout: HTTP request timeout in seconds (default 90).
        retries: Number of retries on HTTP 429 (default 2).

    Returns:
        A :class:`SearchResult` or ``None`` if no results found.

    Raises:
        ValueError: If more than 2 legs provided.
    """
    _validate_leg_search_inputs(legs, cabin=cabin, adults=adults)

    request_legs = [
        _normalize_rpc_leg(
            leg.from_airport,
            leg.to_airport,
            leg.date,
            max_stops=leg.max_stops,
            airlines=list(leg.airlines) if leg.airlines else None,
        )
        for leg in legs
    ]

    return _search_with_normalized_legs(
        request_legs,
        cabin=cabin,
        adults=adults,
        sort=sort,
        include_basic_economy=include_basic_economy,
        timeout=timeout,
        retries=retries,
    )


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
    request_legs = [
        _normalize_rpc_leg(
            origin,
            destination,
            date,
            max_stops=max_stops,
            airlines=airlines,
            earliest_departure=earliest_departure,
            latest_departure=latest_departure,
            earliest_arrival=earliest_arrival,
            latest_arrival=latest_arrival,
        )
    ]
    if return_date is not None:
        request_legs.append(
            _normalize_rpc_leg(
                destination,
                origin,
                return_date,
                max_stops=max_stops,
                airlines=airlines,
                earliest_departure=return_earliest_departure,
                latest_departure=return_latest_departure,
            )
        )

    result = _search_with_normalized_legs(
        request_legs,
        cabin=cabin,
        adults=adults,
        sort=sort,
        include_basic_economy=include_basic_economy,
        timeout=timeout,
        retries=retries,
        correct_roundtrip_prices=parsed_number is None,
    )

    # When a flight_number filter is provided, filter BEFORE correcting
    # roundtrip prices. This avoids calling GetBookingResults on every
    # itinerary only to discard most of them — turning N+1 RPCs into 2.
    if parsed_number is not None:
        result = _filter_by_flight_number(result, parsed_carrier, parsed_number)
        if result is not None and return_date is not None and cabin == "economy":
            _correct_roundtrip_economy_prices(
                result,
                include_basic_economy=include_basic_economy,
                timeout=timeout,
                retries=retries,
            )

    return result


# ---------------------------------------------------------------------------
# check_price() — targeted price lookup for a known flight.
# ---------------------------------------------------------------------------


@dataclass
class SelectedLeg:
    """A leg with a specific flight selection for pricing."""
    flight_number: str
    origin: str
    destination: str
    date: str


@dataclass
class ResolvedLeg:
    """A resolved leg in a price check result."""
    flight_summary: str           # e.g. "DL 2300"
    origin: str                   # e.g. "JFK"
    destination: str              # e.g. "LAX"
    date: str                     # e.g. "2026-06-15"
    itinerary: Optional[Itinerary] = None
    selection: str = "explicit"   # "explicit" or "auto"


@dataclass
class PriceResult:
    """Result of a targeted price check for a specific flight.

    Attributes:
        price: Total price in USD (integer).
        fare_brand: Fare brand label (e.g. ``"MAIN"``, ``"BASIC"``).
        is_basic_economy: Whether the price is for basic economy.
        booking_options: All available fare tiers from GetBookingResults.
        itinerary: The matched flight itinerary (kept for backward compat).
        resolved_legs: Resolved leg details for each leg in the price check.
        rpc_calls: Number of RPC calls made (for observability).
    """
    price: int
    fare_brand: Optional[str] = None
    is_basic_economy: bool = False
    booking_options: list[BookingOption] = field(default_factory=list)
    itinerary: Optional[Itinerary] = None
    resolved_legs: list[ResolvedLeg] = field(default_factory=list)
    rpc_calls: int = 0


def _flight_summary_from_itin(itin: Optional[Itinerary]) -> str:
    """Build a compact flight summary string from an itinerary."""
    if itin is None or not itin.flights:
        return ""
    first = itin.flights[0]
    return f"{first.airline} {first.flight_number}" if first.airline else str(first.flight_number or "")


def _resolved_leg_from_itinerary(
    itinerary: Itinerary,
    *,
    origin: str,
    destination: str,
    date: str,
    selection: str,
) -> ResolvedLeg:
    """Create a resolved-leg record from an itinerary."""
    return ResolvedLeg(
        flight_summary=_flight_summary_from_itin(itinerary),
        origin=origin,
        destination=destination,
        date=date,
        itinerary=itinerary,
        selection=selection,
    )


def _price_from_outbound_itinerary(
    outbound: Itinerary,
    *,
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
    return_flight_number: Optional[str] = None,
    cabin: str = "economy",
    adults: int = 1,
    max_stops: Optional[int] = None,
    include_basic_economy: bool = False,
    timeout: int = 90,
    retries: int = 2,
    rpc_calls: int = 0,
    outbound_selection: str = "explicit",
) -> Optional[PriceResult]:
    """Resolve pricing once the outbound itinerary is already known exactly."""
    outbound_leg = _resolved_leg_from_itinerary(
        outbound,
        origin=origin,
        destination=destination,
        date=date,
        selection=outbound_selection,
    )

    if return_date is None:
        price = outbound.price
        if price is None or price <= 0:
            return None
        return PriceResult(
            price=price,
            itinerary=outbound,
            resolved_legs=[outbound_leg],
            rpc_calls=rpc_calls,
        )

    selected_outbound_legs = _build_selected_legs(outbound)
    if not selected_outbound_legs:
        return None

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

    return_selection = "auto"
    if return_flight_number is not None:
        ret_carrier, ret_number = parse_flight_number(return_flight_number)
        return_result = _filter_by_flight_number(return_result, ret_carrier, ret_number)
        if return_result is None:
            return None
        return_selection = "explicit"

    return_itin = (
        return_result.best[0] if return_result.best
        else (return_result.other[0] if return_result.other else None)
    )
    if return_itin is None:
        return None

    return_leg = _resolved_leg_from_itinerary(
        return_itin,
        origin=destination,
        destination=origin,
        date=return_date,
        selection=return_selection,
    )
    resolved = [outbound_leg, return_leg]

    try:
        options = get_booking_results(
            return_itin,
            timeout=timeout,
            retries=retries,
        )
        rpc_calls += 1
    except (SwoopHTTPError, SwoopParseError) as exc:
        logger.debug("GetBookingResults failed for roundtrip: %s", exc)
        price = return_itin.price
        if price is None or price <= 0:
            return None
        return PriceResult(
            price=price,
            itinerary=return_itin,
            resolved_legs=resolved,
            rpc_calls=rpc_calls,
        )

    if include_basic_economy:
        eligible = [o for o in options if o.price > 0]
    else:
        eligible = [o for o in options if not o.is_basic and o.price > 0]

    if not eligible:
        price = return_itin.price
        if price is None or price <= 0:
            return None
        return PriceResult(
            price=price,
            itinerary=return_itin,
            booking_options=options,
            resolved_legs=resolved,
            rpc_calls=rpc_calls,
        )

    best_option = min(eligible, key=lambda o: o.price)
    return PriceResult(
        price=best_option.price,
        fare_brand=best_option.brand_label or best_option.brand_code or None,
        is_basic_economy=best_option.is_basic,
        booking_options=options,
        itinerary=return_itin,
        resolved_legs=resolved,
        rpc_calls=rpc_calls,
    )


def price_legs(
    legs: list[SelectedLeg],
    *,
    cabin: str = "economy",
    adults: int = 1,
    include_basic_economy: bool = False,
    timeout: int = 90,
    retries: int = 2,
) -> Optional[PriceResult]:
    """Look up the current price using explicit leg definitions.

    For 1 leg: equivalent to ``check_price()`` one-way.
    For 2 legs: equivalent to ``check_price()`` roundtrip.

    Args:
        legs: List of :class:`SelectedLeg` objects (1 or 2).
        cabin: Cabin class (default ``"economy"``).
        adults: Number of adult passengers (default 1).
        include_basic_economy: Include basic economy fares (default ``False``).
        timeout: HTTP request timeout in seconds (default 90).
        retries: Number of retries on HTTP 429 (default 2).

    Returns:
        A :class:`PriceResult` or ``None`` if the flight was not found.

    Raises:
        ValueError: If more than 2 legs provided.
    """
    if len(legs) > 2:
        raise ValueError("multi-city pricing is not yet supported")
    if len(legs) == 0:
        raise ValueError("at least one leg is required")

    first = legs[0]
    if len(legs) == 2:
        second = legs[1]
        return check_price(
            first.flight_number,
            origin=first.origin,
            destination=first.destination,
            date=first.date,
            return_flight_number=second.flight_number,
            return_date=second.date,
            cabin=cabin,
            adults=adults,
            include_basic_economy=include_basic_economy,
            timeout=timeout,
            retries=retries,
        )
    else:
        return check_price(
            first.flight_number,
            origin=first.origin,
            destination=first.destination,
            date=first.date,
            cabin=cabin,
            adults=adults,
            include_basic_economy=include_basic_economy,
            timeout=timeout,
            retries=retries,
        )


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

    return _price_from_outbound_itinerary(
        outbound,
        origin=origin,
        destination=destination,
        date=date,
        return_date=return_date,
        return_flight_number=return_flight_number,
        cabin=cabin,
        adults=adults,
        max_stops=max_stops,
        include_basic_economy=include_basic_economy,
        timeout=timeout,
        retries=retries,
        rpc_calls=rpc_calls,
        outbound_selection="explicit",
    )


__all__ = [
    # Functions
    "search",
    "search_legs",
    "check_price",
    "price_legs",
    "get_booking_results",
    "search_raw",
    "parse_flight_number",
    "itinerary_matches_flight",
    # Types
    "PriceResult",
    "SearchResult",
    "SearchLeg",
    "SelectedLeg",
    "ResolvedLeg",
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
