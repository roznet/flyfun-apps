#!/usr/bin/env python3
"""
Euro AIP MCP Server

Provides European AIP airport data, route planning, and flight information
tools to LLM clients via the Model Context Protocol.

Data coverage varies by country — use the get_data_coverage tool to check
which countries have current AIRAC data before planning.
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from pydantic import Field

# Add the flyfun-apps package to the path (before importing shared)
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables using shared loader
from shared.env_loader import load_component_env

component_dir = Path(__file__).parent
load_component_env(component_dir)

from fastmcp import FastMCP

from shared.airport_tools import (
    calculate_flight_distance as shared_calculate_flight_distance,
    find_airports_near_location as shared_find_airports_near_location,
    find_airports_near_route as shared_find_airports_near_route,
    get_airport_details as shared_get_airport_details,
    get_data_coverage as shared_get_data_coverage,
    get_notification_for_airport as shared_get_notification_for_airport,
    list_aip_fields as shared_list_aip_fields,
    query_aip_fields as shared_query_aip_fields,
    search_airports as shared_search_airports,
)
from shared.tool_context import ToolContext
from shared.viz_url import build_compact_payload

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# Web app base URL and viz API endpoint
MAPS_BASE_URL = os.getenv("MAPS_BASE_URL", "https://maps.flyfun.aero")
# In Docker: http://web-server:8000 (internal network)
# Locally: http://localhost:8000
VIZ_API_URL = os.getenv("VIZ_API_URL", "http://localhost:8000/api/viz")


def _attach_viz_url(tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Post visualization payload to the web server and attach a short link.

    If the web server is unreachable the result is returned without a link.
    """
    payload = build_compact_payload(tool_name, result)
    if payload is None:
        return result

    try:
        import json
        import urllib.request

        req_body = json.dumps({"payload": payload}).encode()
        req = urllib.request.Request(
            VIZ_API_URL,
            data=req_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            key = json.loads(resp.read())["key"]

        result["action"] = {
            "type": "present_link",
            "url": f"{MAPS_BASE_URL}/v/{key}",
            "label": "View on FlyFun Maps",
        }
    except Exception as exc:
        logger.warning("Failed to store viz payload: %s", exc)

    return result

# ---- Global context ----------------------------------------------------------
_tool_context: Optional[ToolContext] = None


def _require_tool_context() -> ToolContext:
    if _tool_context is None:
        raise RuntimeError("Tool context not initialized. Server not started properly.")
    return _tool_context


# ---- Lifespan ----------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastMCP):
    global _tool_context

    from shared.aviation_agent.config import get_settings

    settings = get_settings()
    logger.info("Loading airport model from database")
    _tool_context = settings.build_tool_context(load_rules=False)

    logger.info(
        "Server ready — %d airports loaded, notifications=%s",
        _tool_context.model.airports.count(),
        "yes" if _tool_context.notification_service else "no",
    )

    try:
        yield
    finally:
        pass


mcp = FastMCP(
    name="euro_aip",
    instructions=(
        "European AIP airport data for GA flight planning. "
        "Covers airports, runways, procedures, frequencies, customs notifications, "
        "and route planning across Europe. Data freshness varies by country — "
        "call get_data_coverage first to check which countries have current AIRAC data.\n\n"
        "Tools that return geographic results include an `action` block with a link "
        "to an interactive map. Present this link to the user as a clickable URL "
        "so they can visually explore the results."
    ),
    lifespan=lifespan,
    stateless_http=True,
)


# ---- Shared descriptions -----------------------------------------------------
_MAP_LINK_NOTE = (
    " Returns an interactive map link in `action.url` — "
    "present it to the user so they can explore the results visually."
)

_FILTERS_DESC = (
    "Optional filter dict. Keys: "
    "country (ISO-2 code, e.g. 'FR'), "
    "has_avgas (bool), has_jet_a (bool), "
    "has_hard_runway (bool), has_procedures (bool — IFR capable), "
    "point_of_entry (bool — customs/border crossing), "
    "min_runway_length_ft (int), max_runway_length_ft (int), "
    "restaurant (bool), hotel (bool)"
)

# ---- Tools -------------------------------------------------------------------

@mcp.tool(
    name="get_data_coverage",
    description=(
        "Check AIP data freshness per country. Returns AIRAC cycle date, data source, "
        "and airport count for each country. Call this before planning to know which "
        "countries have current data and which need cross-checking with official sources."
    ),
)
def get_data_coverage() -> Dict[str, Any]:
    return shared_get_data_coverage(_require_tool_context())


@mcp.tool(
    name="search_airports",
    description=(
        "Search airports by ICAO code, IATA code, name, or city. "
        "Returns matching airports with key details (runways, fuel, procedures). "
        "For proximity searches use find_airports_near_location instead."
        + _MAP_LINK_NOTE
    ),
)
def search_airports(
    query: Annotated[str, Field(
        description="ICAO code, IATA code, airport name, or city (e.g. 'LFPG', 'CDG', 'Nice')")],
    max_results: Annotated[int, Field(
        description="Maximum number of results")] = 10,
    include_large_airports: Annotated[bool, Field(
        description="Include large commercial airports (excluded by default for GA)")] = False,
    filters: Annotated[Optional[Dict[str, Any]], Field(
        description=_FILTERS_DESC)] = None,
) -> Dict[str, Any]:
    result = shared_search_airports(
        _require_tool_context(), query, max_results, filters,
        include_large_airports=include_large_airports,
    )
    return _attach_viz_url("search_airports", result)


@mcp.tool(
    name="find_airports_near_location",
    description=(
        "Find airports near a geographic point — an ICAO code, city, landmark, "
        "or lat/lon coordinates. Returns airports within the search radius sorted "
        "by suitability, with distance and notification requirements."
        + _MAP_LINK_NOTE
    ),
)
def find_airports_near_location(
    location_query: Annotated[str, Field(
        description="ICAO code, city, landmark, or 'lat, lon' (e.g. 'EGTF', 'Zurich', '48.85, 2.29')")],
    max_distance_nm: Annotated[float, Field(
        description="Search radius in nautical miles")] = 50.0,
    max_results: Annotated[int, Field(
        description="Maximum number of results")] = 10,
    include_large_airports: Annotated[bool, Field(
        description="Include large commercial airports (excluded by default for GA)")] = False,
    max_hours_notice: Annotated[Optional[int], Field(
        description="Only return airports requiring at most this many hours customs notice (e.g. 24)")] = None,
    filters: Annotated[Optional[Dict[str, Any]], Field(
        description=_FILTERS_DESC)] = None,
) -> Dict[str, Any]:
    result = shared_find_airports_near_location(
        _require_tool_context(),
        location_query,
        max_distance_nm=max_distance_nm,
        max_results=max_results,
        filters=filters,
        include_large_airports=include_large_airports,
        max_hours_notice=max_hours_notice,
    )
    return _attach_viz_url("find_airports_near_location", result)


@mcp.tool(
    name="find_airports_near_route",
    description=(
        "Find airports along a route between two or more locations. "
        "Supports multi-leg routes via intermediate waypoints, time-based filtering "
        "(e.g. fuel stops within 3h flight), and airport filters. "
        "Useful for fuel stops, alternates, and customs/border crossing airports."
        + _MAP_LINK_NOTE
    ),
)
def find_airports_near_route(
    from_location: Annotated[str, Field(
        description="Departure — ICAO code or location name, include country if ambiguous (e.g. 'LFPO', 'Vik, Iceland')")],
    to_location: Annotated[str, Field(
        description="Destination — ICAO code or location name, include country if ambiguous")],
    via: Annotated[Optional[List[str]], Field(
        description="Intermediate waypoints in order (e.g. ['LFPB', 'Straubing'])")] = None,
    max_distance_nm: Annotated[float, Field(
        description="Search radius from route centerline in NM")] = 50.0,
    max_results: Annotated[int, Field(
        description="Maximum number of results")] = 10,
    include_large_airports: Annotated[bool, Field(
        description="Include large commercial airports (excluded by default for GA)")] = False,
    max_hours_notice: Annotated[Optional[int], Field(
        description="Only return airports requiring at most this many hours customs notice")] = None,
    max_leg_time_hours: Annotated[Optional[float], Field(
        description="Max flight time from departure in hours for time-based filtering (e.g. 3.0)")] = None,
    cruise_speed_kts: Annotated[Optional[float], Field(
        description="Cruise speed in knots for time calculation (e.g. 140)")] = None,
    aircraft_type: Annotated[Optional[str], Field(
        description="Aircraft type for speed lookup (e.g. 'C172', 'SR22', 'PA28')")] = None,
    filters: Annotated[Optional[Dict[str, Any]], Field(
        description=_FILTERS_DESC)] = None,
) -> Dict[str, Any]:
    result = shared_find_airports_near_route(
        _require_tool_context(),
        from_location,
        to_location,
        via=via,
        max_distance_nm=max_distance_nm,
        max_results=max_results,
        filters=filters,
        include_large_airports=include_large_airports,
        max_hours_notice=max_hours_notice,
        max_leg_time_hours=max_leg_time_hours,
        cruise_speed_kts=cruise_speed_kts,
        aircraft_type=aircraft_type,
    )
    return _attach_viz_url("find_airports_near_route", result)


@mcp.tool(
    name="get_airport_details",
    description=(
        "Get full details for a specific airport: runways, procedures, frequencies, "
        "fuel, opening hours, and other AIP information."
        + _MAP_LINK_NOTE
    ),
)
def get_airport_details(
    icao_code: Annotated[str, Field(
        description="Airport ICAO code (e.g. 'LFPG', 'EGLL', 'EDDM')")],
) -> Dict[str, Any]:
    result = shared_get_airport_details(_require_tool_context(), icao_code)
    return _attach_viz_url("get_airport_details", result)


@mcp.tool(
    name="get_notification_for_airport",
    description=(
        "Get customs/immigration notification requirements for an airport. "
        "Returns required notice period, contact details, and day-specific rules."
        + _MAP_LINK_NOTE
    ),
)
def get_notification_for_airport(
    icao: Annotated[str, Field(
        description="Airport ICAO code (e.g. 'LFRG', 'LFPT')")],
    day_of_week: Annotated[Optional[str], Field(
        description="Specific day for day-dependent rules (e.g. 'Saturday')")] = None,
) -> Dict[str, Any]:
    result = shared_get_notification_for_airport(_require_tool_context(), icao, day_of_week)
    return _attach_viz_url("get_notification_for_airport", result)


@mcp.tool(
    name="calculate_flight_distance",
    description=(
        "Calculate great-circle distance and estimated flight time between two locations. "
        "Accepts ICAO codes or place names. Provide aircraft type or cruise speed for time estimates."
        + _MAP_LINK_NOTE
    ),
)
def calculate_flight_distance(
    from_location: Annotated[str, Field(
        description="Departure — ICAO code or location name (e.g. 'EGTF', 'Paris')")],
    to_location: Annotated[str, Field(
        description="Destination — ICAO code or location name (e.g. 'LFMD', 'Nice, France')")],
    cruise_speed_kts: Annotated[Optional[float], Field(
        description="Cruise speed in knots (e.g. 140)")] = None,
    aircraft_type: Annotated[Optional[str], Field(
        description="Aircraft type for speed lookup (e.g. 'C172', 'SR22')")] = None,
) -> Dict[str, Any]:
    result = shared_calculate_flight_distance(
        _require_tool_context(), from_location, to_location,
        cruise_speed_kts=cruise_speed_kts,
        aircraft_type=aircraft_type,
    )
    return _attach_viz_url("calculate_flight_distance", result)


@mcp.tool(
    name="list_aip_fields",
    description=(
        "List what AIP data fields exist — what information categories are stored for airports. "
        "Returns field names, numeric IDs, and airport counts. "
        "Use when asked 'what fields are available', 'what data do you have', or 'list AIP fields'. "
        "Call this before query_aip_fields to discover field names."
    ),
)
def list_aip_fields() -> Dict[str, Any]:
    return shared_list_aip_fields(_require_tool_context())


@mcp.tool(
    name="query_aip_fields",
    description=(
        "Get the value of a specific AIP field (customs, hotels, restaurants, ATS, fuel, maintenance, etc.) "
        "across airports filtered by country or ICAO codes. "
        "Use for 'customs info in France', 'ATS hours', 'fuel types at LFPG', 'what changed recently'. "
        "Supports change history via changed_since parameter. "
        "Common fields: Customs and immigration (302), Hotels (501), Restaurants (502), "
        "ATS (307), Fuelling (308), Maintenance (406), Type of Traffic permitted (207)."
    ),
)
def query_aip_fields(
    field: Annotated[str, Field(
        description="AIP standard field name or numeric ID (e.g. 'Customs and immigration', '302', 'Hotels')")],
    country: Annotated[Optional[str], Field(
        description="ISO-2 country code to filter airports (e.g. 'FR', 'DE')")] = None,
    icao_codes: Annotated[Optional[List[str]], Field(
        description="Explicit list of ICAO codes (use after a search or route tool)")] = None,
    changed_since: Annotated[Optional[str], Field(
        description="ISO date (YYYY-MM-DD). Returns only airports where field changed after this date")] = None,
    max_results: Annotated[int, Field(
        description="Maximum airports to return")] = 20,
) -> Dict[str, Any]:
    return shared_query_aip_fields(
        _require_tool_context(),
        field=field,
        country=country,
        icao_codes=icao_codes,
        changed_since=changed_since,
        max_results=max_results,
    )


# ---- CLI entry point ---------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Euro AIP MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio",
        help="Transport type (default: stdio)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Host for HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=8001,
        help="Port for HTTP transport (default: 8001)",
    )
    parser.add_argument(
        "--database", default=None,
        help="Database file (overrides AIRPORTS_DB env var)",
    )

    args = parser.parse_args()
    if args.database is not None:
        os.environ["AIRPORTS_DB"] = args.database

    if args.transport == "http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()
