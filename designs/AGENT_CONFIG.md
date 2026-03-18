# Aviation Agent Configuration

> JSON-based behavior configuration, environment variables, and prompt management.

## Quick Reference

| File | Purpose |
|------|---------|
| `shared/aviation_agent/config.py` | Settings and config loading |
| `shared/aviation_agent/behavior_config.py` | Pydantic schema for JSON config |
| `shared/aviation_agent/adapters/langgraph_runner.py` | Provider factory (`_resolve_llm()`, `_PROVIDER_REGISTRY`) |
| `configs/aviation_agent/default.json` | Default behavior config (OpenAI) |
| `configs/aviation_agent/anthropic.json` | Anthropic Claude config |
| `configs/aviation_agent/gemini.json` | Google Gemini config |
| `configs/aviation_agent/prompts/` | System prompt files |

**Key Exports:**
- `get_settings()` - Environment-based settings
- `get_behavior_config()` - JSON-based behavior config
- `AgentBehaviorConfig` - Pydantic config schema

**Prerequisites:** Read `AGENT_ARCHITECTURE.md` first.

---

## Two-Tier Configuration

**Key question: "Does this change how the agent thinks, or where data goes?"**

| Category | Location | Examples |
|----------|----------|----------|
| **Behavior** (how agent thinks) | JSON config files | LLM models, temperatures, prompts, RAG params |
| **Infrastructure** (where data goes) | Environment variables | DB paths, API keys, feature flags |

### Why This Separation?

- **Checkpointer** → `.env` (WHERE state is stored, not HOW agent behaves)
- **LLM models** → JSON (HOW the agent thinks and responds)
- **Database paths** → `.env` (deployment-specific, may contain secrets)
- **Prompts** → Markdown files (easy to edit, version controlled)

---

## Environment Variables

Infrastructure and deployment settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `AVIATION_AGENT_ENABLED` | Feature flag | `false` |
| `AVIATION_AGENT_CONFIG` | Config file name (without `.json`) | `"default"` |
| `VECTOR_DB_PATH` | Local ChromaDB path | `"cache/rules_vector_db"` |
| `VECTOR_DB_URL` | Remote ChromaDB URL | – |
| `CHECKPOINTER_PROVIDER` | Memory backend: `memory`, `sqlite`, `none` | `"memory"` |
| `CHECKPOINTER_SQLITE_PATH` | SQLite DB path | `"cache/checkpointer.db"` |
| `AIRPORTS_DB` | Airports database path | – |
| `RULES_JSON` | Rules JSON path | – |
| `COHERE_API_KEY` | Cohere API key (for reranking) | – |
| `OPENAI_API_KEY` | OpenAI API key | – |
| `ANTHROPIC_API_KEY` | Anthropic API key | – |
| `GOOGLE_API_KEY` | Google API key | – |

---

## Behavior Configuration

JSON files in `configs/aviation_agent/`:

### Full Schema

```json
{
  "version": "1.0",
  "name": "default",
  "description": "Default aviation agent configuration",

  "llms": {
    "planner": {
      "provider": "openai",
      "model": null,
      "temperature": 0.0,
      "streaming": false,
      "max_retries": 3,
      "request_timeout": 60
    },
    "formatter": {
      "provider": "openai",
      "model": null,
      "temperature": 0.0,
      "streaming": true
    },
    "router": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "temperature": 0.0,
      "streaming": false
    },
    "rules": null
  },

  "routing": {
    "enabled": true
  },

  "query_reformulation": {
    "enabled": true
  },

  "rag": {
    "embedding_model": "text-embedding-3-small",
    "retrieval": {
      "top_k": 5,
      "similarity_threshold": 0.3,
      "rerank_candidates_multiplier": 2
    }
  },

  "reranking": {
    "enabled": true,
    "provider": "cohere",
    "cohere": {"model": "rerank-v3.5"},
    "openai": {"model": "text-embedding-3-large"}
  },

  "next_query_prediction": {
    "enabled": true,
    "max_suggestions": 4
  },

  "comparison": {
    "max_questions": 15,
    "min_difference": 0.1
  },

  "prompts": {
    "planner": "prompts/planner_v1.md",
    "formatter": "prompts/formatter_v1.md",
    "rules_agent": "prompts/rules_agent_v1.md",
    "router": "prompts/router_v1.md",
    "comparison_synthesis": "prompts/comparison_synthesis_v1.md"
  }
}
```

### Configuration Sections

