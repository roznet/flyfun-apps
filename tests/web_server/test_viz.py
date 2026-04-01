"""Tests for the visualization payload store (web/server/api/viz.py).

Unit tests for the store functions + integration tests via FastAPI TestClient.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure web/server is importable
_server_dir = Path(__file__).resolve().parents[2] / "web" / "server"
if str(_server_dir) not in sys.path:
    sys.path.insert(0, str(_server_dir))

from api.viz import (
    _store,
    get_payload,
    store_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_store():
    """Ensure a clean store for every test."""
    _store.clear()
    yield
    _store.clear()


SAMPLE_PAYLOAD = {
    "tool": "find_airports_near_location",
    "visualization": {"type": "point_with_markers", "center": {"lat": 45.7, "lon": 4.9}},
    "highlights": [{"ident": "LFLL", "name": "Lyon", "lat": 45.7, "lon": 4.9}],
}


# ---------------------------------------------------------------------------
# Unit tests: store functions
# ---------------------------------------------------------------------------

def test_store_and_retrieve():
    """Round-trip: store a payload, retrieve it by key."""
    key = store_payload(SAMPLE_PAYLOAD)
    assert isinstance(key, str)
    assert len(key) == 8
    assert get_payload(key) == SAMPLE_PAYLOAD


def test_deterministic_key():
    """Same payload always produces the same key."""
    k1 = store_payload(SAMPLE_PAYLOAD)
    k2 = store_payload(SAMPLE_PAYLOAD)
    assert k1 == k2


def test_different_payloads_different_keys():
    k1 = store_payload({"a": 1})
    k2 = store_payload({"b": 2})
    assert k1 != k2


def test_missing_key_returns_none():
    assert get_payload("deadbeef") is None


def test_expired_entry_returns_none():
    """Entries past TTL are evicted on read."""
    key = store_payload(SAMPLE_PAYLOAD)
    # Backdate the timestamp past TTL
    payload, _ = _store[key]
    _store[key] = (payload, time.time() - 25 * 3600)
    assert get_payload(key) is None
    assert key not in _store


def test_evict_expired_on_store():
    """Expired entries are cleaned up when storing new ones."""
    old_key = store_payload({"old": True})
    payload, _ = _store[old_key]
    _store[old_key] = (payload, time.time() - 25 * 3600)

    store_payload({"new": True})
    assert old_key not in _store


def test_evict_lru_when_over_capacity():
    """When store exceeds _MAX_ENTRIES, oldest 50% are dropped."""
    with patch("api.viz._MAX_ENTRIES", 10):
        # Fill past capacity
        for i in range(11):
            store_payload({"i": i})
        # 11 unique payloads stored, eviction should have trimmed
        assert len(_store) <= 11
        # Store one more — eviction runs at start of store_payload
        store_payload({"i": "final"})
        assert len(_store) < 11


# ---------------------------------------------------------------------------
# Integration tests: FastAPI endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app, base_url="http://localhost:8000")


def test_post_and_get_payload(client):
    """POST a payload, then GET it back by key."""
    resp = client.post("/api/viz", json={"payload": SAMPLE_PAYLOAD})
    assert resp.status_code == 200
    key = resp.json()["key"]
    assert isinstance(key, str) and len(key) == 8

    resp = client.get(f"/api/viz/{key}")
    assert resp.status_code == 200
    assert resp.json() == SAMPLE_PAYLOAD


def test_get_missing_key_404(client):
    resp = client.get("/api/viz/00000000")
    assert resp.status_code == 404


def test_get_invalid_key_400(client):
    resp = client.get("/api/viz/" + "a" * 17)
    assert resp.status_code == 400


def test_viz_shortlink_serves_spa(client):
    """GET /v/{key} serves the SPA (index.html), not the raw payload."""
    key = store_payload(SAMPLE_PAYLOAD)
    resp = client.get(f"/v/{key}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_post_then_shortlink_roundtrip(client):
    """Full flow: POST payload → get key → /v/{key} serves SPA → /api/viz/{key} returns data."""
    # MCP server POSTs payload
    resp = client.post("/api/viz", json={"payload": SAMPLE_PAYLOAD})
    key = resp.json()["key"]

    # Frontend loads SPA at /v/{key}
    resp = client.get(f"/v/{key}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]

    # Frontend fetches payload from API
    resp = client.get(f"/api/viz/{key}")
    assert resp.status_code == 200
    assert resp.json()["visualization"]["type"] == "point_with_markers"
