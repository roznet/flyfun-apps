# Chatbot WebUI Design & Migration Plan

## Executive Summary

This document reviews the current chatbot implementation (`chatbot_service.py` + `chatbot_core.py`), analyzes the new LangGraph-based aviation agent (`aviation_agent_chat.py`), and proposes a **FULL MIGRATION** strategy to unify and streamline the chatbot architecture.

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
**FULL MIGRATION** - Replace old chatbot service completely with agent-based implementation, preserving all features (streaming, thinking, filters, visualization).

---

## Migration Decision: FULL MIGRATION (Option A)

✅ **Decision Made:** Complete replacement of `chatbot_service.py` and `chatbot_core.py` with agent-based implementation.

**Key Requirements:**
1. ✅ Add streaming support to agent (SSE events)
2. ✅ Add thinking extraction (parse `<thinking>` tags)
3. ✅ Add filter generation (extract in planner, inject in tool runner)
4. ✅ Add visualization enhancement (extract ICAOs from answer)
5. ✅ Add conversation logging
6. ✅ Preserve all current features
7. ✅ Remove old code completely after migration

**What Needs to Be Updated in Agent:**

### Core Agent Changes:
1. **`state.py`** - Add `planning_reasoning`, `formatting_reasoning`, `thinking`, `error` fields
2. **`planning.py`** - Update prompt to extract filters into `arguments.filters` (no separate field needed)
3. **`execution.py`** - Use `plan.arguments.filters` directly (no injection needed)
4. **`formatting.py`** - Add streaming support, ICAO extraction, visualization enhancement
5. **`graph.py`** - Combine reasoning into `thinking` field in formatter node
6. **`adapters/streaming.py`** - NEW: LangGraph streaming adapter with SSE events + token tracking
7. **`adapters/logging.py`** - NEW: Conversation logging using LangGraph events
8. **`aviation_agent_chat.py`** - Add `/chat/stream` endpoint

### Features to Preserve:
- ✅ Streaming with SSE (thinking + message events)
- ✅ Filter generation from user messages
- ✅ Visualization extraction and enhancement
- ✅ Conversation logging
- ✅ Token tracking
- ✅ Error handling
- ✅ Multi-turn conversations

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

**Changes Required:**

1. **Update `AgentState`** - Add `thinking` and `error` fields
2. **Update `AviationPlan`** - Add `filters` field
3. **Update `formatting.py`** - Add streaming support and thinking extraction
4. **Create `adapters/streaming.py`** - LangGraph streaming adapter
5. **Update `aviation_agent_chat.py`** - Add streaming endpoint

**Step 1: Update `state.py`**

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: Optional[AviationPlan]
    planning_reasoning: Optional[str]  # NEW: Planner's reasoning (why this tool/approach)
    tool_result: Optional[Any]
    formatting_reasoning: Optional[str]  # NEW: Formatter's reasoning (how to present results)
    final_answer: Optional[str]
    thinking: Optional[str]  # NEW: Combined reasoning for UI (planning + formatting)
    ui_payload: Optional[dict]
    error: Optional[str]  # NEW: Error message if execution fails
```

**Why state-based thinking is better:**
- ✅ **Structured** - Explicit state fields, not parsed from text
- ✅ **Reliable** - Doesn't depend on LLM format compliance
- ✅ **Streamable** - Can emit thinking as nodes execute
- ✅ **Testable** - Can assert on thinking state directly
- ✅ **LangGraph-native** - Uses state management, not text parsing

**Step 2: Update `planning.py` - Extract filters into arguments.filters**

**Key Insight:** No separate `filters` field needed! Filters are just part of tool arguments. Tools return `filter_profile` in results, which UI can use.

```python
# AviationPlan stays the same - no filters field needed
class AviationPlan(BaseModel):
    selected_tool: str
    arguments: Dict[str, Any] = {}  # Filters go here: arguments.filters
    answer_style: str = "narrative_markdown"
```

**Update planner prompt to extract filters into arguments:**

```python
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are AviationPlan, a planning agent that selects exactly one aviation tool.\n"
            "Tools:\n{tool_catalog}\n\n"
            "**Filter Extraction:**\n"
            "If the user mentions specific requirements (AVGAS, customs, runway length, country, etc.),\n"
            "extract them as a 'filters' object in the 'arguments' field. Only include filters the user explicitly requests.\n"
            "Available filters: has_avgas, has_jet_a, has_hard_runway, has_procedures, point_of_entry,\n"
            "country (ISO-2 code), min_runway_length_ft, max_runway_length_ft, max_landing_fee.\n\n"
            "Example: If user says 'fuel stop with AVGAS', set arguments.filters = {{'has_avgas': true}}\n\n"
            "Always return JSON that matches this schema:\n{schema}\n"
            "Pick the tool that can produce the most authoritative answer for the pilot."
        ),
    ),
    # ... rest of prompt
])

# In planner_node, generate reasoning:
def planner_node(state: AgentState) -> Dict[str, Any]:
    plan: AviationPlan = planner.invoke({"messages": state.get("messages") or []})
    
    # Generate reasoning from plan
    reasoning_parts = [f"Selected tool: {plan.selected_tool}"]
    if plan.arguments.get("filters"):
        filter_str = ", ".join(f"{k}={v}" for k, v in plan.arguments["filters"].items())
        reasoning_parts.append(f"with filters: {filter_str}")
    if plan.arguments:
        other_args = {k: v for k, v in plan.arguments.items() if k != "filters"}
        if other_args:
            arg_str = ", ".join(f"{k}={v}" for k, v in other_args.items())
            reasoning_parts.append(f"with arguments: {arg_str}")
    
    reasoning = ". ".join(reasoning_parts) + "."
    
    return {
        "plan": plan,
        "planning_reasoning": reasoning
    }
