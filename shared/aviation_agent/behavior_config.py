from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    model: Optional[str] = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    streaming: bool = False
    max_retries: int = Field(default=3, ge=0, le=10)
    request_timeout: int = Field(default=60, ge=5, le=300)  # seconds


class LLMsConfig(BaseModel):
    planner: LLMConfig
    formatter: LLMConfig
    router: LLMConfig
    rules: Optional[LLMConfig] = None  # None = use formatter


class RoutingConfig(BaseModel):
    """
    Legacy routing configuration.

    NOTE: Routing is deprecated. The planner now handles all tool selection directly,
    including rules tools (answer_rules_question, browse_rules, compare_rules_between_countries).
    This config is kept for backwards compatibility but has no effect.
    """
    enabled: bool = False  # Deprecated - routing is no longer used


class QueryReformulationConfig(BaseModel):
    enabled: bool = True


class RetrievalConfig(BaseModel):
    top_k: int = Field(default=5, gt=0, le=100)
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    rerank_candidates_multiplier: int = Field(default=2, gt=0)


class RAGConfig(BaseModel):
    embedding_model: str = "text-embedding-3-small"
    retrieval: RetrievalConfig = RetrievalConfig()


class CohereRerankingConfig(BaseModel):
    model: Literal["rerank-v3.5", "rerank-english-v3.0", "rerank-multilingual-v3.0"] = "rerank-v3.5"


class OpenAIRerankingConfig(BaseModel):
    model: str = "text-embedding-3-large"  # Uses embedding model for reranking


class RerankingConfig(BaseModel):
    enabled: bool = True
    provider: Literal["cohere", "openai", "none"] = "cohere"
    cohere: Optional[CohereRerankingConfig] = CohereRerankingConfig()
    openai: Optional[OpenAIRerankingConfig] = OpenAIRerankingConfig()


class NextQueryPredictionConfig(BaseModel):
    enabled: bool = True
    max_suggestions: int = Field(default=4, gt=0, le=20)


class ComparisonConfig(BaseModel):
    """
    Configuration for cross-country rule comparison feature.

    This feature uses answer embeddings to identify semantic differences
    between countries' rules, then uses LLM synthesis to explain differences.
    """
    enabled: bool = True

    # Embedding-based filtering parameters
    max_questions: int = Field(
        default=15,
        gt=0,
        le=100,
        description="Maximum questions to send to LLM for synthesis. "
                    "Set high (e.g., 100) to send all, low (e.g., 5) for aggressive filtering."
    )
    min_difference: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Minimum cosine difference threshold. "
                    "0.0 = include identical answers, 1.0 = only opposite answers."
    )
    send_all_threshold: int = Field(
        default=10,
        gt=0,
        description="If total questions <= this, send all regardless of difference score."
    )

    # LLM synthesis settings
    synthesis_model: Optional[str] = Field(
        default=None,
        description="Model for synthesis. None = use formatter model."
    )
    synthesis_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0
    )


class PromptsConfig(BaseModel):
    planner: str  # Path to prompt file, e.g., "prompts/planner_v1.md"
    formatter: str
    rules_agent: str
    router: str
    comparison_synthesis: Optional[str] = None  # Optional: for cross-country comparison


class ExamplesConfig(BaseModel):
    planner: str  # Path to planner examples file, e.g., "examples/planner_examples_v1.json"


class ToolsConfig(BaseModel):
    """Configuration for tool description file paths."""
    search_airports: Optional[str] = None
    find_airports_near_location: Optional[str] = None
    find_airports_near_route: Optional[str] = None
    get_airport_details: Optional[str] = None
    get_airport_pricing: Optional[str] = None
    get_pilot_reviews: Optional[str] = None
    get_fuel_prices: Optional[str] = None
    list_rules_for_country: Optional[str] = None
    compare_rules_between_countries: Optional[str] = None
    get_notification_for_airport: Optional[str] = None


