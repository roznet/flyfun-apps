from __future__ import annotations

import json
from typing import Any, Dict, Iterable

from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableLambda

from .planning import AviationPlan


def build_formatter_runnable(llm: Runnable) -> Runnable:
    """
    Return a runnable that converts planner/tool output into the final answer + UI payload.
    """

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are an aviation assistant. Use the tool findings to answer the pilot's question.\n"
                    "Always cite operational caveats when data may be outdated. Prefer concise Markdown."
                ),
            ),
            MessagesPlaceholder(variable_name="messages"),
            (
                "human",
                (
                    "Planner requested style: {answer_style}\n"
                    "Tool result summary (JSON):\n{tool_result_json}\n"
                    "Pretty text (if available):\n{pretty_text}\n\n"
                    "Produce the final pilot-facing response in Markdown."
                ),
            ),
        ]
    )

    chain = prompt | llm | StrOutputParser()

    def _invoke(payload: Dict[str, Any]) -> Dict[str, Any]:
        plan: AviationPlan = payload["plan"]
        tool_result = payload.get("tool_result") or {}
        final_answer = chain.invoke(
            {
                "messages": payload["messages"],
                "answer_style": plan.answer_style,
                "tool_result_json": json.dumps(tool_result, indent=2, ensure_ascii=False),
                "pretty_text": tool_result.get("pretty", ""),
            }
        )
        ui_payload = build_ui_payload(plan, tool_result)
        return {
            "final_answer": final_answer.strip(),
            "ui_payload": ui_payload,
        }

    return RunnableLambda(_invoke)


def build_ui_payload(plan: AviationPlan, tool_result: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """
    Build UI payload using hybrid approach:
    - Flatten commonly-used fields (filters, visualization, airports) for convenience
    - Keep mcp_raw for everything else and as authoritative source
    """
    if not tool_result:
        return None

    # Determine kind based on tool
    kind = _determine_kind(plan.selected_tool)
    if not kind:
        return None

    # Base payload with kind and mcp_raw (authoritative source)
    base_payload: Dict[str, Any] = {
        "kind": kind,
        "mcp_raw": tool_result,
    }

    # Add kind-specific metadata
    if plan.selected_tool in {"search_airports", "find_airports_near_route", "find_airports_near_location"}:
        base_payload["departure"] = plan.arguments.get("from_icao") or plan.arguments.get("departure")
        base_payload["destination"] = plan.arguments.get("to_icao") or plan.arguments.get("destination")
        if plan.arguments.get("ifr") is not None:
            base_payload["ifr"] = plan.arguments.get("ifr")

    elif plan.selected_tool in {
        "get_airport_details",
        "get_border_crossing_airports",
        "get_airport_statistics",
        "get_airport_pricing",
        "get_pilot_reviews",
        "get_fuel_prices",
    }:
        base_payload["icao"] = plan.arguments.get("icao") or plan.arguments.get("icao_code")
        # For search_airports, also extract icao from first airport if available
        if plan.selected_tool == "search_airports" and tool_result.get("airports"):
            airports = tool_result.get("airports", [])
            if airports and isinstance(airports[0], dict):
                base_payload["icao"] = airports[0].get("ident") or base_payload.get("icao")

    elif plan.selected_tool in {
        "list_rules_for_country",
        "compare_rules_between_countries",
        "get_answers_for_questions",
        "list_rule_categories_and_tags",
        "list_rule_countries",
    }:
        base_payload["region"] = plan.arguments.get("region") or plan.arguments.get("country_code")
        base_payload["topic"] = plan.arguments.get("topic") or plan.arguments.get("category")

    # Flatten commonly-used fields for convenience (hybrid approach)
    # These are the fields UI accesses most frequently
    if "filter_profile" in tool_result:
        base_payload["filters"] = tool_result["filter_profile"]
    
    if "visualization" in tool_result:
        base_payload["visualization"] = tool_result["visualization"]
    
    if "airports" in tool_result:
        base_payload["airports"] = tool_result["airports"]

    return base_payload


def _determine_kind(tool_name: str) -> str | None:
    """Determine UI payload kind based on tool name."""
    if tool_name in {"search_airports", "find_airports_near_route", "find_airports_near_location"}:
        return "route"
    
    if tool_name in {
        "get_airport_details",
        "get_border_crossing_airports",
        "get_airport_statistics",
        "get_airport_pricing",
        "get_pilot_reviews",
        "get_fuel_prices",
    }:
        return "airport"
    
    if tool_name in {
        "list_rules_for_country",
        "compare_rules_between_countries",
        "get_answers_for_questions",
        "list_rule_categories_and_tags",
        "list_rule_countries",
    }:
        return "rules"
    
    return None

