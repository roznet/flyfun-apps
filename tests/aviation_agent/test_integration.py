"""
Integration tests for aviation agent streaming endpoint.

These tests verify the complete flow from HTTP request to SSE response.
Requires a running server or can be run with TestClient.

Note: These tests require LLM configuration. Set AVIATION_AGENT_PLANNER_MODEL
and AVIATION_AGENT_FORMATTER_MODEL environment variables, or they will be skipped.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "web" / "server"))

from main import app


@pytest.fixture(scope="session")
def api_key_available():
    """Check if OpenAI API key is available for integration tests."""
    return bool(os.getenv("OPENAI_API_KEY"))


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment variables for aviation agent."""
    # Check if LLM models are configured
    planner_model = os.getenv("AVIATION_AGENT_PLANNER_MODEL")
    formatter_model = os.getenv("AVIATION_AGENT_FORMATTER_MODEL")
    
    # If not set, try to use defaults for testing (but require API key)
    if not planner_model:
        os.environ["AVIATION_AGENT_PLANNER_MODEL"] = "gpt-4o-mini"
    if not formatter_model:
        os.environ["AVIATION_AGENT_FORMATTER_MODEL"] = "gpt-4o-mini"
    
    # Ensure agent is enabled
    os.environ["AVIATION_AGENT_ENABLED"] = "true"
    
    # Set data paths if not already set
    if not os.getenv("AIRPORTS_DB"):
        # Try to find airports.db
        root = Path(__file__).parent.parent.parent
        for candidate in [root / "data" / "airports.db", root / "airports.db"]:
            if candidate.exists():
                os.environ["AIRPORTS_DB"] = str(candidate)
                break
    
    if not os.getenv("RULES_JSON"):
        # Try to find rules.json
        root = Path(__file__).parent.parent.parent
        for candidate in [root / "data" / "rules.json", root / "rules.json"]:
            if candidate.exists():
                os.environ["RULES_JSON"] = str(candidate)
                break


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    # Use an allowed host to bypass TrustedHostMiddleware
    return TestClient(app, base_url="http://localhost:8000")


@pytest.mark.integration
def test_streaming_endpoint_returns_sse_events(client, api_key_available):
    """Test that the streaming endpoint returns properly formatted SSE events."""
    if not api_key_available:
        pytest.skip("OPENAI_API_KEY not set - skipping integration test")
    
    response = client.post(
        "/api/aviation-agent/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "Say hello in 3 words"}
            ]
        },
        headers={"Content-Type": "application/json"},
    )
    
    # Agent might be disabled (404), middleware might block (400), or LLM config missing (503)
    assert response.status_code in [200, 400, 404, 503], f"Unexpected status: {response.status_code}, response: {response.text[:200]}"
    
    if response.status_code == 404:
        pytest.skip("Aviation agent is disabled")
    elif response.status_code == 400:
        pytest.skip("Request blocked by middleware (likely TrustedHostMiddleware)")
    elif response.status_code == 503:
        pytest.skip(f"Agent configuration error: {response.json().get('detail', 'Unknown error')}")
    
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    # Parse SSE events
    events = []
    event_type = None
    for line in response.iter_lines():
        if line:
            # TestClient.iter_lines() returns strings, not bytes
            line_str = line if isinstance(line, str) else line.decode('utf-8')
            if line_str.startswith('event:'):
                event_type = line_str.split(':', 1)[1].strip()
            elif line_str.startswith('data:'):
                data_str = line_str.split(':', 1)[1].strip()
                try:
                    data = json.loads(data_str)
                    if event_type:
                        events.append({"event": event_type, "data": data})
                except json.JSONDecodeError:
                    pass
    
    # Verify we got some events
    assert len(events) > 0, "Should receive at least one SSE event"
    
    # Verify event types
    event_types = [e["event"] for e in events]
    assert "plan" in event_types or "message" in event_types or "done" in event_types


@pytest.mark.integration
def test_streaming_endpoint_emits_plan_event(client, api_key_available):
    """Test that the streaming endpoint emits a plan event."""
    if not api_key_available:
        pytest.skip("OPENAI_API_KEY not set - skipping integration test")
    
    response = client.post(
        "/api/aviation-agent/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "What is airport LFPG?"}
            ]
        },
    )
    
    # Agent might be disabled (404), middleware might block (400), or LLM config missing (503)
    assert response.status_code in [200, 400, 404, 503], f"Unexpected status: {response.status_code}"
    if response.status_code == 404:
        pytest.skip("Aviation agent is disabled")
    elif response.status_code == 400:
        pytest.skip("Request blocked by middleware")
    elif response.status_code == 503:
        pytest.skip(f"Agent configuration error: {response.json().get('detail', 'Unknown error')}")
    
    events = []
    event_type = None
    for line in response.iter_lines():
        if line:
            # TestClient.iter_lines() returns strings, not bytes
            line_str = line if isinstance(line, str) else line.decode('utf-8')
            if line_str.startswith('event:'):
                event_type = line_str.split(':', 1)[1].strip()
            elif line_str.startswith('data:'):
                data_str = line_str.split(':', 1)[1].strip()
                try:
                    data = json.loads(data_str)
                    if event_type:
                        events.append({"event": event_type, "data": data})
                        if event_type == "plan":
                            break  # Stop after plan event
                except json.JSONDecodeError:
                    pass
    
    plan_events = [e for e in events if e["event"] == "plan"]
    assert len(plan_events) > 0, "Should emit plan event"
    assert "selected_tool" in plan_events[0]["data"]


