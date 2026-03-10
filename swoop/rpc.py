"""Google Flights RPC endpoint client.

Uses the internal GetShoppingResults RPC endpoint that the Google Flights
web app uses when showing "more flights." Supports time-window filtering.

Based on reverse-engineering from punitarani/fli.
"""

from copy import deepcopy
import json
import logging
import urllib.parse
from typing import Any, Optional

from ._booking import (
    _classify_fare_family,
    _extract_brand_block,
    _extract_context_tokens,
    _extract_display_price_cents_from_context,
    _extract_option_index_and_token_price_cents,
    _extract_price_block,
    _extract_segment_identity_from_context,
    _infer_rebookability_signal,
    _looks_like_brand_block,
    _looks_like_price_block,
    _normalize_attribute_vector,
    _parse_booking_rpc_response,
    _read_varint,
    _safe_get,
    _skip_wire_value,
    parse_booking_payload,
)
from .decoder import BookingOption, SearchResult, Itinerary, decode_result
from .exceptions import SwoopHTTPError, SwoopParseError, SwoopRateLimitError

logger = logging.getLogger(__name__)

SHOPPING_RPC_URL = (
    "https://www.google.com/_/FlightsFrontendUi/data/"
    "travel.frontend.flights.FlightsFrontendService/GetShoppingResults"
)
BOOKING_RPC_URL = (
    "https://www.google.com/_/FlightsFrontendUi/data/"
    "travel.frontend.flights.FlightsFrontendService/GetBookingResults"
)

# Cabin class mapping (matches Google Flights internal values)
CABIN_CLASS_MAP = {
    "economy": 1,
    "premium-economy": 2,
    "business": 3,
    "first": 4,
}

# Sort order values
SORT_TOP = 1
SORT_CHEAPEST = 2
SORT_DEPARTURE_TIME = 3
SORT_ARRIVAL_TIME = 4
SORT_DURATION = 5

# Max stops values (different from the HTML approach)
STOPS_ANY = 0
STOPS_NONSTOP = 1
STOPS_ONE_OR_FEWER = 2
STOPS_TWO_OR_FEWER = 3