#### LLMs

| Component | Purpose | Default Model |
|-----------|---------|---------------|
| `planner` | Tool selection | env var / `gpt-4o` |
| `formatter` | Answer synthesis | env var / `gpt-4o` |
| `router` | Query classification | `gpt-4o-mini` |
| `rules` | Rules synthesis | uses `formatter` |

**Per-component settings:**
- `provider`: LLM provider — `"openai"`, `"anthropic"`, or `"google"` (default: `"openai"`)
- `model`: Model name or `null` (use env var)
- `temperature`: 0.0-2.0 (0.0 = deterministic)
- `streaming`: Enable streaming (formatter only)
- `max_retries`: Retry count for transient failures (default: 3)
- `request_timeout`: Timeout per request in seconds (default: 60)

**Multi-Provider Support:**

Provider resolution is handled by `_PROVIDER_REGISTRY` in `langgraph_runner.py`. Each provider maps to a LangChain class, required API key env var, and provider-specific kwargs. All providers accept `model=` and `timeout=` as common constructor params.

| Provider | LangChain Class | API Key | Notes |
|----------|----------------|---------|-------|
| `openai` | `ChatOpenAI` | `OPENAI_API_KEY` | Needs `stream_usage=True` for streaming token tracking |
| `anthropic` | `ChatAnthropic` | `ANTHROPIC_API_KEY` | |
| `google` | `ChatGoogleGenerativeAI` | `GOOGLE_API_KEY` | |

#### RAG

```json
"rag": {
  "embedding_model": "text-embedding-3-small",
  "retrieval": {
    "top_k": 5,
    "similarity_threshold": 0.3,
    "rerank_candidates_multiplier": 2
  }
}
```

#### Reranking

| Provider | Description |
|----------|-------------|
| `cohere` | Specialized rerank models (best quality) |
| `openai` | Embedding similarity (no extra API cost) |
| `none` | Disable reranking |

---

## Prompt Management

Prompts stored as markdown in `configs/aviation_agent/prompts/`:

```
prompts/
  planner_v1.md           # Tool selection prompt
  formatter_v1.md         # Answer synthesis prompt
  comparison_synthesis_v1.md  # Comparison prompt
  router_v1.md            # Query classification prompt
  rules_agent_v1.md       # Rules synthesis prompt
```

### Loading Prompts

```python
# In behavior config
prompt_content = behavior_config.load_prompt("formatter")

# Resolves: configs/aviation_agent/prompts/formatter_v1.md
```

### Versioned Prompts

Use versioned filenames for A/B testing:

```json
{
  "prompts": {
    "formatter": "prompts/formatter_v2_concise.md"
  }
}
```

---

## Configuration Loading

### Cached Loading

```python
@lru_cache(maxsize=1)
def get_settings() -> AviationAgentSettings:
    """Load settings from environment (cached)."""
    return AviationAgentSettings()


@lru_cache(maxsize=10)
def get_behavior_config(config_name: str = None) -> AgentBehaviorConfig:
    """Load behavior config from JSON (cached)."""
    config_name = config_name or os.getenv("AVIATION_AGENT_CONFIG", "default")
    config_path = Path(f"configs/aviation_agent/{config_name}.json")

    if config_path.exists():
        return AgentBehaviorConfig.parse_file(config_path)

    # Fallback to defaults
    return AgentBehaviorConfig()
```

### LLM Resolution Priority

```
1. Explicitly passed LLM instance (testing)
2. Model from behavior config
3. Environment variable override
4. Runtime error
```

---

## Creating Configurations

### Copy and Modify

```bash
# Create new config
cp configs/aviation_agent/default.json configs/aviation_agent/experiment.json

# Edit experiment.json

# Use it
export AVIATION_AGENT_CONFIG=experiment
```

### Example: Anthropic Provider

```json
{
  "llms": {
    "planner": {
      "provider": "anthropic",
      "model": "claude-sonnet-4-6"
    },
    "formatter": {
      "provider": "anthropic",
      "model": "claude-sonnet-4-6",
      "streaming": true
    }
  }
}
```

### Example: Test Different Models

```json
{
  "llms": {
    "formatter": {
      "model": "gpt-4o",
      "temperature": 0.0
    },
    "planner": {
      "model": "gpt-4o-mini",
      "temperature": 0.0
    }
  }
}
```

### Example: Disable Features

```json
{
  "routing": {"enabled": false},
  "reranking": {"enabled": false},
  "next_query_prediction": {"enabled": false}
}
```

