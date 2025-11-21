from __future__ import annotations

from shared.aviation_agent.formatting import build_ui_payload
from shared.aviation_agent.planning import AviationPlan


def test_ui_payload_route_kind():
    plan = AviationPlan(
        selected_tool="search_airports",
        arguments={"departure": "EGTF", "destination": "LSGS"},
    )
    payload = build_ui_payload(plan, {"airports": [], "pretty": "demo"})
    assert payload["kind"] == "route"
    assert payload["mcp_raw"]["pretty"] == "demo"


def test_ui_payload_none_when_no_tool_result():
    plan = AviationPlan(selected_tool="search_airports", arguments={})
    assert build_ui_payload(plan, None) is None

