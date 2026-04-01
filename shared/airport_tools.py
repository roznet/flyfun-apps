#!/usr/bin/env python3
"""
Shared Airport & Aviation Rules Tools
======================================

This module provides the core tool functions used by both the MCP server and
the internal aviation chatbot agent. Tools are organized into two main categories:

AIRPORT TOOLS (Section 5):
    - search_airports: Search by ICAO, name, city, or country
    - find_airports_near_location: Find airports near a geographic point
    - find_airports_near_route: Find airports along a flight route
    - get_airport_details: Get comprehensive airport information
    - get_notification_for_airport: Customs notification requirements
    - calculate_flight_distance: Calculate distance and flight time between airports

AIP FIELD TOOLS (Section 6b):
    - list_aip_fields: Discover available AIP standard fields
    - query_aip_fields: Query raw AIP field values with optional change history

RULES TOOLS (Section 7):
    - answer_rules_question: Answer specific questions about rules for a country (RAG-based)
    - browse_rules: Browse/list rules by category and tags with pagination
    - compare_rules_between_countries: Compare rules between two or more countries

TOOL REGISTRY (Section 8):
    - get_shared_tool_specs(): Returns the tool manifest for registration

Usage:
    from shared.airport_tools import get_shared_tool_specs
    specs = get_shared_tool_specs()
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, OrderedDict as OrderedDictType, TypedDict
import os
import urllib.parse
import json
import urllib.request

from euro_aip.models.airport import Airport
from euro_aip.models.navpoint import NavPoint

from .aircraft_speeds import resolve_cruise_speed, get_aircraft_info, format_time
from .filtering import FilterEngine
from .prioritization import PriorityEngine
from .tool_context import ToolContext


# =============================================================================
# SECTION 2: TYPE DEFINITIONS
# =============================================================================

ToolCallable = Callable[..., Dict[str, Any]]


class ToolSpec(TypedDict):
    """Metadata describing a shared tool.

    Attributes:
        name: Tool identifier used for registration and invocation
        handler: The callable function that implements the tool
        description: Human-readable description (from config or docstring)
        parameters: JSON Schema defining the tool's parameters
        expose_to_llm: If True, tool is available to the aviation agent;
                       if False, tool is internal or MCP-only
    """
    name: str
    handler: ToolCallable
    description: str
    parameters: Dict[str, Any]
    expose_to_llm: bool


# =============================================================================
# SECTION 4: INTERNAL HELPERS
# =============================================================================

# -----------------------------------------------------------------------------
# Geocoding & Location Helpers
# -----------------------------------------------------------------------------

# European country codes for geocoding preference
EUROPEAN_COUNTRY_CODES = {
    "DE", "FR", "GB", "ES", "IT", "NL", "BE", "CH", "AT", "PL", "PT",
    "GR", "IE", "SE", "NO", "DK", "FI", "CZ", "HU", "HR", "SI", "SK",
    "RO", "BG", "TR", "MT", "LU", "IS", "EE", "LV", "LT", "CY", "RS",
    "AL", "ME", "MK", "BA", "GG", "JE", "IM", "FO", "MC", "AD", "LI",
}


def _geoapify_geocode(query: str) -> Optional[Dict[str, Any]]:
    """
    Forward-geocode a free-text location using Geoapify.

    Prefers European locations for ambiguous queries (e.g., "Bromley" returns UK, not USA).

    Args:
        query: Free-text location name (e.g., "Paris", "Lake Geneva")

    Returns:
        Dict with 'lat', 'lon', 'formatted', 'country_code' on success;
        None on failure or if GEOAPIFY_API_KEY is not set.
    """
    api_key = os.environ.get("GEOAPIFY_API_KEY")
    if not api_key:
        return None
    base_url = "https://api.geoapify.com/v1/geocode/search"
    params = {
        "text": query,
        "limit": 5,  # Get multiple results to find European match
        "format": "json",
        "apiKey": api_key,
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            payload = resp.read()
            data = json.loads(payload.decode("utf-8"))
            results = data.get("results") or []
            if not results:
                return None

            # Prefer European results for ambiguous queries like "Bromley"
            selected = None
            for result in results:
                country_code = (result.get("country_code") or "").upper()
                if country_code in EUROPEAN_COUNTRY_CODES:
                    selected = result
                    break

            # Fall back to first result if no European match
            if not selected:
                selected = results[0]

            lat = selected.get("lat")
            lon = selected.get("lon")
            if lat is None or lon is None:
                return None
            return {
                "lat": float(lat),
                "lon": float(lon),
                "formatted": selected.get("formatted") or query,
                "country_code": selected.get("country_code"),
            }
    except Exception:
        return None


def _find_nearest_airport_in_db(
    ctx: ToolContext,
    icao_or_location: str,
    max_search_radius_nm: float = 100.0
) -> Optional[Dict[str, Any]]:
    """
    Find the nearest airport in the database for a given ICAO code or location name.

    Resolution process:
    1. First checks if the input is an ICAO code in the database
    2. If not found, tries to geocode it as a location name
    3. Finds the nearest airport to those coordinates
       - Prefers airports in the same country as the geocoded location
       - Falls back to nearest airport if none in same country

    Args:
        ctx: Tool context with airport model
        icao_or_location: ICAO code or free-text location name
        max_search_radius_nm: Maximum search radius in nautical miles

    Returns:
        Dict with 'airport', 'original_query', 'was_geocoded', 'distance_nm',
        'geocoded_location'; or None if nothing found.
    """
    icao = icao_or_location.strip().upper()

    # First try direct ICAO lookup
    airport = ctx.model.airports.get(icao)
    if airport:
        return {
            "airport": airport,
            "original_query": icao_or_location,
            "was_geocoded": False,
            "distance_nm": 0.0,
            "geocoded_location": None
        }

    # Not found as ICAO - try geocoding as location name
    geocode = _geoapify_geocode(icao_or_location)

    if not geocode:
        return None

    center_point = NavPoint(latitude=geocode["lat"], longitude=geocode["lon"], name=geocode["formatted"])
    geocode_country = geocode.get("country_code")  # ISO-2 country code from Geoapify

    # Find airports within radius, tracking both same-country and any-country nearest
    nearest_same_country = None
    nearest_same_country_distance = float('inf')
    nearest_any = None
    nearest_any_distance = float('inf')

    for apt in ctx.model.airports:
        if not getattr(apt, "navpoint", None):
            continue
        try:
            _, distance_nm = apt.navpoint.haversine_distance(center_point)
        except Exception:
            continue

        if distance_nm > max_search_radius_nm:
            continue

        # Track nearest airport overall
        if distance_nm < nearest_any_distance:
            nearest_any_distance = distance_nm
            nearest_any = apt

        # Track nearest airport in same country (if country known)
        if geocode_country and getattr(apt, "iso_country", None):
            if apt.iso_country.upper() == geocode_country.upper():
                if distance_nm < nearest_same_country_distance:
                    nearest_same_country_distance = distance_nm
                    nearest_same_country = apt

    # Prefer same-country airport if found, otherwise use nearest any
    if nearest_same_country:
        return {
            "airport": nearest_same_country,
            "original_query": icao_or_location,
            "was_geocoded": True,
            "distance_nm": round(nearest_same_country_distance, 1),
            "geocoded_location": geocode["formatted"]
        }

    if nearest_any:
        return {
            "airport": nearest_any,
            "original_query": icao_or_location,
            "was_geocoded": True,
            "distance_nm": round(nearest_any_distance, 1),
            "geocoded_location": geocode["formatted"]
        }

    return None


# -----------------------------------------------------------------------------
# Airport Data Helpers
# -----------------------------------------------------------------------------

def _airport_summary(a: Airport) -> Dict[str, Any]:
    """Convert an Airport object to a summary dict for API responses."""
    return {
        "ident": a.ident,
        "name": a.name,
        "municipality": a.municipality,
        "iso_country": a.iso_country,
        "latitude_deg": getattr(a, "latitude_deg", None),
        "longitude_deg": getattr(a, "longitude_deg", None),
        "longest_runway_length_ft": getattr(a, "longest_runway_length_ft", None),
        "point_of_entry": bool(getattr(a, "point_of_entry", False)),
        "has_aip_data": bool(a.aip_entries) if hasattr(a, "aip_entries") else False,
        "has_procedures": bool(a.procedures),
        "has_hard_runway": bool(getattr(a, "has_hard_runway", False)),
    }


def _build_priority_context(
    base_context: Optional[Dict[str, Any]] = None,
    persona_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build context dict for PriorityEngine.apply().

    Merges base_context (e.g., segment_distances) with persona_id if provided.
    """
    context = dict(base_context) if base_context else {}
    if persona_id:
        context["persona_id"] = persona_id
    return context


# -----------------------------------------------------------------------------
# Airport Filter & Sort Pipeline
# -----------------------------------------------------------------------------

@dataclass
class AirportFilterResult:
    """Result of filtering and sorting airports.

    Attributes:
        airports: Filtered and sorted list of Airport objects
        notification_infos: Dict mapping ICAO codes to NotificationInfo objects
    """
    airports: List[Airport]
    notification_infos: Dict[str, Any]


def _filter_and_sort_airports(
    ctx: ToolContext,
    airports: List[Airport],
    filters: Optional[Dict[str, Any]] = None,
    include_large_airports: bool = False,
    priority_strategy: str = "persona_optimized",
    priority_context_extra: Optional[Dict[str, Any]] = None,
    max_hours_notice: Optional[int] = None,
    max_results: int = 100,
    persona_id: Optional[str] = None,
) -> AirportFilterResult:
    """
    Common pipeline for airport tools: filter → notification filter → priority sort.

    This helper consolidates the repeated filtering and sorting logic used by
    all airport search tools.

    Args:
        ctx: Tool context with model and services
        airports: List of candidate airports to filter/sort
        filters: Optional dict of filter criteria (has_avgas, point_of_entry, etc.)
        include_large_airports: If False, excludes large commercial airports
        priority_strategy: Sorting strategy for PriorityEngine
        priority_context_extra: Additional context for priority sorting (e.g., distances)
        max_hours_notice: If set, filter to airports with <= this notification requirement
        max_results: Maximum number of airports to return
        persona_id: Optional persona ID for personalized sorting

    Returns:
        AirportFilterResult with sorted airports and notification info dict
    """
    # 1. Build effective filters (always exclude large airports unless explicitly included)
    effective_filters: Dict[str, Any] = {}
    if not include_large_airports:
        effective_filters["exclude_large_airports"] = True
    if filters:
        effective_filters.update(filters)

    # 2. Apply filters using FilterEngine
    if effective_filters:
        filter_engine = FilterEngine(context=ctx)
        airports = filter_engine.apply(airports, effective_filters)

    # 3. Fetch notification info for all candidate airports
    notification_infos: Dict[str, Any] = {}
    if ctx.notification_service and airports:
        candidate_icaos = [a.ident for a in airports]
        notification_infos = ctx.notification_service.get_notification_info_batch(candidate_icaos)

        # Filter by notification requirements if max_hours_notice is specified
        if max_hours_notice is not None and notification_infos:
            filtered_by_notification = []
            for airport in airports:
                info = notification_infos.get(airport.ident)
                if info and info.matches_criteria(max_hours_notice=max_hours_notice):
                    filtered_by_notification.append(airport)
                elif info is None:
                    # No notification data - include by default (unknown requirements)
                    filtered_by_notification.append(airport)
            airports = filtered_by_notification

    # 4. Apply priority sorting using PriorityEngine
    priority_engine = PriorityEngine(context=ctx)
    priority_context = _build_priority_context(
        base_context=priority_context_extra,
        persona_id=persona_id
    )
    sorted_airports = priority_engine.apply(
        airports,
        strategy=priority_strategy,
        context=priority_context,
        max_results=max_results
    )

    return AirportFilterResult(
        airports=sorted_airports,
        notification_infos=notification_infos
    )


