from __future__ import annotations

from typing import List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from ..config import AviationAgentSettings, get_settings
from ..execution import ToolRunner
from ..formatting import build_formatter_runnable
from ..graph import build_agent_graph
from ..planning import build_planner_runnable
from ..state import AgentState
from ..tools import AviationToolClient


def build_agent(
    *,
    settings: Optional[AviationAgentSettings] = None,
    planner_llm: Optional[Runnable] = None,
    formatter_llm: Optional[Runnable] = None,
):
    settings = settings or get_settings()
    if not settings.enabled:
        raise RuntimeError("Aviation agent is disabled via AVIATION_AGENT_ENABLED flag.")

    planner_llm = _resolve_llm(planner_llm, settings.planner_model, role="planner")
    formatter_llm = _resolve_llm(formatter_llm, settings.formatter_model, role="formatter")

    tool_client = AviationToolClient(settings.build_tool_context())
    tool_runner = ToolRunner(tool_client)
    planner = build_planner_runnable(planner_llm, tuple(tool_client.tools.values()))
    formatter = build_formatter_runnable(formatter_llm)
    graph = build_agent_graph(planner, tool_runner, formatter)
    return graph


def run_aviation_agent(
    messages: List[BaseMessage],
    *,
    settings: Optional[AviationAgentSettings] = None,
    planner_llm: Optional[Runnable] = None,
    formatter_llm: Optional[Runnable] = None,
) -> AgentState:
    graph = build_agent(
        settings=settings,
        planner_llm=planner_llm,
        formatter_llm=formatter_llm,
    )
    result = graph.invoke({"messages": messages})
    return result


def _resolve_llm(llm: Optional[Runnable], model_name: Optional[str], role: str) -> Runnable:
    if llm is not None:
        return llm
    if not model_name:
        raise RuntimeError(
            f"No {role} LLM provided. Set AVIATION_AGENT_{role.upper()}_MODEL or pass an llm instance."
        )

    try:
        from langchain_openai import ChatOpenAI
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            f"Cannot auto-create {role} LLM. Install langchain-openai or inject a custom Runnable."
        ) from exc

    return ChatOpenAI(model=model_name, temperature=0)

