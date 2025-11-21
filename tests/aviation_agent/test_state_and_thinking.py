"""
Tests for state updates and thinking functionality.

These tests verify:
- Planning reasoning is generated
- Formatting reasoning is generated
- Thinking is combined correctly
- Error handling in state
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from shared.aviation_agent.adapters import build_agent, run_aviation_agent
from shared.aviation_agent.config import AviationAgentSettings


def test_state_contains_planning_reasoning(agent_settings, planner_llm_stub, formatter_llm_stub):
    """Test that state contains planning_reasoning after planner node."""
    from shared.aviation_agent.adapters import build_agent
    from langchain_core.messages import HumanMessage
    
    graph = build_agent(
        settings=agent_settings,
        planner_llm=planner_llm_stub,
        formatter_llm=formatter_llm_stub,
    )
    
    messages = [HumanMessage(content="Find airports near Paris")]
    state = graph.invoke({"messages": messages})
    
    assert "planning_reasoning" in state
    assert state["planning_reasoning"] is not None
    assert "Selected tool" in state["planning_reasoning"]


def test_state_contains_thinking(agent_settings, planner_llm_stub, formatter_llm_stub):
    """Test that state contains combined thinking after formatter node."""
    from shared.aviation_agent.adapters import build_agent
    from langchain_core.messages import HumanMessage
    
    graph = build_agent(
        settings=agent_settings,
        planner_llm=planner_llm_stub,
        formatter_llm=formatter_llm_stub,
    )
    
    messages = [HumanMessage(content="What is airport LFPG?")]
    state = graph.invoke({"messages": messages})
    
    assert "thinking" in state
    # Thinking should combine planning and formatting reasoning
    if state.get("thinking"):
        assert "Selected tool" in state["thinking"] or "Formatted answer" in state["thinking"]


def test_state_handles_errors(agent_settings):
    """Test that state contains error field when errors occur."""
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableLambda
    
    # Create a planner that raises an error
    def failing_planner(_):
        raise ValueError("Test error")
    
    failing_planner_runnable = RunnableLambda(failing_planner)
    
    # Use a simple formatter stub
    from langchain_core.runnables import RunnableLambda as RL
    
    def simple_formatter(_):
        return {"final_answer": "Test", "formatting_reasoning": "Test"}
    
    formatter_stub = RL(simple_formatter)
    
    from shared.aviation_agent.execution import ToolRunner
    from shared.aviation_agent.tools import AviationToolClient
    from shared.aviation_agent.graph import build_agent_graph
    
    tool_client = AviationToolClient(agent_settings.build_tool_context())
    tool_runner = ToolRunner(tool_client)
    graph = build_agent_graph(failing_planner_runnable, tool_runner, formatter_stub)
    
    messages = [HumanMessage(content="Test")]
    state = graph.invoke({"messages": messages})
    
    # Should have error in state
    assert "error" in state
    assert state["error"] is not None

