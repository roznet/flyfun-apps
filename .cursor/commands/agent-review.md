# Aviation Agent Architecture Review

## Overview
Review code changes in `shared/aviation_agent/` and `web/server/api/aviation_agent_chat.py` to ensure compliance with our LangGraph agent architecture. Verify that the UI payload remains stable, tool names match the manifest, and state management follows LangGraph patterns.

## Architecture Rules

1. **UI Payload Stability** - Hybrid approach must be maintained:
   - Stable top-level keys (`kind`, `departure`, `icao`, `region`, etc.)
   - Flattened common fields (`filters`, `visualization`, `airports`)
   - Full MCP result in `mcp_raw` as authoritative source

2. **Tool Name Consistency** - Tool names must match exactly with `shared/airport_tools.get_shared_tool_specs()`
   - Planner uses literal tool names from manifest
   - No invented or hardcoded tool names

3. **State Management** - AgentState is single source of truth:
   - Use TypedDict structure, no direct mutations
   - Errors stored in state, not raised as exceptions
   - Use LangGraph reducers (`operator.add` for messages)

4. **UI Payload Building** - Only `build_ui_payload()` creates `ui_payload`:
   - Centralized in `formatting.py`
   - Must preserve hybrid structure
   - Tool-to-kind mapping must be correct

5. **Visualization Types** - Must match UI expectations:
   - `route_with_markers` - Route with airport markers
   - `markers` - General airport markers
   - `point_with_markers` - Location point with airports
   - `marker_with_details` - Single airport focus
   - Types come from tool results, not agent code

6. **Filter Extraction** - Filters must be in `plan.arguments.filters`:
   - Extracted by planner, not formatter
   - Tools return `filter_profile` (what was applied)
   - UI gets filters from flattened `ui_payload.filters`

7. **Error Handling** - Errors propagate through state:
   - Store errors in `state["error"]` field
   - Formatter can produce error message even on failure
   - Errors emitted as SSE events

8. **Separation of Concerns**:
   - `planning.py` - Planner logic only
   - `execution.py` - Tool execution only
   - `formatting.py` - Answer formatting and UI payload building
   - `graph.py` - LangGraph node definitions only
   - No mixing of concerns

## Review Checklist

### 1. UI Payload Structure
- [ ] `ui_payload` has `kind` field (route/airport/rules)?
- [ ] `mcp_raw` contains full tool result as authoritative source?
- [ ] Common fields (`filters`, `visualization`, `airports`) are flattened at top level?
- [ ] No breaking changes to stable top-level fields?
- [ ] `build_ui_payload()` is the only place creating `ui_payload`?

### 2. Tool Name Consistency
- [ ] Tool names match exactly with `shared/airport_tools.py`?
- [ ] Planner validates tool names against manifest?
- [ ] No hardcoded tool names that don't exist?
- [ ] Tool-to-kind mapping in `_determine_kind()` is complete?

### 3. State Management
- [ ] Uses `AgentState` TypedDict structure?
- [ ] No direct state mutations (dict[key] = value)?
- [ ] Errors stored in state, not raised as exceptions?
- [ ] Messages use `operator.add` reducer?

### 4. Visualization Types
- [ ] Visualization types match what UI expects?
- [ ] Types come from tool results, not agent-generated?
- [ ] `_enhance_visualization()` preserves existing structure?
- [ ] Route endpoints always included in filtered markers?

### 5. Filter Handling
- [ ] Filters extracted in planner, not formatter?
- [ ] Filters stored in `plan.arguments.filters`?
- [ ] Tools return `filter_profile` in results?
- [ ] UI payload flattens `filter_profile` to `filters`?

### 6. Error Handling
- [ ] Errors stored in `state["error"]`?
- [ ] Formatter handles errors gracefully?
- [ ] Errors emitted as SSE events?
- [ ] No unhandled exceptions?

### 7. Separation of Concerns
- [ ] Planner doesn't format answers?
- [ ] Tool runner doesn't build UI payload?
- [ ] Formatter doesn't execute tools?
- [ ] Graph nodes are thin wrappers?

### 8. LangGraph Patterns
- [ ] Uses `astream_events()` for streaming?
- [ ] State reducers used correctly?
- [ ] Nodes return state dictionaries?
- [ ] Graph edges defined correctly?

## Red Flags to Flag

Flag these violations immediately:

- 🔴 **Breaking UI payload structure**: Changing stable top-level fields (`kind`, `departure`, `icao`, etc.)
- 🔴 **Invented tool names**: Using tool names not in `shared/airport_tools.py`
- 🔴 **Direct state mutations**: `state["key"] = value` instead of returning dict
- 🔴 **UI payload created outside `build_ui_payload()`**: Creating `ui_payload` manually
- 🔴 **Raised exceptions instead of state errors**: `raise Exception()` instead of `return {"error": "..."}`
- 🔴 **Mixing concerns**: Planner formatting answers, formatter executing tools
- 🔴 **Hardcoded visualization types**: Generating visualization types instead of using tool results
- 🔴 **Filters in wrong place**: Filters extracted in formatter instead of planner
- 🔴 **Breaking kind mapping**: Tools not mapped to correct UI `kind` buckets
- 🔴 **Missing mcp_raw**: UI payload without `mcp_raw` field

