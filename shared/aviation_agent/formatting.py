from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Dict, Iterable, List

from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableLambda

from .planning import AviationPlan


def build_formatter_runnable(llm: Runnable, stream: bool = False) -> Runnable:
    """
    Return a runnable that converts planner/tool output into the final answer + UI payload.
    
    If stream=True, returns a streaming runnable that yields chunks.
    
    Note: Thinking is handled via state (planning_reasoning + formatting_reasoning),
    not extracted from LLM output tags.
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

    if stream:
        # Streaming version - SIMPLIFIED: No tag parsing, thinking comes from state
        chain = prompt | llm | StrOutputParser()
        
        async def _astream(payload: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
            plan: AviationPlan = payload["plan"]
            tool_result = payload.get("tool_result") or {}
            
            full_response = ""
            
            # Stream LLM output directly - simple and fast
            async for chunk in chain.astream({
                "messages": payload["messages"],
                "answer_style": plan.answer_style,
                "tool_result_json": json.dumps(tool_result, indent=2, ensure_ascii=False),
                "pretty_text": tool_result.get("pretty", ""),
            }):
                full_response += chunk
                # Stream directly as message - no tag parsing needed!
                yield {"type": "message", "content": chunk}
            
            # Finalize
            answer = full_response.strip()
            ui_payload = build_ui_payload(plan, tool_result)
            
            # Optional: Enhance visualization with ICAOs from answer
            mentioned_icaos = []
            if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
                mentioned_icaos = _extract_icao_codes(answer)
                if mentioned_icaos:
                    ui_payload = _enhance_visualization(ui_payload, mentioned_icaos, tool_result)
            
            # Generate simple formatting reasoning (not from LLM, from our logic)
            formatting_reasoning = f"Formatted answer using {plan.answer_style} style."
            if mentioned_icaos:
                formatting_reasoning += f" Mentioned {len(mentioned_icaos)} airports."
            
            yield {"type": "done", "answer": answer, "formatting_reasoning": formatting_reasoning, "ui_payload": ui_payload}
        
        return RunnableLambda(_astream)
    else:
        # Non-streaming version
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
            answer = final_answer.strip()
            ui_payload = build_ui_payload(plan, tool_result)
            
            # Optional: Enhance visualization with ICAOs from answer
            mentioned_icaos = []
            if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
                mentioned_icaos = _extract_icao_codes(answer)
                if mentioned_icaos:
                    ui_payload = _enhance_visualization(ui_payload, mentioned_icaos, tool_result)
            
            # Generate simple formatting reasoning
            formatting_reasoning = f"Formatted answer using {plan.answer_style} style."
            if mentioned_icaos:
                formatting_reasoning += f" Mentioned {len(mentioned_icaos)} airports."
            
            return {
                "final_answer": answer,
                "formatting_reasoning": formatting_reasoning,
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

