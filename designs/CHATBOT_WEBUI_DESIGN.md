# Aviation Agent WebUI Design

## Executive Summary

This document describes the design and architecture of the LangGraph-based aviation agent used for the chatbot WebUI. The agent provides structured planning, tool execution, and formatted responses with streaming support, map visualizations, and conversation logging.

**Current Architecture:**
- `aviation_agent_chat.py`: FastAPI router with streaming endpoint
- LangGraph-based agent with three-phase pipeline: Planner → Tool Runner → Formatter
- Stable UI payload format (flattened fields for convenient access)
- State-based thinking (no tag parsing)
- SSE streaming with token tracking
- Conversation logging

**Key Features:**
- Streaming responses with Server-Sent Events (SSE)
- State-based thinking extraction (planning + formatting reasoning)
- Filter generation from user messages (extracted in planner)
- Tool-based visualizations (from tool results, not parsed from answers)
- Conversation logging
- Token tracking
- Error handling via state propagation
- Multi-turn conversations with checkpointing
- Next query prediction (optional, configurable)
- Notification enrichment for location/route tools

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
SSE events with the following types (in order):
- `plan` - Planner output (selected tool, arguments)
- `thinking` - Planning reasoning (may be multiple chunks)
- `tool_call_start` - Tool execution started
- `tool_call_end` - Tool execution completed
- `message` - Character-by-character answer stream
- `thinking_done` - Thinking complete
- `ui_payload` - Visualization data (emitted once when formatter completes)
- `final_answer` - Complete serializable state for logging
- `done` - Request complete with token counts, session_id, thread_id, run_id
- `error` - Error occurred

### 1.2 LangGraph Agent Structure

**Pipeline Structure:**
```
Planner Node
  ↓ (AviationPlan)
[Next Query Predictor Node] (optional, configurable)
  ↓ (suggested_queries)
Tool Runner Node
  ↓ (tool_result)
Formatter Node
  ↓ (final_answer + ui_payload)
```

**Note:** Next Query Predictor node is optional and controlled via behavior config. When enabled, it runs after planner and before tool execution.

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
    persona_id: Optional[str]  # Persona ID for airport prioritization
    suggested_queries: Optional[List[dict]]  # Follow-up query suggestions
```

**Benefits:**
1. **Structured planning** - AviationPlan with selected_tool, arguments, answer_style
2. **Separation of concerns** - Planning, execution, formatting are separate nodes
3. **Stable UI payload** - Flattened design: kind + top-level fields for convenient access
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
- `persona_id`: Persona ID for airport prioritization (GA friendliness)
- `suggested_queries`: Follow-up query suggestions (from next query predictor)

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

**Notification Enrichment (Post-Processing):**

For location/route tools (`find_airports_near_location`, `find_airports_near_route`, `search_airports`), the tool node performs optional post-processing to enrich airport results with notification data.

**Trigger Conditions:**
- User query contains notification keywords: "notification", "notify", "customs", "notice", "prior", "how early", "when should"
- Tool is a location/route tool
- Tool result contains airports

**Process:**
1. Extract `day_of_week` from query if mentioned (e.g., "saturday", "sunday")
2. For each airport (limited to first 15), fetch notification data via `NotificationService`
3. Add `notification` field to each airport object
4. Append notification summary to `pretty` output

**Result:**
- Enriched airports with `notification` field containing:
  - `found`: Boolean indicating if notification data exists
  - `hours_notice`: Required notice hours
  - `day_specific_rule`: Day-specific notification rule (if applicable)
  - `summary`: Human-readable summary

### 2.4 Formatting (`formatting.py`)

**Formatter Responsibilities:**
1. Convert tool results into user-facing answer
2. Build UI payload from plan and tool result
3. Generate formatting reasoning
4. Include suggested queries in UI payload (if available)

**Formatter Chain:**
```python
prompt | llm | StrOutputParser()
```

**Key Design:**
- **No tag parsing** - Streams LLM output directly as `message` events
- **State-based thinking** - Formatting reasoning stored in state, not extracted from text
- **UI payload building** - Uses flattened approach for convenient access
- **Specialized formatters** - Comparison tools use dedicated `comparison_synthesis` prompt

**Visualization Source:**

**Important:** Visualizations come **entirely from the tool result** in the UI payload. The formatter does NOT parse the LLM's answer text to determine what to visualize.

- Tools return visualization data in their results
- Formatter includes this visualization in the UI payload as-is
- No extraction or filtering based on answer text
- Visualization is determined by tool logic, not LLM output

**Rationale:**
- Tools return DATA, formatters do SYNTHESIS
- Visualization should be consistent and reliable
- No coupling between LLM text output and visualization
- Single source of truth: tool result → UI payload → frontend

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
planner → [predict_next_queries] → tool → formatter → END
```

