#!/usr/bin/env python3
"""
Rules Comparison Service for cross-country aviation rule analysis.

This module provides a high-level API for comparing aviation rules across
countries, combining embedding-based filtering with LLM synthesis.

Supports two main use cases:
1. Cross-country differences: "What's different about airspace rules in FR vs DE?"
2. Norm/outlier detection: "What's the typical rule for transponders? Who's different?"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from .answer_comparer import (
    AnswerComparer,
    AnswerDifference,
    ComparisonResult,
    OutlierResult,
)
from .behavior_config import ComparisonConfig

logger = logging.getLogger(__name__)


# Default synthesis prompt for cross-country comparison
DEFAULT_COMPARISON_PROMPT = """You are an aviation regulations expert helping pilots understand differences between countries.

You are comparing aviation rules for: {countries}
{topic_context}

Here are the rules with semantic differences detected between the countries:

{rules_context}

Instructions:
1. Analyze the REAL regulatory differences (not just phrasing differences)
2. Group related differences by topic/importance
3. Highlight differences that would practically affect a pilot
4. Be specific about which country requires what
5. If two countries say essentially the same thing differently, note they are equivalent
6. Use clear formatting with bullet points

Provide a clear, practical summary of what a pilot flying between these countries needs to know."""


# Default prompt for outlier analysis
DEFAULT_OUTLIER_PROMPT = """You are an aviation regulations expert analyzing how different countries handle a specific regulation.

Question: {question_text}

Countries analyzed: {countries}

Here are the answers ranked by how different they are from the typical response:

{outliers_context}

The mean distance from typical is: {mean_distance:.2f} (0 = identical, 1 = completely different)

Instructions:
1. Identify what the "typical" or "standard" approach is across countries
2. Highlight countries that differ significantly and explain how
3. Note any practical implications for pilots
4. Be specific about regulatory requirements

