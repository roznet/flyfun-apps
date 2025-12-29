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

RULES TOOLS (Section 6):
    - answer_rules_question: Answer specific questions about rules for a country (RAG-based)
    - browse_rules: Browse/list rules by category and tags with pagination
    - compare_rules_between_countries: Compare rules between two or more countries

TOOL REGISTRY (Section 7):
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
        "country": a.iso_country,
        "iso_country": a.iso_country,  # Include both for compatibility
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

    # Direct copy keys (values matter)
    for key in ["country", "max_runway_length_ft", "min_runway_length_ft", "max_landing_fee"]:
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
    max_distance_nm: float = 50.0,
    max_results: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    include_large_airports: bool = False,
    priority_strategy: str = "persona_optimized",
    max_hours_notice: Optional[int] = None,  # Filter by notification requirements
    **kwargs: Any,  # Accept _persona_id injected by ToolRunner
) -> Dict[str, Any]:
    """
    List airports within a specified distance from a direct route between two locations, with optional airport filters.

    **USE THIS TOOL when user asks about airports "between" two locations.**

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
    # Try to resolve both locations (with fallback to nearest airport via geocoding)
    from_result = _find_nearest_airport_in_db(ctx, from_location)
    to_result = _find_nearest_airport_in_db(ctx, to_location)

    if not from_result:
        return {
            "found": False,
            "error": f"Could not find or geocode departure location '{from_location}'. Please verify the ICAO code or location name.",
            "pretty": f"Could not find airport or location '{from_location}'."
        }

    if not to_result:
        return {
            "found": False,
            "error": f"Could not find or geocode destination location '{to_location}'. Please verify the ICAO code or location name.",
            "pretty": f"Could not find airport or location '{to_location}'."
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

    results = ctx.model.find_airports_near_route(
        [from_airport.ident, to_airport.ident],
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

    total_count = len(airports)
    airports_for_llm = airports[:max_results]

    # Generate filter profile for UI synchronization
    filter_profile = _build_filter_profile(
        {"route_distance": max_distance_nm},
        filters,
        max_hours_notice,
    )

    return {
        "count": total_count,
        "airports": airports_for_llm,  # Limited for LLM
        "filter_profile": filter_profile,  # Filter settings for UI sync
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
                }
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


# =============================================================================
# SECTION 6: RULES TOOLS
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
    Uses semantic search (RAG) to find the most relevant Q&A pairs.

    Args:
        country_code: ISO-2 country code (e.g., FR, GB)
        question: The user's actual question
        tags: Optional tags to filter results (used as fallback if RAG unavailable)
        use_rag: Use RAG semantic search (default: True). Falls back to tags if False or RAG unavailable.
    """
    country_code = country_code.upper()
    rules_manager = ctx.ensure_rules_manager()

    # Try RAG-based retrieval first
    if use_rag and ctx.rules_rag:
        try:
            results = ctx.rules_rag.retrieve_rules(
                query=question,
                countries=[country_code],
                top_k=5,
                similarity_threshold=0.3,
            )

            if results:
                # Format results for display
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

    # Fallback to tag-based retrieval
    rules = rules_manager.get_rules_for_country(
        country_code=country_code,
        tags=tags
    )

    if not rules:
        available = ", ".join(rules_manager.get_available_countries())
        return {
            "found": False,
            "country_code": country_code,
            "count": 0,
            "retrieval_mode": "tags",
            "message": f"No rules found for {country_code}. Available countries: {available}"
        }

    formatted_text = rules_manager.format_rules_for_display(rules, group_by_category=True)

    return {
        "found": True,
        "country_code": country_code,
        "count": len(rules),
        "retrieval_mode": "tags",
        "rules": rules[:20],  # Limit for tag-based (less targeted)
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
    use_embeddings: bool = True,
) -> Dict[str, Any]:
    """
    Compare aviation rules and regulations between countries (iso-2 codes eg FR,GB,DE).
    Can be filtered by tags like flight_plan, transponder, airspace, etc.

    This tool returns DATA only - synthesis is done by the formatter node.
    Returns a _tool_type="comparison" marker for formatter routing.
    """
    countries = [c.upper() for c in countries]

    # Try embedding-based comparison first (smarter - detects semantic differences)
    # NOTE: Tool returns DATA only - synthesis is done by formatter
    if use_embeddings and ctx.comparison_service:
        try:
            result = ctx.comparison_service.compare_countries(
                countries=countries,
                tags=tags,
                synthesize=False,  # Never synthesize in tool - formatter does this
            )

            # Build differences for response
            differences = result.differences if result.differences else []

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
            return {
                "found": True,
                "countries": countries,
                "tags": tags,
                "total_questions": result.total_questions,
                "questions_analyzed": result.questions_analyzed,
                "filtered_by_embedding": result.filtered_by_embedding,
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

    diff_count = len(comparison.get('differences', []))

    # Build rules_context from text-based comparison for formatter
    rules_context_lines = []
    for i, diff in enumerate(comparison.get('differences', []), 1):
        rules_context_lines.append(f"\n### {i}. {diff.get('question_text', 'Unknown')}")
        for cc, rule in diff.get('rules', {}).items():
            rules_context_lines.append(f"**{cc}**: {rule}")
        rules_context_lines.append("")

    countries_str = ", ".join(countries)
    return {
        "found": True,
        "countries": countries,
        "tags": tags,
        "comparison": comparison,
        "differences": comparison.get('differences', []),
        "rules_context": "\n".join(rules_context_lines),  # For formatter synthesis
        "total_differences": diff_count,
        "filtered_by_embedding": False,
        "message": f"Comparison between {countries_str} complete.",
        "_tool_type": "comparison",
    }


def _compare_rules_between_countries_tool(
    ctx: ToolContext,
    countries: List[str],
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Wrapper that adds a human readable summary field expected by UI clients.
    Used as the actual handler in the tool registry.
    """
    result = compare_rules_between_countries(
        ctx, countries, tags=tags
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
