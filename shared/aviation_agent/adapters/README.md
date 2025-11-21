# Aviation Agent Adapters

## What Are Adapters in LangChain?

**Adapters** are a design pattern that bridge incompatible interfaces between different systems. In LangChain/LangGraph context, adapters typically:

1. **Transform data formats** - Convert between HTTP JSON ↔ LangChain message types
2. **Orchestrate execution** - Wire together LangGraph components with external systems
3. **Add cross-cutting concerns** - Logging, streaming, error handling, observability
4. **Abstract complexity** - Hide implementation details from consumers (e.g., FastAPI routes)

Think of adapters as **translation layers** that let different parts of your system communicate:

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   FastAPI   │ ───> │   Adapter    │ ───> │  LangGraph  │
│   (HTTP)    │      │  (Transform) │      │   (Agent)   │
└─────────────┘      └──────────────┘      └─────────────┘
```

## Our Aviation Agent Adapters

We have **4 adapters** that each handle a specific responsibility:

### 1. `langgraph_runner.py` - **Orchestration Adapter**

**Purpose**: Builds and runs the complete LangGraph agent.

**What it does**:
- Resolves LLM instances (from env vars or passed instances)
- Constructs the agent graph (planner → tool runner → formatter)
- Provides a simple `run_aviation_agent()` function that hides graph complexity

**Key Functions**:
```python
build_agent()           # Constructs the graph with all dependencies
run_aviation_agent()     # Runs the agent end-to-end
_resolve_llm()          # Auto-creates LLMs from env vars or uses provided instances
```

**Example Flow**:
```python
# Without adapter (complex):
settings = get_settings()
tool_client = AviationToolClient(settings.build_tool_context())
planner_llm = ChatOpenAI(model="gpt-4o-mini")
planner = build_planner_runnable(planner_llm, tool_client.tools)
tool_runner = ToolRunner(tool_client)
formatter = build_formatter_chain(formatter_llm)
graph = build_agent_graph(planner, tool_runner, formatter)
result = graph.invoke({"messages": messages})

# With adapter (simple):
result = run_aviation_agent(messages)  # Handles everything above
```

**Why it's needed**: Without this, every consumer (FastAPI, CLI, tests) would need to know how to wire up planner/tool/formatter. The adapter encapsulates that knowledge.

---

### 2. `fastapi_io.py` - **HTTP ↔ LangChain Adapter**

**Purpose**: Converts between FastAPI HTTP models and LangChain message types.

**What it does**:
- Transforms HTTP JSON `{"role": "user", "content": "..."}` → `HumanMessage`
- Converts `AgentState` → HTTP response `{"answer": "...", "ui_payload": {...}}`
- Provides type-safe Pydantic models for FastAPI

**Key Classes**:
```python
ChatMessage      # HTTP message format (role + content)
ChatRequest      # HTTP request body (list of messages)
ChatResponse     # HTTP response (answer + metadata + ui_payload)
```

**Example Flow**:
```python
# HTTP Request:
POST /api/aviation-agent/chat
{
  "messages": [
    {"role": "user", "content": "Find airports near Paris"}
  ]
}

# Adapter converts to:
[HumanMessage(content="Find airports near Paris")]

# Agent processes...

