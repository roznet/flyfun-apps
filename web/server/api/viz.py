"""
Visualization payload store.

Short-lived, in-memory store that maps opaque keys to visualization payloads.
The MCP server POSTs a payload and gets back a key; the frontend GETs
``/api/viz/{key}`` to retrieve and display it.

No persistence — payloads are ephemeral session artifacts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory store with TTL
# ---------------------------------------------------------------------------

_MAX_ENTRIES = 10_000
_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# {key: (payload_dict, created_at_epoch)}
_store: Dict[str, tuple[Dict[str, Any], float]] = {}


def _evict_expired() -> None:
    """Remove entries older than TTL."""
    now = time.time()
    expired = [k for k, (_, ts) in _store.items() if now - ts > _TTL_SECONDS]
    for k in expired:
        del _store[k]


def _evict_lru() -> None:
    """If over capacity, drop oldest 50%."""
    if len(_store) <= _MAX_ENTRIES:
        return
    sorted_keys = sorted(_store, key=lambda k: _store[k][1])
    for k in sorted_keys[: len(sorted_keys) // 2]:
        del _store[k]


def store_payload(payload: Dict[str, Any]) -> str:
    """Store a payload and return its key (8-char hex digest)."""
    _evict_expired()
    _evict_lru()

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(raw.encode()).hexdigest()[:8]
    _store[key] = (payload, time.time())
    return key


def get_payload(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve a payload by key, or None if expired/missing."""
    entry = _store.get(key)
    if entry is None:
        return None
    payload, ts = entry
    if time.time() - ts > _TTL_SECONDS:
        del _store[key]
        return None
    return payload


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class VizStoreRequest(BaseModel):
    payload: Dict[str, Any]


class VizStoreResponse(BaseModel):
    key: str


@router.post("", response_model=VizStoreResponse)
def create_viz(req: VizStoreRequest) -> VizStoreResponse:
    """Store a visualization payload and return its key."""
    key = store_payload(req.payload)
    logger.debug("Stored viz payload: key=%s", key)
    return VizStoreResponse(key=key)


@router.get("/{key}")
def get_viz(key: str) -> Dict[str, Any]:
    """Retrieve a stored visualization payload."""
    if len(key) > 16:
        raise HTTPException(status_code=400, detail="Invalid key")
    payload = get_payload(key)
    if payload is None:
        raise HTTPException(status_code=404, detail="Visualization not found or expired")
    return payload
