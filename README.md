# swoop

Google Flights price scraper. Search flights programmatically using the same RPC endpoints the Google Flights web app uses.

```python
from swoop import search

results = search("JFK", "LAX", "2026-06-01")
for flight in results.best:
    airline = ", ".join(flight.airline_names)
    print(f"${flight.price} — {airline}")
```

## Install

```bash
pip install swoop-flights
```

## Usage

### One-way search

```python
from swoop import search

results = search("SFO", "JFK", "2026-06-15")

# results.best  — top-ranked flights
# results.other — remaining flights
for flight in results.best:
    print(f"${flight.price}")
    print(f"  {flight.departure_airport} → {flight.arrival_airport}")
    print(f"  {flight.airline_names}, {flight.stop_count} stops")
    print(f"  {flight.travel_time} min total")
```

### Roundtrip search

```python
results = search("SFO", "JFK", "2026-06-15", return_date="2026-06-22")
# Price in results is the roundtrip total
```

### Cabin class and filters

```python
from swoop import search, SORT_CHEAPEST

results = search(
    "LAX", "NRT", "2026-06-15",
    cabin="business",       # economy, premium-economy, business, first
    max_stops=0,            # nonstop only
    sort=SORT_CHEAPEST,     # cheapest first
    airlines=["NH", "JL"],  # filter to specific carriers
)
```

### Time window filtering

```python
results = search(
    "JFK", "LHR", "2026-06-15",
    earliest_departure=8,   # depart after 8am
    latest_departure=14,    # depart before 2pm
)
```

### Booking details (fare options)

```python
from swoop import search, get_booking_results

results = search("JFK", "LAX", "2026-06-15")
itinerary = results.best[0]

# Get fare tiers — just pass the itinerary
options = get_booking_results(itinerary)

for opt in options:
    print(f"${opt.price} — {opt.brand_label} ({opt.fare_family})")
```

You can also pass a booking token string with explicit parameters:

```python
options = get_booking_results(
    itinerary.booking_token,
    origin="JFK",
    destination="LAX",
    date="2026-06-15",
    selected_legs=[
        [
            flight.departure_airport,
            f"{flight.departure_date[0]}-{flight.departure_date[1]:02d}-{flight.departure_date[2]:02d}",
            flight.arrival_airport,
            None,
            flight.airline,
            flight.flight_number,
        ]
        for flight in itinerary.flights
    ],
)
```

### Retry and timeout

```python
# Retry up to 3 times on HTTP 429 (rate limit) with exponential backoff
results = search("JFK", "LAX", "2026-06-15", retries=3, timeout=90)

# Same for booking results
options = get_booking_results(itinerary, retries=2, timeout=60)
```

### Flight details

Each `Itinerary` contains detailed segment data:

```python
results = search("JFK", "LAX", "2026-06-15")
for itinerary in results.best:
    for flight in itinerary.flights:
        print(f"{flight.airline} {flight.flight_number}")
        print(f"  {flight.departure_airport} → {flight.arrival_airport}")
        print(f"  Aircraft: {flight.aircraft}")
        print(f"  Legroom: {flight.legroom}")
        if flight.co2_grams:
            print(f"  CO₂: {flight.co2_grams}g")

    if itinerary.carbon_emissions:
        ce = itinerary.carbon_emissions
        print(f"  Route emissions: {ce.difference_percent}% vs typical")

    if results.price_range:
        print(f"  Price range: ${results.price_range.low}–${results.price_range.high}")
```

## Error handling

```python
from swoop import search, SwoopHTTPError, SwoopRateLimitError, SwoopParseError

try:
    results = search("JFK", "LAX", "2026-06-15")
except SwoopRateLimitError:
    print("Rate limited — wait a few minutes")
except SwoopHTTPError as e:
    print(f"HTTP {e.status_code}")
except SwoopParseError as e:
    print(f"Parse error: {e}")
```

## API reference

### `search(origin, destination, date, **kwargs)`

Search Google Flights and return a `SearchResult`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `origin` | `str` | required | Origin IATA code |
| `destination` | `str` | required | Destination IATA code |
| `date` | `str` | required | Departure date (`YYYY-MM-DD`) |
| `return_date` | `str \| None` | `None` | Return date for roundtrip |
| `cabin` | `str` | `"economy"` | `economy`, `premium-economy`, `business`, `first` |
| `adults` | `int` | `1` | Number of adults |
| `max_stops` | `int \| None` | `None` | `None`=any, `0`=nonstop, `1`=1 stop, `2`=2 stops |
| `sort` | `int` | `SORT_DEPARTURE_TIME` | Sort order constant |
| `airlines` | `list[str] \| None` | `None` | Filter by airline codes |
| `include_basic_economy` | `bool` | `False` | Include basic economy fares |
| `timeout` | `int` | `90` | HTTP timeout in seconds |
| `retries` | `int` | `0` | Retries on HTTP 429 with exponential backoff |

Returns `SearchResult | None`. `None` means no results found.

### `get_booking_results(itinerary_or_token, **kwargs)`

Get fare options for a specific itinerary. Pass an `Itinerary` object directly, or a booking token string with explicit `origin`, `destination`, `date`, and `selected_legs`. Returns `list[BookingOption]` with `price`, `brand_label`, `brand_code`, `fare_family`, etc. `BookingOption` supports both attribute access (`opt.price`) and dict-style access (`opt["price"]`, `opt.get("price")`).

### Result types

- **`SearchResult`** — `best: list[Itinerary]`, `other: list[Itinerary]`, `price_range: PriceRange | None`
- **`Itinerary`** — Full itinerary with `price`, `flights`, `layovers`, `travel_time`, `booking_token`, `carbon_emissions`
- **`Flight`** — Segment details: `airline`, `flight_number`, `aircraft`, `legroom`, `co2_grams`, `amenities`
- **`Layover`** — Stop info: `minutes`, airports, `is_overnight`
- **`CarbonEmissions`** — `this_flight_grams`, `typical_for_route_grams`, `difference_percent`

### Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `SORT_TOP` | `1` | Google's default ranking |
| `SORT_CHEAPEST` | `2` | Cheapest first |
| `SORT_DEPARTURE_TIME` | `3` | By departure time |
| `SORT_ARRIVAL_TIME` | `4` | By arrival time |
| `SORT_DURATION` | `5` | Shortest first |

## Pricing notes

Use `itinerary.price` to get the USD price as an integer.

By default, `search()` excludes basic economy fares so prices reflect Main Cabin. Pass `include_basic_economy=True` to include them:

```python
results = search("JFK", "LAX", "2026-06-15", include_basic_economy=True)
```

## How it works

Swoop uses Google Flights' internal `GetShoppingResults` and `GetBookingResults` RPC endpoints — the same ones the web app calls when you search for flights. Requests are serialized as nested JSON payloads and sent via HTTP POST with browser impersonation (via [primp](https://github.com/deedy5/primp)).

Responses are decoded from nested list structures into typed Python dataclasses.

## Dependencies

- **[primp](https://github.com/deedy5/primp)** — HTTP client with browser TLS impersonation
- **[protobuf](https://pypi.org/project/protobuf/)** — Protocol buffer serialization

## License

MIT
