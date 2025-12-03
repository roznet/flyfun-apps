#!/usr/bin/env python3
"""
MCP Server for Euro AIP Airport Database

This server provides tools for querying airport data, route planning, and flight information
to LLM clients like ChatGPT and Claude.

See `shared/README.md` for more information on the shared tooling and how to add/update tools.

"""
from __future__ import annotations
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

# Add the flyfun-apps package to the path (before importing shared)
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables using shared loader
from shared.env_loader import load_component_env

# Load from component directory (e.g., mcp_server/dev.env)
component_dir = Path(__file__).parent
load_component_env(component_dir)

from fastmcp import Context, FastMCP

from euro_aip.models.euro_aip_model import EuroAipModel
from euro_aip.storage.database_storage import DatabaseStorage
from euro_aip.storage.enrichment_storage import EnrichmentStorage

from shared.airport_tools import (
    ToolContext,
    search_airports as shared_search_airports,
    find_airports_near_route as shared_find_airports_near_route,
    get_airport_details as shared_get_airport_details,
    get_border_crossing_airports as shared_get_border_crossing_airports,
    get_airport_statistics as shared_get_airport_statistics,
    get_airport_pricing as shared_get_airport_pricing,
    get_pilot_reviews as shared_get_pilot_reviews,
    get_fuel_prices as shared_get_fuel_prices,
    list_rules_for_country as shared_list_rules_for_country,
    compare_rules_between_countries as shared_compare_rules_between_countries,
    get_answers_for_questions as shared_get_answers_for_questions,
    list_rule_categories_and_tags as shared_list_rule_categories_and_tags,
    list_rule_countries as shared_list_rule_countries,
)
from shared.rules_manager import RulesManager

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# ---- Types for structured output (optional but nice) -------------------------
class AirportSummary(TypedDict, total=False):
    ident: str
    name: str
    municipality: Optional[str]
    country: Optional[str]
    latitude_deg: Optional[float]
    longitude_deg: Optional[float]
    longest_runway_length_ft: Optional[int]
    point_of_entry: bool

class AirportNearRoute(TypedDict):
    airport: AirportSummary
    distance_nm: float

# ---- Global model storage for FastMCP 2.11 --------------------------------
_model: Optional[EuroAipModel] = None
_enrichment_storage: Optional[EnrichmentStorage] = None
_tool_context: Optional[ToolContext] = None

def get_model() -> EuroAipModel:
    """Get the global model instance."""
    if _model is None:
        raise RuntimeError("Model not initialized. Server not started properly.")
    return _model

def get_enrichment_storage() -> EnrichmentStorage:
    """Get the global enrichment storage instance."""
    if _enrichment_storage is None:
        raise RuntimeError("Enrichment storage not initialized. Server not started properly.")
    return _enrichment_storage


def _require_tool_context() -> ToolContext:
    if _tool_context is None:
        raise RuntimeError("Tool context not initialized. Server not started properly.")
    return _tool_context

# ---- Server with lifespan to manage resources --------------------------------
@asynccontextmanager
async def lifespan(app: FastMCP):
    global _model
    global _enrichment_storage
    global _tool_context
    db_path = os.environ.get("AIRPORTS_DB", "airports.db")
    logger.info(f"Loading model from database at '{db_path}'")
    # Let FastMCP handle logging/levels via FASTMCP_LOG_LEVEL, etc.
    db_storage = DatabaseStorage(db_path)
    _model = db_storage.load_model()
    _enrichment_storage = EnrichmentStorage(db_path)
    logger.info("Enrichment storage initialized")
    rules_path = os.environ.get("RULES_JSON", "rules.json")
    logger.info(f"Loading rules from '{rules_path}'")
    rules_manager = RulesManager(rules_path)
    rules_manager.load_rules()
    _tool_context = ToolContext(
        model=_model,
        enrichment_storage=_enrichment_storage,
        rules_manager=rules_manager,
    )
    try:
        yield
    finally:
        # Add teardown if needed
        pass

mcp = FastMCP(
    name="euro_aip",
    instructions=(
        "Euro AIP Airport MCP Server. Tools for querying airport data, route planning, "
        "and country-specific aviation rules. Use two-letter ISO country codes (e.g., FR, GB). "
        "Rules tools support filters by category/tags; try listing available countries, categories, and tags first."
    ),
    lifespan=lifespan,
)

# ---- Tools -------------------------------------------------------------------
# Helper to keep tool descriptions consistent with shared functions
def _desc(func) -> str:
    return (func.__doc__ or "").strip()


