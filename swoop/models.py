"""Public result models for staged trip search and pricing."""

from dataclasses import dataclass, field
from typing import Optional

from .decoder import BookingOption, Itinerary, PriceRange


@dataclass
class TripLeg:
    """A single requested leg paired with its resolved itinerary."""

    origin: str
    destination: str
    date: str
    itinerary: Optional[Itinerary] = None


@dataclass
class TripOption:
    """A complete trip option spanning one or more requested legs.

    ``price`` is in the currency's major unit (e.g. 250 for $250 USD,
    6725 for ₹6,725 INR). ``currency`` is the ISO 4217 code.
    """

    selector: str
    price: Optional[int] = None
    currency: Optional[str] = None
    legs: list[TripLeg] = field(default_factory=list)


@dataclass
class SearchResult:
    """Public trip-level search result."""

    results: list[TripOption] = field(default_factory=list)
    price_range: Optional[PriceRange] = None
    is_complete: bool = True
    currency: Optional[str] = None


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

    flight_summary: str
    origin: str
    destination: str
    date: str
    itinerary: Optional[Itinerary] = None
    selection: str = "explicit"


@dataclass
class PriceResult:
    """Result of a targeted price check for a specific trip.

    ``price`` is in the currency's major unit (e.g. 342 for $342 USD,
    5540 for ¥5,540 JPY). ``currency`` is the ISO 4217 code.
    """

    price: int
    currency: Optional[str] = None
    fare_brand: Optional[str] = None
    is_basic_economy: bool = False
    booking_options: list[BookingOption] = field(default_factory=list)
    itinerary: Optional[Itinerary] = None
    resolved_legs: list[ResolvedLeg] = field(default_factory=list)
    rpc_calls: int = 0
