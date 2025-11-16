#!/usr/bin/env python3
"""
Shared airport tool logic used by both the MCP server and internal chatbot client.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, OrderedDict as OrderedDictType, TypedDict

from euro_aip.models.euro_aip_model import EuroAipModel
from euro_aip.models.airport import Airport
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
    """Search for airports by name, ICAO code, IATA code, or city name with optional filters (country, procedures, runway, fuel, fees). Returns matching airports sorted by priority."""
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
    from_icao: str,
    to_icao: str,
    max_distance_nm: float = 50.0,
    filters: Optional[Dict[str, Any]] = None,
    priority_strategy: str = "cost_optimized",
) -> Dict[str, Any]:
    """List airports within a specified distance from a direct route between two airports, with optional airport filters. IMPORTANT: When user mentions fuel (e.g., AVGAS, Jet-A), customs/border crossing, runway type (paved/hard), IFR procedures, or country, you MUST include the corresponding filter: has_avgas=True for AVGAS, has_jet_a=True for Jet-A, point_of_entry=True for customs, has_hard_runway=True for paved runways, has_procedures=True for IFR, country='XX' for specific country. Useful for finding fuel stops, alternates, or customs stops."""
    results = ctx.model.find_airports_near_route(
        [from_icao.upper(), to_icao.upper()],
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

    from_airport = ctx.model.get_airport(from_icao.upper())
    to_airport = ctx.model.get_airport(to_icao.upper())

    pretty = (
        f"Found {len(airports)} airports within {max_distance_nm}nm of route {from_icao.upper()} to {to_icao.upper()}."
        if airports else
        f"No airports within {max_distance_nm}nm of {from_icao.upper()}->{to_icao.upper()}."
    )

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
        "visualization": {
            "type": "route_with_markers",
            "route": {
                "from": {
                    "icao": from_icao.upper(),
                    "lat": getattr(from_airport, "latitude_deg", None) if from_airport else None,
                    "lon": getattr(from_airport, "longitude_deg", None) if from_airport else None,
                },
                "to": {
                    "icao": to_icao.upper(),
                    "lat": getattr(to_airport, "latitude_deg", None) if to_airport else None,
                    "lon": getattr(to_airport, "longitude_deg", None) if to_airport else None,
                }
            },
            "markers": airports_for_llm  # Only show what LLM sees and recommends
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
            "find_airports_near_route",
            {
                "name": "find_airports_near_route",
                "handler": find_airports_near_route,
                "description": _tool_description(find_airports_near_route),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_icao": {
                            "type": "string",
                            "description": "Departure airport ICAO code (e.g., EGTF).",
                        },
                        "to_icao": {
                            "type": "string",
                            "description": "Destination airport ICAO code (e.g., LFMD).",
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
                    "required": ["from_icao", "to_icao"],
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

