# Aviation Agent Streaming

> SSE streaming, FastAPI integration, and token tracking.

## Quick Reference

| File | Purpose |
|------|---------|
| `web/server/api/aviation_agent_chat.py` | FastAPI SSE endpoint |
| `shared/aviation_agent/adapters/streaming.py` | SSE streaming adapter |
| `shared/aviation_agent/adapters/langgraph_runner.py` | Graph orchestration |

**Key Exports:**
- `aviation_agent_chat_stream()` - SSE endpoint
- `stream_agent_response()` - Streaming adapter

**Prerequisites:** Read `AGENT_ARCHITECTURE.md` first.

---

## SSE Event Types

| Event | Data | When Sent |
|-------|------|-----------|
| `plan` | Planner output (tool, arguments) | After planner node |
| `thinking` | Planning reasoning | After planner node |
| `tool_call_start` | Tool name | Before tool execution |
| `tool_call_end` | Execution time | After tool execution |
| `message` | Answer chunk (character) | During formatter streaming |
| `ui_payload` | Visualization data | After formatter |
| `done` | Session ID, token counts | End of request |
| `error` | Error message | On failure |

### Event Order

```
1. plan           → Selected tool and arguments
2. thinking       → Why this tool was selected
3. tool_call_start → Tool execution beginning
4. tool_call_end   → Tool execution complete
5. message (×N)   → Answer streamed character-by-character
6. ui_payload     → Visualization data
7. done           → Final metadata
```

---

## SSE Event Format

Standard SSE format with `event` and `data` fields:

```
event: plan
data: {"tool": "find_airports_near_route", "arguments": {...}}

event: thinking
data: {"content": "User wants airports along route..."}

event: tool_call_start
data: {"tool": "find_airports_near_route"}

event: tool_call_end
data: {"tool": "find_airports_near_route", "duration_ms": 150}

event: message
data: {"content": "H"}

event: message
data: {"content": "e"}

event: message
data: {"content": "r"}

...

event: ui_payload
data: {"kind": "route", "tool": "find_airports_near_route", ...}

event: done
data: {"session_id": "abc123", "tokens": {"input": 1500, "output": 300}}
```

---

## FastAPI Endpoint

### Streaming Endpoint

```python
@router.post("/chat/stream")
async def aviation_agent_chat_stream(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
    session_id: Optional[str] = None,
) -> StreamingResponse:
    """SSE streaming endpoint."""

    async def generate():
        agent = build_agent()

        async for event in stream_agent_response(agent, request.messages, session_id):
            yield f"event: {event['event']}\n"
            yield f"data: {json.dumps(event['data'])}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

### Non-Streaming Endpoint

```python
@router.post("/chat")
async def aviation_agent_chat(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
) -> ChatResponse:
    """Non-streaming endpoint for simple requests."""

    agent = build_agent()
    result = await agent.ainvoke({
        "messages": [HumanMessage(content=m) for m in request.messages]
    })

    return ChatResponse(
        answer=result["final_answer"],
        ui_payload=result["ui_payload"],
        session_id=result.get("session_id"),
    )
```

---

## LangGraph Streaming

### Using astream_events

```python
async def stream_agent_response(
    agent: CompiledGraph,
    messages: List[str],
    session_id: Optional[str] = None
) -> AsyncGenerator[dict, None]:
    """Stream events from agent execution."""

    initial_state = {
        "messages": [HumanMessage(content=m) for m in messages]
    }

    total_input_tokens = 0
    total_output_tokens = 0

    async for event in agent.astream_events(initial_state, version="v2"):
        kind = event.get("event")

        # Stream LLM tokens
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                yield {
                    "event": "message",
                    "data": {"content": chunk.content}
                }

        # Track token usage
        elif kind == "on_llm_end":
            output = event.get("data", {}).get("output")
            if output:
                usage = output.response_metadata.get("token_usage", {})
                total_input_tokens += usage.get("prompt_tokens", 0)
                total_output_tokens += usage.get("completion_tokens", 0)

        # Plan output
        elif kind == "on_chain_end":
            name = event.get("name", "")
            if name == "planner":
                output = event.get("data", {}).get("output", {})
                yield {
                    "event": "plan",
                    "data": output.get("plan", {})
                }

    # Final event
    yield {
        "event": "done",
        "data": {
            "session_id": session_id or str(uuid.uuid4()),
            "tokens": {
                "input": total_input_tokens,
                "output": total_output_tokens
            }
        }
    }
```

---

## Token Tracking

Token usage aggregated across all LLM calls:

```python
# Tracked LLM calls
- Planner (tool selection)
- Formatter (answer synthesis)
- Router (query classification) - if enabled
- Rules Agent (rules synthesis) - if rules path
```

### Non-Streaming Token Extraction

Two extraction paths to support all providers:

```python
# Path 1: OpenAI - uses response_metadata.token_usage
if kind == "on_llm_end":
    usage = output.response_metadata.get("token_usage", {})
    total_input_tokens += usage.get("prompt_tokens", 0)
    total_output_tokens += usage.get("completion_tokens", 0)