```

**Benefits:**
- ✅ **Simpler** - No separate field, filters are just arguments
- ✅ **UI gets filters from** `ui_payload.mcp_raw.filter_profile` (what tool actually applied)
- ✅ **Consistent** - Filters are part of tool call, not separate metadata

**Step 4: Update `formatting.py` - Add streaming and state-based thinking**

**Note:** We use state-based thinking instead of tag parsing. The formatter can optionally generate reasoning, but it's stored in state, not extracted from text.

def build_formatter_runnable(llm: Runnable, stream: bool = False) -> Runnable:
    """
    Return a runnable that converts planner/tool output into the final answer + UI payload.
    
    If stream=True, returns a streaming runnable that yields chunks.
    
    Note: Thinking is handled via state (planning_reasoning + formatting_reasoning),
    not extracted from LLM output tags.
    """
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            (
                "You are an aviation assistant. Use the tool findings to answer the pilot's question.\n"
                "Always cite operational caveats when data may be outdated. Prefer concise Markdown.\n"
                "Provide clear, helpful information with references to map visualization when applicable."
            ),
        ),
        MessagesPlaceholder(variable_name="messages"),
            (
            "human",
            (
                "Planner requested style: {answer_style}\n"
                "Tool result summary (JSON):\n{tool_result_json}\n"
                "Pretty text (if available):\n{pretty_text}\n\n"
                "Produce the final pilot-facing response in Markdown."
            ),
        ),
    ])

    if stream:
        # Streaming version - SIMPLIFIED: No tag parsing, thinking comes from state
        chain = prompt | llm | StrOutputParser()
        
        async def _astream(payload: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
            plan: AviationPlan = payload["plan"]
            tool_result = payload.get("tool_result") or {}
            
            full_response = ""
            
            # Stream LLM output directly - simple and fast
            async for chunk in chain.astream({
                "messages": payload["messages"],
                "answer_style": plan.answer_style,
                "tool_result_json": json.dumps(tool_result, indent=2, ensure_ascii=False),
                "pretty_text": tool_result.get("pretty", ""),
            }):
                full_response += chunk
                # Stream directly as message - no tag parsing needed!
                yield {"type": "message", "content": chunk}
            
            # Finalize
            answer = full_response.strip()
            ui_payload = build_ui_payload(plan, tool_result)
            
            # Optional: Enhance visualization with ICAOs from answer
            mentioned_icaos = []
            if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
                mentioned_icaos = _extract_icao_codes(answer)
                if mentioned_icaos:
                    ui_payload = _enhance_visualization(ui_payload, mentioned_icaos, tool_result)
            
            # Generate simple formatting reasoning (not from LLM, from our logic)
            formatting_reasoning = f"Formatted answer using {plan.answer_style} style."
            if mentioned_icaos:
                formatting_reasoning += f" Mentioned {len(mentioned_icaos)} airports."
            
            yield {"type": "done", "answer": answer, "formatting_reasoning": formatting_reasoning, "ui_payload": ui_payload}
        
        return RunnableLambda(_astream)
    else:
        # Non-streaming version (existing)
        chain = prompt | llm | StrOutputParser()
        
        def _invoke(payload: Dict[str, Any]) -> Dict[str, Any]:
            plan: AviationPlan = payload["plan"]
            tool_result = payload.get("tool_result") or {}
            final_answer = chain.invoke({
                "messages": payload["messages"],
                "answer_style": plan.answer_style,
                "tool_result_json": json.dumps(tool_result, indent=2, ensure_ascii=False),
                "pretty_text": tool_result.get("pretty", ""),
            })
            
            answer = final_answer.strip()
            ui_payload = build_ui_payload(plan, tool_result)
            
            # Enhance visualization
            if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
                mentioned_icaos = _extract_icao_codes(answer)
                if mentioned_icaos:
                    ui_payload = _enhance_visualization(ui_payload, mentioned_icaos, tool_result)
            
            # Generate simple formatting reasoning
            formatting_reasoning = f"Formatted answer using {plan.answer_style} style."
            
            return {
                "final_answer": answer,
                "formatting_reasoning": formatting_reasoning,
                "ui_payload": ui_payload,
            }
        
        return RunnableLambda(_invoke)

def _extract_icao_codes(text: str) -> List[str]:
    """Extract ICAO airport codes (4 uppercase letters) from text."""
    pattern = r'\b([A-Z]{4})\b'
    matches = re.findall(pattern, text)
    seen = set()
    return [code for code in matches if code not in seen and not seen.add(code)]

def _enhance_visualization(
    ui_payload: Dict[str, Any],
    mentioned_icaos: List[str],
    tool_result: Dict[str, Any]
) -> Dict[str, Any]:
    """Enhance visualization with airports mentioned in answer."""
    # Implementation: fetch full airport data for mentioned ICAOs
    # and merge into ui_payload.mcp_raw.visualization
    # (Similar to chatbot_service._create_visualization_from_icaos)
    return ui_payload
```

**Step 5: Create `adapters/streaming.py` with token tracking**

**LangGraph Pattern:** Use `astream_events()` to capture LLM events and extract token usage. This is the standard LangGraph approach.

```python
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Dict, Any, List

from langchain_core.messages import BaseMessage
from langgraph.graph import CompiledGraph

from ..state import AgentState

logger = logging.getLogger(__name__)


async def stream_aviation_agent(
    messages: List[BaseMessage],
    graph: CompiledGraph,
    session_id: Optional[str] = None,  # NEW: Pass from request
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream agent execution with SSE-compatible events and token tracking.
    
    Uses LangGraph's astream_events() which is the standard pattern for:
    - Streaming node execution
    - Tracking token usage from LLM calls
    - Capturing tool execution
    """
    """
    Stream agent execution with SSE-compatible events.
    
    Uses LangGraph's astream_events() to capture node execution and LLM streaming.
    
    Yields SSE events:
        - {"event": "plan", "data": {...}} - Planner output
        - {"event": "tool_call_start", "data": {"name": "...", "arguments": {...}}}
        - {"event": "tool_call_end", "data": {"name": "...", "result": {...}}}
        - {"event": "thinking", "data": {"content": "..."}} - Character-by-character thinking
        - {"event": "thinking_done", "data": {}} - Thinking complete
        - {"event": "message", "data": {"content": "..."}} - Character-by-character answer
        - {"event": "ui_payload", "data": {...}} - Visualization data
        - {"event": "done", "data": {"session_id": "...", "tokens": {...}}}
        - {"event": "error", "data": {"message": "..."}} - Error occurred
    """
    # Track token usage across all LLM calls
    total_input_tokens = 0
    total_output_tokens = 0
    
    try:
        # Use LangGraph's astream_events for fine-grained streaming
        # This is the standard LangGraph pattern for streaming + token tracking
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
            include_names=["planner", "tool", "formatter"],
        ):
            kind = event.get("event")
            
            if kind == "on_chain_start" and event.get("name") == "planner":
                # Planner started
                continue
            
            elif kind == "on_chain_end" and event.get("name") == "planner":
                # Planner completed - emit plan and thinking
                output = event.get("data", {}).get("output", {})
                plan = output.get("plan") if isinstance(output, dict) else output
                
                if plan:
                    plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan
                    yield {
                        "event": "plan",
                        "data": plan_dict
                    }
                
                # Emit thinking if planning_reasoning is available
                if isinstance(output, dict) and output.get("planning_reasoning"):
                    yield {
                        "event": "thinking",
                        "data": {"content": output["planning_reasoning"]}
                    }
            
            elif kind == "on_chain_start" and event.get("name") == "tool":
                # Tool execution started
                plan = event.get("data", {}).get("input", {}).get("plan")
                if plan:
                    yield {
                        "event": "tool_call_start",
                        "data": {
                            "name": plan.selected_tool,
                            "arguments": plan.arguments
                        }
                    }
            
            elif kind == "on_chain_end" and event.get("name") == "tool":
                # Tool execution completed
                result = event.get("data", {}).get("output", {}).get("tool_result")
                plan = event.get("data", {}).get("input", {}).get("plan")
                if plan and result:
                    yield {
                        "event": "tool_call_end",
                        "data": {
                            "name": plan.selected_tool,
                            "arguments": plan.arguments,
                            "result": result
                        }
                    }
            
            # Track token usage from LLM calls (LangGraph standard pattern)
            elif kind == "on_llm_end":
                # Extract token usage from LLM response
                usage = event.get("data", {}).get("output", {}).get("response_metadata", {}).get("token_usage")
                if usage:
                    total_input_tokens += usage.get("prompt_tokens", 0)
                    total_output_tokens += usage.get("completion_tokens", 0)
            
            elif kind == "on_llm_stream" and event.get("name") == "formatter":
                # Stream formatter LLM output
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield {
                        "event": "message",
                        "data": {"content": chunk.content}
                    }
            
            elif kind == "on_chain_end" and event.get("name") == "formatter":
                # Formatter completed - emit final results
                output = event.get("data", {}).get("output", {})
                
                if isinstance(output, dict):
                    # Emit thinking if available (combined from planning + formatting)
                    if output.get("thinking"):
                        # Thinking was already streamed from planner, just mark as done
                        yield {
                            "event": "thinking_done",
                            "data": {}
                        }
                    
                    # Emit error if present
                    if output.get("error"):
                        yield {
                            "event": "error",
                            "data": {"message": output["error"]}
                        }
                    
                    # Emit UI payload
                    if output.get("ui_payload"):
                        yield {
                            "event": "ui_payload",
                            "data": output.get("ui_payload")
                        }
                    
                    # Emit done event
                    yield {
                        "event": "done",
                        "data": {
                            "session_id": session_id,
                            "tokens": {
                                "input": total_input_tokens,
                                "output": total_output_tokens,
                                "total": total_input_tokens + total_output_tokens
                            }
                        }
                    }
        
    except Exception as e:
        logger.exception("Error in stream_aviation_agent")
        yield {
            "event": "error",
            "data": {"message": str(e)}
        }
```

