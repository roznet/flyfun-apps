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

import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from shared.aviation_agent.planning import build_planner_runnable
from shared.aviation_agent.tools import AviationToolClient


def _load_test_cases() -> list[Dict[str, Any]]:
    """Load test cases from JSON fixture file."""
    fixture_path = Path(__file__).parent / "fixtures" / "planner_test_cases.json"
    with open(fixture_path) as f:
        return json.load(f)


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


@pytest.mark.planner_behavior
@pytest.mark.parametrize("test_case", _load_test_cases())
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
    expected_tool = test_case["expected_tool"]
    expected_args = test_case.get("expected_arguments", {})
    description = test_case.get("description", "")
    
    # Build planner with live LLM
    planner = build_planner_runnable(
        live_planner_llm,
        tuple(behavior_tool_client.tools.values())
    )
    
    # Run planner
    messages = [HumanMessage(content=question)]
    plan = planner.invoke({"messages": messages})
    
    # Assertions
    assert plan.selected_tool == expected_tool, (
        f"Expected tool '{expected_tool}' but got '{plan.selected_tool}'. "
        f"Description: {description}"
    )
    
    # Check that expected arguments are present (allowing extra args)
    plan_args = plan.arguments or {}
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
            # For simple values, check exact match (case-insensitive for strings)
            plan_value = plan_args[key]
            if isinstance(expected_value, str) and isinstance(plan_value, str):
                assert plan_value.upper() == expected_value.upper(), (
                    f"Expected '{key}' = '{expected_value}' (case-insensitive), "
                    f"got '{plan_value}'"
                )
            else:
                assert plan_value == expected_value, (
                    f"Expected '{key}' = {expected_value}, got {plan_value}"
                )

