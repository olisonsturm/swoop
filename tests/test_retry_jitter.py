"""Tests for retry with jitter defaults."""

import inspect

import swoop
import swoop.rpc


class TestRetryDefaults:
    """Verify all RPC functions default to retries=2."""

    def test_http_post_default_retries(self):
        sig = inspect.signature(swoop.rpc._http_post)
        assert sig.parameters["retries"].default == 2

    def test_search_raw_default_retries(self):
        sig = inspect.signature(swoop.search_raw)
        assert sig.parameters["retries"].default == 2

    def test_get_booking_results_default_retries(self):
        sig = inspect.signature(swoop.get_booking_results)
        assert sig.parameters["retries"].default == 2

    def test_search_default_retries(self):
        sig = inspect.signature(swoop.search)
        assert sig.parameters["retries"].default == 2
