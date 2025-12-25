"""
Behavioral tests for the aviation agent planner.

These tests verify that the planner correctly selects tools and extracts arguments
from natural language questions. They require a live LLM and should be run selectively.

Run with:
    pytest -m planner_behavior                    # Run all behavioral tests
    pytest -m planner_behavior -v                 # Verbose output
    pytest -m "not planner_behavior"              # Skip behavioral tests (default)

Or set environment variable:
    RUN_PLANNER_BEHAVIOR_TESTS=1 pytest tests/aviation_agent/test_planner_behavior.py
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from shared.aviation_agent.planning import build_planner_runnable
from shared.aviation_agent.tools import AviationToolClient


# Global list to collect test results for CSV export
_test_results: list[Dict[str, Any]] = []


def _load_test_cases() -> list[Dict[str, Any]]:
    """Load test cases from JSON fixture file."""
    fixture_path = Path(__file__).parent / "fixtures" / "planner_test_cases.json"
    with open(fixture_path) as f:
        all_cases = json.load(f)
    # Filter out comment-only entries (those without a "question" field)
    return [tc for tc in all_cases if "question" in tc]


def _should_run_behavior_tests() -> bool:
    """Check if behavioral tests should run (require explicit opt-in)."""
    return os.getenv("RUN_PLANNER_BEHAVIOR_TESTS") == "1"


@pytest.fixture(scope="session")
def live_planner_llm():
    """Create a live LLM for planner tests (only if explicitly enabled)."""
    if not _should_run_behavior_tests():
        pytest.skip("Behavioral tests require RUN_PLANNER_BEHAVIOR_TESTS=1")

    model = os.getenv("AVIATION_AGENT_PLANNER_MODEL", "gpt-4o-mini")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    return ChatOpenAI(model=model, temperature=0, api_key=api_key)


@pytest.fixture(scope="session")
def behavior_tool_client(agent_settings):
    """Tool client for behavioral tests."""
    from shared.aviation_agent.tools import AviationToolClient
    return AviationToolClient(agent_settings.build_tool_context())


def _save_results_to_csv():
    """Save collected test results to CSV file."""
    if not _test_results:
        return

    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"planner_test_results_{timestamp}.csv"

    fieldnames = [
        "test_case", "question", "description", "status",
        "expected_tool", "actual_tool", "tool_match",
        "expected_args", "actual_args", "args_match"
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_test_results)

    print(f"\n{'='*60}")
    print(f"Results saved to: {csv_path}")
    print(f"{'='*60}")


@pytest.fixture(scope="session", autouse=True)
def save_csv_on_finish(request):
    """Fixture to save CSV results after all tests complete."""
    yield
    if _should_run_behavior_tests():
        _save_results_to_csv()


@pytest.mark.planner_behavior
@pytest.mark.parametrize("test_case", _load_test_cases(), ids=lambda tc: tc.get("question", "")[:40])
def test_planner_selects_correct_tool(
    test_case: Dict[str, Any],
    live_planner_llm,
    behavior_tool_client: AviationToolClient,
):
    """
    Test that planner selects the expected tool for a given question.

    This is a behavioral/integration test that requires a live LLM.
    """
    question = test_case["question"]
    expected_tool_raw = test_case["expected_tool"]
    expected_args_raw = test_case.get("expected_arguments", {})
    description = test_case.get("description", "")

    # Normalize to lists for multiple valid choices
    # expected_tool can be string or array, expected_arguments must match
    if isinstance(expected_tool_raw, list):
        expected_tools = expected_tool_raw
        expected_args_list = expected_args_raw  # Should be array of same size
    else:
        expected_tools = [expected_tool_raw]
        expected_args_list = [expected_args_raw]

    # Get available tags from rules manager for dynamic prompt injection
    available_tags = None
    if behavior_tool_client._context.rules_manager:
        available_tags = behavior_tool_client._context.rules_manager.get_available_tags()

    # Build planner with live LLM
    planner = build_planner_runnable(
        live_planner_llm,
        tuple(behavior_tool_client.tools.values()),
        available_tags=available_tags,
    )

    # Run planner
    messages = [HumanMessage(content=question)]
    plan = planner.invoke({"messages": messages})

    # Determine if tool matches any valid option
    plan_args = plan.arguments or {}
    tool_match = False
    matched_index = -1
    for i, valid_tool in enumerate(expected_tools):
        if plan.selected_tool == valid_tool:
            tool_match = True
            matched_index = i
            break

    # Check args match for the matched tool (or first if no match)
    expected_args = expected_args_list[matched_index] if matched_index >= 0 else expected_args_list[0]
    args_match = True
    for key, expected_value in expected_args.items():
        if key not in plan_args:
            args_match = False
            break
        if isinstance(expected_value, dict):
            plan_value = plan_args.get(key, {})
            for nested_key, nested_value in expected_value.items():
                if nested_key not in plan_value or plan_value[nested_key] != nested_value:
                    args_match = False
                    break

    # Collect result for CSV
    test_case_num = len(_test_results)
    _test_results.append({
        "test_case": test_case_num,
        "question": question,
        "description": description,
        "status": "PASS" if (tool_match and args_match) else "FAIL",
        "expected_tool": json.dumps(expected_tools),
        "actual_tool": plan.selected_tool,
        "tool_match": "YES" if tool_match else "NO",
        "expected_args": json.dumps(expected_args),
        "actual_args": json.dumps(plan.arguments),
        "args_match": "YES" if args_match else "NO",
    })

    # Print actual results for visibility
    print(f"\n{'='*60}")
    print(f"Question: {question}")
    print(f"Expected Tool(s): {expected_tools}")
    print(f"Actual Tool:      {plan.selected_tool}")
    print(f"Expected Args: {json.dumps(expected_args, indent=2)}")
    print(f"Actual Args:   {json.dumps(plan.arguments, indent=2)}")
    print(f"{'='*60}")

    # Assertions
    assert plan.selected_tool in expected_tools, (
        f"Expected one of {expected_tools} but got '{plan.selected_tool}'. "
        f"Description: {description}"
    )

    # Check that expected arguments are present (allowing extra args)
    for key, expected_value in expected_args.items():
        assert key in plan_args, (
            f"Expected argument '{key}' not found in plan.arguments. "
            f"Got: {plan_args}"
        )

        if isinstance(expected_value, dict):
            # For nested dicts (like filters), check that expected keys exist
            plan_value = plan_args.get(key, {})
            for nested_key, nested_value in expected_value.items():
                assert nested_key in plan_value, (
                    f"Expected nested argument '{key}.{nested_key}' not found. "
                    f"Got: {plan_value}"
                )
                assert plan_value[nested_key] == nested_value, (
                    f"Expected '{key}.{nested_key}' = {nested_value}, "
                    f"got {plan_value[nested_key]}"
                )
        else:
            # For simple values, check match
            plan_value = plan_args[key]
            if isinstance(expected_value, str) and isinstance(plan_value, str):
                # For location fields, allow country disambiguation suffix
                # e.g., "Paris" matches "Paris, France", "Bromley" matches "Bromley, UK"
                location_fields = {"from_location", "to_location", "location_query"}
                if key in location_fields:
                    # Accept if actual starts with expected (case-insensitive)
                    # This allows "Paris, France" to match expected "Paris"
                    assert plan_value.upper().startswith(expected_value.upper()), (
                        f"Expected '{key}' to start with '{expected_value}', "
                        f"got '{plan_value}'"
                    )
                else:
                    # Exact match (case-insensitive) for other string fields
                    assert plan_value.upper() == expected_value.upper(), (
                        f"Expected '{key}' = '{expected_value}' (case-insensitive), "
                        f"got '{plan_value}'"
                    )
            elif key == "tags" and isinstance(expected_value, list) and isinstance(plan_value, list):
                # For tags, require exact match (order-independent)
                # This ensures we notice when planner starts returning extra/different tags
                expected_set = set(expected_value)
                actual_set = set(plan_value)

                missing_tags = expected_set - actual_set
                extra_tags = actual_set - expected_set

                if missing_tags:
                    assert False, (
                        f"Missing tags for question: \"{question[:60]}...\"\n"
                        f"  Missing: {sorted(missing_tags)}\n"
                        f"  Expected: {sorted(expected_set)}\n"
                        f"  Actual:   {sorted(actual_set)}"
                    )

                if extra_tags:
                    assert False, (
                        f"New tags appeared for question: \"{question[:60]}...\"\n"
                        f"  Extra tags: {sorted(extra_tags)}\n"
                        f"  Expected:   {sorted(expected_set)}\n"
                        f"  Actual:     {sorted(actual_set)}\n\n"
                        f"  → Should we expand the expectation to include {sorted(extra_tags)}?\n"
                        f"  → If yes, update the test fixture. If no, check why planner added these tags."
                    )
            else:
                assert plan_value == expected_value, (
                    f"Expected '{key}' = {expected_value}, got {plan_value}"
                )