class AgentBehaviorConfig(BaseModel):
    """
    Agent behavior configuration - controls HOW the agent thinks and acts.

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ CONFIGURATION GUIDELINES                                                 │
    │                                                                          │
    │ This file (behavior_config.py) is for BEHAVIOR settings:                 │
    │   ✓ LLM models, temperatures, prompts                                    │
    │   ✓ Feature flags that change agent logic (routing, RAG, reranking)     │
    │   ✓ Algorithm parameters (top_k, similarity thresholds)                  │
    │   ✓ Anything that affects "how the agent thinks"                         │
    │                                                                          │
    │ Environment variables (config.py / .env) are for DEPLOYMENT settings:    │
    │   ✓ Database paths and connection strings                                │
    │   ✓ API keys and secrets                                                 │
    │   ✓ Feature flags for enabling/disabling entire services                 │
    │   ✓ Storage locations (checkpointer, logs, vector DB)                    │
    │   ✓ Anything that varies between dev/staging/prod                        │
    │                                                                          │
    │ The key question: "Does this change how the agent thinks, or where       │
    │ data goes?" Behavior → JSON config. Infrastructure → .env                │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    version: str = "1.0"
    name: Optional[str] = None
    description: Optional[str] = None

    llms: LLMsConfig
    routing: RoutingConfig
    query_reformulation: QueryReformulationConfig
    rag: RAGConfig
    reranking: RerankingConfig
    next_query_prediction: NextQueryPredictionConfig
    comparison: ComparisonConfig = ComparisonConfig()  # Cross-country comparison
    prompts: PromptsConfig
    examples: ExamplesConfig
    tools: Optional[ToolsConfig] = None  # Optional: tool description file paths

    _config_dir: Optional[Path] = None  # Internal: set by from_file()

    def load_prompt(self, prompt_key: str) -> str:
        """Load prompt text from file."""
        prompt_path = getattr(self.prompts, prompt_key, None)
        if not prompt_path:
            raise ValueError(f"Prompt '{prompt_key}' not found in config")

        # Resolve relative to config directory
        if not hasattr(self, "_config_dir") or self._config_dir is None:
            raise ValueError("Config directory not set. Use from_file() to load config.")

        full_path = self._config_dir / prompt_path
        if not full_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {full_path}")

        return full_path.read_text(encoding="utf-8")

    def load_tool_description(self, tool_name: str) -> Optional[str]:
        """Load tool description from file if configured.
        
        Args:
            tool_name: Name of the tool (e.g., "search_airports")
            
        Returns:
            Tool description text from file, or None if not configured.
        """
        if not self.tools:
            return None
            
        tool_path = getattr(self.tools, tool_name, None)
        if not tool_path:
            return None
            
        # Resolve relative to config directory
        if not hasattr(self, "_config_dir") or self._config_dir is None:
            return None
            
        full_path = self._config_dir / tool_path
        if not full_path.exists():
            logger.warning(f"Tool description file not found: {full_path}")
            return None
            
        return full_path.read_text(encoding="utf-8").strip()

    def load_examples(self, component: str = "planner") -> list[dict[str, str]]:
        """
        Load examples from JSON file for the specified component.
        
        Args:
            component: Component name (e.g., "planner")
        
        Returns:
            List of example dicts with 'question' and 'answer' keys.
            Returns empty list if file not found or invalid.
        """
        # Resolve relative to config directory
        if not hasattr(self, "_config_dir") or self._config_dir is None:
            raise ValueError("Config directory not set. Use from_file() to load config.")

        examples_path = getattr(self.examples, component, None)
        if not examples_path:
            logger.warning(f"Examples path not configured for component '{component}'")
            return []

        full_path = self._config_dir / examples_path
        if not full_path.exists():
            logger.warning(f"Examples file not found: {full_path}")
            return []

        try:
            with open(full_path, encoding="utf-8") as f:
                examples = json.load(f)
            if not isinstance(examples, list):
                logger.warning(f"Examples file must contain a JSON array, got {type(examples)}")
                return []
            return examples
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse examples file {full_path}: {e}")
            return []

    @classmethod
    def from_file(cls, path: Path) -> "AgentBehaviorConfig":
        """Load config from JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        config = cls(**data)
        # Store config directory for prompt loading
        config._config_dir = path.parent
        return config

    @classmethod
    def default(cls) -> "AgentBehaviorConfig":
        """Create default config matching current hardcoded values."""
        return cls(
            version="1.0",
            name="default",
            description="Default aviation agent configuration",
            llms=LLMsConfig(
                planner=LLMConfig(model=None, temperature=0.0, streaming=False),
                formatter=LLMConfig(model=None, temperature=0.0, streaming=True),
                router=LLMConfig(model="gpt-4o-mini", temperature=0.0, streaming=False),
                rules=None,  # Uses formatter
            ),
            routing=RoutingConfig(enabled=False),  # Deprecated - routing is no longer used
            query_reformulation=QueryReformulationConfig(enabled=True),
            rag=RAGConfig(
                embedding_model="text-embedding-3-small",
                retrieval=RetrievalConfig(top_k=5, similarity_threshold=0.3, rerank_candidates_multiplier=2),
            ),
            reranking=RerankingConfig(
                enabled=True,
                provider="cohere",
                cohere=CohereRerankingConfig(model="rerank-v3.5"),
                openai=OpenAIRerankingConfig(model="text-embedding-3-large"),
            ),
            next_query_prediction=NextQueryPredictionConfig(enabled=True, max_suggestions=4),
            comparison=ComparisonConfig(
                enabled=True,
                max_questions=15,
                min_difference=0.1,
                send_all_threshold=10,
            ),
            prompts=PromptsConfig(
                planner="prompts/planner_v1.md",
                formatter="prompts/formatter_v1.md",
                rules_agent="prompts/rules_agent_v1.md",
                router="prompts/router_v1.md",
            ),
            examples=ExamplesConfig(
                planner="examples/planner_examples_v1.json",
            ),
        )

