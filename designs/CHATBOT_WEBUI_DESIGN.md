# Chatbot WebUI Design & Migration Plan

## Executive Summary

This document reviews the current chatbot implementation (`chatbot_service.py` + `chatbot_core.py`), analyzes the new LangGraph-based aviation agent (`aviation_agent_chat.py`), and proposes a migration strategy to unify and streamline the chatbot architecture.

**Current State:**
- `chatbot_service.py`: Direct OpenAI API integration with manual tool orchestration
- `chatbot_core.py`: Simple two-phase LLM → tools → LLM loop
- Streaming support with SSE (Server-Sent Events)
- Complex filter generation and visualization extraction logic

**New State:**
- `aviation_agent_chat.py`: LangGraph-based agent with structured planning
- Three-phase pipeline: Planner → Tool Runner → Formatter
- Stable UI payload format (A3 design)
- Better separation of concerns

**Goal:**
Migrate the web UI to use the new agent architecture while preserving streaming, visualization, and user experience features.

---

## 1. Current Architecture Review

### 1.1 `chatbot_service.py` - Main Service Layer

**Responsibilities:**
- LLM client initialization (primary + fallback + answer generation models)
- MCP client integration for tool execution
- System prompt management (very detailed, 600+ lines)
- Filter generation from user messages (LLM-based)
- Streaming response generation with SSE
- Thinking/answer extraction and cleaning
- Visualization data extraction and enhancement
- Conversation logging

**Key Methods:**
- `chat()`: Non-streaming chat endpoint
- `chat_stream()`: Streaming chat with SSE events
- `_generate_filters_from_request()`: LLM-based filter extraction
- `_extract_thinking_and_answer()`: Parse `<thinking>` tags from LLM output
- `_create_visualization_from_icaos()`: Build visualization from mentioned ICAOs
- `_format_tool_response()`: Fallback formatter when LLM fails

**Architecture Pattern:**
```
User Message
  ↓
Filter Generation (LLM call #1)
  ↓
Tool Detection (LLM call #2 with tools)
  ↓
Tool Execution (MCP client)
  ↓
Answer Generation (LLM call #3, streaming)
  ↓
Response (thinking + answer + visualization)
```

**Issues:**
1. **Multiple LLM calls per request** (3-4 calls: filter gen, tool detection, answer gen)
2. **Complex prompt engineering** (600+ line system prompt with many rules)
3. **Tight coupling** between LLM output format and UI expectations
4. **Manual tool orchestration** (no structured planning)
5. **Filter injection logic** (generated filters merged into tool calls)
6. **Visualization extraction** (post-processing LLM output to find ICAOs)

### 1.2 `chatbot_core.py` - Core Orchestration

**Responsibilities:**
- Simple two-phase conversation loop
- Tool execution orchestration
- Message history management
- Fallback formatting when LLM output is unusable

**Architecture:**
```
Messages + Tools
  ↓
LLM Call (with tool_choice="auto")
  ↓
[If tools requested]
  Tool Execution
  ↓
LLM Call (final answer)
  ↓
Extract Thinking + Answer
  ↓
Return Result
```

**Issues:**
1. **No structured planning** (LLM decides tools ad-hoc)
2. **No separation of concerns** (planning, execution, formatting all mixed)
3. **Limited error handling** (basic fallback only)
4. **No UI payload structure** (visualization extracted post-hoc)

### 1.3 Current UI Integration

**Endpoints:**
- `/api/chat/stream` - Streaming chat (SSE)
- `/api/chat/message` - Non-streaming chat

**Response Format:**
```json
{
  "message": "Final answer text",
  "thinking": "Internal reasoning",
  "visualization": { "type": "route_with_markers", ... },
  "tool_calls": [...],
  "history": [...]
}
```

**SSE Events:**
- `event: thinking` - Character-by-character thinking stream
- `event: thinking_done` - Thinking complete
- `event: message` - Character-by-character answer stream
- `event: tool_calls` - Tool execution metadata
- `event: visualization` - Map visualization data
- `event: done` - Request complete with token counts

---

## 2. New Agent Architecture Review

### 2.1 `aviation_agent_chat.py` - FastAPI Router

**Responsibilities:**
- Feature flag checking (`AVIATION_AGENT_ENABLED`)
- Request/response marshaling
- Error handling

**Current Endpoint:**
- `POST /api/aviation-agent/chat` - Non-streaming chat

**Response Format:**
```json
{
  "answer": "Final answer text",
  "planner_meta": { "selected_tool": "...", "arguments": {...} },
  "ui_payload": {
    "kind": "route" | "airport" | "rules",
    "departure": "...",
    "mcp_raw": { ... }
  }
}
```

