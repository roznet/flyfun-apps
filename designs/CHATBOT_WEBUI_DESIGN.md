# Aviation Agent WebUI Design

## Executive Summary

This document describes the design and architecture of the LangGraph-based aviation agent used for the chatbot WebUI. The agent provides structured planning, tool execution, and formatted responses with streaming support, map visualizations, and conversation logging.

**Current Architecture:**
- `aviation_agent_chat.py`: FastAPI router with streaming endpoint
- LangGraph-based agent with three-phase pipeline: Planner → Tool Runner → Formatter
- Stable UI payload format (hybrid approach: flattened common fields + mcp_raw)
- State-based thinking (no tag parsing)
- SSE streaming with token tracking
- Conversation logging

**Key Features:**
- Streaming responses with Server-Sent Events (SSE)
- State-based thinking extraction (planning + formatting reasoning)
- Filter generation from user messages (extracted in planner)
- Visualization enhancement (ICAO extraction from answers)
- Conversation logging
- Token tracking
- Error handling via state propagation
- Multi-turn conversations

---

## 1. Architecture Overview

### 1.1 FastAPI Router (`aviation_agent_chat.py`)

**Responsibilities:**
- Feature flag checking (`AVIATION_AGENT_ENABLED`)
- Request/response marshaling
- Error handling
- SSE streaming endpoint

**Endpoints:**
- `POST /api/aviation-agent/chat/stream` - Streaming chat (SSE)
- `POST /api/aviation-agent/chat` - Non-streaming chat

**Request Format:**
```json
{
  "messages": [
    {"role": "user", "content": "Find airports between EGTF and LFMD"}
  ],
  "session_id": "optional-session-id"
}
```

**Response Format (Streaming):**
SSE events with the following types:
- `plan` - Planner output (selected tool, arguments)
- `thinking` - Planning reasoning
- `tool_call_start` - Tool execution started
- `tool_call_end` - Tool execution completed
- `message` - Character-by-character answer stream
- `ui_payload` - Visualization data
- `done` - Request complete with token counts
- `error` - Error occurred

### 1.2 LangGraph Agent Structure

**Three-Phase Pipeline:**
```
Planner Node
  ↓ (AviationPlan)
Tool Runner Node
  ↓ (tool_result)
Formatter Node
  ↓ (final_answer + ui_payload)
```

**State:**
```python
class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: Optional[AviationPlan]  # Structured plan
    planning_reasoning: Optional[str]  # Planner's reasoning
    tool_result: Optional[Any]
    formatting_reasoning: Optional[str]  # Formatter's reasoning
    final_answer: Optional[str]
    thinking: Optional[str]  # Combined reasoning for UI
    ui_payload: Optional[dict]  # Stable UI structure
    error: Optional[str]  # Error message if execution fails
```

**Benefits:**
1. **Structured planning** - AviationPlan with selected_tool, arguments, answer_style
2. **Separation of concerns** - Planning, execution, formatting are separate nodes
3. **Stable UI payload** - Hybrid design: kind + top-level fields + mcp_raw
4. **Better testability** - Each node can be tested independently
5. **Tool validation** - Planner validates tool exists before execution
6. **State-based thinking** - Explicit reasoning fields, not parsed from text
7. **Error handling** - Errors propagate through state, not exceptions

---

## 2. Core Components

### 2.1 State Management (`state.py`)

**AgentState Structure:**
- `messages`: Conversation history (uses `operator.add` reducer)
- `plan`: Structured plan from planner node
- `planning_reasoning`: Why the planner selected this tool/approach
- `tool_result`: Raw result from tool execution
- `formatting_reasoning`: How the formatter presents results
- `final_answer`: User-facing response text
- `thinking`: Combined reasoning (planning + formatting) for UI display
- `ui_payload`: Structured payload for UI integration
- `error`: Error message if execution fails

