"""
Pydantic models for ga_friendliness library.

All data structures used throughout the library are defined here for consistency
and validation. Models use Pydantic for automatic validation and serialization.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, field_validator


# --- Raw Input Models ---


class RawReview(BaseModel):
    """
    Raw review from any source (airfield.directory, CSV, etc.).
    
    Used as input to the NLP extraction pipeline.
    """

    icao: str = Field(..., description="Airport ICAO code")
    review_text: str = Field(..., description="Raw review text content")
    review_id: Optional[str] = Field(
        default=None, description="Unique ID within source"
    )
    rating: Optional[float] = Field(
        default=None, description="Source rating (e.g., 1-5)"
    )
    timestamp: Optional[str] = Field(
        default=None, description="ISO format UTC timestamp"
    )
    language: Optional[str] = Field(
        default=None, description='Language code (e.g., "EN", "DE")'
    )
    ai_generated: Optional[bool] = Field(
        default=None, description="If source indicates AI-generated"
    )
    source: str = Field(
        default="unknown",
        description='Source identifier (e.g., "airfield.directory", "csv")',
    )


# --- Extraction Models ---


class AspectLabel(BaseModel):
    """Single label for an aspect (e.g., 'cost': 'expensive')."""

    aspect: str = Field(..., description="Aspect name from ontology")
    label: str = Field(..., description="Label value for the aspect")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0"
    )


class ReviewExtraction(BaseModel):
    """Structured extraction from a single review."""

    review_id: Optional[str] = Field(default=None, description="Source review ID")
    aspects: List[AspectLabel] = Field(
        default_factory=list, description="Extracted aspect-label pairs"
    )
    raw_text_excerpt: Optional[str] = Field(
        default=None, description="Text excerpt for transparency/debugging"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO format timestamp from source review (for time decay)",
    )


# --- Ontology Configuration ---


class OntologyConfig(BaseModel):
    """Loaded ontology.json structure."""

    version: str = Field(..., description="Ontology version string")
    aspects: Dict[str, List[str]] = Field(
        ..., description="Mapping of aspect_name -> [allowed_labels]"
    )

    def get_allowed_labels(self, aspect: str) -> List[str]:
        """Get allowed labels for an aspect."""
        return self.aspects.get(aspect, [])

    def validate_aspect(self, aspect: str) -> bool:
        """Check if aspect exists in ontology."""
        return aspect in self.aspects

    def validate_label(self, aspect: str, label: str) -> bool:
        """Check if label is allowed for aspect."""
        return label in self.aspects.get(aspect, [])


# --- Persona Configuration ---


class PersonaWeights(BaseModel):
    """Weights for a single persona's feature scores."""

    ga_cost_score: float = Field(default=0.0, ge=0.0)
    ga_review_score: float = Field(default=0.0, ge=0.0)
    ga_hassle_score: float = Field(default=0.0, ge=0.0)
    ga_ops_ifr_score: float = Field(default=0.0, ge=0.0)
    ga_ops_vfr_score: float = Field(default=0.0, ge=0.0)
    ga_access_score: float = Field(default=0.0, ge=0.0)
    ga_fun_score: float = Field(default=0.0, ge=0.0)
    ga_hospitality_score: float = Field(
        default=0.0,
        ge=0.0,
        description="Weight for availability/proximity of restaurant and accommodation",
    )

    def total_weight(self) -> float:
        """Calculate total weight across all features."""
        return (
            self.ga_cost_score
            + self.ga_review_score
            + self.ga_hassle_score
            + self.ga_ops_ifr_score
            + self.ga_ops_vfr_score
            + self.ga_access_score
            + self.ga_fun_score
            + self.ga_hospitality_score
        )


class MissingBehavior(str, Enum):
    """
    How to handle missing (NULL) feature values when computing persona scores.
    
    Different personas have different tolerance for missing data:
        - IFR touring persona: missing IFR score is bad (assume no IFR capability)
        - Training persona: missing hospitality score is irrelevant (exclude)
        - Lunch stop persona: missing hospitality is bad (can't recommend)
    """

    NEUTRAL = "neutral"  # Treat missing as 0.5 (neutral/average)
    NEGATIVE = "negative"  # Treat missing as 0.0 (worst case, feature is required)
    POSITIVE = "positive"  # Treat missing as 1.0 (best case, rare use)
    EXCLUDE = "exclude"  # Exclude from scoring, re-normalize remaining weights