**Step 5: Update `graph.py` - Combine thinking + error handling**

```python
def build_agent_graph(planner, tool_runner: ToolRunner, formatter):
    graph = StateGraph(AgentState)
    
    def planner_node(state: AgentState) -> Dict[str, Any]:
        try:
            plan: AviationPlan = planner.invoke({"messages": state.get("messages") or []})
            # Generate simple reasoning from plan
            reasoning = f"Selected tool: {plan.selected_tool}"
            if plan.arguments.get("filters"):
                filter_str = ", ".join(f"{k}={v}" for k, v in plan.arguments["filters"].items())
                reasoning += f" with filters: {filter_str}"
            return {"plan": plan, "planning_reasoning": reasoning}
        except Exception as e:
            return {"error": str(e)}
    
    def tool_node(state: AgentState) -> Dict[str, Any]:
        if state.get("error"):
            return {}  # Skip if planner failed
        plan = state.get("plan")
        if not plan:
            return {"error": "No plan available"}
        try:
            result = tool_runner.run(plan)
            return {"tool_result": result}
        except Exception as e:
            return {"error": str(e)}
    
    def formatter_node(state: AgentState) -> Dict[str, Any]:
        # Handle errors gracefully
        if state.get("error"):
            return {
                "final_answer": f"I encountered an error: {state['error']}. Please try again.",
                "error": state["error"],
                "thinking": state.get("planning_reasoning", ""),
            }
        
        try:
            formatted = formatter.invoke({
                "messages": state.get("messages") or [],
                "plan": state.get("plan"),
                "tool_result": state.get("tool_result"),
            })
            
            # Combine planning and formatting reasoning
            thinking_parts = []
            if state.get("planning_reasoning"):
                thinking_parts.append(state["planning_reasoning"])
            if formatted.get("formatting_reasoning"):
                thinking_parts.append(formatted["formatting_reasoning"])
            
            return {
                "final_answer": formatted.get("final_answer", ""),
                "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
                "ui_payload": formatted.get("ui_payload"),
            }
        except Exception as e:
            return {
                "final_answer": f"Error formatting response: {str(e)}",
                "error": str(e),
                "thinking": state.get("planning_reasoning", ""),
            }
    
    graph.add_node("planner", planner_node)
    graph.add_node("tool", tool_node)
    graph.add_node("formatter", formatter_node)
    
    graph.set_entry_point("planner")
    graph.add_edge("planner", "tool")
    graph.add_edge("tool", "formatter")
    graph.add_edge("formatter", END)
    
    return graph.compile()
```

**Benefits:**
- ✅ **LangGraph-native error handling** - Errors in state, not exceptions
- ✅ **Graceful degradation** - Formatter can still produce error message
- ✅ **State-based thinking** - Combined from planning + formatting reasoning

**Step 6: Update `aviation_agent_chat.py` - Add streaming endpoint**

```python
from fastapi.responses import StreamingResponse
import json

@router.post("/chat/stream")
async def aviation_agent_chat_stream(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
) -> StreamingResponse:
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")
    
    try:
        graph = build_agent(settings=settings)
        
        async def event_generator():
            session_id = getattr(request, 'session_id', None)  # Extract from request if available
            async for event in stream_aviation_agent(
                request.to_langchain(),
                graph,
                session_id=session_id
            ):
                event_name = event.get("event")
                event_data = event.get("data", {})
                yield f"event: {event_name}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as exc:
        logger.exception("Aviation agent streaming failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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

**Update `planning.py` - Add filters to AviationPlan:**

```python
class AviationPlan(BaseModel):
    selected_tool: str
    arguments: Dict[str, Any] = {}
    answer_style: str = "narrative_markdown"
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extracted filters from user message (AVGAS, customs, runway length, etc.)"
    )
