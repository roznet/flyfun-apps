"""
Build compact visualization payloads for the web app.

The payload is a small JSON dict describing the map view (tool, visualization
type, route/point, filters, and highlighted airports).  It is POSTed to the
web server's ``/api/viz`` store and accessed via a short ``/v/{key}`` link.

Payload is kept small by stripping full airport objects and keeping only the
fields needed for highlights (ident, name, lat, lon, country).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_compact_payload(
    tool_name: str,
    tool_result: Dict[str, Any],
    filters: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build a compact visualization payload from a tool result.

    Returns None if the tool result contains no visualization data.
    """
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
