# Aviation Agent Architecture

> **Read this first** before working on any agent feature.

## Quick Reference

| File | Purpose |
|------|---------|
| `shared/aviation_agent/state.py` | AgentState TypedDict definition |
| `shared/aviation_agent/graph.py` | LangGraph graph construction |
| `shared/aviation_agent/planning.py` | Planner node and AviationPlan |
| `shared/aviation_agent/execution.py` | Tool runner node |
| `shared/aviation_agent/formatting.py` | Formatter chains and UI payload |
| `shared/aviation_agent/routing.py` | Query router (rules vs database) |
| `shared/aviation_agent/rules_rag.py` | RAG retrieval system |
| `shared/aviation_agent/config.py` | Settings and config loading |
| `web/server/api/aviation_agent_chat.py` | FastAPI SSE endpoint |

**Key Exports:**
- `AgentState` - LangGraph state type
- `AviationPlan` - Planner output schema
- `build_agent()` - Graph factory function
- `build_ui_payload()` - UI payload construction

**Related Docs:**
- `AGENT_PLANNER.md` - Planner node, tool selection, filters
- `AGENT_FORMATTER.md` - Formatter chains, UI payload structure
- `AGENT_RAG.md` - Rules RAG, router, comparison system
- `AGENT_TOOLS.md` - Tool catalog, missing_info pattern
- `AGENT_CONFIG.md` - Configuration system
- `AGENT_STREAMING.md` - SSE streaming, FastAPI integration

---

## Core Design: Planner-Based Architecture

The agent uses a **planner-based architecture** where the LLM planner selects the appropriate tool:

```
User Query
    ↓
┌─────────────────┐
│ Router Node     │ → Classifies: rules vs database
└─────────────────┘
    ↓           ↓
    Rules      Database
    Path        Path
    ↓           ↓
┌──────────────┐  ┌──────────────────┐
│ Rules RAG    │  │ Planner Node     │
│ Retrieval    │  │ (Tool Selection) │
└──────────────┘  └──────────────────┘
    ↓                    ↓
┌──────────────┐  ┌──────────────────┐
│ Rules Agent  │  │ Tool Runner      │
│ Synthesis    │  │ (Execution)      │
└──────────────┘  └──────────────────┘
    ↓                    ↓
    └────────┬───────────┘
             ↓
┌────────────────────────┐
│    Formatter Node      │
│ (Strategy-Based)       │
└────────────────────────┘
             ↓
       Final Answer
```

### Key Principles

1. **Router First**: Query router classifies as rules/database/both
2. **Planner Selects Tool**: For database path, planner picks one tool
3. **Tools Return DATA Only**: Tools never do LLM synthesis
4. **Formatter Does SYNTHESIS**: Strategy-based formatting per tool type

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]

    # Planning
    plan: Optional[AviationPlan]          # Tool selection plan
    planning_reasoning: Optional[str]     # Why this tool

    # Router (rules path)
    router_decision: Optional[RouterDecision]
    retrieved_rules: Optional[List[Dict]]

    # Tool execution
    tool_result: Optional[Any]            # Raw tool result

    # Output
    formatting_reasoning: Optional[str]   # How formatter presents
    final_answer: Optional[str]           # User-facing response
    thinking: Optional[str]               # Combined reasoning
    ui_payload: Optional[dict]            # Stable UI structure
    error: Optional[str]                  # Error if failed

    # Optional
    persona_id: Optional[str]             # GA persona
    suggested_queries: Optional[List[dict]]  # Follow-ups
```

### State Field Ownership

| Field | Set By | Used By |
|-------|--------|---------|
| `messages` | Entry point | All nodes (conversation history) |
| `router_decision` | Router node | Conditional edge |
| `plan` | Planner node | Tool runner, Formatter |
| `tool_result` | Tool runner | Formatter |
| `final_answer` | Formatter | SSE streaming |
| `ui_payload` | Formatter | SSE streaming |
| `error` | Any node | Error handling |

### LangGraph Patterns

**Message Accumulation:**
```python
messages: Annotated[List[BaseMessage], operator.add]
```
Uses `operator.add` reducer — LangGraph automatically merges messages.

**Partial Updates:**
```python
class AgentState(TypedDict, total=False):  # total=False
```
Nodes return only the fields they modify, not entire state.

---

## Graph Structure

```python
def build_agent() -> CompiledGraph:
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("router", router_node)
    graph.add_node("rules_agent", rules_agent_node)
    graph.add_node("planner", planner_node)
    graph.add_node("tool_runner", tool_node)
    graph.add_node("formatter", formatter_node)

    # Entry and routing
    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route_decision,
        {
            "rules_agent": "rules_agent",
            "planner": "planner",
        }
    )

    # Database path
    graph.add_edge("planner", "tool_runner")
    graph.add_edge("tool_runner", "formatter")

    # Rules path
    graph.add_edge("rules_agent", END)

    # Formatter to end
    graph.add_edge("formatter", END)

    return graph.compile()
```

### Conditional Routing

```python
def route_decision(state: AgentState) -> str:
    decision = state.get("router_decision")
    if decision and decision.path == "rules":
        return "rules_agent"
    return "planner"  # database path (default)