Provide a clear summary of the norm and the outliers."""


@dataclass
class SynthesizedComparison:
    """Result of a synthesized cross-country comparison."""

    countries: List[str]
    tags: Optional[List[str]]
    synthesis: str  # LLM-generated summary
    differences: List[Dict[str, Any]]  # Raw differences for reference
    total_questions: int
    questions_analyzed: int
    filtered_by_embedding: bool  # Whether embedding filtering was applied


@dataclass
class SynthesizedOutlierAnalysis:
    """Result of outlier analysis with LLM synthesis."""

    question_id: str
    question_text: str
    synthesis: str
    outliers: List[Dict[str, Any]]
    countries_analyzed: List[str]


class RulesComparisonService:
    """
    High-level service for cross-country rule comparison.

    Combines AnswerComparer (embedding-based filtering) with LLM synthesis
    to provide actionable insights about rule differences.
    """

    def __init__(
        self,
        answer_comparer: AnswerComparer,
        llm: Runnable,
        config: Optional[ComparisonConfig] = None,
        comparison_prompt: Optional[str] = None,
        outlier_prompt: Optional[str] = None,
    ):
        """
        Initialize RulesComparisonService.

        Args:
            answer_comparer: AnswerComparer instance for embedding operations
            llm: LLM for synthesis
            config: Optional ComparisonConfig for parameters
            comparison_prompt: Optional custom comparison prompt
            outlier_prompt: Optional custom outlier analysis prompt
        """
        self.answer_comparer = answer_comparer
        self.llm = llm
        self.config = config or ComparisonConfig()

        # Build prompt templates
        self.comparison_template = ChatPromptTemplate.from_messages([
            ("system", comparison_prompt or DEFAULT_COMPARISON_PROMPT),
        ])

        self.outlier_template = ChatPromptTemplate.from_messages([
            ("system", outlier_prompt or DEFAULT_OUTLIER_PROMPT),
        ])

    def compare_countries(
        self,
        countries: List[str],
        tags: Optional[List[str]] = None,
        max_questions: Optional[int] = None,
        min_difference: Optional[float] = None,
        synthesize: bool = True,
    ) -> SynthesizedComparison:
        """
        Compare rules between countries with optional LLM synthesis.

        Args:
            countries: List of country codes to compare (e.g., ["FR", "DE"])
            tags: Optional list of tags to filter questions (e.g., ["airspace", "flight_plan"])
            max_questions: Override config max_questions
            min_difference: Override config min_difference
            synthesize: Whether to generate LLM synthesis

        Returns:
            SynthesizedComparison with differences and optional synthesis
        """
        # Use config defaults if not overridden
        effective_max = max_questions or self.config.max_questions
        effective_min_diff = min_difference if min_difference is not None else self.config.min_difference

        # Get filtered differences from AnswerComparer
        comparison = self.answer_comparer.compare_countries(
            countries=countries,
            tags=tags,
            max_questions=effective_max,
            min_difference=effective_min_diff,
            send_all_threshold=self.config.send_all_threshold,
        )

        # Convert to dict format
        differences_dicts = [d.to_dict() for d in comparison.differences]

        # Check if embedding filtering was applied
        filtered_by_embedding = comparison.total_questions > self.config.send_all_threshold

        synthesis = ""
        if synthesize and comparison.differences:
            synthesis = self._synthesize_comparison(
                countries=countries,
                differences=comparison.differences,
                tags=tags,
            )

        return SynthesizedComparison(
            countries=countries,
            tags=tags,
            synthesis=synthesis,
            differences=differences_dicts,
            total_questions=comparison.total_questions,
            questions_analyzed=comparison.questions_compared,
            filtered_by_embedding=filtered_by_embedding,
        )

    def analyze_outliers(
        self,
        question_id: str,
        countries: Optional[List[str]] = None,
        top_n: int = 5,
        synthesize: bool = True,
    ) -> SynthesizedOutlierAnalysis:
        """
        Find countries with unusual answers for a specific question.

        Args:
            question_id: Question ID to analyze
            countries: Optional list of countries. If None, uses all.
            top_n: Number of top outliers to include
            synthesize: Whether to generate LLM synthesis

        Returns:
            SynthesizedOutlierAnalysis with outliers and optional synthesis
        """
        # Get outliers from AnswerComparer
        outlier_result = self.answer_comparer.find_outliers_for_question(
            question_id=question_id,
            countries=countries,
            top_n=top_n,
        )

        synthesis = ""
        if synthesize and outlier_result.outliers:
            synthesis = self._synthesize_outliers(outlier_result)

        return SynthesizedOutlierAnalysis(
            question_id=question_id,
            question_text=outlier_result.question_text,
            synthesis=synthesis,
            outliers=outlier_result.outliers,
            countries_analyzed=outlier_result.countries_analyzed,
        )

    def analyze_topic_outliers(
        self,
        tag: Optional[str] = None,
        category: Optional[str] = None,
        countries: Optional[List[str]] = None,
        max_questions: int = 5,
    ) -> List[SynthesizedOutlierAnalysis]:
        """
        Find outliers across multiple questions in a topic.

        Args:
            tag: Tag to filter questions
            category: Category to filter questions
            countries: Countries to analyze
            max_questions: Maximum questions to analyze

        Returns:
            List of outlier analyses for each question
        """
        if not self.answer_comparer.rules_manager:
            logger.error("RulesManager required for topic outlier analysis")
            return []

        # Get question IDs
        rm = self.answer_comparer.rules_manager
        if not rm.loaded:
            rm.load_rules()

        if tag:
            question_ids = rm.get_questions_by_tag(tag)
        elif category:
            question_ids = rm.get_questions_by_category(category)
        else:
            question_ids = list(rm.question_map.keys())

        # Limit to max_questions
        question_ids = question_ids[:max_questions]

        results = []
        for qid in question_ids:
            analysis = self.analyze_outliers(
                question_id=qid,
                countries=countries,
                synthesize=True,
            )
            if analysis.outliers:
                results.append(analysis)

        return results

    def _synthesize_comparison(
        self,
        countries: List[str],
        differences: List[AnswerDifference],
        tags: Optional[List[str]],
    ) -> str:
        """Generate LLM synthesis for comparison."""
        # Build topic context
        topic_context = f"Topics: {', '.join(tags)}" if tags else ""

        # Build rules context
        rules_lines = []
        for i, diff in enumerate(differences, 1):
            rules_lines.append(f"\n### {i}. {diff.question_text}")
            rules_lines.append(f"Tags: {', '.join(diff.tags)}")
            rules_lines.append(f"Semantic difference score: {diff.difference_score:.2f}")
            rules_lines.append("")
            for country, answer in diff.answers.items():
                rules_lines.append(f"**{country}**: {answer}")
            rules_lines.append("")

        rules_context = "\n".join(rules_lines)

        try:
            chain = self.comparison_template | self.llm
            result = chain.invoke({
                "countries": ", ".join(countries),
                "topic_context": topic_context,
                "rules_context": rules_context,
            })

            return result.content if hasattr(result, "content") else str(result)

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return f"Error generating synthesis: {e}"

    def _synthesize_outliers(self, outlier_result: OutlierResult) -> str:
        """Generate LLM synthesis for outlier analysis."""
        # Build outliers context
        outliers_lines = []
        for i, outlier in enumerate(outlier_result.outliers, 1):
            outliers_lines.append(
                f"{i}. **{outlier['country']}** (distance: {outlier['distance']:.2f})"
            )
            outliers_lines.append(f"   Answer: {outlier['answer']}")
            outliers_lines.append("")

        outliers_context = "\n".join(outliers_lines)

        try:
            chain = self.outlier_template | self.llm
            result = chain.invoke({
                "question_text": outlier_result.question_text,
                "countries": ", ".join(outlier_result.countries_analyzed),
                "outliers_context": outliers_context,
                "mean_distance": outlier_result.mean_distance,
            })

            return result.content if hasattr(result, "content") else str(result)

        except Exception as e:
            logger.error(f"Outlier synthesis failed: {e}")
            return f"Error generating synthesis: {e}"


def create_comparison_service(
    vector_db_path: Optional[str] = None,
    vector_db_url: Optional[str] = None,
    rules_manager: Optional[Any] = None,
    llm: Optional[Runnable] = None,
    config: Optional[ComparisonConfig] = None,
) -> Optional[RulesComparisonService]:
    """
    Factory function to create a RulesComparisonService.

    Args:
        vector_db_path: Path to ChromaDB storage (local mode)
        vector_db_url: URL to ChromaDB service
        rules_manager: RulesManager instance
        llm: LLM for synthesis. If None, uses default from environment.
        config: ComparisonConfig. If None, uses defaults.

    Returns:
        RulesComparisonService instance or None if initialization fails
    """
    from .answer_comparer import create_answer_comparer

    try:
        # Create answer comparer
        answer_comparer = create_answer_comparer(
            vector_db_path=vector_db_path,
            vector_db_url=vector_db_url,
            rules_manager=rules_manager,
        )

        if not answer_comparer:
            logger.error("Failed to create AnswerComparer")
            return None

        # Create LLM if not provided
        if llm is None:
            from langchain_openai import ChatOpenAI
            import os

            model = os.getenv("COMPARISON_MODEL", "gpt-4o")
            temperature = config.synthesis_temperature if config else 0.0
            llm = ChatOpenAI(model=model, temperature=temperature)

        return RulesComparisonService(
            answer_comparer=answer_comparer,
            llm=llm,
            config=config,
        )

    except Exception as e:
        logger.error(f"Failed to create RulesComparisonService: {e}")
        return None