### Example: Different Reranker

```json
{
  "reranking": {
    "provider": "openai",
    "openai": {"model": "text-embedding-3-large"}
  }
}
```

---

## Directory Structure

```
configs/aviation_agent/
  default.json              # Default configuration (OpenAI)
  anthropic.json            # Anthropic Claude config
  gemini.json               # Google Gemini config
  prompts/
    planner_v1.md
    formatter_v1.md
    comparison_synthesis_v1.md
    router_v1.md
    rules_agent_v1.md
    ab_judge_v1.md          # LLM judge prompt for A/B comparison
```

---

## Component Integration

All components automatically use behavior config:

| Component | Config Used |
|-----------|-------------|
| `graph.py` | routing, RAG, reranking, next query |
| `planning.py` | planner prompt |
| `formatting.py` | formatter prompt |
| `routing.py` | router model and prompt |
| `rules_rag.py` | RAG settings, reranking |
| `langgraph_runner.py` | LLM models, providers, temperatures |

---

## Testing with Configs

```python
# Use specific config in tests
from shared.aviation_agent.config import get_behavior_config

config = get_behavior_config("test")

# Or inject mock LLM directly
from langchain.chat_models.fake import FakeChatModel

mock_llm = FakeChatModel(responses=["test response"])
planner = build_planner_runnable(llm=mock_llm, tools=tools)
```

---

## Debug CLI

```bash
# Use specific config/provider
python tools/avdbg.py "Find airports" --config anthropic
python tools/avdbg.py "Find airports" --config gemini --plan

# Show current config
python tools/avdbg.py "Find airports" -v
# Shows: Using config: default
```

---

## A/B Testing Tools

### Planner Behavior Test (`tools/ab_test.py`)

Runs planner test cases across configs, compares tool selection accuracy:

```bash
python tools/ab_test.py --configs default anthropic gemini
python tools/ab_test.py --configs default anthropic --cases 5
python tools/ab_test.py --configs default anthropic --output results/comparison.csv
```

Uses shared test utilities from `tests/aviation_agent/test_utils.py`.

### LLM Judge Comparison (`tools/ab_compare.py`)

Runs full agent queries through two configs and uses a judge LLM to compare answers on accuracy, completeness, clarity, and helpfulness (1-5 scale each):

```bash
python tools/ab_compare.py --configs default anthropic --query "Find airports near Paris with AVGAS"
python tools/ab_compare.py --configs default anthropic --queries queries.txt
python tools/ab_compare.py --configs default anthropic --judge openai
```

Judge prompt: `configs/aviation_agent/prompts/ab_judge_v1.md`

---

## Pydantic Schema

```python
class LLMConfig(BaseModel):
    provider: str = "openai"  # "openai", "anthropic", "google"
    model: Optional[str] = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    streaming: bool = False
    max_retries: int = Field(default=3, ge=0, le=10)
    request_timeout: int = Field(default=60, ge=5, le=300)


class LLMsConfig(BaseModel):
    planner: LLMConfig
    formatter: LLMConfig
    router: LLMConfig
    rules: Optional[LLMConfig] = None  # None = use formatter


class RetrievalConfig(BaseModel):
    top_k: int = 5
    similarity_threshold: float = 0.3
    rerank_candidates_multiplier: int = 2


class AgentBehaviorConfig(BaseModel):
    version: str = "1.0"
    name: str = "default"
    llms: LLMsConfig = LLMsConfig()
    routing: RoutingConfig = RoutingConfig()
    query_reformulation: QueryReformulationConfig = QueryReformulationConfig()
    rag: RAGConfig = RAGConfig()
    reranking: RerankingConfig = RerankingConfig()
    next_query_prediction: NextQueryConfig = NextQueryConfig()
    comparison: ComparisonConfig = ComparisonConfig()
    prompts: PromptsConfig = PromptsConfig()

    def load_prompt(self, key: str) -> str:
        """Load prompt content from file."""
        prompt_path = getattr(self.prompts, key)
        full_path = Path("configs/aviation_agent") / prompt_path
        return full_path.read_text()
```

---

## Best Practices

1. **Use defaults** — Only override what you need to change
2. **Version prompts** — Use v1, v2 suffixes for A/B testing
3. **Keep secrets in env** — Never put API keys in JSON
4. **Test with configs** — Use `--config test` for reproducible tests
5. **Document changes** — Add description field to custom configs
