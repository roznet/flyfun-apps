# Aviation Agent – Design & Implementation Guide (A3 UI Payload Version)

This document describes the full architecture, components, testing strategy, and UI-integration
design for an aviation-focused LangChain/LangGraph agent that uses your custom **aviation MCP database**
(routes, airports, rules) and exposes **structured outputs** suitable for a modern chat UI
(including side panels such as maps, airport cards, or rules checklists).

This version implements **UI payload Plan A3**:

- The UI receives a **stable, curated JSON payload (`ui_payload`)**
- It contains:
  - `kind`: `"route"`, `"airport"`, or `"rules"`
  - A small set of stable **top-level fields** (e.g. `departure`, `icao`, `region`)
  - A **full MCP tool output** stored under the key:  
    ```
    "mcp_raw": { ... }
    ```

- Internally, the agent’s planner (`AviationPlan`) is **decoupled** from the UI.
- Only the `_build_ui_payload(plan, tool_result)` function must be updated if planner output evolves.

This design strongly isolates UI from internal LLM schema changes while still enabling rich UI behavior.

---

## 1. High-Level Architecture

### Core design:

The agent operates in **three steps via LangGraph**:

1. **Planner Node**
   - LLM with structured output (`AviationPlan`).
   - Selects one aviation tool.
   - Extracts the best possible arguments.
   - Specifies answer style.

2. **Tool Runner Node**
   - Executes the chosen MCP-backed LangChain tool.
   - Returns raw JSON (`tool_result`).

3. **Formatter Node**
   - Produces:
     - The final answer text.
     - A **UI payload** (`ui_payload`) matching A3:
       ```
       {
         "kind": "...",
         ... stable high-level fields ...,
         "mcp_raw": { ... full MCP response ... }
       }
       ```

### Agent state flow

```
┌────────┐     ┌─────────────┐     ┌───────────────┐
│ User   │ --> │ Planner Node │ --> │ Tool Runner   │ --> Formatter Node --> UI
└────────┘     └─────────────┘     └───────────────┘
```

The UI receives:

- `answer` (markdown)
- `ui_payload` (stable JSON)
- `planner_meta` (full plan for debugging)
- `tool_result` is not needed but can also be exposed.

---

## 2. Repository Integration Plan

FlyFun already separates shared Python libraries (`shared/`), FastAPI server code (`web/server/`),
and pytest suites (`tests/`). The LangChain/LangGraph agent should follow that pattern so the same
package can be imported by the web server, CLI tools, or future jobs without duplication.

```
shared/aviation_agent/
  __init__.py
  config.py
  state.py
  mcp_client.py
  tools.py
  planning.py
  execution.py
  formatting.py
  graph.py
  adapters/
    __init__.py
    langgraph_runner.py      # orchestration helpers (e.g., run_aviation_agent)
    fastapi_io.py            # translate HTTP payloads ↔ agent inputs
```

```
web/server/api/
  aviation_agent_chat.py     # FastAPI router that imports shared.aviation_agent adapters
  ...
```

```
tests/aviation_agent/
  __init__.py
  conftest.py                # shared fixtures + MCP doubles
  fixtures.py
  test_planner.py
  test_execution.py
  test_formatter.py
  test_graph_e2e.py
```

### Placement notes

- `shared/aviation_agent/` keeps the LangGraph stack versioned once and importable from both
  `web/server/chatbot_service.py` and any offline scripts.
- The new FastAPI router in `web/server/api/aviation_agent_chat.py` can be mounted by
  `web/server/main.py` (or `chatbot_service.py`) alongside existing routes, so deployment and env
  configuration stay in one place.
- Tests live under `tests/aviation_agent/` so they follow the repo’s pytest discovery pattern and can
  re-use existing `tests/tools` helpers.

---

## 3. Web/API Wiring Inside `web/server`

1. **Router** – create `web/server/api/aviation_agent_chat.py` with a `router = APIRouter()` that:
   - Validates chat requests (messages, MCP auth, feature flags).
   - Instantiates the shared `McpClient` (or re-uses `web/server/mcp_client.py` helpers).
   - Calls `shared.aviation_agent.adapters.langgraph_runner.run_aviation_agent(...)`.
   - Returns the `ChatResponse` schema (see §9) so UI consumers only read `answer`, `planner_meta`,
     and `ui_payload`.
2. **Server entry point** – import the router in `web/server/chatbot_service.py` or `web/server/main.py`
   and include it: `app.include_router(aviation_agent_chat.router, prefix="/aviation-agent")`.
3. **Logging & metrics** – leverage existing `conversation_logs/` pipeline by emitting structured
   events before/after agent calls (shared adapter emits instrumentation hooks so the API layer can
   attach request IDs).
4. **Configuration & flagging** – `shared/aviation_agent/config.py` reads environment variables supplied
   by `web/server/dev.env` / `prod.env`, including an `AVIATION_AGENT_ENABLED` feature flag. The server
   should only `include_router(...)` when this flag is true so rollouts can be staged safely.