@mcp.tool(name="search_airports", description=_desc(shared_search_airports))
def search_airports(
    query: str,
    max_results: int = 50,
    filters: Optional[Dict[str, Any]] = None,
    priority_strategy: str = "cost_optimized",
    ctx: Context = None
) -> Dict[str, Any]:
    context = _require_tool_context()
    result = shared_search_airports(context, query, max_results, filters, priority_strategy)
    return result


@mcp.tool(name="find_airports_near_route", description=_desc(shared_find_airports_near_route))
def find_airports_near_route(
    from_location: str,
    to_location: str,
    max_distance_nm: float = 50.0,
    filters: Optional[Dict[str, Any]] = None,
    priority_strategy: str = "cost_optimized",
    ctx: Context = None,
) -> Dict[str, Any]:
    context = _require_tool_context()
    result = shared_find_airports_near_route(
        context,
        from_location,
        to_location,
        max_distance_nm,
        filters=filters,
        priority_strategy=priority_strategy,
    )
    return result


@mcp.tool(name="get_airport_details", description=_desc(shared_get_airport_details))
def get_airport_details(icao_code: str, ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_get_airport_details(context, icao_code)


@mcp.tool(name="list_rules_for_country", description=_desc(shared_list_rules_for_country))
def list_rules_for_country(country: str,
                           category: Optional[str] = None,
                           tags: Optional[List[str]] = None,
                           include_unanswered: bool = False,
                           search: Optional[str] = None,
                           tags_mode: str = "any",
                           ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    if include_unanswered or tags_mode != "any":  # features not currently exposed via shared helper
        raise ValueError("include_unanswered and tags_mode parameters are not supported in this implementation.")
    result = shared_list_rules_for_country(context, country, category=category, tags=tags)
    return result


@mcp.tool(name="compare_rules_between_countries", description=_desc(shared_compare_rules_between_countries))
def compare_rules_between_countries(country_a: str,
                                    country_b: str,
                                    category: Optional[str] = None,
                                    ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    result = shared_compare_rules_between_countries(
        context,
        country1=country_a,
        country2=country_b,
        category=category,
    )
    comparison = result.get("comparison", {})
    return {
        "found": result.get("found", False),
        "comparison": comparison,
        "formatted_summary": result.get("formatted_summary"),
        "total_differences": result.get("total_differences"),
        "pretty": result.get("formatted_summary"),
    }


@mcp.tool(name="get_answers_for_questions", description=_desc(shared_get_answers_for_questions))
def get_answers_for_questions(question_ids: List[str], ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_get_answers_for_questions(context, question_ids)


@mcp.tool(name="list_rule_categories_and_tags", description=_desc(shared_list_rule_categories_and_tags))
def list_rule_categories_and_tags(ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_list_rule_categories_and_tags(context)


@mcp.tool(name="list_rule_countries", description=_desc(shared_list_rule_countries))
def list_rule_countries(ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_list_rule_countries(context)


@mcp.tool(name="get_border_crossing_airports", description=_desc(shared_get_border_crossing_airports))
def get_border_crossing_airports(country: Optional[str] = None, ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_get_border_crossing_airports(context, country)


@mcp.tool(name="get_airport_statistics", description=_desc(shared_get_airport_statistics))
def get_airport_statistics(country: Optional[str] = None, ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_get_airport_statistics(context, country)


@mcp.tool(name="get_airport_pricing", description=_desc(shared_get_airport_pricing))
def get_airport_pricing(icao_code: str, ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_get_airport_pricing(context, icao_code)


@mcp.tool(name="get_pilot_reviews", description=_desc(shared_get_pilot_reviews))
def get_pilot_reviews(icao_code: str, limit: int = 10, ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_get_pilot_reviews(context, icao_code, limit)


@mcp.tool(name="get_fuel_prices", description=_desc(shared_get_fuel_prices))
def get_fuel_prices(icao_code: str, ctx: Context = None) -> Dict[str, Any]:
    context = _require_tool_context()
    return shared_get_fuel_prices(context, icao_code)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Euro AIP MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type: stdio (default) or http (replaces legacy SSE).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for HTTP transport (default: 8001)",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Database file (overrides AIRPORTS_DB environment variable)",
    )
    parser.add_argument(
        "--rules",
        default=None,
        help="Rules JSON file (overrides RULES_JSON environment variable)",
    )

    args = parser.parse_args()
    if args.database is not None:
        os.environ["AIRPORTS_DB"] = args.database
    if args.rules is not None:
        os.environ["RULES_JSON"] = args.rules

    if args.transport == "http":
        # Use "streamable-http" for langchain-mcp-adapters compatibility
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()