**Node Functions:**
1. **planner_node** - Invokes planner, generates planning_reasoning, returns plan
2. **predict_next_queries_node** (optional) - Generates follow-up query suggestions based on plan
3. **tool_node** - Executes tool from plan, performs notification enrichment if applicable, returns tool_result
4. **formatter_node** - Formats answer, builds UI payload, enhances visualization, combines thinking, returns final_answer + ui_payload

**Note:** `predict_next_queries_node` is optional and controlled via behavior config. When enabled, it runs after planner and before tool execution.

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

**SSE Events Emitted (in order):**
1. `plan` - When planner completes (AviationPlan structure)
2. `thinking` - Planning reasoning (from planning_reasoning, may be multiple chunks)
3. `tool_call_start` - Tool execution started (name, arguments)
4. `tool_call_end` - Tool execution completed (name, result)
5. `message` - LLM answer chunks (character-by-character, from formatter)
6. `thinking_done` - Thinking complete (emitted when formatter completes)
7. `ui_payload` - Visualization data (emitted once when formatter completes)
8. `final_answer` - Complete serializable state for logging (emitted after formatter)
9. `done` - Request complete with metadata (session_id, thread_id, run_id, token counts)
10. `error` - Error occurred (error message, can occur at any point)

**Event Ordering:**
Events are emitted in the order shown above. The `error` event can occur at any point if an error is encountered. The `final_answer` event contains the complete serializable state (excluding messages) for conversation logging purposes.

**Token Tracking:**
- Extracts token usage from `on_llm_end` and `on_chat_model_end` events
- Accumulates across ALL LLM calls (planner + formatter)
- Tracks both input tokens (prompt) and output tokens (completion)
- Returns in `done` event: `{input, output, total}`
- Token usage is extracted from LLM response metadata

**Thread ID and Session ID:**
- `thread_id`: Generated if not provided (format: `thread_{uuid}`)
  - Required for checkpointing (conversation memory)
  - Enables multi-turn conversations
  - Included in `done` event
- `session_id`: Extracted from header or generated (format: `session_{timestamp}`)
  - Used for conversation logging
  - Included in `done` event
- `run_id`: Generated UUID for LangSmith feedback tracking
  - Included in `done` event for feedback submission

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

### 4.1 Flattened Approach

**Design Decision:** Flatten commonly-used fields for convenient access. No redundant data.

**Structure:**
```json
{
  "kind": "route",
  "departure": "EGTF",
  "destination": "LFMD",
  "filters": {...},  // From tool_result.filter_profile
  "visualization": {...},  // From tool_result.visualization
  "airports": [...],  // From tool_result.airports
  "suggested_queries": [...],  // Optional: follow-up query suggestions
  "show_rules": {  // Optional: for rules tools
    "countries": ["FR", "DE"],
    "categories_by_country": {"FR": ["IFR"], "DE": ["VFR"]}
  }
}
```

**Benefits:**
- ✅ **Convenient access** - Direct access to fields without nesting
- ✅ **Reduced bandwidth** - No redundant data duplication
- ✅ **Lower token usage** - Smaller payloads in LLM context
- ✅ **Simpler structure** - Easier to work with in frontend
- ✅ **Clear contract** - Only flattened fields, no hidden data

**Flattened Fields:**
1. `filters` (from `filter_profile`) - UI needs for filter sync
2. `visualization` - UI needs for map rendering
3. `airports` - UI needs for airport list

