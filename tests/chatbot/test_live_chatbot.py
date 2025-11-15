#!/usr/bin/env python3
"""
Live integration tests that hit the real LLM + MCP stack.
Disabled by default; enable with RUN_LIVE_LLM_TESTS=1.
"""

import os

import pytest

pytest.importorskip("openai")

from web.server.chatbot_service import ChatbotService


LIVE_FLAG = os.getenv("RUN_LIVE_LLM_TESTS") == "1"


@pytest.mark.live_llm
@pytest.mark.skipif(not LIVE_FLAG, reason="Set RUN_LIVE_LLM_TESTS=1 to run live LLM tests")
def test_live_route_planning_triggers_route_tool():
    service = ChatbotService()

    response = service.chat(
        "Plan a VFR route from EGTF to LFMD with an AVGAS-capable fuel stop."
        " Make sure you recommend at least one option along the route."
    )

    assert "EGTF" in response["message"], "Expected departure airport mention in answer"
    assert "LFMD" in response["message"], "Expected destination airport mention in answer"
    assert any(
        tool["name"] == "find_airports_near_route"
        for tool in response.get("tool_calls", [])
    ), "Route planning should call find_airports_near_route"
    assert response.get("visualization") is not None, "Map data should be present"

