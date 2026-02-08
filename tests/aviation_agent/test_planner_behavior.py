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

from shared.aviation_agent.adapters.langgraph_runner import _resolve_llm
from shared.aviation_agent.planning import build_planner_runnable
from shared.aviation_agent.tools import AviationToolClient
from tests.aviation_agent.test_utils import load_test_cases, normalize_expected, match_tool_and_args


# Global list to collect test results for CSV export
_test_results: list[Dict[str, Any]] = []


def _should_run_behavior_tests() -> bool:
    """Check if behavioral tests should run (require explicit opt-in)."""
    return os.getenv("RUN_PLANNER_BEHAVIOR_TESTS") == "1"


@pytest.fixture(scope="session")
def live_planner_llm():
    """Create a live LLM for planner tests (only if explicitly enabled)."""
    if not _should_run_behavior_tests():
        pytest.skip("Behavioral tests require RUN_PLANNER_BEHAVIOR_TESTS=1")

    from shared.aviation_agent.config import get_behavior_config
    config_name = os.getenv("AVIATION_AGENT_CONFIG", "default")
    behavior_config = get_behavior_config(config_name)

    return _resolve_llm(
        None,
        behavior_config.llms.planner.model,
        role="planner",
        provider=behavior_config.llms.planner.provider,
        temperature=behavior_config.llms.planner.temperature,
    )


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
@pytest.mark.parametrize("test_case", load_test_cases(), ids=lambda tc: tc.get("question", "")[:40])
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
    description = test_case.get("description", "")
    expected_tools, expected_args_list = normalize_expected(test_case)

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

    # Validate using shared utilities
    tool_match, args_match, reason = match_tool_and_args(
        plan.selected_tool, plan.arguments or {}, expected_tools, expected_args_list,
    )

    # Determine expected_args for CSV (use matched tool's args or first)
    matched_index = next(
        (i for i, t in enumerate(expected_tools) if t == plan.selected_tool), 0
    )
    expected_args = expected_args_list[matched_index]

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
    assert tool_match and args_match, (
        f"FAIL: {reason}\n"
        f"Description: {description}\n"
        f"Expected tool(s): {expected_tools}, got: '{plan.selected_tool}'\n"
        f"Expected args: {json.dumps(expected_args)}\n"
        f"Actual args:   {json.dumps(plan.arguments)}"
    )