```

**Update Planner Prompt in `planning.py`:**

```python
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are AviationPlan, a planning agent that selects exactly one aviation tool.\n"
            "Tools:\n{tool_catalog}\n\n"
            "**Filter Extraction:**\n"
            "If the user mentions specific requirements, extract them as a filters object:\n"
            "- has_avgas: Boolean (user mentions AVGAS or piston fuel)\n"
            "- has_jet_a: Boolean (user mentions Jet-A or jet fuel)\n"
            "- has_hard_runway: Boolean (user mentions paved/hard/asphalt runway)\n"
            "- has_procedures: Boolean (user mentions IFR/instrument procedures)\n"
            "- point_of_entry: Boolean (user mentions customs/border crossing)\n"
            "- country: String ISO-2 code (user mentions specific country)\n"
            "- min_runway_length_ft: Number (user specifies minimum runway length)\n"
            "- max_runway_length_ft: Number (user specifies maximum runway length)\n"
            "- max_landing_fee: Number (user mentions price limit)\n\n"
            "ONLY include filters that the user explicitly requests. Return null if no filters needed.\n\n"
            "Always return JSON that matches this schema:\n{schema}\n"
            "Pick the tool that can produce the most authoritative answer for the pilot."
        ),
    ),
    # ... rest of prompt
])
```

**Update `execution.py` - No changes needed!**

Filters are already in `plan.arguments.filters`, so tool runner just uses them directly:

```python
class ToolRunner:
    def run(self, plan: AviationPlan) -> Dict[str, Any]:
        # Filters are already in plan.arguments.filters (if planner extracted them)
        # Tool will use them and return filter_profile in result
        return self.tool_client.invoke(plan.selected_tool, plan.arguments)
```

**Tool results include `filter_profile`** which UI can use:
- `tool_result.filter_profile` contains what filters were actually applied
- UI gets this from `ui_payload.mcp_raw.filter_profile`

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

## 11. Thinking Tag Analysis & Better Approach

### Current Thinking Tag Implementation

**What it does:**
- The LLM is instructed to wrap internal reasoning in `<thinking>...</thinking>` tags
- The service extracts thinking from the LLM output and streams it separately
- Thinking is shown in a separate UI panel (internal reasoning)
- Final answer is shown as the main message (user-facing response)

**Problems with tag-based approach:**
1. **Relies on LLM following format** - LLM might not always use tags correctly
2. **Post-processing required** - Need to parse and clean tags from output
3. **Not structured** - Thinking is just text, not structured data
4. **Hard to stream** - Need character-by-character parsing during streaming

### Better LangGraph-Native Approach

**Store thinking in AgentState directly:**

Instead of parsing tags from LLM output, we can:
1. **Planner node** - Emit reasoning as `planning_reasoning` in state
2. **Formatter node** - Emit reasoning as `formatting_reasoning` in state
3. **Combine** - Merge both into `thinking` field for UI display

**Benefits:**
- ✅ **Structured** - Thinking is explicit state, not parsed from text
- ✅ **Reliable** - Doesn't depend on LLM format compliance
- ✅ **Streamable** - Can stream thinking as it's generated in nodes
- ✅ **Testable** - Can assert on thinking state directly

**Implementation:**

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: Optional[AviationPlan]
    planning_reasoning: Optional[str]  # NEW: Planner's reasoning
    tool_result: Optional[Any]
    formatting_reasoning: Optional[str]  # NEW: Formatter's reasoning
    final_answer: Optional[str]
    thinking: Optional[str]  # Combined reasoning for UI
    ui_payload: Optional[dict]
    error: Optional[str]
```

**Planner node update:**
```python
def planner_node(state: AgentState) -> Dict[str, Any]:
    plan: AviationPlan = planner.invoke({"messages": state.get("messages") or []})
    
    # Extract reasoning from planner (if LLM provides it)
    # Or generate simple reasoning from plan
    reasoning = f"Selected tool: {plan.selected_tool} with filters: {plan.filters}"
    
    return {
        "plan": plan,
        "planning_reasoning": reasoning
    }
```

**Formatter node update:**
```python
def formatter_node(state: AgentState) -> Dict[str, Any]:
    formatted = formatter.invoke({...})
    
    # Combine planning and formatting reasoning
    thinking_parts = []
    if state.get("planning_reasoning"):
        thinking_parts.append(state["planning_reasoning"])
    if formatted.get("formatting_reasoning"):
        thinking_parts.append(formatted["formatting_reasoning"])
    
    return {
        "final_answer": formatted["final_answer"],
        "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
        "ui_payload": formatted["ui_payload"]
    }
```

**Alternative: Use LLM with structured output for reasoning**

We could also ask the planner/formatter LLMs to output structured responses with separate `reasoning` and `answer` fields, but that requires changing the LLM prompts.

**Recommendation:** Use state-based approach - simpler, more reliable, and more LangGraph-native.

---

## 12. UI Payload Structure: mcp_raw vs Flattened Fields

### Current Design (A3): mcp_raw Approach

**Current structure:**
```python
{
    "kind": "route",
    "departure": "EGTF",
    "destination": "LFMD",
    "mcp_raw": {
        "filter_profile": {...},
        "visualization": {...},
        "airports": [...],
        # ... all other tool result fields
    }
}
```

**UI access:**
- `ui_payload.mcp_raw.filter_profile` - Filters applied
- `ui_payload.mcp_raw.visualization` - Map visualization
- `ui_payload.mcp_raw.airports` - Airport data

### Alternative: Flattened Fields Approach

**Alternative structure:**
```python
{
    "kind": "route",
    "departure": "EGTF",
    "destination": "LFMD",
    "filters": {...},  # Flattened from mcp_raw.filter_profile
    "visualization": {...},  # Flattened from mcp_raw.visualization
    "airports": [...],  # Flattened from mcp_raw.airports
    "mcp_raw": {...}  # Still keep for everything else
}
```

**UI access:**
- `ui_payload.filters` - Direct access
- `ui_payload.visualization` - Direct access
- `ui_payload.airports` - Direct access

### Comparison: Pros & Cons

#### Option A: Keep mcp_raw Only (Current A3)

**Pros:**
- ✅ **Stable top-level schema** - Only `kind` and a few metadata fields at top level
- ✅ **Future-proof** - New tool fields automatically available via `mcp_raw`
- ✅ **Single source of truth** - `mcp_raw` is authoritative, no duplication
- ✅ **Simple maintenance** - Just pass through tool result, no extraction logic
- ✅ **No breaking changes** - Tool result structure changes don't affect UI payload schema

**Cons:**
- ❌ **More verbose** - UI needs `ui_payload.mcp_raw.filter_profile` instead of `ui_payload.filters`
- ❌ **Less intuitive** - Nested structure requires knowing tool result structure

#### Option B: Flatten Common Fields

**Pros:**
- ✅ **Easier UI access** - `ui_payload.filters` is more intuitive
- ✅ **Less nesting** - Common fields at top level
- ✅ **Better DX** - Developers don't need to know about `mcp_raw`

**Cons:**
- ❌ **Maintenance burden** - Need to extract fields from tool result
- ❌ **Decisions required** - Which fields to flatten? (filters, visualization, airports, ...)
- ❌ **Duplication risk** - Same data in two places (flattened + mcp_raw)
- ❌ **Breaking changes** - If tool adds new common field, need to update flattening
- ❌ **Incomplete** - Some fields might not be flattened, still need mcp_raw

