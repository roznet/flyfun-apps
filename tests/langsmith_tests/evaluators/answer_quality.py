"""
Answer Quality Evaluator

Evaluates the quality and completeness of the final formatted answer.
"""

from typing import Dict, Any, List
import re


def extract_icao_codes(text: str) -> List[str]:
    """Extract ICAO codes from text (4-letter codes starting with letter)"""
    # ICAO codes are 4 uppercase letters, starting with a letter
    pattern = r'\b[A-Z][A-Z0-9]{3}\b'
    return list(set(re.findall(pattern, text.upper())))


def evaluate_answer_mentions(run: Any, example: Any) -> Dict[str, Any]:
    """
    Check if the answer mentions expected keywords or ICAO codes.

    Args:
        run: LangSmith run object
        example: Test case with should_mention/should_include_icaos

    Returns:
        Evaluation result
    """
    try:
        outputs = run.outputs or {}
        final_answer = outputs.get("final_answer", "")

        if not final_answer:
            return {
                "key": "answer_mentions",
                "score": 0.0,
                "comment": "No final answer generated"
            }

        expected = example.outputs.get("expected", {})
        should_mention = expected.get("should_mention", [])
        should_include_icaos = expected.get("should_include_icaos", [])
        should_not_include = expected.get("should_not_include", [])

        if not should_mention and not should_include_icaos and not should_not_include:
            return {
                "key": "answer_mentions",
                "score": None,
                "comment": "No mention expectations defined"
            }

        # Check keyword mentions
        answer_lower = final_answer.lower()
        mentioned_keywords = [kw for kw in should_mention if kw.lower() in answer_lower]
        missing_keywords = [kw for kw in should_mention if kw.lower() not in answer_lower]

        # Check ICAO codes
        mentioned_icaos = extract_icao_codes(final_answer)
        expected_icaos_found = [icao for icao in should_include_icaos if icao in mentioned_icaos]
        expected_icaos_missing = [icao for icao in should_include_icaos if icao not in mentioned_icaos]

        # Check exclusions
        unwanted_icaos = [icao for icao in should_not_include if icao in mentioned_icaos]

        # Calculate score
        total_expected = len(should_mention) + len(should_include_icaos)
        total_found = len(mentioned_keywords) + len(expected_icaos_found)
        score = (total_found / total_expected) if total_expected > 0 else 1.0

        # Penalize for unwanted mentions
        if unwanted_icaos:
            score = max(0.0, score - 0.2 * len(unwanted_icaos))

        # Build comment
        comments = []
        if mentioned_keywords:
            comments.append(f"Keywords: {', '.join(mentioned_keywords)}")
        if missing_keywords:
            comments.append(f"Missing: {', '.join(missing_keywords)}")
        if expected_icaos_found:
            comments.append(f"ICAOs: {', '.join(expected_icaos_found)}")
        if expected_icaos_missing:
            comments.append(f"Missing ICAOs: {', '.join(expected_icaos_missing)}")
        if unwanted_icaos:
            comments.append(f"❌ Unwanted: {', '.join(unwanted_icaos)}")

        return {
            "key": "answer_mentions",
            "score": score,
            "comment": " | ".join(comments) if comments else "All mentions correct ✓"
        }

    except Exception as e:
        return {
            "key": "answer_mentions",
            "score": 0.0,
            "comment": f"Error: {str(e)}"
        }


def evaluate_answer_length(run: Any, example: Any) -> Dict[str, Any]:
    """
    Check if the answer has reasonable length (not too short, not too verbose).

    Args:
        run: LangSmith run object
        example: Test case

    Returns:
        Evaluation result
    """
    try:
        outputs = run.outputs or {}
        final_answer = outputs.get("final_answer", "")

        if not final_answer:
            return {
                "key": "answer_length",
                "score": 0.0,
                "comment": "No answer"
            }

        word_count = len(final_answer.split())

        # Scoring based on length
        if word_count < 10:
            score = 0.3
            comment = f"Too short ({word_count} words)"
        elif word_count > 500:
            score = 0.7
            comment = f"Too verbose ({word_count} words)"
        elif word_count < 30:
            score = 0.7
            comment = f"Brief ({word_count} words)"
        else:
            score = 1.0
            comment = f"Good length ({word_count} words)"

        return {
            "key": "answer_length",
            "score": score,
            "comment": comment
        }

    except Exception as e:
        return {
            "key": "answer_length",
            "score": 0.0,
            "comment": f"Error: {str(e)}"
        }


def evaluate_answer_format(run: Any, example: Any) -> Dict[str, Any]:
    """
    Check if the answer is properly formatted (markdown, structure).

    Args:
        run: LangSmith run object
        example: Test case

    Returns:
        Evaluation result
    """
    try:
        outputs = run.outputs or {}
        final_answer = outputs.get("final_answer", "")

        if not final_answer:
            return {"key": "answer_format", "score": 0.0, "comment": "No answer"}

        # Check for markdown formatting
        has_headers = bool(re.search(r'^#{1,3}\s', final_answer, re.MULTILINE))
        has_lists = bool(re.search(r'^\s*[-*]\s', final_answer, re.MULTILINE))
        has_bold = bool(re.search(r'\*\*\w+\*\*', final_answer))

        formatting_score = sum([has_headers, has_lists, has_bold]) / 3

        comments = []
        if has_headers:
            comments.append("Headers ✓")
        if has_lists:
            comments.append("Lists ✓")
        if has_bold:
            comments.append("Bold ✓")

        if not comments:
            comments.append("No markdown formatting")

        return {
            "key": "answer_format",
            "score": formatting_score,
            "comment": ", ".join(comments)
        }

    except Exception as e:
        return {
            "key": "answer_format",
            "score": 0.0,
            "comment": f"Error: {str(e)}"
        }