**Why State-Based Thinking:**
- ✅ **Structured** - Explicit state fields, not parsed from text
- ✅ **Reliable** - Doesn't depend on LLM format compliance
- ✅ **Streamable** - Can emit thinking as nodes execute
- ✅ **Testable** - Can assert on thinking state directly
- ✅ **LangGraph-native** - Uses state management, not text parsing

### 2.2 Planning (`planning.py`)

**AviationPlan Structure:**
```python
class AviationPlan(BaseModel):
    selected_tool: str
    arguments: Dict[str, Any] = {}  # Filters go here: arguments.filters
    answer_style: str = "narrative_markdown"
```

**Key Design Decisions:**
1. **Filters in arguments** - No separate `filters` field needed. Filters are part of tool arguments.
2. **Planner extracts filters** - LLM extracts user requirements (AVGAS, customs, runway length, etc.) into `arguments.filters`
3. **Planning reasoning** - Generated from plan structure (tool name, filters, arguments)

**Planner Prompt:**
- Instructs LLM to select exactly one aviation tool
- Extracts filters from user message into `arguments.filters`
- Only includes filters the user explicitly requests
- Returns structured AviationPlan

**Available Filters:**
- `has_avgas`: Boolean (AVGAS fuel)
- `has_jet_a`: Boolean (Jet-A fuel)
- `has_hard_runway`: Boolean (paved/hard runways)
- `has_procedures`: Boolean (IFR procedures)
- `point_of_entry`: Boolean (customs/border crossing)
- `country`: String (ISO-2 code)
- `min_runway_length_ft`: Number
- `max_runway_length_ft`: Number
- `max_landing_fee`: Number

### 2.3 Execution (`execution.py`)

**ToolRunner Class:**
- Executes the selected tool from the plan
- Uses MCP client to invoke tools
- Filters are already in `plan.arguments.filters` (no injection needed)
- Returns tool result with `filter_profile` (what filters were actually applied)

**Tool Result Structure:**
- `filter_profile`: Filters actually applied by the tool
- `visualization`: Map visualization data
- `airports`: Airport data (for route/airport searches)
- `pretty`: Human-readable summary
- Other tool-specific fields

### 2.4 Formatting (`formatting.py`)

**Formatter Responsibilities:**
1. Convert tool results into user-facing answer
2. Build UI payload from plan and tool result
3. Extract ICAO codes from answer (optional enhancement)
4. Enhance visualization with mentioned airports (optional)
5. Generate formatting reasoning

**Formatter Chain:**
```python
prompt | llm | StrOutputParser()
```

**Key Design:**
- **No tag parsing** - Streams LLM output directly as `message` events
- **State-based thinking** - Formatting reasoning stored in state, not extracted from text
- **Visualization enhancement** - Optional: extracts ICAOs from answer and enriches visualization
- **UI payload building** - Uses hybrid approach (flattened common fields + mcp_raw)

**UI Payload Building:**
```python
def build_ui_payload(plan: AviationPlan, tool_result: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """
    Build UI payload using hybrid approach:
    - Flatten commonly-used fields (filters, visualization, airports) for convenience
    - Keep mcp_raw for everything else and as authoritative source
    """
    # Base payload with kind and mcp_raw
    base_payload = {
        "kind": _determine_kind(plan.selected_tool),
        "mcp_raw": tool_result,
    }
    
    # Add kind-specific metadata (departure, destination, icao, etc.)
    
    # Flatten commonly-used fields for convenience
    if "filter_profile" in tool_result:
        base_payload["filters"] = tool_result["filter_profile"]
    if "visualization" in tool_result:
        base_payload["visualization"] = tool_result["visualization"]
    if "airports" in tool_result:
        base_payload["airports"] = tool_result["airports"]
    
    return base_payload
```

### 2.5 Graph Assembly (`graph.py`)

**Graph Structure:**
```
planner → tool → formatter → END
```