def _build_filters(
    origin: str,
    destination: str,
    date: str,
    cabin: str = "economy",
    adults: int = 1,
    sort: int = SORT_TOP,
    max_stops: Optional[int] = None,
    airlines: Optional[list[str]] = None,
    earliest_departure: Optional[int] = None,
    latest_departure: Optional[int] = None,
    earliest_arrival: Optional[int] = None,
    latest_arrival: Optional[int] = None,
    return_date: Optional[str] = None,
    return_earliest_departure: Optional[int] = None,
    return_latest_departure: Optional[int] = None,
    selected_outbound_legs: Optional[list[list[Any]]] = None,
    exclude_basic_economy: bool = False,
) -> list[Any]:
    """Build nested filters payload used by shopping/booking RPC calls.

    Args:
        origin: Origin airport IATA code (e.g., "JFK")
        destination: Destination airport IATA code (e.g., "LAX")
        date: Departure date in YYYY-MM-DD format
        cabin: Cabin class (economy, premium-economy, business, first)
        adults: Number of adult passengers
        sort: Sort order (use SORT_* constants)
        max_stops: Maximum stops (None=any, 0=nonstop, 1=one stop, 2=two stops)
        airlines: List of airline codes to filter by (e.g., ["DL"])
        earliest_departure: Earliest departure hour (0-23)
        latest_departure: Latest departure hour (1-24)
        earliest_arrival: Earliest arrival hour (0-23)
        latest_arrival: Latest arrival hour (1-24)
        return_date: Return date in YYYY-MM-DD format (makes it a roundtrip search)
        return_earliest_departure: Earliest return departure hour (0-23)
        return_latest_departure: Latest return departure hour (1-24)
        selected_outbound_legs: Pre-selected outbound legs for roundtrip expansion.
            Each leg must be [dep_airport, dep_date, arr_airport, None, airline_code, flight_number].
    """
    seat_type = CABIN_CLASS_MAP.get(cabin, 1)

    # Map max_stops: our API uses None=any, 0=nonstop, 1=one, 2=two
    # RPC uses 0=any, 1=nonstop, 2=one, 3=two
    if max_stops is None:
        stops_val = STOPS_ANY
    else:
        stops_val = max_stops + 1

    # Time restrictions for outbound
    time_restrictions = None
    if any(v is not None for v in [earliest_departure, latest_departure, earliest_arrival, latest_arrival]):
        time_restrictions = [
            earliest_departure,
            latest_departure,
            earliest_arrival,
            latest_arrival,
        ]

    # Airlines filter
    airlines_filter = None
    if airlines:
        airlines_filter = sorted(airlines)

    is_roundtrip = return_date is not None
    # Trip type: 1 = roundtrip, 2 = one-way
    trip_type = 1 if is_roundtrip else 2

    # Build outbound segment
    # Airport nesting MUST be exactly 3 levels: [[[code, 0]]]
    # Using 4 levels [[[["JFK", 0]]]] silently returns zero results.
    outbound_segment = [
        [[[origin, 0]]],          # departure airport
        [[[destination, 0]]],      # arrival airport
        time_restrictions,        # time restrictions [earliest_dep, latest_dep, earliest_arr, latest_arr]
        stops_val,                # max stops
        airlines_filter,          # airlines filter
        None,                     # placeholder
        date,                     # travel date (YYYY-MM-DD)
        None,                     # max duration
        selected_outbound_legs if is_roundtrip else None,  # selected outbound flight for return expansion
        None,                     # layover airports
        None,                     # placeholder
        None,                     # placeholder
        None,                     # layover duration
        None,                     # emissions
        3,                        # constant
    ]

    segments = [outbound_segment]

    # Build return segment for roundtrip searches
    if is_roundtrip:
        return_time_restrictions = None
        if return_earliest_departure is not None or return_latest_departure is not None:
            return_time_restrictions = [
                return_earliest_departure,
                return_latest_departure,
                None,  # earliest arrival
                None,  # latest arrival
            ]

        return_segment = [
            [[[destination, 0]]],      # departure airport (reversed)
            [[[origin, 0]]],           # arrival airport (reversed)
            return_time_restrictions,  # time restrictions
            stops_val,                 # max stops (same as outbound)
            airlines_filter,           # airlines filter (same as outbound)
            None,                      # placeholder
            return_date,               # return travel date
            None,                      # max duration
            None,                      # selected flight
            None,                      # layover airports
            None,                      # placeholder
            None,                      # placeholder
            None,                      # layover duration
            None,                      # emissions
            3,                         # constant
        ]
        segments.append(return_segment)

    # Main filters structure
    filters = [
        [],                                          # empty array
        [
            None,                                    # [0] placeholder
            None,                                    # [1] placeholder
            trip_type,                               # [2] trip type (1=roundtrip, 2=one-way)
            None,                                    # [3] placeholder
            [],                                      # [4] empty array
            seat_type,                               # [5] seat type
            [adults, 0, 0, 0],                       # [6] passengers [adults, children, infants_on_lap, infants_in_seat]
            None,                                    # [7] price limit
            None,                                    # [8-12] placeholders
            None,
            None,
            None,
            None,
            segments,                                # [13] flight segments
            None,                                    # [14-16] placeholders
            None,
            None,
            1,                                       # [17] constant
            None,                                    # [18-27] placeholders
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            1 if exclude_basic_economy else None,    # [28] exclude basic economy (1=exclude, None/0=include)
        ],
        sort,                                        # sort order
        0,                                           # constant
        0,                                           # constant
        2,                                           # constant
    ]
    return filters


def _encode_f_req_payload(payload: list[Any]) -> str:
    """Encode payload to the URL-escaped `f.req` value."""
    payload_json = json.dumps(payload, separators=(",", ":"))
    wrapped = json.dumps([None, payload_json], separators=(",", ":"))
    return urllib.parse.quote(wrapped)


def _build_f_req(
    origin: str,
    destination: str,
    date: str,
    cabin: str = "economy",
    adults: int = 1,
    sort: int = SORT_TOP,
    max_stops: Optional[int] = None,
    airlines: Optional[list[str]] = None,
    earliest_departure: Optional[int] = None,
    latest_departure: Optional[int] = None,
    earliest_arrival: Optional[int] = None,
    latest_arrival: Optional[int] = None,
    return_date: Optional[str] = None,
    return_earliest_departure: Optional[int] = None,
    return_latest_departure: Optional[int] = None,
    selected_outbound_legs: Optional[list[list[Any]]] = None,
    exclude_basic_economy: bool = False,
) -> str:
    """Build the f.req body for the GetShoppingResults RPC endpoint."""
    filters = _build_filters(
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
        selected_outbound_legs=selected_outbound_legs,
        exclude_basic_economy=exclude_basic_economy,
    )
    # Encoding: JSON -> wrap in [None, json_string] -> URL-encode.
    # The double-JSON pattern (stringify, then wrap in array and stringify again)
    # mirrors how the Google Flights web app encodes its RPC requests.
    return _encode_f_req_payload(filters)