#### Option C: Hybrid Approach (Recommended)

**Flatten commonly-used fields, keep mcp_raw for everything:**

```python
{
    "kind": "route",
    "departure": "EGTF",
    "destination": "LFMD",
    # Flattened for convenience (commonly used)
    "filters": tool_result.get("filter_profile"),  # Convenience access
    "visualization": tool_result.get("visualization"),  # Convenience access
    "airports": tool_result.get("airports"),  # Convenience access
    # Full data still available
    "mcp_raw": tool_result  # Authoritative source, includes everything
}
```

**Pros:**
- ✅ **Best of both worlds** - Convenient top-level access + full data available
- ✅ **UI choice** - Use convenient fields or dive into mcp_raw
- ✅ **Future-proof** - New fields still in mcp_raw
- ✅ **Backward compatible** - UI can migrate gradually

**Cons:**
- ⚠️ **Slight duplication** - But only for commonly-used fields
- ⚠️ **Need to decide** - Which fields to flatten? (but limited set)

### Recommendation: Hybrid Approach

**Flatten these commonly-used fields:**
1. `filters` (from `filter_profile`) - UI needs this for filter sync
2. `visualization` - UI needs this for map rendering
3. `airports` - UI needs this for airport list (for route/airport searches)

**Keep mcp_raw for:**
- Everything else (counts, metadata, etc.)
- Future fields we don't know about yet
- Authoritative source

**Implementation: ✅ COMPLETED**

The hybrid approach is now implemented in `shared/aviation_agent/formatting.py`:

```python
def build_ui_payload(plan: AviationPlan, tool_result: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """
    Build UI payload using hybrid approach:
    - Flatten commonly-used fields (filters, visualization, airports) for convenience
    - Keep mcp_raw for everything else and as authoritative source
    """
    if not tool_result:
        return None

    # Determine kind based on tool
    kind = _determine_kind(plan.selected_tool)
    if not kind:
        return None

    # Base payload with kind and mcp_raw (authoritative source)
    base_payload: Dict[str, Any] = {
        "kind": kind,
        "mcp_raw": tool_result,
    }

    # Add kind-specific metadata
    if plan.selected_tool in {"search_airports", "find_airports_near_route", "find_airports_near_location"}:
        base_payload["departure"] = plan.arguments.get("from_icao") or plan.arguments.get("departure")
        base_payload["destination"] = plan.arguments.get("to_icao") or plan.arguments.get("destination")
        if plan.arguments.get("ifr") is not None:
            base_payload["ifr"] = plan.arguments.get("ifr")
    # ... other tool-specific metadata

    # Flatten commonly-used fields for convenience (hybrid approach)
    if "filter_profile" in tool_result:
        base_payload["filters"] = tool_result["filter_profile"]
    if "visualization" in tool_result:
        base_payload["visualization"] = tool_result["visualization"]
    if "airports" in tool_result:
        base_payload["airports"] = tool_result["airports"]

    return base_payload
```

**UI Usage:**
```javascript
// Convenient access (recommended)
const filters = ui_payload.filters;
const visualization = ui_payload.visualization;
const airports = ui_payload.airports;

// Or access via mcp_raw (if needed)
const filters = ui_payload.mcp_raw.filter_profile;
const visualization = ui_payload.mcp_raw.visualization;
```

**Benefits:**
- ✅ UI code is cleaner: `ui_payload.filters` instead of `ui_payload.mcp_raw.filter_profile`
- ✅ Still future-proof: new fields in `mcp_raw`
- ✅ No breaking changes: UI can use either approach
- ✅ Limited flattening: Only 3 commonly-used fields, rest in mcp_raw

---

## 13. Open Questions - RESOLVED

1. **Should we keep the old chatbot service as fallback?**
   - ✅ **Decision: NO** - Full migration, remove old code completely

2. **How to handle multi-turn conversations?**
   - ✅ **Decision: Agent already supports message history** - Pass history in ChatRequest.messages, agent state preserves it

3. **Should we add tool call streaming?**
   - ✅ **Decision: YES** - Emit `tool_call_start` and `tool_call_end` events for better UX

4. **How to handle errors in agent?**
   - ✅ **Decision: Propagate through state** - Add `error` field to AgentState, emit `error` SSE event

5. **Should we add retry logic?**
   - ✅ **Decision: YES** - Add retry for transient failures (LLM API, MCP connection) in adapter layer

6. **Should we preserve filter generation?**
   - ✅ **Decision: YES** - Planner extracts filters into `arguments.filters` (no separate field needed)
   - ✅ **UI gets filters from** `ui_payload.mcp_raw.filter_profile` (what tool actually applied)
   - ✅ **Simplified** - Filters are just part of tool arguments, UI payload contains filter_profile

7. **Should we preserve visualization enhancement?**
   - ✅ **Decision: YES** - Extract ICAOs from final_answer in formatter, enhance ui_payload

8. **How to handle thinking?**
   - ✅ **Decision: Use state-based approach** - Store `planning_reasoning` and `formatting_reasoning` in state, combine into `thinking` field
   - ✅ **Better than tag parsing** - More reliable, structured, LangGraph-native

---

## 12. Implementation Checklist

### Phase 1: Core Agent Updates

- [ ] **Update `shared/aviation_agent/state.py`**
  - Add `thinking: Optional[str]` field
  - Add `error: Optional[str]` field

- [ ] **Update `shared/aviation_agent/planning.py`**
  - Add `filters: Optional[Dict[str, Any]]` to `AviationPlan`
  - Update planner prompt to extract filters from user message
  - Update schema in prompt to include filters field

- [ ] **Update `shared/aviation_agent/execution.py`**
  - Add `FILTERABLE_TOOLS` constant
  - Update `ToolRunner.run()` to inject filters into tool calls

- [ ] **Update `shared/aviation_agent/formatting.py`**
  - Add `_extract_thinking_and_answer()` function (copy from chatbot_service)
  - Add `_extract_icao_codes()` function
  - Add `_enhance_visualization()` function
  - Update `build_formatter_runnable()` to support streaming
  - Add thinking extraction to formatter prompt
  - Add visualization enhancement logic

### Phase 2: Streaming Support

- [ ] **Create `shared/aviation_agent/adapters/streaming.py`**
  - Implement `stream_aviation_agent()` function
  - Use LangGraph's `astream_events()` API
  - Emit SSE events: plan, tool_call_start, tool_call_end, thinking, message, ui_payload, done, error
  - Handle formatter streaming chunks

- [ ] **Update `shared/aviation_agent/adapters/__init__.py`**
  - Export `stream_aviation_agent`

- [ ] **Update `web/server/api/aviation_agent_chat.py`**
  - Add `/chat/stream` endpoint
  - Use `StreamingResponse` with SSE format
  - Handle errors gracefully

