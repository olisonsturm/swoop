# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-11

### Added

- `check_price()` — targeted price lookup for a specific flight (1 RPC one-way, 3 RPCs roundtrip)
- `PriceResult` dataclass with `price`, `fare_brand`, `is_basic_economy`, `booking_options`, `itinerary`, `rpc_calls`
- `swoop price` CLI command for quick price checks from the terminal
- Retry with exponential backoff and jitter on HTTP 429 (default `retries=2` across all RPC functions)
- Roundtrip support for `check_price()` with `return_flight_number` and `return_date`

### Removed

- **Breaking:** `search_flight()` function — use `search()` with `flight_number=` param, or `check_price()` for price lookups
- **Breaking:** `swoop flight` CLI command — use `swoop search --flight` or `swoop price`
- `format_flight_detail()` and `format_flight_json()` formatters

### Fixed

- Filter by flight number before correcting roundtrip prices (avoids unnecessary RPC calls)
- Don't filter return flights by outbound airline in `check_price()` roundtrip path
- Swap arrival airport decoder indices to match current Google Flights response format
- Remove unnecessary `verify=False` from TLS client

### Changed

- Narrow `except Exception` to specific swoop error types
- Rename `departure_airport`/`arrival_airport` fields to `_code` suffix for consistency
- Deduplicate internal `_safe_get` helper

## [0.1.0] - 2026-03-09

### Added

- `search()` — high-level entry point with cabin class, airline, time window, and stop filters
- `search_flight()` — convenience wrapper to find a specific flight by number
- `search_raw()` — low-level RPC access to `GetShoppingResults`
- `get_booking_results()` — fetch fare tiers (`BookingOption`) for a specific itinerary
- Roundtrip search with automatic price correction via `GetBookingResults`
- Basic economy exclusion: one-way uses RPC-level filter, roundtrip uses booking results
- `Itinerary.price` property — canonical price preferring `direct_price` over protobuf-decoded price
- Typed dataclasses: `SearchResult`, `Itinerary`, `Flight`, `BookingOption`, `Layover`, `Codeshare`, `CarbonEmissions`, `PriceRange`, `AmenityFlags`, `QualitySignals`
- Exception hierarchy: `SwoopError` → `SwoopHTTPError` → `SwoopRateLimitError`, `SwoopParseError`
- Input validation with optional `airportsdata` for IATA code checking (`pip install swoop-flights[validation]`)
- Retry with exponential backoff on HTTP 429
- Sort and stop filter constants (`SORT_CHEAPEST`, `STOPS_NONSTOP`, etc.)
- Flight number parsing and itinerary matching (`parse_flight_number`, `itinerary_matches_flight`)
- Carbon emissions, legroom, amenity flags, and quality signal decoding
- Frozen API surface tests to catch accidental breaking changes
