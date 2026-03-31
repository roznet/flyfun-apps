"""
Build deep-link URLs that open the web app with a specific visualization.

The URL carries a compact JSON payload (base64url-encoded) in the ``?viz=``
query parameter.  The frontend decodes it and feeds it through the same
``LLMIntegration`` pipeline used by the chatbot, so the user sees the exact
same map view.

Payload is kept small by stripping full airport objects and keeping only the
fields needed for highlights (ident, name, lat, lon, country).
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional

# Default base URL for the web app (overridable via env)
DEFAULT_BASE_URL = "https://maps.flyfun.aero"


def build_viz_url(
    tool_name: str,
    tool_result: Dict[str, Any],
    *,
    base_url: str = DEFAULT_BASE_URL,
    filters: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return a deep-link URL embedding the visualization, or None if no viz."""
    payload = _build_compact_payload(tool_name, tool_result, filters)
    if payload is None:
        return None

    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")  # strip padding for shorter URLs

    return f"{base_url}?viz={encoded}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_HIGHLIGHT_KEYS = ("ident", "name", "latitude_deg", "longitude_deg", "iso_country")


def _compact_airport(airport: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Keep only the fields the frontend needs for a highlight marker."""
    ident = airport.get("ident")
    lat = airport.get("latitude_deg")
    lon = airport.get("longitude_deg")
    if not ident or lat is None or lon is None:
        return None
    return {k: airport[k] for k in _HIGHLIGHT_KEYS if k in airport}


def _strip_visualization(viz: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *viz* with bulky airport lists removed.

    Route endpoints, point centre, and marker ident are preserved — the
    frontend uses those to trigger its own API searches.  The ``markers``
    and ``data`` arrays are replaced by the compact ``highlights`` list
    built separately.
    """
    stripped: Dict[str, Any] = {"type": viz["type"]}

    if "route" in viz:
        # Keep only ICAO codes (frontend triggers search from those)
        route = viz["route"]
        compact_route: Dict[str, Any] = {}
        for key in ("from", "to"):
            if key in route:
                compact_route[key] = {"icao": route[key].get("icao", "")}
        if "via" in route:
            compact_route["via"] = [
                {"icao": wp.get("icao", "")} for wp in route["via"]
            ]
        stripped["route"] = compact_route

    if "point" in viz:
        stripped["point"] = viz["point"]

    if "marker" in viz:
        stripped["marker"] = viz["marker"]

    if "radius_nm" in viz:
        stripped["radius_nm"] = viz["radius_nm"]

    return stripped


def _build_compact_payload(
    tool_name: str,
    tool_result: Dict[str, Any],
    filters: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    viz = tool_result.get("visualization")
    if not viz or "type" not in viz:
        return None

    payload: Dict[str, Any] = {
        "tool": tool_name,
        "visualization": _strip_visualization(viz),
    }

    # Filters — use explicit arg, fall back to tool_result's filter_profile
    effective_filters = filters or tool_result.get("filter_profile")
    if effective_filters:
        # Strip keys that are empty/None to save bytes
        compact = {k: v for k, v in effective_filters.items() if v is not None and v != ""}
        if compact:
            payload["filters"] = compact

    # Highlights — compact airport summaries for blue markers
    airports: List[Dict[str, Any]] = tool_result.get("airports", [])
    if isinstance(airports, list) and airports:
        highlights = [h for a in airports if (h := _compact_airport(a)) is not None]
        if highlights:
            payload["highlights"] = highlights

    return payload