class PersonaMissingBehaviors(BaseModel):
    """Per-feature missing value behavior for a persona."""

    ga_cost_score: MissingBehavior = Field(default=MissingBehavior.NEUTRAL)
    ga_review_score: MissingBehavior = Field(default=MissingBehavior.NEUTRAL)
    ga_hassle_score: MissingBehavior = Field(default=MissingBehavior.NEUTRAL)
    ga_ops_ifr_score: MissingBehavior = Field(default=MissingBehavior.NEUTRAL)
    ga_ops_vfr_score: MissingBehavior = Field(default=MissingBehavior.NEUTRAL)
    ga_access_score: MissingBehavior = Field(default=MissingBehavior.NEUTRAL)
    ga_fun_score: MissingBehavior = Field(default=MissingBehavior.NEUTRAL)
    ga_hospitality_score: MissingBehavior = Field(
        default=MissingBehavior.EXCLUDE,
        description="Default: optional feature",
    )


class PersonaConfig(BaseModel):
    """Single persona definition."""

    id: str = Field(..., description="Unique persona identifier")
    label: str = Field(..., description="Human-readable label")
    description: str = Field(..., description="Description of persona use case")
    weights: PersonaWeights = Field(..., description="Feature weights for scoring")
    missing_behaviors: Optional[PersonaMissingBehaviors] = Field(
        default=None, description="How to handle missing features (default: all NEUTRAL)"
    )


class PersonasConfig(BaseModel):
    """Loaded personas.json structure."""

    version: str = Field(..., description="Personas config version string")
    personas: Dict[str, PersonaConfig] = Field(
        ..., description="Mapping of persona_id -> PersonaConfig"
    )


# --- Aggregation Context ---


class AggregationContext(BaseModel):
    """
    Context for aggregation (enables time decay and Bayesian smoothing extensions).
    
    All fields are optional to maintain backward compatibility.
    When None, extensions are disabled and behavior matches original implementation.
    """

    sample_count: int = Field(..., description="Number of reviews/tags contributing")
    reference_time: Optional[datetime] = Field(
        default=None,
        description="Reference time for time decay calculations (usually build time)",
    )
    global_priors: Optional[Dict[str, float]] = Field(
        default=None, description="Global average scores for Bayesian smoothing"
    )


# --- Feature Scores ---


class AirportFeatureScores(BaseModel):
    """Normalized feature scores for an airport."""

    icao: str = Field(..., description="Airport ICAO code")
    ga_cost_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_review_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_hassle_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_ops_ifr_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_ops_vfr_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_access_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_fun_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_hospitality_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Availability/proximity of restaurant and accommodation [0, 1]",
    )


# --- Airport Stats ---


class AirportStats(BaseModel):
    """Aggregated stats for ga_airfield_stats table."""

    icao: str = Field(..., description="Airport ICAO code")
    rating_avg: Optional[float] = Field(default=None, description="Average rating")
    rating_count: int = Field(default=0, description="Number of ratings")
    last_review_utc: Optional[str] = Field(
        default=None, description="Timestamp of latest review"
    )

    # Fee bands by MTOW
    fee_band_0_749kg: Optional[float] = Field(default=None, description="0-749 kg MTOW")
    fee_band_750_1199kg: Optional[float] = Field(
        default=None, description="750-1199 kg MTOW"
    )
    fee_band_1200_1499kg: Optional[float] = Field(
        default=None, description="1200-1499 kg MTOW"
    )
    fee_band_1500_1999kg: Optional[float] = Field(
        default=None, description="1500-1999 kg MTOW"
    )
    fee_band_2000_3999kg: Optional[float] = Field(
        default=None, description="2000-3999 kg MTOW"
    )
    fee_band_4000_plus_kg: Optional[float] = Field(
        default=None, description="4000+ kg MTOW"
    )
    fee_currency: Optional[str] = Field(default=None, description="Currency code")

    # Binary flags and IFR capabilities
    mandatory_handling: bool = Field(default=False)
    ifr_procedure_available: bool = Field(
        default=False,
        description="True if airport has instrument approach procedures (ILS, RNAV, VOR, etc.)",
    )
    ifr_score: int = Field(
        default=0,
        ge=0,
        le=4,
        description="IFR capability score: 0=no IFR, 1=IFR permitted, 2=basic (VOR/NDB), 3=RNP, 4=ILS",
    )
    night_available: bool = Field(default=False)
    
    # AIP metadata (from airports.db)
    hotel_info: Optional[str] = Field(
        default=None, description="Hotel availability info from AIP"
    )
    restaurant_info: Optional[str] = Field(
        default=None, description="Restaurant availability info from AIP"
    )

    # Feature scores (all normalized [0, 1])
    ga_cost_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_review_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_hassle_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_ops_ifr_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_ops_vfr_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_access_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_fun_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ga_hospitality_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Availability/proximity of restaurant and accommodation",
    )
    notification_hassle_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="From AIP notification rules (optional)",
    )

    # Versioning
    source_version: str = Field(..., description="Source snapshot identifier")
    scoring_version: str = Field(default="ga_scores_v1", description="Scoring version")


# --- AIP Rule Models ---


