from __future__ import annotations

from shared.aviation_agent.adapters.langgraph_runner import run_aviation_agent


def test_agent_runner_produces_ui_payload(
    agent_settings,
    sample_messages,
    planner_llm_stub,
    formatter_llm_stub,
):
    state = run_aviation_agent(
        sample_messages,
        settings=agent_settings,
        planner_llm=planner_llm_stub,
        formatter_llm=formatter_llm_stub,
    )

    assert state["plan"].selected_tool == "search_airports"
    assert state["final_answer"]
    assert state["ui_payload"]["kind"] == "route"

