# Aviation Agent Configuration Guide

## Overview

The aviation agent uses a JSON-based configuration system that allows you to control all behavioral settings without code changes. This enables easy A/B testing, experimentation, and prompt versioning.

**Key Features:**
- All behavioral settings in one JSON file
- System prompts stored in separate markdown files
- Easy switching between configs via environment variable
- Type-safe validation with Pydantic
- Backward compatible with environment variables

## Quick Start

### 1. Select a Configuration

Set the `AVIATION_AGENT_CONFIG` environment variable to the name of your config file (without `.json`):

```bash
export AVIATION_AGENT_CONFIG=default
```

If not set, defaults to `default.json`.

### 2. Create a New Configuration

Copy `data/aviation_agent_configs/default.json` to create a new config:

```bash
cp data/aviation_agent_configs/default.json data/aviation_agent_configs/my_experiment.json
```

Edit `my_experiment.json` to customize settings, then use:

```bash
export AVIATION_AGENT_CONFIG=my_experiment
```

### 3. Modify Prompts

Edit prompt files in `data/aviation_agent_configs/prompts/`:
- `planner_v1.md` - Planner system prompt
- `formatter_v1.md` - Formatter system prompt
- `rules_agent_v1.md` - Rules agent system prompt
- `router_v1.md` - Router system prompt

Reference different prompt versions in your config:

```json
{
  "prompts": {
    "formatter": "prompts/formatter_v2_concise.md"
  }
}
```

## Configuration Schema

### Full Configuration Structure

```json
{
  "version": "1.0",
  "name": "default",
  "description": "Default aviation agent configuration",
  
  "llms": {
    "planner": {
      "model": null,
      "temperature": 0.0,
      "streaming": false
    },
    "formatter": {
      "model": null,
      "temperature": 0.0,
      "streaming": true
    },
    "router": {
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
    "cohere": {
      "model": "rerank-v3.5"
    },
    "openai": {
      "model": "text-embedding-3-large"
    }
  },
  
  "next_query_prediction": {
    "enabled": true,
    "max_suggestions": 4
  },
  
  "prompts": {
    "planner": "prompts/planner_v1.md",
    "formatter": "prompts/formatter_v1.md",
    "rules_agent": "prompts/rules_agent_v1.md",
    "router": "prompts/router_v1.md"
  }
}
```

### Configuration Sections

#### LLMs

Controls model selection, temperature, and streaming for each component:

- **planner**: LLM for planning tool execution (null = use environment variable)
- **formatter**: LLM for formatting responses (null = use environment variable)
- **router**: LLM for query routing (default: `gpt-4o-mini`)
- **rules**: LLM for rules synthesis (null = use formatter model)

Each LLM config supports:
- `model`: Model name (e.g., `"gpt-4o"`, `"gpt-4o-mini"`) or `null` to use env var
- `temperature`: 0.0-2.0, controls randomness (0.0 = deterministic)
- `streaming`: Whether to stream responses

#### Routing

- `enabled`: Enable/disable query routing (rules vs database vs both)

#### Query Reformulation

- `enabled`: Enable/disable query reformulation for better RAG matching

#### RAG (Retrieval-Augmented Generation)

- `embedding_model`: Embedding model name (e.g., `"text-embedding-3-small"`)
- `retrieval.top_k`: Number of documents to retrieve (default: 5)
- `retrieval.similarity_threshold`: Minimum similarity score (0.0-1.0, default: 0.3)
- `retrieval.rerank_candidates_multiplier`: Multiply top_k for reranking candidates (default: 2)

#### Reranking

- `enabled`: Enable/disable reranking
- `provider`: `"cohere"`, `"openai"`, or `"none"`
- `cohere.model`: Cohere model (`"rerank-v3.5"`, `"rerank-english-v3.0"`, `"rerank-multilingual-v3.0"`)
- `openai.model`: OpenAI embedding model for reranking (e.g., `"text-embedding-3-large"`)

**Reranking Providers:**
- **Cohere**: Specialized rerank models via API (requires `COHERE_API_KEY`)
- **OpenAI**: Uses embeddings with cosine similarity (requires `OPENAI_API_KEY`)
- **None**: Disables reranking, uses initial retrieval order

#### Next Query Prediction

- `enabled`: Enable/disable next query suggestions
- `max_suggestions`: Maximum number of suggestions (1-20, default: 4)

#### Prompts

File paths to system prompt markdown files (relative to config directory):
- `planner`: Planner system prompt
- `formatter`: Formatter system prompt
- `rules_agent`: Rules agent system prompt
- `router`: Router system prompt

## Directory Structure

