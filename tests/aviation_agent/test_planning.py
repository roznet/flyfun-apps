from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableLambda

from shared.aviation_agent.planning import build_planner_runnable


def test_planner_returns_plan(tool_client, sample_messages):
    llm = RunnableLambda(
        lambda _: '{"selected_tool": "search_airports", "arguments": {"query": "LSGS"}, "answer_style": "markdown"}'
    )
    planner = build_planner_runnable(llm, tuple(tool_client.tools.values()))
    plan = planner.invoke({"messages": sample_messages})
    assert plan.selected_tool == "search_airports"
    assert plan.arguments["query"] == "LSGS"


def test_planner_rejects_unknown_tool(tool_client, sample_messages):
    llm = RunnableLambda(lambda _: '{"selected_tool": "unknown_tool", "arguments": {}}')
    planner = build_planner_runnable(llm, tuple(tool_client.tools.values()))
    with pytest.raises(ValueError):
        planner.invoke({"messages": sample_messages})

