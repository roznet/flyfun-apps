from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableLambda

from .planning import AviationPlan


def build_formatter_chain(llm: Runnable, system_prompt: Optional[str] = None) -> Runnable:
    """
    Return the LLM chain for formatting answers.
    
    This chain will be used directly in the formatter node so LangGraph can capture streaming.
    The node will handle state transformation and UI payload building.
    """
    # Load system prompt from config if not provided
    if system_prompt is None:
        from .config import get_settings, get_behavior_config
        settings = get_settings()
        behavior_config = get_behavior_config(settings.agent_config_name)
        system_prompt = behavior_config.load_prompt("formatter")
    
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                system_prompt,
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

    # Build chain - Use directly in node so LangGraph can capture streaming
    return prompt | llm | StrOutputParser()


def build_comparison_formatter_chain(llm: Runnable, system_prompt: str) -> Runnable:
    """
    Build a formatter chain for comparison tool results.

    Uses the comparison_synthesis prompt which expects:
    - countries: comma-separated list of countries being compared
    - topic_context: optional tag/category context
    - rules_context: pre-formatted rules differences

    This follows the design principle: tools return DATA, formatters do SYNTHESIS.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
    ])

    # Build chain - LangGraph can capture streaming
    return prompt | llm | StrOutputParser()


def build_formatter_runnable(llm: Runnable) -> Runnable:
    """
    Legacy wrapper for backward compatibility.
    Returns a runnable that transforms state to chain inputs.
    """
    chain = build_formatter_chain(llm)
    
    def _transform_state(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Transform AgentState to chain inputs."""
        plan: AviationPlan = payload["plan"]
        tool_result = payload.get("tool_result") or {}
        
        return {
            "messages": payload["messages"],
            "answer_style": plan.answer_style,
            "tool_result_json": json.dumps(tool_result, indent=2, ensure_ascii=False),
            "pretty_text": tool_result.get("pretty", ""),
        }
    
    # Return a chain that transforms state, then runs the LLM chain
    # This allows LangGraph to capture streaming from the LLM chain
    return RunnableLambda(_transform_state) | chain


def build_ui_payload(
    plan: AviationPlan,
    tool_result: Dict[str, Any] | None,
    suggested_queries: List[dict] | None = None
) -> Dict[str, Any] | None:
    """
    Build UI payload with flattened fields for convenient access.
    - Flatten commonly-used fields (filters, visualization, airports) for convenience
    - Include suggested_queries for next query prediction
    - Include kind-specific metadata (departure, destination, icao, region, topic)
    """
    if not tool_result:
        return None

    # Determine kind based on tool
    kind = _determine_kind(plan.selected_tool)
    if not kind:
        return None

    # Base payload with kind and tool name
    # Tool name enables frontend to derive context-aware behavior (e.g., legend mode)
    base_payload: Dict[str, Any] = {
        "kind": kind,
        "tool": plan.selected_tool,
    }

    # Add kind-specific metadata
    if plan.selected_tool in {
        "search_airports",
        "find_airports_near_route",
        "find_airports_near_location",
        "calculate_flight_distance",
    }:
        base_payload["departure"] = (
            plan.arguments.get("from_location") or
            plan.arguments.get("from_icao") or
            plan.arguments.get("departure")
        )
        base_payload["destination"] = (
            plan.arguments.get("to_location") or
            plan.arguments.get("to_icao") or
            plan.arguments.get("destination")
        )
        if plan.arguments.get("via"):
            base_payload["via"] = plan.arguments["via"]
        if plan.arguments.get("ifr") is not None:
            base_payload["ifr"] = plan.arguments.get("ifr")

    elif plan.selected_tool in {
        "get_airport_details",
        "get_notification_for_airport",
    }:
        base_payload["icao"] = plan.arguments.get("icao") or plan.arguments.get("icao_code")

    elif plan.selected_tool in {
        "answer_rules_question",
        "browse_rules",
        "compare_rules_between_countries",
    }:
        base_payload["region"] = plan.arguments.get("region") or plan.arguments.get("country_code")
        base_payload["topic"] = plan.arguments.get("topic") or plan.arguments.get("category")

        # Build show_rules for frontend to display rules in Rules tab
        countries: list[str] = []
        tags_by_country: dict[str, list[str]] = {}

        # Extract countries from tool result
        if "country_code" in tool_result:
            countries = [tool_result["country_code"]]
        elif "countries" in tool_result:
            countries = tool_result["countries"]

        # Extract tags from plan arguments (what was used to filter)
        tags = plan.arguments.get("tags") or []

        # Build tags_by_country - apply same tags to all countries
        if countries:
            if tags:
                tags_by_country = {country: tags for country in countries}

            base_payload["show_rules"] = {
                "countries": countries,
                "tags_by_country": tags_by_country
            }

    # Flatten commonly-used fields for convenience (hybrid approach)
    # These are the fields UI accesses most frequently
    if "filter_profile" in tool_result:
        base_payload["filters"] = tool_result["filter_profile"]
    
    if "visualization" in tool_result:
        base_payload["visualization"] = tool_result["visualization"]
    
    if "airports" in tool_result:
        base_payload["airports"] = tool_result["airports"]

    # Add suggested queries if available
    if suggested_queries:
        base_payload["suggested_queries"] = suggested_queries

    return base_payload


def _determine_kind(tool_name: str) -> str | None:
    """Determine UI payload kind based on tool name."""
    if tool_name in {
        "search_airports",
        "find_airports_near_route",
        "find_airports_near_location",
        "calculate_flight_distance",
    }:
        return "route"

    if tool_name in {
        "get_airport_details",
        "get_notification_for_airport",
    }:
        return "airport"

    if tool_name in {
        "answer_rules_question",
        "browse_rules",
        "compare_rules_between_countries",
    }:
        return "rules"

    return None


