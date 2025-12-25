"""
Behavioral tests for rules retrieval (RAG and comparison paths).

These tests verify which rules are retrieved for different queries,
helping validate the quality of semantic search and comparison filtering.

Run with:
    RUN_RULES_RETRIEVAL_TESTS=1 pytest tests/aviation_agent/test_rules_retrieval_behavior.py -v

Or run specific test:
    RUN_RULES_RETRIEVAL_TESTS=1 pytest tests/aviation_agent/test_rules_retrieval_behavior.py::test_rag_retrieval -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest


def _load_rag_test_cases() -> List[Dict[str, Any]]:
    """Load RAG test cases from fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "rag_test_cases.json"
    with open(fixture_path) as f:
        return json.load(f)


def _load_comparison_test_cases() -> List[Dict[str, Any]]:
    """Load comparison test cases from fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "comparison_test_cases.json"
    with open(fixture_path) as f:
        return json.load(f)


def _should_run_retrieval_tests() -> bool:
    """Check if retrieval tests should run (require explicit opt-in)."""
    return os.getenv("RUN_RULES_RETRIEVAL_TESTS") == "1"


@pytest.fixture(scope="module")
def rag_system():
    """Create RulesRAGSystem for testing."""
    if not _should_run_retrieval_tests():
        pytest.skip("Retrieval tests require RUN_RULES_RETRIEVAL_TESTS=1")

    from shared.aviation_agent.rules_rag import RulesRAGSystem
    from shared.rules_manager import RulesManager

    # Initialize with real data
    rules_manager = RulesManager(rules_json_path="data/rules.json")
    rules_manager.load_rules()

    rag = RulesRAGSystem(
        chroma_path="data/chroma_rules",
        rules_manager=rules_manager,
        enable_reformulation=False,  # Disable for deterministic tests
    )

    return rag


@pytest.fixture(scope="module")
def answer_comparer():
    """Create AnswerComparer for testing."""
    if not _should_run_retrieval_tests():
        pytest.skip("Retrieval tests require RUN_RULES_RETRIEVAL_TESTS=1")

    from shared.aviation_agent.answer_comparer import AnswerComparer
    from shared.rules_manager import RulesManager

    # Initialize with real data
    rules_manager = RulesManager(rules_json_path="data/rules.json")
    rules_manager.load_rules()

    comparer = AnswerComparer(
        chroma_path="data/chroma_rules",
        rules_manager=rules_manager,
    )

    return comparer


@pytest.mark.rules_retrieval
@pytest.mark.parametrize("test_case", _load_rag_test_cases(), ids=lambda tc: tc.get("description", "")[:50])
def test_rag_retrieval(test_case: Dict[str, Any], rag_system):
    """
    Test RAG retrieval for a given query.

    This test captures which rules are retrieved and logs them for inspection.
    Add assertions once expected results are validated.
    """
    query = test_case["query"]
    country = test_case["country"]
    top_k = test_case.get("top_k", 5)
    description = test_case.get("description", "")

    # Retrieve rules
    results = rag_system.retrieve_rules(
        query=query,
        countries=[country],
        top_k=top_k,
    )

    # Log results for inspection
    print(f"\n{'='*70}")
    print(f"Query: {query}")
    print(f"Country: {country}")
    print(f"Description: {description}")
    print(f"Retrieved {len(results)} rules:")
    print("-" * 70)

    for i, rule in enumerate(results, 1):
        question_id = rule.get("question_id", "N/A")
        question_text = rule.get("question_text", rule.get("question", "N/A"))[:80]
        score = rule.get("score", rule.get("similarity", 0))
        tags = rule.get("tags", [])
        category = rule.get("category", "N/A")

        print(f"  {i}. [{score:.3f}] {question_text}")
        print(f"     ID: {question_id} | Category: {category} | Tags: {tags}")

    print(f"{'='*70}")

    # Basic assertion: should retrieve some results
    assert len(results) > 0, f"No results retrieved for query: {query}"

    # TODO: Add specific assertions once expected results are validated
    # Example: assert any("flight plan" in r.get("question_text", "").lower() for r in results)


@pytest.mark.rules_retrieval
@pytest.mark.parametrize("test_case", _load_comparison_test_cases(), ids=lambda tc: tc.get("description", "")[:50])
def test_comparison_retrieval(test_case: Dict[str, Any], answer_comparer):
    """
    Test comparison retrieval between countries.

    This test captures which rule differences are identified and logs them.
    Add assertions once expected results are validated.
    """
    countries = test_case["countries"]
    tags = test_case.get("tags")
    description = test_case.get("description", "")

    # Compare countries
    result = answer_comparer.compare_countries(
        countries=countries,
        tags=tags,
        max_questions=20,  # Get more for inspection
        min_difference=0.05,  # Lower threshold for more results
    )

    # Log results for inspection
    print(f"\n{'='*70}")
    print(f"Countries: {countries}")
    print(f"Tags: {tags or 'None'}")
    print(f"Description: {description}")
    print(f"Total questions: {result.total_questions}")
    print(f"Questions compared: {result.questions_compared}")
    print(f"Differences found: {len(result.differences)}")
    print("-" * 70)

    for i, diff in enumerate(result.differences[:10], 1):  # Show top 10
        question_id = diff.question_id
        question_text = diff.question_text[:70] if diff.question_text else "N/A"
        diff_score = diff.difference_score

        print(f"  {i}. [{diff_score:.3f}] {question_text}")
        print(f"     ID: {question_id}")

        # Show answer snippets for each country
        for cc, answer in diff.answers.items():
            answer_preview = answer[:60] + "..." if len(answer) > 60 else answer
            print(f"     {cc}: {answer_preview}")

    print(f"{'='*70}")

    # Basic assertion: comparison should complete
    assert result.total_questions >= 0, "Comparison failed"

    # TODO: Add specific assertions once expected results are validated
    # Example: assert len(result.differences) > 0, "Should find some differences"
