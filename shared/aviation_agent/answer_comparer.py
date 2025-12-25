#!/usr/bin/env python3
"""
Answer comparison module for cross-country rule analysis.

This module provides functionality to compare aviation rules across countries
using answer embeddings stored in ChromaDB. It supports:
- Pairwise country comparison (find differences between two countries)
- Outlier detection (find countries with unusual rules for a question)
- Batch comparison for multiple questions with embedding-based filtering
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AnswerDifference:
    """Represents a semantic difference between country answers for a question."""

    question_id: str
    question_text: str
    category: str
    tags: List[str]
    difference_score: float  # 0.0 = identical, 1.0 = completely different
    countries: List[str]
    answers: Dict[str, str]  # country_code -> answer_text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "category": self.category,
            "tags": self.tags,
            "difference_score": round(self.difference_score, 3),
            "countries": self.countries,
            "answers": self.answers,
        }


@dataclass
class OutlierResult:
    """Result of outlier detection for a question."""

    question_id: str
    question_text: str
    countries_analyzed: List[str]
    outliers: List[Dict[str, Any]]  # [{country, distance, answer}, ...]
    mean_distance: float


@dataclass
class ComparisonResult:
    """Result of a cross-country comparison."""

    countries: List[str]
    tags: Optional[List[str]]
    differences: List[AnswerDifference]
    total_questions: int
    questions_compared: int
    synthesis: Optional[str] = None  # LLM-generated summary


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))


class AnswerComparer:
    """
    Compare answer embeddings across countries using ChromaDB.

    This class provides methods to:
    - Get answer embeddings for specific questions/countries
    - Compute pairwise differences between countries
    - Find outlier countries for specific questions
    - Filter questions by semantic difference for efficient LLM synthesis
    """

    ANSWERS_COLLECTION_NAME = "aviation_rules_answers"

    def __init__(
        self,
        chromadb_client: Any,
        rules_manager: Optional[Any] = None,
    ):
        """
        Initialize AnswerComparer.

        Args:
            chromadb_client: ChromaDB client instance
            rules_manager: Optional RulesManager for question metadata lookups
        """
        self.client = chromadb_client
        self.rules_manager = rules_manager
        self._collection = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy initialization of collection."""
        if self._initialized:
            return self._collection is not None

        try:
            self._collection = self.client.get_collection(
                name=self.ANSWERS_COLLECTION_NAME,
                embedding_function=None  # We retrieve embeddings directly
            )
            doc_count = self._collection.count()
            logger.info(f"✓ AnswerComparer initialized with {doc_count} answer embeddings")
            self._initialized = True
            return True
        except Exception as e:
            logger.warning(f"Could not load answers collection: {e}")
            logger.warning("Answer comparison will not be available. "
                          "Rebuild vector DB with build_answer_embeddings=True")
            self._initialized = True
            return False

    def get_answer_embeddings(
        self,
        question_id: str,
        countries: Optional[List[str]] = None,
    ) -> Dict[str, np.ndarray]:
        """
        Get answer embeddings for a question across countries.

        Args:
            question_id: Question ID to get embeddings for
            countries: Optional list of countries. If None, gets all available.

        Returns:
            Dict mapping country_code to embedding vector
        """
        if not self._ensure_initialized():
            return {}

        try:
            if countries:
                # Get specific countries
                ids = [
                    f"{question_id}_{cc.upper()}_answer".replace(" ", "_")
                    for cc in countries
                ]
                result = self._collection.get(
                    ids=ids,
                    include=["embeddings", "metadatas"]
                )
            else:
                # Get all countries for this question
                result = self._collection.get(
                    where={"question_id": question_id},
                    include=["embeddings", "metadatas"]
                )

            embeddings = {}
            if result and result.get("ids"):
                result_embeddings = result.get("embeddings")
                result_metadatas = result.get("metadatas")

                # Check if embeddings exist and are not empty
                has_embeddings = (
                    result_embeddings is not None
                    and len(result_embeddings) > 0
                )

                for i, doc_id in enumerate(result["ids"]):
                    if has_embeddings and i < len(result_embeddings):
                        # Extract country from metadata
                        metadata = result_metadatas[i] if result_metadatas else {}
                        country = metadata.get("country_code", "")
                        emb = result_embeddings[i]
                        # Check if embedding exists and has content
                        if country and emb is not None and len(emb) > 0:
                            embeddings[country] = np.array(emb)

            return embeddings

        except Exception as e:
            logger.error(f"Failed to get answer embeddings for {question_id}: {e}")
            return {}

    def get_answer_texts(
        self,
        question_id: str,
        countries: List[str],
    ) -> Dict[str, str]:
        """
        Get answer texts for a question across specified countries.

        Args:
            question_id: Question ID
            countries: List of country codes

        Returns:
            Dict mapping country_code to answer_text
        """
        if not self._ensure_initialized():
            return {}

        try:
            ids = [
                f"{question_id}_{cc.upper()}_answer".replace(" ", "_")
                for cc in countries
            ]
            result = self._collection.get(
                ids=ids,
                include=["documents", "metadatas"]
            )

            answers = {}
            if result and result["ids"]:
                for i, doc_id in enumerate(result["ids"]):
                    metadata = result["metadatas"][i] if result["metadatas"] else {}
                    country = metadata.get("country_code", "")
                    document = result["documents"][i] if result["documents"] else ""
                    if country:
                        answers[country] = document

            return answers

        except Exception as e:
            logger.error(f"Failed to get answer texts for {question_id}: {e}")
            return {}

    def compute_pairwise_difference(
        self,
        question_id: str,
        country_a: str,
        country_b: str,
    ) -> float:
        """
        Compute semantic difference between two countries' answers.

        Args:
            question_id: Question ID to compare
            country_a: First country code
            country_b: Second country code

        Returns:
            Difference score: 0.0 = identical, 1.0 = completely different
            Returns 0.0 if embeddings are not available.
        """
        embeddings = self.get_answer_embeddings(
            question_id,
            [country_a.upper(), country_b.upper()]
        )

        country_a_upper = country_a.upper()
        country_b_upper = country_b.upper()

        if country_a_upper not in embeddings or country_b_upper not in embeddings:
            logger.debug(f"Missing embeddings for {question_id}: "
                        f"got {list(embeddings.keys())}, need [{country_a_upper}, {country_b_upper}]")
            return 0.0

        similarity = cosine_similarity(
            embeddings[country_a_upper],
            embeddings[country_b_upper]
        )

        return 1.0 - similarity

    def compute_multi_country_difference(
        self,
        question_id: str,
        countries: List[str],
    ) -> float:
        """
        Compute overall semantic difference across multiple countries.

        Uses pairwise comparisons and returns the average difference.

        Args:
            question_id: Question ID to compare
            countries: List of country codes (2 or more)

        Returns:
            Average difference score across all pairs
        """
        if len(countries) < 2:
            return 0.0

        embeddings = self.get_answer_embeddings(question_id, countries)

        if len(embeddings) < 2:
            return 0.0

        # Compute pairwise differences
        countries_with_emb = list(embeddings.keys())
        differences = []

        for i, c1 in enumerate(countries_with_emb):
            for c2 in countries_with_emb[i + 1:]:
                similarity = cosine_similarity(embeddings[c1], embeddings[c2])
                differences.append(1.0 - similarity)

        return float(np.mean(differences)) if differences else 0.0

    def find_most_different_questions(
        self,
        question_ids: List[str],
        countries: List[str],
        max_questions: int = 15,
        min_difference: float = 0.1,
    ) -> List[AnswerDifference]:
        """
        Find questions with the biggest semantic differences between countries.

        This is the core method for filtering questions before LLM synthesis.

        Args:
            question_ids: List of question IDs to analyze
            countries: List of countries to compare
            max_questions: Maximum questions to return
            min_difference: Minimum difference threshold

        Returns:
            List of AnswerDifference objects sorted by difference (highest first)
        """
        if not self._ensure_initialized():
            return []

        if len(countries) < 2:
            logger.warning("Need at least 2 countries to compare")
            return []

        # Compute differences for all questions
        differences = []

        for qid in question_ids:
            diff_score = self.compute_multi_country_difference(qid, countries)

            if diff_score < min_difference:
                continue

            # Get answer texts and metadata
            answers = self.get_answer_texts(qid, countries)

            # Get question metadata from rules_manager if available
            question_text = ""
            category = ""
            tags = []

            if self.rules_manager:
                if not self.rules_manager.loaded:
                    self.rules_manager.load_rules()
                q_info = self.rules_manager.question_map.get(qid, {})
                question_text = q_info.get("question_text", "")
                category = q_info.get("category", "")
                tags = q_info.get("tags", [])

            differences.append(AnswerDifference(
                question_id=qid,
                question_text=question_text,
                category=category,
                tags=tags,
                difference_score=diff_score,
                countries=countries,
                answers=answers,
            ))

        # Sort by difference (highest first)
        differences.sort(key=lambda x: x.difference_score, reverse=True)

        # Return top N
        result = differences[:max_questions]

        logger.info(
            f"Found {len(differences)} questions above threshold {min_difference}, "
            f"returning top {len(result)}"
        )

        return result

    def find_outliers_for_question(
        self,
        question_id: str,
        countries: Optional[List[str]] = None,
        top_n: int = 3,
    ) -> OutlierResult:
        """
        Find countries with unusual answers for a question.

        Computes the mean embedding across all countries, then finds
        countries whose answers are furthest from the mean.

        Args:
            question_id: Question ID to analyze
            countries: Optional list of countries. If None, uses all available.
            top_n: Number of top outliers to return

        Returns:
            OutlierResult with outlier countries sorted by distance
        """
        embeddings = self.get_answer_embeddings(question_id, countries)

        if len(embeddings) < 2:
            return OutlierResult(
                question_id=question_id,
                question_text="",
                countries_analyzed=[],
                outliers=[],
                mean_distance=0.0,
            )

        # Compute mean embedding
        all_embs = np.array(list(embeddings.values()))
        mean_emb = all_embs.mean(axis=0)

        # Get answer texts
        country_list = list(embeddings.keys())
        answers = self.get_answer_texts(question_id, country_list)

        # Compute distance from mean for each country
        outliers = []
        distances = []

        for country, emb in embeddings.items():
            distance = 1.0 - cosine_similarity(emb, mean_emb)
            distances.append(distance)
            outliers.append({
                "country": country,
                "distance": round(distance, 3),
                "answer": answers.get(country, ""),
            })

        # Sort by distance (highest first)
        outliers.sort(key=lambda x: x["distance"], reverse=True)

        # Get question text
        question_text = ""
        if self.rules_manager:
            if not self.rules_manager.loaded:
                self.rules_manager.load_rules()
            q_info = self.rules_manager.question_map.get(question_id, {})
            question_text = q_info.get("question_text", "")

        return OutlierResult(
            question_id=question_id,
            question_text=question_text,
            countries_analyzed=country_list,
            outliers=outliers[:top_n],
            mean_distance=float(np.mean(distances)),
        )

    def compare_countries(
        self,
        countries: List[str],
        tags: Optional[List[str]] = None,
        max_questions: int = 15,
        min_difference: float = 0.1,
        send_all_threshold: int = 10,
    ) -> ComparisonResult:
        """
        Compare rules between countries, optionally filtered by tags.

        This is the main entry point for cross-country comparison.

        Args:
            countries: List of country codes to compare
            tags: Optional list of tags to filter questions (union of all tag matches)
            max_questions: Maximum questions to include
            min_difference: Minimum semantic difference threshold
            send_all_threshold: If total questions <= this, include all

        Returns:
            ComparisonResult with filtered differences
        """
        if not self.rules_manager:
            logger.error("RulesManager required for compare_countries")
            return ComparisonResult(
                countries=countries,
                tags=tags,
                differences=[],
                total_questions=0,
                questions_compared=0,
            )

        # Ensure rules are loaded
        if not self.rules_manager.loaded:
            self.rules_manager.load_rules()

        # Get question IDs based on tags filter
        if tags:
            question_ids = self.rules_manager.get_questions_by_tags(tags)
        else:
            # All questions
            question_ids = list(self.rules_manager.question_map.keys())

        total_questions = len(question_ids)

        # If small set, include all regardless of difference
        if total_questions <= send_all_threshold:
            # Set min_difference to 0 to include all
            effective_min_diff = 0.0
            effective_max_q = total_questions
        else:
            effective_min_diff = min_difference
            effective_max_q = max_questions

        # Find most different questions
        differences = self.find_most_different_questions(
            question_ids=question_ids,
            countries=countries,
            max_questions=effective_max_q,
            min_difference=effective_min_diff,
        )

        return ComparisonResult(
            countries=countries,
            tags=tags,
            differences=differences,
            total_questions=total_questions,
            questions_compared=len(differences),
        )


