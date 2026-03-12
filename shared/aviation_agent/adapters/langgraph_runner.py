from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import List, Optional, Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from ..config import AviationAgentSettings, get_settings, get_behavior_config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_checkpointer(provider: str, sqlite_path: Optional[str] = None) -> Any:
    """
    Get or create a checkpointer instance (cached for reuse).

    The checkpointer must be shared across requests to enable
    multi-turn conversations. InMemorySaver loses state if recreated.

    Args:
        provider: "memory", "sqlite", or "none"
        sqlite_path: Path to SQLite database (only for sqlite provider)

    Returns:
        Checkpointer instance or None if disabled
    """
    if provider == "none":
        logger.info("Checkpointing disabled")
        return None

    if provider == "memory":
        from langgraph.checkpoint.memory import MemorySaver
        logger.info("Using InMemorySaver checkpointer (dev mode)")
        return MemorySaver()

    if provider == "sqlite":
        if not sqlite_path:
            raise ValueError("sqlite_path required for sqlite checkpointer")
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            logger.info(f"Using SqliteSaver checkpointer: {sqlite_path}")
            return SqliteSaver.from_conn_string(sqlite_path)
        except ImportError:
            raise RuntimeError(
                "SqliteSaver requires langgraph-checkpoint-sqlite. "
                "Install with: pip install langgraph-checkpoint-sqlite"
            )

    raise ValueError(f"Unknown checkpointer provider: {provider}")


def get_checkpointer(settings: AviationAgentSettings) -> Any:
    """
    Get checkpointer based on settings.

    Args:
        settings: AviationAgentSettings with checkpointer_provider and checkpointer_sqlite_path

    Returns:
        Checkpointer instance or None if disabled
    """
    provider = settings.checkpointer_provider
    if provider == "none":
        return None

    return _get_checkpointer(provider, settings.checkpointer_sqlite_path)


from ..execution import ToolRunner
from ..formatting import build_formatter_chain
from ..graph import _build_agent_graph
from ..planning import build_planner_runnable
from ..state import AgentState
from ..tools import AviationToolClient


def build_agent(
    *,
    settings: Optional[AviationAgentSettings] = None,
    planner_llm: Optional[Runnable] = None,
    formatter_llm: Optional[Runnable] = None,
):
    """
    Build the aviation agent graph.

    Args:
        settings: AviationAgentSettings instance (uses default if None)
        planner_llm: LLM for planning (testing only - uses behavior_config in production)
        formatter_llm: LLM for formatting (testing only - uses behavior_config in production)

    Feature flags like next_query_prediction are controlled via
    behavior_config JSON files, not function parameters.
    """
    settings = settings or get_settings()
    if not settings.enabled:
        raise RuntimeError("Aviation agent is disabled via AVIATION_AGENT_ENABLED flag.")

    # Load behavior config for LLM settings
    behavior_config = get_behavior_config(settings.agent_config_name)

    # Resolve LLMs from behavior config (no env var fallback - all config in JSON)
    planner_llm = _resolve_llm(
        planner_llm,
        behavior_config.llms.planner.model,
        role="planner",
        provider=behavior_config.llms.planner.provider,
        config_name=settings.agent_config_name,
        temperature=behavior_config.llms.planner.temperature,
        streaming=behavior_config.llms.planner.streaming,
        max_retries=behavior_config.llms.planner.max_retries,
        request_timeout=behavior_config.llms.planner.request_timeout,
    )

    formatter_llm = _resolve_llm(
        formatter_llm,
        behavior_config.llms.formatter.model,
        role="formatter",
        provider=behavior_config.llms.formatter.provider,
        config_name=settings.agent_config_name,
        temperature=behavior_config.llms.formatter.temperature,
        streaming=behavior_config.llms.formatter.streaming,
        max_retries=behavior_config.llms.formatter.max_retries,
        request_timeout=behavior_config.llms.formatter.request_timeout,
    )

    tool_context = settings.build_tool_context()
    tool_client = AviationToolClient(tool_context)
    tool_runner = ToolRunner(tool_client)
    # Only expose LLM-visible tools to planner (filter out internal/MCP-only tools)
    llm_tools = tuple(t for t in tool_client.tools.values() if t.expose_to_llm)

    # Get available tags from rules manager for dynamic prompt injection
    available_tags = None
    if tool_context.rules_manager:
        available_tags = tool_context.rules_manager.get_available_tags()

    planner = build_planner_runnable(planner_llm, llm_tools, available_tags=available_tags)

    # Create checkpointer for conversation memory (from settings, not behavior config)
    checkpointer = get_checkpointer(settings)

    graph = _build_agent_graph(
        planner,
        tool_runner,
        formatter_llm,
        behavior_config=behavior_config,
        checkpointer=checkpointer,
    )
    return graph


