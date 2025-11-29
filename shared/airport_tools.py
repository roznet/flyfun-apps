#!/usr/bin/env python3
"""
Shared airport tool logic used by both the MCP server and internal chatbot client.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, OrderedDict as OrderedDictType, TypedDict
import os
import urllib.parse
import json
import urllib.request

from euro_aip.models.euro_aip_model import EuroAipModel
from euro_aip.models.airport import Airport
from euro_aip.models.navpoint import NavPoint
from euro_aip.storage.database_storage import DatabaseStorage
from euro_aip.storage.enrichment_storage import EnrichmentStorage

from .rules_manager import RulesManager
from .filtering import FilterEngine
from .prioritization import PriorityEngine


ToolCallable = Callable[..., Dict[str, Any]]


class ToolSpec(TypedDict):
    """Metadata describing a shared tool."""

    name: str
    handler: ToolCallable
    description: str
    parameters: Dict[str, Any]
    expose_to_llm: bool


@dataclass
class ToolContext:
    """Context providing access to shared resources for tool execution."""

    model: EuroAipModel
    enrichment_storage: Optional[EnrichmentStorage] = None
    rules_manager: Optional[RulesManager] = None

    @classmethod
    def create(
        cls,
        db_path: str,
        rules_path: Optional[str] = None,
        load_rules: bool = True,
    ) -> "ToolContext":
        storage = DatabaseStorage(db_path)
        model = storage.load_model()
        enrichment = EnrichmentStorage(db_path)

        rules_manager = None
        if rules_path or load_rules:
            rules_manager = RulesManager(rules_path)
            if load_rules:
                rules_manager.load_rules()

        return cls(model=model, enrichment_storage=enrichment, rules_manager=rules_manager)

    def ensure_rules_manager(self) -> RulesManager:
        if not self.rules_manager:
            self.rules_manager = RulesManager()
            self.rules_manager.load_rules()
        elif not self.rules_manager.loaded:
            self.rules_manager.load_rules()
        return self.rules_manager


def _airport_summary(a: Airport) -> Dict[str, Any]:
    return {
        "ident": a.ident,
        "name": a.name,
        "municipality": a.municipality,
        "country": a.iso_country,
        "latitude_deg": getattr(a, "latitude_deg", None),
        "longitude_deg": getattr(a, "longitude_deg", None),
        "longest_runway_length_ft": getattr(a, "longest_runway_length_ft", None),
        "point_of_entry": bool(getattr(a, "point_of_entry", False)),
        "has_aip_data": bool(a.aip_entries) if hasattr(a, "aip_entries") else False,
        "has_procedures": bool(a.procedures),
        "has_hard_runway": bool(getattr(a, "has_hard_runway", False)),
    }


def search_airports(
    ctx: ToolContext,
    query: str,
    max_results: int = 50,
    filters: Optional[Dict[str, Any]] = None,
    priority_strategy: str = "cost_optimized",
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

    Returns matching airports sorted by priority.
    """
    q = query.upper().strip()
    matches: List[Airport] = []

    for a in ctx.model.airports.values():
        if (
            (q in a.ident)
            or (a.name and q in a.name.upper())
            or (getattr(a, "iata_code", None) and q in a.iata_code)
            or (a.municipality and q in a.municipality.upper())
        ):
            matches.append(a)
            if len(matches) >= 200:  # Get more candidates before filtering
                break

    # Apply filters using FilterEngine
    if filters:
        filter_engine = FilterEngine(context=ctx)
        matches = filter_engine.apply(matches, filters)

    # Apply priority sorting using PriorityEngine
    priority_engine = PriorityEngine(context=ctx)
    sorted_airports = priority_engine.apply(
        matches,
        strategy=priority_strategy,
        context={},
        max_results=max_results
    )

    # Convert to summaries
    airport_summaries = [_airport_summary(a) for a in sorted_airports]

    pretty = "No airports found." if not airport_summaries else (
        f"Found {len(airport_summaries)} airports matching '{query}':\n\n" +
        "\n\n".join(
            f"**{m['ident']} - {m['name']}**\nLocation: {m['municipality'] or 'Unknown'}, {m['country'] or 'Unknown'}"
            for m in airport_summaries[:20]  # Only show first 20 in text
        )
    )

    # Generate filter profile for UI synchronization
    filter_profile = {"search_query": query}
    if filters:
        if filters.get("country"):
            filter_profile["country"] = filters["country"]
        if filters.get("has_procedures"):
            filter_profile["has_procedures"] = True
        if filters.get("has_aip_data"):
            filter_profile["has_aip_data"] = True
        if filters.get("has_hard_runway"):
            filter_profile["has_hard_runway"] = True
        if filters.get("point_of_entry"):
            filter_profile["point_of_entry"] = True
        if filters.get("max_runway_length_ft"):
            filter_profile["max_runway_length_ft"] = filters["max_runway_length_ft"]
        if filters.get("min_runway_length_ft"):
            filter_profile["min_runway_length_ft"] = filters["min_runway_length_ft"]
        if filters.get("has_avgas"):
            filter_profile["has_avgas"] = True
        if filters.get("has_jet_a"):
            filter_profile["has_jet_a"] = True
        if filters.get("max_landing_fee"):
            filter_profile["max_landing_fee"] = filters["max_landing_fee"]

    # Limit for LLM to save tokens
    total_count = len(airport_summaries)
    airports_for_llm = airport_summaries[:20] if len(airport_summaries) > 20 else airport_summaries

    return {
        "count": total_count,
        "airports": airports_for_llm,  # Limited for LLM
        "pretty": pretty,
        "filter_profile": filter_profile,  # Filter settings for UI sync
        "visualization": {
            "type": "markers",
            "data": airport_summaries  # Show ALL matching airports on map
        }
    }


