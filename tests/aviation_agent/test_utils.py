"""
Shared test utilities for aviation agent planner tests.

Provides reusable functions for loading test cases, validating planner arguments,
and normalizing expected values. Used by both test_planner_behavior.py and tools/ab_test.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_test_cases(fixture_path: Path | None = None) -> List[Dict[str, Any]]:
    """
    Load planner test cases from JSON fixture file.

    Args:
        fixture_path: Path to fixture file. Defaults to fixtures/planner_test_cases.json
                      relative to this module.

    Returns:
        List of test case dicts (comment-only entries filtered out).
    """
    if fixture_path is None:
        fixture_path = Path(__file__).parent / "fixtures" / "planner_test_cases.json"
    with open(fixture_path) as f:
        all_cases = json.load(f)
    return [tc for tc in all_cases if "question" in tc]


def normalize_expected(test_case: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Normalize expected_tool and expected_arguments to lists.

    Some test cases allow multiple valid tools (list form). This function
    normalizes both scalar and list forms into parallel lists.

    Returns:
        (expected_tools, expected_args_list) - parallel lists of the same length.
    """
    expected_tool_raw = test_case["expected_tool"]
    expected_args_raw = test_case.get("expected_arguments", {})

    if isinstance(expected_tool_raw, list):
        return expected_tool_raw, expected_args_raw
    return [expected_tool_raw], [expected_args_raw]


def validate_arguments(
    plan_args: Dict[str, Any],
    expected_args: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Validate that plan arguments match expected arguments.

    Applies flexible matching rules:
    - Location fields (from_location, to_location, location_query): prefix match
    - aircraft_type: normalized comparison via shared.aircraft_speeds
    - question: non-empty check (planner can reformulate)
    - tags: set equality (order-independent)
    - Nested dicts (filters): recursive key/value match
    - Other strings: case-insensitive exact match

    Args:
        plan_args: Actual arguments from planner output.
        expected_args: Expected arguments from test case.

    Returns:
        (matches, reason) - True if all expected args match, with reason if not.
    """
    for key, expected_value in expected_args.items():
        if key not in plan_args:
            return False, f"Missing argument '{key}'"

        plan_value = plan_args[key]

        if isinstance(expected_value, dict):
            # Nested dict (e.g., filters) - check each key/value
            for nested_key, nested_value in expected_value.items():
                if nested_key not in plan_value:
                    return False, f"Missing nested argument '{key}.{nested_key}'"
                if plan_value[nested_key] != nested_value:
                    return False, f"'{key}.{nested_key}': expected {nested_value}, got {plan_value[nested_key]}"

        elif isinstance(expected_value, str) and isinstance(plan_value, str):
            if key == "question":
                if not plan_value:
                    return False, "Empty 'question' field"
            elif key in {"from_location", "to_location", "location_query"}:
                if not plan_value.upper().startswith(expected_value.upper()):
                    return False, f"'{key}': expected prefix '{expected_value}', got '{plan_value}'"
            elif key == "aircraft_type":
                try:
                    from shared.aircraft_speeds import normalize_aircraft_type
                    if normalize_aircraft_type(expected_value) != normalize_aircraft_type(plan_value):
                        return False, f"'{key}': '{expected_value}' != '{plan_value}' (normalized)"
                except ImportError:
                    if plan_value.upper() != expected_value.upper():
                        return False, f"'{key}': '{expected_value}' != '{plan_value}'"
            else:
                if plan_value.upper() != expected_value.upper():
                    return False, f"'{key}': expected '{expected_value}', got '{plan_value}'"

        elif key == "tags" and isinstance(expected_value, list) and isinstance(plan_value, list):
            expected_set = set(expected_value)
            actual_set = set(plan_value)
            if expected_set != actual_set:
                missing = expected_set - actual_set
                extra = actual_set - expected_set
                parts = []
                if missing:
                    parts.append(f"missing={sorted(missing)}")
                if extra:
                    parts.append(f"extra={sorted(extra)}")
                return False, f"tags mismatch: {', '.join(parts)}"
        else:
            if plan_value != expected_value:
                return False, f"'{key}': expected {expected_value}, got {plan_value}"

    return True, ""


def match_tool_and_args(
    selected_tool: str,
    plan_args: Dict[str, Any],
    expected_tools: List[str],
    expected_args_list: List[Dict[str, Any]],
) -> Tuple[bool, bool, str]:
    """
    Check if the selected tool matches any expected tool, and validate args.

    Returns:
        (tool_match, args_match, reason) - reason is empty string if both match.
    """
    matched_index = -1
    for i, valid_tool in enumerate(expected_tools):
        if selected_tool == valid_tool:
            matched_index = i
            break

    tool_match = matched_index >= 0

    # Use matched tool's args, or first tool's args as fallback
    expected_args = expected_args_list[matched_index] if tool_match else expected_args_list[0]
    args_match, reason = validate_arguments(plan_args or {}, expected_args)

    if not tool_match:
        reason = f"Tool mismatch: expected {expected_tools}, got '{selected_tool}'"

    return tool_match, args_match, reason
