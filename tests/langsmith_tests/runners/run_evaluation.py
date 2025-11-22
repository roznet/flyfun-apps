#!/usr/bin/env python3
"""
LangSmith Evaluation Runner for Aviation Agent

This script runs evaluations against the aviation agent using LangSmith datasets and custom evaluators.

Usage:
    python run_evaluation.py --dataset issue-8-baseline --create-dataset
    python run_evaluation.py --dataset issue-8-baseline --experiment baseline-v1
    python run_evaluation.py --category geographic_search --experiment geo-test
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from langsmith import Client
from langsmith.evaluation import evaluate
from langchain_core.messages import HumanMessage

# Import test cases and evaluators
from tests.langsmith_tests.datasets.issue_8_baseline import (
    ALL_TEST_CASES,
    get_test_cases_by_category,
)
from tests.langsmith_tests.evaluators.tool_selection import (
    evaluate_tool_selection,
    evaluate_tool_execution,
)
from tests.langsmith_tests.evaluators.filter_extraction import (
    evaluate_filter_extraction,
    evaluate_filter_completeness,
)
from tests.langsmith_tests.evaluators.answer_quality import (
    evaluate_answer_mentions,
    evaluate_answer_length,
    evaluate_answer_format,
)

# Import aviation agent
from shared.aviation_agent.adapters import run_aviation_agent
from shared.aviation_agent.config import get_settings


def create_langsmith_dataset(dataset_name: str, test_cases: List[Dict[str, Any]]):
    """
    Create a LangSmith dataset from test cases.

    Args:
        dataset_name: Name for the dataset
        test_cases: List of test case dictionaries
    """
    client = Client()

    print(f"Creating dataset '{dataset_name}' with {len(test_cases)} test cases...")

    # Check if dataset already exists
    try:
        existing_datasets = list(client.list_datasets(dataset_name=dataset_name))
        if existing_datasets:
            print(f"Dataset '{dataset_name}' already exists. Deleting and recreating...")
            for ds in existing_datasets:
                client.delete_dataset(dataset_id=ds.id)
    except Exception as e:
        print(f"Note: {e}")

    # Create new dataset
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description=f"Test cases for aviation agent evaluation ({len(test_cases)} cases)",
    )

    # Add examples
    for test_case in test_cases:
        client.create_example(
            dataset_id=dataset.id,
            inputs=test_case["inputs"],
            outputs=test_case.get("expected", {}),
            metadata={
                "test_id": test_case["id"],
                "category": test_case["category"],
                "description": test_case.get("description", ""),
            },
        )

    print(f"✓ Dataset '{dataset_name}' created with {len(test_cases)} examples")
    print(f"  View at: https://smith.langchain.com/datasets")

    return dataset


def run_evaluation_suite(
    dataset_name: str,
    experiment_prefix: str = "aviation-agent-eval",
    max_concurrency: int = 1,
):
    """
    Run full evaluation suite against a dataset.

    Args:
        dataset_name: Name of the LangSmith dataset
        experiment_prefix: Prefix for experiment name
        max_concurrency: Maximum number of concurrent evaluations
    """
    settings = get_settings()

    if not settings.enabled:
        print("ERROR: Aviation agent is disabled in settings")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Running Evaluation: {experiment_prefix}")
    print(f"Dataset: {dataset_name}")
    print(f"{'='*60}\n")

    # Define the function to evaluate
    def aviation_agent_predict(inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Wrapper to run aviation agent and return outputs"""
        query = inputs.get("query")
        if not query:
            return {"error": "No query provided"}

        try:
            # Convert query to messages
            messages = [HumanMessage(content=query)]

            # Run aviation agent
            state = run_aviation_agent(messages, settings=settings)

            # Return the full state as output
            return {
                "plan": state.get("plan"),
                "tool_result": state.get("tool_result"),
                "final_answer": state.get("final_answer"),
                "thinking": state.get("thinking"),
                "ui_payload": state.get("ui_payload"),
                "error": state.get("error"),
            }

        except Exception as e:
            return {"error": str(e), "final_answer": f"Error: {str(e)}"}

    # Run evaluation
    print("Starting evaluation...")
    print(f"Evaluators:")
    print(f"  - Tool Selection")
    print(f"  - Tool Execution")
    print(f"  - Filter Extraction")
    print(f"  - Filter Completeness")
    print(f"  - Answer Mentions")
    print(f"  - Answer Length")
    print(f"  - Answer Format")
    print()

    results = evaluate(
        aviation_agent_predict,
        data=dataset_name,
        evaluators=[
            evaluate_tool_selection,
            evaluate_tool_execution,
            evaluate_filter_extraction,
            evaluate_filter_completeness,
            evaluate_answer_mentions,
            evaluate_answer_length,
            evaluate_answer_format,
        ],
        experiment_prefix=experiment_prefix,
        max_concurrency=max_concurrency,
    )

    print(f"\n{'='*60}")
    print(f"Evaluation Complete!")
    print(f"{'='*60}\n")

    # Print summary
    print("Results Summary:")
    print(f"  View detailed results at: https://smith.langchain.com/")
    print()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run LangSmith evaluations for aviation agent"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="issue-8-baseline",
        help="Dataset name in LangSmith",
    )
    parser.add_argument(
        "--create-dataset",
        action="store_true",
        help="Create/recreate the dataset before running evaluation",
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Filter test cases by category (geographic_search, smart_filtering, regulatory, complex)",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        default="aviation-agent-eval",
        help="Experiment name prefix",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Maximum concurrent evaluations (default: 1 for sequential)",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="List available test case categories",
    )

    args = parser.parse_args()

    # Check for required environment variables
    if not os.getenv("LANGCHAIN_API_KEY"):
        print("ERROR: LANGCHAIN_API_KEY environment variable not set")
        print("Please set it in your .env file or environment")
        sys.exit(1)

    # List categories
    if args.list_categories:
        categories = set(tc["category"] for tc in ALL_TEST_CASES)
        print("Available test case categories:")
        for cat in sorted(categories):
            count = len(get_test_cases_by_category(cat))
            print(f"  - {cat}: {count} test cases")
        sys.exit(0)

    # Get test cases
    if args.category:
        test_cases = get_test_cases_by_category(args.category)
        if not test_cases:
            print(f"ERROR: No test cases found for category '{args.category}'")
            sys.exit(1)
        print(f"Using {len(test_cases)} test cases from category '{args.category}'")
    else:
        test_cases = ALL_TEST_CASES
        print(f"Using all {len(test_cases)} test cases")

    # Create dataset if requested
    if args.create_dataset:
        create_langsmith_dataset(args.dataset, test_cases)

    # Run evaluation
    run_evaluation_suite(
        dataset_name=args.dataset,
        experiment_prefix=args.experiment,
        max_concurrency=args.concurrency,
    )


if __name__ == "__main__":
    main()