---

## 4. Tests & Fixtures Under `tests/aviation_agent`

- Mirror the directories enumerated above so every LangGraph component has a direct pytest file.
- Re-use or extend `tests/tools` fixtures for MCP responses; the existing repo already keeps recorded
  payloads under `tests/chatbot/fixtures`, so the new `fixtures.py` can point to that data to avoid
  duplication.
- Integration tests (`test_graph_e2e.py`) import the FastAPI router via `TestClient`, proving that the
  wiring inside `web/server/api/aviation_agent_chat.py` marshals request/response data exactly as the
  UI expects.
- Add contract tests that assert the `ui_payload` schema whenever new planner/tool combinations are
  added; this guards the A3 payload stability requirement.

---

## 5. Planner Schema & Tool Naming

- `AviationPlan.selected_tool` uses the literal MCP tool names defined in
  `shared/airport_tools.get_shared_tool_specs()` (e.g., `search_airports`,
  `find_airports_near_route`, `get_airport_details`, `list_rules_for_country`, …).
- Add a validation helper inside `shared/aviation_agent/planning.py` that raises if a plan references
  a tool that does not exist in the manifest; this keeps planner schema and MCP registration aligned.
- `_build_ui_payload()` maps these literal tool names to the three UI `kind` buckets. Whenever the
  MCP manifest grows, update only the mapping table (not the schema) to reflect the new tool’s kind.

---

## 6. `state.py` — Agent State With A3 UI Payload

```python
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    plan: Optional[AviationPlan]
    tool_result: Optional[Any]
    final_answer: Optional[str]

    # A3: stable UI payload
    ui_payload: Optional[dict]
```

---

## 7. `_build_ui_payload()` — The A3 Specification

A3’s rule:

> **Stable top-level keys** + **raw MCP result under `mcp_raw`**  
> UI must not depend on full planner or full tool_result.

```python
def _build_ui_payload(plan: AviationPlan, tool_result: dict | None) -> dict | None:
    if tool_result is None:
        return None

    if plan.selected_tool in {"search_airports", "find_airports_near_route", "find_airports_near_location"}:
        return {
            "kind": "route",
            "departure": plan.arguments.get("departure"),
            "destination": plan.arguments.get("destination"),
            "ifr": plan.arguments.get("ifr"),
            "mcp_raw": tool_result,    # the authoritative data
        }

    if plan.selected_tool in {
        "get_airport_details",
        "get_border_crossing_airports",
        "get_airport_statistics",
        "get_airport_pricing",
        "get_pilot_reviews",
        "get_fuel_prices",
    }:
        return {
            "kind": "airport",
            "icao": plan.arguments.get("icao"),
            "mcp_raw": tool_result,
        }

    if plan.selected_tool in {
        "list_rules_for_country",
        "compare_rules_between_countries",
        "get_answers_for_questions",
        "list_rule_categories_and_tags",
        "list_rule_countries",
    }:
        return {
            "kind": "rules",
            "region": plan.arguments.get("region"),
            "topic": plan.arguments.get("topic"),
            "mcp_raw": tool_result,
        }

    return None
```

### Why this design?

- **Highly stable**: UI structure rarely changes.
- **Fully future-proof**: Planner can evolve without breaking UI.
- **Powerful**: UI still gets everything via `mcp_raw`.

---

## 8. Formatter Node — Now Returns `final_answer` + `ui_payload`

Final code:

```python
resp = formatter_llm.invoke(llm_input)
ui_payload = _build_ui_payload(plan, tool_result)

return {
    "final_answer": resp.content,
    "ui_payload": ui_payload,
}
```

---

## 9. FastAPI Endpoint — Clean Stable Output

```python
class ChatResponse(BaseModel):
    answer: str
    planner_meta: dict | None = None
    ui_payload: dict | None = None

@app.post("/chat")
def chat(request: ChatRequest):
    ...
    state = run_aviation_agent(messages, mcp_client)
    plan_dict = state["plan"].model_dump() if state["plan"] else None

    return ChatResponse(
        answer=state["final_answer"],
        planner_meta=plan_dict,
        ui_payload=state.get("ui_payload"),
    )
```

### UI only needs `ui_payload`:

- `"kind": "route"` → show a route map  
- `"kind": "airport"` → show airport info card  
- `"kind": "rules"` → show rules panel  
- `"mcp_raw"` provides all underlying details for drawing polylines, etc.

---

## 10. Tests Updated for A3 Payload

Example:

```python
def test_end_to_end_route_query_builds_route_ui_payload():
    state = run_aviation_agent([HumanMessage(content="IFR EGTF to LSGS")], mcp)

    ui = state["ui_payload"]
    assert ui["kind"] == "route"
    assert ui["departure"] == "EGTF"
    assert "mcp_raw" in ui
    assert "suggested_route" in ui["mcp_raw"]
```