**Node Functions:**
1. **planner_node** - Invokes planner, generates planning_reasoning, returns plan
2. **tool_node** - Executes tool from plan, returns tool_result
3. **formatter_node** - Formats answer, builds UI payload, combines thinking, returns final_answer + ui_payload

**Error Handling:**
- Errors stored in state (`error` field)
- Formatter can produce error message even on failure
- Errors propagate through state, not exceptions
- Graceful degradation - formatter always produces some response

**Thinking Combination:**
```python
thinking_parts = []
if state.get("planning_reasoning"):
    thinking_parts.append(state["planning_reasoning"])
if formatted.get("formatting_reasoning"):
    thinking_parts.append(formatted["formatting_reasoning"])

thinking = "\n\n".join(thinking_parts) if thinking_parts else None
```

---

## 3. Streaming Implementation

### 3.1 Streaming Adapter (`adapters/streaming.py`)

**Function: `stream_aviation_agent()`**

Uses LangGraph's `astream_events()` API to capture:
- Node execution events
- LLM streaming chunks
- Token usage
- Tool execution

**SSE Events Emitted:**
1. `plan` - When planner completes (AviationPlan structure)
2. `thinking` - Planning reasoning (from planning_reasoning)
3. `tool_call_start` - Tool execution started (name, arguments)
4. `tool_call_end` - Tool execution completed (name, result)
5. `message` - LLM answer chunks (character-by-character)
6. `thinking_done` - Thinking complete
7. `ui_payload` - Visualization data
8. `done` - Request complete (session_id, token counts)
9. `error` - Error occurred (error message)

**Token Tracking:**
- Extracts token usage from `on_llm_end` and `on_chat_model_end` events
- Accumulates across all LLM calls (planner + formatter)
- Returns in `done` event: `{input, output, total}`

**Implementation Pattern:**
```python
async for event in graph.astream_events(
    {"messages": messages},
    version="v2",
):
    kind = event.get("event")
    
    # Handle different event types
    if kind == "on_chain_end" and event.get("name") == "planner":
        # Emit plan and thinking
    elif kind == "on_chain_start" and event.get("name") == "tool":
        # Emit tool_call_start
    elif kind == "on_chat_model_stream":
        # Emit message chunks
    # ... etc
```

### 3.2 FastAPI Streaming Endpoint

**Endpoint: `/api/aviation-agent/chat/stream`**

```python
@router.post("/chat/stream")
async def aviation_agent_chat_stream(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
    session_id: Optional[str] = None,  # From header
) -> StreamingResponse:
    graph = build_agent(settings=settings)
    
    async def event_generator():
        async for event in stream_aviation_agent(
            request.to_langchain(),
            graph,
            session_id=session_id
        ):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
        
        # After streaming, log conversation
        final_state = graph.invoke({"messages": request.to_langchain()})
        log_conversation_from_state(...)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
```

---

## 4. UI Payload Structure

### 4.1 Hybrid Approach

**Design Decision:** Flatten commonly-used fields for convenience, keep `mcp_raw` as authoritative source.

**Structure:**
```json
{
  "kind": "route",
  "departure": "EGTF",
  "destination": "LFMD",
  "filters": {...},  // Flattened from mcp_raw.filter_profile
  "visualization": {...},  // Flattened from mcp_raw.visualization
  "airports": [...],  // Flattened from mcp_raw.airports
  "mcp_raw": {
    "filter_profile": {...},
    "visualization": {...},
    "airports": [...],
    // ... all other tool result fields
  }
}
```

**Benefits:**
- ✅ **Convenient access** - `ui_payload.filters` instead of `ui_payload.mcp_raw.filter_profile`
- ✅ **Future-proof** - New fields automatically in `mcp_raw`
- ✅ **Authoritative source** - `mcp_raw` is the complete tool result
- ✅ **No breaking changes** - UI can use either approach
- ✅ **Limited flattening** - Only 3 commonly-used fields

**Flattened Fields:**
1. `filters` (from `filter_profile`) - UI needs for filter sync
2. `visualization` - UI needs for map rendering
3. `airports` - UI needs for airport list