def run_aviation_agent(
    messages: List[BaseMessage],
    *,
    settings: Optional[AviationAgentSettings] = None,
    planner_llm: Optional[Runnable] = None,
    formatter_llm: Optional[Runnable] = None,
    persona_id: Optional[str] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> AgentState:
    """
    Run the aviation agent on a list of messages.

    Args:
        messages: List of messages to process
        settings: AviationAgentSettings instance (uses default if None)
        planner_llm: LLM for planning (testing only - uses behavior_config in production)
        formatter_llm: LLM for formatting (testing only - uses behavior_config in production)
        persona_id: Optional persona ID for the agent
        session_id: Optional session ID for tracing
        thread_id: Optional thread ID for conversation memory. When provided with
            checkpointing enabled, enables multi-turn conversation resume.
    """
    graph = build_agent(
        settings=settings,
        planner_llm=planner_llm,
        formatter_llm=formatter_llm,
    )
    initial_state = {"messages": messages}
    if persona_id:
        initial_state["persona_id"] = persona_id

    # Generate run ID for LangSmith tracing (always unique per invocation)
    run_id = str(uuid.uuid4())

    # Generate thread_id if not provided (checkpointing requires it)
    # This enables conversation memory even for single-turn requests
    effective_thread_id = thread_id or f"thread_{uuid.uuid4().hex[:12]}"

    # Config for LangSmith observability and checkpointing
    config = {
        "run_id": run_id,  # Explicit run_id for LangSmith feedback tracking
        "run_name": f"aviation-agent-{run_id[:8]}",
        "tags": ["aviation-agent", "sync"],
        "metadata": {
            "session_id": session_id,
            "persona_id": persona_id,
            "thread_id": effective_thread_id,
            "agent_version": "1.0",
        },
        # thread_id is required when checkpointing is enabled
        "configurable": {"thread_id": effective_thread_id},
    }

    result = graph.invoke(initial_state, config=config)
    return result


_PROVIDER_REGISTRY = {
    "openai": {
        "class_path": "langchain_openai.ChatOpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "extra_kwargs": lambda streaming: {"stream_usage": streaming},
    },
    "anthropic": {
        "class_path": "langchain_anthropic.ChatAnthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "extra_kwargs": lambda streaming: {"cache_control": {"type": "ephemeral"}},
    },
    "google": {
        "class_path": "langchain_google_genai.ChatGoogleGenerativeAI",
        "api_key_env": "GOOGLE_API_KEY",
        "extra_kwargs": lambda streaming: {},
    },
}


def _resolve_llm(
    llm: Optional[Runnable],
    model_name: Optional[str],
    role: str,
    *,
    provider: str = "openai",
    config_name: Optional[str] = None,
    temperature: float = 0.0,
    streaming: bool = False,
    max_retries: int = 3,
    request_timeout: int = 60,
) -> Runnable:
    """
    Resolve an LLM instance with retry configuration.

    Supports multiple providers (openai, anthropic, google) via a registry.
    Each provider's LangChain integration is imported lazily.

    Args:
        llm: Existing LLM instance (returned as-is if provided)
        model_name: Model name from config
        role: Role name for error messages (planner, formatter, etc.)
        provider: LLM provider name ("openai", "anthropic", "google")
        config_name: Config file name for error messages
        temperature: LLM temperature setting
        streaming: Whether to enable streaming
        max_retries: Number of retries for transient failures (from config)
        request_timeout: Timeout per request in seconds (from config)

    Returns:
        Configured LLM instance with retry support
    """
    if llm is not None:
        return llm
    if not model_name:
        config_hint = f" in configs/aviation_agent/{config_name}.json" if config_name else ""
        raise RuntimeError(
            f"No {role} LLM configured. Set llms.{role}.model{config_hint} or pass an llm instance."
        )

    if provider not in _PROVIDER_REGISTRY:
        raise RuntimeError(
            f"Unknown LLM provider '{provider}' for {role}. "
            f"Supported providers: {', '.join(sorted(_PROVIDER_REGISTRY))}"
        )

    reg = _PROVIDER_REGISTRY[provider]

    # Check API key is available
    import os
    api_key_env = reg["api_key_env"]
    if not os.environ.get(api_key_env):
        raise RuntimeError(
            f"{api_key_env} environment variable is required for provider '{provider}' ({role} LLM). "
            f"Set it in your .env file or environment."
        )

    # Dynamically import the provider class
    module_path, class_name = reg["class_path"].rsplit(".", 1)
    try:
        import importlib
        module = importlib.import_module(module_path)
        llm_class = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            f"Cannot import {reg['class_path']} for {role} LLM. "
            f"Install the required package: pip install {module_path.replace('.', '-')}"
        ) from exc

    # Build common kwargs
    kwargs = {
        "model": model_name,
        "temperature": temperature,
        "streaming": streaming,
        "max_retries": max_retries,
        "timeout": request_timeout,
    }
    # Add provider-specific kwargs
    kwargs.update(reg["extra_kwargs"](streaming))

    llm_instance = llm_class(**kwargs)

    logger.debug(
        f"Created {role} LLM: provider={provider}, model={model_name}, "
        f"max_retries={max_retries}, timeout={request_timeout}s"
    )

    return llm_instance

