"""
GA Friendliness Library

A library for computing GA (General Aviation) friendliness scores for airports
based on reviews, fees, and operational characteristics.

Main components:
    - Models: Pydantic models for data structures
    - Config: Configuration loading and validation
    - Storage: Database operations for ga_meta.sqlite
    - Ontology: Aspect/label ontology management
    - Personas: Persona-based scoring

Example usage:
    from shared.ga_friendliness import (
        GAFriendlinessSettings,
        GAMetaStorage,
        OntologyManager,
        PersonaManager,
        get_settings,
        get_default_ontology,
        get_default_personas,
    )
    
    # Load settings
    settings = get_settings()
    
    # Initialize storage
    storage = GAMetaStorage(settings.ga_meta_db_path)
    
    # Load ontology and personas
    ontology = OntologyManager(get_default_ontology())
    personas = PersonaManager(get_default_personas())
"""

# --- Exceptions ---
from .exceptions import (
    AIPRuleParsingError,
    BuildError,
    CacheError,
    ConfigurationError,
    FeatureMappingError,
    GAFriendlinessError,
    OntologyValidationError,
    PersonaValidationError,
    ReviewExtractionError,
    StorageError,
)

# --- Models ---
from .models import (
    # Raw input
    RawReview,
    # Extraction
    AspectLabel,
    ReviewExtraction,
    # Ontology
    OntologyConfig,
    # Personas
    PersonaWeights,
    MissingBehavior,
    PersonaMissingBehaviors,
    PersonaConfig,
    PersonasConfig,
    # Aggregation
    AggregationContext,
    # Features
    AirportFeatureScores,
    AirportStats,
    # AIP rules
    NotificationRule,
    ParsedAIPRules,
    RuleSummary,
    # Feature mappings
    FeatureMappingsConfig,
    ReviewFeatureDefinition,
    AIPFeatureDefinition,
    AspectConfig,
    # Build
    FailureMode,
    BuildMetrics,
    BuildResult,
)

# --- Configuration ---
from .config import (
    GAFriendlinessSettings,
    get_settings,
    load_ontology,
    load_personas,
    get_default_ontology,
    get_default_personas,
)

# --- Database ---
from .database import (
    SCHEMA_VERSION,
    get_connection,
    create_schema,
    ensure_schema_version,
    attach_euro_aip,
)

# --- Storage ---
from .storage import (
    GAMetaStorage,
    parse_timestamp,
)

# --- Interfaces ---
from .interfaces import (
    ReviewSource,
    AIPDataSource,
    StorageInterface,
    ReviewExtractorInterface,
    RuleParserInterface,
    RuleSummarizerInterface,
    SummaryGeneratorInterface,
)

# --- Ontology ---
from .ontology import OntologyManager

# --- Personas ---
from .personas import (
    PersonaManager,
    FEATURE_NAMES,
)

# --- UI Config ---
from .ui_config import (
    FEATURE_DISPLAY_NAMES,
    FEATURE_DESCRIPTIONS,
    RELEVANCE_BUCKETS,
    get_ui_config,
    validate_config_consistency,
)

# --- Cache ---
from .cache import CachedDataLoader

# --- Sources ---
from .sources import (
    CSVReviewSource,
    AirfieldDirectorySource,
    AirportJsonDirectorySource,
    CompositeReviewSource,
    AirportsDatabaseSource,
)

# --- Features ---
from .features import (
    FeatureMapper,
    AIRCRAFT_MTOW_MAP,
    get_mtow_for_aircraft,
    get_fee_band_for_mtow,
    aggregate_fees_by_band,
    apply_bayesian_smoothing,
)

# --- Builder ---
from .builder import GAFriendlinessBuilder

__all__ = [
    # Exceptions
    "GAFriendlinessError",
    "OntologyValidationError",
    "PersonaValidationError",
    "ReviewExtractionError",
    "StorageError",
    "FeatureMappingError",
    "BuildError",
    "AIPRuleParsingError",
    "ConfigurationError",
    "CacheError",
    # Models
    "RawReview",
    "AspectLabel",
    "ReviewExtraction",
    "OntologyConfig",
    "PersonaWeights",
    "MissingBehavior",
    "PersonaMissingBehaviors",
    "PersonaConfig",
    "PersonasConfig",
    "AggregationContext",
    "AirportFeatureScores",
    "AirportStats",
    "NotificationRule",
    "ParsedAIPRules",
    "RuleSummary",
    "FeatureMappingsConfig",
    "ReviewFeatureDefinition",
    "AIPFeatureDefinition",
    "AspectConfig",
    "FailureMode",
    "BuildMetrics",
    "BuildResult",
    # Configuration
    "GAFriendlinessSettings",
    "get_settings",
    "load_ontology",
    "load_personas",
    "get_default_ontology",
    "get_default_personas",
    # Database
    "SCHEMA_VERSION",
    "get_connection",
    "create_schema",
    "ensure_schema_version",
    "attach_euro_aip",
    # Storage
    "GAMetaStorage",
    "parse_timestamp",
    # Interfaces
    "ReviewSource",
    "AIPDataSource",
    "StorageInterface",
    "ReviewExtractorInterface",
    "RuleParserInterface",
    "RuleSummarizerInterface",
    "SummaryGeneratorInterface",
    # Ontology
    "OntologyManager",
    # Personas
    "PersonaManager",
    "FEATURE_NAMES",
    # UI Config
    "FEATURE_DISPLAY_NAMES",
    "FEATURE_DESCRIPTIONS",
    "RELEVANCE_BUCKETS",
    "get_ui_config",
    "validate_config_consistency",
    # Cache
    "CachedDataLoader",
    # Sources
    "CSVReviewSource",
    "AirfieldDirectorySource",
    "AirportJsonDirectorySource",
    "CompositeReviewSource",
    "AirportsDatabaseSource",
    # Features
    "FeatureMapper",
    "AIRCRAFT_MTOW_MAP",
    "get_mtow_for_aircraft",
    "get_fee_band_for_mtow",
    "aggregate_fees_by_band",
    "apply_bayesian_smoothing",
    # Builder
    "GAFriendlinessBuilder",
]

