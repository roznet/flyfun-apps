#!/usr/bin/env python3
"""
Unit tests for answer comparison functionality.

Tests cover:
- AnswerComparer: embedding-based comparison
- RulesComparisonService: high-level API with LLM synthesis
- RulesManager tag/category methods
"""
import json
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import numpy as np
import pytest

from shared.aviation_agent.answer_comparer import (
    AnswerComparer,
    AnswerDifference,
    ComparisonResult,
    OutlierResult,
    cosine_similarity,
    create_answer_comparer,
)
from shared.aviation_agent.behavior_config import ComparisonConfig
from shared.rules_manager import RulesManager


@pytest.fixture
def sample_rules_json(tmp_path):
    """Create a sample rules.json file for testing."""
    rules_data = {
        "questions": [
            {
                "question_id": "test-q1",
                "question_text": "Is a flight plan required for VFR flights?",
                "category": "VFR",
                "tags": ["vfr", "flight_plan"],
                "answers_by_country": {
                    "FR": {
                        "answer_html": "No, not required for VFR in France.",
                        "links": ["https://example.com/fr"],
                        "last_reviewed": "2025-01-01"
                    },
                    "GB": {
                        "answer_html": "No, VFR flight plans are not mandatory in the UK.",
                        "links": ["https://example.com/gb"],
                        "last_reviewed": "2025-01-01"
                    },
                    "DE": {
                        "answer_html": "Yes, a flight plan is always required in Germany.",
                        "links": ["https://example.com/de"],
                        "last_reviewed": "2025-01-01"
                    }
                }
            },
            {
                "question_id": "test-q2",
                "question_text": "What are the customs clearance requirements?",
                "category": "Customs",
                "tags": ["customs", "international"],
                "answers_by_country": {
                    "FR": {
                        "answer_html": "Must clear at designated POE.",
                        "links": [],
                        "last_reviewed": "2025-01-01"
                    },
                    "GB": {
                        "answer_html": "Clear customs at any designated airport.",
                        "links": [],
                        "last_reviewed": "2025-01-01"
                    }
                }
            },
            {
                "question_id": "test-q3",
                "question_text": "Are transponders required in Class E?",
                "category": "VFR",
                "tags": ["vfr", "transponder", "airspace"],
                "answers_by_country": {
                    "FR": {
                        "answer_html": "No",
                        "links": [],
                        "last_reviewed": "2025-01-01"
                    },
                    "GB": {
                        "answer_html": "No",
                        "links": [],
                        "last_reviewed": "2025-01-01"
                    },
                    "DE": {
                        "answer_html": "Not required but must be switched on if equipped.",
                        "links": [],
                        "last_reviewed": "2025-01-01"
                    }
                }
            }
        ]
    }

    rules_file = tmp_path / "test_rules.json"
    rules_file.write_text(json.dumps(rules_data), encoding="utf-8")
    return rules_file


@pytest.fixture
def rules_manager(sample_rules_json):
    """Create a RulesManager with test data."""
    rm = RulesManager(str(sample_rules_json))
    rm.load_rules()
    return rm


class TestCosineSimilarity:
    """Tests for cosine similarity function."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity of 1.0."""
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(a, b) == pytest.approx(1.0)

    def test_opposite_vectors(self):
        """Opposite vectors should have similarity of -1.0."""
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity of 0.0."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector(self):
        """Zero vector should return 0.0 similarity."""
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 2.0])
        assert cosine_similarity(a, b) == 0.0


class TestRulesManagerTags:
    """Tests for RulesManager tag-related methods."""

    def test_get_available_tags(self, rules_manager):
        """Should return sorted list of unique tags."""
        tags = rules_manager.get_available_tags()
        assert isinstance(tags, list)
        assert len(tags) > 0
        assert "vfr" in tags
        assert "flight_plan" in tags
        assert "customs" in tags
        assert tags == sorted(tags)  # Should be sorted

    def test_get_available_categories(self, rules_manager):
        """Should return sorted list of categories."""
        categories = rules_manager.get_available_categories()
        assert isinstance(categories, list)
        assert "VFR" in categories
        assert "Customs" in categories

    def test_get_questions_by_tag(self, rules_manager):
        """Should return question IDs for a specific tag."""
        vfr_questions = rules_manager.get_questions_by_tag("vfr")
        assert isinstance(vfr_questions, list)
        assert len(vfr_questions) >= 1
        assert "test-q1" in vfr_questions

    def test_get_questions_by_tag_nonexistent(self, rules_manager):
        """Should return empty list for nonexistent tag."""
        questions = rules_manager.get_questions_by_tag("nonexistent")
        assert questions == []

    def test_get_questions_by_category(self, rules_manager):
        """Should return question IDs for a specific category."""
        vfr_questions = rules_manager.get_questions_by_category("VFR")
        assert isinstance(vfr_questions, list)
        assert len(vfr_questions) >= 1

    def test_get_statistics_includes_tags(self, rules_manager):
        """Statistics should include tag information."""
        stats = rules_manager.get_statistics()
        assert "tags" in stats
        assert "tag_list" in stats
        assert isinstance(stats["tag_list"], list)


