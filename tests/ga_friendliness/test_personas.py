"""
Unit tests for ga_friendliness persona management.
"""

import pytest

from shared.ga_friendliness import (
    PersonaManager,
    PersonasConfig,
    AirportFeatureScores,
    MissingBehavior,
)


@pytest.mark.unit
class TestPersonaManager:
    """Tests for PersonaManager class."""

    def test_create_manager(self, sample_personas):
        """Test creating PersonaManager."""
        manager = PersonaManager(sample_personas)
        assert manager.version == "1.0-test"

    def test_get_persona(self, sample_personas):
        """Test getting persona by ID."""
        manager = PersonaManager(sample_personas)
        
        persona = manager.get_persona("test_ifr")
        assert persona is not None
        assert persona.label == "Test IFR Persona"

    def test_get_nonexistent_persona(self, sample_personas):
        """Test getting non-existent persona."""
        manager = PersonaManager(sample_personas)
        
        persona = manager.get_persona("nonexistent")
        assert persona is None

    def test_list_persona_ids(self, sample_personas):
        """Test listing all persona IDs."""
        manager = PersonaManager(sample_personas)
        
        ids = manager.list_persona_ids()
        assert "test_ifr" in ids
        assert "test_vfr" in ids
        assert "test_lunch" in ids


@pytest.mark.unit
class TestPersonaScoring:
    """Tests for persona score computation."""

    def test_compute_score_basic(self, sample_personas, sample_feature_scores):
        """Test basic score computation."""
        manager = PersonaManager(sample_personas)
        
        score = manager.compute_score("test_ifr", sample_feature_scores)
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_compute_score_nonexistent_persona(self, sample_personas, sample_feature_scores):
        """Test score computation for non-existent persona."""
        manager = PersonaManager(sample_personas)
        
        score = manager.compute_score("nonexistent", sample_feature_scores)
        assert score is None

    def test_compute_scores_all_personas(self, sample_personas, sample_feature_scores):
        """Test computing scores for all personas."""
        manager = PersonaManager(sample_personas)
        
        scores = manager.compute_scores_for_all_personas(sample_feature_scores)
        assert "test_ifr" in scores
        assert "test_vfr" in scores
        assert "test_lunch" in scores

    def test_score_with_missing_neutral(self, sample_personas, sample_feature_scores_with_missing):
        """Test scoring with missing values using NEUTRAL behavior."""
        manager = PersonaManager(sample_personas)
        
        # test_vfr uses NEUTRAL for missing values by default
        score = manager.compute_score("test_vfr", sample_feature_scores_with_missing)
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_score_with_missing_negative(self, sample_personas, sample_feature_scores_with_missing):
        """Test scoring with missing values using NEGATIVE behavior."""
        manager = PersonaManager(sample_personas)
        
        # test_lunch has ga_hospitality_score with NEGATIVE behavior
        # When hospitality is missing, it should be treated as 0.0
        score = manager.compute_score("test_lunch", sample_feature_scores_with_missing)
        assert score is not None
        # Score should be lower because hospitality is treated as 0 (negative)

    def test_top_personas_for_airport(self, sample_personas, sample_feature_scores):
        """Test getting top personas for an airport."""
        manager = PersonaManager(sample_personas)
        
        top = manager.get_top_personas_for_airport(sample_feature_scores, n=2)
        assert len(top) == 2
        # Should be sorted by score descending
        assert top[0][1] >= top[1][1]


@pytest.mark.unit
class TestPersonaExplanation:
    """Tests for persona score explanation."""

    def test_explain_score(self, sample_personas, sample_feature_scores):
        """Test explaining score computation."""
        manager = PersonaManager(sample_personas)
        
        explanation = manager.explain_score("test_ifr", sample_feature_scores)
        assert "persona_id" in explanation
        assert "features" in explanation
        assert "final_score" in explanation

    def test_explain_score_features(self, sample_personas, sample_feature_scores):
        """Test feature breakdown in explanation."""
        manager = PersonaManager(sample_personas)

        explanation = manager.explain_score("test_ifr", sample_feature_scores)
        features = explanation["features"]

        # test_ifr has weights for review_ops_ifr_score and aip_ops_ifr_score
        assert "review_ops_ifr_score" in features
        assert features["review_ops_ifr_score"]["weight"] > 0
        assert features["review_ops_ifr_score"]["included"] is True

    def test_explain_score_with_missing(self, sample_personas, sample_feature_scores_with_missing):
        """Test explanation with missing values."""
        manager = PersonaManager(sample_personas)

        explanation = manager.explain_score("test_ifr", sample_feature_scores_with_missing)
        features = explanation["features"]

        # review_ops_ifr_score is missing, should show resolved value
        if "review_ops_ifr_score" in features:
            assert features["review_ops_ifr_score"]["raw_value"] is None
            assert features["review_ops_ifr_score"]["resolved_value"] is not None


@pytest.mark.unit
class TestMissingBehaviorHandling:
    """Tests for missing behavior handling."""

    def test_neutral_behavior(self, sample_personas):
        """Test NEUTRAL missing behavior."""
        manager = PersonaManager(sample_personas)
        
        # All features missing
        scores = AirportFeatureScores(icao="TEST")
        
        # test_ifr uses NEUTRAL by default
        score = manager.compute_score("test_ifr", scores)
        assert score is not None
        # With all 0.5 values and normalized weights, should be 0.5
        assert 0.4 <= score <= 0.6

    def test_exclude_behavior(self, sample_personas):
        """Test EXCLUDE missing behavior."""
        manager = PersonaManager(sample_personas)

        # Feature scores with hospitality missing
        scores = AirportFeatureScores(
            icao="TEST",
            review_cost_score=0.8,
            review_fun_score=0.7,
            review_hassle_score=0.6,
            review_hospitality_score=None,
            aip_hospitality_score=None,
        )

        # The score should still be computed, just without hospitality
        score = manager.compute_score("test_lunch", scores)
        assert score is not None

    def test_negative_behavior(self, sample_personas):
        """Test NEGATIVE missing behavior."""
        manager = PersonaManager(sample_personas)

        # test_lunch has hospitality as NEGATIVE behavior

        # With hospitality present
        with_hospitality = AirportFeatureScores(
            icao="TEST",
            review_cost_score=0.5,
            review_fun_score=0.5,
            review_hassle_score=0.5,
            review_hospitality_score=0.8,
            aip_hospitality_score=0.7,
        )

        # With hospitality missing (treated as 0.0)
        without_hospitality = AirportFeatureScores(
            icao="TEST",
            review_cost_score=0.5,
            review_fun_score=0.5,
            review_hassle_score=0.5,
            review_hospitality_score=None,
            aip_hospitality_score=None,
        )

        score_with = manager.compute_score("test_lunch", with_hospitality)
        score_without = manager.compute_score("test_lunch", without_hospitality)

        # Score should be lower when hospitality is missing (treated as 0)
        assert score_with > score_without

