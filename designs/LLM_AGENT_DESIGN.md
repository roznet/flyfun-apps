# Aviation Agent – Design & Architecture Guide

This document describes the architecture, components, and design principles for the aviation-focused LangGraph agent that uses the custom **aviation MCP database** (routes, airports, rules) and exposes **structured outputs** suitable for a modern chat UI (including side panels such as maps, airport cards, or rules checklists).

## UI Payload Design (Hybrid Approach)

The agent implements a **hybrid UI payload design**:

- The UI receives a **stable, curated JSON payload (`ui_payload`)**
- It contains:
  - `kind`: `"route"`, `"airport"`, or `"rules"`
  - A small set of stable **top-level fields** (e.g. `departure`, `icao`, `region`)
  - **Flattened commonly-used fields** for convenience (`filters`, `visualization`, `airports`)
  - A **full MCP tool output** stored under the key:  
    ```
    "mcp_raw": { ... }
    ```

- Internally, the agent's planner (`AviationPlan`) is **decoupled** from the UI.
- Only the `build_ui_payload(plan, tool_result)` function must be updated if planner output evolves.

This design strongly isolates UI from internal LLM schema changes while still enabling rich UI behavior and convenient access to common fields.

---

## 1. High-Level Architecture

### Core Design

The agent operates in **three steps via LangGraph**:

1. **Planner Node**
   - LLM with structured output (`AviationPlan`).
   - Selects one aviation tool.
   - Extracts the best possible arguments (including filters).
   - Specifies answer style.

2. **Tool Runner Node**
   - Executes the chosen MCP-backed LangChain tool.
   - Returns raw JSON (`tool_result`).

3. **Formatter Node**
   - Produces:
     - The final answer text.
     - A **UI payload** (`ui_payload`) with hybrid structure:
       ```json
       {
         "kind": "...",
         ... stable high-level fields ...,
         "filters": {...},  // Flattened from mcp_raw.filter_profile
         "visualization": {...},  // Flattened from mcp_raw.visualization
         "airports": [...],  // Flattened from mcp_raw.airports
         "mcp_raw": { ... full MCP response ... }
       }
       ```

### Agent State Flow

```
┌────────┐     ┌─────────────┐     ┌───────────────┐
│ User   │ --> │ Planner Node │ --> │ Tool Runner   │ --> Formatter Node --> UI
└────────┘     └─────────────┘     └───────────────┘
```

The UI receives (via SSE streaming):

- `answer` (markdown, streamed character-by-character)
- `ui_payload` (stable JSON with hybrid structure)
- `thinking` (combined planning + formatting reasoning)
- `plan` (full plan for debugging)
- Token usage statistics

---

## 2. Repository Structure

The agent follows FlyFun's pattern of separating shared Python libraries (`shared/`), FastAPI server code (`web/server/`), and pytest suites (`tests/`).

```
shared/aviation_agent/
  __init__.py
  config.py
  state.py
  planning.py
  execution.py
  formatting.py
  graph.py
  adapters/
    __init__.py
    streaming.py          # SSE streaming adapter
    logging.py            # Conversation logging
    langgraph_runner.py   # Orchestration helpers
```

```
web/server/api/
  aviation_agent_chat.py  # FastAPI router with streaming endpoint
```

```
tests/aviation_agent/
  __init__.py
  conftest.py             # Shared fixtures + MCP doubles
  test_planning.py
  test_execution.py
  test_formatting.py
  test_graph_e2e.py
  test_streaming.py
  test_integration.py
```

### Placement Notes

- `shared/aviation_agent/` keeps the LangGraph stack versioned once and importable from both the web server and any offline scripts.
- The FastAPI router in `web/server/api/aviation_agent_chat.py` is mounted by `web/server/main.py` with feature flag support (`AVIATION_AGENT_ENABLED`).
- Tests live under `tests/aviation_agent/` and follow the repo's pytest discovery pattern.

---

## 3. Web/API Integration

### Router (`web/server/api/aviation_agent_chat.py`)

The FastAPI router:
- Validates chat requests (messages, session IDs).
- Instantiates the agent graph via `build_agent()`.
- Provides streaming endpoint (`/chat/stream`) using SSE.
- Provides non-streaming endpoint (`/chat`) for simple requests.
- Handles conversation logging after execution.
- Returns structured responses with `answer`, `ui_payload`, and metadata.

