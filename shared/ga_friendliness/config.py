"""
Configuration loading and validation for ga_friendliness library.

Supports loading from JSON files and environment variables.
Uses Pydantic BaseSettings for configuration management.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from .exceptions import ConfigurationError, OntologyValidationError, PersonaValidationError
from .models import OntologyConfig, PersonasConfig


class GAFriendlinessSettings(BaseSettings):
    """Settings for GA friendliness processing.
    
    Can be loaded from environment variables with GA_FRIENDLINESS_ prefix,
    or set directly in code.
    """

    # Paths
    euro_aip_db_path: Optional[Path] = Field(
        default=None, description="Path to euro_aip.sqlite"
    )
    ga_meta_db_path: Path = Field(
        default=Path("ga_meta.sqlite"), description="Path to ga_meta.sqlite (output)"
    )
    ontology_json_path: Optional[Path] = Field(
        default=None, description="Path to ontology.json"
    )
    personas_json_path: Optional[Path] = Field(
        default=None, description="Path to personas.json"
    )
    cache_dir: Path = Field(
        default=Path("cache/ga_friendliness"), description="Cache directory"
    )

    # LLM settings
    llm_model: str = Field(default="gpt-4o-mini", description="LLM model name")
    llm_temperature: float = Field(
        default=0.0, ge=0.0, le=2.0, description="LLM temperature"
    )
    llm_api_key: Optional[str] = Field(
        default=None, description="LLM API key (from env or explicit)"
    )
    use_mock_llm: bool = Field(
        default=False, description="Use mock LLM for testing (ignores API key)"
    )
    llm_max_retries: int = Field(default=3, ge=1, description="Max LLM retry attempts")

    # Processing settings
    confidence_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Min confidence for tag inclusion"
    )
    batch_size: int = Field(default=50, ge=1, description="Reviews per LLM batch")

    # Time decay settings (disabled by default)
    enable_time_decay: bool = Field(
        default=False, description="Apply time decay to review weights"
    )
    time_decay_half_life_days: float = Field(
        default=365.0, gt=0, description="Half-life for exponential decay"
    )
    time_decay_reference_time: Optional[datetime] = Field(
        default=None, description="Reference time (None = use build time)"
    )

    # Bayesian smoothing settings (disabled by default)
    enable_bayesian_smoothing: bool = Field(
        default=False, description="Apply Bayesian smoothing to feature scores"
    )
    bayesian_smoothing_strength: float = Field(
        default=10.0, ge=0, description="k parameter (higher = more smoothing)"
    )
    compute_global_priors: bool = Field(
        default=True, description="Compute priors from all airports"
    )
    global_priors: Optional[Dict[str, float]] = Field(
        default=None, description="Fixed priors if compute_global_priors=False"
    )

    # Versioning
    source_version: str = Field(
        default="unknown", description='Source version (e.g., "airfield.directory-2025-11-01")'
    )
    scoring_version: str = Field(default="ga_scores_v1", description="Scoring version")

    # Failure handling
    failure_mode: str = Field(
        default="continue",
        description="How to handle failures: 'continue', 'fail_fast', 'skip'",
    )

    model_config = {
        "env_prefix": "GA_FRIENDLINESS_",
        "env_file": ".env",
        "extra": "ignore",
    }

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def get_api_key_from_env(cls, v: Optional[str]) -> Optional[str]:
        """Fall back to OPENAI_API_KEY if not set."""
        if v is None:
            return os.getenv("OPENAI_API_KEY")
        return v


def load_json_file(path: Path, description: str = "JSON file") -> Dict[str, Any]:
    """
    Load and parse a JSON file.
    
    Args:
        path: Path to JSON file
        description: Description for error messages
        
    Returns:
        Parsed JSON as dict
        
    Raises:
        ConfigurationError: If file doesn't exist or JSON is malformed
    """
    if not path.exists():
        raise ConfigurationError(f"{description} not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in {description} ({path}): {e}")
    except Exception as e:
        raise ConfigurationError(f"Error reading {description} ({path}): {e}")


def load_ontology(path: Path) -> OntologyConfig:
    """
    Load and validate ontology.json.
    
    Args:
        path: Path to ontology.json
        
    Returns:
        Validated OntologyConfig
        
    Raises:
        OntologyValidationError: If JSON is malformed or structure invalid
    """
    try:
        data = load_json_file(path, "ontology.json")
    except ConfigurationError as e:
        raise OntologyValidationError(str(e))

    try:
        config = OntologyConfig(**data)
    except Exception as e:
        raise OntologyValidationError(f"Invalid ontology structure: {e}")

    # Validate aspects have at least one label
    for aspect, labels in config.aspects.items():
        if not labels:
            raise OntologyValidationError(
                f"Aspect '{aspect}' has no labels defined"
            )

    return config


def load_personas(path: Path) -> PersonasConfig:
    """
    Load and validate personas.json.
    
    Args:
        path: Path to personas.json
        
    Returns:
        Validated PersonasConfig
        
    Raises:
        PersonaValidationError: If JSON is malformed or weights don't sum reasonably
    """
    try:
        data = load_json_file(path, "personas.json")
    except ConfigurationError as e:
        raise PersonaValidationError(str(e))

    try:
        config = PersonasConfig(**data)
    except Exception as e:
        raise PersonaValidationError(f"Invalid personas structure: {e}")

    # Valid feature names (all possible feature scores)
    valid_feature_names = {
        "review_cost_score",
        "review_hassle_score",
        "review_review_score",
        "review_ops_ifr_score",
        "review_ops_vfr_score",
        "review_access_score",
        "review_fun_score",
        "review_hospitality_score",
        "aip_ops_ifr_score",
        "aip_hospitality_score",
    }

    # Validate each persona
    for persona_id, persona in config.personas.items():
        # Get all weights from persona
        weights_dict = persona.weights.model_dump()

        # Check that all weights are non-negative
        for feature_name, weight in weights_dict.items():
            if weight < 0:
                raise PersonaValidationError(
                    f"Persona '{persona_id}' has negative weight for '{feature_name}': {weight}"
                )

            # Check that feature name is valid
            if weight > 0 and feature_name not in valid_feature_names:
                raise PersonaValidationError(
                    f"Persona '{persona_id}' references unknown feature: '{feature_name}'. "
                    f"Valid features: {', '.join(sorted(valid_feature_names))}"
                )

        # Check that weights sum to approximately 1.0 (tolerance: 0.05)
        total_weight = persona.weights.total_weight()
        if total_weight <= 0:
            raise PersonaValidationError(
                f"Persona '{persona_id}' has no positive weights"
            )

        if abs(total_weight - 1.0) > 0.05:
            raise PersonaValidationError(
                f"Persona '{persona_id}' weights sum to {total_weight:.3f}, "
                f"expected approximately 1.0 (±0.05)"
            )

    return config


def get_settings(**overrides: Any) -> GAFriendlinessSettings:
    """
    Load settings from environment variables and defaults.
    
    Environment variables (prefixed with GA_FRIENDLINESS_):
        GA_FRIENDLINESS_EURO_AIP_DB_PATH
        GA_FRIENDLINESS_GA_META_DB_PATH
        GA_FRIENDLINESS_ONTOLOGY_JSON_PATH
        GA_FRIENDLINESS_PERSONAS_JSON_PATH
        GA_FRIENDLINESS_LLM_MODEL
        OPENAI_API_KEY (or GA_FRIENDLINESS_LLM_API_KEY)
        
    Args:
        **overrides: Override specific settings
        
    Returns:
        GAFriendlinessSettings instance
    """
    return GAFriendlinessSettings(**overrides)


# --- Default ontology and personas (inline fallbacks) ---

DEFAULT_ONTOLOGY: Dict[str, Any] = {
    "version": "1.0",
    "aspects": {
        "cost": ["cheap", "reasonable", "expensive", "unclear"],
        "staff": ["very_positive", "positive", "neutral", "negative", "very_negative"],
        "bureaucracy": ["simple", "moderate", "complex"],
        "fuel": ["excellent", "ok", "poor", "unavailable"],
        "runway": ["excellent", "ok", "poor"],
        "transport": ["excellent", "good", "ok", "poor", "none"],
        "food": ["excellent", "good", "ok", "poor", "none"],
        "restaurant": ["on_site", "walking", "nearby", "available", "none"],
        "accommodation": ["on_site", "walking", "nearby", "available", "none"],
        "noise_neighbours": ["not_an_issue", "minor_concern", "significant_issue"],
        "training_traffic": ["busy", "moderate", "quiet", "none"],
        "overall_experience": [
            "very_positive",
            "positive",
            "neutral",
            "negative",
            "very_negative",
        ],
        # IFR/VFR operations aspects (for ops_ifr_score and ops_vfr_score)
        "ifr": ["excellent", "good", "ok", "poor", "unavailable"],
        "procedure": ["well_documented", "standard", "complex", "unclear"],
        "approach": ["excellent", "good", "ok", "poor"],
        "vfr": ["excellent", "good", "ok", "poor", "restricted"],
    },
}


DEFAULT_PERSONAS: Dict[str, Any] = {
    "version": "1.0",
    "personas": {
        "ifr_touring_sr22": {
            "id": "ifr_touring_sr22",
            "label": "IFR touring (SR22)",
            "description": "IFR touring mission: prefers solid IFR capability, reasonable fees, low bureaucracy",
            "weights": {
                "aip_ops_ifr_score": 0.25,
                "review_hassle_score": 0.20,
                "review_cost_score": 0.20,
                "review_review_score": 0.15,
                "review_access_score": 0.10,
                "review_fun_score": 0.05,
                "review_hospitality_score": 0.05,
            },
        },
        "vfr_budget": {
            "id": "vfr_budget",
            "label": "VFR budget flyer",
            "description": "VFR pilot focused on low cost and easy access",
            "weights": {
                "review_cost_score": 0.35,
                "review_hassle_score": 0.25,
                "review_ops_vfr_score": 0.20,
                "review_review_score": 0.10,
                "review_access_score": 0.10,
            },
        },
        "lunch_stop": {
            "id": "lunch_stop",
            "label": "Lunch stop",
            "description": "Looking for a nice lunch destination with good restaurant",
            "weights": {
                "review_hospitality_score": 0.25,
                "aip_hospitality_score": 0.10,
                "review_fun_score": 0.25,
                "review_cost_score": 0.15,
                "review_hassle_score": 0.15,
                "review_review_score": 0.10,
            },
            "missing_behaviors": {
                "review_hospitality_score": "negative",  # Required for lunch stops
                "aip_hospitality_score": "negative",  # Required for lunch stops
            },
        },
        "training": {
            "id": "training",
            "label": "Training flight",
            "description": "Training flight focus on ops and low cost",
            "weights": {
                "review_ops_vfr_score": 0.30,
                "review_cost_score": 0.30,
                "review_hassle_score": 0.20,
                "review_review_score": 0.20,
            },
        },
    },
}


def get_default_ontology() -> OntologyConfig:
    """Get the default built-in ontology."""
    return OntologyConfig(**DEFAULT_ONTOLOGY)


def get_default_personas() -> PersonasConfig:
    """Get the default built-in personas."""
    return PersonasConfig(**DEFAULT_PERSONAS)

