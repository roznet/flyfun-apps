from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda

from shared.aviation_agent.config import AviationAgentSettings
from shared.aviation_agent.tools import AviationToolClient


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _locate(filename: str) -> Path:
    candidates = [
        _project_root() / "data" / filename,
        _project_root() / "web" / "server" / filename,
        _project_root() / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Unable to locate {filename}")


@pytest.fixture(scope="session")
def data_files() -> Dict[str, str]:
    return {
        "airports_db": str(_locate("airports.db")),
        "rules_json": str(_locate("rules.json")),
    }


@pytest.fixture(scope="session")
def agent_settings(data_files: Dict[str, str]) -> AviationAgentSettings:
    return AviationAgentSettings(
        enabled=True,
        planner_model=None,
        formatter_model=None,
        airports_db=Path(data_files["airports_db"]),
        rules_json=Path(data_files["rules_json"]),
    )


@pytest.fixture(scope="session")
def tool_client(agent_settings: AviationAgentSettings) -> AviationToolClient:
    return AviationToolClient(agent_settings.build_tool_context())


@pytest.fixture
def sample_messages() -> list[HumanMessage]:
    return [
        HumanMessage(content="Need IFR routing from EGTF to LSGS with customs stops."),
    ]


@pytest.fixture
def planner_llm_stub():
    payload = '{"selected_tool": "search_airports", "arguments": {"query": "LSGS"}, "answer_style": "markdown"}'
    return RunnableLambda(lambda _: payload)


@pytest.fixture
def formatter_llm_stub():
    return RunnableLambda(lambda _: "Stubbed final answer.")