# Path 2: Anthropic/Google fallback - uses usage_metadata
if not usage and hasattr(output, "usage_metadata"):
    um = output.usage_metadata
    total_input_tokens += um.get("input_tokens", 0)
    total_output_tokens += um.get("output_tokens", 0)
```

| Provider | Non-Streaming Path | Key Names |
|----------|-------------------|-----------|
| OpenAI | `response_metadata.token_usage` | `prompt_tokens`, `completion_tokens` |
| Anthropic | `usage_metadata` | `input_tokens`, `output_tokens` |
| Google | `usage_metadata` | `input_tokens`, `output_tokens` |

### Streaming Token Extraction

Streaming uses `usage_metadata` on the final chunk — this is standardized across all providers, no special handling needed.

### Token Usage in done Event

```json
{
  "event": "done",
  "data": {
    "session_id": "abc123",
    "tokens": {
      "input": 1500,
      "output": 300,
      "total": 1800
    }
  }
}
```

---

## Session Management

### Thread ID / Session ID

- Generated per conversation
- Used for checkpointer (conversation memory)
- Returned in `done` event

```python
# Session ID flow
1. Client sends request (optionally with session_id)
2. Agent uses session_id for checkpointer lookup
3. Response includes session_id in done event
4. Client uses same session_id for follow-ups
```

### Checkpointer Integration

```python
# In config.py
CHECKPOINTER_PROVIDER = os.getenv("CHECKPOINTER_PROVIDER", "memory")

# Options:
# - "memory": In-memory (lost on restart)
# - "sqlite": Persistent SQLite
# - "none": No conversation memory

def get_checkpointer():
    if CHECKPOINTER_PROVIDER == "sqlite":
        return SqliteSaver(CHECKPOINTER_SQLITE_PATH)
    elif CHECKPOINTER_PROVIDER == "memory":
        return MemorySaver()
    return None
```

---

## Error Handling

### Error Events

```python
try:
    async for event in agent.astream_events(...):
        yield transform_event(event)
except Exception as e:
    yield {
        "event": "error",
        "data": {"message": str(e)}
    }
```

### Error Format

```json
{
  "event": "error",
  "data": {
    "message": "Tool execution failed: ...",
    "code": "TOOL_ERROR"
  }
}
```

---

## Frontend Integration

### EventSource API

```typescript
const eventSource = new EventSource('/api/aviation-agent/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ messages: ['Find airports near Paris'] })
});

eventSource.addEventListener('message', (e) => {
  const data = JSON.parse(e.data);
  appendToAnswer(data.content);
});

eventSource.addEventListener('ui_payload', (e) => {
  const payload = JSON.parse(e.data);
  updateVisualization(payload);
});

eventSource.addEventListener('done', (e) => {
  const data = JSON.parse(e.data);
  setSessionId(data.session_id);
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  showError(e.data);
  eventSource.close();
});
```

### ChatbotManager Integration

See `WEB_APP_CHAT.md` for frontend ChatbotManager implementation.

---

## Server Integration

### Router Mount

```python
# web/server/main.py
from web.server.api import aviation_agent_chat

if aviation_agent_chat.feature_enabled():
    app.include_router(
        aviation_agent_chat.router,
        prefix="/api/aviation-agent",
        tags=["aviation-agent"],
    )
```

### Feature Flag

```python
# aviation_agent_chat.py
def feature_enabled() -> bool:
    return os.getenv("AVIATION_AGENT_ENABLED", "").lower() == "true"
```

---

## Testing

```python
# test_streaming.py
@pytest.mark.asyncio
async def test_sse_event_order():
    """Events arrive in expected order."""
    events = []
    async for event in stream_agent_response(agent, ["test query"]):
        events.append(event["event"])

    assert events[0] == "plan"
    assert "message" in events
    assert events[-2] == "ui_payload"
    assert events[-1] == "done"


@pytest.mark.asyncio
async def test_token_tracking():
    """Token usage is aggregated."""
    done_event = None
    async for event in stream_agent_response(agent, ["test query"]):
        if event["event"] == "done":
            done_event = event

    assert done_event["data"]["tokens"]["input"] > 0
    assert done_event["data"]["tokens"]["output"] > 0


# test_integration.py
def test_streaming_endpoint(client):
    """FastAPI endpoint returns SSE."""
    response = client.post(
        "/api/aviation-agent/chat/stream",
        json={"messages": ["Find airports near Paris"]},
        headers={"Accept": "text/event-stream"}
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
```

---

## Debugging

```bash
# Test endpoint with curl
curl -N -X POST http://localhost:8000/api/aviation-agent/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages": ["Find airports near Paris"]}'

# Output:
# event: plan
# data: {"tool": "find_airports_near_location", ...}
#
# event: thinking
# data: {"content": "User wants airports near..."}
#
# event: message
# data: {"content": "H"}
# ...
```

```python
# Test streaming in Python
import asyncio
from shared.aviation_agent.adapters.streaming import stream_agent_response
from shared.aviation_agent.graph import build_agent

async def test():
    agent = build_agent()
    async for event in stream_agent_response(agent, ["Find airports near Paris"]):
        print(f"{event['event']}: {event['data']}")

asyncio.run(test())
```
