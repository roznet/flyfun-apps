from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .execution import ToolRunner
from .formatting import build_formatter_chain
from .planning import AviationPlan
from .state import AgentState

logger = logging.getLogger(__name__)


def build_agent_graph(planner, tool_runner: ToolRunner, formatter_llm):
    """
    Assemble the LangGraph workflow using injected planner/formatter runnables.
    """

    graph = StateGraph(AgentState)

    def planner_node(state: AgentState) -> Dict[str, Any]:
        try:
            plan: AviationPlan = planner.invoke({"messages": state.get("messages") or []})
            # Generate simple reasoning from plan
            reasoning_parts = [f"Selected tool: {plan.selected_tool}"]
            if plan.arguments.get("filters"):
                filter_str = ", ".join(f"{k}={v}" for k, v in plan.arguments["filters"].items())
                reasoning_parts.append(f"with filters: {filter_str}")
            if plan.arguments:
                other_args = {k: v for k, v in plan.arguments.items() if k != "filters"}
                if other_args:
                    arg_str = ", ".join(f"{k}={v}" for k, v in other_args.items())
                    reasoning_parts.append(f"with arguments: {arg_str}")
            
            reasoning = ". ".join(reasoning_parts) + "."
            return {"plan": plan, "planning_reasoning": reasoning}
        except Exception as e:
            return {"error": str(e)}

    def tool_node(state: AgentState) -> Dict[str, Any]:
        if state.get("error"):
            return {}  # Skip if planner failed
        plan = state.get("plan")
        if not plan:
            return {"error": "No plan available"}
        try:
            result = tool_runner.run(plan)
            return {"tool_result": result}
        except Exception as e:
            return {"error": str(e)}

    # Build formatter chain directly - this allows LangGraph to capture streaming
    formatter_chain = build_formatter_chain(formatter_llm)
    
    def formatter_node(state: AgentState) -> Dict[str, Any]:
        # Handle errors gracefully
        error = state.get("error")
        if error:
            return {
                "final_answer": f"I encountered an error: {error}. Please try again.",
                "error": error,
                "thinking": state.get("planning_reasoning", ""),
            }
        
        try:
            # Transform state to chain inputs
            plan = state.get("plan")
            tool_result = state.get("tool_result") or {}
            
            # Use chain directly - LangGraph's astream_events() will capture streaming
            # The chain is: prompt | llm | StrOutputParser(), so it should return a string
            chain_result = formatter_chain.invoke(
                {
                    "messages": state.get("messages") or [],
                    "answer_style": plan.answer_style if plan else "narrative_markdown",
                    "tool_result_json": json.dumps(tool_result, indent=2, ensure_ascii=False),
                    "pretty_text": tool_result.get("pretty", ""),
                }
            )
            
            # Process the answer and build UI payload
            from .formatting import build_ui_payload, _extract_icao_codes, _enhance_visualization
            from langchain_core.messages import BaseMessage
            
            # Handle different return types from the chain
            if isinstance(chain_result, str):
                answer = chain_result.strip()
            elif hasattr(chain_result, "content"):
                # AIMessage or similar - extract content
                answer = str(chain_result.content).strip()
            else:
                # Fallback to string conversion
                answer = str(chain_result).strip()
            
            # Build UI payload
            ui_payload = build_ui_payload(plan, tool_result) if plan else None
            
            # Optional: Enhance visualization with ICAOs from answer
            mentioned_icaos = []
            if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
                mentioned_icaos = _extract_icao_codes(answer)
                if mentioned_icaos:
                    ui_payload = _enhance_visualization(ui_payload, mentioned_icaos, tool_result)
            
            # Generate simple formatting reasoning
            formatting_reasoning = f"Formatted answer using {plan.answer_style if plan else 'default'} style."
            if mentioned_icaos:
                formatting_reasoning += f" Mentioned {len(mentioned_icaos)} airports."
            
            # Combine planning and formatting reasoning
            thinking_parts = []
            planning_reasoning = state.get("planning_reasoning")
            if planning_reasoning:
                thinking_parts.append(planning_reasoning)
            thinking_parts.append(formatting_reasoning)
            
            return {
                "final_answer": answer,
                "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
                "ui_payload": ui_payload,
            }
        except Exception as e:
            logger.exception("Formatter node error")
            return {
                "final_answer": f"Error formatting response: {str(e)}",
                "error": str(e),
                "thinking": state.get("planning_reasoning", ""),
            }

    graph.add_node("planner", planner_node)
    graph.add_node("tool", tool_node)
    graph.add_node("formatter", formatter_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "tool")
    graph.add_edge("tool", "formatter")
    graph.add_edge("formatter", END)

    return graph.compile()