**Kind-Specific Metadata:**
- Route tools: `departure`, `destination`, `ifr`
- Airport tools: `icao`
- Rules tools: `region`, `topic`

### 4.2 UI Integration

**Frontend Usage:**
```javascript
// Convenient access (recommended)
const filters = ui_payload.filters;
const visualization = ui_payload.visualization;
const airports = ui_payload.airports;

// Or access via mcp_raw (if needed)
const filters = ui_payload.mcp_raw.filter_profile;
const visualization = ui_payload.mcp_raw.visualization;
```

**Visualization Types:**
- `route_with_markers` - Route line with airport markers
- `markers` - Array of airports
- `marker_with_details` - Single airport with details
- `point_with_markers` - Location with nearby airports

See `designs/TOOL_VISUALIZATION_MAPPING.md` for complete tool-to-visualization mapping.

---

## 5. Conversation Logging

### 5.1 Logging Implementation (`adapters/logging.py`)

**Function: `log_conversation_from_state()`**

**Approach:** Post-execution logging (simple, non-blocking)

**Process:**
1. Extract data from final AgentState after streaming completes
2. Build log entry in existing format
3. Save to JSON file (one file per day: `conversation_logs/YYYY-MM-DD.json`)

**Log Entry Structure:**
```json
{
  "session_id": "...",
  "timestamp": "2024-01-01T12:00:00",
  "timestamp_end": "2024-01-01T12:00:05",
  "duration_seconds": 5.23,
  "question": "User message",
  "answer": "Assistant response",
  "thinking": "Internal reasoning",
  "tool_calls": [
    {
      "name": "find_airports_near_route",
      "arguments": {"from_icao": "EGTF", "to_icao": "LFMD"},
      "result": {...}
    }
  ],
  "metadata": {
    "has_visualizations": true,
    "num_tool_calls": 1,
    "has_error": false
  }
}
```

**Why Post-Execution:**
- ✅ **Simple** - Just extract from final state
- ✅ **Non-blocking** - Doesn't slow down streaming
- ✅ **Reliable** - All data available at end
- ✅ **Easy to implement** - Minimal code changes

**Usage:**
```python
# After streaming completes
final_state = graph.invoke({"messages": messages})
log_conversation_from_state(
    session_id=session_id,
    state=final_state,
    messages=messages,
    start_time=start_time,
    end_time=time.time(),
    log_dir=Path("conversation_logs")
)
```

---

## 6. Design Principles

### 6.1 State-Based Thinking

**Principle:** Store reasoning in state, not parse from LLM output.

**Implementation:**
- `planning_reasoning`: Generated from plan structure
- `formatting_reasoning`: Generated from formatting logic
- `thinking`: Combined from both for UI display

