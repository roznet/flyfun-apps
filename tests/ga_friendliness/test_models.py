"""
Unit tests for ga_friendliness models.
"""

import pytest
from pydantic import ValidationError

from shared.ga_friendliness import (
    # Models
    RawReview,
    AspectLabel,
    ReviewExtraction,
    OntologyConfig,
    PersonaWeights,
    MissingBehavior,
    PersonaMissingBehaviors,
    PersonaConfig,
    PersonasConfig,
    AirportFeatureScores,
    AirportStats,
    NotificationRule,
    RuleSummary,
    FailureMode,
    BuildMetrics,
)


@pytest.mark.unit
class TestRawReview:
    """Tests for RawReview model."""

    def test_create_minimal(self):
        """Test creating RawReview with minimal fields."""
        review = RawReview(icao="EGKB", review_text="Great airfield!")
        assert review.icao == "EGKB"
        assert review.review_text == "Great airfield!"
        assert review.source == "unknown"

    def test_create_full(self):
        """Test creating RawReview with all fields."""
        review = RawReview(
            icao="EGKB",
            review_text="Great airfield!",
            review_id="review_001",
            rating=4.5,
            timestamp="2024-06-15T10:30:00Z",
            language="EN",
            ai_generated=False,
            source="airfield.directory",
        )
        assert review.rating == 4.5
        assert review.source == "airfield.directory"

    def test_missing_required_fields(self):
        """Test that missing required fields raise error."""
        with pytest.raises(ValidationError):
            RawReview(icao="EGKB")  # Missing review_text


@pytest.mark.unit
class TestAspectLabel:
    """Tests for AspectLabel model."""

    def test_create_valid(self):
        """Test creating valid AspectLabel."""
        label = AspectLabel(aspect="cost", label="expensive", confidence=0.85)
        assert label.aspect == "cost"
        assert label.label == "expensive"
        assert label.confidence == 0.85

    def test_confidence_validation(self):
        """Test confidence must be in [0, 1]."""
        with pytest.raises(ValidationError):
            AspectLabel(aspect="cost", label="cheap", confidence=1.5)
        
        with pytest.raises(ValidationError):
            AspectLabel(aspect="cost", label="cheap", confidence=-0.1)

    def test_boundary_confidence(self):
        """Test boundary confidence values."""
        label_min = AspectLabel(aspect="cost", label="cheap", confidence=0.0)
        label_max = AspectLabel(aspect="cost", label="cheap", confidence=1.0)
        assert label_min.confidence == 0.0
        assert label_max.confidence == 1.0


@pytest.mark.unit
class TestReviewExtraction:
    """Tests for ReviewExtraction model."""

    def test_create_empty(self):
        """Test creating ReviewExtraction with no aspects."""
        extraction = ReviewExtraction()
        assert extraction.aspects == []
        assert extraction.review_id is None

    def test_create_with_aspects(self, sample_extraction):
        """Test creating ReviewExtraction with aspects."""
        assert len(sample_extraction.aspects) == 3
        assert sample_extraction.review_id == "review_001"


@pytest.mark.unit
class TestOntologyConfig:
    """Tests for OntologyConfig model."""

    def test_create_valid(self, sample_ontology):
        """Test creating valid OntologyConfig."""
        assert sample_ontology.version == "1.0-test"
        assert "cost" in sample_ontology.aspects

    def test_get_allowed_labels(self, sample_ontology):
        """Test get_allowed_labels method."""
        labels = sample_ontology.get_allowed_labels("cost")
        assert "cheap" in labels
        assert "expensive" in labels

    def test_validate_aspect(self, sample_ontology):
        """Test validate_aspect method."""
        assert sample_ontology.validate_aspect("cost") is True
        assert sample_ontology.validate_aspect("nonexistent") is False

    def test_validate_label(self, sample_ontology):
        """Test validate_label method."""
        assert sample_ontology.validate_label("cost", "cheap") is True
        assert sample_ontology.validate_label("cost", "invalid") is False


