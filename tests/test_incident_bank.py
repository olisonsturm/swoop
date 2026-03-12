"""Validate the incident regression bank contract for contributors."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parent.parent
INCIDENT_DIR = Path(__file__).parent / "incidents"
MANIFEST_PATH = INCIDENT_DIR / "manifest.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text())
ALLOWED_CATEGORIES = {
    "pricing-cabin",
    "selector-replay",
    "booking-parser",
    "decoder-degradation",
}


def test_incident_manifest_has_entries():
    assert MANIFEST["version"]
    assert MANIFEST["incidents"]


def test_incident_ids_are_unique_and_categorized():
    ids = [incident["id"] for incident in MANIFEST["incidents"]]
    assert len(ids) == len(set(ids))
    for incident in MANIFEST["incidents"]:
        assert incident["category"] in ALLOWED_CATEGORIES
        assert incident["summary"]
        assert incident["test_ref"]


def test_incident_references_exist():
    for incident in MANIFEST["incidents"]:
        test_path = ROOT / incident["test_ref"].split("::", 1)[0]
        assert test_path.exists(), f"Missing regression test file for {incident['id']}"
        fixture_path = incident.get("fixture_path")
        if fixture_path:
            assert (ROOT / fixture_path).exists(), f"Missing fixture for {incident['id']}"