# Adapter converts back:
{
  "answer": "Here are airports near Paris...",
  "planner_meta": {"selected_tool": "find_airports_near_location", ...},
  "ui_payload": {"kind": "route", "mcp_raw": {...}}
}
```

**Why it's needed**: LangChain uses `BaseMessage` objects, but HTTP APIs use JSON. This adapter translates between them so FastAPI doesn't need to know about LangChain types.

---

### 3. `streaming.py` - **Streaming Adapter**

**Purpose**: Converts LangGraph's internal streaming events into SSE-compatible events for the web UI.

**What it does**:
- Listens to LangGraph's `astream_events()` (planner, tool calls, formatter)
- Transforms events into standardized SSE format
- Tracks token usage across all LLM calls
- Emits character-by-character answer streaming

**Event Types Emitted**:
```python
{"event": "plan", "data": {...}}              # Planner output
{"event": "thinking", "data": {"content": "..."}}  # Planning reasoning
{"event": "tool_call_start", "data": {...}}   # Tool execution started
{"event": "tool_call_end", "data": {...}}      # Tool execution completed
{"event": "message", "data": {"content": "a"}} # Answer chunk (character-by-character)
{"event": "ui_payload", "data": {...}}        # Visualization data
{"event": "done", "data": {"tokens": {...}}}   # Final summary with token counts
```

**Example Flow**:
```python
# LangGraph emits internal events:
on_chain_start(name="planner")
on_chain_end(name="planner", output=plan)
on_chain_start(name="tool")
on_chain_end(name="tool", output=result)
on_chat_model_stream(chunk="H")
on_chat_model_stream(chunk="e")
on_chat_model_stream(chunk="l")
...

# Adapter transforms to SSE:
event: plan
data: {"selected_tool": "search_airports", ...}

event: tool_call_start
data: {"name": "search_airports", ...}

event: message
data: {"content": "H"}

event: message
data: {"content": "e"}
...
```

**Why it's needed**: LangGraph's streaming is low-level and tied to its internal structure. The adapter provides a clean, UI-friendly event stream that the frontend can consume via Server-Sent Events (SSE).

---

### 4. `logging.py` - **Observability Adapter**

**Purpose**: Extracts conversation data from agent state and logs it for analysis/debugging.

**What it does**:
- Extracts plan, tool calls, answers, UI payloads from final `AgentState`
- Formats data into JSON log files (one file per day)
- Tracks timing, token usage, errors
- Saves to `conversation_logs/` directory

**Log Entry Format**:
```json
{
  "session_id": "abc123",
  "timestamp": "2025-01-15T10:30:00Z",
  "duration_seconds": 2.5,
  "question": "Find airports near Paris",
  "tool_calls": [
    {
      "name": "find_airports_near_location",
      "arguments": {"location_query": "Paris"},
      "result": {...}
    }
  ],
  "answer": "Here are airports...",
  "ui_payload": {...},
  "tokens": {"input": 150, "output": 200}
}
```

**Why it's needed**: Agent execution is complex (planner → tool → formatter). This adapter captures the full conversation flow in one place for debugging, analytics, and improving prompts.

---

## How They Work Together

Here's how all adapters collaborate in a typical request:

```
1. HTTP Request arrives at FastAPI
   ↓
2. fastapi_io.py: ChatRequest → [HumanMessage]
   ↓
3. langgraph_runner.py: build_agent() → creates graph
   ↓
4. langgraph_runner.py: run_aviation_agent() → executes graph
   ↓
5. streaming.py: (if streaming) → transforms events to SSE
   ↓
6. logging.py: (after completion) → saves conversation log
   ↓
7. fastapi_io.py: AgentState → ChatResponse
   ↓
8. HTTP Response sent to client
```

## Design Benefits

1. **Separation of Concerns**: Each adapter has one job
2. **Testability**: Can test adapters independently (mock LangGraph, test HTTP conversion)
3. **Reusability**: `langgraph_runner` can be used by CLI, FastAPI, or background jobs
4. **Maintainability**: Changes to LangGraph internals only affect `langgraph_runner`, not FastAPI routes

## When to Add New Adapters

Add a new adapter when you need to:
- Bridge to a new system (e.g., WebSocket, gRPC, MQTT)
- Add cross-cutting functionality (e.g., rate limiting, caching, retries)
- Transform data formats (e.g., Protobuf, MessagePack)
- Abstract complex setup (e.g., multi-agent orchestration)

## Summary

Adapters are **translation layers** that:
- **langgraph_runner**: Orchestrates the agent (builds graph, runs execution)
- **fastapi_io**: Converts HTTP ↔ LangChain types
- **streaming**: Transforms LangGraph events → SSE events
- **logging**: Extracts conversation data → log files

Together, they make the agent easy to use from FastAPI while keeping the core agent logic clean and testable.

