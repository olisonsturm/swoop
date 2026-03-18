"""Typed protobuf payload builders for Google Flights RPC requests.

Constructs the serialized protobuf payloads used in the ?tfs= query parameter
and decodes ItinerarySummary responses. Uses string IATA codes directly
(no Airport enum dependency).
"""

import base64
from dataclasses import dataclass
from typing import List, Literal, Optional, Union

from . import flights_pb2 as PB

AIRLINE_ALLIANCES = ["SKYTEAM", "STAR_ALLIANCE", "ONEWORLD"]


class SearchLeg:
    """A search leg defining origin, destination, date, and optional filters.

    Each search has one leg (one-way) or two legs (roundtrip). This class
    builds the per-leg protobuf data used in the ``?tfs=`` query parameter.

    Args:
        date: Departure date (YYYY-MM-DD).
        from_airport: Origin IATA code.
        to_airport: Destination IATA code.
        max_stops: Maximum number of stops. None = any.
        airlines: Filter to these airline IATA codes.
    """

    __slots__ = ("date", "from_airport", "to_airport", "max_stops", "airlines")

    def __init__(
        self,
        *,
        date: str,
        from_airport: str,
        to_airport: str,
        max_stops: Optional[int] = None,
        airlines: Optional[List[str]] = None,
    ):
        self.date = date
        self.from_airport = from_airport.upper()
        self.to_airport = to_airport.upper()
        self.max_stops = max_stops

        if airlines is not None:
            self.airlines = []
            for airline in airlines:
                airline = airline.upper()
                if not (len(airline) == 2 or airline in AIRLINE_ALLIANCES):
                    raise ValueError(
                        f"Invalid airline code: {airline}. "
                        f"Must be 2-char IATA code or alliance: {AIRLINE_ALLIANCES}"
                    )
                self.airlines.append(airline)
        else:
            self.airlines = None

    def apply_to(self, info) -> None:
        data = info.data.add()
        data.date = self.date
        data.from_flight.airport = self.from_airport
        data.to_flight.airport = self.to_airport
        if self.max_stops is not None:
            data.max_stops = self.max_stops
        if self.airlines is not None:
            data.airlines.extend(self.airlines)


class Passengers:
    def __init__(
        self,
        *,
        adults: int = 1,
        children: int = 0,
        infants_in_seat: int = 0,
        infants_on_lap: int = 0,
    ):
        total = adults + children + infants_in_seat + infants_on_lap
        if total > 9:
            raise ValueError(f"Too many passengers ({total} > 9 max)")
        if infants_on_lap > adults:
            raise ValueError(
                f"Need at least one adult per infant on lap "
                f"({infants_on_lap} infants but only {adults} adults)"
            )

        self.pb = []
        self.pb += [PB.Passenger.ADULT for _ in range(adults)]
        self.pb += [PB.Passenger.CHILD for _ in range(children)]
        self.pb += [PB.Passenger.INFANT_IN_SEAT for _ in range(infants_in_seat)]
        self.pb += [PB.Passenger.INFANT_ON_LAP for _ in range(infants_on_lap)]

    def apply_to(self, info) -> None:
        for p in self.pb:
            info.passengers.append(p)


class TFSData:
    """Builds the ``?tfs=`` query parameter for Google Flights URL.

    TFS (Travel Flight Search) is the parameter name Google Flights uses
    in its URL to encode the serialized protobuf search request.
    """

    def __init__(
        self,
        *,
        flight_data: List[SearchLeg],
        seat: int,
        trip: int,
        passengers: Passengers,
        max_stops: Optional[int] = None,
        exclude_basic_economy: bool = False,
    ):
        self.flight_data = flight_data
        self.seat = seat
        self.trip = trip
        self.passengers = passengers
        self.max_stops = max_stops
        self.exclude_basic_economy = exclude_basic_economy

    def pb(self):
        info = PB.Info()
        info.seat = self.seat
        info.trip = self.trip
        self.passengers.apply_to(info)

        for fd in self.flight_data:
            fd.apply_to(info)

        if self.max_stops is not None:
            for flight in info.data:
                flight.max_stops = self.max_stops

        if self.exclude_basic_economy:
            info.exclude_basic_economy = True

        return info

    def to_string(self) -> bytes:
        return self.pb().SerializeToString()

    def as_b64(self) -> bytes:
        return base64.b64encode(self.to_string())

    @staticmethod
    def from_interface(
        *,
        flight_data: List[SearchLeg],
        trip: Literal["round-trip", "one-way", "multi-city"],
        passengers: Passengers,
        seat: Literal["economy", "premium-economy", "business", "first"],
        max_stops: Optional[int] = None,
        exclude_basic_economy: bool = False,
    ) -> "TFSData":
        trip_t = {
            "round-trip": PB.Trip.ROUND_TRIP,
            "one-way": PB.Trip.ONE_WAY,
            "multi-city": PB.Trip.MULTI_CITY,
        }[trip]
        seat_t = {
            "economy": PB.Seat.ECONOMY,
            "premium-economy": PB.Seat.PREMIUM_ECONOMY,
            "business": PB.Seat.BUSINESS,
            "first": PB.Seat.FIRST,
        }[seat]
        return TFSData(
            flight_data=flight_data,
            seat=seat_t,
            trip=trip_t,
            passengers=passengers,
            max_stops=max_stops,
            exclude_basic_economy=exclude_basic_economy,
        )


# Currencies where Google deviates from ISO 4217 precision.
# Google sends these as whole major units despite ISO saying they have
# 2 decimal places. Confirmed via live API captures.
_GOOGLE_PRECISION_OVERRIDES = {
    "INR": 0,  # ISO says 2 (paise), but Google sends whole rupees
}


def _currency_divisor(currency: str) -> int:
    """Return the divisor to convert Google's protobuf price to major unit.

    Uses babel's ISO 4217 currency precision (e.g. USD=2 → 10^2=100,
    JPY=0 → 10^0=1), with overrides for currencies where Google deviates
    from the standard.
    """
    if currency in _GOOGLE_PRECISION_OVERRIDES:
        return 10 ** _GOOGLE_PRECISION_OVERRIDES[currency]
    try:
        from babel.numbers import get_currency_precision
        return 10 ** get_currency_precision(currency)
    except Exception:
        return 100  # safe fallback if babel unavailable


@dataclass
class ItinerarySummary:
    """Decoded price data from a Google Flights itinerary summary token.

    The ``price`` field is in the response currency's major unit.
    ``currency`` is the 3-letter ISO 4217 code.
    """

    flights: str
    price: float
    currency: str

    @classmethod
    def from_b64(cls, b64_string: str) -> "ItinerarySummary":
        try:
            raw = base64.b64decode(b64_string)
            pb = PB.ItinerarySummary()
            pb.ParseFromString(raw)
            divisor = _currency_divisor(pb.price.currency)
            return cls(pb.flights, pb.price.price / divisor, pb.price.currency)
        except Exception:
            return cls("", 0, "USD")