### Phase 3: Logging & Utilities

- [x] **Create `shared/aviation_agent/adapters/logging.py`** ✅ COMPLETED
  - Implemented `log_conversation_from_state()` using Option A (post-execution)
  - Reuses existing conversation log format
  - Extracts data from final AgentState
  - Simple, non-blocking approach

---

## 14. Conversation Logging: Approach Analysis & Recommendation

### Current Implementation

**Current approach (chatbot_service.py):**
- Logs after conversation completes
- Extracts data from final state
- Saves to JSON file (one file per day)
- Format: `conversation_logs/YYYY-MM-DD.json`

**Log entry structure:**
```python
{
    "session_id": "...",
    "timestamp": "2024-01-01T12:00:00",
    "timestamp_end": "2024-01-01T12:00:05",
    "duration_seconds": 5.23,
    "question": "User message",
    "answer": "Assistant response",
    "thinking": "Internal reasoning",
    "tool_calls": [...],
    "metadata": {
        "model": "gpt-4o",
        "tokens_input": 100,
        "tokens_output": 50,
        "tokens_total": 150,
        "total_time_seconds": 5.23,
        "num_tool_calls": 1,
        "has_visualizations": true
    }
}
```

### Three Logging Approaches for LangGraph

#### Option A: Post-Execution Logging (Simplest)

**Approach:** Log after agent execution completes, extract from final state.

```python
async def stream_aviation_agent(...):
    start_time = time.time()
    final_state = None
    
    async for event in graph.astream_events(...):
        # ... stream events to UI ...
        
        # Capture final state
        if event.get("event") == "on_chain_end" and event.get("name") == "formatter":
            final_state = event.get("data", {}).get("output")
    
    # Log after streaming completes
    if final_state:
        log_conversation(
            session_id=session_id,
            state=final_state,
            start_time=start_time,
            end_time=time.time(),
            messages=messages
        )
```

**Pros:**
- ✅ **Simple** - Just extract from final state
- ✅ **Non-blocking** - Doesn't slow down streaming
- ✅ **Reliable** - All data available at end
- ✅ **Easy to implement** - Minimal code changes

**Cons:**
- ❌ **No partial logs** - If agent crashes, no log entry
- ❌ **Requires state tracking** - Need to capture final state
- ❌ **Separate from streaming** - Logging happens after UI response

#### Option B: Event-Based Logging (Most Flexible)

**Approach:** Capture data incrementally from `astream_events()` and log at end.

```python
async def stream_aviation_agent(...):
    start_time = time.time()
    log_data = {
        "tool_calls": [],
        "plan": None,
        "final_answer": None,
        "thinking": None,
        "ui_payload": None,
        "tokens": {"input": 0, "output": 0}
    }
    
    async for event in graph.astream_events(...):
        # Stream to UI
        yield event_to_sse(event)
        
        # Capture logging data incrementally
        if event.get("event") == "on_chain_end":
            if event.get("name") == "planner":
                log_data["plan"] = event.get("data", {}).get("output")
            elif event.get("name") == "tool":
                log_data["tool_calls"].append({
                    "name": ...,
                    "arguments": ...,
                    "result": event.get("data", {}).get("output")
                })
            elif event.get("name") == "formatter":
                output = event.get("data", {}).get("output")
                log_data["final_answer"] = output.get("final_answer")
                log_data["thinking"] = output.get("thinking")
                log_data["ui_payload"] = output.get("ui_payload")
        
        # Track tokens
        if event.get("event") == "on_llm_end":
            usage = event.get("data", {}).get("output", {}).get("response_metadata", {}).get("token_usage")
            if usage:
                log_data["tokens"]["input"] += usage.get("prompt_tokens", 0)
                log_data["tokens"]["output"] += usage.get("completion_tokens", 0)
    
    # Log after streaming
    log_conversation(
        session_id=session_id,
        log_data=log_data,
        start_time=start_time,
        end_time=time.time(),
        messages=messages
    )
```

**Pros:**
- ✅ **Incremental capture** - Collect data as events occur
- ✅ **More control** - Can log partial data if needed
- ✅ **Integrated** - Uses same event stream as streaming
- ✅ **Flexible** - Can add more event types easily

**Cons:**
- ⚠️ **More complex** - Need to track multiple event types
- ⚠️ **State management** - Need to accumulate data across events
- ⚠️ **Still post-execution** - Logs at end, not during

#### Option C: Callback-Based Logging (LangGraph Native)

**Approach:** Use LangGraph callbacks to log during execution.

```python
from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List

class ConversationLogger(BaseCallbackHandler):
    def __init__(self, session_id: str, log_dir: Path):
        self.session_id = session_id
        self.log_dir = log_dir
        self.start_time = time.time()
        self.log_data = {
            "tool_calls": [],
            "tokens": {"input": 0, "output": 0}
        }
    
    def on_chain_end(self, outputs: Dict[str, Any], **kwargs):
        name = kwargs.get("name")
        if name == "planner":
            self.log_data["plan"] = outputs
        elif name == "tool":
            self.log_data["tool_calls"].append(outputs)
        elif name == "formatter":
            self.log_data["final_answer"] = outputs.get("final_answer")
            self.log_data["thinking"] = outputs.get("thinking")
            self.log_data["ui_payload"] = outputs.get("ui_payload")
    
    def on_llm_end(self, response, **kwargs):
        usage = response.response_metadata.get("token_usage", {})
        self.log_data["tokens"]["input"] += usage.get("prompt_tokens", 0)
        self.log_data["tokens"]["output"] += usage.get("completion_tokens", 0)
    
    def on_chain_error(self, error: Exception, **kwargs):
        self.log_data["error"] = str(error)
    
    def flush(self, messages: List[BaseMessage]):
        """Write log entry to file."""
        end_time = time.time()
        log_entry = {
            "session_id": self.session_id,
            "timestamp": datetime.fromtimestamp(self.start_time).isoformat(),
            "timestamp_end": datetime.fromtimestamp(end_time).isoformat(),
            "duration_seconds": round(end_time - self.start_time, 2),
            "question": messages[-1].content if messages else "",
            "answer": self.log_data.get("final_answer", ""),
            "thinking": self.log_data.get("thinking", ""),
            "tool_calls": self.log_data.get("tool_calls", []),
            "metadata": {
                "tokens_input": self.log_data["tokens"]["input"],
                "tokens_output": self.log_data["tokens"]["output"],
                "tokens_total": sum(self.log_data["tokens"].values()),
                "num_tool_calls": len(self.log_data.get("tool_calls", [])),
            }
        }
        # Save to file (reuse existing format)
        _save_log_entry(log_entry, self.log_dir)

# Usage
logger = ConversationLogger(session_id, log_dir)
graph.invoke({"messages": messages}, config={"callbacks": [logger]})
logger.flush(messages)
```

