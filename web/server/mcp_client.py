#!/usr/bin/env python3
"""
Internal MCP Client for Chatbot Service
Calls the MCP server's tools and returns results for the LLM.
"""

import httpx
import logging
import requests
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import re
from rules_manager import RulesManager

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for calling MCP server tools internally."""

    def __init__(self, mcp_base_url: str = "http://localhost:8002"):
        self.mcp_base_url = mcp_base_url
        self.client = httpx.Client(timeout=30.0)

        # Initialize rules manager and load rules
        self.rules_manager = RulesManager()
        rules_loaded = self.rules_manager.load_rules()
        if rules_loaded:
            logger.info(f"Rules manager initialized - loaded {len(self.rules_manager.rules)} rules")
        else:
            logger.warning("Rules manager initialized but no rules loaded")

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool via internal HTTP request.
        For now, we'll use the euro_aip model directly instead of HTTP.
        """
        import time

        try:
            # Import the model directly for faster access
            from euro_aip.storage.database_storage import DatabaseStorage
            from euro_aip.storage.enrichment_storage import EnrichmentStorage
            from euro_aip.models.euro_aip_model import EuroAipModel
            import os

            # Load model if not already loaded
            if not hasattr(self, 'model'):
                load_start = time.time()
                logger.info(f"⏱️ MCP: Loading database model...")

                db_path = os.getenv("AIRPORTS_DB", "airports.db")
                db_storage = DatabaseStorage(db_path)
                self.model = db_storage.load_model()
                self.enrichment_storage = EnrichmentStorage(db_path)

                load_end = time.time()
                logger.info(f"⏱️ MCP: Database loaded in {load_end - load_start:.2f}s - {len(self.model.airports)} airports")
                logger.info(f"⏱️ MCP: Enrichment storage loaded")

            # Execute tool based on name
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
        """Search airports by name, ICAO, IATA, or municipality."""
        q = query.upper().strip()
        matches = []

        for a in self.model.airports.values():
            if (
                (q in a.ident)
                or (a.name and q in a.name.upper())
                or (getattr(a, "iata_code", None) and q in a.iata_code)
                or (a.municipality and q in a.municipality.upper())
            ):
                matches.append({
                    "ident": a.ident,
                    "name": a.name,
                    "municipality": a.municipality,
                    "country": a.iso_country,
                    "latitude_deg": getattr(a, "latitude_deg", None),
                    "longitude_deg": getattr(a, "longitude_deg", None),
                    "longest_runway_length_ft": getattr(a, "longest_runway_length_ft", None),
                    "point_of_entry": bool(getattr(a, "point_of_entry", False)),
                })
                if len(matches) >= max_results:
                    break

        return {
            "count": len(matches),
            "airports": matches,
            "visualization": {
                "type": "markers",
                "data": matches  # Frontend will plot these on map
            }
        }

    def _find_airports_near_route(
        self,
        from_icao: str,
        to_icao: str,
        max_distance_nm: float = 50.0
    ) -> Dict[str, Any]:
        """Find airports within distance of a direct route."""
        results = self.model.find_airports_near_route(
            [from_icao.upper(), to_icao.upper()],
            max_distance_nm
        )

        airports = []
        for item in results:
            a = item["airport"]
            airports.append({
                "ident": a.ident,
                "name": a.name,
                "municipality": a.municipality,
                "country": a.iso_country,
                "latitude_deg": getattr(a, "latitude_deg", None),
                "longitude_deg": getattr(a, "longitude_deg", None),
                "distance_nm": float(item["distance_nm"]),
                "longest_runway_length_ft": getattr(a, "longest_runway_length_ft", None),
                "point_of_entry": bool(getattr(a, "point_of_entry", False)),
            })

        # Get from/to airport coordinates for route line
        from_airport = self.model.get_airport(from_icao.upper())
        to_airport = self.model.get_airport(to_icao.upper())

        return {
            "count": len(airports),
            "airports": airports,
            "visualization": {
                "type": "route_with_markers",
                "route": {
                    "from": {
                        "icao": from_icao,
                        "lat": getattr(from_airport, "latitude_deg", None) if from_airport else None,
                        "lon": getattr(from_airport, "longitude_deg", None) if from_airport else None,
                    },
                    "to": {
                        "icao": to_icao,
                        "lat": getattr(to_airport, "latitude_deg", None) if to_airport else None,
                        "lon": getattr(to_airport, "longitude_deg", None) if to_airport else None,
                    }
                },
                "markers": airports  # Airports along the route
            }
        }

    def _get_airport_details(self, icao_code: str) -> Dict[str, Any]:
        """Get detailed information about a specific airport."""
        icao = icao_code.strip().upper()
        a = self.model.get_airport(icao)

        if not a:
            return {"found": False, "error": f"Airport {icao} not found"}

        # Get standardized entries (AIP data)
        standardized = []
        for e in (a.get_standardized_entries() or []):
            if getattr(e, "std_field", None) and getattr(e, "value", None):
                standardized.append({
                    "field": e.std_field,
                    "value": e.value
                })

        # Get runway details
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

        details = {
            "found": True,
            "airport": {
                "ident": a.ident,
                "name": a.name,
                "municipality": a.municipality,
                "country": a.iso_country,
                "latitude_deg": getattr(a, "latitude_deg", None),
                "longitude_deg": getattr(a, "longitude_deg", None),
                "elevation_ft": getattr(a, "elevation_ft", None),
                "point_of_entry": bool(getattr(a, "point_of_entry", False)),
            },
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
                    "zoom": 12  # Zoom level for detail view
                }
            }
        }

        return details

    def _get_border_crossing_airports(self, country: Optional[str] = None) -> Dict[str, Any]:
        """Get list of border crossing (customs) airports."""
        airports_list = self.model.get_border_crossing_airports()

        if country:
            c = country.upper()
            airports_list = [a for a in airports_list if (a.iso_country or "").upper() == c]

        # Group by country
        grouped = {}
        all_airports = []
        for a in airports_list:
            country_code = a.iso_country or "Unknown"
            if country_code not in grouped:
                grouped[country_code] = []

            airport_data = {
                "ident": a.ident,
                "name": a.name,
                "municipality": a.municipality,
                "country": a.iso_country,
                "latitude_deg": getattr(a, "latitude_deg", None),
                "longitude_deg": getattr(a, "longitude_deg", None),
            }
            grouped[country_code].append(airport_data)
            all_airports.append(airport_data)

        return {
            "count": len(all_airports),
            "by_country": grouped,
            "airports": all_airports,
            "visualization": {
                "type": "markers",
                "data": all_airports,
                "style": "customs"  # Special styling for customs airports
            }
        }

    def _get_airport_statistics(self, country: Optional[str] = None) -> Dict[str, Any]:
        """Get airport statistics, optionally filtered by country."""
        if country:
            airports = self.model.get_airports_by_country(country.upper())
        else:
            airports = list(self.model.airports.values())

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

        return {"stats": stats}

    def _get_airport_pricing(self, icao_code: str) -> Dict[str, Any]:
        """Get pricing data (landing fees, fuel prices) for an airport."""
        icao = icao_code.strip().upper()
        pricing = self.enrichment_storage.get_pricing_data(icao)

        if not pricing:
            return {
                "found": False,
                "icao_code": icao,
                "message": f"No pricing data available for {icao}. Data may not be in airfield.directory or not yet synced."
            }

        return {
            "found": True,
            "icao_code": icao,
            "pricing": {
                "landing_fees": {
                    "C172": pricing.get('landing_fee_c172'),
                    "DA42": pricing.get('landing_fee_da42'),
                    "SR22": pricing.get('landing_fee_sr22'),
                    "PC12": pricing.get('landing_fee_pc12'),
                },
                "fuel_prices": {
                    "AVGAS": pricing.get('avgas_price'),
                    "JetA1": pricing.get('jeta1_price'),
                    "SuperPlus": pricing.get('superplus_price'),
                },
                "currency": pricing.get('currency'),
                "fuel_provider": pricing.get('fuel_provider'),
                "payment_available": bool(pricing.get('payment_available')),
                "ppr_available": bool(pricing.get('ppr_available')),
                "last_updated": pricing.get('last_updated'),
                "source": pricing.get('source', 'airfield.directory')
            }
        }

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
            logger.info(f"DEBUG: RulesManager has {len(self.rules_manager.rules)} total rules loaded, loaded={self.rules_manager.loaded}")

            rules = self.rules_manager.get_rules_for_country(
                country_code=country_code,
                category=category,
                tags=tags
            )

            if not rules:
                logger.warning(f"⚠️ No rules found for {country_code.upper()}")
                return {
                    "found": False,
                    "country_code": country_code.upper(),
                    "count": 0,
                    "message": f"No rules found for {country_code.upper()}. Available countries: {', '.join(self.rules_manager.get_available_countries())}"
                }

            # Format for display
            formatted_text = self.rules_manager.format_rules_for_display(
                rules,
                group_by_category=True
            )

            categories = list(set(r.get('category', 'General') for r in rules))
            logger.info(f"✅ Found {len(rules)} rules for {country_code.upper()} across {len(categories)} categories: {', '.join(categories)}")

            return {
                "found": True,
                "country_code": country_code.upper(),
                "count": len(rules),
                "rules": rules[:50],  # Limit to 50 rules in response
                "formatted_text": formatted_text,
                "categories": categories
            }

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

            comparison = self.rules_manager.compare_rules_between_countries(
                country1=country1,
                country2=country2,
                category=category
            )

            c1_count = comparison.get('total_rules_country1', 0)
            c2_count = comparison.get('total_rules_country2', 0)
            diff_count = len(comparison.get('differences', []))

            logger.info(f"✅ Comparison complete: {country1.upper()} ({c1_count} rules) vs {country2.upper()} ({c2_count} rules) - {diff_count} differences found")

            return {
                "found": True,
                "comparison": comparison,
                "formatted_summary": comparison.get('summary', ''),
                "total_differences": diff_count,
                "message": f"Comparison between {country1.upper()} and {country2.upper()} complete."
            }

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
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_airports",
                    "description": "Search for airports by name, ICAO code, IATA code, or city name. Returns matching airports with key information.",
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
                    "description": "Find airports within a specified distance from a direct route between two airports. Useful for finding fuel stops, alternates, or customs stops.",
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
                        },
                        "required": ["from_icao", "to_icao"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_airport_details",
                    "description": "Get comprehensive details about a specific airport including runways, procedures, facilities, and AIP information.",
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
                    "description": "List all airports that are official border crossing points (with customs). Optionally filter by country.",
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
                    "description": "Get statistical information about airports in the database, such as counts of airports with customs, fuel types, etc. Optionally filter by country.",
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
                    "description": "Get pricing data (landing fees by aircraft type and fuel prices) from airfield.directory. Returns landing fees for C172, DA42, SR22, PC12 and fuel prices for AVGAS, JetA1, SuperPlus. Coverage: 30% of EU airports (678 airports with pricing).",
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
                    "description": "Get community pilot reviews (PIREPs) from airfield.directory. Returns ratings, comments, and pilot feedback for an airport. Coverage: 350 airports with reviews (448 total reviews).",
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
                    "description": "Get fuel availability and prices from airfield.directory. Shows which fuel types are available (AVGAS, JetA1, SuperPlus, etc.) and their prices if known. Coverage: 624 airports with fuel data.",
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
                    "description": "Get aviation rules and regulations for a specific European country. Includes information about customs, flight plans, airspace, IFR/VFR requirements, fuel, and other operational rules. Useful for understanding country-specific requirements for cross-border flights.",
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
                    "description": "Compare aviation rules and regulations between two European countries. Shows differences in requirements, procedures, and regulations. Essential for planning international flights to understand varying requirements.",
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