**Kind-Specific Metadata:**
- Route tools: `departure`, `destination`, `ifr`
- Airport tools: `icao`
- Rules tools: `region`, `topic`, `show_rules` (optional)

**Additional Fields:**
- `suggested_queries`: Optional array of follow-up query suggestions (from next query predictor)
  - Format: `[{text, tool, category, priority}, ...]`
  - Only included if next query prediction is enabled
- `show_rules`: Optional object for rules tools to trigger rules panel display
  - Format: `{countries: string[], categories_by_country: Record<string, string[]>}`
  - Used by frontend to display country rules in right panel

### 4.2 UI Integration

**Frontend Event Processing:**

The frontend (`ChatbotManager`) processes `ui_payload` events as follows:

1. **Extract `visualization`** → Call `llmIntegration.handleVisualization()`
2. **Extract `filter_profile`** → Call `llmIntegration.applyFilterProfile()`
3. **Extract `show_rules`** → Dispatch `show-country-rules` event
4. **Extract `suggested_queries`** → Render in UI

**Frontend Usage:**
```javascript
// Direct access to flattened fields
const filters = ui_payload.filters;
const visualization = ui_payload.visualization;
const airports = ui_payload.airports;
const suggestedQueries = ui_payload.suggested_queries;
```

**Visualization Types and Behavior:**

The `LLMIntegration` class handles each visualization type as follows:

1. **`markers`** - Display airports as markers (two modes)

   **Mode 1: With meaningful filters** (country, point_of_entry, has_avgas, etc.):
   - Clears old LLM highlights
   - Applies filter profile to store (updates UI filter controls)
   - Adds blue highlights for the specific airports returned by the tool
   - Dispatches `trigger-filter-refresh` event to load ALL airports matching filters
   - Result: Map shows all airports matching filters, with LLM recommendations highlighted in blue

   **Mode 2: No meaningful filters** (just airport list):
   - Clears old LLM highlights
   - Sets airports in store directly (only shows returned airports)
   - Adds blue highlights for all returned airports
   - Fits map bounds to show all airports
   - Result: Map shows only the returned airports, all highlighted

2. **`route_with_markers`** - Display route with airports
   - Clears old LLM highlights
   - Sets highlights for airports mentioned in chat
   - Updates search query in store
   - Applies filter profile
   - Triggers route search via `trigger-search` event
   - Shows all airports along route with highlights on chat airports

3. **`marker_with_details`** - Focus on specific airport
   - Updates search query in store
   - Triggers search via `trigger-search` event (centers map, shows marker)
   - Triggers `airport-click` event (loads and displays details panel)

4. **`point_with_markers`** - Display point location with airports
   - Clears old LLM highlights
   - Sets highlights for recommended airports
   - Sets locate state in store with center point
   - Applies filter profile
   - Triggers locate search via `trigger-locate` event
   - Shows all airports within radius with highlights on recommended airports

**Filter Profile Application:**

When `filter_profile` is present in `ui_payload`:
1. Extract from `ui_payload.filters` (flattened field)
2. Map to `FilterConfig` format (validate keys and types)
3. Apply via `store.setFilters()`
4. Sync UI controls via `uiManager.syncFiltersToUI()`

**Rules Panel Display:**

When `show_rules` is present in `ui_payload`:
1. Extract `countries` and `categories_by_country`
2. Dispatch `show-country-rules` event with details
3. Rules panel displays country rules with category filters

**Tool-to-Visualization Mapping:**

| Tool | Visualization Type | UI Behavior |
|------|-------------------|-------------|
| `search_airports` | `markers` | With filters: applies filters + loads ALL matching + highlights recommended. Without filters: shows returned airports + highlights all |
| `find_airports_near_route` | `route_with_markers` | Highlights chat airports, triggers route search, shows route line |
| `find_airports_near_location` | `point_with_markers` | Sets locate state, highlights recommended airports, triggers locate search |
| `get_airport_details` | `marker_with_details` | Centers map, shows marker, opens details panel |
| `get_notification_for_airport` | `marker_with_details` | Same as `get_airport_details` |
| `answer_rules_question` | None | Triggers rules panel via `show_rules` field |
| `browse_rules` | None | Triggers rules panel via `show_rules` field |
| `compare_rules_between_countries` | None | Triggers rules panel via `show_rules` field |

