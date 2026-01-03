#!/usr/bin/env python3
"""
Next Query Predictor - Rule-based prediction of follow-up queries.

Predicts relevant follow-up queries based on:
- User query text
- Tool selected by planner
- Tool arguments (including filters)

Does NOT use tool results - predictions are purely intent-based.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .planning import AviationPlan

if TYPE_CHECKING:
    from .behavior_config import NextQueryPredictionConfig, ToolSuggestionTemplates

logger = logging.getLogger(__name__)

# Constants for suggestion categories
class SuggestionCategory:
    """Constants for suggestion categories."""
    RULES = "rules"
    ROUTE = "route"
    DETAILS = "details"
    PRICING = "pricing"

# Constants for tool names
class ToolName:
    """Constants for tool names."""
    FIND_AIRPORTS_NEAR_ROUTE = "find_airports_near_route"
    FIND_AIRPORTS_NEAR_LOCATION = "find_airports_near_location"
    SEARCH_AIRPORTS = "search_airports"
    GET_AIRPORT_DETAILS = "get_airport_details"
    GET_NOTIFICATION_FOR_AIRPORT = "get_notification_for_airport"
    ANSWER_RULES_QUESTION = "answer_rules_question"
    BROWSE_RULES = "browse_rules"
    COMPARE_RULES_BETWEEN_COUNTRIES = "compare_rules_between_countries"

# Constants for filter names
class FilterName:
    """Constants for filter names."""
    HAS_AVGAS = "has_avgas"
    POINT_OF_ENTRY = "point_of_entry"
    HAS_HARD_RUNWAY = "has_hard_runway"

# Priority constants
PRIORITY_HIGH = 5
PRIORITY_MEDIUM_HIGH = 4
PRIORITY_MEDIUM = 3
PRIORITY_LOW = 2
PRIORITY_VERY_LOW = 1


@dataclass
class QueryContext:
    """Context from current query execution - NO RESULTS."""
    user_query: str
    tool_used: str
    tool_arguments: Dict[str, Any]
    filters_applied: Dict[str, Any]

    # Derived from arguments only
    locations_mentioned: List[str]
    icao_codes_mentioned: List[str]
    countries_mentioned: List[str]


@dataclass
class SuggestedQuery:
    """A suggested follow-up query."""
    query_text: str
    tool_name: str
    category: str  # "rules", "route", "details", "pricing"
    priority: int  # 1-5, higher = more relevant


def extract_context_from_plan(
    user_query: str,
    plan: AviationPlan
) -> QueryContext:
    """Extract context from query and plan only (NO RESULTS)."""

    args = plan.arguments
    filters = args.get("filters", {})

    # Extract locations from arguments
    locations = []
    if "from_location" in args:
        locations.append(args["from_location"])
    if "to_location" in args:
        locations.append(args["to_location"])
    if "location_query" in args:
        locations.append(args["location_query"])

    # Extract ICAO codes (4 uppercase letters)
    icao_codes = []
    if "icao_code" in args:
        icao_codes.append(args["icao_code"])
    for loc in locations:
        if loc and len(loc) == 4 and loc.isupper():
            icao_codes.append(loc)

    # Extract countries from arguments
    countries = []
    if "country" in args:
        countries.append(args["country"])
    if "country_code" in args:
        countries.append(args["country_code"])
    if "country1" in args:
        countries.append(args["country1"])
    if "country2" in args:
        countries.append(args["country2"])
    if "country" in filters:
        countries.append(filters["country"])

    return QueryContext(
        user_query=user_query,
        tool_used=plan.selected_tool,
        tool_arguments=args,
        filters_applied=filters,
        locations_mentioned=locations,
        icao_codes_mentioned=icao_codes,
        countries_mentioned=countries
    )


class NextQueryPredictor:
    """Predicts relevant follow-up queries based on current context."""

    def __init__(
        self,
        rules_json_path: Optional[Path] = None,
        config: Optional["NextQueryPredictionConfig"] = None
    ):
        """
        Initialize predictor with rule-based templates.

        Args:
            rules_json_path: Optional path to rules.json for loading actual rule questions
            config: Optional NextQueryPredictionConfig with templates. If not provided, uses hard-coded defaults.
        """
        self.rules_by_category: Dict[str, List[str]] = {}
        self.rules_by_country: Dict[str, List[str]] = {}
        self.config = config
        self.templates: Dict[str, "ToolSuggestionTemplates"] = {}

        # Load rules.json if provided
        if rules_json_path:
            rules_path = Path(rules_json_path)
            if rules_path.exists():
                self._load_rules(rules_path)
                if self.rules_by_category:
                    logger.info(f"NextQueryPredictor initialized with {len(self.rules_by_category)} rule categories from {rules_path}")
                else:
                    logger.warning(f"NextQueryPredictor: rules.json loaded but no categories found in {rules_path}")
            else:
                logger.warning(f"NextQueryPredictor: rules.json not found at {rules_path}")

        if not self.rules_by_category:
            logger.info("NextQueryPredictor initialized (rule-based, no rules.json loaded)")
        
        # Load templates from file if config provided
        if self.config and self.config.templates_path:
            self._load_templates(self.config.templates_path)
            if self.templates:
                logger.info(f"NextQueryPredictor initialized with {len(self.templates)} tool templates from {self.config.templates_path}")
            else:
                logger.warning(f"NextQueryPredictor: No templates loaded from {self.config.templates_path}, will use hard-coded defaults")

    def _load_rules(self, rules_json_path: Path):
        """Load rule questions from rules.json."""
        try:
            with open(rules_json_path, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)

            # Handle both flat array format and nested format
            if isinstance(rules_data, list):
                # Flat format: [{"country_code": "GB", "question_id": "...", ...}, ...]
                rules_list = rules_data
            elif isinstance(rules_data, dict) and "questions" in rules_data:
                # Nested format: {"questions": [...]}
                # Extract questions without expanding by country (we only need unique questions)
                rules_list = rules_data.get("questions", [])
            else:
                logger.warning(f"Invalid rules.json format: expected list or dict with 'questions' key")
                return

            # Group questions by category
            for rule in rules_list:
                question = rule.get('question_text', '')
                category = rule.get('category', 'Unknown')

                if not question or category == 'ignore':
                    continue

                # Store by category (unique questions only)
                if category not in self.rules_by_category:
                    self.rules_by_category[category] = []
                if question not in self.rules_by_category[category]:
                    self.rules_by_category[category].append(question)

                # For nested format, also store by country
                if isinstance(rule.get('answers_by_country'), dict):
                    for country in rule['answers_by_country'].keys():
                        if country not in self.rules_by_country:
                            self.rules_by_country[country] = []
                        if question not in self.rules_by_country[country]:
                            self.rules_by_country[country].append(question)
                # For flat format
                elif 'country_code' in rule:
                    country = rule['country_code']
                    if country not in self.rules_by_country:
                        self.rules_by_country[country] = []
                    if question not in self.rules_by_country[country]:
                        self.rules_by_country[country].append(question)

            logger.debug(f"Loaded {sum(len(q) for q in self.rules_by_category.values())} unique rule questions from {len(rules_list)} entries")
        except Exception as e:
            logger.warning(f"Failed to load rules.json: {e}")

    def _load_templates(self, templates_path: str):
        """Load suggestion templates from JSON file."""
        from .behavior_config import ToolSuggestionTemplates
        from .config import PROJECT_ROOT
        
        try:
            # Resolve path relative to configs/ directory
            templates_file = PROJECT_ROOT / "configs" / templates_path
            
            logger.info(f"NextQueryPredictor: Loading templates from {templates_file}")
            
            if not templates_file.exists():
                logger.warning(f"NextQueryPredictor: templates file not found at {templates_file}")
                logger.warning(f"NextQueryPredictor: PROJECT_ROOT={PROJECT_ROOT}, templates_path={templates_path}")
                return
            
            with open(templates_file, 'r', encoding='utf-8') as f:
                templates_data = json.load(f)
            
            # Parse templates
            templates_dict = templates_data.get("templates", {})
            if not templates_dict:
                logger.warning(f"NextQueryPredictor: No 'templates' key found in {templates_file}")
                return
            
            for tool_name, tool_templates_data in templates_dict.items():
                try:
                    self.templates[tool_name] = ToolSuggestionTemplates(**tool_templates_data)
                except Exception as e:
                    logger.error(f"NextQueryPredictor: Failed to parse templates for {tool_name}: {e}")
                    continue
            
            logger.info(f"NextQueryPredictor: Successfully loaded templates for {len(self.templates)} tools from {templates_file}")
        except json.JSONDecodeError as e:
            logger.error(f"NextQueryPredictor: Invalid JSON in templates file {templates_path}: {e}")
        except Exception as e:
            logger.error(f"NextQueryPredictor: Failed to load templates from {templates_path}: {e}", exc_info=True)

    def predict_next_queries(
        self,
        context: QueryContext,
        max_suggestions: int = 4
    ) -> List[SuggestedQuery]:
        """
        Generate follow-up query suggestions using rule-based templates.

        Args:
            context: Query context (query + plan, no results)
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of suggested queries, ranked by priority
        """
        suggestions = []

        # Apply tool-specific templates
        if context.tool_used == ToolName.FIND_AIRPORTS_NEAR_ROUTE:
            suggestions.extend(self._route_tool_suggestions(context))
        elif context.tool_used == ToolName.FIND_AIRPORTS_NEAR_LOCATION:
            suggestions.extend(self._location_tool_suggestions(context))
        elif context.tool_used == ToolName.SEARCH_AIRPORTS:
            suggestions.extend(self._search_tool_suggestions(context))
        elif context.tool_used == ToolName.GET_AIRPORT_DETAILS:
            suggestions.extend(self._airport_details_suggestions(context))
        elif context.tool_used in [ToolName.ANSWER_RULES_QUESTION, ToolName.BROWSE_RULES, ToolName.COMPARE_RULES_BETWEEN_COUNTRIES]:
            suggestions.extend(self._rules_tool_suggestions(context))

        # Rank and return top suggestions
        ranked = self._rank_suggestions(suggestions)
        return ranked[:max_suggestions]

    def _suggest_filter_based_queries(
        self,
        context: QueryContext,
        filter_suggestions: List[Dict[str, Any]]
    ) -> List[SuggestedQuery]:
        """
        Generate suggestions based on missing filters.
        
        Args:
            context: Query context
            filter_suggestions: List of dicts with keys: filter, query_text, tool_name, category, priority
            
        Returns:
            List of SuggestedQuery objects for filters not yet applied
        """
        suggestions = []
        for filter_config in filter_suggestions:
            filter_name = filter_config["filter"]
            if not context.filters_applied.get(filter_name):
                suggestions.append(SuggestedQuery(
                    query_text=filter_config["query_text"],
                    tool_name=filter_config["tool_name"],
                    category=filter_config["category"],
                    priority=filter_config["priority"]
                ))
        return suggestions

    def _suggest_entity_based_queries(
        self,
        context: QueryContext,
        entity_suggestions: List[Dict[str, Any]]
    ) -> List[SuggestedQuery]:
        """
        Generate suggestions based on mentioned entities (ICAO codes, countries, locations).
        
        Args:
            context: Query context
            entity_suggestions: List of dicts with keys: entity_type, query_template, tool_name, category, priority
                entity_type should be one of: "icao_codes", "countries", "locations"
                
        Returns:
            List of SuggestedQuery objects for entities found in context
        """
        suggestions = []
        for entity_config in entity_suggestions:
            entity_type = entity_config["entity_type"]
            entities = getattr(context, f"{entity_type}_mentioned", [])
            
            if entities:
                # Extract template variable name
                # "icao_codes" -> "icao", "countries" -> "country", "locations" -> "location"
                # First remove _codes/_mentioned suffixes, then singularize
                var_name = entity_type.replace("_codes", "").replace("_mentioned", "")
                if var_name.endswith("ies"):
                    var_name = var_name[:-3] + "y"  # countries -> country
                elif var_name.endswith("s"):
                    var_name = var_name[:-1]  # locations -> location
                entity_value = entities[0]
                
                # Format template with entity value
                query_text = entity_config["query_template"].format(**{var_name: entity_value})
                
                suggestions.append(SuggestedQuery(
                    query_text=query_text,
                    tool_name=entity_config["tool_name"],
                    category=entity_config["category"],
                    priority=entity_config["priority"]
                ))
        return suggestions

    def _route_tool_suggestions(self, context: QueryContext) -> List[SuggestedQuery]:
        """Suggestions for route planning queries."""
        suggestions = []

        # Get templates from config or use defaults
        templates = self._get_tool_templates(ToolName.FIND_AIRPORTS_NEAR_ROUTE)

        # Filter-based suggestions
        if templates.filters:
            filter_suggestions = [
                {
                    "filter": f.filter,
                    "query_text": f.query_template,
                    "tool_name": f.tool_name,
                    "category": f.category,
                    "priority": f.priority
                }
                for f in templates.filters
            ]
            suggestions.extend(self._suggest_filter_based_queries(context, filter_suggestions))
        else:
            # Fallback to hard-coded defaults
            filter_suggestions = [
                {
                    "filter": FilterName.HAS_AVGAS,
                    "query_text": "Show me airports with AVGAS along this route",
                    "tool_name": ToolName.FIND_AIRPORTS_NEAR_ROUTE,
                    "category": SuggestionCategory.ROUTE,
                    "priority": PRIORITY_MEDIUM_HIGH
                },
                {
                    "filter": FilterName.POINT_OF_ENTRY,
                    "query_text": "Which airports have customs facilities on this route?",
                    "tool_name": ToolName.FIND_AIRPORTS_NEAR_ROUTE,
                    "category": SuggestionCategory.ROUTE,
                    "priority": PRIORITY_HIGH
                }
            ]
            suggestions.extend(self._suggest_filter_based_queries(context, filter_suggestions))

        # Entity-based suggestions (ICAO codes)
        if templates.entities:
            entity_suggestions = [
                {
                    "entity_type": e.entity_type,
                    "query_template": e.query_template,
                    "tool_name": e.tool_name,
                    "category": e.category,
                    "priority": e.priority
                }
                for e in templates.entities
            ]
            suggestions.extend(self._suggest_entity_based_queries(context, entity_suggestions))
        else:
            # Fallback to hard-coded defaults
            entity_suggestions = [
                {
                    "entity_type": "icao_codes",
                    "query_template": "What are the procedures at {icao}?",
                    "tool_name": ToolName.GET_AIRPORT_DETAILS,
                    "category": SuggestionCategory.DETAILS,
                    "priority": PRIORITY_MEDIUM
                },
                {
                    "entity_type": "icao_codes",
                    "query_template": "Tell me more about {icao}",
                    "tool_name": ToolName.GET_AIRPORT_DETAILS,
                    "category": SuggestionCategory.DETAILS,
                    "priority": PRIORITY_MEDIUM
                }
            ]
            suggestions.extend(self._suggest_entity_based_queries(context, entity_suggestions))

        # ALWAYS suggest rules for route queries (not just cross-country)
        # Routes typically involve multiple countries or international flight
        suggestions.extend(self._get_route_rule_suggestions(context, templates))

        return suggestions

    def _get_tool_templates(self, tool_name: str) -> "ToolSuggestionTemplates":
        """Get templates for a tool from loaded templates, or return empty templates."""
        from .behavior_config import ToolSuggestionTemplates
        
        return self.templates.get(tool_name, ToolSuggestionTemplates())

    def _get_route_rule_suggestions(
        self,
        context: QueryContext,
        templates: Optional["ToolSuggestionTemplates"] = None
    ) -> List[SuggestedQuery]:
        """
        Get rule suggestions for route queries.

        Provides variety by selecting one question from each relevant category.
        Works for ALL route queries, not just cross-country.
        """
        suggestions = []
        
        if templates is None:
            templates = self._get_tool_templates(ToolName.FIND_AIRPORTS_NEAR_ROUTE)

        # If we have loaded rules from rules.json, use actual questions
        if self.rules_by_category:
            # Use category priorities from config if available
            if templates.rule_categories:
                for cat_template in templates.rule_categories:
                    questions = self.rules_by_category.get(cat_template.name, [])
                    if questions:
                        # Take first N questions from this category
                        for question in questions[:cat_template.max_questions]:
                            suggestions.append(SuggestedQuery(
                                query_text=question,
                                tool_name=ToolName.ANSWER_RULES_QUESTION,
                                category=SuggestionCategory.RULES,
                                priority=cat_template.priority
                            ))
            else:
                # Fallback to hard-coded category priorities
                category_priorities = [
                    ('International', PRIORITY_HIGH, 1),
                    ('VFR', PRIORITY_MEDIUM_HIGH, 1),
                    ('Airspace', PRIORITY_MEDIUM_HIGH, 1),
                    ('Flight Rules', PRIORITY_MEDIUM_HIGH, 1),
                    ('IFR', PRIORITY_MEDIUM, 1),
                    ('Airfields', PRIORITY_MEDIUM, 1),
                ]

                for category, priority, max_count in category_priorities:
                    questions = self.rules_by_category.get(category, [])
                    if questions:
                        for question in questions[:max_count]:
                            suggestions.append(SuggestedQuery(
                                query_text=question,
                                tool_name=ToolName.ANSWER_RULES_QUESTION,
                                category=SuggestionCategory.RULES,
                                priority=priority
                            ))
        else:
            # Use fallback queries from config if available
            if templates.fallback_queries:
                for fallback_query in templates.fallback_queries:
                    suggestions.append(SuggestedQuery(
                        query_text=fallback_query,
                        tool_name=ToolName.ANSWER_RULES_QUESTION,
                        category=SuggestionCategory.RULES,
                        priority=PRIORITY_MEDIUM_HIGH
                    ))
            else:
                # Fallback to hard-coded generic questions
                suggestions.append(SuggestedQuery(
                    query_text="What are the customs rules for countries along this route?",
                    tool_name=ToolName.ANSWER_RULES_QUESTION,
                    category=SuggestionCategory.RULES,
                    priority=PRIORITY_MEDIUM_HIGH
                ))
                suggestions.append(SuggestedQuery(
                    query_text="Do I need to file a flight plan for this route?",
                    tool_name=ToolName.ANSWER_RULES_QUESTION,
                    category=SuggestionCategory.RULES,
                    priority=PRIORITY_MEDIUM_HIGH
                ))

        return suggestions

    def _location_tool_suggestions(self, context: QueryContext) -> List[SuggestedQuery]:
        """Suggestions for location-based searches."""
        suggestions = []

        location = context.tool_arguments.get("location_query", "this location")
        templates = self._get_tool_templates(ToolName.FIND_AIRPORTS_NEAR_LOCATION)

        # Filter-based suggestions
        if templates.filters:
            # Format templates with location variable
            filter_suggestions = []
            for f in templates.filters:
                query_text = f.query_template.format(location=location) if "{location}" in f.query_template else f.query_template
                filter_suggestions.append({
                    "filter": f.filter,
                    "query_text": query_text,
                    "tool_name": f.tool_name,
                    "category": f.category,
                    "priority": f.priority
                })
            suggestions.extend(self._suggest_filter_based_queries(context, filter_suggestions))
        else:
            # Fallback to hard-coded defaults
            filter_suggestions = [
                {
                    "filter": FilterName.HAS_HARD_RUNWAY,
                    "query_text": f"Show airports with hard runways near {location}",
                    "tool_name": ToolName.FIND_AIRPORTS_NEAR_LOCATION,
                    "category": SuggestionCategory.ROUTE,
                    "priority": PRIORITY_MEDIUM
                },
                {
                    "filter": FilterName.HAS_AVGAS,
                    "query_text": f"Show airports with AVGAS near {location}",
                    "tool_name": ToolName.FIND_AIRPORTS_NEAR_LOCATION,
                    "category": SuggestionCategory.ROUTE,
                    "priority": PRIORITY_MEDIUM_HIGH
                }
            ]
            suggestions.extend(self._suggest_filter_based_queries(context, filter_suggestions))

        # Entity-based suggestions (countries)
        if templates.entities:
            entity_suggestions = [
                {
                    "entity_type": e.entity_type,
                    "query_template": e.query_template,
                    "tool_name": e.tool_name,
                    "category": e.category,
                    "priority": e.priority
                }
                for e in templates.entities
            ]
            suggestions.extend(self._suggest_entity_based_queries(context, entity_suggestions))
        else:
            # Fallback to hard-coded defaults
            entity_suggestions = [
                {
                    "entity_type": "countries",
                    "query_template": "What are the landing requirements for {country}?",
                    "tool_name": ToolName.ANSWER_RULES_QUESTION,
                    "category": SuggestionCategory.RULES,
                    "priority": PRIORITY_MEDIUM_HIGH
                }
            ]
            suggestions.extend(self._suggest_entity_based_queries(context, entity_suggestions))

        return suggestions

    def _search_tool_suggestions(self, context: QueryContext) -> List[SuggestedQuery]:
        """Suggestions for airport search queries."""
        suggestions = []
        templates = self._get_tool_templates(ToolName.SEARCH_AIRPORTS)

        # Filter-based suggestions
        if templates.filters:
            filter_suggestions = [
                {
                    "filter": f.filter,
                    "query_text": f.query_template,
                    "tool_name": f.tool_name,
                    "category": f.category,
                    "priority": f.priority
                }
                for f in templates.filters
            ]
            suggestions.extend(self._suggest_filter_based_queries(context, filter_suggestions))
        else:
            # Fallback to hard-coded defaults
            filter_suggestions = [
                {
                    "filter": FilterName.POINT_OF_ENTRY,
                    "query_text": "Show only airports with customs facilities",
                    "tool_name": ToolName.SEARCH_AIRPORTS,
                    "category": SuggestionCategory.ROUTE,
                    "priority": PRIORITY_MEDIUM
                }
            ]
            suggestions.extend(self._suggest_filter_based_queries(context, filter_suggestions))

        # Entity-based suggestions (countries)
        if templates.entities:
            entity_suggestions = [
                {
                    "entity_type": e.entity_type,
                    "query_template": e.query_template,
                    "tool_name": e.tool_name,
                    "category": e.category,
                    "priority": e.priority
                }
                for e in templates.entities
            ]
            suggestions.extend(self._suggest_entity_based_queries(context, entity_suggestions))
        else:
            # Fallback to hard-coded defaults
            entity_suggestions = [
                {
                    "entity_type": "countries",
                    "query_template": "What are the VFR rules for {country}?",
                    "tool_name": ToolName.ANSWER_RULES_QUESTION,
                    "category": SuggestionCategory.RULES,
                    "priority": PRIORITY_MEDIUM_HIGH
                }
            ]
            suggestions.extend(self._suggest_entity_based_queries(context, entity_suggestions))

        return suggestions

    def _airport_details_suggestions(self, context: QueryContext) -> List[SuggestedQuery]:
        """Suggestions after viewing airport details."""
        suggestions = []

        icao = context.tool_arguments.get("icao_code")
        if not icao:
            return suggestions

        templates = self._get_tool_templates(ToolName.GET_AIRPORT_DETAILS)

        # Suggest notification requirements (always shown for airport details)
        # This is hard-coded as it's tool-specific, not template-based
        suggestions.append(SuggestedQuery(
            query_text=f"What are the notification requirements for {icao}?",
            tool_name=ToolName.GET_NOTIFICATION_FOR_AIRPORT,
            category=SuggestionCategory.DETAILS,
            priority=PRIORITY_MEDIUM_HIGH
        ))

        # Entity-based suggestions (countries)
        if templates.entities:
            entity_suggestions = [
                {
                    "entity_type": e.entity_type,
                    "query_template": e.query_template,
                    "tool_name": e.tool_name,
                    "category": e.category,
                    "priority": e.priority
                }
                for e in templates.entities
            ]
            suggestions.extend(self._suggest_entity_based_queries(context, entity_suggestions))
        else:
            # Fallback to hard-coded defaults
            entity_suggestions = [
                {
                    "entity_type": "countries",
                    "query_template": "What are the customs rules for {country}?",
                    "tool_name": ToolName.ANSWER_RULES_QUESTION,
                    "category": SuggestionCategory.RULES,
                    "priority": PRIORITY_MEDIUM
                }
            ]
            suggestions.extend(self._suggest_entity_based_queries(context, entity_suggestions))

        return suggestions


    def _rules_tool_suggestions(self, context: QueryContext) -> List[SuggestedQuery]:
        """Suggestions after viewing rules."""
        suggestions = []

        # Entity-based suggestions (countries)
        if context.countries_mentioned:
            country = context.countries_mentioned[0]
            suggestions.append(SuggestedQuery(
                query_text=f"Which airports have customs in {country}?",
                tool_name=ToolName.SEARCH_AIRPORTS,
                category=SuggestionCategory.ROUTE,
                priority=PRIORITY_HIGH
            ))

            # Suggest VFR rules if not already viewing them
            if "vfr" not in context.user_query.lower():
                suggestions.append(SuggestedQuery(
                    query_text=f"What are the VFR weather minimums for {country}?",
                    tool_name=ToolName.ANSWER_RULES_QUESTION,
                    category=SuggestionCategory.RULES,
                    priority=PRIORITY_MEDIUM_HIGH
                ))

        # Suggest comparison if only one country
        if len(context.countries_mentioned) == 1:
            suggestions.append(SuggestedQuery(
                query_text="Compare rules with neighboring countries",
                tool_name=ToolName.COMPARE_RULES_BETWEEN_COUNTRIES,
                category=SuggestionCategory.RULES,
                priority=PRIORITY_MEDIUM
            ))

        return suggestions

    def _rank_suggestions(self, suggestions: List[SuggestedQuery]) -> List[SuggestedQuery]:
        """
        Rank suggestions by priority and diversity.

        Ensures variety by preferring different categories and tools.
        """
        if not suggestions:
            return []

        # Sort by priority (descending)
        sorted_suggestions = sorted(suggestions, key=lambda s: s.priority, reverse=True)

        # Deduplicate by query text
        seen_queries = set()
        unique_suggestions = []
        for suggestion in sorted_suggestions:
            if suggestion.query_text not in seen_queries:
                seen_queries.add(suggestion.query_text)
                unique_suggestions.append(suggestion)

        # Prefer diversity in categories
        ranked = []
        seen_categories = set()

        # First pass: one from each category
        for suggestion in unique_suggestions:
            if suggestion.category not in seen_categories:
                ranked.append(suggestion)
                seen_categories.add(suggestion.category)

        # Second pass: fill remaining slots
        for suggestion in unique_suggestions:
            if suggestion not in ranked:
                ranked.append(suggestion)

        return ranked
