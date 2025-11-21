from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.airport_tools import ToolContext


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AIRPORT_DB_CANDIDATES = [
    "web/server/airports.db",
    "data/airports.db",
    "airports.db",
]
RULES_JSON_CANDIDATES = [
    "data/rules.json",
    "rules.json",
    "web/server/rules.json",
]


def _locate_file(candidates: list[str]) -> Path:
    for candidate in candidates:
        path = PROJECT_ROOT / candidate
        if path.exists():
            return path
    # fall back to the first candidate even if it does not exist yet
    return PROJECT_ROOT / candidates[0]


def _default_airports_db() -> Path:
    env_value = os.environ.get("AIRPORTS_DB")
    if env_value:
        env_path = Path(env_value)
        if env_path.exists():
            return env_path
    return _locate_file(AIRPORT_DB_CANDIDATES)


def _default_rules_json() -> Path:
    env_value = os.environ.get("RULES_JSON")
    if env_value:
        env_path = Path(env_value)
        if env_path.exists():
            return env_path
    return _locate_file(RULES_JSON_CANDIDATES)


class AviationAgentSettings(BaseSettings):
    """
    Central configuration for the aviation agent.

    Putting the logic in a BaseSettings class lets FastAPI use dependency
    injection while keeping CLI scripts simple.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    enabled: bool = Field(
        default=True,
        description="Feature flag that allows the FastAPI layer to disable the agent entirely.",
        alias="AVIATION_AGENT_ENABLED",
    )
    planner_model: Optional[str] = Field(
        default=None,
        description="LLM name to use for the planner. If None, callers must inject an LLM instance.",
        alias="AVIATION_AGENT_PLANNER_MODEL",
    )
    formatter_model: Optional[str] = Field(
        default=None,
        description="LLM name to use for the formatter. If None, callers must inject an LLM instance.",
        alias="AVIATION_AGENT_FORMATTER_MODEL",
    )
    airports_db: Path = Field(
        default_factory=_default_airports_db,
        description="Path to airports.db used by ToolContext.",
        alias="AIRPORTS_DB",
    )
    rules_json: Path = Field(
        default_factory=_default_rules_json,
        description="Path to rules.json used by ToolContext.",
        alias="RULES_JSON",
    )

    def build_tool_context(self, *, load_rules: bool = True) -> ToolContext:
        return ToolContext.create(
            db_path=str(self.airports_db),
            rules_path=str(self.rules_json),
            load_rules=load_rules,
        )


@lru_cache(maxsize=1)
def get_settings() -> AviationAgentSettings:
    """
    Cached accessor for scenarios (e.g., FastAPI dependency) where constructing
    BaseSettings repeatedly would be expensive.
    """

    return AviationAgentSettings()