def _build_filter_profile(
    base: Dict[str, Any],
    filters: Optional[Dict[str, Any]] = None,
    max_hours_notice: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build filter profile dict for UI synchronization.

    Args:
        base: Base profile dict (e.g., {"search_query": "Paris"})
        filters: Optional filters dict from tool call
        max_hours_notice: Optional notification filter

    Returns:
        Complete filter profile for UI sync
    """
    profile = dict(base)

    if max_hours_notice is not None:
        profile["max_hours_notice"] = max_hours_notice

    if not filters:
        return profile

    # Direct copy keys (values matter - strings or numbers, not booleans)
    for key in ["country", "max_runway_length_ft", "min_runway_length_ft", "max_landing_fee",
                "hotel", "restaurant"]:
        if filters.get(key):
            profile[key] = filters[key]

    # Boolean keys (just need to be truthy)
    for key in ["has_procedures", "has_aip_data", "has_hard_runway",
                "point_of_entry", "has_avgas", "has_jet_a"]:
        if filters.get(key):
            profile[key] = True

    return profile


# -----------------------------------------------------------------------------
# Tool Description Helpers
# -----------------------------------------------------------------------------

def _tool_description(func: Callable) -> str:
    """Get tool description from docstring (legacy function, kept for compatibility)."""
    return (func.__doc__ or "").strip()


def _get_tool_description(func: Callable, tool_name: str) -> str:
    """Get tool description from config file, falling back to docstring.

    Args:
        func: The tool function (for docstring fallback)
        tool_name: Name of the tool for config lookup

    Returns:
        Tool description text from config file, or docstring if not configured.
    """
    # Lazy import to avoid circular dependency (config imports airport_tools)
    try:
        from shared.aviation_agent.config import get_behavior_config, get_settings
        settings = get_settings()
        config = get_behavior_config(settings.agent_config_name or "default")

        # Try to load from config
        if config:
            description = config.load_tool_description(tool_name)
            if description:
                return description
    except Exception:
        # If config loading fails, fall back to docstring
        pass

    # Fallback to docstring
    return (func.__doc__ or "").strip()


# =============================================================================
# SECTION 5: AIRPORT TOOLS
# =============================================================================

# -----------------------------------------------------------------------------
# Search & Discovery
# -----------------------------------------------------------------------------

def search_airports(
    ctx: ToolContext,
    query: str,
    max_results: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    include_large_airports: bool = False,
    priority_strategy: str = "persona_optimized",
    **kwargs: Any,  # Accept _persona_id injected by ToolRunner
) -> Dict[str, Any]:
    """
    Search for airports by ICAO code, IATA code, airport name, or city name with optional filters (country, procedures, runway, fuel, fees).

    **USE THIS TOOL for direct name/code searches**, not for proximity searches.

    Examples:
    - "LFPG" → use this tool (ICAO code search)
    - "Charles de Gaulle" → use this tool (airport name search)
    - "Paris airports" → use this tool (searches airports with "Paris" in name/city)
    - "CDG" → use this tool (IATA code search)

    **DO NOT use this tool for "near" queries** - use find_airports_near_location instead for proximity searches.

    **By default, large commercial airports are excluded** (not suitable for GA).
    Set include_large_airports=True only if user explicitly asks for large/commercial airports.

    Returns matching airports sorted by priority.
    """
    q = query.upper().strip()
    matches: List[Airport] = []

    # Check if query contains multiple ICAO codes (space-separated 4-letter codes)
    # Filter out common conjunctions like "and", "or", commas
    parts = [p.strip(",") for p in q.split() if p.upper() not in ("AND", "OR", "&", ",")]
    if len(parts) > 1 and all(len(p) == 4 and p.isalpha() for p in parts):
        # Multiple ICAO codes - search for each
        icao_set = set(parts)
        for a in ctx.model.airports:
            if a.ident in icao_set:
                matches.append(a)
                if len(matches) >= len(icao_set):
                    break  # Found all requested airports

        # Skip country detection and standard search
        # Filter and sort using common pipeline
        persona_id = kwargs.pop("_persona_id", None)
        result = _filter_and_sort_airports(
            ctx=ctx,
            airports=matches,
            filters=filters,
            include_large_airports=True,  # Don't filter out large airports when explicitly requested
            priority_strategy=priority_strategy,
            max_results=max(max_results, len(icao_set)),  # Return at least as many as requested
            persona_id=persona_id,
        )

        airport_summaries = [_airport_summary(a) for a in result.airports]
        filter_profile = _build_filter_profile({"search_query": query}, filters)

        return {
            "count": len(airport_summaries),
            "airports": airport_summaries,
            "filter_profile": filter_profile,
            "visualization": {
                "type": "markers",
                "data": airport_summaries
            }
        }

    # Country name to ISO-2 code mapping for common country searches
    country_name_map = {
        "GERMANY": "DE", "FRANCE": "FR", "UNITED KINGDOM": "GB", "UK": "GB",
        "SPAIN": "ES", "ITALY": "IT", "NETHERLANDS": "NL", "BELGIUM": "BE",
        "SWITZERLAND": "CH", "AUSTRIA": "AT", "POLAND": "PL", "PORTUGAL": "PT",
        "GREECE": "GR", "IRELAND": "IE", "SWEDEN": "SE", "NORWAY": "NO",
        "DENMARK": "DK", "FINLAND": "FI", "CZECH REPUBLIC": "CZ", "CZECHIA": "CZ",
        "HUNGARY": "HU", "CROATIA": "HR", "SLOVENIA": "SI", "SLOVAKIA": "SK",
        "ROMANIA": "RO", "BULGARIA": "BG", "TURKEY": "TR", "MALTA": "MT",
        "LUXEMBOURG": "LU", "ICELAND": "IS", "ESTONIA": "EE", "LATVIA": "LV",
        "LITHUANIA": "LT", "CYPRUS": "CY", "SERBIA": "RS", "ALBANIA": "AL",
        "MONTENEGRO": "ME", "NORTH MACEDONIA": "MK", "BOSNIA": "BA",
        "GUERNSEY": "GG", "JERSEY": "JE",
    }

    # Check if query is a country name
    country_code = country_name_map.get(q)
    detected_country = None  # Track if we detected a country for filter_profile

    if country_code:
        # Search by country code
        detected_country = country_code
        for a in ctx.model.airports:
            if (a.iso_country or "").upper() == country_code:
                matches.append(a)
                if len(matches) >= 200:
                    break
    else:
        # Standard search: ICAO, name, IATA, municipality, or ISO country
        for a in ctx.model.airports:
            if (
                (q in a.ident)
                or (a.name and q in a.name.upper())
                or (getattr(a, "iata_code", None) and q in a.iata_code)
                or (a.municipality and q in a.municipality.upper())
                or ((a.iso_country or "").upper() == q)  # Also check ISO country code
            ):
                matches.append(a)
                if len(matches) >= 200:  # Get more candidates before filtering
                    break

    # Filter and sort using common pipeline
    persona_id = kwargs.pop("_persona_id", None)
    result = _filter_and_sort_airports(
        ctx=ctx,
        airports=matches,
        filters=filters,
        include_large_airports=include_large_airports,
        priority_strategy=priority_strategy,
        max_results=max_results,
        persona_id=persona_id,
    )

    # Convert to summaries
    airport_summaries = [_airport_summary(a) for a in result.airports]

    # Generate filter profile for UI synchronization
    # Include detected country so UI can sync the country filter dropdown
    base_profile: Dict[str, Any] = {"search_query": query}
    if detected_country:
        base_profile["country"] = detected_country
    filter_profile = _build_filter_profile(base_profile, filters)

    return {
        "count": len(airport_summaries),
        "airports": airport_summaries[:max_results],  # Limited for LLM
        "filter_profile": filter_profile,
        "visualization": {
            "type": "markers",
            "data": airport_summaries  # Show ALL matching airports on map
        }
    }


def find_airports_near_location(
    ctx: ToolContext,
    location_query: str,
    max_distance_nm: float = 50.0,
    max_results: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    include_large_airports: bool = False,
    priority_strategy: str = "persona_optimized",
    max_hours_notice: Optional[int] = None,  # Filter by notification requirements
    # Optional pre-resolved center (bypasses geocoding) - used by REST API
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    **kwargs: Any,  # Accept _persona_id injected by ToolRunner
) -> Dict[str, Any]:
    """
    Find airports near a geographic location (ICAO code, free-text location name, city, landmark, or coordinates) within a specified distance.

    **USE THIS TOOL when user asks about airports "near", "around", "close to" a location.**

    Examples:
    - "airports near EGTF" → use this tool with location_query="EGTF"
    - "airports near Paris" → use this tool with location_query="Paris"
    - "airports around Lake Geneva" → use this tool with location_query="Lake Geneva"
    - "airports close to Zurich" → use this tool with location_query="Zurich"
    - "airports near 48.8584, 2.2945" → use this tool with location_query="48.8584, 2.2945"
    - "airports near Vannes with less than 24h notice" → use with max_hours_notice=24

    Process:
    1) If location_query is an ICAO code, uses that airport's coordinates as center
    2) Otherwise geocodes the location via Geoapify (or uses pre-resolved center if provided)
    3) Computes distance from each airport to that point and filters by max_distance_nm
    4) Applies optional filters (fuel, customs, runway, etc.) and priority sorting
    5) If max_hours_notice is set, filters to airports requiring at most that many hours notice

    **By default, large commercial airports are excluded** (not suitable for GA).
    Set include_large_airports=True only if user explicitly asks for large/commercial airports.
    """
    # Use pre-resolved center if provided, otherwise try ICAO lookup then geocode
    if center_lat is not None and center_lon is not None:
        geocode = {
            "lat": center_lat,
            "lon": center_lon,
            "formatted": location_query or "Center"
        }
    else:
        # First try direct ICAO lookup (handles "airports near EGTF" queries)
        icao = location_query.strip().upper()
        airport = ctx.model.airports.get(icao)
        if airport and hasattr(airport, 'navpoint') and airport.navpoint:
            geocode = {
                "lat": airport.navpoint.latitude,
                "lon": airport.navpoint.longitude,
                "formatted": f"{airport.name} ({icao})"
            }
        else:
            # Not found as ICAO - try geocoding as location name
            geocode = _geoapify_geocode(location_query)
            if not geocode:
                return {
                    "found": False,
                    "pretty": f"Could not geocode '{location_query}'. Ensure GEOAPIFY_API_KEY is set and the query is valid."
                }

    center_point = NavPoint(latitude=geocode["lat"], longitude=geocode["lon"], name=geocode["formatted"])

    # Compute distances to all airports and filter by radius
    candidate_airports: List[Airport] = []
    point_distances: Dict[str, float] = {}
    for airport in ctx.model.airports:
        if not getattr(airport, "navpoint", None):
            continue
        try:
            _, distance_nm = airport.navpoint.haversine_distance(center_point)
        except Exception:
            continue
        if distance_nm <= float(max_distance_nm):
            candidate_airports.append(airport)
            point_distances[airport.ident] = float(distance_nm)

    # Filter and sort using common pipeline
    persona_id = kwargs.pop("_persona_id", None)
    result = _filter_and_sort_airports(
        ctx=ctx,
        airports=candidate_airports,
        filters=filters,
        include_large_airports=include_large_airports,
        priority_strategy=priority_strategy,
        priority_context_extra={"point_distances": point_distances},
        max_hours_notice=max_hours_notice,
        max_results=100,
        persona_id=persona_id,
    )

    # Build summaries with distance and notification info
    airports: List[Dict[str, Any]] = []
    for a in result.airports:
        summary = _airport_summary(a)
        summary["distance_nm"] = round(point_distances.get(a.ident, 0.0), 2)
        if a.ident in result.notification_infos:
            summary["notification"] = result.notification_infos[a.ident].to_summary_dict()
        airports.append(summary)

    total_count = len(airports)
    airports_for_llm = airports[:max_results]

    # Generate filter profile for UI synchronization
    filter_profile = _build_filter_profile(
        {"location_query": location_query, "radius_nm": max_distance_nm},
        filters,
        max_hours_notice,
    )

    return {
        "found": True,
        "count": total_count,
        "center": {"lat": geocode["lat"], "lon": geocode["lon"], "label": geocode["formatted"]},
        "airports": airports_for_llm,  # Limited for LLM
        "filter_profile": filter_profile,
        "visualization": {
            "type": "point_with_markers",
            "point": {
                "label": geocode["formatted"],
                "lat": geocode["lat"],
                "lon": geocode["lon"],
            },
            "markers": airports_for_llm,  # Only recommended airports for highlighting
            "radius_nm": max_distance_nm  # For UI to trigger search with same radius
        }
    }


def find_airports_near_route(
    ctx: ToolContext,
    from_location: str,
    to_location: str,
    via: Optional[List[str]] = None,
    max_distance_nm: float = 50.0,
    max_results: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    include_large_airports: bool = False,
    priority_strategy: str = "persona_optimized",
    max_hours_notice: Optional[int] = None,  # Filter by notification requirements
    max_leg_time_hours: Optional[float] = None,  # Filter by max flight time from departure
    cruise_speed_kts: Optional[float] = None,  # Cruise speed for time-based filtering
    aircraft_type: Optional[str] = None,  # Aircraft type for speed lookup
    **kwargs: Any,  # Accept _persona_id injected by ToolRunner
) -> Dict[str, Any]:
    """
    List airports within a specified distance from a route between two or more locations, with optional airport filters.

    **USE THIS TOOL when user asks about airports "between" two or more locations.**

    **IMPORTANT - Pass location names exactly as user provides them, INCLUDING country/region context:**
    - Pass ICAO codes as-is (e.g., "LFPO", "EGKB", "EDDM")
    - Pass location names WITH COUNTRY if user mentions it - DO NOT strip country context
    - The tool will automatically geocode location names and find the nearest airport
    - Examples:
      - "between LFPO and Bromley" → from_location="LFPO", to_location="Bromley"
      - "between Paris and Vik in Iceland" → from_location="Paris", to_location="Vik, Iceland"
      - "Vik, Iceland" or "Vik in Iceland" → to_location="Vik, Iceland" (INCLUDE COUNTRY!)
      - "between LFPO and EDDM" → from_location="LFPO", to_location="EDDM"
      - "border entry between EGTF and LFMD with less than 24h notice" → use with point_of_entry=True, max_hours_notice=24

    **Multi-leg routes (via waypoints):**
    When user specifies intermediate stops or waypoints, use 'via' parameter:
    - via: List of intermediate waypoints in order (ICAO codes or location names)
    - Examples:
      - "from EDML via Straubing and Vilshofen to Schärding" → from_location="EDML", to_location="Schärding", via=["Straubing", "Vilshofen"]
      - "EGTF to LFMD via LFPB" → from_location="EGTF", to_location="LFMD", via=["LFPB"]

    **Time-based filtering:**
    When user asks for stops "within X hours flight", use max_leg_time_hours with speed:
    - max_leg_time_hours: Maximum flight time from departure (e.g., 3 for "within 3 hours")
    - cruise_speed_kts: Cruise speed in knots (e.g., 140)
    - aircraft_type: Aircraft type for speed lookup (e.g., "C172", "SR22")
    - If time is specified but no speed/aircraft, tool returns missing_info asking for speed
    - Examples:
      - "stop within 3h flight with my C172" → max_leg_time_hours=3, aircraft_type="C172"
      - "fuel stop within 2 hours at 140 knots" → max_leg_time_hours=2, cruise_speed_kts=140

    **Filters:**
    When user mentions fuel (e.g., AVGAS, Jet-A), customs/border crossing, runway type (paved/hard), IFR procedures, country, or notification requirements, you MUST include the corresponding filter:
    - has_avgas=True for AVGAS
    - has_jet_a=True for Jet-A
    - point_of_entry=True for customs
    - has_hard_runway=True for paved runways
    - has_procedures=True for IFR
    - country='XX' for specific country
    - max_hours_notice=24 for airports with <24h notification (or 48 for <48h, etc.)

    **By default, large commercial airports are excluded** (not suitable for GA).
    Set include_large_airports=True only if user explicitly asks for large/commercial airports.

    Useful for finding fuel stops, alternates, or customs stops along a route.
    """
    # Resolve cruise speed if time-based filtering requested
    max_enroute_distance_nm: Optional[float] = None
    resolved_speed: Optional[float] = None
    speed_source: Optional[str] = None

    if max_leg_time_hours is not None:
        resolved_speed, speed_source = resolve_cruise_speed(cruise_speed_kts, aircraft_type)
        if resolved_speed:
            max_enroute_distance_nm = max_leg_time_hours * resolved_speed
        else:
            # Time constraint specified but no speed - return missing_info
            return {
                "found": True,
                "count": 0,
                "airports": [],
                "missing_info": [{
                    "key": "cruise_speed",
                    "reason": f"Required to calculate {max_leg_time_hours}h flight range",
                    "prompt": "What's your cruise speed or aircraft type?",
                    "examples": ["120 knots", "Cessna 172", "SR22"],
                }],
                "filter_profile": {
                    "max_leg_time_hours": max_leg_time_hours,
                },
            }

    # Try to resolve both locations (with fallback to nearest airport via geocoding)
    from_result = _find_nearest_airport_in_db(ctx, from_location)
    to_result = _find_nearest_airport_in_db(ctx, to_location)

    if not from_result:
        return {
            "found": False,
            "error": f"Could not find or geocode departure location '{from_location}'. Please verify the ICAO code or location name.",
            "pretty": f"Could not find airport or location '{from_location}'.",
            "missing_info": [],
        }

    if not to_result:
        return {
            "found": False,
            "error": f"Could not find or geocode destination location '{to_location}'. Please verify the ICAO code or location name.",
            "pretty": f"Could not find airport or location '{to_location}'.",
            "missing_info": [],
        }

    from_airport = from_result["airport"]
    to_airport = to_result["airport"]

    # Build substitution notes if geocoding was used
    substitution_notes = []
    if from_result["was_geocoded"]:
        substitution_notes.append(
            f"Note: '{from_result['original_query']}' was geocoded to {from_result['geocoded_location']}. "
            f"Using nearest airport {from_airport.ident} ({from_airport.name}), {from_result['distance_nm']}nm away."
        )
    if to_result["was_geocoded"]:
        substitution_notes.append(
            f"Note: '{to_result['original_query']}' was geocoded to {to_result['geocoded_location']}. "
            f"Using nearest airport {to_airport.ident} ({to_airport.name}), {to_result['distance_nm']}nm away."
        )

    # Resolve via waypoints for multi-leg routes
    # Try RouteResolver first (handles both airports and nav waypoints like BILGO),
    # then fall back to airport lookup / geocoding for location names
    from euro_aip.models.route_resolver import RouteResolver
    from euro_aip.models.navpoint import NavPoint

    via_results = []
    if via:
        resolver = RouteResolver(ctx.model)
        for wp in via:
            # Try RouteResolver first (airports + waypoints)
            resolved_point = resolver.resolve_point(wp.strip().upper())
            if resolved_point:
                via_results.append({
                    "resolved_point": resolved_point,
                    "airport": None,
                    "original_query": wp,
                    "was_geocoded": False,
                })
            else:
                # Fall back to geocoding for location names
                wp_result = _find_nearest_airport_in_db(ctx, wp)
                if not wp_result:
                    return {
                        "found": False,
                        "error": f"Could not find or geocode waypoint '{wp}'. Please verify the ICAO code or location name.",
                        "pretty": f"Could not find airport or location '{wp}'.",
                        "missing_info": [],
                    }
                via_results.append({
                    "resolved_point": None,
                    "airport": wp_result["airport"],
                    "original_query": wp,
                    "was_geocoded": wp_result["was_geocoded"],
                })
                if wp_result["was_geocoded"]:
                    substitution_notes.append(
                        f"Note: '{wp_result['original_query']}' was geocoded to {wp_result['geocoded_location']}. "
                        f"Using nearest airport {wp_result['airport'].ident} ({wp_result['airport'].name}), {wp_result['distance_nm']}nm away."
                    )

    # Build full route using NavPoints for waypoints, ICAO strings for airports
    route_points: list = [from_airport.ident]
    for vr in via_results:
        if vr["resolved_point"]:
            rp = vr["resolved_point"]
            route_points.append(NavPoint(latitude=rp.latitude, longitude=rp.longitude, name=rp.name))
        else:
            route_points.append(vr["airport"].ident)
    route_points.append(to_airport.ident)

    results = ctx.model.find_airports_near_route(
        route_points,
        max_distance_nm
    )

    # Calculate total route distance for position-based sorting
    total_route_distance_nm = 0.0
    if hasattr(from_airport, 'navpoint') and hasattr(to_airport, 'navpoint'):
        try:
            _, total_route_distance_nm = from_airport.navpoint.haversine_distance(to_airport.navpoint)
        except Exception:
            pass  # Keep as 0.0 if calculation fails

    # Extract airports and build distance map for context
    airport_objects = [item["airport"] for item in results]
    segment_distances = {
        item["airport"].ident: float(item.get("segment_distance_nm") or 0.0) for item in results
    }
    enroute_distances = {
        item["airport"].ident: item.get("enroute_distance_nm")
        for item in results
        if item.get("enroute_distance_nm") is not None
    }

    # Filter and sort using common pipeline
    persona_id = kwargs.pop("_persona_id", None)
    result = _filter_and_sort_airports(
        ctx=ctx,
        airports=airport_objects,
        filters=filters,
        include_large_airports=include_large_airports,
        priority_strategy=priority_strategy,
        priority_context_extra={
            "segment_distances": segment_distances,
            "enroute_distances": enroute_distances,
            "total_route_distance_nm": total_route_distance_nm,
            "sort_by": "halfway",  # Prioritize airports near middle of route
        },
        max_hours_notice=max_hours_notice,
        max_results=100,
        persona_id=persona_id,
    )

    # Build summaries with distance and notification info
    airports: List[Dict[str, Any]] = []
    for airport in result.airports:
        summary = _airport_summary(airport)
        summary["segment_distance_nm"] = segment_distances.get(airport.ident, 0.0)
        if airport.ident in enroute_distances:
            summary["enroute_distance_nm"] = enroute_distances[airport.ident]
        if airport.ident in result.notification_infos:
            summary["notification"] = result.notification_infos[airport.ident].to_summary_dict()
        airports.append(summary)

    # Filter by max enroute distance (time-based constraint)
    if max_enroute_distance_nm is not None:
        airports = [
            a for a in airports
            if a.get("enroute_distance_nm") is not None
            and a["enroute_distance_nm"] <= max_enroute_distance_nm
        ]

    total_count = len(airports)
    airports_for_llm = airports[:max_results]

    # Generate filter profile for UI synchronization
    filter_profile = _build_filter_profile(
        {"route_distance": max_distance_nm},
        filters,
        max_hours_notice,
    )

    # Add time-based filter info if applicable
    if max_leg_time_hours is not None and resolved_speed is not None:
        filter_profile["max_leg_time_hours"] = max_leg_time_hours
        filter_profile["cruise_speed_kts"] = resolved_speed
        filter_profile["cruise_speed_source"] = speed_source
        filter_profile["max_enroute_distance_nm"] = max_enroute_distance_nm

    return {
        "count": total_count,
        "airports": airports_for_llm,  # Limited for LLM
        "filter_profile": filter_profile,  # Filter settings for UI sync
        "missing_info": [],  # No missing info on success
        "substitutions": {
            "from": {
                "original": from_location,
                "resolved": from_airport.ident,
                "was_geocoded": from_result["was_geocoded"],
                "geocoded_location": from_result.get("geocoded_location"),
                "distance_nm": from_result.get("distance_nm", 0.0)
            } if from_result["was_geocoded"] else None,
            "to": {
                "original": to_location,
                "resolved": to_airport.ident,
                "was_geocoded": to_result["was_geocoded"],
                "geocoded_location": to_result.get("geocoded_location"),
                "distance_nm": to_result.get("distance_nm", 0.0)
            } if to_result["was_geocoded"] else None,
            "via": [
                {
                    "original": via[i] if via else (vr["resolved_point"].name if vr["resolved_point"] else vr["airport"].ident),
                    "resolved": vr["resolved_point"].name if vr["resolved_point"] else vr["airport"].ident,
                    "was_geocoded": vr["was_geocoded"],
                    "geocoded_location": vr.get("geocoded_location"),
                    "distance_nm": vr.get("distance_nm", 0.0)
                }
                for i, vr in enumerate(via_results)
                if vr["was_geocoded"]
            ] if via_results else [],
        },
        "visualization": {
            "type": "route_with_markers",
            "route": {
                "from": {
                    "icao": from_airport.ident,
                    "name": from_airport.name,
                    "municipality": from_airport.municipality,
                    "lat": getattr(from_airport, "latitude_deg", None),
                    "lon": getattr(from_airport, "longitude_deg", None),
                },
                "to": {
                    "icao": to_airport.ident,
                    "name": to_airport.name,
                    "municipality": to_airport.municipality,
                    "lat": getattr(to_airport, "latitude_deg", None),
                    "lon": getattr(to_airport, "longitude_deg", None),
                },
                "via": [
                    {
                        "icao": vr["resolved_point"].name if vr["resolved_point"] else vr["airport"].ident,
                        "name": vr["resolved_point"].name if vr["resolved_point"] else vr["airport"].name,
                        "municipality": None if vr["resolved_point"] else getattr(vr["airport"], "municipality", None),
                        "lat": vr["resolved_point"].latitude if vr["resolved_point"] else getattr(vr["airport"], "latitude_deg", None),
                        "lon": vr["resolved_point"].longitude if vr["resolved_point"] else getattr(vr["airport"], "longitude_deg", None),
                        "type": vr["resolved_point"].point_type if vr["resolved_point"] else "airport",
                    }
                    for vr in via_results
                ] if via_results else [],
            },
            "markers": airports_for_llm,  # Only recommended airports for highlighting
            "radius_nm": max_distance_nm  # For UI to trigger search with same radius
        }
    }


def get_airport_details(
    ctx: ToolContext,
    icao_code: str,
    **kwargs: Any,  # Accept _persona_id injected by ToolRunner (not used by this tool)
) -> Dict[str, Any]:
    """Get comprehensive details about a specific airport including runways, procedures, facilities, and AIP information."""
    # Extract and ignore _persona_id (injected by ToolRunner, not used by this tool)
    kwargs.pop("_persona_id", None)

    icao = icao_code.strip().upper()
    a = ctx.model.airports.get(icao)

    if not a:
        return {"found": False, "pretty": f"Airport {icao} not found."}

    standardized = []
    for e in (a.get_standardized_entries() or []):
        if getattr(e, "std_field", None) and getattr(e, "value", None):
            standardized.append({
                "field": e.std_field,
                "value": e.value
            })

    runways = []
    for r in a.runways:
        runways.append({
            "le_ident": r.le_ident,
            "he_ident": r.he_ident,
            "length_ft": r.length_ft,
            "width_ft": r.width_ft,
            "surface": r.surface,
            "lighted": bool(getattr(r, "lighted", False)),
        })

    return {
        "found": True,
        "airport": _airport_summary(a),
        "runways": runways,
        "runway_summary": {
            "count": len(a.runways),
            "longest_ft": getattr(a, "longest_runway_length_ft", None),
            "has_hard_surface": bool(getattr(a, "has_hard_runway", False)),
        },
        "procedures": {"count": len(a.procedures)},
        "aip_data": standardized,
        "visualization": {
            "type": "marker_with_details",
            "marker": {
                "ident": a.ident,
                "lat": getattr(a, "latitude_deg", None),
                "lon": getattr(a, "longitude_deg", None),
                "zoom": 12
            }
        }
    }



# -----------------------------------------------------------------------------
# Notification Requirements
# -----------------------------------------------------------------------------

def get_notification_for_airport(
    ctx: ToolContext,
    icao: str,
    day_of_week: Optional[str] = None,
    **kwargs: Any,  # Accept _persona_id injected by ToolRunner (not used by this tool)
) -> Dict[str, Any]:
    """
    Get customs/immigration notification requirements for a specific airport.

    Use when user asks about notification requirements, customs, or when to
    notify for a specific airport.
    """
    # Extract and ignore _persona_id (injected by ToolRunner, not used by this tool)
    kwargs.pop("_persona_id", None)

    if not ctx.notification_service:
        return {
            "found": False,
            "icao": icao.upper(),
            "error": "Notification service not available.",
            "pretty": f"Notification service not available. Cannot look up {icao.upper()}."
        }
    return ctx.notification_service.get_notification_for_airport(icao, day_of_week)


# -----------------------------------------------------------------------------
# Flight Distance & Time Calculation
# -----------------------------------------------------------------------------

def calculate_flight_distance(
    ctx: ToolContext,
    from_location: str,
    to_location: str,
    cruise_speed_kts: Optional[float] = None,
    aircraft_type: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Calculate distance and estimated flight time between two airports or locations.

    **USE THIS TOOL when user asks about:**
    - Flight distance: "How far is EGTF from LFMD?"
    - Flight time: "How long to fly from London to Nice?"
    - Route planning: "What's the distance between Paris and Munich?"

    **Speed/Aircraft handling:**
    - If user specifies aircraft type (e.g., "with a C172"), use aircraft_type parameter
    - If user specifies speed (e.g., "at 140 knots"), use cruise_speed_kts parameter
    - If neither provided and user asks about TIME, tool returns distance and asks for speed
    - If user only asks about DISTANCE, no speed needed

    **Location resolution:**
    - Accepts ICAO codes (e.g., "EGTF", "LFMD")
    - Accepts city/location names (e.g., "Paris", "Nice, France")
    - Automatically finds nearest airport for non-ICAO locations

    Returns distance in nautical miles and estimated flight time if speed is known.
    """
    # Try to resolve both locations
    from_result = _find_nearest_airport_in_db(ctx, from_location)
    to_result = _find_nearest_airport_in_db(ctx, to_location)

    if not from_result:
        return {
            "found": False,
            "error": f"Could not find or geocode departure location '{from_location}'.",
            "missing_info": [{
                "key": "from_location",
                "reason": "Location not found in database or could not be geocoded",
                "prompt": f"Could not find '{from_location}'. Please provide an ICAO code or valid location name.",
                "examples": ["EGTF", "Paris", "Nice, France"],
            }],
        }

    if not to_result:
        return {
            "found": False,
            "error": f"Could not find or geocode destination location '{to_location}'.",
            "missing_info": [{
                "key": "to_location",
                "reason": "Location not found in database or could not be geocoded",
                "prompt": f"Could not find '{to_location}'. Please provide an ICAO code or valid location name.",
                "examples": ["LFMD", "Cannes", "Munich, Germany"],
            }],
        }

    from_airport = from_result["airport"]
    to_airport = to_result["airport"]

    # Calculate great circle distance
    distance_nm: Optional[float] = None
    if hasattr(from_airport, 'navpoint') and hasattr(to_airport, 'navpoint'):
        try:
            _, distance_nm = from_airport.navpoint.haversine_distance(to_airport.navpoint)
            distance_nm = round(distance_nm, 1)
        except Exception:
            pass

    if distance_nm is None:
        return {
            "found": False,
            "error": "Could not calculate distance between airports (missing coordinates).",
        }

    # Resolve cruise speed
    speed, speed_source = resolve_cruise_speed(cruise_speed_kts, aircraft_type)

    # Build response
    response: Dict[str, Any] = {
        "found": True,
        "from": {
            "icao": from_airport.ident,
            "name": from_airport.name,
            "municipality": from_airport.municipality,
            "lat": getattr(from_airport, "latitude_deg", None),
            "lon": getattr(from_airport, "longitude_deg", None),
        },
        "to": {
            "icao": to_airport.ident,
            "name": to_airport.name,
            "municipality": to_airport.municipality,
            "lat": getattr(to_airport, "latitude_deg", None),
            "lon": getattr(to_airport, "longitude_deg", None),
        },
        "distance_nm": distance_nm,
        "cruise_speed_kts": speed,
        "cruise_speed_source": speed_source,
        "estimated_time_hours": None,
        "estimated_time_formatted": None,
        "missing_info": [],
        "visualization": {
            "type": "route",
            "route": {
                "from": {
                    "icao": from_airport.ident,
                    "name": from_airport.name,
                    "lat": getattr(from_airport, "latitude_deg", None),
                    "lon": getattr(from_airport, "longitude_deg", None),
                },
                "to": {
                    "icao": to_airport.ident,
                    "name": to_airport.name,
                    "lat": getattr(to_airport, "latitude_deg", None),
                    "lon": getattr(to_airport, "longitude_deg", None),
                },
            },
        },
    }

    # Add substitution notes if locations were geocoded
    if from_result["was_geocoded"] or to_result["was_geocoded"]:
        response["substitutions"] = {
            "from": {
                "original": from_location,
                "resolved": from_airport.ident,
                "was_geocoded": from_result["was_geocoded"],
                "geocoded_location": from_result.get("geocoded_location"),
                "distance_nm": from_result.get("distance_nm", 0.0),
            } if from_result["was_geocoded"] else None,
            "to": {
                "original": to_location,
                "resolved": to_airport.ident,
                "was_geocoded": to_result["was_geocoded"],
                "geocoded_location": to_result.get("geocoded_location"),
                "distance_nm": to_result.get("distance_nm", 0.0),
            } if to_result["was_geocoded"] else None,
        }

    # Calculate time if speed is known
    if speed:
        time_hours = distance_nm / speed
        response["estimated_time_hours"] = round(time_hours, 2)
        response["estimated_time_formatted"] = format_time(time_hours)
    else:
        # No speed provided - add missing_info for formatter to ask
        response["missing_info"] = [{
            "key": "cruise_speed",
            "reason": "Required to calculate flight time",
            "prompt": "What's your cruise speed or aircraft type?",
            "examples": ["120 knots", "Cessna 172", "SR22"],
        }]

    return response