**Benefits:**
- More reliable (doesn't depend on LLM format)
- Easier to test (can assert on state)
- LangGraph-native (uses state management)
- Streamable (can emit as nodes execute)

### 6.2 Filters as Arguments

**Principle:** Filters are part of tool arguments, not separate metadata.

**Implementation:**
- Planner extracts filters into `plan.arguments.filters`
- Tool runner uses `plan.arguments` directly
- Tool returns `filter_profile` (what was actually applied)
- UI gets filters from `ui_payload.filters` (flattened) or `ui_payload.mcp_raw.filter_profile`

**Benefits:**
- Simpler (no separate field)
- Consistent (filters are tool arguments)
- UI gets actual applied filters from tool result

### 6.3 Hybrid UI Payload

**Principle:** Flatten commonly-used fields for convenience, keep `mcp_raw` as authoritative source.

**Benefits:**
- Convenient UI access
- Future-proof (new fields in mcp_raw)
- No breaking changes
- Limited flattening (only 3 fields)

### 6.4 Error Handling in State

**Principle:** Errors propagate through state, not exceptions.

**Implementation:**
- Nodes set `error` field in state on failure
- Formatter can produce error message even on failure
- Errors emitted as `error` SSE event
- Graceful degradation - always produces some response

**Benefits:**
- LangGraph-native (errors in state)
- Streamable (errors can be streamed)
- Graceful (formatter can still respond)

### 6.5 LangGraph-Native Patterns

**Principles:**
1. Use `astream_events()` for streaming (standard LangGraph pattern)
2. Use state reducers (`operator.add` for messages)
3. Store reasoning in state, not parse from text
4. Handle errors in nodes, not external try/catch
5. Use structured planning (AviationPlan)

---

## 7. Code Structure

### Current Structure
```
shared/aviation_agent/
  state.py              # AgentState definition
  planning.py           # Planner node + AviationPlan
  execution.py          # ToolRunner
  formatting.py         # Formatter + UI payload building
  graph.py              # Graph assembly
  adapters/
    streaming.py        # SSE streaming adapter
    logging.py          # Conversation logging
    __init__.py

web/server/api/
  aviation_agent_chat.py  # FastAPI router
```

---

## 8. Testing Strategy

### Unit Tests
- Test planner filter extraction
- Test tool runner execution
- Test formatter UI payload building
- Test state management
- Test thinking combination

### Integration Tests
- Test streaming endpoint (SSE events)
- Test visualization enhancement
- Test conversation logging
- Test error handling
- Test token tracking

### E2E Tests
- Test full conversation flow
- Test route planning queries
- Test airport search queries
- Test rules queries
- Test streaming response
- Test multi-turn conversations

---

## 9. Key Design Decisions

### 9.1 State-Based Thinking (Not Tag Parsing)

**Decision:** Store reasoning in state fields, not parse `<thinking>` tags from LLM output.

**Rationale:**
- More reliable (doesn't depend on LLM format compliance)
- Easier to test (can assert on state)
- LangGraph-native (uses state management)
- Streamable (can emit as nodes execute)

### 9.2 Filters in Arguments (Not Separate Field)

**Decision:** Filters are part of `plan.arguments.filters`, not a separate `filters` field.

**Rationale:**
- Simpler (no separate field needed)
- Consistent (filters are tool arguments)
- UI gets actual applied filters from tool result (`filter_profile`)

### 9.3 Hybrid UI Payload (Not Pure mcp_raw)

**Decision:** Flatten commonly-used fields (`filters`, `visualization`, `airports`) while keeping `mcp_raw` as authoritative source.

**Rationale:**
- Convenient UI access
- Future-proof (new fields in mcp_raw)
- No breaking changes
- Limited flattening (only 3 fields)

### 9.4 Post-Execution Logging (Not Event-Based)

**Decision:** Log after streaming completes, extract from final state.

**Rationale:**
- Simple and reliable
- Non-blocking (doesn't slow down streaming)
- Easy to implement
- All data available at end

### 9.5 Error Handling in State (Not Exceptions)

**Decision:** Errors stored in state, formatter can produce error message even on failure.

**Rationale:**
- LangGraph-native (errors in state)
- Streamable (errors can be streamed)
- Graceful degradation (always produces some response)

---

## 10. Future Enhancements

### Potential Improvements
1. **Retry logic** - Add retry for transient failures (LLM API, MCP connection)
2. **Caching** - Cache tool results for common queries
3. **Rate limiting** - Per-user rate limiting
4. **Analytics** - Track tool usage, query patterns
5. **A/B testing** - Test different planner/formatter prompts
6. **Multi-tool support** - Allow planner to select multiple tools
7. **Conditional edges** - Add conditional routing based on tool results
8. **Human-in-the-loop** - Add approval step for certain tool calls

---

## Appendix: Related Documents

- `designs/LLM_AGENT_DESIGN.md` - Original agent design
- `designs/TOOL_VISUALIZATION_MAPPING.md` - Tool-to-visualization mapping
- `PHASE5_UI_INTEGRATION_SUMMARY.md` - UI integration details
