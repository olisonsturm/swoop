"""Golden file tests for non-USD currency responses.

These fixtures were captured from live Google Flights API calls with
different country codes. They verify that currency detection, protobuf
decoding, and the Itinerary.currency property work correctly with real
response data.
"""

import json
from pathlib import Path

import pytest

from swoop.decoder import decode_result


FIXTURES = Path(__file__).parent / "fixtures" / "responses"


def _load_fixture(name: str) -> list:
    with open(FIXTURES / name) as f:
        return json.load(f)


class TestGoldenGBP:
    """LHR->EDI with country=GB — prices in GBP."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.result = decode_result(_load_fixture("shopping_oneway_gb.json"))

    def test_has_results(self):
        all_itins = self.result.best + self.result.other
        assert len(all_itins) >= 1

    def test_currency_is_gbp(self):
        for itin in self.result.best + self.result.other:
            if itin.price_info:
                assert itin.price_info.currency == "GBP"

    def test_itinerary_currency_property(self):
        itin = (self.result.best + self.result.other)[0]
        assert itin.currency == "GBP"

    def test_prices_are_sane_gbp(self):
        """GBP domestic flights should be roughly £30-£600."""
        for itin in self.result.best + self.result.other:
            if itin.price is not None:
                assert 10 <= itin.price <= 2000, f"GBP price {itin.price} out of range"

    def test_direct_price_matches_protobuf(self):
        """direct_price and rounded protobuf price should be within £1."""
        for itin in self.result.best + self.result.other:
            if itin.direct_price is not None and itin.price_info is not None:
                assert abs(itin.direct_price - round(itin.price_info.price)) <= 1


class TestGoldenJPY:
    """NRT->KIX with country=JP — prices in JPY (zero-decimal)."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.result = decode_result(_load_fixture("shopping_oneway_jp.json"))

    def test_has_results(self):
        all_itins = self.result.best + self.result.other
        assert len(all_itins) >= 1

    def test_currency_is_jpy(self):
        for itin in self.result.best + self.result.other:
            if itin.price_info:
                assert itin.price_info.currency == "JPY"

    def test_itinerary_currency_property(self):
        itin = (self.result.best + self.result.other)[0]
        assert itin.currency == "JPY"

    def test_prices_are_sane_jpy(self):
        """JPY domestic flights should be roughly ¥3,000-¥80,000."""
        for itin in self.result.best + self.result.other:
            if itin.price is not None:
                assert 1000 <= itin.price <= 200000, f"JPY price {itin.price} out of range"

    def test_protobuf_price_matches_direct(self):
        """With currency-aware divisor, protobuf price should match direct_price within ¥1."""
        for itin in self.result.best + self.result.other:
            if itin.direct_price is not None and itin.price_info is not None:
                assert abs(itin.direct_price - round(itin.price_info.price)) <= 1, (
                    f"direct_price={itin.direct_price} vs pb_price={itin.price_info.price}"
                )


class TestGoldenINR:
    """DEL->BOM with country=IN — prices in INR."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.result = decode_result(_load_fixture("shopping_oneway_in.json"))

    def test_has_results(self):
        all_itins = self.result.best + self.result.other
        assert len(all_itins) >= 1

    def test_currency_is_inr(self):
        for itin in self.result.best + self.result.other:
            if itin.price_info and itin.price_info.currency:
                assert itin.price_info.currency == "INR"

    def test_itinerary_currency_property(self):
        itin = (self.result.best + self.result.other)[0]
        assert itin.currency == "INR"

    def test_prices_are_sane_inr(self):
        """INR domestic flights should be roughly ₹2,000-₹50,000."""
        for itin in self.result.best + self.result.other:
            if itin.price is not None and itin.price > 0:
                assert 1000 <= itin.price <= 100000, f"INR price {itin.price} out of range"

    def test_direct_price_matches_protobuf(self):
        """direct_price and rounded protobuf price should be within ₹1."""
        for itin in self.result.best + self.result.other:
            if itin.direct_price is not None and itin.price_info is not None and itin.price_info.price > 0:
                assert abs(itin.direct_price - round(itin.price_info.price)) <= 1