def find_airports_near_route(
    ctx: ToolContext,
    from_location: str,
    to_location: str,
    max_distance_nm: float = 50.0,
    filters: Optional[Dict[str, Any]] = None,
    priority_strategy: str = "cost_optimized",
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

    **Filters:**
    When user mentions fuel (e.g., AVGAS, Jet-A), customs/border crossing, runway type (paved/hard), IFR procedures, or country, you MUST include the corresponding filter:
    - has_avgas=True for AVGAS
    - has_jet_a=True for Jet-A
    - point_of_entry=True for customs
    - has_hard_runway=True for paved runways
    - has_procedures=True for IFR
    - country='XX' for specific country

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

    # Apply filters using FilterEngine
    if filters:
        filter_engine = FilterEngine(context=ctx)
        airport_objects = filter_engine.apply(airport_objects, filters)

    # Apply priority sorting using PriorityEngine
    priority_engine = PriorityEngine(context=ctx)
    sorted_airports = priority_engine.apply(
        airport_objects,
        strategy=priority_strategy,
        context={"segment_distances": segment_distances, "enroute_distances": enroute_distances},
        max_results=100  # Get more for full list, will limit to 20 for LLM later
    )

    # Convert to summaries with distance_nm
    airports: List[Dict[str, Any]] = []
    for airport in sorted_airports:
        summary = _airport_summary(airport)
        summary["segment_distance_nm"] = segment_distances.get(airport.ident, 0.0)
        if airport.ident in enroute_distances:
            summary["enroute_distance_nm"] = enroute_distances[airport.ident]
        airports.append(summary)

    pretty = (
        f"Found {len(airports)} airports within {max_distance_nm}nm of route {from_airport.ident} to {to_airport.ident}."
        if airports else
        f"No airports within {max_distance_nm}nm of {from_airport.ident}->{to_airport.ident}."
    )

    # Add substitution notes if any airports were geocoded
    if substitution_notes:
        pretty = "\n".join(substitution_notes) + "\n\n" + pretty

    # Limit airports sent to LLM to save tokens (keep all for visualization)
    # For route planning, top 20 airports sorted by priority is sufficient
    total_count = len(airports)
    airports_for_llm = airports[:20] if len(airports) > 20 else airports

    # Generate filter profile for UI synchronization
    filter_profile = {"route_distance": max_distance_nm}
    if filters:
        # Legacy filters
        if filters.get("country"):
            filter_profile["country"] = filters["country"]
        if filters.get("has_procedures"):
            filter_profile["has_procedures"] = True
        if filters.get("has_aip_data"):
            filter_profile["has_aip_data"] = True
        if filters.get("has_hard_runway"):
            filter_profile["has_hard_runway"] = True
        if filters.get("point_of_entry"):
            filter_profile["point_of_entry"] = True
        # New filters
        if filters.get("max_runway_length_ft"):
            filter_profile["max_runway_length_ft"] = filters["max_runway_length_ft"]
        if filters.get("min_runway_length_ft"):
            filter_profile["min_runway_length_ft"] = filters["min_runway_length_ft"]
        if filters.get("has_avgas"):
            filter_profile["has_avgas"] = True
        if filters.get("has_jet_a"):
            filter_profile["has_jet_a"] = True
        if filters.get("max_landing_fee"):
            filter_profile["max_landing_fee"] = filters["max_landing_fee"]

    return {
        "count": total_count,
        "airports": airports_for_llm,  # Limited for LLM
        "pretty": pretty,
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
                    "lat": getattr(from_airport, "latitude_deg", None),
                    "lon": getattr(from_airport, "longitude_deg", None),
                },
                "to": {
                    "icao": to_airport.ident,
                    "lat": getattr(to_airport, "latitude_deg", None),
                    "lon": getattr(to_airport, "longitude_deg", None),
                }
            },
            "markers": airports  # Include ALL airports for map visualization (not just LLM-limited subset)
        }
    }


