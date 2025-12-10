#!/usr/bin/env python3
"""
Query routing system for aviation agent.

This module provides classification of user queries into "rules" or "database" paths,
with intelligent country extraction supporting multiple input formats.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ICAO prefix to ISO-2 country code mapping
# Based on ICAO location indicators (first 2 letters)
ICAO_TO_ISO2 = {
    # Europe
    "BI": "IS",  # Iceland
    "EB": "BE",  # Belgium
    "ED": "DE",  # Germany
    "EE": "EE",  # Estonia
    "EF": "FI",  # Finland
    "EG": "GB",  # United Kingdom
    "EH": "NL",  # Netherlands
    "EI": "IE",  # Ireland
    "EK": "DK",  # Denmark
    "EL": "LU",  # Luxembourg
    "EN": "NO",  # Norway
    "EP": "PL",  # Poland
    "ES": "SE",  # Sweden
    "ET": "DE",  # Germany (also ED)
    "EV": "LV",  # Latvia
    "EY": "LT",  # Lithuania
    "LA": "AL",  # Albania
    "LB": "BG",  # Bulgaria
    "LC": "CY",  # Cyprus
    "LD": "HR",  # Croatia
    "LE": "ES",  # Spain
    "LF": "FR",  # France
    "LG": "GR",  # Greece
    "LH": "HU",  # Hungary
    "LI": "IT",  # Italy
    "LJ": "SI",  # Slovenia
    "LK": "CZ",  # Czech Republic
    "LL": "IL",  # Israel
    "LM": "MT",  # Malta
    "LO": "AT",  # Austria
    "LP": "PT",  # Portugal
    "LQ": "BA",  # Bosnia and Herzegovina
    "LR": "RO",  # Romania
    "LS": "CH",  # Switzerland
    "LT": "TR",  # Turkey
    "LU": "MD",  # Moldova
    "LV": "PS",  # Palestine
    "LW": "MK",  # North Macedonia
    "LX": "GI",  # Gibraltar
    "LY": "RS",  # Serbia
    "LZ": "SK",  # Slovakia
    
    # Additional common ICAO prefixes
    "EG": "GB",  # UK
    "LF": "FR",  # France
    "ED": "DE",  # Germany
    "LS": "CH",  # Switzerland
    "LO": "AT",  # Austria
    "LE": "ES",  # Spain
    "LI": "IT",  # Italy
    "LP": "PT",  # Portugal
    "EB": "BE",  # Belgium
    "EH": "NL",  # Netherlands
}


# Country name to ISO-2 code mapping (common variations)
COUNTRY_ALIASES = {
    # Primary names
    "france": "FR",
    "germany": "DE",
    "united kingdom": "GB",
    "uk": "GB",
    "switzerland": "CH",
    "austria": "AT",
    "spain": "ES",
    "italy": "IT",
    "portugal": "PT",
    "belgium": "BE",
    "netherlands": "NL",
    "greece": "GR",
    "poland": "PL",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "ireland": "IE",
    "czech republic": "CZ",
    "hungary": "HU",
    "romania": "RO",
    "croatia": "HR",
    "slovenia": "SI",
    "slovakia": "SK",
    "bulgaria": "BG",
    "serbia": "RS",
    "albania": "AL",
    "luxembourg": "LU",
    "estonia": "EE",
    "latvia": "LV",
    "lithuania": "LT",
    "cyprus": "CY",
    "malta": "MT",
    "iceland": "IS",
    
    # Common variations
    "england": "GB",
    "britain": "GB",
    "great britain": "GB",
    "swiss": "CH",
    "holland": "NL",
    "czech": "CZ",
    "czechia": "CZ",
}


# Keywords for fast pre-filter routing
RULES_KEYWORDS = [
    "rules", "regulations", "allowed", "required", "requirement", "requirements",
    "clearance", "schengen", "border", "poe", "point of entry",
    "flight plan", "fpl", "ifr", "vfr", "ppr", "prior permission",
    "procedures", "rules", "law", "legal", "permitted", "permissible",
    "must", "need to", "do i", "can i", "am i", "should i",
]

DATABASE_KEYWORDS = [
    "find", "search", "show", "list", "get", "airports",
    "near", "close to", "around", "between", "from", "to",
    "with avgas", "with jet", "runway", "facilities",
    "route", "distance", "navigation", "map",
    # Notification queries for specific airports go to DATABASE
    "notification", "notify", "notice", "h24", "<24h", "less than 24",
]

# Keywords that indicate notification queries - when combined with ICAO codes, route to DATABASE
NOTIFICATION_KEYWORDS = [
    "notification", "notify", "customs", "notice", "when should i",
    "how much notice", "how early", "prior notice", "h24", "24h",
]


class RouterDecision(BaseModel):
    """Result of query routing."""
    
    path: Literal["rules", "database", "both"] = Field(
        ...,
        description="Which agent path to take: rules (regulations), database (airport search), or both"
    )
    
    countries: List[str] = Field(
        default_factory=list,
        description="Extracted ISO-2 country codes (e.g., ['FR', 'GB'])"
    )
    
    confidence: float = Field(
        default=1.0,
        description="Confidence in routing decision (0.0-1.0)"
    )
    
    reasoning: str = Field(
        default="",
        description="Brief explanation of routing decision"
    )
    
    needs_clarification: bool = Field(
        default=False,
        description="Whether user input is too ambiguous and needs clarification"
    )
    
    clarification_message: Optional[str] = Field(
        default=None,
        description="Message to show user if clarification needed"
    )


class CountryExtractor:
    """
    Extracts country codes from user queries.
    
    Supports multiple input formats:
    - Country names: "France", "Germany", "United Kingdom"
    - ISO-2 codes: "FR", "GB", "DE"
    - ICAO codes: "LFMD", "EGTF" (extracts country from prefix)
    
    Also uses conversation context to infer countries from previous messages.
    """
    
    def __init__(self):
        """Initialize country extractor."""
        self.icao_to_iso = ICAO_TO_ISO2
        self.country_aliases = COUNTRY_ALIASES
        
        # Compile regex patterns for efficiency
        self.iso2_pattern = re.compile(r'\b([A-Z]{2})\b')
        self.icao_pattern = re.compile(r'\b([A-Z]{4})\b')
    
    def extract(
        self,
        query: str,
        conversation: Optional[List[BaseMessage]] = None,
        max_context_messages: int = 5
    ) -> List[str]:
        """
        Extract country codes from query and conversation context.
        
        Args:
            query: User query text
            conversation: Optional conversation history
            max_context_messages: How many previous messages to check
            
        Returns:
            List of unique ISO-2 country codes (e.g., ["FR", "GB"])
        """
        countries = set()
        
        # 1. Try explicit ISO-2 codes (FR, GB, DE)
        countries.update(self._extract_iso2_codes(query))
        
        # 2. Try country names (France, Germany, UK)
        countries.update(self._extract_country_names(query))
        
        # 3. Try ICAO codes (LFMD, EGTF)
        countries.update(self._extract_from_icao(query))
        
        # 4. Check conversation context if nothing found
        if not countries and conversation:
            for message in reversed(conversation[-max_context_messages:]):
                content = message.content if hasattr(message, 'content') else str(message)
                context_countries = self.extract(content, conversation=None)
                if context_countries:
                    countries.update(context_countries)
                    logger.debug(f"Extracted countries from context: {context_countries}")
                    break
        
        result = sorted(countries)
        if result:
            logger.debug(f"Extracted countries: {result} from query: '{query[:50]}'")
        return result
    
    def _extract_iso2_codes(self, text: str) -> List[str]:
        """Extract ISO-2 country codes (e.g., FR, GB)."""
        countries = []
        
        # Find all 2-letter uppercase codes
        matches = self.iso2_pattern.findall(text)
        
        for code in matches:
            # Check if it's a valid ISO-2 code
            # We check against known codes in our mapping
            if code in COUNTRY_ALIASES.values():
                countries.append(code)
        
        return countries
    
    def _extract_country_names(self, text: str) -> List[str]:
        """Extract countries from names (e.g., France → FR)."""
        countries = []
        text_lower = text.lower()
        
        # Sort by length (longest first) to match "United Kingdom" before "Kingdom"
        sorted_names = sorted(self.country_aliases.items(), key=lambda x: len(x[0]), reverse=True)
        
        for name, iso_code in sorted_names:
            if name in text_lower:
                countries.append(iso_code)
                # Remove matched text to avoid double-matching
                text_lower = text_lower.replace(name, "")
        
        return countries
    
    def _extract_from_icao(self, text: str) -> List[str]:
        """Extract countries from ICAO codes (e.g., LFMD → LF → FR)."""
        countries = []
        
        # Find all 4-letter uppercase codes (potential ICAO)
        matches = self.icao_pattern.findall(text)
        
        for icao in matches:
            # Extract first 2 letters (ICAO prefix)
            prefix = icao[:2]
            
            # Map to ISO-2 code
            if prefix in self.icao_to_iso:
                iso_code = self.icao_to_iso[prefix]
                countries.append(iso_code)
                logger.debug(f"ICAO {icao} → prefix {prefix} → country {iso_code}")
        
        return countries


class QueryRouter:
    """
    Routes queries to appropriate agent path (rules vs database).
    
    Uses a two-stage approach:
    1. Fast keyword pre-filter for obvious cases (~80% of queries)
    2. LLM-based classification for ambiguous queries (~20%)
    """
    
    def __init__(self, llm: Optional[Any] = None):
        """
        Initialize query router.
        
        Args:
            llm: Optional LLM instance for ambiguous queries. If None, uses environment.
        """
        self.llm = llm
        self._initialized = False
        self.country_extractor = CountryExtractor()
    
    def _ensure_llm(self):
        """Lazy initialization of LLM."""
        if self._initialized:
            return
        
        if self.llm is None:
            try:
                from langchain_openai import ChatOpenAI
                model = os.getenv("ROUTER_MODEL", "gpt-4o-mini")
                self.llm = ChatOpenAI(model=model, temperature=0)
                logger.debug(f"Initialized router LLM: {model}")
            except ImportError:
                logger.warning(
                    "LLM routing requires langchain-openai. "
                    "Using keyword-only routing."
                )
                self.llm = None
        
        self._initialized = True
    
    def route(
        self,
        query: str,
        conversation: Optional[List[BaseMessage]] = None
    ) -> RouterDecision:
        """
        Route a query to the appropriate agent path.
        
        Args:
            query: User query text
            conversation: Optional conversation history
            
        Returns:
            RouterDecision with path, countries, and reasoning
        """
        # Extract countries first
        countries = self.country_extractor.extract(query, conversation)
        
        # PRIORITY: Check for ICAO code + notification keywords → DATABASE
        # This overrides all other routing for specific airport notification queries
        has_icao = bool(re.search(r'\b[A-Z]{4}\b', query))
        notification_score = self._keyword_score(query, NOTIFICATION_KEYWORDS)
        
        if has_icao and notification_score >= 1:
            logger.info(f"ICAO + notification detected → forcing DATABASE path")
            return RouterDecision(
                path="database",
                countries=countries,
                confidence=0.95,
                reasoning=f"ICAO code with notification keywords ({notification_score}) → use notification tool"
            )
        
        # Fast keyword pre-filter
        rules_score = self._keyword_score(query, RULES_KEYWORDS)
        db_score = self._keyword_score(query, DATABASE_KEYWORDS)
        
        logger.debug(f"Keyword scores: rules={rules_score}, database={db_score}")
        
        # Strong signals (confident routing)
        if rules_score >= 2 and rules_score > db_score:
            return RouterDecision(
                path="rules",
                countries=countries,
                confidence=0.9,
                reasoning=f"Detected {rules_score} rules keywords"
            )
        
        if db_score >= 2 and db_score > rules_score:
            return RouterDecision(
                path="database",
                countries=countries,
                confidence=0.9,
                reasoning=f"Detected {db_score} database keywords"
            )
        
        # Ambiguous query - use LLM
        return self._llm_route(query, conversation, countries)
    
    def _keyword_score(self, text: str, keywords: List[str]) -> int:
        """Count how many keywords match in text."""
        text_lower = text.lower()
        return sum(1 for keyword in keywords if keyword in text_lower)
    
    def _llm_route(
        self,
        query: str,
        conversation: Optional[List[BaseMessage]],
        countries: List[str]
    ) -> RouterDecision:
        """Use LLM to classify ambiguous queries."""
        self._ensure_llm()
        
        if self.llm is None:
            # Fallback: default to rules if ambiguous
            logger.warning("No LLM available, defaulting to rules path")
            return RouterDecision(
                path="rules",
                countries=countries,
                confidence=0.5,
                reasoning="Ambiguous query, defaulting to rules (no LLM available)"
            )
        
        try:
            # Build conversation context
            context_str = ""
            if conversation:
                recent = conversation[-3:]  # Last 3 messages
                for msg in recent:
                    role = "User" if msg.type == "human" else "Assistant"
                    content = msg.content if hasattr(msg, 'content') else str(msg)
                    context_str += f"{role}: {content}\n"
            
            # Load prompt template from config
            if not hasattr(self, '_router_prompt_template'):
                from .config import get_settings, get_behavior_config
                settings = get_settings()
                behavior_config = get_behavior_config(settings.agent_config_name)
                self._router_prompt_template = behavior_config.load_prompt("router")
            
            # Format prompt with context and query
            prompt = self._router_prompt_template.format(
                context_str=context_str,
                query=query
            )
            
            response = self.llm.invoke(prompt)
            answer = response.content.strip().lower()
            
            # Parse response
            if "rules" in answer:
                path = "rules"
                reasoning = "LLM classified as rules query"
            elif "database" in answer:
                path = "database"
                reasoning = "LLM classified as database query"
            else:
                logger.warning(f"Unexpected LLM response: {answer}, defaulting to rules")
                path = "rules"
                reasoning = "Ambiguous LLM response, defaulting to rules"
            
            return RouterDecision(
                path=path,
                countries=countries,
                confidence=0.75,
                reasoning=reasoning
            )
            
        except Exception as e:
            logger.error(f"LLM routing failed: {e}")
            return RouterDecision(
                path="rules",
                countries=countries,
                confidence=0.5,
                reasoning=f"LLM routing failed, defaulting to rules: {e}"
            )


def route_query(
    query: str,
    conversation: Optional[List[BaseMessage]] = None,
    llm: Optional[Any] = None
) -> RouterDecision:
    """
    Convenience function to route a query.
    
    Args:
        query: User query text
        conversation: Optional conversation history
        llm: Optional LLM instance
        
    Returns:
        RouterDecision
    """
    router = QueryRouter(llm=llm)
    return router.route(query, conversation)


if __name__ == "__main__":
    # Simple test when run directly
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(message)s'
    )
    
    # Test cases
    test_queries = [
        ("Do I need to file a flight plan in France?", "rules with country"),
        ("Find airports near Paris", "database"),
        ("What are the rules for LFMD?", "rules with ICAO"),
        ("Show me airports between FR and GB", "database with countries"),
        ("Can I fly VFR at night in Germany?", "rules"),
        ("Airports with AVGAS", "database"),
    ]
    
    print("\n" + "=" * 70)
    print("QUERY ROUTER TEST")
    print("=" * 70)
    
    router = QueryRouter()
    
    for query, expected in test_queries:
        print(f"\nQuery: \"{query}\"")
        print(f"Expected: {expected}")
        
        decision = router.route(query)
        
        print(f"→ Path: {decision.path}")
        print(f"→ Countries: {decision.countries}")
        print(f"→ Confidence: {decision.confidence:.2f}")
        print(f"→ Reasoning: {decision.reasoning}")