### Server Integration

The router is included in `web/server/main.py`:

```python
if aviation_agent_chat.feature_enabled():
    app.include_router(
        aviation_agent_chat.router,
        prefix="/api/aviation-agent",
        tags=["aviation-agent"],
    )
```

### Configuration

- `shared/aviation_agent/config.py` reads environment variables from `web/server/dev.env` / `prod.env`.
- `AVIATION_AGENT_ENABLED` feature flag controls router inclusion.
- LLM model configuration via `AVIATION_AGENT_PLANNER_MODEL` and `AVIATION_AGENT_FORMATTER_MODEL`.

---

## 4. Testing Strategy

### Unit Tests

- `test_planning.py` - Planner filter extraction, tool selection
- `test_execution.py` - Tool runner execution
- `test_formatting.py` - UI payload building, visualization enhancement
- `test_state_and_thinking.py` - State management, thinking combination

### Integration Tests

- `test_graph_e2e.py` - Full graph execution
- `test_streaming.py` - SSE event streaming
- `test_integration.py` - FastAPI router integration via TestClient

### Test Fixtures

- Re-use `tests/tools` fixtures for MCP responses
- MCP doubles for isolated testing
- Contract tests that assert `ui_payload` schema stability

---

## 5. Planner Schema & Tool Naming

### Tool Selection

- `AviationPlan.selected_tool` uses the literal MCP tool names defined in `shared/airport_tools.get_shared_tool_specs()` (e.g., `search_airports`, `find_airports_near_route`, `get_airport_details`, `list_rules_for_country`, …).
- Validation in `shared/aviation_agent/planning.py` ensures planner references only tools that exist in the manifest.
- `build_ui_payload()` maps these literal tool names to the three UI `kind` buckets (`route`, `airport`, `rules`).

### Filter Extraction

- Planner extracts user requirements (AVGAS, customs, runway length, country, etc.) into `plan.arguments.filters`.
- Filters are part of tool arguments, not a separate field.
- Tools return `filter_profile` in results, which UI can use for filter synchronization.

---

## 6. Agent State

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: Optional[AviationPlan]
    planning_reasoning: Optional[str]  # Planner's reasoning
    tool_result: Optional[Any]
    formatting_reasoning: Optional[str]  # Formatter's reasoning
    final_answer: Optional[str]
    thinking: Optional[str]  # Combined reasoning for UI
    ui_payload: Optional[dict]  # Stable UI structure (hybrid approach)
    error: Optional[str]  # Error message if execution fails
```

### State Fields

- **`messages`**: Conversation history (uses `operator.add` reducer for automatic accumulation)
- **`plan`**: Structured plan from planner node
- **`planning_reasoning`**: Why the planner selected this tool/approach
- **`tool_result`**: Raw result from tool execution
- **`formatting_reasoning`**: How the formatter presents results
- **`final_answer`**: User-facing response text
- **`thinking`**: Combined reasoning (planning + formatting) for UI display
- **`ui_payload`**: Structured payload for UI integration
- **`error`**: Error message if execution fails

---

## 7. UI Payload Building (`build_ui_payload()`)

### Hybrid Approach

The UI payload uses a **hybrid design**:
- **Stable top-level keys** (`kind`, `departure`, `icao`, etc.)
- **Flattened commonly-used fields** (`filters`, `visualization`, `airports`) for convenience
- **Full MCP result** under `mcp_raw` as authoritative source

### Implementation

```python
def build_ui_payload(plan: AviationPlan, tool_result: dict | None) -> dict | None:
    if tool_result is None:
        return None

    # Determine kind based on tool
    kind = _determine_kind(plan.selected_tool)
    if not kind:
        return None

    # Base payload with kind and mcp_raw (authoritative source)
    base_payload = {
        "kind": kind,
        "mcp_raw": tool_result,
    }

    # Add kind-specific metadata
    if plan.selected_tool in {"search_airports", "find_airports_near_route", "find_airports_near_location"}:
        base_payload["departure"] = (
            plan.arguments.get("from_location") or
            plan.arguments.get("from_icao") or
            plan.arguments.get("departure")
        )
        base_payload["destination"] = (
            plan.arguments.get("to_location") or
            plan.arguments.get("to_icao") or
            plan.arguments.get("destination")
        )
        if plan.arguments.get("ifr") is not None:
            base_payload["ifr"] = plan.arguments.get("ifr")

    elif plan.selected_tool in {
        "get_airport_details",
        "get_border_crossing_airports",
        "get_airport_statistics",
        "get_airport_pricing",
        "get_pilot_reviews",
        "get_fuel_prices",
    }:
        base_payload["icao"] = plan.arguments.get("icao") or plan.arguments.get("icao_code")

    elif plan.selected_tool in {
        "list_rules_for_country",
        "compare_rules_between_countries",
        "get_answers_for_questions",
        "list_rule_categories_and_tags",
        "list_rule_countries",
    }:
        base_payload["region"] = plan.arguments.get("region") or plan.arguments.get("country_code")
        base_payload["topic"] = plan.arguments.get("topic") or plan.arguments.get("category")

    # Flatten commonly-used fields for convenience (hybrid approach)
    if "filter_profile" in tool_result:
        base_payload["filters"] = tool_result["filter_profile"]
    if "visualization" in tool_result:
        base_payload["visualization"] = tool_result["visualization"]
    if "airports" in tool_result:
        base_payload["airports"] = tool_result["airports"]

    return base_payload
