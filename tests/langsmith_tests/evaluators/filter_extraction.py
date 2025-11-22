"""
Filter Extraction Evaluator

Checks if the aviation agent correctly extracted filters from natural language queries.
"""

from typing import Dict, Any, Set


def normalize_filter_value(value: Any) -> Any:
    """Normalize filter values for comparison"""
    if isinstance(value, str):
        return value.strip().upper()
    return value


def evaluate_filter_extraction(run: Any, example: Any) -> Dict[str, Any]:
    """
    Evaluate if the planner correctly extracted filters from the user query.

    Args:
        run: LangSmith run object
        example: Test case with expected filters

    Returns:
        Evaluation result with score and feedback
    """
    try:
        # Extract actual filters from plan
        outputs = run.outputs or {}
        plan = outputs.get("plan")

        if not plan:
            return {
                "key": "filter_extraction",
                "score": 0.0,
                "comment": "No plan found"
            }

        actual_args = plan.get("arguments", {}) if isinstance(plan, dict) else getattr(plan, "arguments", {})
        actual_filters = actual_args.get("filters", {})

        # Get expected filters
        expected = example.outputs.get("expected", {})
        expected_filters = expected.get("filters", {})

        if not expected_filters:
            return {
                "key": "filter_extraction",
                "score": None,
                "comment": "No expected filters defined for this test case"
            }

        # Compare filters
        missing_filters = []
        incorrect_filters = []
        correct_count = 0

        for key, expected_value in expected_filters.items():
            if key not in actual_filters:
                missing_filters.append(key)
            else:
                actual_value = actual_filters[key]
                # Normalize for comparison (case-insensitive for strings)
                if normalize_filter_value(actual_value) == normalize_filter_value(expected_value):
                    correct_count += 1
                else:
                    incorrect_filters.append(f"{key}: expected {expected_value}, got {actual_value}")

        total_expected = len(expected_filters)
        score = correct_count / total_expected if total_expected > 0 else 0.0

        # Build feedback comment
        comments = []
        if correct_count > 0:
            comments.append(f"{correct_count}/{total_expected} filters correct")
        if missing_filters:
            comments.append(f"Missing: {', '.join(missing_filters)}")
        if incorrect_filters:
            comments.append(f"Incorrect: {'; '.join(incorrect_filters)}")

        return {
            "key": "filter_extraction",
            "score": score,
            "comment": " | ".join(comments) if comments else "All filters correct ✓"
        }

    except Exception as e:
        return {
            "key": "filter_extraction",
            "score": 0.0,
            "comment": f"Evaluation error: {str(e)}"
        }


def evaluate_filter_completeness(run: Any, example: Any) -> Dict[str, Any]:
    """
    Check if all relevant information from the query was captured in filters.

    This is a stricter check - we want to ensure nothing important was missed.
    """
    try:
        outputs = run.outputs or {}
        plan = outputs.get("plan")

        if not plan:
            return {"key": "filter_completeness", "score": 0.0, "comment": "No plan"}

        actual_args = plan.get("arguments", {}) if isinstance(plan, dict) else getattr(plan, "arguments", {})
        actual_filters = actual_args.get("filters", {})

        expected = example.outputs.get("expected", {})
        expected_filters = expected.get("filters", {})

        # Check for any extra unexpected filters (could be good or bad)
        extra_filters = set(actual_filters.keys()) - set(expected_filters.keys())

        if not expected_filters:
            return {"key": "filter_completeness", "score": None, "comment": "No expected filters"}

        # Score based on having all required filters
        has_all = all(key in actual_filters for key in expected_filters.keys())

        comment = "Complete ✓" if has_all else "Missing some filters"
        if extra_filters:
            comment += f" (Extra filters: {', '.join(extra_filters)})"

        return {
            "key": "filter_completeness",
            "score": 1.0 if has_all else 0.0,
            "comment": comment
        }

    except Exception as e:
        return {
            "key": "filter_completeness",
            "score": 0.0,
            "comment": f"Error: {str(e)}"
        }