### 2.2 LangGraph Agent Structure

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
class AgentState:
    messages: List[BaseMessage]
    plan: Optional[AviationPlan]  # Structured plan
    tool_result: Optional[Any]
    final_answer: Optional[str]
    ui_payload: Optional[dict]  # Stable UI structure
```

**Benefits:**
1. **Structured planning** (AviationPlan with selected_tool, arguments, answer_style)
2. **Separation of concerns** (planning, execution, formatting)
3. **Stable UI payload** (A3 design: kind + top-level fields + mcp_raw)
4. **Better testability** (each node can be tested independently)
5. **Tool validation** (planner validates tool exists before execution)

**Limitations:**
1. **No streaming support** (currently synchronous only)
2. **No thinking extraction** (no `<thinking>` tag support)
3. **No filter generation** (filters must come from planner)
4. **No visualization enhancement** (uses raw tool results)

---

## 3. Integration Options & Recommendations

### Option A: Full Migration (Recommended)

**Strategy:** Replace `chatbot_service.py` with agent-based implementation, add streaming support to agent.

**Changes Required:**

1. **Add Streaming to Agent**
   - Stream planner output (optional, for debugging)
   - Stream formatter output (main answer)
   - Add thinking extraction to formatter
   - Emit SSE events from FastAPI router

2. **Add Filter Generation to Planner**
   - Extend `AviationPlan` to include `filters` field
   - Planner LLM extracts filters from user message
   - Tool runner injects filters into tool calls

3. **Enhance UI Payload**
   - Keep A3 structure (kind + mcp_raw)
   - Add visualization enhancement in formatter
   - Extract ICAOs from final_answer and enrich visualization

4. **Preserve Features**
   - Conversation logging (move to adapter layer)
   - Token tracking (add to agent state)
   - Error handling (improve agent error propagation)

**Implementation Steps:**
1. Add streaming support to `formatting.py` (stream formatter LLM)
2. Add thinking extraction to formatter (parse `<thinking>` tags)
3. Extend `AviationPlan` with `filters` field
4. Update planner to extract filters
5. Add SSE streaming adapter in `fastapi_io.py`
6. Update `aviation_agent_chat.py` to support streaming endpoint
7. Migrate conversation logging to adapter
8. Update UI to consume new endpoint format

**Pros:**
- Single codebase, no duplication
- Better architecture (separation of concerns)
- Structured planning improves reliability
- Stable UI payload reduces UI breakage
- Easier to test and maintain

**Cons:**
- Larger migration effort
- Need to preserve all existing features
- Risk of breaking changes during migration

### Option B: Parallel Operation (Transitional)

**Strategy:** Keep both systems running, route requests based on feature flag or user preference.

**Changes Required:**
1. Add feature flag to route requests
2. Keep both endpoints active
3. Gradually migrate users to new endpoint
4. Monitor usage and errors

**Pros:**
- Low risk (can rollback easily)
- Allows A/B testing
- Gradual migration

**Cons:**
- Code duplication
- Maintenance burden (two systems)
- User confusion (different endpoints)

### Option C: Hybrid Approach (Pragmatic)

**Strategy:** Use agent for planning and tool execution, keep current streaming/formatting logic.

**Changes Required:**
1. Replace tool detection with agent planner
2. Use agent tool runner for execution
3. Keep current streaming/formatting logic
4. Gradually migrate formatting to agent formatter

**Pros:**
- Incremental migration
- Preserves existing streaming
- Reduces risk

**Cons:**
- Partial migration (not fully unified)
- Still some duplication
- Complex integration points

---

## 4. Recommended Migration Plan (Option A)

### Phase 1: Foundation (Week 1-2)

**Goal:** Add streaming and thinking support to agent

**Tasks:**
1. ✅ Extend `AgentState` with `thinking` field
2. ✅ Add streaming support to `formatting.py` (stream formatter LLM)
3. ✅ Add thinking extraction to formatter (parse `<thinking>` tags)
4. ✅ Create SSE streaming adapter in `adapters/fastapi_io.py`
5. ✅ Add streaming endpoint to `aviation_agent_chat.py`

**Deliverables:**
- Streaming agent endpoint: `/api/aviation-agent/chat/stream`
- SSE events: `thinking`, `message`, `tool_calls`, `ui_payload`, `done`

### Phase 2: Feature Parity (Week 3-4)

**Goal:** Add filter generation and visualization enhancement

**Tasks:**
1. ✅ Extend `AviationPlan` with `filters: Optional[Dict[str, Any]]` field
2. ✅ Update planner prompt to extract filters from user message
3. ✅ Update tool runner to inject filters into tool calls
4. ✅ Add visualization enhancement to formatter (extract ICAOs from answer)
5. ✅ Add conversation logging to adapter layer

**Deliverables:**
- Filter generation in planner
- Enhanced visualizations
- Conversation logging

### Phase 3: UI Integration (Week 5)

**Goal:** Update UI to use new endpoint

**Tasks:**
1. ✅ Update frontend to consume `/api/aviation-agent/chat/stream`
2. ✅ Map `ui_payload` to visualization components
3. ✅ Handle new response format
4. ✅ Test end-to-end flows

**Deliverables:**
- Updated UI using agent endpoint
- All features working

### Phase 4: Cleanup (Week 6)

**Goal:** Remove old chatbot service

**Tasks:**
1. ✅ Remove `chatbot_service.py` (or mark as deprecated)
2. ✅ Remove `chatbot_core.py` (or keep for reference)
3. ✅ Update documentation
4. ✅ Remove feature flags

**Deliverables:**
- Clean codebase
- Single chatbot implementation

---

## 5. Technical Design Details

### 5.1 Streaming Agent Implementation

**New File: `shared/aviation_agent/adapters/streaming.py`**

```python
from typing import AsyncIterator, Dict, Any
from langchain_core.runnables import Runnable
from langgraph.graph import StateGraph