```

### Why This Design?

- **Highly stable**: UI structure rarely changes (only `kind` and a few metadata fields at top level)
- **Convenient access**: Common fields (`filters`, `visualization`, `airports`) are flattened for easy UI access
- **Fully future-proof**: Planner can evolve without breaking UI (new fields automatically in `mcp_raw`)
- **Authoritative source**: `mcp_raw` contains complete tool result
- **No breaking changes**: UI can use either flattened fields or `mcp_raw`

---

## 8. Formatter Node

The formatter node produces both the final answer and the UI payload:

```python
def formatter_node(state: AgentState) -> Dict[str, Any]:
    # Format answer using LLM
    answer = formatter_llm.invoke({
        "messages": state.get("messages") or [],
        "answer_style": plan.answer_style,
        "tool_result_json": json.dumps(tool_result, indent=2),
        "pretty_text": tool_result.get("pretty", ""),
    })
    
    # Build UI payload
    ui_payload = build_ui_payload(plan, tool_result)
    
    # Optional: Enhance visualization with ICAOs from answer
    if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
        mentioned_icaos = _extract_icao_codes(answer)
        if mentioned_icaos:
            ui_payload = _enhance_visualization(ui_payload, mentioned_icaos, tool_result)
    
    # Generate formatting reasoning
    formatting_reasoning = f"Formatted answer using {plan.answer_style} style."
    
    # Combine planning and formatting reasoning
    thinking_parts = []
    if state.get("planning_reasoning"):
        thinking_parts.append(state["planning_reasoning"])
    thinking_parts.append(formatting_reasoning)
    
    return {
        "final_answer": answer.strip(),
        "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
        "ui_payload": ui_payload,
    }
