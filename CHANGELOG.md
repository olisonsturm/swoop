# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-11

### Added

- `check_price()` — targeted price lookup for a specific flight (1 RPC one-way, 3 RPCs roundtrip)
- `PriceResult` dataclass with `price`, `fare_brand`, `is_basic_economy`, `booking_options`, `itinerary`, `resolved_legs`, `rpc_calls`
- `search_legs()` — leg-based search API accepting `list[SearchLeg]`
- `price_legs()` — leg-based pricing API accepting `list[SelectedLeg]`
- `SearchLeg`, `SelectedLeg`, `ResolvedLeg` exports
- `flight_summary` in search output (table, JSON, CSV, brief formats)
- `--price N` option on `swoop search` to drill down into search results
- `--leg` syntax for explicit leg pricing (1 or 2 legs): `swoop price --leg JFK LAX 2026-06-15 DL2300`
- Resolved flight details (aircraft, legroom, times) in price table output
- `resolved_legs` array in price JSON output
- `swoop price` CLI command with positional args: `swoop price DL2300 JFK LAX 2026-06-15`
- Roundtrip search labels prices as roundtrip totals
- Retry with exponential backoff and jitter on HTTP 429 (default `retries=2` across all RPC functions)
- Roundtrip support for `check_price()` with `return_flight_number` and `return_date`

### Removed

- **Breaking:** `search_flight()` function — use `search()` with `flight_number=` param, or `check_price()` for price lookups
- **Breaking:** `swoop flight` CLI command — use `swoop search --flight` or `swoop price`
- **Breaking:** `swoop book` CLI command — use `swoop search --price N` instead
- `format_flight_detail()`, `format_flight_json()`, `format_booking_table()`, `format_booking_json()` formatters

### Fixed

- Filter by flight number before correcting roundtrip prices (avoids unnecessary RPC calls)
- Don't filter return flights by outbound airline in `check_price()` roundtrip path
- Swap arrival airport decoder indices to match current Google Flights response format
- Remove unnecessary `verify=False` from TLS client
- Pin `protobuf>=6.31.1` to match generated code — fixes install failures on older protobuf versions ([#1](https://github.com/saraswatayu/swoop/issues/1))

### Changed

- `price` CLI command uses positional args (`FLIGHT ORIGIN DEST DATE`) instead of flags
- `search()` signature unchanged; `check_price()` now populates `resolved_legs`
- 3+ leg multi-city search/pricing remains intentionally unexposed until end-to-end validation is complete
- Narrow `except Exception` to specific swoop error types
- Rename `departure_airport`/`arrival_airport` fields to `_code` suffix for consistency
- Deduplicate internal `_safe_get` helper

## [0.2.2] - 2026-03-10

### Changed

- Rewrite README with badges, progressive disclosure, terminal screenshot, and mermaid diagram

## [0.2.1] - 2026-03-09

### Fixed

- Use itinerary-level IATA codes for route display instead of first segment codes

## [0.2.0] - 2026-03-09

### Added

- CLI with `swoop search`, `swoop flight`, and `swoop book` commands (`pip install swoop-flights[cli]`)
- Table, JSON, CSV, and brief output formats
- Cabin class, airline, time window, nonstop, and sort filters in the CLI

### Fixed

- Handle `None` values in time tuples from decoder

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
