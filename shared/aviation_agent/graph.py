from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .execution import ToolRunner
from .planning import AviationPlan
from .state import AgentState


def build_agent_graph(planner, tool_runner: ToolRunner, formatter):
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

    def formatter_node(state: AgentState) -> Dict[str, Any]:
        # Handle errors gracefully
        if state.get("error"):
            return {
                "final_answer": f"I encountered an error: {state['error']}. Please try again.",
                "error": state["error"],
                "thinking": state.get("planning_reasoning", ""),
            }
        
        try:
            formatted = formatter.invoke(
                {
                    "messages": state.get("messages") or [],
                    "plan": state.get("plan"),
                    "tool_result": state.get("tool_result"),
                }
            )
            
            # Combine planning and formatting reasoning
            thinking_parts = []
            if state.get("planning_reasoning"):
                thinking_parts.append(state["planning_reasoning"])
            if formatted.get("formatting_reasoning"):
                thinking_parts.append(formatted["formatting_reasoning"])
            
            return {
                "final_answer": formatted.get("final_answer", ""),
                "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
                "ui_payload": formatted.get("ui_payload"),
            }
        except Exception as e:
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

