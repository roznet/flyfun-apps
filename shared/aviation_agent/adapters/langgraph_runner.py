from __future__ import annotations

from typing import List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from ..config import AviationAgentSettings, get_settings, get_behavior_config
from ..execution import ToolRunner
from ..formatting import build_formatter_chain
from ..graph import build_agent_graph
from ..planning import build_planner_runnable
from ..state import AgentState
from ..tools import AviationToolClient


def build_agent(
    *,
    settings: Optional[AviationAgentSettings] = None,
    planner_llm: Optional[Runnable] = None,
    formatter_llm: Optional[Runnable] = None,
    router_llm: Optional[Runnable] = None,
    rules_llm: Optional[Runnable] = None,
    enable_routing: bool = True,  # Re-enabled - ChromaDB now on local filesystem
):
    settings = settings or get_settings()
    if not settings.enabled:
        raise RuntimeError("Aviation agent is disabled via AVIATION_AGENT_ENABLED flag.")

    # Load behavior config for LLM settings
    behavior_config = get_behavior_config(settings.agent_config_name)
    
    # Resolve LLMs with config overrides
    planner_model = behavior_config.llms.planner.model or settings.planner_model
    planner_llm = _resolve_llm(
        planner_llm, 
        planner_model, 
        role="planner",
        temperature=behavior_config.llms.planner.temperature,
        streaming=behavior_config.llms.planner.streaming
    )
    
    formatter_model = behavior_config.llms.formatter.model or settings.formatter_model
    formatter_llm = _resolve_llm(
        formatter_llm, 
        formatter_model, 
        role="formatter",
        temperature=behavior_config.llms.formatter.temperature,
        streaming=behavior_config.llms.formatter.streaming
    )
    
    # Router and rules LLMs
    router_model = behavior_config.llms.router.model or settings.router_model
    if router_llm is None and router_model:
        router_llm = _resolve_llm(
            None, 
            router_model, 
            role="router",
            temperature=behavior_config.llms.router.temperature,
            streaming=behavior_config.llms.router.streaming
        )
    
    if rules_llm is None:
        if behavior_config.llms.rules and behavior_config.llms.rules.model:
            rules_llm = _resolve_llm(
                None,
                behavior_config.llms.rules.model,
                role="rules",
                temperature=behavior_config.llms.rules.temperature,
                streaming=behavior_config.llms.rules.streaming
            )
        else:
            rules_llm = formatter_llm  # Default to formatter LLM for rules

    tool_client = AviationToolClient(settings.build_tool_context())
    tool_runner = ToolRunner(tool_client)
    planner = build_planner_runnable(planner_llm, tuple(tool_client.tools.values()))
    
    graph = build_agent_graph(
        planner,
        tool_runner,
        formatter_llm,
        router_llm=router_llm,
        rules_llm=rules_llm,
        enable_routing=enable_routing,
        behavior_config=behavior_config
    )
    return graph


def run_aviation_agent(
    messages: List[BaseMessage],
    *,
    settings: Optional[AviationAgentSettings] = None,
    planner_llm: Optional[Runnable] = None,
    formatter_llm: Optional[Runnable] = None,
    enable_routing: bool = True,
    persona_id: Optional[str] = None,
) -> AgentState:
    graph = build_agent(
        settings=settings,
        planner_llm=planner_llm,
        formatter_llm=formatter_llm,
        enable_routing=enable_routing,
    )
    initial_state = {"messages": messages}
    if persona_id:
        initial_state["persona_id"] = persona_id
    result = graph.invoke(initial_state)
    return result


def _resolve_llm(
    llm: Optional[Runnable], 
    model_name: Optional[str], 
    role: str,
    temperature: float = 0.0,
    streaming: bool = False
) -> Runnable:
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

    return ChatOpenAI(model=model_name, temperature=temperature, streaming=streaming)