def get_airport_details(ctx: ToolContext, icao_code: str) -> Dict[str, Any]:
    """Get comprehensive details about a specific airport including runways, procedures, facilities, and AIP information."""
    icao = icao_code.strip().upper()
    a = ctx.model.get_airport(icao)

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

    pretty_lines = [
        f"**{a.ident} - {a.name}**",
        f"City: {a.municipality or 'Unknown'}",
        f"Country: {a.iso_country or 'Unknown'}",
    ]
    if getattr(a, "latitude_deg", None) is not None and getattr(a, "longitude_deg", None) is not None:
        pretty_lines.append(f"Coordinates: {a.latitude_deg:.4f}, {a.longitude_deg:.4f}")
    if getattr(a, "elevation_ft", None) is not None:
        pretty_lines.append(f"Elevation: {a.elevation_ft}ft")
    pretty_lines += [
        "",
        f"Runways: {len(a.runways)} (longest {getattr(a, 'longest_runway_length_ft', 'Unknown')}ft)",
        f"Hard surface: {'Yes' if getattr(a,'has_hard_runway', False) else 'No'}",
        "",
        f"Procedures: {len(a.procedures)}",
        "",
        f"Border crossing point: {'Yes' if getattr(a,'point_of_entry', False) else 'No'}",
    ]

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
        "pretty": "\n".join(pretty_lines),
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


def get_border_crossing_airports(ctx: ToolContext, country: Optional[str] = None) -> Dict[str, Any]:
    """List all airports that are official border crossing points (with customs). Optionally filter by country."""
    airports_list = ctx.model.get_border_crossing_airports()

    if country:
        c = country.upper()
        airports_list = [a for a in airports_list if (a.iso_country or "").upper() == c]

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    all_airports: List[Dict[str, Any]] = []
    for a in airports_list:
        data = _airport_summary(a)
        country_code = data["country"] or "Unknown"
        grouped.setdefault(country_code, []).append(data)
        all_airports.append(data)

    pretty_lines = [
        f"**Border Crossing Airports{' in ' + country.upper() if country else ''}:**\n"
    ]
    for cc, arr in grouped.items():
        pretty_lines.append(f"**{cc}:**")
        for item in arr:
            label = item["ident"] + " - " + (item["name"] or "")
            city = item.get("municipality")
            pretty_lines.append(f"- {label}" + (f" ({city})" if city else ""))
        pretty_lines.append("")

    # Limit data sent to LLM: max 10 airports per country, max 5 countries (top 50 total)
    # Keep full data for visualization on map
    grouped_for_llm = {}
    airports_for_llm = []
    for cc, arr in list(grouped.items())[:5]:  # Max 5 countries
        limited_arr = arr[:10]  # Max 10 per country
        grouped_for_llm[cc] = limited_arr
        airports_for_llm.extend(limited_arr)

    # Generate filter profile for UI synchronization
    filter_profile = {"point_of_entry": True}  # Border crossing filter
    if country:
        filter_profile["country"] = country.upper()

    return {
        "count": len(all_airports),
        "by_country": grouped_for_llm,  # Limited for LLM
        "airports": airports_for_llm,  # Limited for LLM
        "pretty": "\n".join(pretty_lines),
        "filter_profile": filter_profile,  # Filter settings for UI sync
        "visualization": {
            "type": "markers",
            "data": airports_for_llm,  # Only show what LLM sees and recommends
            "style": "customs"
        }
    }


def get_airport_statistics(ctx: ToolContext, country: Optional[str] = None) -> Dict[str, Any]:
    """Get statistical information about airports, such as counts with customs, fuel types, or procedures. Optionally filter by country."""
    airports = ctx.model.get_airports_by_country(country.upper()) if country else list(ctx.model.airports.values())
    total = len(airports)

    stats = {
        "total_airports": total,
        "with_customs": sum(1 for a in airports if getattr(a, "point_of_entry", False)),
        "with_avgas": sum(1 for a in airports if getattr(a, "avgas", False)),
        "with_jet_a": sum(1 for a in airports if getattr(a, "jet_a", False)),
        "with_procedures": sum(1 for a in airports if a.procedures),
    }

    pct = lambda n: round((n / total * 100), 1) if total else 0.0
    stats.update({
        "with_customs_pct": pct(stats["with_customs"]),
        "with_avgas_pct": pct(stats["with_avgas"]),
        "with_jet_a_pct": pct(stats["with_jet_a"]),
        "with_procedures_pct": pct(stats["with_procedures"]),
    })

    pretty = [
        f"**Airport Statistics{' for ' + country.upper() if country else ''}:**",
        f"Total airports: {stats['total_airports']}",
        f"With customs: {stats['with_customs']} ({stats['with_customs_pct']}%)",
        f"With AVGAS: {stats['with_avgas']} ({stats['with_avgas_pct']}%)",
        f"With Jet A: {stats['with_jet_a']} ({stats['with_jet_a_pct']}%)",
        f"With procedures: {stats['with_procedures']} ({stats['with_procedures_pct']}%)",
    ]

    return {"stats": stats, "pretty": "\n".join(pretty)}