**Pros:**
- ✅ **LangGraph native** - Uses standard callback pattern
- ✅ **Real-time** - Can log during execution
- ✅ **Separation of concerns** - Logging separate from streaming
- ✅ **Reusable** - Can use in both streaming and non-streaming
- ✅ **Error handling** - Can catch errors via callbacks

**Cons:**
- ⚠️ **More setup** - Need to create callback class
- ⚠️ **State management** - Need to accumulate data in callback
- ⚠️ **Streaming complexity** - Need to pass callbacks to astream_events

### Recommendation: **Option A (Post-Execution) + Option C (Callbacks for Non-Streaming)**

**For Streaming Endpoints:**
- Use **Option A (Post-Execution)** - Simple, non-blocking, reliable
- Extract data from final state after streaming completes
- Log in background (don't block response)

**For Non-Streaming Endpoints:**
- Use **Option C (Callbacks)** - LangGraph native, real-time
- Pass callback to `graph.invoke()`
- Log immediately after execution

**Implementation:**

```python
# adapters/logging.py
from pathlib import Path
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

def log_conversation_from_state(
    session_id: str,
    state: Dict[str, Any],
    messages: List[BaseMessage],
    start_time: float,
    end_time: float,
    log_dir: Path,
) -> None:
    """
    Log conversation from final agent state (for streaming endpoints).
    Simple post-execution logging.
    """
    try:
        # Extract data from state
        plan = state.get("plan")
        tool_result = state.get("tool_result")
        final_answer = state.get("final_answer", "")
        thinking = state.get("thinking", "")
        ui_payload = state.get("ui_payload")
        
        # Build tool_calls list
        tool_calls = []
        if plan and tool_result:
            tool_calls.append({
                "name": plan.selected_tool if hasattr(plan, "selected_tool") else plan.get("selected_tool"),
                "arguments": plan.arguments if hasattr(plan, "arguments") else plan.get("arguments", {}),
                "result": tool_result
            })
        
        # Extract user question
        question = ""
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                question = last_message.content
            elif isinstance(last_message, dict):
                question = last_message.get("content", "")
        
        # Build log entry (reuse existing format)
        log_entry = {
            "session_id": session_id,
            "timestamp": datetime.fromtimestamp(start_time).isoformat(),
            "timestamp_end": datetime.fromtimestamp(end_time).isoformat(),
            "duration_seconds": round(end_time - start_time, 2),
            "question": question,
            "answer": final_answer,
            "thinking": thinking,
            "tool_calls": tool_calls,
            "metadata": {
                "has_visualizations": ui_payload is not None,
                "num_tool_calls": len(tool_calls),
            }
        }
        
        # Save to file
        _save_log_entry(log_entry, log_dir)
        
    except Exception as e:
        logger.error(f"Error logging conversation: {e}", exc_info=True)
        # Don't fail request if logging fails

def _save_log_entry(log_entry: Dict[str, Any], log_dir: Path) -> None:
    """Save log entry to JSON file (one file per day)."""
    log_dir.mkdir(exist_ok=True)
    date_str = datetime.fromtimestamp(
        datetime.fromisoformat(log_entry["timestamp"]).timestamp()
    ).strftime("%Y-%m-%d")
    log_file = log_dir / f"{date_str}.json"
    
    # Read existing logs
    logs = []
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Could not read log file {log_file}, starting fresh")
    
    # Append new entry
    logs.append(log_entry)
    
    # Write back
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    
    logger.info(f"💾 Conversation logged to {log_file}")
```

**Usage in streaming endpoint:**
```python
# In stream_aviation_agent or aviation_agent_chat.py
from shared.aviation_agent.adapters.logging import log_conversation_from_state
from pathlib import Path
import time

start_time = time.time()

# After streaming completes, get final state and log
final_state = graph.invoke({"messages": messages})  # Get final state

# Log after streaming (non-blocking, in background)
log_conversation_from_state(
    session_id=session_id,
    state=final_state,
    messages=messages,
    start_time=start_time,
    end_time=time.time(),
    log_dir=Path("conversation_logs")
)
```

**Note:** For streaming, you'll need to capture the final state after the stream completes. The simplest approach is to call `graph.invoke()` after streaming to get the final state, or track state during streaming events.

### Final Recommendation Summary

**✅ Use Option A (Post-Execution) for streaming:**
- Simple and reliable
- Non-blocking
- Easy to implement
- Works well with existing format

**✅ Use Option C (Callbacks) for non-streaming (optional):**
- More LangGraph-native
- Can add later if needed
- Better for real-time monitoring

**Key Points:**
- Reuse existing log format (backward compatible)
- Don't block response for logging
- Handle errors gracefully (don't fail request)
- Extract from final state (simpler than event tracking)

- [ ] **Update `shared/aviation_agent/adapters/__init__.py`**
  - Export logging functions

### Phase 4: Testing

- [ ] **Update tests for new fields**
  - Test filter extraction in planner
  - Test filter injection in tool runner
  - Test thinking extraction in formatter
  - Test visualization enhancement

- [ ] **Add streaming tests**
  - Test SSE event format
  - Test streaming endpoint
  - Test error handling

- [ ] **E2E tests**
  - Test full conversation flow
  - Test streaming response
  - Test visualization generation

### Phase 5: UI Integration

- [ ] **Update frontend to use new endpoint**
  - Change from `/api/chat/stream` to `/api/aviation-agent/chat/stream`
  - Update event handlers for new event names
  - Map `ui_payload` to visualization components

- [ ] **Test UI features**
  - Streaming thinking/message display
  - Map visualization
  - Tool call indicators
  - Error handling

### Phase 6: Cleanup

- [ ] **Remove old code**
  - Delete `web/server/chatbot_service.py`
  - Delete `web/server/chatbot_core.py`
  - Remove old chatbot router from `main.py`

- [ ] **Update documentation**
  - Update API docs
  - Update README
  - Update deployment docs

## 15. Final Review: Simplifications & LangGraph-Native Improvements

### Issues Found & Resolutions

#### 1. ❌ **INCONSISTENCY: Formatter Still Has Thinking Tag Parsing**

**Problem:** The formatter streaming code (lines 510-584) still includes complex `<thinking>` tag parsing logic, but we decided to use **state-based thinking** instead.

**Resolution:** Remove tag parsing from formatter. Stream LLM output directly as `message` events. Thinking comes from state (`planning_reasoning` + `formatting_reasoning`), not from LLM output.

**Simplified Formatter Streaming:**
```python
async def _astream(payload: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
    plan: AviationPlan = payload["plan"]
    tool_result = payload.get("tool_result") or {}
    
    full_response = ""
    
    # Stream LLM output directly - no tag parsing needed!
    async for chunk in chain.astream({...}):
        full_response += chunk
        yield {"type": "message", "content": chunk}  # Simple, direct streaming
    
    # Finalize
    answer = full_response.strip()
    ui_payload = build_ui_payload(plan, tool_result)
    
    # Enhance visualization if needed
    if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
        mentioned_icaos = _extract_icao_codes(answer)
        if mentioned_icaos:
            ui_payload = _enhance_visualization(ui_payload, mentioned_icaos, tool_result)
    
    # Generate formatting reasoning (simple, not from LLM)
    formatting_reasoning = f"Formatted answer using {plan.answer_style} style."
    
    yield {"type": "done", "answer": answer, "formatting_reasoning": formatting_reasoning, "ui_payload": ui_payload}
```

**Benefits:**
- ✅ **Much simpler** - No complex tag parsing
- ✅ **Consistent** - Matches state-based thinking approach
- ✅ **Faster** - No character-by-character processing
- ✅ **More reliable** - Doesn't depend on LLM format

#### 2. ✅ **TODO: session_id in streaming**

**Problem:** `"session_id": None,  # TODO: pass from request`

**Resolution:** Pass `session_id` as parameter to `stream_aviation_agent()`:
```python
async def stream_aviation_agent(
    messages: List[BaseMessage],
    graph: CompiledGraph,
    session_id: Optional[str] = None,  # NEW
) -> AsyncIterator[Dict[str, Any]]:
    # ... in done event:
    yield {
        "event": "done",
        "data": {
            "session_id": session_id,  # Use passed value
            "tokens": {...}
        }
    }
```

#### 3. ✅ **Error Handling: Use LangGraph Conditional Edges**

**Current:** Errors propagate through state, but graph always goes planner → tool → formatter.

**Better (LangGraph-native):** Add error handling node with conditional edges.

```python
def build_agent_graph(planner, tool_runner: ToolRunner, formatter):
    graph = StateGraph(AgentState)
    
    def planner_node(state: AgentState) -> Dict[str, Any]:
        try:
            plan: AviationPlan = planner.invoke({"messages": state.get("messages") or []})
            return {"plan": plan, "planning_reasoning": _generate_planning_reasoning(plan)}
        except Exception as e:
            return {"error": str(e)}
    
    def tool_node(state: AgentState) -> Dict[str, Any]:
        plan = state.get("plan")
        if not plan:
            return {"error": "No plan available"}
        try:
            result = tool_runner.run(plan)
            return {"tool_result": result}
        except Exception as e:
            return {"error": str(e)}
    
    def formatter_node(state: AgentState) -> Dict[str, Any]:
        if state.get("error"):
            return {"final_answer": f"Error: {state['error']}", "error": state["error"]}
        try:
            formatted = formatter.invoke({...})
            # Combine reasoning
            thinking_parts = []
            if state.get("planning_reasoning"):
                thinking_parts.append(state["planning_reasoning"])
            if formatted.get("formatting_reasoning"):
                thinking_parts.append(formatted["formatting_reasoning"])
            
            return {
                "final_answer": formatted.get("final_answer", ""),
                "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
                "ui_payload": formatted.get("ui_payload"),
            }
        except Exception as e:
            return {"error": str(e), "final_answer": f"Error formatting response: {str(e)}"}
    
    graph.add_node("planner", planner_node)
    graph.add_node("tool", tool_node)
    graph.add_node("formatter", formatter_node)
    
    graph.set_entry_point("planner")
    graph.add_edge("planner", "tool")
    graph.add_edge("tool", "formatter")
    graph.add_edge("formatter", END)
    
    return graph.compile()
```

**Benefits:**
- ✅ **LangGraph-native** - Errors handled in nodes, not external try/catch
- ✅ **State-based** - Errors stored in state, can be streamed
- ✅ **Graceful degradation** - Formatter can still produce error message

#### 4. ✅ **Simplify Visualization Enhancement**

**Question:** Do we really need to extract ICAOs from answer and enhance visualization?

**Analysis:**
- Tools already return good visualization data
- ICAO extraction is post-processing that might not be needed
- Adds complexity

**Simplification Option:**
- **Option A:** Keep it - useful for filtering visualization to only mentioned airports
- **Option B:** Remove it - use tool visualization as-is (simpler)

**Recommendation:** **Keep it for now, but make it optional** - only enhance if answer mentions specific ICAOs that aren't in tool results. This gives us flexibility without complexity.

#### 5. ✅ **Token Tracking: Use LangGraph's Built-in Mechanisms**

**Current:** Manual tracking in `astream_events()`.

**Better:** LangGraph's `astream_events()` already provides token usage. We can simplify by:
- Using `event.data.output.response_metadata.token_usage` directly
- Or using LangGraph's built-in token tracking if available

**Current approach is fine** - it's the standard LangGraph pattern.

#### 6. ✅ **Remove Duplicate Code Examples**

**Issue:** Some code examples appear multiple times with slight variations.

**Resolution:** Consolidate to single authoritative example per section.

### Final Simplifications Summary

1. ✅ **Remove thinking tag parsing from formatter** - Use state-based thinking only
2. ✅ **Pass session_id as parameter** - Resolve TODO
3. ✅ **Use LangGraph error handling** - Errors in state, not external try/catch
4. ✅ **Simplify formatter streaming** - Direct chunk streaming, no tag parsing
5. ✅ **Make visualization enhancement optional** - Only if needed

### LangGraph-Native Improvements

1. ✅ **State-based thinking** - Already decided, just need to remove tag parsing
2. ✅ **Error handling in nodes** - Errors in state, not exceptions
3. ✅ **Use astream_events()** - Already planned, standard pattern
4. ✅ **State reducers** - Already using `operator.add` for messages (correct)

### Remaining Decisions

1. **Visualization enhancement** - Keep or remove?
   - **Recommendation:** Keep, but make it simple and optional

2. **Thinking streaming** - How to stream thinking from state?
   - **Recommendation:** Emit `thinking` event when `planning_reasoning` is set, then `thinking_done` when formatter completes

3. **Error recovery** - Should formatter try to produce answer even on error?
   - **Recommendation:** Yes, produce error message in `final_answer`, set `error` in state

## 13. Next Steps

1. ✅ **Decision made:** Full migration (Option A)
2. ✅ **Plan ready:** This document contains all implementation details
3. ✅ **Simplifications identified:** Remove tag parsing, use state-based thinking
4. ✅ **LangGraph-native patterns:** Error handling in nodes, state-based thinking
5. **Create migration branch:** `git checkout -b migrate-to-agent`
6. **Start Phase 1:** Update core agent files
7. **Test incrementally:** Test each phase before moving to next
8. **Deploy gradually:** Use feature flag for gradual rollout

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