**Adding New Filters (Important!):**

All airport filtering uses `FilterEngine` (`shared/filtering/filter_engine.py`) as the single source of truth. Both LangGraph tools and REST API endpoints use the same engine.

**To add a new filter:**

1. **Create Filter class** in `shared/filtering/filters/`
   ```python
   class MyNewFilter(Filter):
       name = "my_filter"
       description = "Filter by something"

       def apply(self, airport, value, context) -> bool:
           # Return True if airport passes filter
   ```

2. **Register in FilterEngine** (`shared/filtering/filter_engine.py`)
   ```python
   FilterRegistry.register(MyNewFilter())
   ```

3. **Add to filter profile** (`shared/airport_tools.py:_build_filter_profile()`)
   ```python
   # For string/number values:
   for key in ["country", ..., "my_filter"]:
   # For boolean values:
   for key in ["has_procedures", ..., "my_filter"]:
   ```

4. **Add REST API query parameter** (`web/server/api/airports.py`)
   ```python
   my_filter: Optional[str] = Query(None, description="...")
   # Then add to filters dict:
   if my_filter:
       filters["my_filter"] = my_filter
   ```

5. **Add frontend support** (if UI control needed)
   - `web/client/ts/store/types.ts` - Add to `FilterConfig`
   - `web/client/ts/adapters/api-adapter.ts` - Add to `transformFiltersToParams()`
   - `web/client/ts/adapters/llm-integration.ts` - Add to `applyFilterProfile()`
   - `web/client/ts/managers/ui-manager.ts` - Add UI control handler and `syncFiltersToUI()`

**Supported Filters:**
- `country`, `has_procedures`, `has_aip_data`, `has_hard_runway`, `point_of_entry`
- `has_avgas`, `has_jet_a`, `hotel`, `restaurant`
- `min_runway_length_ft`, `max_runway_length_ft`, `max_landing_fee`
- `trip_distance`, `exclude_large_airports`

**Special Case:** AIP field filtering (`aip_field`, `aip_value`, `aip_operator`) uses `_matches_aip_field()` helper, not FilterEngine.

See `designs/UI_FILTER_STATE_DESIGN.md` for complete UI, filter, state management, and LLM integration details.

---

## 5. State Management Rules

### 5.1 Single Source of Truth

**Principle:** All application state lives in the Zustand store (`web/client/ts/store/store.ts`).

**Implementation:**
- LLMIntegration updates store via actions only (`store.getState().setX()`)
- No direct state manipulation
- UI updates via store subscriptions (reactive)
- No duplicated state in components

### 5.2 UI Payload Validation Rules

**Visualization Type Validation:**
- Only accept known types: `markers`, `route_with_markers`, `marker_with_details`, `point_with_markers`
- Reject unknown types with warning
- Default to safe behavior (no visualization) if type is invalid

