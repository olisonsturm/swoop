"""Tests for the public swoop API (search function and package exports)."""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import patch

import pytest

import swoop
import swoop.rpc as rpc
from swoop.decoder import BookingOption, Flight, Itinerary
from swoop.exceptions import SwoopHTTPError, SwoopRateLimitError

from tests.factories import FakeHTTPResponse


def test_version():
    assert hasattr(swoop, "__version__")
    assert swoop.__version__ == "0.2.2"


def test_all_exports_importable():
    for name in swoop.__all__:
        assert hasattr(swoop, name), f"swoop.__all__ lists {name!r} but it's not importable"


def test_search_validates_cabin():
    with pytest.raises(ValueError, match="Invalid cabin"):
        swoop.search("JFK", "LAX", "2026-06-01", cabin="biz")

    with pytest.raises(ValueError, match="Invalid cabin"):
        swoop.search("JFK", "LAX", "2026-06-01", cabin="coach")


def test_search_validates_iata():
    with pytest.raises(ValueError, match="origin"):
        swoop.search("jfk", "LAX", "2026-06-01")

    with pytest.raises(ValueError, match="destination"):
        swoop.search("JFK", "la", "2026-06-01")


def test_search_validates_date():
    with pytest.raises(ValueError, match="date"):
        swoop.search("JFK", "LAX", "not-a-date")


def test_search_validates_adults():
    with pytest.raises(ValueError, match="adults"):
        swoop.search("JFK", "LAX", "2026-06-01", adults=0)


def test_search_accepts_valid_cabins(fake_primp):
    """search() should accept all valid cabin values without raising."""
    fake_primp(200, ")]}'" + json.dumps([["wrb.fr", None, "null"]]))

    for cabin in ("economy", "premium-economy", "business", "first"):
        result = swoop.search("JFK", "LAX", "2026-06-01", cabin=cabin)
        assert result is None  # null inner data -> None


