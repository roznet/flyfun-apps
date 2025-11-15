#!/usr/bin/env python3
"""
Core orchestration primitives for the chatbot service.
Extracted to enable deterministic service-level testing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)


class LLMCompletionCallable(Protocol):
    """Callable that wraps an LLM completion API."""

    def __call__(self, **kwargs) -> Any:
        ...


class ToolExecutor(Protocol):
    """Callable interface for executing MCP tools (or fakes in tests)."""

    def __call__(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


ThinkingExtractor = Callable[[str], Tuple[str, str]]
ToolFormatter = Callable[[str, Dict[str, Any], Dict[str, Any]], str]


@dataclass
class RunConversationResult:
    messages: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    visualizations: List[Any] = field(default_factory=list)
    thinking: str = ""
    final_message: str = ""


def run_conversation(
    *,
    messages: List[Dict[str, Any]],
    llm_call: LLMCompletionCallable,
    tool_executor: ToolExecutor,
    tools: Optional[List[Dict[str, Any]]],
    llm_model: str,
    max_completion_tokens: Optional[int],
    extract_thinking_and_answer: ThinkingExtractor,
    format_tool_response: ToolFormatter,
) -> RunConversationResult:
    """
    Execute the two-phase (LLM -> optional tools -> LLM) conversation loop.

    Args:
        messages: Conversation messages including system/history/user.
        llm_call: Callable that executes the LLM request (handles fallbacks).
        tool_executor: Callable that executes tool calls synchronously.
        tools: List of tool schemas advertised to the LLM.
        llm_model: Model identifier to pass to llm_call.
        max_completion_tokens: Optional token cap for completions.
        extract_thinking_and_answer: Function that splits LLM output.
        format_tool_response: Fallback formatter if LLM output is unusable.

    Returns:
        RunConversationResult containing final answer, thinking, tool metadata,
        visualizations, and updated message history.
    """

    token_budget = max_completion_tokens
    logger.debug("Starting conversation run with %d messages", len(messages))

    response = llm_call(
        model=llm_model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_completion_tokens=token_budget,
    )

    assistant_message = response.choices[0].message
    tool_calls_made: List[Dict[str, Any]] = []
    visualizations: List[Any] = []

    if getattr(assistant_message, "tool_calls", None):
        logger.info("LLM requested %d tool call(s)", len(assistant_message.tool_calls))

        messages.append({
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_message.tool_calls
            ],
        })

        for tool_call in assistant_message.tool_calls:
            function_name = tool_call.function.name
            raw_arguments = tool_call.function.arguments or "{}"
            function_args = json.loads(raw_arguments)

            logger.info("Executing tool '%s' with args %s", function_name, function_args)
            tool_result = tool_executor(function_name, function_args)

            tool_record = {
                "name": function_name,
                "arguments": function_args,
                "result": tool_result,
            }
            tool_calls_made.append(tool_record)

            if "visualization" in tool_result:
                visualizations.append(tool_result["visualization"])

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": json.dumps(tool_result),
            })

        final_response = llm_call(
            model=llm_model,
            messages=messages,
            max_completion_tokens=token_budget,
        )
        raw_content = final_response.choices[0].message.content or ""
    else:
        raw_content = assistant_message.content or ""

    thinking, final_message = extract_thinking_and_answer(raw_content)

    if (
        tool_calls_made
        and (
            not final_message
            or len(final_message) < 20
            or final_message.strip().startswith("{")
            or final_message.strip().startswith("[")
            or '"path"' in final_message
            or '"query"' in final_message
        )
    ):
        logger.warning("LLM response unusable; falling back to formatted tool output")
        first_tool = tool_calls_made[0]
        final_message = format_tool_response(
            first_tool["name"],
            first_tool["arguments"],
            first_tool["result"],
        )
        thinking = ""

    if not tool_calls_made:
        messages.append({"role": "assistant", "content": final_message})

    return RunConversationResult(
        messages=messages,
        tool_calls=tool_calls_made,
        visualizations=visualizations,
        thinking=thinking,
        final_message=final_message,
    )