@pytest.mark.unit
class TestPersonaWeights:
    """Tests for PersonaWeights model."""

    def test_create_default(self):
        """Test creating PersonaWeights with defaults."""
        weights = PersonaWeights()
        assert weights.review_cost_score == 0.0
        assert weights.total_weight() == 0.0

    def test_create_with_values(self):
        """Test creating PersonaWeights with values."""
        weights = PersonaWeights(
            review_cost_score=0.30,
            review_hassle_score=0.25,
            review_review_score=0.45,
        )
        assert weights.total_weight() == 1.0

    def test_negative_weight_invalid(self):
        """Test that negative weights are invalid."""
        with pytest.raises(ValidationError):
            PersonaWeights(review_cost_score=-0.1)


@pytest.mark.unit
class TestMissingBehavior:
    """Tests for MissingBehavior enum."""

    def test_values(self):
        """Test enum values."""
        assert MissingBehavior.NEUTRAL.value == "neutral"
        assert MissingBehavior.NEGATIVE.value == "negative"
        assert MissingBehavior.POSITIVE.value == "positive"
        assert MissingBehavior.EXCLUDE.value == "exclude"


@pytest.mark.unit
class TestPersonasConfig:
    """Tests for PersonasConfig model."""

    def test_create_valid(self, sample_personas):
        """Test creating valid PersonasConfig."""
        assert sample_personas.version == "1.0-test"
        assert "test_ifr" in sample_personas.personas
        assert "test_vfr" in sample_personas.personas


@pytest.mark.unit
class TestAirportFeatureScores:
    """Tests for AirportFeatureScores model."""

    def test_create_valid(self, sample_feature_scores):
        """Test creating valid feature scores."""
        assert sample_feature_scores.icao == "EGKB"
        assert sample_feature_scores.review_cost_score == 0.65

    def test_score_validation(self):
        """Test score must be in [0, 1]."""
        with pytest.raises(ValidationError):
            AirportFeatureScores(icao="EGKB", review_cost_score=1.5)

    def test_allow_none(self):
        """Test None values are allowed."""
        scores = AirportFeatureScores(icao="EGKB", review_cost_score=None)
        assert scores.review_cost_score is None


@pytest.mark.unit
class TestAirportStats:
    """Tests for AirportStats model."""

    def test_create_valid(self, sample_airport_stats):
        """Test creating valid AirportStats."""
        assert sample_airport_stats.icao == "EGKB"
        assert sample_airport_stats.rating_avg == 4.25
        assert sample_airport_stats.fee_band_0_749kg == 15.0

    def test_boolean_flags(self, sample_airport_stats):
        """Test AIP availability flags."""
        assert sample_airport_stats.aip_ifr_available == 3  # RNAV
        assert sample_airport_stats.aip_night_available == 0


@pytest.mark.unit
class TestNotificationRule:
    """Tests for NotificationRule model."""

    def test_create_minimal(self):
        """Test creating minimal NotificationRule."""
        rule = NotificationRule(rule_type="ppr", notification_type="hours")
        assert rule.rule_type == "ppr"
        assert rule.is_obligatory is True

    def test_create_full(self):
        """Test creating NotificationRule with all fields."""
        rule = NotificationRule(
            rule_type="ppr",
            weekday_start=0,
            weekday_end=4,
            notification_hours=24,
            notification_type="hours",
            is_obligatory=True,
            confidence=0.95,
        )
        assert rule.weekday_start == 0
        assert rule.weekday_end == 4


@pytest.mark.unit
class TestRuleSummary:
    """Tests for RuleSummary model."""

    def test_create_valid(self):
        """Test creating valid RuleSummary."""
        summary = RuleSummary(
            notification_summary="24h weekdays, 48h weekends",
            hassle_level="moderate",
            notification_score=0.6,
        )
        assert summary.hassle_level == "moderate"
        assert summary.notification_score == 0.6


@pytest.mark.unit
class TestBuildMetrics:
    """Tests for BuildMetrics model."""

    def test_create_default(self):
        """Test creating BuildMetrics with defaults."""
        metrics = BuildMetrics()
        assert metrics.total_airports == 0
        assert metrics.llm_calls == 0
        assert metrics.errors == []


@pytest.mark.unit
class TestFailureMode:
    """Tests for FailureMode enum."""

    def test_values(self):
        """Test enum values."""
        assert FailureMode.CONTINUE.value == "continue"
        assert FailureMode.FAIL_FAST.value == "fail_fast"
        assert FailureMode.SKIP.value == "skip"

