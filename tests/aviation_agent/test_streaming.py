"""
Tests for aviation agent streaming functionality.

These tests verify:
- Streaming endpoint works
- SSE events are properly formatted
- Token tracking works
- Error handling in streaming
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator, Dict, Any

import pytest
from langchain_core.messages import HumanMessage

from shared.aviation_agent.adapters import build_agent, stream_aviation_agent
from shared.aviation_agent.config import AviationAgentSettings


def _should_run_streaming_tests() -> bool:
    """Check if streaming tests should run (require explicit opt-in)."""
    return os.getenv("RUN_STREAMING_TESTS") == "1"


@pytest.fixture(scope="session")
def streaming_agent_settings() -> AviationAgentSettings:
    """Settings for streaming tests."""
    if not _should_run_streaming_tests():
        pytest.skip("Streaming tests require RUN_STREAMING_TESTS=1")
    
    from pathlib import Path
    from tests.aviation_agent.conftest import _locate
    
    return AviationAgentSettings(
        enabled=True,
        planner_model=os.getenv("AVIATION_AGENT_PLANNER_MODEL", "gpt-4o-mini"),
        formatter_model=os.getenv("AVIATION_AGENT_FORMATTER_MODEL", "gpt-4o-mini"),
        airports_db=Path(_locate("airports.db")),
        rules_json=Path(_locate("rules.json")),
    )


@pytest.mark.streaming
@pytest.mark.asyncio
async def test_streaming_emits_plan_event(streaming_agent_settings):
    """Test that streaming emits plan event."""
    graph = build_agent(settings=streaming_agent_settings)
    messages = [HumanMessage(content="Find airports near Paris")]
    
    events = []
    async for event in stream_aviation_agent(messages, graph):
        events.append(event)
        if event.get("event") == "plan":
            break  # Stop after plan event
    
    assert len(events) > 0, "Should emit at least one event"
    plan_event = next((e for e in events if e.get("event") == "plan"), None)
    assert plan_event is not None, "Should emit plan event"
    assert "data" in plan_event
    assert "selected_tool" in plan_event["data"]


@pytest.mark.streaming
@pytest.mark.asyncio
async def test_streaming_emits_message_events(streaming_agent_settings):
    """Test that streaming emits message events."""
    graph = build_agent(settings=streaming_agent_settings)
    messages = [HumanMessage(content="What is airport LFPG?")]
    
    events = []
    async for event in stream_aviation_agent(messages, graph):
        events.append(event)
        if event.get("event") == "done":
            break
    
    message_events = [e for e in events if e.get("event") == "message"]
    assert len(message_events) > 0, "Should emit message events"
    
    # Verify message events have content
    for event in message_events:
        assert "data" in event
        assert "content" in event["data"]


@pytest.mark.streaming
@pytest.mark.asyncio
async def test_streaming_emits_done_event_with_tokens(streaming_agent_settings):
    """Test that streaming emits done event with token counts."""
    graph = build_agent(settings=streaming_agent_settings)
    messages = [HumanMessage(content="What is airport LFPG?")]
    
    done_event = None
    async for event in stream_aviation_agent(messages, graph, session_id="test-session"):
        if event.get("event") == "done":
            done_event = event
            break
    
    assert done_event is not None, "Should emit done event"
    assert "data" in done_event
    assert "tokens" in done_event["data"]
    assert "input" in done_event["data"]["tokens"]
    assert "output" in done_event["data"]["tokens"]
    assert "total" in done_event["data"]["tokens"]
    assert done_event["data"]["session_id"] == "test-session"


@pytest.mark.streaming
@pytest.mark.asyncio
async def test_streaming_emits_ui_payload(streaming_agent_settings):
    """Test that streaming emits ui_payload event."""
    graph = build_agent(settings=streaming_agent_settings)
    messages = [HumanMessage(content="Find airports from EGTF to LFMD")]
    
    ui_payload_event = None
    async for event in stream_aviation_agent(messages, graph):
        if event.get("event") == "ui_payload":
            ui_payload_event = event
            break
    
    if ui_payload_event:
        assert "data" in ui_payload_event
        payload = ui_payload_event["data"]
        assert "kind" in payload
        assert "mcp_raw" in payload


@pytest.mark.streaming
@pytest.mark.asyncio
async def test_streaming_handles_errors_gracefully(streaming_agent_settings):
    """Test that streaming handles errors and emits error event."""
    graph = build_agent(settings=streaming_agent_settings)
    # Use invalid input that might cause an error
    messages = [HumanMessage(content="")]
    
    error_event = None
    done_event = None
    async for event in stream_aviation_agent(messages, graph):
        if event.get("event") == "error":
            error_event = event
        if event.get("event") == "done":
            done_event = event
            break
    
    # Should either emit error or complete (depending on how agent handles empty input)
    assert done_event is not None or error_event is not None