---

## 11. MCP Tool & Payload Catalog

The shared code already centralizes every MCP tool signature in `shared/airport_tools.py`; the agent
should treat that file as the single source of truth and let `get_shared_tool_specs()` drive planner
validation. For documentation, keep a concise catalog (below) that mirrors the manifest, so LangGraph
developers, FastAPI engineers, and UI implementers can all read the same contract.

### How to read this table

- **Shared fn**: callable exported from `shared/airport_tools`.
- **MCP name**: identifier registered in `mcp_server/main.py` (always matches the shared fn).
- **Required / optional args**: only list the surface needed by the planner; deeper parameter rules
  still live in the code docstrings.
- **Default `ui_payload.kind`**: what `_build_ui_payload()` should emit for the associated planner
  tool. When multiple tools map to the same kind (e.g., several airport-search tools → `route`), we
  note it explicitly.
- **Notable `mcp_raw` keys**: fields the UI cares about. Everything else is still available through
  `mcp_raw` but does not need bespoke documentation.

| Tool | Shared fn | Required args | Optional args | Default `ui_payload.kind` | Notable `mcp_raw` keys |
| --- | --- | --- | --- | --- | --- |
| `search_airports` | `search_airports` | `query` | `max_results`, `filters`, `priority_strategy` | `route` | `airports`, `filter_profile`, `visualization.type='markers'` |
| `find_airports_near_location` | `find_airports_near_location` | `location_query` | `max_distance_nm`, `filters`, `priority_strategy` | `route` | `center`, `airports`, `filter_profile`, `visualization.type='point_with_markers'` |
| `find_airports_near_route` | `find_airports_near_route` | `from_icao`, `to_icao` | `max_distance_nm`, `filters`, `priority_strategy` | `route` | `airports`, `filter_profile`, `visualization.type='route_with_markers'` |
| `get_airport_details` | `get_airport_details` | `icao_code` | – | `airport` | `airport`, `runways`, `visualization.type='marker_with_details'` |
| `get_border_crossing_airports` | `get_border_crossing_airports` | – | `country` | `airport` | `airports`, `by_country`, `filter_profile`, `visualization.style='customs'` |
| `get_airport_statistics` | `get_airport_statistics` | – | `country` | `airport` | `stats` |
| `get_airport_pricing` | `get_airport_pricing` | `icao_code` | – | `airport` | `pricing`, `pretty` |
| `get_pilot_reviews` | `get_pilot_reviews` | `icao_code` | `limit` | `airport` | `reviews`, `average_rating` |
| `get_fuel_prices` | `get_fuel_prices` | `icao_code` | – | `airport` | `fuels`, `pricing` |
| `list_rules_for_country` | `list_rules_for_country` | `country_code` | `category`, `tags` | `rules` | `rules`, `formatted_text`, `categories` |
| `compare_rules_between_countries` | `_compare_rules_between_countries_tool` | `country1`, `country2` | `category` | `rules` | `comparison`, `formatted_summary`, `total_differences` |
| `get_answers_for_questions` | `get_answers_for_questions` | `question_ids` | – | `rules` | `items`, `pretty` |
| `list_rule_categories_and_tags` | `list_rule_categories_and_tags` | – | – | `rules` | `categories`, `tags`, `counts` |
| `list_rule_countries` | `list_rule_countries` | – | – | `rules` | `items`, `count` |

### Documentation workflow

1. **Scriptable manifest** – If new tools are added to `shared/airport_tools.py`, run a helper
   (e.g., `python -m shared.aviation_agent.adapters.dump_tool_manifest`) that prints this table so the
   doc stays synchronized.
2. **Planner alignment** – Update `AviationPlan.selected_tool` enums whenever the MCP manifest changes.
   The `_build_ui_payload()` function only needs to know which `kind` to emit for each planner tool,
   not every raw field.
3. **Payload stability** – Treat the `Notable mcp_raw keys` column as a contract with the UI; when
   changing those keys, update the design doc and UI renderer in tandem.

---

## 12. Summary of A3 Benefits

### ✔ Stable for the UI  
Only `kind`, `departure`, `icao`, etc. matter.

### ✔ Internal evolution is painless  
Planner and tool schemas can change freely.

### ✔ Full richness preserved  
`mcp_raw` always contains everything.

### ✔ Clean, simple UI dispatch  
```ts
switch(ui_payload.kind) {
  case "route": renderRoute(ui_payload.mcp_raw); break;
  case "airport": renderAirport(ui_payload.mcp_raw); break;
  case "rules": renderRules(ui_payload.mcp_raw); break;
}
```

---

## Final Notes

This README is now ready for:

- Cursor
- Claude Code
- ChatGPT code interpreter
- Direct handoff to developers

Everything needed to implement the agent end‑to‑end is included.

