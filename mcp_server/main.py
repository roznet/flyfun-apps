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
from typing import Any, Dict, List, Optional

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
    search_airports as shared_search_airports,
)
from shared.tool_context import ToolContext

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

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
        "call get_data_coverage first to check which countries have current AIRAC data."
    ),
    lifespan=lifespan,
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
    ),
)
def search_airports(
    query: str,
    max_results: int = 10,
    include_large_airports: bool = False,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Args:
        query: ICAO code, IATA code, airport name, or city (e.g. "LFPG", "CDG", "Nice")
        max_results: Maximum number of results (default 10)
        include_large_airports: Include large commercial airports (excluded by default for GA)
        filters: Optional dict with keys: country (ISO-2), has_avgas (bool), has_jet_a (bool),
                 has_hard_runway (bool), has_procedures (bool), point_of_entry (bool)
    """
    return shared_search_airports(
        _require_tool_context(), query, max_results, filters,
        include_large_airports=include_large_airports,
    )


@mcp.tool(
    name="find_airports_near_location",
    description=(
        "Find airports near a geographic point — an ICAO code, city, landmark, "
        "or lat/lon coordinates. Returns airports within the search radius sorted "
        "by suitability, with distance and notification requirements."
    ),
)
def find_airports_near_location(
    location_query: str,
    max_distance_nm: float = 50.0,
    max_results: int = 10,
    include_large_airports: bool = False,
    max_hours_notice: Optional[int] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Args:
        location_query: ICAO code, city, landmark, or "lat, lon" (e.g. "EGTF", "Zurich", "48.85, 2.29")
        max_distance_nm: Search radius in nautical miles (default 50)
        max_results: Maximum number of results (default 10)
        include_large_airports: Include large commercial airports (excluded by default for GA)
        max_hours_notice: Only return airports requiring at most this many hours customs notice (e.g. 24)
        filters: Optional dict with keys: country (ISO-2), has_avgas (bool), has_jet_a (bool),
                 has_hard_runway (bool), has_procedures (bool), point_of_entry (bool)
    """
    return shared_find_airports_near_location(
        _require_tool_context(),
        location_query,
        max_distance_nm=max_distance_nm,
        max_results=max_results,
        filters=filters,
        include_large_airports=include_large_airports,
        max_hours_notice=max_hours_notice,
    )


@mcp.tool(
    name="find_airports_near_route",
    description=(
        "Find airports along a route between two or more locations. "
        "Supports multi-leg routes via intermediate waypoints, time-based filtering "
        "(e.g. fuel stops within 3h flight), and airport filters. "
        "Useful for fuel stops, alternates, and customs/border crossing airports."
    ),
)
def find_airports_near_route(
    from_location: str,
    to_location: str,
    via: Optional[List[str]] = None,
    max_distance_nm: float = 50.0,
    max_results: int = 10,
    include_large_airports: bool = False,
    max_hours_notice: Optional[int] = None,
    max_leg_time_hours: Optional[float] = None,
    cruise_speed_kts: Optional[float] = None,
    aircraft_type: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Args:
        from_location: Departure — ICAO code or location name with country context (e.g. "LFPO", "Vik, Iceland")
        to_location: Destination — ICAO code or location name with country context
        via: Intermediate waypoints in order (e.g. ["LFPB", "Straubing"])
        max_distance_nm: Search radius from route centerline in NM (default 50)
        max_results: Maximum number of results (default 10)
        include_large_airports: Include large commercial airports (excluded by default for GA)
        max_hours_notice: Only return airports requiring at most this many hours customs notice
        max_leg_time_hours: Maximum flight time from departure for time-based filtering (e.g. 3.0)
        cruise_speed_kts: Cruise speed in knots for time calculation (e.g. 140)
        aircraft_type: Aircraft type for speed lookup (e.g. "C172", "SR22", "PA28")
        filters: Optional dict with keys: country (ISO-2), has_avgas (bool), has_jet_a (bool),
                 has_hard_runway (bool), has_procedures (bool), point_of_entry (bool)
    """
    return shared_find_airports_near_route(
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


@mcp.tool(
    name="get_airport_details",
    description=(
        "Get full details for a specific airport: runways, procedures, frequencies, "
        "fuel, opening hours, and other AIP information."
    ),
)
def get_airport_details(icao_code: str) -> Dict[str, Any]:
    """
    Args:
        icao_code: Airport ICAO code (e.g. "LFPG", "EGLL", "EDDM")
    """
    return shared_get_airport_details(_require_tool_context(), icao_code)


@mcp.tool(
    name="get_notification_for_airport",
    description=(
        "Get customs/immigration notification requirements for an airport. "
        "Returns required notice period, contact details, and day-specific rules."
    ),
)
def get_notification_for_airport(
    icao: str,
    day_of_week: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Args:
        icao: Airport ICAO code (e.g. "LFRG", "LFPT")
        day_of_week: Optional specific day for day-dependent rules (e.g. "Saturday")
    """
    return shared_get_notification_for_airport(_require_tool_context(), icao, day_of_week)


@mcp.tool(
    name="calculate_flight_distance",
    description=(
        "Calculate great-circle distance and estimated flight time between two locations. "
        "Accepts ICAO codes or place names. Provide aircraft type or cruise speed for time estimates."
    ),
)
def calculate_flight_distance(
    from_location: str,
    to_location: str,
    cruise_speed_kts: Optional[float] = None,
    aircraft_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Args:
        from_location: Departure — ICAO code or location name (e.g. "EGTF", "Paris")
        to_location: Destination — ICAO code or location name (e.g. "LFMD", "Nice, France")
        cruise_speed_kts: Cruise speed in knots (e.g. 140)
        aircraft_type: Aircraft type for speed lookup (e.g. "C172", "SR22")
    """
    return shared_calculate_flight_distance(
        _require_tool_context(), from_location, to_location,
        cruise_speed_kts=cruise_speed_kts,
        aircraft_type=aircraft_type,
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