@pytest.mark.integration
def test_streaming_endpoint_emits_message_events(client, api_key_available):
    """Test that the streaming endpoint emits message events."""
    if not api_key_available:
        pytest.skip("OPENAI_API_KEY not set - skipping integration test")
    
    response = client.post(
        "/api/aviation-agent/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "Say hello"}
            ]
        },
    )
    
    # Agent might be disabled (404), middleware might block (400), or LLM config missing (503)
    assert response.status_code in [200, 400, 404, 503], f"Unexpected status: {response.status_code}"
    if response.status_code == 404:
        pytest.skip("Aviation agent is disabled")
    elif response.status_code == 400:
        pytest.skip("Request blocked by middleware")
    elif response.status_code == 503:
        pytest.skip(f"Agent configuration error: {response.json().get('detail', 'Unknown error')}")
    
    events = []
    event_type = None
    for line in response.iter_lines():
        if line:
            # TestClient.iter_lines() returns strings, not bytes
            line_str = line if isinstance(line, str) else line.decode('utf-8')
            if line_str.startswith('event:'):
                event_type = line_str.split(':', 1)[1].strip()
            elif line_str.startswith('data:'):
                data_str = line_str.split(':', 1)[1].strip()
                try:
                    data = json.loads(data_str)
                    if event_type:
                        events.append({"event": event_type, "data": data})
                        if event_type == "done":
                            break  # Stop after done event
                except json.JSONDecodeError:
                    pass
    
    message_events = [e for e in events if e["event"] == "message"]
    assert len(message_events) > 0, "Should emit message events"
    
    # Verify message events have content
    for event in message_events:
        assert "content" in event["data"]


@pytest.mark.integration
def test_streaming_endpoint_emits_done_event(client, api_key_available):
    """Test that the streaming endpoint emits done event with tokens."""
    if not api_key_available:
        pytest.skip("OPENAI_API_KEY not set - skipping integration test")
    
    response = client.post(
        "/api/aviation-agent/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "Say hello"}
            ]
        },
    )
    
    # Agent might be disabled (404), middleware might block (400), or LLM config missing (503)
    assert response.status_code in [200, 400, 404, 503], f"Unexpected status: {response.status_code}"
    if response.status_code == 404:
        pytest.skip("Aviation agent is disabled")
    elif response.status_code == 400:
        pytest.skip("Request blocked by middleware")
    elif response.status_code == 503:
        pytest.skip(f"Agent configuration error: {response.json().get('detail', 'Unknown error')}")
    
    done_event = None
    event_type = None
    for line in response.iter_lines():
        if line:
            # TestClient.iter_lines() returns strings, not bytes
            line_str = line if isinstance(line, str) else line.decode('utf-8')
            if line_str.startswith('event:'):
                event_type = line_str.split(':', 1)[1].strip()
            elif line_str.startswith('data:'):
                data_str = line_str.split(':', 1)[1].strip()
                try:
                    data = json.loads(data_str)
                    if event_type == "done":
                        done_event = {"event": event_type, "data": data}
                        break
                except json.JSONDecodeError:
                    pass
    
    assert done_event is not None, "Should emit done event"
    assert "tokens" in done_event["data"]
    assert "input" in done_event["data"]["tokens"]
    assert "output" in done_event["data"]["tokens"]


@pytest.mark.integration
def test_streaming_endpoint_handles_errors(client, api_key_available):
    """Test that the streaming endpoint handles errors gracefully."""
    if not api_key_available:
        pytest.skip("OPENAI_API_KEY not set - skipping integration test")
    
    # Test with invalid request (empty messages)
    response = client.post(
        "/api/aviation-agent/chat/stream",
        json={
            "messages": []
        },
    )
    
    # Should either return 200 with error event, or return error status
    # Depending on validation, it might be 422, 400, 404 (disabled), or 503 (config error)
    assert response.status_code in [200, 422, 400, 404, 503]

