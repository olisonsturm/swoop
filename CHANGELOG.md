# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
