#!/usr/bin/env python3
"""
Unit tests for routing system (routing.py).
"""
import pytest
from unittest.mock import Mock

from langchain_core.messages import HumanMessage, AIMessage

from shared.aviation_agent.routing import (
    CountryExtractor,
    QueryRouter,
    RouterDecision,
    route_query,
    ICAO_TO_ISO2,
    COUNTRY_ALIASES,
)


class TestCountryExtractor:
    """Tests for CountryExtractor class."""
    
    @pytest.fixture
    def extractor(self):
        return CountryExtractor()
    
    def test_extract_iso2_codes(self, extractor):
        """Test extraction of ISO-2 country codes."""
        assert extractor.extract("Flying in FR") == ["FR"]
        assert extractor.extract("From FR to GB") == ["FR", "GB"]
        assert set(extractor.extract("FR GB DE")) == {"FR", "GB", "DE"}
    
    def test_extract_country_names(self, extractor):
        """Test extraction from country names."""
        assert extractor.extract("Flying in France") == ["FR"]
        assert set(extractor.extract("From France to Germany")) == {"FR", "DE"}
        assert extractor.extract("United Kingdom") == ["GB"]
    
    def test_extract_country_aliases(self, extractor):
        """Test common country name variations."""
        assert extractor.extract("UK") == ["GB"]
        assert extractor.extract("Holland") == ["NL"]
        assert extractor.extract("Swiss") == ["CH"]
    
    def test_extract_icao_codes(self, extractor):
        """Test extraction from ICAO codes."""
        # LFMD → LF → FR
        assert extractor.extract("Rules for LFMD") == ["FR"]
        # EGTF → EG → GB
        assert extractor.extract("Arriving at EGTF") == ["GB"]
        # Multiple ICAO codes
        result = extractor.extract("From LFPG to LOWI")
        assert "FR" in result  # LFPG → FR
        assert "AT" in result  # LOWI → AT
    
    def test_extract_mixed_formats(self, extractor):
        """Test extraction with mixed input formats."""
        # Country name + ICAO
        result = extractor.extract("From France to LOWI")
        assert "FR" in result
        assert "AT" in result
        
        # ISO + country name
        result = extractor.extract("From FR to Germany")
        assert "FR" in result
        assert "DE" in result
    
    def test_extract_from_context(self, extractor):
        """Test extraction from conversation context."""
        conversation = [
            HumanMessage(content="Tell me about France"),
            AIMessage(content="France is..."),
            HumanMessage(content="What about customs?"),  # No country here
        ]
        
        # Should extract FR from context
        result = extractor.extract("What about customs?", conversation)
        assert "FR" in result
    
    def test_no_countries(self, extractor):
        """Test handling of queries with no countries."""
        assert extractor.extract("What are the general rules?") == []
        assert extractor.extract("Tell me about airports") == []
    
    def test_case_insensitivity(self, extractor):
        """Test that country names are case-insensitive."""
        assert extractor.extract("france") == ["FR"]
        assert extractor.extract("FRANCE") == ["FR"]
        assert extractor.extract("France") == ["FR"]


class TestICAOMapping:
    """Tests for ICAO to ISO-2 mapping."""
    
    def test_common_icao_prefixes(self):
        """Test common ICAO prefixes are mapped."""
        assert ICAO_TO_ISO2["LF"] == "FR"  # France
        assert ICAO_TO_ISO2["EG"] == "GB"  # UK
        assert ICAO_TO_ISO2["ED"] == "DE"  # Germany
        assert ICAO_TO_ISO2["LS"] == "CH"  # Switzerland
        assert ICAO_TO_ISO2["LO"] == "AT"  # Austria
    
    def test_country_aliases(self):
        """Test country name aliases."""
        assert COUNTRY_ALIASES["france"] == "FR"
        assert COUNTRY_ALIASES["uk"] == "GB"
        assert COUNTRY_ALIASES["holland"] == "NL"
        assert COUNTRY_ALIASES["swiss"] == "CH"