def _build_booking_f_req(
    booking_token: str,
    filter_block: list[Any],
    selected_legs: list[list[Any]],
) -> str:
    """Build the f.req body for GetBookingResults.

    The booking endpoint expects:
      [[None, booking_token], <filter_block>, None, 0]
    and requires selected legs at filter_block[13][0][8].
    """
    if not booking_token or not selected_legs:
        return ""

    payload_filter = deepcopy(filter_block)
    try:
        segments = payload_filter[13]
        if not isinstance(segments, list) or not segments or not isinstance(segments[0], list):
            return ""
        while len(segments[0]) <= 8:
            segments[0].append(None)
        segments[0][8] = selected_legs
    except (IndexError, TypeError):
        return ""

    inner = [[None, booking_token], payload_filter, None, 0]
    return _encode_f_req_payload(inner)


def _http_post(
    url: str,
    content: bytes,
    *,
    timeout: int = 90,
    retries: int = 0,
) -> Any:
    """POST with optional retry on 429 and timeout.

    Args:
        url: The URL to POST to.
        content: Request body bytes.
        timeout: Request timeout in seconds.
        retries: Number of retries on HTTP 429. Uses exponential backoff
            (1s, 2s, 4s, ...). Non-429 errors are never retried.

    Returns:
        The response object from primp.

    Raises:
        SwoopRateLimitError: If 429 persists after all retries.
        SwoopHTTPError: If a non-200/non-429 response is received.
    """
    import time

    from primp import Client

    client = Client(impersonate="chrome", verify=False)
    headers = {"content-type": "application/x-www-form-urlencoded;charset=UTF-8"}

    for attempt in range(1 + retries):
        res = client.post(url, content=content, headers=headers, timeout=timeout)
        if res.status_code == 200:
            logger.debug("HTTP 200 from %s (%d bytes)", url.split("/")[-1], len(res.text))
            return res
        if res.status_code == 429 and attempt < retries:
            delay = 2 ** attempt  # 1s, 2s, 4s, ...
            logger.info("HTTP 429 from %s, retrying in %ds (attempt %d/%d)", url.split("/")[-1], delay, attempt + 1, retries)
            time.sleep(delay)
            continue
        if res.status_code == 429:
            raise SwoopRateLimitError()
        raise SwoopHTTPError(res.status_code)


def search_raw(
    origin: str,
    destination: str,
    date: str,
    cabin: str = "economy",
    adults: int = 1,
    sort: int = SORT_DEPARTURE_TIME,
    max_stops: Optional[int] = None,
    airlines: Optional[list[str]] = None,
    earliest_departure: Optional[int] = None,
    latest_departure: Optional[int] = None,
    earliest_arrival: Optional[int] = None,
    latest_arrival: Optional[int] = None,
    return_date: Optional[str] = None,
    return_earliest_departure: Optional[int] = None,
    return_latest_departure: Optional[int] = None,
    selected_outbound_legs: Optional[list[list[Any]]] = None,
    timeout: int = 90,
    retries: int = 0,
    exclude_basic_economy: bool = False,
) -> Optional[SearchResult]:
    """Search Google Flights via RPC endpoint and return decoded results.

    Returns None if no data found. Raises on network errors.
    For roundtrip searches, provide return_date. The price in the result
    is the roundtrip total.

    Args:
        timeout: HTTP request timeout in seconds (default 90).
        retries: Number of retries on HTTP 429 with exponential backoff
            (default 0 — no retries).
    """
    logger.debug(
        "search_raw %s->%s on %s (cabin=%s, adults=%d)",
        origin, destination, date, cabin, adults,
    )

    encoded_body = _build_f_req(
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
        selected_outbound_legs=selected_outbound_legs,
        exclude_basic_economy=exclude_basic_economy,
    )

    # primp's content param requires bytes, not str — passing str silently fails
    res = _http_post(
        SHOPPING_RPC_URL,
        content=f"f.req={encoded_body}".encode(),
        timeout=timeout,
        retries=retries,
    )

    result = _parse_rpc_response(res.text)
    if result is not None and hasattr(result, "best"):
        logger.info(
            "search_raw found %d best + %d other itineraries",
            len(result.best), len(result.other),
        )
    return result