# =============================================================================
# SECTION 6: DATA COVERAGE
# =============================================================================

def get_data_coverage(
    ctx: ToolContext,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Get AIP data coverage and freshness per country.

    Returns which countries have AIP data (procedures, frequencies, etc.),
    when it was last updated (AIRAC cycle), and how many airports are covered.
    Also lists countries that only have basic airport metadata (no AIP data).

    Use this to assess data reliability before flight planning. Countries with
    recent AIRAC dates have current information. Countries with older dates or
    no AIP data should be cross-checked with official sources.
    """
    if not ctx.storage:
        return {
            "available": False,
            "message": "Data coverage information not available (no database storage).",
        }

    coverage_rows = ctx.storage.get_country_coverage()

    if not coverage_rows:
        return {
            "available": True,
            "countries_with_aip_data": [],
            "countries_metadata_only": [],
            "message": "No per-country coverage recorded yet. Run a data update to populate.",
        }

    # Build set of countries that have AIP coverage
    countries_with_aip = []
    covered_isos = set()
    for row in coverage_rows:
        covered_isos.add(row["country_iso"])
        countries_with_aip.append({
            "country_iso": row["country_iso"],
            "airac_date": row["airac_date"],
            "updated_at": row["updated_at"],
            "airports_with_aip_data": row["airports_count"],
        })

    # Find countries that have airports but no AIP data
    all_countries = ctx.model.airports.group_by(lambda a: a.iso_country or 'unknown')
    metadata_only = []
    for country_iso in sorted(all_countries.keys()):
        if country_iso == 'unknown' or country_iso in covered_isos:
            continue
        metadata_only.append({
            "country_iso": country_iso,
            "airports_count": len(all_countries[country_iso]),
        })

    return {
        "available": True,
        "countries_with_aip_data": countries_with_aip,
        "countries_metadata_only": metadata_only,
    }


# =============================================================================
# SECTION 6b: AIP FIELD TOOLS
# =============================================================================
#
# NOTE: Helpers prefixed with _aip_ contain logic that should eventually be
# pushed upstream into the euro_aip library (DatabaseStorage / AirportCollection).
# They are isolated here for easy extraction.  See future-euroaip-update.md.
# =============================================================================

import logging as _logging
import sqlite3 as _sqlite3
from datetime import datetime as _datetime, date as _date
from collections import defaultdict as _defaultdict

_aip_logger = _logging.getLogger(__name__)

# Module-level cache for _aip_collect_std_fields to avoid repeated full scans.
# Keyed by id(model) so it invalidates when the model object changes.
_aip_field_catalog_cache: Dict[int, Dict[int, Dict[str, Any]]] = {}


# -----------------------------------------------------------------------------
# AIP Field Helpers  (candidates for euro_aip library — see future-euroaip-update.md)
# -----------------------------------------------------------------------------

def _aip_collect_std_fields(model: Any) -> Dict[str, Any]:
    """Collect distinct standard fields across all airports.

    Returns dict keyed by std_field_id (int) → {std_field, section, count}.

    Results are cached per model instance to avoid repeated full-airport scans.

    NOTE: Should become ``model.airports.distinct_std_fields()`` in euro_aip.
    """
    cache_key = id(model)
    if cache_key in _aip_field_catalog_cache:
        return _aip_field_catalog_cache[cache_key]

    field_info: Dict[int, Dict[str, Any]] = {}
    for airport in model.airports.with_aip_data():
        seen_ids: set = set()  # deduplicate per-airport
        for entry in airport.aip_entries:
            fid = getattr(entry, "std_field_id", None)
            fname = getattr(entry, "std_field", None)
            if fid is None or fname is None:
                continue
            if fid not in field_info:
                field_info[fid] = {
                    "std_field_id": fid,
                    "std_field": fname,
                    "section": getattr(entry, "section", None),
                    "airport_count": 0,
                }
            if fid not in seen_ids:
                field_info[fid]["airport_count"] += 1
                seen_ids.add(fid)

    _aip_field_catalog_cache[cache_key] = field_info
    return field_info


def _aip_resolve_field(
    field: str,
    known_fields: Dict[int, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Resolve a user-supplied field name or numeric ID to a known field entry.

    Matching strategy (in order):
      1. Exact numeric ID
      2. Case-insensitive exact name match
      3. Case-insensitive substring match (first hit)

    Returns the field_info dict or None.
    """
    # 1. Numeric ID
    if field.isdigit():
        return known_fields.get(int(field))

    field_lower = field.lower().strip()

    # 2. Exact name match
    for info in known_fields.values():
        if info["std_field"].lower() == field_lower:
            return info

    # 3. Substring match
    for info in known_fields.values():
        if field_lower in info["std_field"].lower():
            return info

    return None


def _aip_get_field_values(
    model: Any,
    std_field_id: int,
    *,
    country: Optional[str] = None,
    icao_codes: Optional[List[str]] = None,
    max_results: int = 20,
) -> tuple:
    """Retrieve a specific AIP field value for airports matching criteria.

    Uses the euro_aip collection API for airport selection.

    Returns (results_list, total_count) where total_count is the number of
    matching airports before the max_results limit is applied.

    NOTE: Should become a collection method in euro_aip
    (e.g. ``airports.by_country("FR").aip_field(302)``).
    """
    airports = model.airports.with_aip_data()

    if country:
        airports = airports.by_country(country.upper())

    if icao_codes:
        icao_set = {c.upper() for c in icao_codes}
        airports = airports.filter(lambda a: a.ident in icao_set)

    results: List[Dict[str, Any]] = []
    total_count = 0
    for airport in airports:
        for entry in airport.aip_entries:
            if getattr(entry, "std_field_id", None) == std_field_id:
                total_count += 1
                if len(results) < max_results:
                    results.append({
                        "icao": airport.ident,
                        "name": airport.name,
                        "country": airport.iso_country,
                        "value": getattr(entry, "value", None),
                        "source": getattr(entry, "source", None),
                    })
                break  # one value per airport

    return results, total_count


def _aip_get_field_changes(
    storage: Any,
    std_field_id: int,
    since_date: str,
    *,
    country: Optional[str] = None,
    icao_codes: Optional[List[str]] = None,
    max_results: int = 20,
) -> tuple:
    """Query aip_entries_changes for field modifications since a date.

    Requires raw SQL because euro_aip DatabaseStorage does not yet expose
    a change-query API.

    Returns (results_list, total_count) where total_count is the number of
    matching rows before the LIMIT is applied.

    NOTE: Should become ``storage.get_field_changes(field_id, since, country)``
    in euro_aip.  See future-euroaip-update.md.
    """
    db_path = getattr(storage, "database_path", None)
    if not db_path:
        return [], 0

    try:
        with _sqlite3.connect(db_path) as conn:
            conn.row_factory = _sqlite3.Row

            where_clause = """
                WHERE c.std_field_id = ?
                  AND c.changed_at >= ?
            """
            params: List[Any] = [std_field_id, since_date]

            if country:
                where_clause += """
                  AND c.airport_icao IN (
                      SELECT ident FROM airports WHERE iso_country = ?
                  )
                """
                params.append(country.upper())

            if icao_codes:
                placeholders = ",".join("?" for _ in icao_codes)
                where_clause += f" AND c.airport_icao IN ({placeholders})"
                params.extend(c.upper() for c in icao_codes)

            # Get total count before applying LIMIT
            count_query = f"""
                SELECT COUNT(*) FROM aip_entries_changes c
                {where_clause}
            """
            total_count = conn.execute(count_query, params).fetchone()[0]

            # Get limited results
            data_query = f"""
                SELECT
                    c.airport_icao,
                    c.old_value,
                    c.new_value,
                    c.changed_at,
                    c.source
                FROM aip_entries_changes c
                {where_clause}
                ORDER BY c.changed_at DESC LIMIT ?
            """
            rows = conn.execute(data_query, params + [max_results]).fetchall()

        return [
            {
                "icao": row["airport_icao"],
                "previous_value": row["old_value"],
                "new_value": row["new_value"],
                "changed_at": row["changed_at"],
                "source": row["source"],
            }
            for row in rows
        ], total_count
    except Exception as e:
        _aip_logger.warning("Failed to query aip_entries_changes: %s", e)
        return [], 0


def _aip_get_staleness(
    storage: Any,
    countries: Optional[set] = None,
) -> Dict[str, str]:
    """Get AIRAC dates for relevant countries.

    Uses ``storage.get_country_coverage()`` from euro_aip.
    """
    try:
        coverage_rows = storage.get_country_coverage()
    except Exception:
        return {}

    result: Dict[str, str] = {}
    for row in (coverage_rows or []):
        iso = row["country_iso"]
        if countries is None or iso in countries:
            result[iso] = row["airac_date"]
    return result


# -----------------------------------------------------------------------------
# AIP Field Tools (public interface)
# -----------------------------------------------------------------------------

def list_aip_fields(
    ctx: ToolContext,
    **kwargs: Any,
) -> Dict[str, Any]:
    """List all available AIP standard fields.

    Returns the set of standardized AIP fields present in the database,
    along with how many airports have data for each field.
    Use this to discover what fields are available before querying with
    query_aip_fields.
    """
    kwargs.pop("_persona_id", None)

    field_info = _aip_collect_std_fields(ctx.model)

    fields_list = sorted(field_info.values(), key=lambda f: f["std_field_id"])

    return {
        "fields": fields_list,
        "total_fields": len(fields_list),
        "total_airports_with_aip_data": ctx.model.airports.with_aip_data().count(),
    }


def query_aip_fields(
    ctx: ToolContext,
    field: str,
    country: Optional[str] = None,
    icao_codes: Optional[List[str]] = None,
    changed_since: Optional[str] = None,
    max_results: int = 20,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Query raw AIP field values for airports matching criteria.

    Retrieves the value of a specific AIP standard field across airports,
    optionally filtered by country or ICAO codes. When changed_since is
    provided, returns only airports where the field changed after that date,
    including old and new values.

    Common fields: Customs and immigration (302), Hotels (501),
    Restaurants (502), ATS (101), Maintenance, Type of Traffic permitted (207).

    Use list_aip_fields to discover all available fields.
    """
    kwargs.pop("_persona_id", None)

    # --- Resolve field ---
    known_fields = _aip_collect_std_fields(ctx.model)
    resolved = _aip_resolve_field(field, known_fields)

    if not resolved:
        return {
            "found": False,
            "error": f"Unknown AIP field: '{field}'",
            "hint": "Use list_aip_fields to see available fields.",
            "pretty": f"I couldn't find an AIP field matching '{field}'. "
                       "You can use list_aip_fields to see what's available.",
        }

    std_field_id = resolved["std_field_id"]
    std_field_name = resolved["std_field"]

    # --- Build result ---
    staleness: Dict[str, Any] = {}

    if changed_since:
        # Change history mode
        changes, total_matches = _aip_get_field_changes(
            ctx.storage,
            std_field_id,
            changed_since,
            country=country,
            icao_codes=icao_codes,
            max_results=max_results,
        )

        # Enrich with airport names from the model
        for change in changes:
            airport = ctx.model.airports.get(change["icao"])
            change["name"] = airport.name if airport else change["icao"]
            change["country"] = airport.iso_country if airport else None

        # Also include the current value for context
        if changes:
            current_lookup = {
                a.ident: next(
                    (e.value for e in a.aip_entries if getattr(e, "std_field_id", None) == std_field_id),
                    None,
                )
                for a in ctx.model.airports.with_aip_data()
                if a.ident in {c["icao"] for c in changes}
            }
            for change in changes:
                change["current_value"] = current_lookup.get(change["icao"])

        airports_result = changes
        staleness["changes_queried_since"] = changed_since
    else:
        # Normal value query mode
        airports_result, total_matches = _aip_get_field_values(
            ctx.model,
            std_field_id,
            country=country,
            icao_codes=icao_codes,
            max_results=max_results,
        )

    # --- Staleness info ---
    result_countries = {a.get("country") for a in airports_result if a.get("country")}
    if ctx.storage and result_countries:
        staleness["country_airac_dates"] = _aip_get_staleness(ctx.storage, result_countries)

    return {
        "found": True,
        "field": {
            "std_field": std_field_name,
            "std_field_id": std_field_id,
        },
        "airports": airports_result,
        "total_matches": total_matches,
        "returned": len(airports_result),
        "staleness": staleness,
    }


# =============================================================================
# SECTION 7: RULES TOOLS
# =============================================================================

# -----------------------------------------------------------------------------
# Country Rules
# -----------------------------------------------------------------------------

def answer_rules_question(
    ctx: ToolContext,
    country_code: str,
    question: str,
    tags: Optional[List[str]] = None,
    use_rag: bool = True,
) -> Dict[str, Any]:
    """
    Answer a specific question about aviation rules for a country.
    Uses LLM-based question matching (primary), RAG (fallback), or tag filtering.

    Args:
        country_code: ISO-2 country code (e.g., FR, GB)
        question: The user's actual question
        tags: Optional tags to filter results (used as fallback if RAG unavailable)
        use_rag: Use RAG semantic search (default: True). Falls back to tags if False or RAG unavailable.
    """
    country_code = country_code.upper()
    rules_manager = ctx.ensure_rules_manager()

    # Get all rules for this country (needed by both LLM matcher and tag fallback)
    all_rules = rules_manager.get_rules_for_country(
        country_code=country_code,
        tags=tags,
    )

    if not all_rules:
        available = ", ".join(rules_manager.get_available_countries())
        return {
            "found": False,
            "country_code": country_code,
            "count": 0,
            "retrieval_mode": "tags",
            "message": f"No rules found for {country_code}. Available countries: {available}"
        }

    # Primary: LLM-based question matching
    if ctx.question_matcher:
        try:
            matched_ids = ctx.question_matcher.match_questions(
                query=question,
                questions=all_rules,
            )
            if matched_ids:
                matched_id_set = set(matched_ids)
                matched_rules = [r for r in all_rules if r.get("question_id") in matched_id_set]

                formatted_lines = []
                for r in matched_rules:
                    q = r.get('question_text', '')
                    a = r.get('answer_html', r.get('answer', ''))
                    formatted_lines.append(f"**Q: {q}**\nA: {a}")

                return {
                    "found": True,
                    "country_code": country_code,
                    "count": len(matched_rules),
                    "retrieval_mode": "llm_match",
                    "rules": matched_rules,
                    "formatted_text": "\n\n".join(formatted_lines),
                }
            else:
                # LLM found no relevant questions — return explicit "not found"
                return {
                    "found": False,
                    "country_code": country_code,
                    "count": 0,
                    "retrieval_mode": "llm_match",
                    "message": (
                        f"No rules in the database match this question for {country_code}. "
                        "The rules database covers common VFR/IFR regulatory topics."
                    ),
                }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"LLM question matching failed, falling back: {e}"
            )

    # Fallback: RAG-based retrieval
    if use_rag and ctx.rules_rag:
        try:
            results = ctx.rules_rag.retrieve_rules(
                query=question,
                countries=[country_code],
                top_k=5,
                similarity_threshold=0.3,
            )

            if results:
                formatted_lines = []
                for r in results:
                    q = r.get('question_text', '')
                    a = r.get('answer_html', r.get('answer', ''))
                    score = r.get('similarity', 0)
                    formatted_lines.append(f"**Q: {q}**\nA: {a}\n(relevance: {score:.2f})")

                return {
                    "found": True,
                    "country_code": country_code,
                    "count": len(results),
                    "retrieval_mode": "rag",
                    "rules": results,
                    "formatted_text": "\n\n".join(formatted_lines),
                }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"RAG retrieval failed, falling back to tags: {e}")

    # Final fallback: return all tag-filtered rules
    formatted_text = rules_manager.format_rules_for_display(all_rules, group_by_category=True)

    return {
        "found": True,
        "country_code": country_code,
        "count": len(all_rules),
        "retrieval_mode": "tags",
        "rules": all_rules[:20],
        "formatted_text": formatted_text,
    }


def browse_rules(
    ctx: ToolContext,
    country_code: str,
    tags: Optional[List[str]] = None,
    offset: int = 0,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Browse/list aviation rules for a country with pagination.
    Use this when user wants to see all rules in a category, not answer a specific question.

    Args:
        country_code: ISO-2 country code (e.g., FR, GB)
        tags: Optional tags to filter rules (e.g., ['flight_plan', 'transponder'])
        offset: Starting index for pagination (default: 0)
        limit: Maximum rules to return (default: 10, max: 50)
    """
    country_code = country_code.upper()
    limit = min(limit, 50)  # Cap at 50

    rules_manager = ctx.ensure_rules_manager()
    all_rules = rules_manager.get_rules_for_country(
        country_code=country_code,
        tags=tags
    )

    if not all_rules:
        available = ", ".join(rules_manager.get_available_countries())
        return {
            "found": False,
            "country_code": country_code,
            "total": 0,
            "message": f"No rules found for {country_code}. Available countries: {available}"
        }

    total = len(all_rules)
    paginated_rules = all_rules[offset:offset + limit]
    has_more = (offset + limit) < total

    formatted_text = rules_manager.format_rules_for_display(paginated_rules, group_by_category=True)
    categories = list({r.get('category', 'General') for r in paginated_rules})

    return {
        "found": True,
        "country_code": country_code,
        "total": total,
        "offset": offset,
        "limit": limit,
        "count": len(paginated_rules),
        "has_more": has_more,
        "rules": paginated_rules,
        "formatted_text": formatted_text,
        "categories": categories,
        "next_offset": offset + limit if has_more else None,
    }


# -----------------------------------------------------------------------------
# Comparison
# -----------------------------------------------------------------------------

def compare_rules_between_countries(
    ctx: ToolContext,
    countries: List[str],
    tags: Optional[List[str]] = None,
    question: Optional[str] = None,
    use_embeddings: bool = True,
) -> Dict[str, Any]:
    """
    Compare aviation rules and regulations between countries (iso-2 codes eg FR,GB,DE).
    Can be filtered by tags like flight_plan, transponder, airspace, etc.

    This tool returns DATA only - synthesis is done by the formatter node.
    Returns a _tool_type="comparison" marker for formatter routing.
    """
    countries = [c.upper() for c in countries]

    # Use QuestionMatcher to narrow to semantically relevant questions
    matched_question_ids = None
    if question and ctx.question_matcher:
        try:
            rules_manager = ctx.ensure_rules_manager()
            # Get rules from one country for question matching
            # (question_ids are shared across countries)
            ref_country = countries[0]
            ref_rules = rules_manager.get_rules_for_country(
                country_code=ref_country,
                tags=tags,
            )
            if ref_rules:
                matched_ids = ctx.question_matcher.match_questions(
                    query=question,
                    questions=ref_rules,
                )
                if matched_ids:
                    matched_question_ids = matched_ids
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Question matching for comparison failed, falling back to tags: {e}"
            )

    # Try embedding-based comparison first (smarter - detects semantic differences)
    # NOTE: Tool returns DATA only - synthesis is done by formatter
    if use_embeddings and ctx.comparison_service:
        try:
            result = ctx.comparison_service.compare_countries(
                countries=countries,
                tags=tags,
                question_ids=matched_question_ids,
                synthesize=False,  # Never synthesize in tool - formatter does this
            )

            # Build differences for response
            differences = result.differences if result.differences else []

            # If embedding comparison analyzed 0 questions (e.g., missing answers collection),
            # fall through to text-based comparison which can still use QuestionMatcher filtering
            if result.questions_analyzed == 0:
                import logging
                logging.getLogger(__name__).info(
                    "Embedding comparison analyzed 0 questions, falling back to text"
                )
                raise RuntimeError("No questions analyzed by embedding comparison")

            # Build rules_context for formatter (pre-formatted for synthesis prompt)
            rules_context_lines = []
            for i, diff in enumerate(differences, 1):
                rules_context_lines.append(f"\n### {i}. {diff.get('question_text', 'Unknown question')}")
                rules_context_lines.append(f"Tags: {', '.join(diff.get('tags', []))}")
                rules_context_lines.append(f"Semantic difference score: {diff.get('difference_score', 0):.2f}")
                rules_context_lines.append("")
                for cc, answer in diff.get("answers", {}).items():
                    rules_context_lines.append(f"**{cc}**: {answer}")
                rules_context_lines.append("")

            countries_str = ", ".join(countries)
            retrieval_mode = "embedding"
            if matched_question_ids is not None:
                retrieval_mode = "llm_match+embedding"
            return {
                "found": True,
                "countries": countries,
                "tags": tags,
                "total_questions": result.total_questions,
                "questions_analyzed": result.questions_analyzed,
                "filtered_by_embedding": result.filtered_by_embedding,
                "retrieval_mode": retrieval_mode,
                "differences": differences,
                "rules_context": "\n".join(rules_context_lines),  # For formatter synthesis
                "total_differences": len(differences),
                "message": f"Comparison between {countries_str} complete.",
                # Mark this as a comparison tool for formatter routing
                "_tool_type": "comparison",
            }
        except Exception as e:
            # Log and fall back to simple comparison
            import logging
            logging.getLogger(__name__).warning(
                f"Embedding comparison failed, falling back to text: {e}"
            )

    # Fall back to simple text-based comparison (only supports 2 countries)
    rules_manager = ctx.ensure_rules_manager()
    if len(countries) >= 2:
        comparison = rules_manager.compare_rules_between_countries(
            country1=countries[0],
            country2=countries[1],
        )
    else:
        comparison = {"differences": []}

    differences = comparison.get('differences', [])

    # Check if one country has no data at all — fall back to single-country answer
    total_c1 = comparison.get('total_rules_country1', 0)
    total_c2 = comparison.get('total_rules_country2', 0)
    missing_country = None
    available_country = None
    if total_c1 == 0 and total_c2 > 0:
        missing_country, available_country = countries[0], countries[1]
    elif total_c2 == 0 and total_c1 > 0:
        missing_country, available_country = countries[1], countries[0]

    if missing_country and available_country:
        # One country has no rules — provide available country's data instead
        available_rules = rules_manager.get_rules_for_country(
            country_code=available_country, tags=tags
        )
        # Narrow by QuestionMatcher if we have matched IDs
        if matched_question_ids is not None:
            matched_id_set = set(matched_question_ids)
            available_rules = [
                r for r in available_rules
                if r.get('question_id') in matched_id_set
            ]
        available_countries = ", ".join(rules_manager.get_available_countries())
        rules_context_lines = [
            f"**Note:** No rules data available for {missing_country}. "
            f"Available countries: {available_countries}.\n"
            f"Below are the rules for **{available_country}** on this topic:\n"
        ]
        for i, rule in enumerate(available_rules, 1):
            q = rule.get('question_text') or rule.get('question_id', 'Unknown')
            a = rule.get('answer_html', '')
            if a:
                rules_context_lines.append(f"### {i}. {q}")
                rules_context_lines.append(f"**{available_country}**: {a}\n")

        countries_str = ", ".join(countries)
        retrieval_mode = "llm_match+text" if matched_question_ids is not None else "text"
        return {
            "found": True,
            "countries": countries,
            "tags": tags,
            "comparison": comparison,
            "differences": [],
            "rules_context": "\n".join(rules_context_lines),
            "total_differences": 0,
            "filtered_by_embedding": False,
            "retrieval_mode": f"{retrieval_mode}+partial",
            "missing_countries": [missing_country],
            "message": (
                f"No rules data for {missing_country}. "
                f"Showing {available_country} rules only."
            ),
            "_tool_type": "comparison",
        }

    # Filter by matched question IDs if QuestionMatcher narrowed the set
    if matched_question_ids is not None:
        matched_id_set = set(matched_question_ids)
        differences = [
            d for d in differences
            if d.get('question_id') in matched_id_set
            or d.get('question') in matched_id_set  # text comparison uses 'question' field
        ]

    diff_count = len(differences)

    # Build rules_context from text-based comparison for formatter
    # Text comparison uses 'question' (not 'question_text') and stores answers
    # under country code keys (e.g., 'FR', 'DE') with 'answer' sub-field
    rules_context_lines = []
    for i, diff in enumerate(differences, 1):
        question_text = diff.get('question_text') or diff.get('question', 'Unknown')
        rules_context_lines.append(f"\n### {i}. {question_text}")
        for cc in countries:
            country_data = diff.get(cc)
            if isinstance(country_data, dict):
                answer = country_data.get('answer', '')
                if answer:
                    rules_context_lines.append(f"**{cc}**: {answer}")
            elif isinstance(country_data, str) and country_data:
                rules_context_lines.append(f"**{cc}**: {country_data}")
        rules_context_lines.append("")

    countries_str = ", ".join(countries)
    return {
        "found": True,
        "countries": countries,
        "tags": tags,
        "comparison": comparison,
        "differences": differences,
        "rules_context": "\n".join(rules_context_lines),  # For formatter synthesis
        "total_differences": diff_count,
        "filtered_by_embedding": False,
        "retrieval_mode": "llm_match+text" if matched_question_ids is not None else "text",
        "message": f"Comparison between {countries_str} complete.",
        "_tool_type": "comparison",
    }


def _compare_rules_between_countries_tool(
    ctx: ToolContext,
    countries: List[str],
    tags: Optional[List[str]] = None,
    question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wrapper that adds a human readable summary field expected by UI clients.
    Used as the actual handler in the tool registry.
    """
    result = compare_rules_between_countries(
        ctx, countries, tags=tags, question=question
    )
    if result.get("formatted_summary") and "pretty" not in result:
        result["pretty"] = result["formatted_summary"]
    return result


# =============================================================================
# SECTION 7: TOOL REGISTRY
# =============================================================================

def _build_shared_tool_specs() -> OrderedDictType[str, ToolSpec]:
    """
    Create the ordered manifest of shared tools.

    All tools have expose_to_llm=True and are available to the aviation agent and MCP server.

    AIRPORT TOOLS:
    - search_airports
    - find_airports_near_location
    - find_airports_near_route
    - get_airport_details
    - get_notification_for_airport
    - calculate_flight_distance

    RULES TOOLS:
    - answer_rules_question
    - browse_rules
    - compare_rules_between_countries
    """
    return OrderedDict([
        # -----------------------------------------------------------------
        # AIRPORT SEARCH & DISCOVERY
        # -----------------------------------------------------------------
        (
            "search_airports",
            {
                "name": "search_airports",
                "handler": search_airports,
                "description": _get_tool_description(search_airports, "search_airports"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Airport name, ICAO/IATA code, or city (e.g., 'Paris', 'LFPG').",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of airports to return. Default is 5. Use higher values (e.g., 10, 20) when user asks for 'all airports', 'more airports', or specifies a number.",
                            "default": 5,
                        },
                        "filters": {
                            "type": "object",
                            "description": "IMPORTANT: Use filters object to filter airports by characteristics mentioned in user's request. Examples: {'has_avgas': True} for AVGAS fuel, {'point_of_entry': True} for customs, {'has_hard_runway': True} for paved runways, {'has_procedures': True} for IFR, {'country': 'FR'} for country. ALWAYS include filters when user specifies characteristics.",
                        },
                        "include_large_airports": {
                            "type": "boolean",
                            "description": "Include large commercial airports (e.g., Heathrow, CDG, JFK). Default is False - large airports are excluded as they are not suitable for GA. Set to True ONLY if user explicitly asks for large/commercial/major airports.",
                            "default": False,
                        },
                        "priority_strategy": {
                            "type": "string",
                            "description": "Priority sorting strategy (e.g., persona_optimized).",
                            "default": "persona_optimized",
                        },
                    },
                    "required": ["query"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "find_airports_near_location",
            {
                "name": "find_airports_near_location",
                "handler": find_airports_near_location,
                "description": _get_tool_description(find_airports_near_location, "find_airports_near_location"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location_query": {
                            "type": "string",
                            "description": "Free-text location: city name (e.g., 'Paris', 'Zurich'), landmark (e.g., 'Lake Geneva'), address (e.g., 'Nice, France'), or coordinates (e.g., '48.8584, 2.2945'). DO NOT use ICAO codes here - use find_airports_near_route for ICAO-based route searches.",
                        },
                        "max_distance_nm": {
                            "type": "number",
                            "description": "Max distance from the location in nautical miles.",
                            "default": 50.0,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of airports to return. Default is 5. Use higher values (e.g., 10, 20) when user asks for 'all airports', 'more airports', or specifies a number.",
                            "default": 5,
                        },
                        "filters": {
                            "type": "object",
                            "description": "Airport filters (fuel, customs, runway length, etc.).",
                        },
                        "include_large_airports": {
                            "type": "boolean",
                            "description": "Include large commercial airports (e.g., Heathrow, CDG, JFK). Default is False - large airports are excluded as they are not suitable for GA. Set to True ONLY if user explicitly asks for large/commercial/major airports.",
                            "default": False,
                        },
                        "priority_strategy": {
                            "type": "string",
                            "description": "Priority sorting strategy (e.g., persona_optimized).",
                            "default": "persona_optimized",
                        },
                        "max_hours_notice": {
                            "type": "integer",
                            "description": "Filter by notification requirements. Only include airports that require at most this many hours of prior notice (e.g., 24 for airports with less than 24h notice, 48 for less than 48h).",
                        },
                    },
                    "required": ["location_query"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "find_airports_near_route",
            {
                "name": "find_airports_near_route",
                "handler": find_airports_near_route,
                "description": _get_tool_description(find_airports_near_route, "find_airports_near_route"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_location": {
                            "type": "string",
                            "description": "Departure location - pass EXACTLY as user provides it INCLUDING any country/region context. Can be ICAO code (e.g., 'LFPO') OR location name with country (e.g., 'Bromley, UK', 'Paris, France', 'Vik, Iceland'). DO NOT convert location names to ICAO codes. ALWAYS include country if user mentions it.",
                        },
                        "to_location": {
                            "type": "string",
                            "description": "Destination location - pass EXACTLY as user provides it INCLUDING any country/region context. Can be ICAO code (e.g., 'EDDM') OR location name with country (e.g., 'Vik, Iceland', 'Nice, France'). DO NOT convert location names to ICAO codes. ALWAYS include country if user mentions it.",
                        },
                        "via": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Intermediate waypoints along the route, in order. Each can be an ICAO code or location name with country context. Use when user specifies 'via', 'through', or 'stopping at' waypoints (e.g., ['LFPB'] for 'via LFPB', ['Straubing', 'Vilshofen'] for 'via Straubing and Vilshofen').",
                        },
                        "max_distance_nm": {
                            "type": "number",
                            "description": "Max distance from route centerline in nautical miles.",
                            "default": 50.0,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of airports to return. Default is 5. Use higher values (e.g., 10, 20) when user asks for 'all airports', 'more airports', or specifies a number.",
                            "default": 5,
                        },
                        "filters": {
                            "type": "object",
                            "description": "IMPORTANT: Use filters object to filter airports by characteristics mentioned in user's request. Examples: {'has_avgas': True} for AVGAS fuel, {'point_of_entry': True} for customs, {'has_hard_runway': True} for paved runways, {'has_procedures': True} for IFR, {'country': 'FR'} for country. ALWAYS include filters when user specifies characteristics like fuel type, customs, runway type, etc.",
                        },
                        "include_large_airports": {
                            "type": "boolean",
                            "description": "Include large commercial airports (e.g., Heathrow, CDG, JFK). Default is False - large airports are excluded as they are not suitable for GA. Set to True ONLY if user explicitly asks for large/commercial/major airports.",
                            "default": False,
                        },
                        "priority_strategy": {
                            "type": "string",
                            "description": "Priority sorting strategy (e.g., persona_optimized).",
                            "default": "persona_optimized",
                        },
                        "max_hours_notice": {
                            "type": "integer",
                            "description": "Filter by notification requirements. Only include airports that require at most this many hours of prior notice (e.g., 24 for airports with less than 24h notice, 48 for less than 48h). Use when user asks for airports with specific notification constraints.",
                        },
                        "max_leg_time_hours": {
                            "type": "number",
                            "description": "Maximum flight time from departure in hours. Filters airports to only those reachable within this time. Requires cruise_speed_kts or aircraft_type. Use when user asks for stops 'within X hours flight'.",
                        },
                        "cruise_speed_kts": {
                            "type": "number",
                            "description": "Cruise speed in knots for time-based filtering. Use when user specifies speed (e.g., '140 knots', 'at 120 kts').",
                        },
                        "aircraft_type": {
                            "type": "string",
                            "description": "Aircraft type for speed lookup (e.g., 'C172', 'SR22', 'PA28'). Use when user mentions their aircraft type for time-based filtering.",
                        },
                    },
                    "required": ["from_location", "to_location"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "get_airport_details",
            {
                "name": "get_airport_details",
                "handler": get_airport_details,
                "description": _get_tool_description(get_airport_details, "get_airport_details"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "icao_code": {
                            "type": "string",
                            "description": "Airport ICAO code (e.g., LFPG).",
                        },
                    },
                    "required": ["icao_code"],
                },
                "expose_to_llm": True,
            },
        ),
        # -----------------------------------------------------------------
        # NOTIFICATION
        # -----------------------------------------------------------------
        (
            "get_notification_for_airport",
            {
                "name": "get_notification_for_airport",
                "handler": get_notification_for_airport,
                "description": _get_tool_description(get_notification_for_airport, "get_notification_for_airport"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "icao": {
                            "type": "string",
                            "description": "Airport ICAO code (e.g., LFRG, LFPT).",
                        },
                        "day_of_week": {
                            "type": "string",
                            "description": "Optional day to get specific rules for (e.g., Saturday, Monday).",
                        },
                    },
                    "required": ["icao"],
                },
                "expose_to_llm": True,
            },
        ),
        # -----------------------------------------------------------------
        # FLIGHT DISTANCE & TIME
        # -----------------------------------------------------------------
        (
            "calculate_flight_distance",
            {
                "name": "calculate_flight_distance",
                "handler": calculate_flight_distance,
                "description": _get_tool_description(calculate_flight_distance, "calculate_flight_distance"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_location": {
                            "type": "string",
                            "description": "Departure location - ICAO code (e.g., 'EGTF') or location name (e.g., 'Paris', 'Nice, France').",
                        },
                        "to_location": {
                            "type": "string",
                            "description": "Destination location - ICAO code (e.g., 'LFMD') or location name (e.g., 'Cannes', 'Munich, Germany').",
                        },
                        "cruise_speed_kts": {
                            "type": "number",
                            "description": "Cruise speed in knots. Use when user specifies a speed (e.g., '140 knots', 'at 120 kts').",
                        },
                        "aircraft_type": {
                            "type": "string",
                            "description": "Aircraft type for speed lookup (e.g., 'C172', 'SR22', 'PA28', 'Cessna 182'). Use when user mentions their aircraft type.",
                        },
                    },
                    "required": ["from_location", "to_location"],
                },
                "expose_to_llm": True,
            },
        ),
        # -----------------------------------------------------------------
        # DATA COVERAGE
        # -----------------------------------------------------------------
        (
            "get_data_coverage",
            {
                "name": "get_data_coverage",
                "handler": get_data_coverage,
                "description": _get_tool_description(get_data_coverage, "get_data_coverage"),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
                "expose_to_llm": True,
            },
        ),
        # -----------------------------------------------------------------
        # AIP FIELD QUERY
        # -----------------------------------------------------------------
        (
            "list_aip_fields",
            {
                "name": "list_aip_fields",
                "handler": list_aip_fields,
                "description": _get_tool_description(list_aip_fields, "list_aip_fields"),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
                "expose_to_llm": True,
            },
        ),
        (
            "query_aip_fields",
            {
                "name": "query_aip_fields",
                "handler": query_aip_fields,
                "description": _get_tool_description(query_aip_fields, "query_aip_fields"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "description": "AIP standard field name or numeric ID. Common fields: 'Customs and immigration' (302), 'Hotels' (501), 'Restaurants' (502), 'ATS' (101), 'Maintenance', 'Type of Traffic permitted' (207). Use list_aip_fields to discover all available fields.",
                        },
                        "country": {
                            "type": "string",
                            "description": "ISO-2 country code to filter airports (e.g., 'FR', 'DE'). Use for country-wide queries like 'customs in France'.",
                        },
                        "icao_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Explicit list of airport ICAO codes. Use after a search or route tool to query fields for specific airports.",
                        },
                        "changed_since": {
                            "type": "string",
                            "description": "ISO date (YYYY-MM-DD). When set, returns only airports where this field changed after this date, with old and new values. Use for 'what changed recently' queries.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum airports to return. Default 20. Use higher for comprehensive queries.",
                            "default": 20,
                        },
                    },
                    "required": ["field"],
                },
                "expose_to_llm": True,
            },
        ),
        # -----------------------------------------------------------------
        # RULES
        # -----------------------------------------------------------------
        (
            "answer_rules_question",
            {
                "name": "answer_rules_question",
                "handler": answer_rules_question,
                "description": _get_tool_description(answer_rules_question, "answer_rules_question"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country_code": {
                            "type": "string",
                            "description": "ISO-2 country code (e.g., FR, GB).",
                        },
                        "question": {
                            "type": "string",
                            "description": "The user's question about aviation rules.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tags to help filter results (e.g., ['flight_plan', 'transponder']).",
                        },
                    },
                    "required": ["country_code", "question"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "browse_rules",
            {
                "name": "browse_rules",
                "handler": browse_rules,
                "description": _get_tool_description(browse_rules, "browse_rules"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country_code": {
                            "type": "string",
                            "description": "ISO-2 country code (e.g., FR, GB).",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional tags to filter rules (e.g., ['flight_plan', 'transponder']).",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Starting index for pagination (default: 0).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum rules to return (default: 10, max: 50).",
                        },
                    },
                    "required": ["country_code"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "compare_rules_between_countries",
            {
                "name": "compare_rules_between_countries",
                "handler": _compare_rules_between_countries_tool,
                "description": _get_tool_description(compare_rules_between_countries, "compare_rules_between_countries"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "countries": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of ISO-2 country codes to compare (e.g., ['FR', 'GB', 'DE']).",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of tags to filter (e.g., ['flight_plan', 'transponder']).",
                        },
                        "question": {
                            "type": "string",
                            "description": "The user's question about aviation rules to compare.",
                        },
                    },
                    "required": ["countries"],
                },
                "expose_to_llm": True,
            },
        ),
    ])


# Module-level tool registry (built once at import time)
_SHARED_TOOL_SPECS: OrderedDictType[str, ToolSpec] = _build_shared_tool_specs()


def get_shared_tool_specs() -> OrderedDictType[str, ToolSpec]:
    """
    Return the shared tool manifest.

    The mapping is ordered to keep registration deterministic.
    Tools are organized into categories - see _build_shared_tool_specs() for details.

    Returns:
        OrderedDict mapping tool names to ToolSpec dicts
    """
    return _SHARED_TOOL_SPECS.copy()