async def stream_aviation_agent(
    messages: List[BaseMessage],
    graph: StateGraph,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream agent execution with SSE-compatible events.
    
    Yields:
        - {"event": "thinking", "data": {"content": "..."}}
        - {"event": "plan", "data": {...}}
        - {"event": "tool_call", "data": {...}}
        - {"event": "message", "data": {"content": "..."}}
        - {"event": "ui_payload", "data": {...}}
        - {"event": "done", "data": {...}}
    """
    # Stream planner output (optional, for debugging)
    # Stream formatter output (main answer with thinking extraction)
    # Emit tool calls and UI payload
    pass
```

**Integration in `aviation_agent_chat.py`:**

```python
@router.post("/chat/stream")
async def aviation_agent_chat_stream(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
) -> StreamingResponse:
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")
    
    graph = build_agent(settings=settings)
    
    async def event_generator():
        async for event in stream_aviation_agent(
            request.to_langchain(),
            graph
        ):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### 5.2 Filter Generation in Planner

**Update `AviationPlan`:**

```python
class AviationPlan(BaseModel):
    selected_tool: str
    arguments: Dict[str, Any] = {}
    answer_style: str = "concise"
    filters: Optional[Dict[str, Any]] = None  # NEW
```

**Update Planner Prompt:**

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", """...existing prompt...
    
    **Filter Extraction:**
    If the user mentions specific requirements (AVGAS, customs, runway length, etc.),
    extract them as a filters object and include in your plan.
    """),
    MessagesPlaceholder(variable_name="messages"),
])
```

**Update Tool Runner:**

```python
def run(self, plan: AviationPlan) -> Dict[str, Any]:
    args = plan.arguments.copy()
    
    # Inject filters if tool supports them
    if plan.filters and plan.selected_tool in FILTERABLE_TOOLS:
        if 'filters' not in args:
            args['filters'] = {}
        args['filters'].update(plan.filters)
    
    return self.tool_client.invoke(plan.selected_tool, args)
```

### 5.3 Visualization Enhancement

**Update Formatter:**

```python
def build_formatter_runnable(llm: Runnable) -> Runnable:
    # ... existing code ...
    
    def _invoke(payload: Dict[str, Any]) -> Dict[str, Any]:
        # ... existing formatting ...
        
        ui_payload = build_ui_payload(plan, tool_result)
        
        # Enhance visualization with ICAOs from answer
        if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
            mentioned_icaos = extract_icao_codes(final_answer)
            if mentioned_icaos:
                ui_payload = enhance_visualization(
                    ui_payload,
                    mentioned_icaos,
                    tool_result
                )
        
        return {
            "final_answer": final_answer.strip(),
            "ui_payload": ui_payload,
        }
```

### 5.4 Conversation Logging

**New File: `shared/aviation_agent/adapters/logging.py`**

```python
def log_conversation(
    session_id: str,
    messages: List[BaseMessage],
    state: AgentState,
    start_time: float,
    end_time: float,
):
    """Log conversation to JSON file (reuse existing format)."""
    # Extract from state: plan, tool_result, final_answer, thinking
    # Save to conversation_logs/ directory
    pass
```

---

## 6. UI Payload Mapping

### Current Format → New Format

**Old:**
```json
{
  "visualization": {
    "type": "route_with_markers",
    "route": {...},
    "markers": [...]
  }
}
```

**New:**
```json
{
  "ui_payload": {
    "kind": "route",
    "departure": "EGTF",
    "destination": "LFMD",
    "mcp_raw": {
      "visualization": {
        "type": "route_with_markers",
        "route": {...},
        "markers": [...]
      },
      "airports": [...],
      "filter_profile": {...}
    }
  }
}
```

**UI Changes:**
- Check `ui_payload.kind` to determine visualization type
- Use `ui_payload.mcp_raw.visualization` for map data
- Use `ui_payload.mcp_raw.airports` for airport list
- Use `ui_payload.mcp_raw.filter_profile` for filter display

---

## 7. Testing Strategy

### Unit Tests
- Test planner filter extraction
- Test tool runner filter injection
- Test formatter thinking extraction
- Test UI payload building

### Integration Tests
- Test streaming endpoint (SSE events)
- Test visualization enhancement
- Test conversation logging
- Test error handling

### E2E Tests
- Test full conversation flow
- Test route planning queries
- Test airport search queries
- Test rules queries
- Test streaming response

---

## 8. Migration Checklist

### Pre-Migration
- [ ] Review current chatbot usage patterns
- [ ] Document all current features
- [ ] Set up feature flag system
- [ ] Create migration branch

### Phase 1: Foundation
- [ ] Add streaming support to agent
- [ ] Add thinking extraction
- [ ] Create SSE adapter
- [ ] Add streaming endpoint
- [ ] Test streaming with simple queries

### Phase 2: Feature Parity
- [ ] Add filter generation to planner
- [ ] Add visualization enhancement
- [ ] Add conversation logging
- [ ] Test all features

### Phase 3: UI Integration
- [ ] Update frontend to new endpoint
- [ ] Map UI payload to components
- [ ] Test end-to-end
- [ ] Update documentation

### Phase 4: Cleanup
- [ ] Remove old chatbot service
- [ ] Remove feature flags
- [ ] Update all documentation
- [ ] Final testing

---

## 9. Risks & Mitigation

### Risk 1: Breaking Changes
**Mitigation:** Feature flags, parallel operation during migration, comprehensive testing

### Risk 2: Performance Regression
**Mitigation:** Benchmark current vs. new, optimize agent execution, cache where possible

### Risk 3: Missing Features
**Mitigation:** Feature parity checklist, thorough testing, user feedback

### Risk 4: UI Compatibility
**Mitigation:** UI payload mapping layer, backward compatibility during transition

---

## 10. Success Criteria

1. ✅ All current features work with new agent
2. ✅ Streaming performance is equal or better
3. ✅ UI payload structure is stable (A3 design)
4. ✅ Code is cleaner and more maintainable
5. ✅ Tests cover all critical paths
6. ✅ Documentation is updated

---

## 11. Open Questions

1. **Should we keep the old chatbot service as fallback?**
   - Recommendation: No, but keep code for reference during migration

2. **How to handle multi-turn conversations?**
   - Agent already supports message history, should work as-is

3. **Should we add tool call streaming?**
   - Recommendation: Yes, for better UX (show tool execution progress)

4. **How to handle errors in agent?**
   - Recommendation: Propagate errors through state, return error in response

5. **Should we add retry logic?**
   - Recommendation: Yes, for transient failures (LLM API, MCP connection)

---

## 12. Next Steps

1. **Review this document** with team
2. **Decide on migration option** (recommend Option A)
3. **Create migration branch** and start Phase 1
4. **Set up feature flags** for gradual rollout
5. **Begin implementation** following the phased plan

---

## Appendix: Code Structure Comparison

### Current Structure
```
web/server/
  chatbot_service.py (1470 lines)
  chatbot_core.py (174 lines)
  mcp_client.py
  main.py
```

### New Structure
```
shared/aviation_agent/
  planning.py
  execution.py
  formatting.py
  graph.py
  state.py
  adapters/
    langgraph_runner.py
    fastapi_io.py
    streaming.py (NEW)
    logging.py (NEW)

web/server/api/
  aviation_agent_chat.py
```

### Unified Structure (After Migration)
```
shared/aviation_agent/
  [all existing files]
  adapters/
    [all adapters including streaming, logging]

web/server/api/
  aviation_agent_chat.py (streaming + non-streaming)
  [chatbot_service.py removed or deprecated]
```

