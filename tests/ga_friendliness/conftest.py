"""
Pytest fixtures for ga_friendliness tests.
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from shared.ga_friendliness import (
    OntologyConfig,
    PersonasConfig,
    PersonaConfig,
    PersonaWeights,
    GAMetaStorage,
    RawReview,
    AspectLabel,
    ReviewExtraction,
    AirportFeatureScores,
    AirportStats,
)


# --- Sample Data ---

SAMPLE_ONTOLOGY: Dict[str, Any] = {
    "version": "1.0-test",
    "aspects": {
        "cost": ["cheap", "reasonable", "expensive", "unclear"],
        "staff": ["very_positive", "positive", "neutral", "negative", "very_negative"],
        "bureaucracy": ["simple", "moderate", "complex"],
        "fuel": ["excellent", "ok", "poor", "unavailable"],
        "restaurant": ["on_site", "walking", "nearby", "available", "none"],
        "accommodation": ["on_site", "walking", "nearby", "available", "none"],
        "overall_experience": [
            "very_positive",
            "positive",
            "neutral",
            "negative",
            "very_negative",
        ],
    },
}

SAMPLE_PERSONAS: Dict[str, Any] = {
    "version": "1.0-test",
    "personas": {
        "test_ifr": {
            "id": "test_ifr",
            "label": "Test IFR Persona",
            "description": "Test persona for IFR touring",
            "weights": {
                "review_ops_ifr_score": 0.20,
                "aip_ops_ifr_score": 0.10,
                "review_hassle_score": 0.25,
                "review_cost_score": 0.20,
                "review_review_score": 0.15,
                "review_access_score": 0.10,
            },
        },
        "test_vfr": {
            "id": "test_vfr",
            "label": "Test VFR Persona",
            "description": "Test persona for VFR budget flying",
            "weights": {
                "review_cost_score": 0.40,
                "review_hassle_score": 0.30,
                "review_ops_vfr_score": 0.20,
                "review_review_score": 0.10,
            },
        },
        "test_lunch": {
            "id": "test_lunch",
            "label": "Test Lunch Stop Persona",
            "description": "Test persona for lunch stops",
            "weights": {
                "review_hospitality_score": 0.30,
                "aip_hospitality_score": 0.10,
                "review_fun_score": 0.30,
                "review_cost_score": 0.15,
                "review_hassle_score": 0.15,
            },
            "missing_behaviors": {
                "review_hospitality_score": "negative",  # Required for lunch stops
                "aip_hospitality_score": "negative",
            },
        },
    },
}

SAMPLE_REVIEWS = [
    {
        "icao": "EGKB",
        "review_text": "Great little airfield, very friendly staff. Fuel prices are reasonable. Easy to fly in VFR.",
        "review_id": "review_001",
        "rating": 4.5,
        "timestamp": "2024-06-15T10:30:00Z",
        "source": "airfield.directory",
    },
    {
        "icao": "EGKB",
        "review_text": "Landing fees are a bit expensive but worth it for the location. Restaurant on site is excellent.",
        "review_id": "review_002",
        "rating": 4.0,
        "timestamp": "2024-05-20T14:00:00Z",
        "source": "airfield.directory",
    },
    {
        "icao": "LFAT",
        "review_text": "Cheap fees, simple paperwork. No fuel available though.",
        "review_id": "review_003",
        "rating": 3.5,
        "timestamp": "2024-04-10T09:15:00Z",
        "source": "airfield.directory",
    },
]


# --- Fixtures ---


@pytest.fixture
def sample_ontology_dict() -> Dict[str, Any]:
    """Return sample ontology dictionary."""
    return SAMPLE_ONTOLOGY.copy()


@pytest.fixture
def sample_ontology(sample_ontology_dict: Dict[str, Any]) -> OntologyConfig:
    """Return sample OntologyConfig."""
    return OntologyConfig(**sample_ontology_dict)


@pytest.fixture
def sample_personas_dict() -> Dict[str, Any]:
    """Return sample personas dictionary."""
    return SAMPLE_PERSONAS.copy()


@pytest.fixture
def sample_personas(sample_personas_dict: Dict[str, Any]) -> PersonasConfig:
    """Return sample PersonasConfig."""
    return PersonasConfig(**sample_personas_dict)


@pytest.fixture
def sample_reviews() -> list[RawReview]:
    """Return sample raw reviews."""
    return [RawReview(**r) for r in SAMPLE_REVIEWS]


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_db_path(temp_dir: Path) -> Path:
    """Return path to temporary database."""
    return temp_dir / "test_ga_persona.db"


@pytest.fixture
def temp_storage(temp_db_path: Path) -> GAMetaStorage:
    """Create a temporary storage instance."""
    storage = GAMetaStorage(temp_db_path)
    yield storage
    storage.close()


@pytest.fixture
def ontology_json_path(temp_dir: Path, sample_ontology_dict: Dict[str, Any]) -> Path:
    """Create temporary ontology.json file."""
    path = temp_dir / "ontology.json"
    with open(path, "w") as f:
        json.dump(sample_ontology_dict, f)
    return path


@pytest.fixture
def personas_json_path(temp_dir: Path, sample_personas_dict: Dict[str, Any]) -> Path:
    """Create temporary personas.json file."""
    path = temp_dir / "personas.json"
    with open(path, "w") as f:
        json.dump(sample_personas_dict, f)
    return path


@pytest.fixture
def sample_extraction() -> ReviewExtraction:
    """Return sample review extraction."""
    return ReviewExtraction(
        review_id="review_001",
        aspects=[
            AspectLabel(aspect="cost", label="reasonable", confidence=0.85),
            AspectLabel(aspect="staff", label="very_positive", confidence=0.92),
            AspectLabel(aspect="overall_experience", label="positive", confidence=0.88),
        ],
        raw_text_excerpt="Great little airfield...",
        timestamp="2024-06-15T10:30:00Z",
    )


@pytest.fixture
def sample_feature_scores() -> AirportFeatureScores:
    """Return sample airport feature scores."""
    return AirportFeatureScores(
        icao="EGKB",
        review_cost_score=0.65,
        review_hassle_score=0.75,
        review_review_score=0.80,
        review_ops_ifr_score=0.60,
        review_ops_vfr_score=0.85,
        review_access_score=0.70,
        review_fun_score=0.72,
        review_hospitality_score=0.78,
        aip_ops_ifr_score=0.75,
        aip_hospitality_score=0.66,
    )


@pytest.fixture
def sample_feature_scores_with_missing() -> AirportFeatureScores:
    """Return sample airport feature scores with some missing values."""
    return AirportFeatureScores(
        icao="LFAT",
        review_cost_score=0.80,
        review_hassle_score=0.90,
        review_review_score=0.65,
        review_ops_ifr_score=None,  # Missing
        review_ops_vfr_score=0.75,
        review_access_score=None,  # Missing
        review_fun_score=0.50,
        review_hospitality_score=None,  # Missing
        aip_ops_ifr_score=None,  # Missing
        aip_hospitality_score=None,  # Missing
    )


@pytest.fixture
def sample_airport_stats() -> AirportStats:
    """Return sample airport stats."""
    return AirportStats(
        icao="EGKB",
        rating_avg=4.25,
        rating_count=2,
        last_review_utc="2024-06-15T10:30:00Z",
        fee_band_0_749kg=15.0,
        fee_band_750_1199kg=20.0,
        fee_band_1200_1499kg=25.0,
        fee_band_1500_1999kg=35.0,
        fee_band_2000_3999kg=50.0,
        fee_band_4000_plus_kg=75.0,
        fee_currency="GBP",
        # AIP raw data
        aip_ifr_available=3,  # RNAV approaches
        aip_night_available=0,
        aip_hotel_info=1,  # Nearby
        aip_restaurant_info=2,  # At airport
        # Review-derived scores
        review_cost_score=0.65,
        review_review_score=0.80,
        review_hassle_score=0.75,
        review_ops_ifr_score=0.60,
        review_ops_vfr_score=0.85,
        review_access_score=0.70,
        review_fun_score=0.72,
        review_hospitality_score=0.78,
        # AIP-derived scores
        aip_ops_ifr_score=0.75,
        aip_hospitality_score=0.66,
        source_version="test-v1",
        scoring_version="ga_scores_v1",
    )


# --- Pytest markers ---


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "llm: Tests that require LLM (may incur costs)")
    config.addinivalue_line("markers", "slow: Tests that take longer to run")

