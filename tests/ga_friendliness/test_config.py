"""
Unit tests for ga_friendliness configuration.
"""

import json
from pathlib import Path

import pytest

from shared.ga_friendliness import (
    GAFriendlinessSettings,
    get_settings,
    load_ontology,
    load_personas,
    get_default_ontology,
    get_default_personas,
    OntologyValidationError,
    PersonaValidationError,
)


@pytest.mark.unit
class TestGAFriendlinessSettings:
    """Tests for GAFriendlinessSettings."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = get_settings()
        assert settings.llm_model == "gpt-4o-mini"
        assert settings.llm_temperature == 0.0
        assert settings.confidence_threshold == 0.5
        assert settings.batch_size == 50
        assert settings.enable_time_decay is False
        assert settings.enable_bayesian_smoothing is False

    def test_override_settings(self):
        """Test overriding settings."""
        settings = get_settings(
            llm_model="gpt-4o",
            confidence_threshold=0.7,
            batch_size=100,
        )
        assert settings.llm_model == "gpt-4o"
        assert settings.confidence_threshold == 0.7
        assert settings.batch_size == 100

    def test_path_settings(self, temp_dir):
        """Test path settings."""
        settings = get_settings(
            ga_meta_db_path=temp_dir / "test.sqlite",
            cache_dir=temp_dir / "cache",
        )
        assert settings.ga_meta_db_path == temp_dir / "test.sqlite"
        assert settings.cache_dir == temp_dir / "cache"


@pytest.mark.unit
class TestLoadOntology:
    """Tests for load_ontology function."""

    def test_load_valid_ontology(self, ontology_json_path):
        """Test loading valid ontology."""
        ontology = load_ontology(ontology_json_path)
        assert ontology.version == "1.0-test"
        assert "cost" in ontology.aspects

    def test_load_missing_file(self, temp_dir):
        """Test loading non-existent file."""
        with pytest.raises(OntologyValidationError, match="not found"):
            load_ontology(temp_dir / "nonexistent.json")

    def test_load_invalid_json(self, temp_dir):
        """Test loading invalid JSON."""
        path = temp_dir / "invalid.json"
        path.write_text("not valid json {")
        
        with pytest.raises(OntologyValidationError, match="Invalid JSON"):
            load_ontology(path)

    def test_load_empty_aspect(self, temp_dir):
        """Test loading ontology with empty aspect labels."""
        path = temp_dir / "empty_aspect.json"
        with open(path, "w") as f:
            json.dump({
                "version": "1.0",
                "aspects": {
                    "cost": [],  # Empty labels
                },
            }, f)
        
        with pytest.raises(OntologyValidationError, match="no labels"):
            load_ontology(path)


@pytest.mark.unit
class TestLoadPersonas:
    """Tests for load_personas function."""

    def test_load_valid_personas(self, personas_json_path):
        """Test loading valid personas."""
        personas = load_personas(personas_json_path)
        assert personas.version == "1.0-test"
        assert "test_ifr" in personas.personas

    def test_load_missing_file(self, temp_dir):
        """Test loading non-existent file."""
        with pytest.raises(PersonaValidationError, match="not found"):
            load_personas(temp_dir / "nonexistent.json")

    def test_load_invalid_json(self, temp_dir):
        """Test loading invalid JSON."""
        path = temp_dir / "invalid.json"
        path.write_text("not valid json {")
        
        with pytest.raises(PersonaValidationError, match="Invalid JSON"):
            load_personas(path)

    def test_load_zero_weight_persona(self, temp_dir):
        """Test loading persona with zero total weight."""
        path = temp_dir / "zero_weight.json"
        with open(path, "w") as f:
            json.dump({
                "version": "1.0",
                "personas": {
                    "zero_persona": {
                        "id": "zero_persona",
                        "label": "Zero Weight Persona",
                        "description": "Persona with no weights",
                        "weights": {},  # All defaults = 0
                    },
                },
            }, f)
        
        with pytest.raises(PersonaValidationError, match="no positive weights"):
            load_personas(path)


@pytest.mark.unit
class TestDefaultConfigs:
    """Tests for default ontology and personas."""

    def test_default_ontology(self):
        """Test default ontology is valid."""
        ontology = get_default_ontology()
        # Bump deliberately alongside DEFAULT_ONTOLOGY (1.2: 2db7aed)
        assert ontology.version == "1.2"
        for aspect in (
            "cost", "staff", "bureaucracy", "restaurant", "accommodation",
            "overall_experience",
            # added in 1.2
            "infrastructure", "customs",
        ):
            assert aspect in ontology.aspects, aspect
        # 1.2 made location-based labels available for amenities
        assert "on_site" in ontology.aspects["restaurant"]
        assert "on_site" in ontology.aspects["accommodation"]
        # every aspect has a non-empty, duplicate-free label list
        for aspect, labels in ontology.aspects.items():
            assert labels, aspect
            assert len(labels) == len(set(labels)), aspect

    def test_default_personas(self):
        """Test default personas are valid."""
        personas = get_default_personas()
        assert personas.version == "1.0"
        assert "ifr_touring_sr22" in personas.personas
        assert "vfr_budget" in personas.personas
        assert "lunch_stop" in personas.personas
        assert "training" in personas.personas

    def test_default_persona_weights(self):
        """Test default persona weights are valid."""
        personas = get_default_personas()
        
        for persona_id, persona in personas.personas.items():
            total = persona.weights.total_weight()
            # Weights should sum to approximately 1.0 (within floating point tolerance)
            assert 0.95 <= total <= 1.05, f"Persona {persona_id} weights sum to {total}"