class NotificationRule(BaseModel):
    """Structured representation of a notification requirement."""

    rule_type: str = Field(
        ..., description="Type: 'ppr', 'pn', 'customs_notification', 'handling_ppr'"
    )
    weekday_start: Optional[int] = Field(
        default=None, ge=0, le=6, description="0=Monday, 6=Sunday"
    )
    weekday_end: Optional[int] = Field(
        default=None, ge=0, le=6, description="End of range (inclusive)"
    )
    notification_hours: Optional[int] = Field(
        default=None, description="Hours before flight (24, 48, etc.)"
    )
    notification_type: str = Field(
        ...,
        description="Type: 'hours', 'business_day', 'specific_time', 'on_request', 'h24'",
    )
    specific_time: Optional[str] = Field(
        default=None, description='e.g., "1300" for "before 1300"'
    )
    business_day_offset: Optional[int] = Field(
        default=None, description='e.g., -1 for "last business day"'
    )
    is_obligatory: bool = Field(default=True, description="Whether mandatory")
    conditions: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional conditions (holidays, seasons, etc.)"
    )

    # Source tracking fields
    source_field: Optional[str] = Field(
        default=None, description="Which AIP field this came from"
    )
    source_section: Optional[str] = Field(
        default=None, description="Which AIP section (customs, handling, etc.)"
    )
    source_std_field_id: Optional[int] = Field(
        default=None, description="euro_aip std_field_id"
    )
    aip_entry_id: Optional[str] = Field(
        default=None, description="Reference to euro_aip entry"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="LLM extraction confidence"
    )


class ParsedAIPRules(BaseModel):
    """Complete parsed rules for an airport."""

    icao: str = Field(..., description="Airport ICAO code")
    notification_rules: List[NotificationRule] = Field(
        default_factory=list, description="Extracted notification rules"
    )
    handling_rules: List[Dict[str, Any]] = Field(
        default_factory=list, description="Future: handling-specific rules"
    )
    source_fields: Dict[str, str] = Field(
        default_factory=dict, description="Map rule -> source field text"
    )


class RuleSummary(BaseModel):
    """High-level summary of notification requirements."""

    notification_summary: str = Field(
        ..., description='Human-readable: "24h weekdays, 48h weekends"'
    )
    hassle_level: str = Field(
        ..., description="'low', 'moderate', 'high', 'very_high'"
    )
    notification_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized score [0, 1] where 1.0 = low hassle, 0.0 = high hassle",
    )


# --- Feature Mapping Configuration ---


class FeatureMappingConfig(BaseModel):
    """Configuration for mapping aspect labels to a feature score."""

    aspect: str = Field(..., description="Aspect name from ontology")
    label_scores: Dict[str, float] = Field(
        ..., description="Mapping of label -> score [0, 1]"
    )
    default_score: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Score when no labels match"
    )


class FeatureMappingsConfig(BaseModel):
    """All feature mapping configurations."""

    version: str = Field(..., description="Feature mappings version")
    mappings: Dict[str, FeatureMappingConfig] = Field(
        ..., description="Mapping of feature_name -> FeatureMappingConfig"
    )


# --- Build Results ---


class FailureMode(str, Enum):
    """How to handle failures during build."""

    CONTINUE = "continue"  # Log and continue with next airport
    FAIL_FAST = "fail_fast"  # Stop immediately on first error
    SKIP = "skip"  # Skip failed airports silently


class BuildMetrics(BaseModel):
    """Metrics collected during build process."""

    total_airports: int = Field(default=0, description="Total airports processed")
    successful_airports: int = Field(default=0, description="Successfully processed")
    failed_airports: int = Field(default=0, description="Failed to process")
    skipped_airports: int = Field(
        default=0, description="Skipped (no changes or filtered)"
    )
    total_reviews: int = Field(default=0, description="Total reviews processed")
    total_extractions: int = Field(default=0, description="Total tag extractions")

    # LLM metrics
    llm_calls: int = Field(default=0, description="Number of LLM API calls")
    llm_tokens_input: int = Field(default=0, description="Total input tokens")
    llm_tokens_output: int = Field(default=0, description="Total output tokens")
    llm_cost_usd: float = Field(default=0.0, description="Estimated LLM cost in USD")

    # Timing
    start_time: Optional[datetime] = Field(default=None)
    end_time: Optional[datetime] = Field(default=None)
    duration_seconds: Optional[float] = Field(default=None)

    # Errors
    errors: List[str] = Field(default_factory=list, description="Error messages")


class BuildResult(BaseModel):
    """Result of a build operation."""

    success: bool = Field(..., description="Whether build completed successfully")
    metrics: BuildMetrics = Field(..., description="Build metrics")
    output_db_path: Optional[str] = Field(
        default=None, description="Path to output database"
    )
    last_successful_icao: Optional[str] = Field(
        default=None, description="Last successfully processed ICAO (for resume)"
    )

