from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.airport_tools import ToolContext

logger = logging.getLogger(__name__)


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
VECTOR_DB_CANDIDATES = [
    "out/rules_vector_db",
    "cache/rules_vector_db",
    "rules_vector_db",
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


def _default_vector_db() -> Path:
    env_value = os.environ.get("VECTOR_DB_PATH")
    if env_value:
        return Path(env_value)
    return _locate_file(VECTOR_DB_CANDIDATES)


def _default_vector_db_url() -> Optional[str]:
    """Get ChromaDB service URL if configured, otherwise None for local mode."""
    return os.environ.get("VECTOR_DB_URL")


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
    vector_db_path: Path = Field(
        default_factory=_default_vector_db,
        description="Path to rules vector database for RAG retrieval (local mode).",
        alias="VECTOR_DB_PATH",
    )
    vector_db_url: Optional[str] = Field(
        default_factory=_default_vector_db_url,
        description="URL to ChromaDB service for RAG retrieval (service mode). If set, takes precedence over vector_db_path.",
        alias="VECTOR_DB_URL",
    )
    
    # RAG settings
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model for RAG (OpenAI: text-embedding-3-small or text-embedding-3-large)",
        alias="EMBEDDING_MODEL",
    )
    enable_query_reformulation: bool = Field(
        default=True,
        description="Whether to reformulate queries for better RAG matching",
        alias="ENABLE_QUERY_REFORMULATION",
    )
    router_model: Optional[str] = Field(
        default="gpt-4o-mini",
        description="LLM model for query routing",
        alias="ROUTER_MODEL",
    )
    agent_config_name: Optional[str] = Field(
        default="default",
        description="Name of agent behavior config file (without .json). Loads from configs/aviation_agent/",
        alias="AVIATION_AGENT_CONFIG",
    )

    def build_tool_context(self, *, load_rules: bool = True) -> ToolContext:
        """
        Build or retrieve cached ToolContext.
        
        ToolContext is expensive to create (loads entire airport database + rules),
        so we cache it at the module level. The cache key includes db_path, rules_path,
        and load_rules flag to ensure we create separate contexts for different configs.
        """
        return _cached_tool_context(
            db_path=str(self.airports_db),
            rules_path=str(self.rules_json),
            load_rules=load_rules,
        )


@lru_cache(maxsize=1)
def _cached_tool_context(
    db_path: str,
    rules_path: str,
    load_rules: bool,
) -> ToolContext:
    """
    Cached ToolContext factory.
    
    ToolContext creation is expensive (loads entire airport database + rules),
    so we cache it at the module level. Only one ToolContext is created per unique
    combination of (db_path, rules_path, load_rules).
    
    This matches the pattern used in:
    - mcp_server/main.py (global _tool_context created once at startup)
    - tests/tools/conftest.py (@lru_cache on tool_context fixture)
    """
    return ToolContext.create(
        db_path=db_path,
        rules_path=rules_path,
        load_rules=load_rules,
    )


@lru_cache(maxsize=1)
def get_settings() -> AviationAgentSettings:
    """
    Cached accessor for scenarios (e.g., FastAPI dependency) where constructing
    BaseSettings repeatedly would be expensive.
    """

    return AviationAgentSettings()


@lru_cache(maxsize=10)  # Cache multiple configs by config name
def get_behavior_config(config_name: str = "default") -> "AgentBehaviorConfig":
    """
    Load agent behavior configuration from config directory.
    
    Args:
        config_name: Name of config file (without .json extension)
        
    Returns:
        AgentBehaviorConfig instance with _config_dir set for prompt loading
    """
    from .behavior_config import AgentBehaviorConfig
    
    config_dir = PROJECT_ROOT / "configs" / "aviation_agent"
    config_file = config_dir / f"{config_name}.json"

    if config_file.exists():
        config = AgentBehaviorConfig.from_file(config_file)
        config._config_dir = config_dir  # Store for prompt loading
        logger.info(f"Loaded agent behavior config: {config_name}")
        return config

    # Fall back to default if specified config doesn't exist
    if config_name != "default":
        default_file = config_dir / "default.json"
        if default_file.exists():
            logger.warning(f"Config '{config_name}' not found, using 'default'")
            config = AgentBehaviorConfig.from_file(default_file)
            config._config_dir = config_dir
            return config

    # Final fallback to hardcoded defaults
    logger.info(f"Using default hardcoded behavior config (config '{config_name}' not found)")
    config = AgentBehaviorConfig.default()
    config._config_dir = config_dir
    return config

