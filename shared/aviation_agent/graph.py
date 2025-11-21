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
        plan: AviationPlan = planner.invoke({"messages": state.get("messages") or []})
        return {"plan": plan}

    def tool_node(state: AgentState) -> Dict[str, Any]:
        plan = state.get("plan")
        if not plan:
            return {}
        result = tool_runner.run(plan)
        return {"tool_result": result}

    def formatter_node(state: AgentState) -> Dict[str, Any]:
        formatted = formatter.invoke(
            {
                "messages": state.get("messages") or [],
                "plan": state.get("plan"),
                "tool_result": state.get("tool_result"),
            }
        )
        return formatted

    graph.add_node("planner", planner_node)
    graph.add_node("tool", tool_node)
    graph.add_node("formatter", formatter_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "tool")
    graph.add_edge("tool", "formatter")
    graph.add_edge("formatter", END)

    return graph.compile()

