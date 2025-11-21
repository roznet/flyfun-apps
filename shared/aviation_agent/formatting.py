from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Dict, Iterable, List

from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableLambda

from .planning import AviationPlan


def build_formatter_chain(llm: Runnable) -> Runnable:
    """
    Return the LLM chain for formatting answers.
    
    This chain will be used directly in the formatter node so LangGraph can capture streaming.
    The node will handle state transformation and UI payload building.
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are an aviation assistant. Use the tool findings to answer the pilot's question.\n"
                    "Always cite operational caveats when data may be outdated. Prefer concise Markdown.\n"
                    "Provide clear, helpful information with references to map visualization when applicable."
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

    # Build chain - Use directly in node so LangGraph can capture streaming
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


def build_ui_payload(plan: AviationPlan, tool_result: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """
    Build UI payload using hybrid approach:
    - Flatten commonly-used fields (filters, visualization, airports) for convenience
    - Keep mcp_raw for everything else and as authoritative source
    """
    if not tool_result:
        return None
    
    # Ensure tool_result is a dict (defensive check)
    if not isinstance(tool_result, dict):
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
    # BREAKPOINT 1: Check if plan.arguments is a dict
    if plan.selected_tool in {"search_airports", "find_airports_near_route", "find_airports_near_location"}:
        # Add breakpoint here to inspect plan.arguments
        if not isinstance(plan.arguments, dict):
            raise TypeError(f"plan.arguments is not a dict: {type(plan.arguments)}, value: {plan.arguments}")
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
        # BREAKPOINT 2: Check if plan.arguments is a dict
        if not isinstance(plan.arguments, dict):
            raise TypeError(f"plan.arguments is not a dict: {type(plan.arguments)}, value: {plan.arguments}")
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
        # BREAKPOINT 3: Check if plan.arguments is a dict
        if not isinstance(plan.arguments, dict):
            raise TypeError(f"plan.arguments is not a dict: {type(plan.arguments)}, value: {plan.arguments}")
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


def _extract_icao_codes(text: str) -> List[str]:
    """Extract ICAO airport codes (4 uppercase letters) from text."""
    if not text:
        return []
    
    pattern = r'\b([A-Z]{4})\b'
    matches = re.findall(pattern, text)
    
    # Deduplicate while preserving order
    seen = set()
    icao_codes = []
    for code in matches:
        if code not in seen:
            seen.add(code)
            icao_codes.append(code)
    
    return icao_codes


def _enhance_visualization(
    ui_payload: Dict[str, Any],
    mentioned_icaos: List[str],
    tool_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Enhance visualization with airports mentioned in answer.
    
    This is optional - only enhances if answer mentions ICAOs not already in visualization.
    For now, we keep it simple and just ensure mentioned airports are included.
    """
    if not ui_payload or not mentioned_icaos:
        return ui_payload
    
    # Get existing visualization
    visualization = ui_payload.get("visualization") or ui_payload.get("mcp_raw", {}).get("visualization")
    if not visualization:
        return ui_payload
    
    # Extract existing airport ICAOs from visualization
    existing_icaos = set()
    if isinstance(visualization, dict):
        # Check markers
        if "markers" in visualization:
            for marker in visualization.get("markers", []):
                if isinstance(marker, dict) and "icao" in marker:
                    existing_icaos.add(marker["icao"])
        # Check route airports
        if "route" in visualization and isinstance(visualization["route"], dict):
            if "airports" in visualization["route"]:
                for airport in visualization["route"]["airports"]:
                    if isinstance(airport, dict) and "ident" in airport:
                        existing_icaos.add(airport["ident"])
    
    # Find mentioned ICAOs not already in visualization
    new_icaos = [icao for icao in mentioned_icaos if icao not in existing_icaos]
    
    # If there are new ICAOs, we could fetch their data and add to visualization
    # For now, we just return the payload as-is (enhancement can be added later if needed)
    # The UI can handle filtering based on mentioned ICAOs if needed
    
    return ui_payload