```
data/
  aviation_agent_configs/
    default.json              # Default configuration
    experiment_a.json          # A/B test variant A
    experiment_b.json          # A/B test variant B
    high_creativity.json       # Higher temperature settings
    no_reranking.json          # Disabled reranking
    multilingual.json          # Multilingual reranking model
    prompts/
      planner_v1.md            # Planner system prompt
      planner_v2.md            # Alternative planner prompt
      formatter_v1.md          # Formatter system prompt
      formatter_v2.md          # Alternative formatter prompt
      rules_agent_v1.md        # Rules agent system prompt
      router_v1.md             # Router system prompt
```

## Environment Variables

**Deployment-specific settings** (not in JSON config):
- `VECTOR_DB_PATH` - Path to local ChromaDB
- `VECTOR_DB_URL` - URL to ChromaDB service
- `AIRPORTS_DB` - Path to airports database
- `RULES_JSON` - Path to rules JSON file
- `COHERE_API_KEY` - Cohere API key (for reranking)
- `OPENAI_API_KEY` - OpenAI API key (for LLMs and embeddings)

**Config selection:**
- `AVIATION_AGENT_CONFIG` - Name of config file to use (without `.json`)

**Legacy LLM overrides** (still work, but prefer config file):
- `AVIATION_AGENT_PLANNER_MODEL` - Planner model override
- `AVIATION_AGENT_FORMATTER_MODEL` - Formatter model override
- `ROUTER_MODEL` - Router model override

## Example Use Cases

### Test Different LLM Models

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

### Test Higher Temperature for Creativity

```json
{
  "llms": {
    "formatter": {
      "model": "gpt-4o",
      "temperature": 0.3
    }
  }
}
```

### Test Different Rerank Providers

**Cohere (multilingual):**
```json
{
  "reranking": {
    "provider": "cohere",
    "cohere": {
      "model": "rerank-multilingual-v3.0"
    }
  }
}
```

**OpenAI:**
```json
{
  "reranking": {
    "provider": "openai",
    "openai": {
      "model": "text-embedding-3-large"
    }
  }
}
```

**Disable reranking:**
```json
{
  "reranking": {
    "provider": "none"
  }
}
```

### Test Different Retrieval Parameters

```json
{
  "rag": {
    "retrieval": {
      "top_k": 10,
      "similarity_threshold": 0.2
    }
  }
}
```

### A/B Test Prompts

```json
{
  "prompts": {
    "formatter": "prompts/formatter_v2_concise.md"
  }
}
```

### Disable Features

```json
{
  "routing": {
    "enabled": false
  },
  "reranking": {
    "enabled": false
  },
  "next_query_prediction": {
    "enabled": false
  }
}
```

## Implementation Details

### Configuration Loading

Configs are loaded via `get_behavior_config()` in `shared/aviation_agent/config.py`:
- Loads from `data/aviation_agent_configs/{config_name}.json`
- Falls back to `default.json` if specified config not found
- Falls back to hardcoded defaults if no config files exist
- Cached per config name (supports multiple configs in parallel)

### Component Integration

All components automatically use the behavior config:
- **graph.py**: Uses config for routing, RAG, reranking, next query prediction
- **planning.py**: Loads planner prompt from config
- **formatting.py**: Loads formatter prompt from config
- **rules_agent.py**: Loads rules agent prompt from config
- **routing.py**: Loads router prompt from config
- **langgraph_runner.py**: Uses config for LLM models and temperatures
- **rules_rag.py**: Uses config for reranking provider and retrieval parameters

### Reranking Implementation

**Cohere Reranker:**
- Direct HTTP API calls to `https://api.cohere.com/v2/rerank`
- No SDK dependency
- Returns documents with `rerank_score` field

**OpenAI Reranker:**
- Uses OpenAI embeddings with cosine similarity
- Embeds query and all documents
- Computes similarity scores and sorts
- Returns documents with `rerank_score` field

**Selection:**
- If `reranking.provider == "cohere"`: Uses `CohereReranker` with `cohere.model`
- If `reranking.provider == "openai"`: Uses `OpenAIReranker` with `openai.model`
- If `reranking.provider == "none"`: No reranking (uses initial retrieval order)

## Summary

### What's in Config (Behavioral Settings)

- LLM models and temperatures
- Feature flags (routing, reformulation, reranking, next query prediction)
- Embedding model selection
- Retrieval parameters (top_k, similarity_threshold)
- Reranking provider and model selection
- System prompts for all components

### What's NOT in Config (Environment Variables)

- `VECTOR_DB_PATH` / `VECTOR_DB_URL` - Deployment-specific
- `AIRPORTS_DB` - Deployment-specific
- `RULES_JSON` - Deployment-specific
- `COHERE_API_KEY` - Secret
- `OPENAI_API_KEY` - Secret

### Key Benefits

1. **Easy Experimentation**: Switch configs via env var
2. **Version Control**: Track prompt and config changes in git
3. **Reproducibility**: Exact config used for each experiment
4. **Type Safety**: Pydantic validation catches errors early
5. **A/B Testing**: Run multiple configs in parallel
6. **Team Collaboration**: Non-developers can adjust prompts/configs
