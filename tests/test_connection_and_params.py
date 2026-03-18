"""Tests for connection reuse, country/proxy support, and passenger type propagation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import swoop._selection as selection
import swoop.rpc as rpc
from swoop.decoder import Flight, Itinerary, RawSearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_itinerary(
    *,
    origin: str = "JFK",
    destination: str = "LAX",
    date: str = "2026-06-15",
    airline: str = "DL",
    flight_number: str = "2300",
    price: int = 299,
    booking_token: str = "tok",
) -> Itinerary:
    year, month, day = [int(p) for p in date.split("-")]
    flight = Flight(
        airline=airline,
        airline_name=airline,
        flight_number=flight_number,
        departure_airport_code=origin,
        arrival_airport_code=destination,
        departure_date=(year, month, day),
        arrival_date=(year, month, day),
        departure_time=(8, 0),
        arrival_time=(11, 15),
        travel_time=195,
    )
    return Itinerary(
        airline_code=airline,
        airline_names=[airline],
        flights=[flight],
        travel_time=195,
        departure_airport_code=origin,
        arrival_airport_code=destination,
        departure_date=(year, month, day),
        arrival_date=(year, month, day),
        departure_time=(8, 0),
        arrival_time=(11, 15),
        direct_price=price,
        booking_token=booking_token,
    )


def _raw_result(*itineraries: Itinerary) -> RawSearchResult:
    return RawSearchResult(_raw=[], best=list(itineraries), other=[])


# ---------------------------------------------------------------------------
# _apply_country
# ---------------------------------------------------------------------------


class TestApplyCountry:
    def test_no_country_returns_url_unchanged(self):
        assert rpc._apply_country("https://example.com/path", None) == "https://example.com/path"

    def test_explicit_country_appends_gl(self):
        url = rpc._apply_country("https://example.com/path", "US")
        assert url == "https://example.com/path?gl=US"

    def test_country_with_existing_query_string(self):
        url = rpc._apply_country("https://example.com/path?foo=bar", "GB")
        assert url == "https://example.com/path?foo=bar&gl=GB"

    def test_default_country_used_when_explicit_is_none(self):
        old = rpc._default_country
        try:
            rpc._default_country = "JP"
            url = rpc._apply_country("https://example.com/path", None)
            assert url == "https://example.com/path?gl=JP"
        finally:
            rpc._default_country = old

    def test_explicit_country_overrides_default(self):
        old = rpc._default_country
        try:
            rpc._default_country = "JP"
            url = rpc._apply_country("https://example.com/path", "FR")
            assert url == "https://example.com/path?gl=FR"
        finally:
            rpc._default_country = old


# ---------------------------------------------------------------------------
# set_country / set_proxy
# ---------------------------------------------------------------------------


class TestSetCountry:
    def setup_method(self):
        self._old = rpc._default_country
        rpc._default_country = None

    def teardown_method(self):
        rpc._default_country = self._old

    def test_sets_uppercase(self):
        rpc.set_country("us")
        assert rpc._default_country == "US"

    def test_none_clears(self):
        rpc.set_country("US")
        rpc.set_country(None)
        assert rpc._default_country is None


class TestSetProxy:
    def setup_method(self):
        self._old_proxy = rpc._default_proxy
        self._old_clients = dict(rpc._clients)
        rpc._default_proxy = None
        rpc._clients.clear()

    def teardown_method(self):
        rpc._default_proxy = self._old_proxy
        rpc._clients.clear()
        rpc._clients.update(self._old_clients)

    def test_sets_proxy(self):
        rpc.set_proxy("socks5://host:1080")
        assert rpc._default_proxy == "socks5://host:1080"

    def test_none_clears(self):
        rpc.set_proxy("socks5://host:1080")
        rpc.set_proxy(None)
        assert rpc._default_proxy is None

    def test_evicts_only_old_default_client(self):
        # Seed two client entries: one for default (empty key), one for a per-call proxy
        rpc._clients[""] = "default-client"
        rpc._clients["socks5://other:9090"] = "other-client"
        rpc._default_proxy = None

        rpc.set_proxy("socks5://new:1080")

        # Old default ("") should be evicted, per-call client should survive
        assert "" not in rpc._clients
        assert rpc._clients["socks5://other:9090"] == "other-client"

    def test_no_op_when_same_proxy(self):
        rpc._default_proxy = "http://x:80"
        rpc._clients["http://x:80"] = "cached"
        rpc.set_proxy("http://x:80")
        # No eviction since proxy didn't change
        assert rpc._clients["http://x:80"] == "cached"


# ---------------------------------------------------------------------------
# _get_client
# ---------------------------------------------------------------------------


class TestGetClient:
    def setup_method(self):
        self._old_proxy = rpc._default_proxy
        self._old_clients = dict(rpc._clients)
        rpc._default_proxy = None
        rpc._clients.clear()

    def teardown_method(self):
        rpc._default_proxy = self._old_proxy
        rpc._clients.clear()
        rpc._clients.update(self._old_clients)

    @patch("primp.Client")
    def test_creates_client_without_proxy(self, MockClient):
        mock = MagicMock()
        MockClient.return_value = mock

        client = rpc._get_client()
        assert client is mock
        MockClient.assert_called_once_with(impersonate="chrome")

    @patch("primp.Client")
    def test_creates_client_with_proxy(self, MockClient):
        mock = MagicMock()
        MockClient.return_value = mock

        client = rpc._get_client(proxy="socks5://host:1080")
        assert client is mock
        MockClient.assert_called_once_with(impersonate="chrome", proxy="socks5://host:1080")

    @patch("primp.Client")
    def test_reuses_cached_client(self, MockClient):
        mock = MagicMock()
        MockClient.return_value = mock

        c1 = rpc._get_client()
        c2 = rpc._get_client()
        assert c1 is c2
        assert MockClient.call_count == 1

    @patch("primp.Client")
    def test_separate_clients_per_proxy(self, MockClient):
        MockClient.side_effect = [MagicMock(), MagicMock()]

        c1 = rpc._get_client(proxy=None)
        c2 = rpc._get_client(proxy="http://proxy:8080")
        assert c1 is not c2
        assert MockClient.call_count == 2

    @patch("primp.Client")
    def test_uses_default_proxy_when_explicit_is_none(self, MockClient):
        mock = MagicMock()
        MockClient.return_value = mock
        rpc._default_proxy = "http://default:3128"

        rpc._get_client(proxy=None)
        MockClient.assert_called_once_with(impersonate="chrome", proxy="http://default:3128")


# ---------------------------------------------------------------------------
# Passenger types reach the RPC payload
# ---------------------------------------------------------------------------


class TestPassengerTypePropagation:
    def test_build_filters_from_legs_includes_all_passenger_types(self):
        legs = [rpc._normalize_rpc_leg("JFK", "LAX", "2026-06-15")]
        filters = rpc._build_filters_from_legs(
            legs,
            cabin="economy",
            adults=2,
            children=1,
            infants_in_seat=1,
            infants_on_lap=1,
        )
        passengers = filters[1][6]
        assert passengers == [2, 1, 1, 1]

    def test_build_filters_from_legs_defaults_to_zero(self):
        legs = [rpc._normalize_rpc_leg("JFK", "LAX", "2026-06-15")]
        filters = rpc._build_filters_from_legs(legs, adults=1)
        passengers = filters[1][6]
        assert passengers == [1, 0, 0, 0]

    def test_search_from_legs_passes_passenger_types_to_filters(self, monkeypatch):
        """Verify _search_from_legs passes children/infants to the filter builder."""
        captured = {}

        original = rpc._build_filters_from_legs

        def spy(legs, **kwargs):
            captured.update(kwargs)
            return original(legs, **kwargs)

        monkeypatch.setattr(rpc, "_build_filters_from_legs", spy)
        monkeypatch.setattr(rpc, "_http_post", lambda *a, **kw: MagicMock(text=""))
        monkeypatch.setattr(rpc, "_parse_rpc_response", lambda text: None)

        rpc._search_from_legs(
            [rpc._normalize_rpc_leg("JFK", "LAX", "2026-06-15")],
            adults=2,
            children=1,
            infants_in_seat=1,
            infants_on_lap=1,
        )

        assert captured["children"] == 1
        assert captured["infants_in_seat"] == 1
        assert captured["infants_on_lap"] == 1

    def test_selector_round_trips_passenger_types(self):
        itin = _make_itinerary()
        request_legs = [{"origin": "JFK", "destination": "LAX", "date": "2026-06-15"}]

        selector = selection.encode_trip_selector(
            request_legs=request_legs,
            itineraries=[itin],
            cabin="economy",
            adults=2,
            children=1,
            infants_in_seat=1,
            infants_on_lap=1,
            include_basic_economy=False,
        )
        payload = selection.decode_trip_selector(selector)
        assert payload["children"] == 1
        assert payload["infants_in_seat"] == 1
        assert payload["infants_on_lap"] == 1

    def test_old_selector_without_passenger_types_defaults_to_zero(self):
        """Selectors created before passenger types should get 0 defaults."""
        itin = _make_itinerary()
        request_legs = [{"origin": "JFK", "destination": "LAX", "date": "2026-06-15"}]

        selector = selection.encode_trip_selector(
            request_legs=request_legs,
            itineraries=[itin],
            cabin="economy",
            adults=1,
            include_basic_economy=False,
        )
        payload = selection.decode_trip_selector(selector)
        # Default passenger types should be 0
        assert payload.get("children", 0) == 0
        assert payload.get("infants_in_seat", 0) == 0
        assert payload.get("infants_on_lap", 0) == 0


# ---------------------------------------------------------------------------
# Proxy propagation through _selection.py call chains
# ---------------------------------------------------------------------------


class TestProxyPropagation:
    def test_search_trip_options_passes_proxy_to_stage_searches(self, monkeypatch):
        """Verify proxy is forwarded to stage _search_from_legs calls."""
        request_legs = [
            {"origin": "JFK", "destination": "LAX", "date": "2026-06-15"},
            {"origin": "LAX", "destination": "SFO", "date": "2026-06-18"},
        ]
        outbound = _make_itinerary(origin="JFK", destination="LAX")
        onward = _make_itinerary(origin="LAX", destination="SFO", booking_token="tok2")
        call_kwargs: list[dict] = []

        def spy(legs, **kwargs):
            call_kwargs.append(kwargs)
            if len(call_kwargs) == 1:
                return _raw_result(outbound)
            return _raw_result(onward)

        monkeypatch.setattr(selection, "_search_from_legs", spy)

        selection.search_trip_options(
            request_legs,
            proxy="socks5://host:1080",
            country="US",
        )

        # Both the first pass and stage search should get proxy
        assert all(kw.get("proxy") == "socks5://host:1080" for kw in call_kwargs)
        assert all(kw.get("country") == "US" for kw in call_kwargs)

    def test_resolve_selected_trip_passes_proxy(self, monkeypatch):
        """Verify proxy is forwarded through resolve_selected_trip."""
        itin = _make_itinerary()
        call_kwargs: list[dict] = []

        def spy(*args, **kwargs):
            call_kwargs.append(kwargs)
            return _raw_result(itin)

        monkeypatch.setattr(selection, "_search_from_legs", spy)

        selection.resolve_selected_trip(
            [{"origin": "JFK", "destination": "LAX", "date": "2026-06-15"}],
            [None],
            proxy="http://proxy:8080",
            country="GB",
        )

        assert call_kwargs[0]["proxy"] == "http://proxy:8080"
        assert call_kwargs[0]["country"] == "GB"

    def test_resolve_trip_selector_passes_proxy(self, monkeypatch):
        """Verify proxy is forwarded through resolve_trip_selector."""
        itin = _make_itinerary()
        request_legs = [{"origin": "JFK", "destination": "LAX", "date": "2026-06-15"}]

        selector = selection.encode_trip_selector(
            request_legs=request_legs,
            itineraries=[itin],
            cabin="economy",
            adults=1,
            include_basic_economy=False,
        )
        call_kwargs: list[dict] = []

        def spy(legs, **kwargs):
            call_kwargs.append(kwargs)
            return _raw_result(itin)

        monkeypatch.setattr(selection, "_search_from_legs", spy)

        selection.resolve_trip_selector(
            selector,
            proxy="socks5://host:1080",
            country="JP",
        )

        assert call_kwargs[0]["proxy"] == "socks5://host:1080"
        assert call_kwargs[0]["country"] == "JP"

    def test_price_selected_trip_passes_proxy_to_booking(self, monkeypatch):
        """Verify proxy reaches fetch_trip_booking_options."""
        request_legs = [
            {"origin": "JFK", "destination": "LAX", "date": "2026-06-15"},
            {"origin": "LAX", "destination": "JFK", "date": "2026-06-20"},
        ]
        itineraries = [
            _make_itinerary(origin="JFK", destination="LAX", booking_token="t1"),
            _make_itinerary(origin="LAX", destination="JFK", booking_token="t2"),
        ]
        call_kwargs: dict = {}

        def spy(*args, **kwargs):
            call_kwargs.update(kwargs)
            return []

        monkeypatch.setattr(selection, "fetch_trip_booking_options", spy)

        selection.price_selected_trip(
            request_legs,
            itineraries,
            proxy="http://proxy:3128",
            country="DE",
        )

        assert call_kwargs["proxy"] == "http://proxy:3128"
        assert call_kwargs["country"] == "DE"

    def test_price_trip_selector_passes_proxy_end_to_end(self, monkeypatch):
        """Verify proxy flows from price_trip_selector through to all calls."""
        itin = _make_itinerary(price=299)
        request_legs = [{"origin": "JFK", "destination": "LAX", "date": "2026-06-15"}]

        selector = selection.encode_trip_selector(
            request_legs=request_legs,
            itineraries=[itin],
            cabin="economy",
            adults=1,
            include_basic_economy=False,
        )
        resolve_kwargs: list[dict] = []

        def spy_search(legs, **kwargs):
            resolve_kwargs.append(kwargs)
            return _raw_result(itin)

        monkeypatch.setattr(selection, "_search_from_legs", spy_search)

        result = selection.price_trip_selector(
            selector,
            proxy="socks5://host:1080",
            country="US",
        )

        assert resolve_kwargs[0]["proxy"] == "socks5://host:1080"
        assert resolve_kwargs[0]["country"] == "US"
        assert result is not None
        assert result.price == 299


class TestPassengerPropagation:
    def test_search_trip_options_passes_passengers_to_stage_searches(self, monkeypatch):
        """Verify children/infants propagate to stage searches."""
        request_legs = [
            {"origin": "JFK", "destination": "LAX", "date": "2026-06-15"},
            {"origin": "LAX", "destination": "SFO", "date": "2026-06-18"},
        ]
        outbound = _make_itinerary(origin="JFK", destination="LAX")
        onward = _make_itinerary(origin="LAX", destination="SFO", booking_token="tok2")
        call_kwargs: list[dict] = []

        def spy(legs, **kwargs):
            call_kwargs.append(kwargs)
            if len(call_kwargs) == 1:
                return _raw_result(outbound)
            return _raw_result(onward)

        monkeypatch.setattr(selection, "_search_from_legs", spy)

        selection.search_trip_options(
            request_legs,
            adults=2,
            children=1,
            infants_in_seat=1,
            infants_on_lap=1,
        )

        # Both first pass and stage search should get passenger types
        for kw in call_kwargs:
            assert kw["children"] == 1
            assert kw["infants_in_seat"] == 1
            assert kw["infants_on_lap"] == 1

    def test_resolve_selected_trip_passes_passengers(self, monkeypatch):
        itin = _make_itinerary()
        call_kwargs: list[dict] = []

        def spy(*args, **kwargs):
            call_kwargs.append(kwargs)
            return _raw_result(itin)

        monkeypatch.setattr(selection, "_search_from_legs", spy)

        selection.resolve_selected_trip(
            [{"origin": "JFK", "destination": "LAX", "date": "2026-06-15"}],
            [None],
            children=1,
            infants_in_seat=2,
            infants_on_lap=1,
        )

        assert call_kwargs[0]["children"] == 1
        assert call_kwargs[0]["infants_in_seat"] == 2
        assert call_kwargs[0]["infants_on_lap"] == 1