def get_airport_pricing(ctx: ToolContext, icao_code: str) -> Dict[str, Any]:
    """Get pricing data (landing fees and fuel prices) from airfield.directory, including common aircraft types and currency information."""
    if not ctx.enrichment_storage:
        raise RuntimeError("Enrichment storage not available in tool context.")

    icao = icao_code.strip().upper()
    pricing = ctx.enrichment_storage.get_pricing_data(icao)

    if not pricing:
        return {
            "found": False,
            "icao_code": icao,
            "pretty": f"No pricing data available for {icao}. Data may not be in airfield.directory or not yet synced."
        }

    pretty = [
        f"**Pricing for {icao}**",
        f"Source: {pricing.get('source', 'airfield.directory')}",
        f"Currency: {pricing.get('currency', 'N/A')}",
        ""
    ]

    if any([pricing.get('landing_fee_c172'), pricing.get('landing_fee_da42'),
            pricing.get('landing_fee_pc12'), pricing.get('landing_fee_sr22')]):
        pretty.append("**Landing Fees:**")
        if pricing.get('landing_fee_c172'):
            pretty.append(f"  C172: {pricing['landing_fee_c172']} {pricing.get('currency', '')}")
        if pricing.get('landing_fee_da42'):
            pretty.append(f"  DA42: {pricing['landing_fee_da42']} {pricing.get('currency', '')}")
        if pricing.get('landing_fee_sr22'):
            pretty.append(f"  SR22: {pricing['landing_fee_sr22']} {pricing.get('currency', '')}")
        if pricing.get('landing_fee_pc12'):
            pretty.append(f"  PC12: {pricing['landing_fee_pc12']} {pricing.get('currency', '')}")
        pretty.append("")

    if any([pricing.get('avgas_price'), pricing.get('jeta1_price'), pricing.get('superplus_price')]):
        pretty.append("**Fuel Prices:**")
        if pricing.get('avgas_price'):
            pretty.append(f"  AVGAS: {pricing['avgas_price']} {pricing.get('currency', '')}/L")
        if pricing.get('jeta1_price'):
            pretty.append(f"  Jet A1: {pricing['jeta1_price']} {pricing.get('currency', '')}/L")
        if pricing.get('superplus_price'):
            pretty.append(f"  SuperPlus: {pricing['superplus_price']} {pricing.get('currency', '')}/L")
        if pricing.get('fuel_provider'):
            pretty.append(f"  Provider: {pricing['fuel_provider']}")
        pretty.append("")

    if pricing.get('payment_available'):
        pretty.append("Payment: Available")
    if pricing.get('ppr_available'):
        pretty.append("PPR: Available")
    if pricing.get('last_updated'):
        pretty.append(f"\nLast updated: {pricing['last_updated']}")

    return {
        "found": True,
        "icao_code": icao,
        "pricing": pricing,
        "pretty": "\n".join(pretty)
    }


def get_pilot_reviews(ctx: ToolContext, icao_code: str, limit: int = 10) -> Dict[str, Any]:
    """Get community pilot reviews (PIREPs) from airfield.directory, including ratings, comments, and review metadata."""
    if not ctx.enrichment_storage:
        raise RuntimeError("Enrichment storage not available in tool context.")

    icao = icao_code.strip().upper()
    reviews = ctx.enrichment_storage.get_pilot_reviews(icao, limit)

    if not reviews:
        return {
            "found": False,
            "icao_code": icao,
            "count": 0,
            "pretty": f"No pilot reviews available for {icao}."
        }

    ratings = [r['rating'] for r in reviews if r.get('rating')]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    pretty = [
        f"**Pilot Reviews for {icao}**",
        f"Total reviews: {len(reviews)}",
        f"Average rating: {avg_rating:.1f}/5.0 ⭐" if avg_rating else "Average rating: N/A",
        ""
    ]

    for i, review in enumerate(reviews, 1):
        rating_stars = "⭐" * review.get('rating', 0)
        author = review.get('author_name') or "Anonymous"
        pretty.append(f"**Review {i}** - {rating_stars} ({review.get('rating')}/5) by {author}")

        comment = (review.get('comment_en') or
                   review.get('comment_de') or
                   review.get('comment_fr') or
                   review.get('comment_it') or
                   review.get('comment_es') or
                   review.get('comment_nl'))

        if comment:
            comment_display = comment[:200] + "..." if len(comment) > 200 else comment
            pretty.append(f'  "{comment_display}"')

        if review.get('created_at'):
            pretty.append(f"  Date: {review['created_at'][:10]}")

        pretty.append("")

    return {
        "found": True,
        "icao_code": icao,
        "count": len(reviews),
        "average_rating": avg_rating,
        "reviews": reviews,
        "pretty": "\n".join(pretty)
    }


