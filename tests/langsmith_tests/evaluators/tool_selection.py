"""
Tool Selection Evaluator

Checks if the aviation agent planner selected the correct tool for a given query.
"""

from typing import Dict, Any, Optional


def evaluate_tool_selection(run: Any, example: Any) -> Dict[str, Any]:
    """
    Evaluate if the planner selected the expected tool.

    Args:
        run: LangSmith run object containing the agent execution
        example: Test case example with expected tool

    Returns:
        Evaluation result with score and feedback
    """
    try:
        # Extract actual tool from run outputs
        # The plan object should be in the state
        outputs = run.outputs or {}
        plan = outputs.get("plan")

        if not plan:
            return {
                "key": "tool_selection",
                "score": 0.0,
                "comment": "No plan found in outputs - planner may have failed"
            }

        actual_tool = plan.get("selected_tool") if isinstance(plan, dict) else getattr(plan, "selected_tool", None)

        # Get expected tool from test case
        expected = example.outputs.get("expected", {})
        expected_tool = expected.get("tool")

        if not expected_tool:
            return {
                "key": "tool_selection",
                "score": None,
                "comment": "No expected tool defined for this test case"
            }

        # Compare tools
        is_correct = actual_tool == expected_tool

        return {
            "key": "tool_selection",
            "score": 1.0 if is_correct else 0.0,
            "comment": f"Expected '{expected_tool}', got '{actual_tool}'" +
                      (" ✓" if is_correct else " ✗")
        }

    except Exception as e:
        return {
            "key": "tool_selection",
            "score": 0.0,
            "comment": f"Evaluation error: {str(e)}"
        }


def evaluate_tool_execution(run: Any, example: Any) -> Dict[str, Any]:
    """
    Evaluate if the tool executed successfully without errors.

    Args:
        run: LangSmith run object
        example: Test case example

    Returns:
        Evaluation result
    """
    try:
        outputs = run.outputs or {}

        # Check for errors in the state
        error = outputs.get("error")
        tool_result = outputs.get("tool_result")

        if error:
            return {
                "key": "tool_execution",
                "score": 0.0,
                "comment": f"Tool execution failed: {error}"
            }

        if not tool_result:
            return {
                "key": "tool_execution",
                "score": 0.0,
                "comment": "No tool result found"
            }

        # Check if tool returned results
        has_results = False
        if isinstance(tool_result, dict):
            has_results = bool(tool_result.get("airports") or tool_result.get("routes") or tool_result.get("borders"))

        return {
            "key": "tool_execution",
            "score": 1.0 if has_results else 0.5,
            "comment": "Tool executed successfully" + (" with results" if has_results else " but no results found")
        }

    except Exception as e:
        return {
            "key": "tool_execution",
            "score": 0.0,
            "comment": f"Evaluation error: {str(e)}"
        }
