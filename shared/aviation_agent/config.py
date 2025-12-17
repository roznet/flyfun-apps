from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.tool_context import ToolContext

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _get_path_from_env(env_var: str, default_filename: str, allow_default: bool = False) -> Path:
    """
    Get path from environment variable.
    
    Args:
        env_var: Environment variable name
        default_filename: Default filename if env var not set (only used if allow_default=True)
        allow_default: If True, use default_filename in current directory when env var not set.
                      If False, raise ValueError (production mode - requires explicit config).
    
    Production code should use allow_default=False to require explicit environment configuration.
    """
    env_value = os.environ.get(env_var)
    if env_value:
        return Path(env_value)
    
    if allow_default:
        # Fallback to default in current directory (for backward compatibility)
        return Path(default_filename)
    
    # Production mode: require explicit configuration
    raise ValueError(
        f"{env_var} environment variable is required. "
        f"Please set it to the path of {default_filename}"
    )


def _default_airports_db() -> Path:
    """
    Get airports.db path from AIRPORTS_DB environment variable.
    
    For production: requires AIRPORTS_DB to be set.
    For backward compatibility: falls back to "airports.db" in current directory.
    """
    return _get_path_from_env("AIRPORTS_DB", "airports.db", allow_default=True)


def _default_rules_json() -> Path:
    """
    Get rules.json path from RULES_JSON environment variable.
    
    For production: requires RULES_JSON to be set.
    For backward compatibility: falls back to "rules.json" in current directory.
    """
    return _get_path_from_env("RULES_JSON", "rules.json", allow_default=True)


def _default_ga_notifications_db() -> Path:
    """
    Get ga_notifications.db path from GA_NOTIFICATIONS_DB environment variable.
    
    For production: requires GA_NOTIFICATIONS_DB to be set.
    For backward compatibility: falls back to "ga_notifications.db" in current directory.
    """
    return _get_path_from_env("GA_NOTIFICATIONS_DB", "ga_notifications.db", allow_default=True)


def _default_ga_meta_db() -> Optional[Path]:
    """
    Get ga_meta.sqlite path from GA_META_DB environment variable.
    
    Returns None if not set (service is optional).
    """
    env_value = os.environ.get("GA_META_DB")
    if env_value:
        return Path(env_value)
    return None


def get_ga_notifications_db_path() -> str:
    """
    Get path to GA notifications database as a string.
    
    Requires GA_NOTIFICATIONS_DB environment variable to be set.
    
    Returns:
        Path to the database as a string
    """
    return str(_default_ga_notifications_db())


def get_ga_meta_db_path() -> Optional[str]:
    """
    Get path to GA meta database as a string.
    
    Returns None if GA_META_DB environment variable is not set (service is optional).
    
    Returns:
        Path to the database as a string, or None if not configured
    """
    path = _default_ga_meta_db()
    return str(path) if path else None


def _default_vector_db() -> Optional[Path]:
    """
    Get vector database path from VECTOR_DB_PATH environment variable.
    
    Returns None if not set (vector DB is optional when using VECTOR_DB_URL).
    """
    env_value = os.environ.get("VECTOR_DB_PATH")
    if env_value:
        return Path(env_value)
    return None


def _default_vector_db_url() -> Optional[str]:
    """Get ChromaDB service URL if configured, otherwise None for local mode."""
    return os.environ.get("VECTOR_DB_URL")


class AviationAgentSettings(BaseSettings):
    """
    Deployment configuration for the aviation agent.

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ CONFIGURATION GUIDELINES                                                 │
    │                                                                          │
    │ This file (config.py) is for DEPLOYMENT/INFRASTRUCTURE settings:         │
    │   ✓ Database paths and connection strings                                │
    │   ✓ API keys and secrets                                                 │
    │   ✓ Feature flags for enabling/disabling entire services                 │
    │   ✓ Storage locations (checkpointer, logs, vector DB)                    │
    │   ✓ Anything that varies between dev/staging/prod                        │
    │                                                                          │
    │ Behavior configuration (behavior_config.py / JSON files) is for:         │
    │   ✓ LLM models, temperatures, prompts                                    │
    │   ✓ Feature flags that change agent logic (routing, RAG, reranking)     │
    │   ✓ Algorithm parameters (top_k, similarity thresholds)                  │
    │   ✓ Anything that affects "how the agent thinks"                         │
    │                                                                          │
    │ The key question: "Does this change how the agent thinks, or where       │
    │ data goes?" Behavior → JSON config. Infrastructure → .env                │
    └─────────────────────────────────────────────────────────────────────────┘
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # Master switch
    enabled: bool = Field(
        default=True,
        description="Feature flag that allows the FastAPI layer to disable the agent entirely.",
        alias="AVIATION_AGENT_ENABLED",
    )

    # Which behavior config to load
    agent_config_name: Optional[str] = Field(
        default="default",
        description="Name of agent behavior config file (without .json). Loads from configs/aviation_agent/",
        alias="AVIATION_AGENT_CONFIG",
    )

    # External RAG resources (optional)
    vector_db_path: Optional[Path] = Field(
        default=None,
        description="Path to local ChromaDB vector database for RAG retrieval.",
        alias="VECTOR_DB_PATH",
    )
    vector_db_url: Optional[str] = Field(
        default=None,
        description="URL to ChromaDB service for RAG retrieval. If set, takes precedence over vector_db_path.",
        alias="VECTOR_DB_URL",
    )

    # Checkpointer settings (conversation memory persistence)
    # This is infrastructure config because it determines WHERE state is stored,
    # not HOW the agent behaves. The same agent logic works with any storage backend.
    checkpointer_provider: str = Field(
        default="memory",
        description="Checkpointer backend: 'memory' (dev), 'sqlite' (persistent), 'none' (disabled)",
        alias="CHECKPOINTER_PROVIDER",
    )
    checkpointer_sqlite_path: Optional[str] = Field(
        default=None,
        description="Path to SQLite database for checkpointer (only used when provider='sqlite')",
        alias="CHECKPOINTER_SQLITE_PATH",
    )

    def build_tool_context(
        self,
        *,
        load_rules: bool = True,
        load_notifications: bool = True,
        load_ga_friendliness: bool = True,
    ) -> ToolContext:
        """
        Build or retrieve cached ToolContext.
        
        ToolContext is expensive to create (loads entire airport database + rules),
        so we cache it at the module level. The cache key includes load flags
        to ensure we create separate contexts for different configs.
        
        Args:
            load_rules: Load rules manager (default: True)
            load_notifications: Load notification service (default: True)
            load_ga_friendliness: Load GA friendliness service (default: True)
        """
        return _cached_tool_context(
            load_rules=load_rules,
            load_notifications=load_notifications,
            load_ga_friendliness=load_ga_friendliness,
        )


@lru_cache(maxsize=1)
def _cached_tool_context(
    load_rules: bool,
    load_notifications: bool,
    load_ga_friendliness: bool,
) -> ToolContext:
    """
    Cached ToolContext factory.
    
    ToolContext creation is expensive (loads entire airport database + rules),
    so we cache it at the module level. Only one ToolContext is created per unique
    combination of load flags.
    
    This matches the pattern used in:
    - mcp_server/main.py (global _tool_context created once at startup)
    - tests/tools/conftest.py (@lru_cache on tool_context fixture)
    """
    return ToolContext.create(
        load_airports=True,  # Always required
        load_rules=load_rules,
        load_notifications=load_notifications,
        load_ga_friendliness=load_ga_friendliness,
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