def get_fuel_prices(ctx: ToolContext, icao_code: str) -> Dict[str, Any]:
    """Get fuel availability and prices from airfield.directory, showing which fuel types are available and any known prices."""
    if not ctx.enrichment_storage:
        raise RuntimeError("Enrichment storage not available in tool context.")

    icao = icao_code.strip().upper()

    fuels = ctx.enrichment_storage.get_fuel_availability(icao)
    pricing = ctx.enrichment_storage.get_pricing_data(icao)

    if not fuels and not pricing:
        return {
            "found": False,
            "icao_code": icao,
            "pretty": f"No fuel data available for {icao}."
        }

    fuel_list = []
    for fuel in fuels or []:
        fuel_type = fuel.get('fuel_type', 'Unknown')
        price = None
        currency = None
        if pricing:
            currency = pricing.get('currency', 'EUR')
            if 'avgas' in fuel_type.lower():
                price = pricing.get('avgas_price')
            elif 'jeta1' in fuel_type.lower() or 'jet a1' in fuel_type.lower():
                price = pricing.get('jeta1_price')
            elif 'super' in fuel_type.lower():
                price = pricing.get('superplus_price')

        fuel_list.append({
            "fuel_type": fuel_type,
            "available": bool(fuel.get('available')),
            "price": price,
            "currency": currency,
            "provider": fuel.get('provider')
        })

    pretty = [f"**Fuel Information for {icao}**", ""]
    for item in fuel_list:
        line = f"  ✓ {item['fuel_type']}"
        if item["price"]:
            line += f" - {item['price']} {item.get('currency', '')}/L"
        if item["provider"]:
            line += f" (Provider: {item['provider']})"
        pretty.append(line)
    pretty.append("")

    if pricing:
        if pricing.get('fuel_provider'):
            pretty.append(f"**Fuel Provider:** {pricing['fuel_provider']}")
        if pricing.get('payment_available'):
            pretty.append("**Payment:** Available")
        if pricing.get('ppr_available'):
            pretty.append("**PPR:** Required")
        if pricing.get('last_updated'):
            pretty.append(f"\n**Last Updated:** {pricing['last_updated']}")

    return {
        "found": True,
        "icao_code": icao,
        "fuels": fuel_list,
        "pricing": pricing,
        "pretty": "\n".join(pretty)
    }


