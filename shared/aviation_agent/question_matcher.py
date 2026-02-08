"""
LLM-based question matcher for aviation rules.

Instead of vector similarity (RAG), sends the full question list to an LLM
which picks semantically relevant questions. With ~58 questions per country,
the full list fits easily in a single LLM call and handles paraphrased queries
far better than embedding similarity.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default prompt path relative to configs/aviation_agent/
_DEFAULT_PROMPT_PATH = "prompts/question_matcher_v1.md"


class QuestionMatcher:
    """
    Uses an LLM to match a user query against a list of known questions.

    Follows the same lazy-init pattern as QueryReformulator in rules_rag.py.
    """

    def __init__(self, llm: Optional[Any] = None, prompt_text: Optional[str] = None):
        """
        Initialize question matcher.

        Args:
            llm: Optional LLM instance. If None, initialized lazily from config.
            prompt_text: Optional system prompt. If None, loaded from default file.
        """
        self.llm = llm
        self.prompt_text = prompt_text
        self._initialized = False

    def _ensure_llm(self):
        """Lazy initialization of LLM."""
        if self._initialized:
            return

        if self.llm is None:
            try:
                from langchain_openai import ChatOpenAI

                try:
                    from .config import get_settings, get_behavior_config

                    settings = get_settings()
                    behavior_config = get_behavior_config(settings.agent_config_name)
                    # Use rules model, fall back to formatter, then default
                    rules_llm = behavior_config.llms.rules
                    if rules_llm and rules_llm.model:
                        model = rules_llm.model
                        temperature = rules_llm.temperature
                    else:
                        model = (
                            behavior_config.llms.formatter.model
                            or behavior_config.llms.planner.model
                            or "gpt-4o-mini"
                        )
                        temperature = behavior_config.llms.formatter.temperature
                except Exception:
                    model = "gpt-4o-mini"
                    temperature = 0.0

                self.llm = ChatOpenAI(model=model, temperature=temperature)
                logger.debug(f"Initialized question matcher LLM: {model}")
            except ImportError:
                logger.warning(
                    "Question matching requires langchain-openai. "
                    "Proceeding without LLM matching."
                )
                self.llm = None

        if self.prompt_text is None:
            self.prompt_text = self._load_prompt()

        self._initialized = True

    def _load_prompt(self) -> str:
        """Load prompt from config file, with inline fallback."""
        try:
            from .config import get_settings, get_behavior_config

            settings = get_settings()
            behavior_config = get_behavior_config(settings.agent_config_name)
            if behavior_config._config_dir:
                prompt_path = behavior_config._config_dir / _DEFAULT_PROMPT_PATH
                if prompt_path.exists():
                    return prompt_path.read_text(encoding="utf-8")
        except Exception:
            pass

        # Try relative to this file's typical config location
        config_dir = Path(__file__).resolve().parents[2] / "configs" / "aviation_agent"
        prompt_path = config_dir / _DEFAULT_PROMPT_PATH
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")

        # Inline fallback
        return (
            "You are a question-matching assistant. Given a user query and a numbered list of "
            "database questions, return a JSON array of matching question numbers (integers). "
            "Return [] if no questions match. Return ONLY the JSON array."
        )

    def match_questions(
        self,
        query: str,
        questions: List[Dict[str, Any]],
        max_matches: int = 5,
    ) -> List[str]:
        """
        Match a user query against a list of known questions using an LLM.

        Args:
            query: The user's natural language question.
            questions: List of rule dicts, each with at least 'question_id' and 'question_text'.
            max_matches: Maximum number of question IDs to return.

        Returns:
            List of matched question_id strings, or empty list if none match.
        """
        self._ensure_llm()

        if self.llm is None:
            logger.debug("No LLM available for question matching")
            return []

        if not questions:
            return []

        # Deduplicate questions by question_id (country rules repeat across entries)
        seen = set()
        unique_questions = []
        for q in questions:
            qid = q.get("question_id", "")
            if qid and qid not in seen:
                seen.add(qid)
                unique_questions.append(q)

        # Use short numeric IDs for the LLM prompt, since real question_ids
        # can be full-length question text strings that the LLM can't reliably reproduce
        idx_to_qid = {}
        question_lines = []
        for i, q in enumerate(unique_questions, 1):
            qid = q.get("question_id", "")
            text = q.get("question_text", "")
            category = q.get("category", "")
            idx_to_qid[i] = qid
            question_lines.append(f"{i}. [{category}] {text}")

        question_list = "\n".join(question_lines)
        valid_nums = set(idx_to_qid.keys())

        user_message = (
            f"Pilot's question: {query}\n\n"
            f"Database questions ({len(unique_questions)} total):\n"
            f"{question_list}\n\n"
            f"Return up to {max_matches} matching question numbers as a JSON array of integers."
        )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=self.prompt_text or ""),
                HumanMessage(content=user_message),
            ]
            response = self.llm.invoke(messages)
            content = response.content.strip()

            # Parse JSON array of integers from response, map back to question_ids
            matched_nums = self._parse_response(content, valid_nums)
            matched_ids = [idx_to_qid[n] for n in matched_nums if n in idx_to_qid]
            logger.debug(
                f"Question matcher: '{query}' → {len(matched_ids)} matches "
                f"(nums={matched_nums})"
            )
            return matched_ids[:max_matches]

        except Exception as e:
            logger.warning(f"Question matching failed: {e}")
            return []

    @staticmethod
    def _parse_response(content: str, valid_nums: set) -> List[int]:
        """Parse LLM response into a list of valid question numbers."""
        # Handle markdown code fences
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return [int(n) for n in result if _is_valid_num(n, valid_nums)]
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: find a JSON array anywhere in the text
        import re

        match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return [int(n) for n in result if _is_valid_num(n, valid_nums)]
            except (json.JSONDecodeError, ValueError):
                pass

        logger.warning(f"Could not parse question matcher response: {content[:200]}")
        return []


def _is_valid_num(n, valid_nums: set) -> bool:
    """Check if a value is a valid question number."""
    try:
        return int(n) in valid_nums
    except (TypeError, ValueError):
        return False