## Review Process

1. **Analyze changed files** in `shared/aviation_agent/` or `web/server/api/aviation_agent_chat.py`
2. **Check each rule** against the checklist above
3. **Verify tool names** against `shared/airport_tools.py` manifest
4. **Verify UI payload structure** matches hybrid approach
5. **Identify violations** with specific file paths and line numbers
6. **Suggest fixes** with code examples showing the corrected approach
7. **Check UI integration** - ensure changes don't break frontend expectations

## Output Format

For each finding:

**✅ APPROVED:**
- `file:line` - Brief explanation of why it's correct
- Example: `formatting.py:73` - Uses `build_ui_payload()` correctly, maintains hybrid structure

**❌ VIOLATION:**
- `file:line` - Description of violation
- **Problem:** Why it violates architecture
- **Fix:** Suggested corrected implementation
- **Impact:** What breaks (UI, tests, etc.)

Example violation:
```
❌ VIOLATION:
planning.py:150
- Issue: Hardcoded tool name "custom_search" that doesn't exist in manifest
- Problem: Tool name not in shared/airport_tools.py, will fail at runtime
- Fix: Use actual tool name from get_shared_tool_specs() or add tool to manifest first
- Impact: Runtime error when planner selects this tool
```

## Approved Patterns Reference

**UI Payload Building:**
```python
# ✅ GOOD: Use build_ui_payload() function
ui_payload = build_ui_payload(plan, tool_result)

# ✅ GOOD: Preserves hybrid structure
base_payload = {
    "kind": kind,
    "mcp_raw": tool_result,  # Authoritative source
    "filters": tool_result.get("filter_profile"),  # Flattened
    "visualization": tool_result.get("visualization"),  # Flattened
}
```

**State Updates:**
```python
# ✅ GOOD: Return state dictionary
def planner_node(state: AgentState) -> Dict[str, Any]:
    plan = create_plan()
    return {"plan": plan, "planning_reasoning": "..."}

# ❌ BAD: Direct mutation
def planner_node(state: AgentState):
    state["plan"] = create_plan()  # Don't do this!
```

**Error Handling:**
```python
# ✅ GOOD: Store error in state
def tool_node(state: AgentState) -> Dict[str, Any]:
    try:
        result = tool_runner.run(plan)
        return {"tool_result": result}
    except Exception as e:
        return {"error": str(e)}  # Store in state, don't raise

# ❌ BAD: Raise exception
def tool_node(state: AgentState):
    result = tool_runner.run(plan)  # Exception bubbles up
```

**Tool Name Usage:**
```python
# ✅ GOOD: Get tool names from manifest
tools = get_shared_tool_specs()
tool_names = [tool.name for tool in tools]
if plan.selected_tool not in tool_names:
    return {"error": f"Unknown tool: {plan.selected_tool}"}

# ❌ BAD: Hardcoded tool names
if plan.selected_tool == "my_custom_tool":  # Tool doesn't exist!
    ...
```

## Key Considerations

### UI Payload Stability
- **Never remove** stable top-level fields (`kind`, `departure`, `icao`, `region`)
- **Always include** `mcp_raw` with full tool result
- **Flatten common fields** for convenience, but don't remove from `mcp_raw`
- **Test UI integration** - changes to `ui_payload` structure can break frontend

### Tool Name Validation
- **Always validate** tool names against `shared/airport_tools.py`
- **Update manifest first** before using new tools
- **Check tool-to-kind mapping** when adding new tools

### State Management
- **Never mutate** state directly
- **Always return** state dictionaries from nodes
- **Handle errors** gracefully in state
- **Use reducers** for collections (messages)

### Visualization Enhancement
- **Preserve route endpoints** when filtering markers
- **Don't generate** visualization types (use tool results)
- **Update both** `visualization` and `mcp_raw.visualization` when enhancing

## Things to Ensure

✅ **DO:**
- Maintain UI payload hybrid structure
- Validate tool names against manifest
- Store errors in state, not raise exceptions
- Use `build_ui_payload()` exclusively
- Preserve route endpoints in filtered markers
- Return state dictionaries from nodes
- Test UI integration after changes

## Things to Avoid

❌ **DON'T:**
- Remove or rename stable UI payload fields
- Invent tool names not in manifest
- Mutate state directly
- Create `ui_payload` outside `build_ui_payload()`
- Raise exceptions instead of storing in state
- Mix concerns between planner/executor/formatter
- Generate visualization types (use tool results)
- Break tool-to-kind mapping

## Notes

- Focus on architecture compliance, not code style
- Flag even minor violations to prevent pattern drift
- Reference `designs/LLM_AGENT_DESIGN.md` for design details
- Check `shared/airport_tools.py` for tool manifest
- Verify UI integration in `web/client/ts/adapters/llm-integration.ts`
- Be constructive - suggest fixes, don't just point out problems