def list_rules_for_country(
    ctx: ToolContext,
    country_code: str,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """List aviation rules and regulations for a specific country (iso-2 code eg FR,GB), including customs, flight plans, and operational requirements. Can be filtered by category like IFR/VFR, airspace, etc."""
    rules_manager = ctx.ensure_rules_manager()
    rules = rules_manager.get_rules_for_country(
        country_code=country_code,
        category=category,
        tags=tags
    )

    if not rules:
        available = ", ".join(rules_manager.get_available_countries())
        return {
            "found": False,
            "country_code": country_code.upper(),
            "count": 0,
            "message": f"No rules found for {country_code.upper()}. Available countries: {available}"
        }

    formatted_text = rules_manager.format_rules_for_display(rules, group_by_category=True)
    categories = list({r.get('category', 'General') for r in rules})

    return {
        "found": True,
        "country_code": country_code.upper(),
        "count": len(rules),
        "rules": rules[:50],
        "formatted_text": formatted_text,
        "categories": categories
    }


def compare_rules_between_countries(
    ctx: ToolContext,
    country1: str,
    country2: str,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """Compare aviation rules and regulations between two countries (iso-2 code eg FR,GB) and highlight differences in answers. Can be filtered by category like IFR/VFR, airspace, etc."""
    rules_manager = ctx.ensure_rules_manager()
    comparison = rules_manager.compare_rules_between_countries(
        country1=country1,
        country2=country2,
        category=category
    )

    diff_count = len(comparison.get('differences', []))

    return {
        "found": True,
        "comparison": comparison,
        "formatted_summary": comparison.get('summary', ''),
        "total_differences": diff_count,
        "message": f"Comparison between {country1.upper()} and {country2.upper()} complete."
    }


def get_answers_for_questions(ctx: ToolContext, question_ids: List[str]) -> Dict[str, Any]:
    """Get rule answers for specific question IDs, including per-country responses, categories, and tags."""
    rules_manager = ctx.ensure_rules_manager()
    items: List[Dict[str, Any]] = []
    for qid in question_ids or []:
        question = rules_manager.question_map.get(qid)
        if not question:
            continue
        items.append({
            "question_id": qid,
            "question_text": question.get("question_text"),
            "category": question.get("category"),
            "tags": question.get("tags") or [],
            "answers_by_country": question.get("answers_by_country", {})
        })

    pretty_lines: List[str] = []
    for item in items:
        pretty_lines.append(f"**{item['question_text']}**")
        answers = item.get("answers_by_country") or {}
        for cc, ans in sorted(answers.items()):
            pretty_lines.append(f"- {cc}: {ans.get('answer_html') or '(no answer)'}")
        pretty_lines.append("")

    return {
        "count": len(items),
        "items": items,
        "pretty": "\n".join(pretty_lines)
    }


def list_rule_categories_and_tags(ctx: ToolContext) -> Dict[str, Any]:
    """List available aviation rule categories and tags from the rules store."""
    rules_manager = ctx.ensure_rules_manager()
    categories = sorted(rules_manager.rules_index.get("categories", {}).keys())
    tags = sorted(rules_manager.rules_index.get("tags", {}).keys())
    by_category = rules_manager.rules_index.get("categories", {})
    by_tag = rules_manager.rules_index.get("tags", {})

    pretty = ["**Categories:**"]
    for c in categories:
        pretty.append(f"- {c} ({len(by_category.get(c, []))})")
    pretty.append("")
    pretty.append("**Tags:**")
    for t in tags:
        pretty.append(f"- {t} ({len(by_tag.get(t, []))})")

    return {
        "categories": categories,
        "tags": tags,
        "counts": {
            "by_category": {c: len(by_category.get(c, [])) for c in categories},
            "by_tag": {t: len(by_tag.get(t, [])) for t in tags},
        },
        "pretty": "\n".join(pretty),
    }


def list_rule_countries(ctx: ToolContext) -> Dict[str, Any]:
    """List available countries (ISO-2 codes) present in the aviation rules store."""
    rules_manager = ctx.ensure_rules_manager()
    countries = rules_manager.get_available_countries()
    pretty = "**Rule Countries (ISO-2):**\n" + ("\n".join(f"- {c}" for c in countries) if countries else "(none)")
    return {"count": len(countries), "items": countries, "pretty": pretty}


def _compare_rules_between_countries_tool(
    ctx: ToolContext,
    country1: str,
    country2: str,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wrapper that adds a human readable summary field expected by UI clients.
    """
    result = compare_rules_between_countries(ctx, country1, country2, category=category)
    if result.get("formatted_summary") and "pretty" not in result:
        result["pretty"] = result["formatted_summary"]
    return result


def _geoapify_geocode(query: str) -> Optional[Dict[str, Any]]:
    """
    Forward-geocode a free-text location using Geoapify.
    Returns a dict with latitude, longitude, formatted address; None on failure.
    """
    api_key = os.environ.get("GEOAPIFY_API_KEY")
    if not api_key:
        return None
    base_url = "https://api.geoapify.com/v1/geocode/search"
    params = {
        "text": query,
        "limit": 1,
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
            top = results[0]
            lat = top.get("lat")
            lon = top.get("lon")
            if lat is None or lon is None:
                return None
            return {
                "lat": float(lat),
                "lon": float(lon),
                "formatted": top.get("formatted") or query,
                "country_code": top.get("country_code"),  # ISO-2 country code (e.g., "IS", "GB")
            }
    except Exception:
        return None


def _find_nearest_airport_in_db(
    ctx: ToolContext,
    icao_or_location: str,
    max_search_radius_nm: float = 100.0
) -> Optional[Dict[str, Any]]:
    """
    Try to find the nearest airport in the database for a given ICAO code or location name.

    1. First checks if the ICAO code exists in the database
    2. If not found, tries to geocode it as a location name
    3. Finds the nearest airport in the database to those coordinates
       - Prefers airports in the same country as the geocoded location
       - Falls back to nearest airport if none in same country

    Returns dict with 'airport' object, 'original_query', 'was_geocoded', 'distance_nm', 'geocoded_location'
    or None if nothing found.
    """
    icao = icao_or_location.strip().upper()

    # First try direct ICAO lookup
    airport = ctx.model.get_airport(icao)
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

    for apt in ctx.model.airports.values():
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


def find_airports_near_location(
    ctx: ToolContext,
    location_query: str,
    max_distance_nm: float = 50.0,
    filters: Optional[Dict[str, Any]] = None,
    priority_strategy: str = "cost_optimized",
) -> Dict[str, Any]:
    """
    Find airports near a geographic location (free-text location name, city, landmark, or coordinates) within a specified distance.

    **USE THIS TOOL when user asks about airports "near", "around", "close to" a location that is NOT an ICAO code.**

    Examples:
    - "airports near Paris" → use this tool with location_query="Paris"
    - "airports around Lake Geneva" → use this tool with location_query="Lake Geneva"
    - "airports close to Zurich" → use this tool with location_query="Zurich"
    - "airports near 48.8584, 2.2945" → use this tool with location_query="48.8584, 2.2945"

    Process:
    1) Geocodes the location via Geoapify to get coordinates
    2) Computes distance from each airport to that point and filters by max_distance_nm
    3) Applies optional filters (fuel, customs, runway, etc.) and priority sorting

    **DO NOT use this tool if user provides ICAO codes** - use find_airports_near_route instead for route-based searches.
    """
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
    for airport in ctx.model.airports.values():
        if not getattr(airport, "navpoint", None):
            continue
        try:
            _, distance_nm = airport.navpoint.haversine_distance(center_point)
        except Exception:
            continue
        if distance_nm <= float(max_distance_nm):
            candidate_airports.append(airport)
            point_distances[airport.ident] = float(distance_nm)

    # Apply optional filters using FilterEngine
    if filters:
        filter_engine = FilterEngine(context=ctx)
        candidate_airports = filter_engine.apply(candidate_airports, filters)

    # Priority sort using PriorityEngine (use distances as context)
    priority_engine = PriorityEngine(context=ctx)
    sorted_airports = priority_engine.apply(
        candidate_airports,
        strategy=priority_strategy,
        context={"point_distances": point_distances},
        max_results=100
    )

    # Summaries with distance
    airports: List[Dict[str, Any]] = []
    for a in sorted_airports:
        summary = _airport_summary(a)
        summary["distance_nm"] = round(point_distances.get(a.ident, 0.0), 2)
        airports.append(summary)

    total_count = len(airports)
    airports_for_llm = airports[:20] if total_count > 20 else airports

    pretty = (
        f"Found {total_count} airports within {max_distance_nm}nm of {geocode['formatted']}."
        if total_count else
        f"No airports within {max_distance_nm}nm of {geocode['formatted']}."
    )

    # Generate filter profile for UI synchronization
    filter_profile: Dict[str, Any] = {
        "location_query": location_query,
        "radius_nm": max_distance_nm
    }
    if filters:
        # Legacy filters
        if filters.get("country"):
            filter_profile["country"] = filters["country"]
        if filters.get("has_procedures"):
            filter_profile["has_procedures"] = True
        if filters.get("has_aip_data"):
            filter_profile["has_aip_data"] = True
        if filters.get("has_hard_runway"):
            filter_profile["has_hard_runway"] = True
        if filters.get("point_of_entry"):
            filter_profile["point_of_entry"] = True
        # New filters
        if filters.get("max_runway_length_ft"):
            filter_profile["max_runway_length_ft"] = filters["max_runway_length_ft"]
        if filters.get("min_runway_length_ft"):
            filter_profile["min_runway_length_ft"] = filters["min_runway_length_ft"]
        if filters.get("has_avgas"):
            filter_profile["has_avgas"] = True
        if filters.get("has_jet_a"):
            filter_profile["has_jet_a"] = True
        if filters.get("max_landing_fee"):
            filter_profile["max_landing_fee"] = filters["max_landing_fee"]

    return {
        "found": True,
        "count": total_count,
        "center": {"lat": geocode["lat"], "lon": geocode["lon"], "label": geocode["formatted"]},
        "airports": airports_for_llm,  # Limited for LLM
        "pretty": pretty,
        "filter_profile": filter_profile,
        "visualization": {
            "type": "point_with_markers",
            "point": {
                "label": geocode["formatted"],
                "lat": geocode["lat"],
                "lon": geocode["lon"],
            },
            "markers": airports  # Show all within radius on map
        }
    }


def _tool_description(func: Callable) -> str:
    return (func.__doc__ or "").strip()


def _build_shared_tool_specs() -> OrderedDictType[str, ToolSpec]:
    """Create the ordered manifest of shared tools."""
    return OrderedDict([
        (
            "search_airports",
            {
                "name": "search_airports",
                "handler": search_airports,
                "description": _tool_description(search_airports),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Airport name, ICAO/IATA code, or city (e.g., 'Paris', 'LFPG').",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return.",
                            "default": 20,
                        },
                        "filters": {
                            "type": "object",
                            "description": "IMPORTANT: Use filters object to filter airports by characteristics mentioned in user's request. Examples: {'has_avgas': True} for AVGAS fuel, {'point_of_entry': True} for customs, {'has_hard_runway': True} for paved runways, {'has_procedures': True} for IFR, {'country': 'FR'} for country. ALWAYS include filters when user specifies characteristics.",
                        },
                        "priority_strategy": {
                            "type": "string",
                            "description": "Priority sorting strategy (e.g., cost_optimized).",
                            "default": "cost_optimized",
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
                "description": _tool_description(find_airports_near_location),
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
                        "filters": {
                            "type": "object",
                            "description": "Airport filters (fuel, customs, runway length, etc.).",
                        },
                        "priority_strategy": {
                            "type": "string",
                            "description": "Priority sorting strategy (e.g., cost_optimized).",
                            "default": "cost_optimized",
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
                "description": _tool_description(find_airports_near_route),
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
                        "filters": {
                            "type": "object",
                            "description": "IMPORTANT: Use filters object to filter airports by characteristics mentioned in user's request. Examples: {'has_avgas': True} for AVGAS fuel, {'point_of_entry': True} for customs, {'has_hard_runway': True} for paved runways, {'has_procedures': True} for IFR, {'country': 'FR'} for country. ALWAYS include filters when user specifies characteristics like fuel type, customs, runway type, etc.",
                        },
                        "priority_strategy": {
                            "type": "string",
                            "description": "Priority sorting strategy (e.g., cost_optimized).",
                            "default": "cost_optimized",
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
                "description": _tool_description(get_airport_details),
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
        (
            "get_border_crossing_airports",
            {
                "name": "get_border_crossing_airports",
                "handler": get_border_crossing_airports,
                "description": _tool_description(get_border_crossing_airports),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Optional ISO-2 country code (e.g., FR, DE).",
                        },
                    },
                },
                "expose_to_llm": True,
            },
        ),
        (
            "get_airport_statistics",
            {
                "name": "get_airport_statistics",
                "handler": get_airport_statistics,
                "description": _tool_description(get_airport_statistics),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Optional ISO-2 country code to filter stats.",
                        },
                    },
                },
                "expose_to_llm": True,
            },
        ),
        (
            "get_airport_pricing",
            {
                "name": "get_airport_pricing",
                "handler": get_airport_pricing,
                "description": _tool_description(get_airport_pricing),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "icao_code": {
                            "type": "string",
                            "description": "Airport ICAO code (e.g., EDAZ).",
                        },
                    },
                    "required": ["icao_code"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "get_pilot_reviews",
            {
                "name": "get_pilot_reviews",
                "handler": get_pilot_reviews,
                "description": _tool_description(get_pilot_reviews),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "icao_code": {
                            "type": "string",
                            "description": "Airport ICAO code.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of reviews to return.",
                            "default": 10,
                        },
                    },
                    "required": ["icao_code"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "get_fuel_prices",
            {
                "name": "get_fuel_prices",
                "handler": get_fuel_prices,
                "description": _tool_description(get_fuel_prices),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "icao_code": {
                            "type": "string",
                            "description": "Airport ICAO code.",
                        },
                    },
                    "required": ["icao_code"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "list_rules_for_country",
            {
                "name": "list_rules_for_country",
                "handler": list_rules_for_country,
                "description": _tool_description(list_rules_for_country),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country_code": {
                            "type": "string",
                            "description": "ISO-2 country code (e.g., FR, GB).",
                        },
                        "category": {
                            "type": "string",
                            "description": "Optional category filter (e.g., Customs).",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of tags to filter rules.",
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
                "description": _tool_description(compare_rules_between_countries),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country1": {
                            "type": "string",
                            "description": "First ISO-2 country code.",
                        },
                        "country2": {
                            "type": "string",
                            "description": "Second ISO-2 country code.",
                        },
                        "category": {
                            "type": "string",
                            "description": "Optional category filter.",
                        },
                    },
                    "required": ["country1", "country2"],
                },
                "expose_to_llm": True,
            },
        ),
        (
            "get_answers_for_questions",
            {
                "name": "get_answers_for_questions",
                "handler": get_answers_for_questions,
                "description": _tool_description(get_answers_for_questions),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of predefined question IDs.",
                        },
                    },
                    "required": ["question_ids"],
                },
                "expose_to_llm": False,
            },
        ),
        (
            "list_rule_categories_and_tags",
            {
                "name": "list_rule_categories_and_tags",
                "handler": list_rule_categories_and_tags,
                "description": _tool_description(list_rule_categories_and_tags),
                "parameters": {"type": "object", "properties": {}},
                "expose_to_llm": False,
            },
        ),
        (
            "list_rule_countries",
            {
                "name": "list_rule_countries",
                "handler": list_rule_countries,
                "description": _tool_description(list_rule_countries),
                "parameters": {"type": "object", "properties": {}},
                "expose_to_llm": False,
            },
        ),
    ])


_SHARED_TOOL_SPECS: OrderedDictType[str, ToolSpec] = _build_shared_tool_specs()


def get_shared_tool_specs() -> OrderedDictType[str, ToolSpec]:
    """
    Return the shared tool manifest.
    The mapping is ordered to keep registration deterministic.
    """
    return _SHARED_TOOL_SPECS.copy()