def _build_selected_legs(itinerary: Itinerary) -> list[list[Any]]:
    """Build selected legs payload from an Itinerary object.

    Simpler version of the parent project's ``_build_selected_outbound_legs``
    — no airport normalization needed since decoder outputs clean codes.
    """
    selected: list[list[Any]] = []
    for flight in itinerary.flights or []:
        dep_date = getattr(flight, "departure_date", None) or (0, 0, 0)
        if not isinstance(dep_date, (list, tuple)) or len(dep_date) < 3:
            continue
        year, month, day = dep_date[0], dep_date[1], dep_date[2]
        if not year or not month or not day:
            continue
        selected.append([
            flight.departure_airport,
            f"{year:04d}-{month:02d}-{day:02d}",
            flight.arrival_airport,
            None,
            flight.airline,
            str(flight.flight_number or ""),
        ])
    return selected


def get_booking_results(
    itinerary_or_token: Itinerary | str,
    *,
    origin: str = "",
    destination: str = "",
    date: str = "",
    cabin: str = "economy",
    adults: int = 1,
    max_stops: Optional[int] = None,
    airlines: Optional[list[str]] = None,
    earliest_departure: Optional[int] = None,
    latest_departure: Optional[int] = None,
    earliest_arrival: Optional[int] = None,
    latest_arrival: Optional[int] = None,
    selected_legs: Optional[list[list[Any]]] = None,
    registry_version: str | None = None,
    required_keys: tuple[str, ...] | None = None,
    timeout: int = 90,
    retries: int = 0,
) -> list[BookingOption]:
    """Fetch fare options (brand + price) for a specific itinerary.

    The first argument can be either an :class:`Itinerary` object (extracts
    token, origin, destination, date, and legs automatically) or a plain
    booking token string (requires explicit keyword arguments).

    Args:
        itinerary_or_token: An Itinerary object or a booking token string.
        origin: Origin airport (required if passing a token string).
        destination: Destination airport (required if passing a token string).
        date: Departure date (required if passing a token string).
        selected_legs: Flight legs (required if passing a token string).
        registry_version: If provided, set as ``registry_version`` on each option.
        required_keys: If provided, warns when any key is missing from parsed options.
        timeout: HTTP request timeout in seconds (default 90).
        retries: Number of retries on HTTP 429 (default 0).
    """
    if isinstance(itinerary_or_token, Itinerary):
        itin = itinerary_or_token
        booking_token = itin.booking_token
        if not origin:
            origin = itin.departure_airport
        if not destination:
            destination = itin.arrival_airport
        if not date:
            dep = itin.departure_date
            if dep and dep != (0, 0, 0):
                date = f"{dep[0]:04d}-{dep[1]:02d}-{dep[2]:02d}"
        if selected_legs is None:
            selected_legs = _build_selected_legs(itin)
    else:
        booking_token = itinerary_or_token

    if not booking_token or not selected_legs:
        return []

    logger.debug(
        "get_booking_results %s->%s on %s (%d legs)",
        origin, destination, date, len(selected_legs),
    )

    filters = _build_filters(
        origin=origin,
        destination=destination,
        date=date,
        cabin=cabin,
        adults=adults,
        sort=SORT_DEPARTURE_TIME,
        max_stops=max_stops,
        airlines=airlines,
        earliest_departure=earliest_departure,
        latest_departure=latest_departure,
        earliest_arrival=earliest_arrival,
        latest_arrival=latest_arrival,
    )
    filter_block = filters[1]
    encoded_body = _build_booking_f_req(booking_token, filter_block, selected_legs)
    if not encoded_body:
        return []

    res = _http_post(
        BOOKING_RPC_URL,
        content=f"f.req={encoded_body}".encode(),
        timeout=timeout,
        retries=retries,
    )

    return _parse_booking_rpc_response(
        res.text,
        registry_version=registry_version,
        required_keys=required_keys,
    )


def _parse_rpc_response(text: str) -> Optional[SearchResult]:
    """Parse the RPC response.

    Response format: `)]}'` security prefix -> strip -> JSON parse
    -> extract [0][2] -> JSON parse again -> flight data.
    The inner structure matches what decode_result() expects.
    """
    # Strip security prefix
    stripped = text.lstrip(")]}'")
    if not stripped.strip():
        return None

    try:
        outer = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise SwoopParseError(f"Failed to parse RPC response JSON: {e}") from e

    # Extract inner JSON string at [0][2]
    inner_json = None
    try:
        inner_json = outer[0][2]
    except (IndexError, TypeError):
        logger.warning("RPC response missing data at [0][2]")
        return None

    if not inner_json:
        return None

    # Inner value is a JSON string that needs to be parsed again
    try:
        data = json.loads(inner_json)
    except (json.JSONDecodeError, TypeError) as e:
        raise SwoopParseError(f"Failed to parse inner RPC response JSON: {e}") from e

    if data is None:
        return None

    return decode_result(data)