def test_search_delegates_to_search_raw(monkeypatch):
    """search() should pass through all args to search_raw correctly."""
    captured = {}

    def fake_search_raw(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(swoop, "search_raw", fake_search_raw)

    swoop.search(
        "SFO", "NRT", "2026-07-01",
        return_date="2026-07-15",
        cabin="business",
        adults=2,
        max_stops=1,
        sort=swoop.SORT_CHEAPEST,
        airlines=["NH"],
        earliest_departure=8,
        latest_departure=16,
        timeout=60,
        retries=3,
    )

    assert captured["origin"] == "SFO"
    assert captured["destination"] == "NRT"
    assert captured["date"] == "2026-07-01"
    assert captured["return_date"] == "2026-07-15"
    assert captured["cabin"] == "business"
    assert captured["adults"] == 2
    assert captured["sort"] == swoop.SORT_CHEAPEST
    assert captured["max_stops"] == 1
    assert captured["airlines"] == ["NH"]
    assert captured["earliest_departure"] == 8
    assert captured["latest_departure"] == 16
    assert captured["timeout"] == 60
    assert captured["retries"] == 3


def test_search_raw_rate_limit_raises_specific_error(fake_primp):
    """429 should raise SwoopRateLimitError, not generic SwoopHTTPError."""
    fake_primp(429, "")

    with pytest.raises(SwoopRateLimitError) as exc_info:
        swoop.search("JFK", "LAX", "2026-06-01")

    assert exc_info.value.status_code == 429
    assert isinstance(exc_info.value, SwoopHTTPError)  # subclass check


def test_passengers_validation():
    """Passengers should raise ValueError, not AssertionError."""
    from swoop.builders import Passengers

    with pytest.raises(ValueError, match="Too many passengers"):
        Passengers(adults=8, children=2)

    with pytest.raises(ValueError, match="infant"):
        Passengers(adults=1, infants_on_lap=2)


def test_exception_hierarchy():
    """All exceptions should inherit from SwoopError."""
    assert issubclass(SwoopHTTPError, swoop.SwoopError)
    assert issubclass(SwoopRateLimitError, swoop.SwoopError)
    assert issubclass(swoop.SwoopParseError, swoop.SwoopError)
    assert issubclass(SwoopRateLimitError, SwoopHTTPError)


# --- BookingOption tests ---


def test_booking_option_attribute_access():
    opt = BookingOption(price=250, brand_label="Main Cabin", brand_code="MAIN")
    assert opt.price == 250
    assert opt.brand_label == "Main Cabin"
    assert opt.brand_code == "MAIN"


def test_booking_option_dict_style_access():
    opt = BookingOption(price=250, brand_label="Main Cabin", fare_family="standard")
    assert opt["price"] == 250
    assert opt["brand_label"] == "Main Cabin"
    assert opt.get("fare_family") == "standard"
    assert opt.get("nonexistent", "default") == "default"


def test_booking_option_getitem_raises_on_missing():
    opt = BookingOption()
    with pytest.raises(AttributeError):
        _ = opt["nonexistent_field"]


# --- Itinerary-based get_booking_results ---


def test_get_booking_results_with_itinerary(monkeypatch):
    """get_booking_results accepts an Itinerary object."""
    itin = Itinerary(
        departure_airport="JFK",
        arrival_airport="LAX",
        departure_date=(2026, 6, 15),
        booking_token="test-token",
        flights=[
            Flight(
                departure_airport="JFK",
                arrival_airport="LAX",
                departure_date=(2026, 6, 15),
                airline="DL",
                flight_number="123",
            ),
        ],
    )

    captured = {}

    def fake_http_post(url, content, *, timeout=90, retries=0):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["retries"] = retries
        return FakeHTTPResponse(200, ")]}'" + json.dumps([["wrb.fr", None, json.dumps([None, []])]]))

    monkeypatch.setattr(rpc, "_http_post", fake_http_post)

    result = rpc.get_booking_results(itin)
    assert result == []  # empty payload -> empty list
    assert captured["timeout"] == 90


def test_get_booking_results_string_still_works(monkeypatch):
    """Old string-based API still works."""
    result = rpc.get_booking_results("", origin="JFK", destination="LAX", date="2026-06-15", selected_legs=[])
    assert result == []

    result = rpc.get_booking_results("token", origin="JFK", destination="LAX", date="2026-06-15", selected_legs=None)
    assert result == []


def test_build_selected_legs():
    itin = Itinerary(
        flights=[
            Flight(
                departure_airport="JFK",
                arrival_airport="ORD",
                departure_date=(2026, 6, 15),
                airline="AA",
                flight_number="100",
            ),
            Flight(
                departure_airport="ORD",
                arrival_airport="LAX",
                departure_date=(2026, 6, 15),
                airline="AA",
                flight_number="200",
            ),
        ],
    )
    legs = rpc._build_selected_legs(itin)
    assert len(legs) == 2
    assert legs[0] == ["JFK", "2026-06-15", "ORD", None, "AA", "100"]
    assert legs[1] == ["ORD", "2026-06-15", "LAX", None, "AA", "200"]


def test_build_selected_legs_skips_bad_dates():
    itin = Itinerary(
        flights=[
            Flight(departure_airport="JFK", arrival_airport="LAX", departure_date=(0, 0, 0)),
        ],
    )
    assert rpc._build_selected_legs(itin) == []


# --- Retry tests ---


def test_http_post_retries_on_429(monkeypatch):
    """_http_post retries on 429 with backoff."""
    call_count = 0

    class FakeClient:
        def __init__(self, **_kw):
            pass
        def post(self, *_a, **_kw):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return FakeHTTPResponse(429, "ok")
            return FakeHTTPResponse(200, "ok")

    monkeypatch.setitem(sys.modules, "primp", types.SimpleNamespace(Client=FakeClient))
    monkeypatch.setattr("time.sleep", lambda _: None)  # skip actual sleep

    res = rpc._http_post("http://test", b"body", timeout=10, retries=3)
    assert res.status_code == 200
    assert call_count == 3


def test_http_post_raises_after_exhausting_retries(fake_primp, monkeypatch):
    """_http_post raises SwoopRateLimitError after all retries fail."""
    fake_primp(429, "")
    monkeypatch.setattr("time.sleep", lambda _: None)

    with pytest.raises(SwoopRateLimitError):
        rpc._http_post("http://test", b"body", timeout=10, retries=2)


def test_http_post_no_retry_on_non_429(monkeypatch):
    """Non-429 errors are raised immediately, never retried."""
    call_count = 0

    class FakeClient:
        def __init__(self, **_kw):
            pass
        def post(self, *_a, **_kw):
            nonlocal call_count
            call_count += 1
            return FakeHTTPResponse(503, "")

    monkeypatch.setitem(sys.modules, "primp", types.SimpleNamespace(Client=FakeClient))

    with pytest.raises(SwoopHTTPError, match="HTTP 503"):
        rpc._http_post("http://test", b"body", timeout=10, retries=3)
    assert call_count == 1


def test_http_post_passes_timeout(monkeypatch):
    """timeout is passed through to primp."""
    captured_kwargs = {}

    class FakeClient:
        def __init__(self, **_kw):
            pass
        def post(self, *_a, **kwargs):
            captured_kwargs.update(kwargs)
            return FakeHTTPResponse(200, "ok")

    monkeypatch.setitem(sys.modules, "primp", types.SimpleNamespace(Client=FakeClient))

    rpc._http_post("http://test", b"body", timeout=45)
    assert captured_kwargs["timeout"] == 45
