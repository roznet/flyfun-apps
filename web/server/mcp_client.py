#!/usr/bin/env python3
"""
Internal MCP Client for Chatbot Service
Calls the MCP server's tools and returns results for the LLM.
"""

import httpx
import logging
import os
import requests
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import re

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
)

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for calling MCP server tools internally."""

    def __init__(self, mcp_base_url: str = "http://localhost:8002"):
        self.mcp_base_url = mcp_base_url
        self.client = httpx.Client(timeout=30.0)
        self._tool_context: Optional[ToolContext] = None

    def _ensure_context(self) -> ToolContext:
        if self._tool_context is None:
            db_path = os.getenv("AIRPORTS_DB", "airports.db")
            rules_path = os.getenv("RULES_JSON", "rules.json")
            self._tool_context = ToolContext.create(db_path=db_path, rules_path=rules_path)
            logger.info(
                "Tool context initialized: %d airports loaded, %d rules available",
                len(self._tool_context.model.airports),
                len(self._tool_context.rules_manager.rules if self._tool_context.rules_manager else []),
            )
        return self._tool_context

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool via internal HTTP request.
        For now, we'll use the euro_aip model directly instead of HTTP.
        """
        import time

        try:
            self._ensure_context()
            exec_start = time.time()
            logger.info(f"⏱️ MCP: Executing {tool_name}...")

            if tool_name == "search_airports":
                result = self._search_airports(**arguments)
            elif tool_name == "find_airports_near_route":
                result = self._find_airports_near_route(**arguments)
            elif tool_name == "get_airport_details":
                result = self._get_airport_details(**arguments)
            elif tool_name == "get_border_crossing_airports":
                result = self._get_border_crossing_airports(**arguments)
            elif tool_name == "get_airport_statistics":
                result = self._get_airport_statistics(**arguments)
            elif tool_name == "get_airport_pricing":
                result = self._get_airport_pricing(**arguments)
            elif tool_name == "get_pilot_reviews":
                result = self._get_pilot_reviews(**arguments)
            elif tool_name == "get_fuel_prices":
                result = self._get_fuel_prices(**arguments)
            elif tool_name == "web_search":
                result = self._web_search(**arguments)
            elif tool_name == "list_rules_for_country":
                result = self._list_rules_for_country(**arguments)
            elif tool_name == "compare_rules_between_countries":
                result = self._compare_rules_between_countries(**arguments)
            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            exec_end = time.time()
            logger.info(f"⏱️ MCP: {tool_name} execution took {exec_end - exec_start:.2f}s")
            return result

        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}", exc_info=True)
            return {"error": str(e)}

    def _search_airports(self, query: str, max_results: int = 20) -> Dict[str, Any]:
        ctx = self._ensure_context()
        return shared_search_airports(ctx, query, max_results)

    def _find_airports_near_route(
        self,
        from_icao: str,
        to_icao: str,
        max_distance_nm: float = 50.0,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        ctx = self._ensure_context()
        return shared_find_airports_near_route(ctx, from_icao, to_icao, max_distance_nm, filters=filters)

    def _get_airport_details(self, icao_code: str) -> Dict[str, Any]:
        ctx = self._ensure_context()
        return shared_get_airport_details(ctx, icao_code)

    def _get_border_crossing_airports(self, country: Optional[str] = None) -> Dict[str, Any]:
        ctx = self._ensure_context()
        return shared_get_border_crossing_airports(ctx, country)

    def _get_airport_statistics(self, country: Optional[str] = None) -> Dict[str, Any]:
        ctx = self._ensure_context()
        return shared_get_airport_statistics(ctx, country)

    def _get_airport_pricing(self, icao_code: str) -> Dict[str, Any]:
        ctx = self._ensure_context()
        return shared_get_airport_pricing(ctx, icao_code)

    def _get_pilot_reviews(self, icao_code: str, limit: int = 10) -> Dict[str, Any]:
        """Get pilot reviews (PIREPs) for an airport."""
        icao = icao_code.strip().upper()
        reviews = self.enrichment_storage.get_pilot_reviews(icao, limit)

        if not reviews:
            return {
                "found": False,
                "icao_code": icao,
                "count": 0,
                "message": f"No pilot reviews available for {icao}."
            }

        # Calculate average rating
        ratings = [r['rating'] for r in reviews if r.get('rating')]
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        # Format reviews for display
        formatted_reviews = []
        for review in reviews:
            formatted_reviews.append({
                "rating": review.get('rating'),
                "author": review.get('author_name') or "Anonymous",
                "comment": (review.get('comment_en') or
                           review.get('comment_de') or
                           review.get('comment_fr') or
                           review.get('comment_it') or
                           review.get('comment_es') or
                           review.get('comment_nl')),
                "date": review.get('created_at'),
                "is_ai_generated": bool(review.get('is_ai_generated'))
            })

        return {
            "found": True,
            "icao_code": icao,
            "count": len(reviews),
            "average_rating": avg_rating,
            "reviews": formatted_reviews
        }

    def _get_fuel_prices(self, icao_code: str) -> Dict[str, Any]:
        """Get fuel availability and pricing for an airport."""
        icao = icao_code.strip().upper()

        # Get fuel availability
        fuels = self.enrichment_storage.get_fuel_availability(icao)

        # Get pricing data for fuel prices
        pricing = self.enrichment_storage.get_pricing_data(icao)

        if not fuels and not pricing:
            return {
                "found": False,
                "icao_code": icao,
                "message": f"No fuel data available for {icao}."
            }

        # Build fuel list with prices
        fuel_list = []
        for fuel in fuels:
            fuel_type = fuel.get('fuel_type', 'Unknown')

            # Try to get price from pricing data
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

        return {
            "found": True,
            "icao_code": icao,
            "fuels": fuel_list,
            "fuel_provider": pricing.get('fuel_provider') if pricing else None,
            "payment_available": bool(pricing.get('payment_available')) if pricing else None,
            "ppr_required": bool(pricing.get('ppr_available')) if pricing else None,
            "last_updated": pricing.get('last_updated') if pricing else None
        }

    def _web_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Perform actual web search using DuckDuckGo HTML scraping.
        Returns real search results from the web.
        """
        try:
            # Use DuckDuckGo HTML search
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            search_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
            response = requests.get(search_url, headers=headers, timeout=15)
            response.raise_for_status()

            # Parse HTML results
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # Find search result divs
            result_divs = soup.find_all('div', class_='result')

            for div in result_divs[:max_results]:
                try:
                    # Extract title and URL
                    title_link = div.find('a', class_='result__a')
                    if not title_link:
                        continue

                    title = title_link.get_text(strip=True)
                    url = title_link.get('href', '')

                    # Extract snippet
                    snippet_div = div.find('a', class_='result__snippet')
                    snippet = snippet_div.get_text(strip=True) if snippet_div else ""

                    # Clean up snippet
                    snippet = re.sub(r'\s+', ' ', snippet).strip()

                    if title and url:
                        results.append({
                            "title": title[:200],  # Limit title length
                            "snippet": snippet[:500] if snippet else "No description available",  # Limit snippet
                            "url": url,
                            "source": "Web Search"
                        })
                except Exception as e:
                    logger.debug(f"Error parsing search result: {e}")
                    continue

            # If no results, provide helpful message
            if not results:
                results.append({
                    "title": "No Results Found",
                    "snippet": f"No web results found for '{query}'. Please try: 1) Checking the airport operator's official website, 2) Reviewing AIP supplements, 3) Contacting handling agents directly, 4) Using official aviation databases like EUROCONTROL.",
                    "url": f"https://duckduckgo.com/?q={requests.utils.quote(query)}",
                    "source": "Search Guidance"
                })

            return {
                "query": query,
                "count": len(results),
                "results": results,
                "message": "⚠️ IMPORTANT: Always verify web search results with official aviation sources before making operational decisions."
            }

        except Exception as e:
            logger.error(f"Error in web search: {e}", exc_info=True)
            return {
                "query": query,
                "error": str(e),
                "message": "Web search unavailable. Please check official aviation sources directly.",
                "results": [{
                    "title": "Web Search Error",
                    "snippet": f"Could not perform web search: {str(e)}. For aviation information, check official sources like AIP, airport operator websites, or EUROCONTROL.",
                    "url": "https://www.eurocontrol.int/",
                    "source": "Error Message"
                }]
            }

    def _list_rules_for_country(
        self,
        country_code: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get aviation rules for a specific country.

        Args:
            country_code: ISO-2 country code (e.g., 'FR', 'GB', 'DE')
            category: Optional category filter
            tags: Optional list of tags to filter by

        Returns:
            Dict with rules and formatted text
        """
        try:
            logger.info(f"📋 Fetching rules for {country_code.upper()}" +
                       (f" (category: {category})" if category else ""))
            ctx = self._ensure_context()
            rules = shared_list_rules_for_country(
                ctx,
                country_code=country_code,
                category=category,
                tags=tags
            )
            logger.info(f"✅ Found {rules['count']} rules for {country_code.upper()}")
            return rules
        except Exception as e:
            logger.error(f"Error listing rules for country: {e}", exc_info=True)
            return {
                "error": str(e),
                "country_code": country_code.upper(),
                "message": "Error retrieving rules. Please check if rules.json is loaded."
            }

    def _compare_rules_between_countries(
        self,
        country1: str,
        country2: str,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare aviation rules between two countries.

        Args:
            country1: First country ISO-2 code
            country2: Second country ISO-2 code
            category: Optional category filter

        Returns:
            Dict with comparison results
        """
        try:
            logger.info(f"🔄 Comparing rules between {country1.upper()} and {country2.upper()}" +
                       (f" (category: {category})" if category else ""))
            ctx = self._ensure_context()
            comparison = shared_compare_rules_between_countries(
                ctx,
                country1=country1,
                country2=country2,
                category=category
            )

            c1_count = comparison.get('total_rules_country1', 0)
            c2_count = comparison.get('total_rules_country2', 0)
            diff_count = len(comparison.get('differences', []))

            logger.info(f"✅ Comparison complete: {country1.upper()} ({c1_count} rules) vs {country2.upper()} ({c2_count} rules) - {diff_count} differences found")

            return comparison
        except Exception as e:
            logger.error(f"Error comparing rules: {e}", exc_info=True)
            return {
                "error": str(e),
                "message": f"Error comparing rules between {country1.upper()} and {country2.upper()}"
            }

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Return tool definitions in OpenAI function calling format.
        These will be provided to the LLM so it knows what tools it can call.
        """

        def _desc(func):
            return (func.__doc__ or "").strip()

        return [
            {
                "type": "function",
                "function": {
                    "name": "search_airports",
                    "description": _desc(shared_search_airports),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (airport name, ICAO code like LFPG, IATA code, or city name)",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 20)",
                                "default": 20,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "find_airports_near_route",
                    "description": _desc(shared_find_airports_near_route),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "from_icao": {
                                "type": "string",
                                "description": "Departure airport ICAO code (e.g., EGTF)",
                            },
                            "to_icao": {
                                "type": "string",
                                "description": "Destination airport ICAO code (e.g., LFMD)",
                            },
                            "max_distance_nm": {
                                "type": "number",
                                "description": "Maximum distance in nautical miles from the direct route (default: 50)",
                                "default": 50.0,
                            },
                            "filters": {
                                "type": "object",
                                "description": "Optional airport filters: country, runway specs, fuel availability, customs, procedures, and pricing.",
                                "properties": {
                                    "country": {"type": "string", "description": "ISO-2 country code (e.g., FR, GB)"},
                                    "has_procedures": {"type": "boolean", "description": "Has instrument procedures"},
                                    "has_aip_data": {"type": "boolean", "description": "Has AIP (Aeronautical Information Publication) data"},
                                    "has_hard_runway": {"type": "boolean", "description": "Has hard surface runway (concrete/asphalt)"},
                                    "point_of_entry": {"type": "boolean", "description": "Is an official border crossing point (has customs)"},
                                    "max_runway_length_ft": {"type": "number", "description": "Maximum runway length in feet (filters OUT longer runways)"},
                                    "min_runway_length_ft": {"type": "number", "description": "Minimum runway length in feet required"},
                                    "has_avgas": {"type": "boolean", "description": "Has AVGAS fuel available"},
                                    "has_jet_a": {"type": "boolean", "description": "Has Jet-A fuel available"},
                                    "max_landing_fee": {"type": "number", "description": "Maximum landing fee (C172) in local currency"},
                                },
                            },
                        },
                        "required": ["from_icao", "to_icao"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_airport_details",
                    "description": _desc(shared_get_airport_details),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "icao_code": {
                                "type": "string",
                                "description": "ICAO code of the airport (e.g., LFPG for Paris Charles de Gaulle)",
                            },
                        },
                        "required": ["icao_code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_border_crossing_airports",
                    "description": _desc(shared_get_border_crossing_airports),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country": {
                                "type": "string",
                                "description": "Optional: ISO country code to filter (e.g., FR for France, GB for UK)",
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_airport_statistics",
                    "description": _desc(shared_get_airport_statistics),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country": {
                                "type": "string",
                                "description": "Optional: ISO country code to filter statistics (e.g., FR, GB, DE)",
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_airport_pricing",
                    "description": _desc(shared_get_airport_pricing),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "icao_code": {
                                "type": "string",
                                "description": "ICAO code of the airport (e.g., EDAZ, LOWZ)",
                            },
                        },
                        "required": ["icao_code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pilot_reviews",
                    "description": _desc(shared_get_pilot_reviews),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "icao_code": {
                                "type": "string",
                                "description": "ICAO code of the airport (e.g., LOWZ, EDXR)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of reviews to return (default: 10)",
                                "default": 10,
                            },
                        },
                        "required": ["icao_code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_fuel_prices",
                    "description": _desc(shared_get_fuel_prices),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "icao_code": {
                                "type": "string",
                                "description": "ICAO code of the airport (e.g., EDAZ, LFMD)",
                            },
                        },
                        "required": ["icao_code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for aviation information not available in the airport database (e.g., current fees, NOTAMs, weather, regulations, AIP supplements). Use this as a fallback when database tools don't have the requested information. Always mention that results should be verified with official sources.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for aviation-related information (e.g., 'LFPG landing fees 2024', 'Paris CDG general aviation procedures')",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of search results to return (default: 5)",
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_rules_for_country",
                    "description": _desc(shared_list_rules_for_country),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country_code": {
                                "type": "string",
                                "description": "ISO-2 country code (e.g., FR for France, GB for UK, DE for Germany, ES for Spain, IT for Italy)",
                            },
                            "category": {
                                "type": "string",
                                "description": "Optional: Filter by category (e.g., 'Customs', 'Flight Plan', 'Airspace', 'IFR/VFR')",
                            },
                        },
                        "required": ["country_code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_rules_between_countries",
                    "description": _desc(shared_compare_rules_between_countries),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country1": {
                                "type": "string",
                                "description": "First country ISO-2 code (e.g., FR, GB, DE)",
                            },
                            "country2": {
                                "type": "string",
                                "description": "Second country ISO-2 code to compare with",
                            },
                            "category": {
                                "type": "string",
                                "description": "Optional: Filter comparison by category",
                            },
                        },
                        "required": ["country1", "country2"],
                    },
                },
            },
        ]