**Filter Profile Validation:**
- Only apply filters that exist in `FilterConfig` type
- Validate filter values match expected types (boolean, string, number)
- Ignore unknown filter keys (don't throw errors)
- Handle null/undefined values gracefully

**Store Action Consistency:**

Each visualization type must map to specific store actions:

- **`markers`** (with filters) → `store.setFilters()` + `store.highlightPoint()` + trigger `trigger-filter-refresh` event
- **`markers`** (without filters) → `store.setAirports()` + `store.highlightPoint()`
- **`route_with_markers`** → `store.setSearchQuery()` + `store.highlightPoint()` + trigger `trigger-search` event
- **`marker_with_details`** → `store.setSearchQuery()` + trigger `trigger-search` and `airport-click` events
- **`point_with_markers`** → `store.setLocate()` + `store.highlightPoint()` + trigger `trigger-locate` event
- **Rules tools** → Dispatch `show-country-rules` event (no store updates)

**No Direct DOM Manipulation:**
- All UI updates must go through store subscriptions
- Use custom events for cross-component communication
- No direct DOM manipulation from LLMIntegration
- UIManager handles DOM updates reactively

**Idempotency:**
- Visualization application should be idempotent
- Filter profile application should be idempotent
- Use flags (`visualizationApplied`, `filterProfileApplied`) to prevent duplicate application
- Re-applying same visualization should not cause side effects

**Event-Based Communication:**
- Use custom events for cross-component actions:
  - `trigger-search` - Trigger search from any component
  - `trigger-locate` - Trigger locate search
  - `trigger-filter-refresh` - Load all airports matching current store filters (for markers with filters)
  - `airport-click` - Open airport details panel
  - `show-country-rules` - Display rules panel
  - `reset-rules-panel` - Reset rules panel
- Store updates trigger reactive UI updates
- No direct method calls across components

---

## 6. Conversation Logging

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
      "arguments": {"from_location": "EGTF", "to_location": "LFMD"},
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

## 7. Next Query Prediction

### 7.1 Overview

**Feature:** Optional node that generates follow-up query suggestions based on the planner's output.

**Status:** Configurable via behavior config (`next_query_prediction.enabled`)

**Location:** `shared/aviation_agent/next_query_predictor.py`, `shared/aviation_agent/graph.py:84`

### 7.2 Implementation

**When Enabled:**
- Runs after planner node, before tool execution
- Uses only plan information (user query, selected tool, arguments)
- Does NOT use tool results (runs before tool execution)

**Process:**
1. Extract context from plan:
   - User query text
   - Selected tool name
   - Tool arguments (including filters)
2. Generate suggestions using rule-based predictor
3. Format for UI: `[{text, tool, category, priority}, ...]`
4. Store in state as `suggested_queries`
5. Include in `ui_payload` for frontend display

**Configuration:**
- `enabled`: Boolean to enable/disable feature
- `max_suggestions`: Maximum number of suggestions to generate

**Benefits:**
- Helps users discover related queries
- Improves user engagement
- Provides context-aware suggestions

---

## 8. Conversation Memory (Checkpointing)

### 8.1 Overview

**Feature:** Multi-turn conversation support using LangGraph checkpointing.

**Status:** Always enabled (thread_id auto-generated if not provided)

**Location:** `shared/aviation_agent/graph.py:352`, `shared/aviation_agent/adapters/streaming.py:68`

### 8.2 Implementation

**Thread ID:**
- Generated if not provided: `thread_{uuid}`
- Required for checkpointing to work
- Included in `done` event for frontend to track

**Checkpointing:**
- Uses LangGraph's built-in checkpointing
- State persists across requests with same `thread_id`
- Conversation history maintained automatically
- Enables context-aware responses

**Usage:**
```python
# First request (new conversation)
request = {"messages": [...], "thread_id": None}  # Auto-generated

# Subsequent requests (continue conversation)
request = {"messages": [...], "thread_id": "thread_abc123"}  # Use from previous response
```

**Benefits:**
- Natural multi-turn conversations
- Context preservation
- Better user experience

---

## 9. Design Principles

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
- UI gets filters from `ui_payload.filters` (flattened field)

**Benefits:**
- Simpler (no separate field)
- Consistent (filters are tool arguments)
- UI gets actual applied filters from tool result

### 6.3 Flattened UI Payload

**Principle:** Flatten commonly-used fields for convenient access. No redundant data.

**Benefits:**
- Convenient UI access (no nesting)
- Reduced bandwidth (no duplicate data)
- Lower token usage (smaller payloads)
- Simpler structure (easier to work with)

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

### 6.6 Store as Single Source of Truth

**Principle:** All application state lives in the Zustand store, no duplicated state.

**Implementation:**
- All state updates go through store actions
- No direct state manipulation
- UI updates via store subscriptions (reactive)
- No component-level state that mirrors store

**Benefits:**
- Predictable state management
- Easier debugging
- Consistent UI updates
- No state synchronization issues

### 6.7 UI Payload Validation

**Principle:** Validate UI payloads before applying to ensure consistency with store state.

**Implementation:**
- Validate visualization types (only accept known types)
- Validate filter profiles (match FilterConfig schema)
- Ignore unknown fields gracefully
- Reject invalid payloads with warnings

**Benefits:**
- Prevents UI errors
- Ensures store consistency
- Graceful degradation
- Better error handling

### 6.8 Idempotency

**Principle:** Visualization and filter profile application should be idempotent.

**Implementation:**
- Use flags to prevent duplicate application
- Re-applying same visualization should not cause side effects
- Filter profile application is idempotent

**Benefits:**
- Safe to re-apply
- No duplicate highlights
- No duplicate filter updates
- Better error recovery

---

## 10. Code Structure

### Current Structure
```
shared/aviation_agent/
  state.py              # AgentState definition
  planning.py           # Planner node + AviationPlan
  execution.py          # ToolRunner
  formatting.py         # Formatter + UI payload building
  graph.py              # Graph assembly
  next_query_predictor.py  # Next query prediction (optional)
  tools.py              # AviationToolClient
  config.py              # Settings and behavior config
  adapters/
    streaming.py        # SSE streaming adapter
    logging.py          # Conversation logging
    __init__.py         # Adapter exports

web/server/api/
  aviation_agent_chat.py  # FastAPI router

web/client/ts/
  adapters/
    llm-integration.ts  # LLM visualization handler
  managers/
    chatbot-manager.ts  # Chatbot UI and SSE event processing
  store/
    store.ts           # Zustand store (single source of truth)
```

---

## 11. Testing Strategy

### Unit Tests
- Test planner filter extraction
- Test tool runner execution
- Test formatter UI payload building
- Test state management
- Test thinking combination
- Test next query predictor
- Test notification enrichment

### Integration Tests
- Test streaming endpoint (SSE events)
- Test event ordering
- Test conversation logging
- Test error handling
- Test token tracking
- Test thread_id generation
- Test checkpointing (multi-turn conversations)

### UI Payload Validation Tests
- Test invalid visualization types are rejected
- Test filter profile validation
- Test store action consistency
- Test idempotency of visualization application
- Test filter profile idempotency

### Visualization Type Tests
- Test each visualization type triggers correct store actions
- Test `markers` type behavior
- Test `route_with_markers` type behavior
- Test `marker_with_details` type behavior
- Test `point_with_markers` type behavior
- Test rules tools trigger rules panel correctly

### E2E Tests
- Test full conversation flow
- Test route planning queries
- Test airport search queries
- Test rules queries
- Test streaming response
- Test multi-turn conversations
- Test next query prediction
- Test notification enrichment
- Test filter profile application

---

## 12. Key Design Decisions

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

### 9.3 Flattened UI Payload (Not Nested Structure)

**Decision:** Flatten commonly-used fields (`filters`, `visualization`, `airports`) for direct access. No redundant `mcp_raw` field.

**Rationale:**
- Convenient UI access (no nesting required)
- Reduced bandwidth (no duplicate data)
- Lower token usage (smaller payloads in LLM context)
- Simpler structure (easier to work with in frontend)
- Clear contract (only flattened fields, no hidden data)

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

### 9.6 Store as Single Source of Truth (Not Component State)

**Decision:** All state lives in Zustand store, no duplicated state in components.

**Rationale:**
- Predictable state management
- Easier debugging
- Consistent UI updates
- No state synchronization issues

### 9.7 UI Payload Validation (Not Blind Application)

**Decision:** Validate UI payloads before applying to ensure consistency with store state.

**Rationale:**
- Prevents UI errors
- Ensures store consistency
- Graceful degradation
- Better error handling

### 9.8 Idempotent Visualization Application (Not Stateful)

**Decision:** Visualization and filter profile application should be idempotent.

**Rationale:**
- Safe to re-apply
- No duplicate highlights
- No duplicate filter updates
- Better error recovery

---

## 13. Future Enhancements

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
- `designs/UI_FILTER_STATE_DESIGN.md` - Complete UI, filter, state management, and LLM visualization design
- `designs/CHATBOT_WEBUI_DESIGN_REVIEW.md` - Review of this document against implementation
- `PHASE5_UI_INTEGRATION_SUMMARY.md` - UI integration details