def create_answer_comparer(
    vector_db_path: Optional[str] = None,
    vector_db_url: Optional[str] = None,
    rules_manager: Optional[Any] = None,
) -> Optional[AnswerComparer]:
    """
    Factory function to create an AnswerComparer.

    Args:
        vector_db_path: Path to ChromaDB storage (local mode)
        vector_db_url: URL to ChromaDB service (takes precedence)
        rules_manager: Optional RulesManager instance

    Returns:
        AnswerComparer instance or None if initialization fails
    """
    try:
        import chromadb
        from chromadb.config import Settings
        from urllib.parse import urlparse

        if vector_db_url:
            parsed_url = urlparse(vector_db_url)
            host = parsed_url.hostname or "localhost"
            port = parsed_url.port or (8000 if parsed_url.scheme == "http" else 443)
            client = chromadb.HttpClient(
                host=host,
                port=port,
                settings=Settings(anonymized_telemetry=False)
            )
        elif vector_db_path:
            client = chromadb.PersistentClient(
                path=vector_db_path,
                settings=Settings(anonymized_telemetry=False)
            )
        else:
            logger.error("Either vector_db_path or vector_db_url required")
            return None

        return AnswerComparer(client, rules_manager)

    except Exception as e:
        logger.error(f"Failed to create AnswerComparer: {e}")
        return None
