"""Shared pytest fixtures for swoop tests."""
from __future__ import annotations

import sys
import types

import pytest

from tests.factories import FakeHTTPResponse


@pytest.fixture
def fake_primp(monkeypatch):
    """Patch primp.Client to return canned responses.

    Usage:
        def test_something(fake_primp):
            fake_primp(200, "response body")
            # now primp.Client().post() returns FakeHTTPResponse(200, "response body")
    """
    def _install(status_code=200, text=""):
        response = FakeHTTPResponse(status_code, text)
        class FakeClient:
            def __init__(self, **_kw):
                pass
            def post(self, *_a, **_kw):
                return response
        monkeypatch.setitem(sys.modules, "primp", types.SimpleNamespace(Client=FakeClient))
        return response
    return _install