class TestQueryRouter:
    """Tests for QueryRouter class."""
    
    @pytest.fixture
    def router(self):
        """Create router without LLM for fast tests."""
        return QueryRouter(llm=None)
    
    def test_rules_keywords(self, router):
        """Test routing based on rules keywords."""
        decision = router.route("Do I need to file a flight plan?")
        assert decision.path == "rules"
        assert decision.confidence >= 0.8
    
    def test_database_keywords(self, router):
        """Test routing based on database keywords."""
        decision = router.route("Find airports near Paris")
        assert decision.path == "database"
        assert decision.confidence >= 0.8
    
    def test_rules_with_country(self, router):
        """Test rules query with country extraction."""
        decision = router.route("What are customs rules in France?")
        assert decision.path == "rules"
        assert "FR" in decision.countries
    
    def test_database_with_country(self, router):
        """Test database query with country extraction."""
        decision = router.route("Find airports in Germany")
        assert decision.path == "database"
        assert "DE" in decision.countries
    
    def test_icao_country_extraction(self, router):
        """Test country extraction from ICAO codes."""
        decision = router.route("What are the rules for LFMD?")
        assert decision.path == "rules"
        assert "FR" in decision.countries  # LFMD → FR
    
    def test_multi_country(self, router):
        """Test extraction of multiple countries for comparison queries.

        Comparison queries route to 'database' path because compare_rules_between_countries
        is a database tool that uses the ComparisonService for embedding-based comparison.
        """
        decision = router.route("Compare rules between France and Germany")
        # Comparison queries with 2+ countries go to database path (compare_rules_between_countries tool)
        assert decision.path == "database"
        assert "FR" in decision.countries
        assert "DE" in decision.countries
    
    def test_strong_rules_signal(self, router):
        """Test query with multiple rules keywords."""
        decision = router.route("Am I allowed to fly VFR with these requirements?")
        assert decision.path == "rules"
        assert decision.confidence >= 0.8
    
    def test_strong_database_signal(self, router):
        """Test query with multiple database keywords."""
        decision = router.route("Find and show airports near route")
        assert decision.path == "database"
        assert decision.confidence >= 0.8


class TestQueryRouterWithLLM:
    """Tests for QueryRouter with LLM (mocked)."""
    
    def test_ambiguous_query_with_llm(self):
        """Test LLM routing for ambiguous queries."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = "rules"
        mock_llm.invoke.return_value = mock_response
        
        router = QueryRouter(llm=mock_llm)
        decision = router.route("Tell me about France")
        
        assert decision.path == "rules"
        mock_llm.invoke.assert_called_once()
    
    def test_llm_failure_fallback(self):
        """Test fallback when LLM fails."""
        mock_llm = Mock()
        mock_llm.invoke.side_effect = Exception("API error")
        
        router = QueryRouter(llm=mock_llm)
        decision = router.route("Ambiguous query")
        
        # Should fallback gracefully
        assert decision.path in ["rules", "database"]
        assert "failed" in decision.reasoning.lower() or "default" in decision.reasoning.lower()
    
    def test_llm_database_response(self):
        """Test LLM routing to database path."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = "database"
        mock_llm.invoke.return_value = mock_response
        
        router = QueryRouter(llm=mock_llm)
        decision = router.route("Something about airports")
        
        assert decision.path == "database"


class TestRouterDecision:
    """Tests for RouterDecision model."""
    
    def test_model_creation(self):
        """Test creating RouterDecision."""
        decision = RouterDecision(
            path="rules",
            countries=["FR", "GB"],
            confidence=0.9,
            reasoning="Test reasoning"
        )
        
        assert decision.path == "rules"
        assert decision.countries == ["FR", "GB"]
        assert decision.confidence == 0.9
        assert decision.reasoning == "Test reasoning"
    
    def test_default_values(self):
        """Test default values in RouterDecision."""
        decision = RouterDecision(path="rules")
        
        assert decision.countries == []
        assert decision.confidence == 1.0
        assert decision.reasoning == ""
        assert decision.needs_clarification is False
        assert decision.clarification_message is None


class TestConvenienceFunction:
    """Tests for route_query convenience function."""
    
    def test_route_query_function(self):
        """Test route_query convenience function."""
        decision = route_query("Do I need a flight plan?")
        assert isinstance(decision, RouterDecision)
        assert decision.path in ["rules", "database", "both"]


@pytest.mark.integration
class TestRouterIntegration:
    """Integration tests with real data."""
    
    def test_real_queries(self):
        """Test router with real-world queries."""
        router = QueryRouter(llm=None)  # No LLM for speed
        
        test_cases = [
            # (query, expected_path, expected_countries)
            ("Do I need to file a flight plan in France?", "rules", ["FR"]),
            ("Find airports near Paris", "database", []),
            ("What are the rules for LFMD?", "rules", ["FR"]),
            ("Show me airports between FR and GB", "database", ["FR", "GB"]),
            ("Can I fly VFR at night in Germany?", "rules", ["DE"]),
            ("Airports with AVGAS in Switzerland", "database", ["CH"]),
        ]
        
        for query, expected_path, expected_countries in test_cases:
            decision = router.route(query)
            assert decision.path == expected_path, f"Failed for: {query}"
            assert set(decision.countries) == set(expected_countries), f"Failed countries for: {query}"
    
    def test_context_aware_routing(self):
        """Test routing with conversation context."""
        router = QueryRouter(llm=None)
        
        conversation = [
            HumanMessage(content="Tell me about France"),
            AIMessage(content="France is..."),
        ]
        
        # Second query without country mention
        decision = router.route("What about customs?", conversation)
        
        # Should extract FR from context
        assert "FR" in decision.countries


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

