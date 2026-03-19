"""Tests for retry with jitter defaults."""

import inspect

import swoop
import swoop.rpc
from swoop.models import TransportConfig


class TestRetryDefaults:
    """Verify all RPC functions default to TransportConfig with retries=2."""

    def test_http_post_default_transport_retries(self):
        sig = inspect.signature(swoop.rpc._http_post)
        assert sig.parameters["transport"].default.retries == 2

    def test_search_raw_default_transport_retries(self):
        sig = inspect.signature(swoop.search_raw)
        assert sig.parameters["transport"].default.retries == 2

    def test_get_booking_results_default_transport_retries(self):
        sig = inspect.signature(swoop.get_booking_results)
        assert sig.parameters["transport"].default.retries == 2

    def test_search_default_transport_retries(self):
        sig = inspect.signature(swoop.search)
        assert sig.parameters["transport"].default.retries == 2