```

---

## 9. FastAPI Endpoint

### Streaming Endpoint

```python
@router.post("/chat/stream")
async def aviation_agent_chat_stream(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
    session_id: Optional[str] = None,
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

### Response Schema

**SSE Events:**
- `plan` - Planner output (selected tool, arguments)
- `thinking` - Planning reasoning
- `tool_call_start` - Tool execution started
- `tool_call_end` - Tool execution completed
- `message` - Character-by-character answer stream
- `ui_payload` - Visualization data
- `done` - Request complete (session_id, token counts)
- `error` - Error occurred

### UI Integration

The UI uses `ui_payload` to determine visualization:

- `"kind": "route"` → show route map with markers
- `"kind": "airport"` → show airport info card
- `"kind": "rules"` → show rules panel
- `mcp_raw` provides all underlying details for drawing polylines, markers, etc.
- Flattened fields (`filters`, `visualization`, `airports`) provide convenient access

---

## 10. MCP Tool & Payload Catalog

The shared code centralizes every MCP tool signature in `shared/airport_tools.py`. The agent treats that file as the single source of truth and uses `get_shared_tool_specs()` for planner validation.

### Tool Catalog

| Tool | Required args | Optional args | Default `ui_payload.kind` | Notable `mcp_raw` keys |
| --- | --- | --- | --- | --- |
| `search_airports` | `query` | `max_results`, `filters`, `priority_strategy` | `route` | `airports`, `filter_profile`, `visualization.type='markers'` |
| `find_airports_near_location` | `location_query` | `max_distance_nm`, `filters`, `priority_strategy` | `route` | `center`, `airports`, `filter_profile`, `visualization.type='point_with_markers'` |
| `find_airports_near_route` | `from_location`, `to_location` | `max_distance_nm`, `filters`, `priority_strategy` | `route` | `airports`, `filter_profile`, `visualization.type='route_with_markers'`, `substitutions` |
| `get_airport_details` | `icao_code` | – | `airport` | `airport`, `runways`, `visualization.type='marker_with_details'` |
| `get_border_crossing_airports` | – | `country` | `airport` | `airports`, `by_country`, `filter_profile`, `visualization.style='customs'` |
| `get_airport_statistics` | – | `country` | `airport` | `stats` |
| `get_airport_pricing` | `icao_code` | – | `airport` | `pricing`, `pretty` |
| `get_pilot_reviews` | `icao_code` | `limit` | `airport` | `reviews`, `average_rating` |
| `get_fuel_prices` | `icao_code` | – | `airport` | `fuels`, `pricing` |
| `list_rules_for_country` | `country_code` | `category`, `tags` | `rules` | `rules`, `formatted_text`, `categories` |
| `compare_rules_between_countries` | `country1`, `country2` | `category` | `rules` | `comparison`, `formatted_summary`, `total_differences` |
| `get_answers_for_questions` | `question_ids` | – | `rules` | `items`, `pretty` |
| `list_rule_categories_and_tags` | – | – | `rules` | `categories`, `tags`, `counts` |
| `list_rule_countries` | – | – | `rules` | `items`, `count` |

### Documentation Workflow

1. **Tool manifest** - Tools are defined in `shared/airport_tools.py` as the single source of truth.
2. **Planner alignment** - `AviationPlan.selected_tool` uses literal tool names from the manifest.
3. **UI payload mapping** - `build_ui_payload()` maps tool names to `kind` buckets.
4. **Payload stability** - The `Notable mcp_raw keys` column serves as a contract with the UI.

See `designs/UI_FILTER_STATE_DESIGN.md` for complete tool-to-visualization mapping and LLM integration details.

---

## 11. Design Benefits

### ✔ Stable for the UI
Only `kind`, `departure`, `icao`, etc. matter at the top level. UI structure rarely changes.

### ✔ Convenient Access
Commonly-used fields (`filters`, `visualization`, `airports`) are flattened for easy access.

### ✔ Internal Evolution is Painless
Planner and tool schemas can change freely. New fields automatically appear in `mcp_raw`.

### ✔ Full Richness Preserved
`mcp_raw` always contains everything from the tool result.

### ✔ Clean, Simple UI Dispatch
```typescript
switch(ui_payload.kind) {
  case "route": 
    renderRoute(ui_payload.visualization || ui_payload.mcp_raw.visualization); 
    break;
  case "airport": 
    renderAirport(ui_payload.mcp_raw); 
    break;
  case "rules": 
    renderRules(ui_payload.mcp_raw); 
    break;
}
```

---

## 12. Key Design Principles

### State-Based Thinking
- Reasoning stored in state fields (`planning_reasoning`, `formatting_reasoning`)
- Combined into `thinking` for UI display
- No tag parsing from LLM output

### Filters as Arguments
- Filters are part of `plan.arguments.filters`
- Tools return `filter_profile` (what was actually applied)
- UI gets filters from flattened `ui_payload.filters` or `ui_payload.mcp_raw.filter_profile`

### Error Handling in State
- Errors stored in state (`error` field)
- Formatter can produce error message even on failure
- Errors emitted as SSE events

### LangGraph-Native Patterns
- Uses `astream_events()` for streaming
- Uses state reducers (`operator.add` for messages)
- Errors propagate through state, not exceptions

---

## Related Documents

- `designs/CHATBOT_WEBUI_DESIGN.md` - WebUI integration and streaming details
- `designs/TOOL_VISUALIZATION_MAPPING.md` - Complete tool-to-visualization mapping
