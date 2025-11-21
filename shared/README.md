## Shared Tooling Overview

This directory hosts the business logic and metadata that power every "tool" exposed by the Euro AIP MCP stack. The same code drives:

- `mcp_server/main.py`, where each FastMCP tool decorator delegates to a shared helper via a `ToolContext`.
- `shared/aviation_agent/tools.py`, where the aviation agent calls tools in-process using the manifest via `AviationToolClient`.
- The integration tests in `tests/tools/` and `tests/aviation_agent/`, which reuse a cached `ToolContext` to verify both in-process and live HTTP flows.

Understanding and extending the shared layer keeps the server, client, and tests in sync.

---

### Adding or Updating a Tool

1. **Implement the handler in `shared/airport_tools.py`**
   - Each handler takes a `ToolContext` as its first argument and returns a dict payload. The context provides access to the Euro AIP model, enrichment storage, and rules.
   - Keep responses consistent with existing helpers: include counts, pretty text, filter profiles, and visualization data when appropriate.
   - Reuse `FilterEngine`, `PriorityEngine`, and other shared utilities instead of duplicating logic.

2. **Update the tool manifest**
   - Near the bottom of `shared/airport_tools.py`, `_build_shared_tool_specs()` defines the ordered tool registry.
   - Add a new entry describing the tool: name, handler, documentation string, JSON schema for arguments, and whether it should be exposed to the LLM.
   - The manifest is consumed by `AviationToolClient` (in `shared/aviation_agent/tools.py`) and provides the metadata used when advertising tools to the LLM.

3. **Keep server wiring explicit**
   - `mcp_server/main.py` contains FastMCP decorators for each tool. Each decorator retrieves the shared `ToolContext` and calls the handler.
   - When adding a tool, create a wrapper similar to the existing ones. This ensures signatures stay explicit (FastMCP cannot register functions with `**kwargs`) while still calling the shared logic.

4. **Client auto-wiring**
   - `shared/aviation_agent/tools.py` loads the manifest via `get_shared_tool_specs()` and uses it to dispatch tool calls without HTTP through `AviationToolClient`.
   - No additional code changes are required when the manifest is updated, unless the tool requires special handling.

5. **Tests**
   - `tests/aviation_agent/` contains integration tests that exercise tools through the agent flow using `AviationToolClient`. When adding a new tool, consider adding coverage here.
   - `tests/tools/test_mcp_server_tools.py` verifies that the FastMCP-decorated functions execute with the cached `ToolContext` by calling each tool's `FunctionTool.fn`.
   - `tests/tools/test_mcp_server_live.py` (optional, gated by `RUN_LIVE_MCP_SERVER_TESTS=1`) starts the HTTP server in a subprocess and calls tools via the official FastMCP client. Use this for end-to-end verification when necessary.

6. **Data sources**
   - `ToolContext.create()` expects local copies of `airports.db` and `rules.json`. The test fixtures in `tests/tools/conftest.py` locate these files automatically by scanning common directories (`data/`, repo root, `mcp_server/`, etc.) and cache the context for reuse across tests.
   - If a tool requires additional data sources, expose them through `ToolContext` so both the server and client can access them consistently.

---

### Argument and Schema Guidelines

- Document arguments in the handler docstring; the manifest pulls descriptions from `_tool_description`.
- The manifest’s `parameters` entry should be valid JSON Schema. Use `type: object`, list required fields, and provide reasonable defaults.
- Avoid `**kwargs` or `*args` in tool functions; FastMCP’s schema generator rejects them.
- When responses include structured data, keep field names stable. The chatbot and UI features (filter profiles, map overlays) rely on these keys.

---

### Testing Strategy Recap

| Layer | Location | What it verifies |
| --- | --- | --- |
| Shared logic | Add pytest cases that call handlers directly where needed | Business rules without MCP plumbing |
| Server wrappers | `tests/tools/test_mcp_server_tools.py` | Decorators + ToolContext wiring (calls `tool.fn`) |
| Agent integration | `tests/aviation_agent/` | Full agent flow with tools via `AviationToolClient` |
| Live HTTP | `tests/tools/test_mcp_server_live.py` (optional) | Full FastMCP server/client over HTTP, gated by `RUN_LIVE_MCP_SERVER_TESTS=1` |

Always run `source venv/bin/activate && pytest tests/tools` before pushing tool changes.

---

### Common Pitfalls & Tips

- **Manifest drift**: if you add a new tool handler but forget the manifest entry, the agent and tests won't see it. Treat the manifest as the source of truth for tool metadata.
- **Context initialization**: both the server and client rely on `ToolContext.create()`. Ensure new data dependencies are made available through that path, not via ad-hoc globals.
- **Performance**: handlers should avoid loading the database repeatedly. Use the provided context and caching layers (`FilterEngine`, `PriorityEngine`, `EnrichmentStorage`).
- **Live tests**: the live HTTP tests install the `fastmcp` client and spawn the server in a subprocess. They are disabled by default; run them only when needed (`RUN_LIVE_MCP_SERVER_TESTS=1`) to avoid long CI cycles.

With this structure, you can add or modify tools once in `shared/airport_tools.py` and know that the server, client, and tests all stay consistent.***