class TestAnswerComparer:
    """Tests for AnswerComparer class."""

    @pytest.fixture
    def mock_chromadb_client(self):
        """Create a mock ChromaDB client."""
        client = Mock()
        collection = Mock()
        collection.count.return_value = 10

        # Mock get for embeddings - use orthogonal vectors to create real differences
        # FR and GB are similar (small angle), DE is very different (large angle)
        fr_emb = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        gb_emb = [0.95, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # Similar to FR
        de_emb = [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # Orthogonal to FR/GB

        def mock_get(ids=None, where=None, include=None):
            # Return mock embeddings based on country
            result = {"ids": [], "embeddings": [], "metadatas": [], "documents": []}

            if ids:
                for doc_id in ids:
                    if "_FR_" in doc_id or doc_id.endswith("_FR_answer"):
                        result["ids"].append(doc_id)
                        result["embeddings"].append(fr_emb)
                        result["metadatas"].append({"country_code": "FR", "question_id": "test-q1"})
                        result["documents"].append("French answer")
                    elif "_GB_" in doc_id or doc_id.endswith("_GB_answer"):
                        result["ids"].append(doc_id)
                        result["embeddings"].append(gb_emb)
                        result["metadatas"].append({"country_code": "GB", "question_id": "test-q1"})
                        result["documents"].append("British answer")
                    elif "_DE_" in doc_id or doc_id.endswith("_DE_answer"):
                        result["ids"].append(doc_id)
                        result["embeddings"].append(de_emb)
                        result["metadatas"].append({"country_code": "DE", "question_id": "test-q1"})
                        result["documents"].append("German answer")

            return result

        collection.get.side_effect = mock_get
        client.get_collection.return_value = collection
        return client

    def test_initialization(self, mock_chromadb_client):
        """Should initialize correctly."""
        comparer = AnswerComparer(mock_chromadb_client)
        assert comparer._collection is None  # Lazy initialization
        assert not comparer._initialized

    def test_get_answer_embeddings(self, mock_chromadb_client, rules_manager):
        """Should retrieve embeddings for specified countries."""
        comparer = AnswerComparer(mock_chromadb_client, rules_manager)

        embeddings = comparer.get_answer_embeddings("test-q1", ["FR", "GB"])

        assert "FR" in embeddings
        assert "GB" in embeddings
        assert isinstance(embeddings["FR"], np.ndarray)
        assert isinstance(embeddings["GB"], np.ndarray)

    def test_compute_pairwise_difference_similar(self, mock_chromadb_client, rules_manager):
        """Similar answers should have low difference score."""
        comparer = AnswerComparer(mock_chromadb_client, rules_manager)

        # FR and GB have similar embeddings in our mock
        diff = comparer.compute_pairwise_difference("test-q1", "FR", "GB")

        assert diff < 0.3  # Should be relatively small

    def test_compute_pairwise_difference_different(self, mock_chromadb_client, rules_manager):
        """Different answers should have high difference score."""
        comparer = AnswerComparer(mock_chromadb_client, rules_manager)

        # FR and DE have very different embeddings in our mock
        diff = comparer.compute_pairwise_difference("test-q1", "FR", "DE")

        assert diff > 0.3  # Should be relatively large

    def test_compute_multi_country_difference(self, mock_chromadb_client, rules_manager):
        """Should compute average difference across multiple countries."""
        comparer = AnswerComparer(mock_chromadb_client, rules_manager)

        diff = comparer.compute_multi_country_difference("test-q1", ["FR", "GB", "DE"])

        assert 0.0 <= diff <= 1.0

    def test_find_most_different_questions(self, mock_chromadb_client, rules_manager):
        """Should return questions sorted by difference."""
        comparer = AnswerComparer(mock_chromadb_client, rules_manager)

        questions = ["test-q1", "test-q2"]
        differences = comparer.find_most_different_questions(
            question_ids=questions,
            countries=["FR", "GB"],
            max_questions=10,
            min_difference=0.0,
        )

        assert isinstance(differences, list)
        # All should be AnswerDifference objects
        for diff in differences:
            assert isinstance(diff, AnswerDifference)

    def test_find_outliers_for_question(self, mock_chromadb_client, rules_manager):
        """Should identify outlier countries."""
        comparer = AnswerComparer(mock_chromadb_client, rules_manager)

        result = comparer.find_outliers_for_question("test-q1", ["FR", "GB", "DE"])

        assert isinstance(result, OutlierResult)
        assert result.question_id == "test-q1"
        assert len(result.outliers) > 0

    def test_compare_countries_with_tags(self, mock_chromadb_client, rules_manager):
        """Should filter by tags when comparing countries."""
        comparer = AnswerComparer(mock_chromadb_client, rules_manager)

        result = comparer.compare_countries(
            countries=["FR", "GB"],
            tags=["vfr"],
            max_questions=10,
            min_difference=0.0,
        )

        assert isinstance(result, ComparisonResult)
        assert result.tags == ["vfr"]
        assert result.countries == ["FR", "GB"]


class TestAnswerDifference:
    """Tests for AnswerDifference dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary correctly."""
        diff = AnswerDifference(
            question_id="test-q1",
            question_text="Test question?",
            category="VFR",
            tags=["vfr", "test"],
            difference_score=0.456789,
            countries=["FR", "GB"],
            answers={"FR": "French answer", "GB": "British answer"},
        )

        result = diff.to_dict()

        assert result["question_id"] == "test-q1"
        assert result["difference_score"] == 0.457  # Rounded to 3 decimals
        assert result["countries"] == ["FR", "GB"]
        assert "FR" in result["answers"]


class TestComparisonConfig:
    """Tests for ComparisonConfig."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = ComparisonConfig()

        assert config.enabled is True
        assert config.max_questions == 15
        assert config.min_difference == 0.1
        assert config.send_all_threshold == 10
        assert config.synthesis_temperature == 0.0

    def test_custom_values(self):
        """Should accept custom values."""
        config = ComparisonConfig(
            max_questions=5,
            min_difference=0.2,
            send_all_threshold=3,
        )

        assert config.max_questions == 5
        assert config.min_difference == 0.2
        assert config.send_all_threshold == 3


class TestRulesComparisonService:
    """Tests for RulesComparisonService."""

    @pytest.fixture
    def mock_answer_comparer(self, rules_manager):
        """Create a mock AnswerComparer."""
        comparer = Mock(spec=AnswerComparer)
        comparer.rules_manager = rules_manager

        # Mock compare_countries
        comparer.compare_countries.return_value = ComparisonResult(
            countries=["FR", "DE"],
            tags=["vfr"],
            differences=[
                AnswerDifference(
                    question_id="test-q1",
                    question_text="Test question?",
                    category="VFR",
                    tags=["vfr"],
                    difference_score=0.5,
                    countries=["FR", "DE"],
                    answers={"FR": "French", "DE": "German"},
                )
            ],
            total_questions=10,
            questions_compared=1,
        )

        return comparer

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM that works with LangChain chaining."""
        from langchain_core.runnables import RunnableLambda

        # Create a simple runnable that returns a mock response with .content
        def mock_invoke(_):
            class Response:
                content = "This is a synthesized comparison."
            return Response()

        return RunnableLambda(mock_invoke)

    def test_compare_countries_with_synthesis(self, mock_answer_comparer, mock_llm):
        """Should generate synthesis when requested."""
        from shared.aviation_agent.comparison_service import RulesComparisonService

        service = RulesComparisonService(
            answer_comparer=mock_answer_comparer,
            llm=mock_llm,
        )

        result = service.compare_countries(
            countries=["FR", "DE"],
            tags=["vfr"],
            synthesize=True,
        )

        assert result.synthesis is not None
        assert isinstance(result.synthesis, str)
        assert len(result.synthesis) > 0
        assert result.countries == ["FR", "DE"]
        assert result.tags == ["vfr"]

    def test_compare_countries_without_synthesis(self, mock_answer_comparer):
        """Should skip synthesis when not requested."""
        from shared.aviation_agent.comparison_service import RulesComparisonService
        from langchain_core.runnables import RunnableLambda

        # Track if LLM was called
        call_count = {"count": 0}

        def tracking_invoke(_):
            call_count["count"] += 1
            class Response:
                content = "Should not be called"
            return Response()

        mock_llm = RunnableLambda(tracking_invoke)

        service = RulesComparisonService(
            answer_comparer=mock_answer_comparer,
            llm=mock_llm,
        )

        result = service.compare_countries(
            countries=["FR", "DE"],
            synthesize=False,
        )

        assert result.synthesis == ""
        # LLM should not be called
        assert call_count["count"] == 0, "LLM should not be called when synthesize=False"


class TestIntegration:
    """Integration tests with real ChromaDB (if available)."""

    @pytest.fixture
    def vector_db_with_answers(self, sample_rules_json, tmp_path):
        """Build a vector DB with answer embeddings."""
        # Skip if OpenAI key not available
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        from shared.aviation_agent.rules_rag import build_vector_db

        vector_db_path = tmp_path / "test_vector_db"

        result = build_vector_db(
            rules_json_path=sample_rules_json,
            vector_db_path=vector_db_path,
            force_rebuild=True,
            build_answer_embeddings=True,
        )

        assert isinstance(result, dict)
        assert result["questions"] > 0
        assert result["answers"] > 0

        return vector_db_path

    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_full_pipeline(self, vector_db_with_answers, rules_manager):
        """Test full comparison pipeline with real embeddings."""
        comparer = create_answer_comparer(
            vector_db_path=str(vector_db_with_answers),
            rules_manager=rules_manager,
        )

        assert comparer is not None

        # Test embedding retrieval
        embeddings = comparer.get_answer_embeddings("test-q1", ["FR", "GB"])
        assert len(embeddings) > 0

        # Test pairwise comparison
        diff = comparer.compute_pairwise_difference("test-q1", "FR", "GB")
        assert 0.0 <= diff <= 1.0

        # Test comparison
        result = comparer.compare_countries(
            countries=["FR", "GB"],
            max_questions=10,
            min_difference=0.0,
        )
        assert isinstance(result, ComparisonResult)