```

---

## Repository Structure

```
shared/aviation_agent/
  __init__.py
  config.py                 # Settings + behavior config loading
  behavior_config.py        # JSON config schema (Pydantic)
  state.py                  # AgentState definition
  planning.py               # Planner node
  execution.py              # Tool runner node
  formatting.py             # Formatter chains
  graph.py                  # Graph construction
  routing.py                # Query router
  rules_rag.py              # RAG retrieval system
  rules_agent.py            # Rules synthesis agent
  answer_comparer.py        # Embedding-based comparison
  comparison_service.py     # High-level comparison API
  next_query_predictor.py   # Follow-up suggestions
  tools.py                  # Tool definitions
  adapters/
    streaming.py            # SSE streaming adapter
    logging.py              # Conversation logging
    langgraph_runner.py     # Orchestration, provider factory (_resolve_llm, _PROVIDER_REGISTRY)

shared/
  aircraft_speeds.py        # GA aircraft speed lookup
  airport_tools.py          # MCP tool implementations
  rules_manager.py          # Rules JSON access

web/server/api/
  aviation_agent_chat.py    # FastAPI router

configs/aviation_agent/
  default.json              # Default config (OpenAI)
  anthropic.json            # Anthropic Claude config
  gemini.json               # Google Gemini config
  prompts/
    planner_v1.md           # Planner system prompt
    formatter_v1.md         # Formatter system prompt
    comparison_synthesis_v1.md  # Comparison prompt
    router_v1.md            # Router system prompt
    rules_agent_v1.md       # Rules agent prompt
    ab_judge_v1.md          # LLM judge prompt for A/B comparison

tests/aviation_agent/
  conftest.py               # Shared fixtures
  test_utils.py             # Shared test utilities (load_test_cases, match_tool_and_args)
  test_planning.py
  test_planner_behavior.py  # LLM behavioral tests (multi-provider via config)
  test_formatting.py
  test_formatter_behavior.py
  test_graph_e2e.py
  test_streaming.py
  test_integration.py
  test_rules_rag.py
  test_routing.py

tools/
  avdbg.py                  # Debug CLI (supports --config for provider selection)
  ab_test.py                # A/B planner behavior test runner across configs
  ab_compare.py             # LLM judge full-answer comparison
```

---

## Error Handling

**Pattern: Errors in State, Not Exceptions**

```python
def planner_node(state: AgentState) -> Dict[str, Any]:
    try:
        plan = planner.invoke({"messages": state.get("messages") or []})
        return {"plan": plan, "planning_reasoning": f"Selected: {plan.selected_tool}"}
    except Exception as e:
        return {"error": str(e)}

def tool_node(state: AgentState) -> Dict[str, Any]:
    if state.get("error"):
        return {}  # Skip execution on prior error
    # ... execute tool
```

**Benefits:**
- Graph continues to completion (can still log, return partial results)
- Formatter can produce error message even on failure
- Errors emitted as SSE events to frontend

---

## SSE Event Flow

```
User Query → Agent Graph → SSE Events
                              ↓
                    ┌─────────────────────┐
                    │ plan               │ → Planner output
                    │ thinking           │ → Planning reasoning
                    │ tool_call_start    │ → Tool execution began
                    │ tool_call_end      │ → Tool completed
                    │ message (streamed) │ → Answer char-by-char
                    │ ui_payload         │ → Visualization data
                    │ done               │ → Session ID, tokens
                    │ error              │ → If failed
                    └─────────────────────┘
```

See `AGENT_STREAMING.md` for complete SSE implementation.

---

## Two-Tier Configuration

| Category | Location | Examples |
|----------|----------|----------|
| **Behavior** (how agent thinks) | JSON config files | LLM models, temperatures, prompts, RAG params |
| **Infrastructure** (where data goes) | Environment variables | DB paths, API keys, feature flags |

See `AGENT_CONFIG.md` for complete configuration documentation.

---

## Key Invariants

### Graph Invariants
- Router always runs first
- Only one tool executes per request (single-tool architecture)
- Formatter always runs last (produces final_answer and ui_payload)

### State Invariants
- `messages` accumulates via reducer (never replace, only append)
- `error` field presence signals failure to downstream nodes
- `ui_payload` is only set by formatter

### Tool Invariants
- Tools return DATA only — never do LLM synthesis
- Tools use `_tool_type` marker for formatter routing
- All tools return `filter_profile` for UI filter sync

---

## Testing Strategy

| Test Type | Location | Purpose |
|-----------|----------|---------|
| Unit | `test_planning.py` | Planner filter extraction, validation |
| Unit | `test_formatting.py` | UI payload building |
| Behavior | `test_planner_behavior.py` | LLM tool selection accuracy |
| Behavior | `test_formatter_behavior.py` | LLM missing_info handling |
| E2E | `test_graph_e2e.py` | Full graph execution |
| E2E | `test_streaming.py` | SSE event streaming |
| Integration | `test_integration.py` | FastAPI endpoint |
| A/B | `tools/ab_test.py` | Cross-provider planner comparison |
| A/B | `tools/ab_compare.py` | LLM judge full-answer comparison |

**Dependency Injection for Tests:**
```python
# Tests inject mock LLMs
mock_llm = FakeChatModel(responses=["mock response"])
planner = build_planner_runnable(llm=mock_llm, tools=tools)
```

---

## Debug CLI

```bash
# Basic query
python tools/avdbg.py "How long to fly EGTF to LFMD"

# See plan and tool result
python tools/avdbg.py "Find airports near Paris" --plan --tool-result

# Verbose mode (all debug info)
python tools/avdbg.py "Compare VFR rules UK vs France" -v
```

See `tools/avdbg.py` for full options.

---

## Debugging

```python
# In Python
from shared.aviation_agent.graph import build_agent
from shared.aviation_agent.config import get_behavior_config

agent = build_agent()
config = get_behavior_config("default")

# Run query
result = agent.invoke({
    "messages": [HumanMessage(content="Find airports near Paris")]
})
print(result["final_answer"])
print(result["ui_payload"])
```
