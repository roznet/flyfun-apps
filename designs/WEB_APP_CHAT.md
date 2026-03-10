# Web App Chat Integration

> ChatbotManager, SSE streaming, UI payload handling, and visualization types.

## Quick Reference

| File | Purpose |
|------|---------|
| `ts/managers/chatbot-manager.ts` | Chat UI, message rendering, SSE processing |
| `ts/adapters/llm-integration.ts` | Visualization handler, filter profile application |
| `ts/utils/geocode-cache.ts` | Location → coordinates cache |

**Key Exports:**
- `ChatbotManager` - Chat UI and SSE event processing
- `LLMIntegration` - Chatbot → map visualization bridge

**Prerequisites:** Read `WEB_APP_ARCHITECTURE.md` and `WEB_APP_STATE.md` first.

**Related:**
- `WEB_APP_LEGENDS.md` - Legend switching based on tool/filters
- `AVIATION_AGENT_DESIGN.md` - Backend agent architecture

---

## Architecture Overview

```
Backend (SSE Stream)          Frontend
────────────────────          ────────
POST /api/aviation-agent/chat/stream
        │
        ▼
    SSE Events ─────────────► ChatbotManager
        │                          │
        │ plan                     │ Render thinking
        │ thinking                 │ Show plan details
        │ message (chunks)         │ Stream answer text
        │ ui_payload ─────────────►│──► LLMIntegration
        │ done                     │         │
        ▼                          │         ▼
                                   │    Store actions
                                   │    (setAirports, setRoute, etc.)
                                   │         │
                                   │         ▼
                                   │    Map/UI updates
```

---

## SSE Event Types

Events are received in order during a chat request:

| Event | Data | When Emitted | Handler Action |
|-------|------|--------------|----------------|
| `plan` | `{selected_tool, arguments}` | After planner | Show tool selection |
| `thinking` | `{content}` | After planner | Display reasoning (collapsible) |
| `tool_call_start` | `{name, arguments}` | Before tool runs | Show loading indicator |
| `tool_call_end` | `{name, result}` | After tool runs | Hide loading indicator |
| `message` | `{content}` | During formatting | Stream answer character-by-character |
| `thinking_done` | `{}` | Formatter complete | Finalize thinking display |
| `ui_payload` | `{kind, tool, visualization, ...}` | Once, after formatter | Trigger visualization |
| `final_answer` | `{...state}` | After formatter | For logging (optional) |
| `done` | `{session_id, thread_id, tokens}` | Request complete | Track session, show token count |
| `error` | `{message}` | On error | Display error message |

---

## Authentication Gating

The chatbot requires authentication. See `AUTH_USAGE.md` for full details.

- **Not signed in**: Chat panel shows sign-in overlay (lock icon + Google sign-in button). Input/send disabled, quick actions hidden.
- **Signed in**: Normal chat UI. `attachEventListeners()`, `loadQuickActions()`, `addWelcomeMessage()` called once via `authInitialized` flag.
- **401 from `/chat/stream`**: Resets auth state → shows sign-in overlay.
- **429 from `/chat/stream`**: Displays daily rate limit message.

Backend: `/api/aviation-agent/chat` and `/chat/stream` require `Depends(current_user_id)`. `/quick-actions` remains public.

---

## ChatbotManager Responsibilities

### Message Rendering
- Render user messages and assistant responses
- Stream answer text character-by-character
- Display thinking/reasoning (collapsible section)
- Show suggested queries after response

### SSE Event Processing
- Connect to streaming endpoint
- Parse and route SSE events
- Handle connection errors and retries

### Session Management
- Track `thread_id` for multi-turn conversations
- Track `session_id` for logging

---

## UI Payload Structure

The `ui_payload` event contains all visualization data:

```typescript
interface UIPayload {
  kind: 'route' | 'airport' | 'rules';
  tool: string;                          // Tool name (for legend switching)

  // Flattened fields (from tool result)
  filters?: FilterConfig;                // filter_profile
  visualization?: Visualization;         // Map visualization data
  airports?: Airport[];                  // Airport list

  // Kind-specific metadata
  departure?: string;                    // Route tools
  destination?: string;
  icao?: string;                         // Airport tools
  region?: string;                       // Rules tools
  topic?: string;

  // Optional features
  suggested_queries?: SuggestedQuery[];
  show_rules?: {                         // Rules panel trigger
    countries: string[];
    tags_by_country: Record<string, string[]>;
  };
}
```

---

## Visualization Types

The `visualization.type` field determines how to display results on the map.

### `markers` - Airport Markers

**Two modes based on filters:**

**Mode 1: With meaningful filters** (country, fuel_type, point_of_entry, etc.)
```
1. Clear old LLM highlights
2. Apply filter profile to store (updates UI filter controls)
3. Add blue highlights for returned airports
4. Dispatch 'trigger-filter-refresh' event
5. Result: Map shows ALL airports matching filters, with LLM recommendations highlighted
```

**Mode 2: No meaningful filters** (just airport list)
```
1. Clear old LLM highlights
2. Set airports in store directly
3. Add blue highlights for all returned airports
4. Fit map bounds
5. Result: Map shows only returned airports, all highlighted
```

### `route_with_markers` - Route with Airports

```
1. Clear old LLM highlights
2. Set highlights for airports mentioned in chat
3. Update search query in store
4. Apply filter profile (if provided)
5. Dispatch 'trigger-search' event
6. Result: Route line drawn, airports along route shown, chat airports highlighted
```

### `point_with_markers` - Location with Airports

```
1. Clear old LLM highlights
2. Set highlights for recommended airports
3. Set locate state in store (center point)
4. Cache geocode result (label → coords)
5. Apply filter profile
6. Dispatch 'trigger-locate' event
7. Result: Airports within radius shown, recommended airports highlighted
```

### `marker_with_details` - Single Airport Focus

```
1. Update search query in store
2. Dispatch 'trigger-search' event (centers map, shows marker)
3. Dispatch 'airport-click' event (opens details panel)
4. Result: Map centers on airport, details panel opens
```

---

## LLMIntegration Methods

### handleVisualization(visualization)

Routes to appropriate handler based on `visualization.type`:

```typescript
handleVisualization(visualization: Visualization): void {
  switch (visualization.type) {
    case 'markers':
      this.handleMarkers(visualization);
      break;
    case 'route_with_markers':
      this.handleRouteWithMarkers(visualization);
      break;
    case 'point_with_markers':
      this.handlePointWithMarkers(visualization);
      break;
    case 'marker_with_details':
      this.handleMarkerWithDetails(visualization);
      break;
  }
}
```

### applySuggestedLegend(tool, filters)

Switches map legend based on query context. See `WEB_APP_LEGENDS.md` for details.

### applyFilterProfile(filters)

Applies filter profile to store and syncs UI controls:

```typescript
applyFilterProfile(filters: FilterConfig): void {
  // Update store
  store.getState().setFilters(filters);

  // Sync UI controls (checkboxes, dropdowns)
  this.uiManager.syncFiltersToUI(filters);
}
```

### clearLLMHighlights()

Removes highlights created by previous LLM responses:

```typescript
clearLLMHighlights(): void {
  const highlights = store.getState().visualization.highlights;
  highlights.forEach((_, id) => {
    if (id.startsWith('llm-')) {
      store.getState().removeHighlight(id);
    }
  });
}
```

---

## Rules Panel Integration

When `show_rules` is present in `ui_payload`:

```typescript
// In ChatbotManager or LLMIntegration
if (uiPayload.show_rules) {
  window.dispatchEvent(new CustomEvent('show-country-rules', {
    detail: {
      countries: uiPayload.show_rules.countries,
      tagsByCountry: uiPayload.show_rules.tags_by_country
    }
  }));
}
```

**Handler in main.ts:**
1. Load rules for each country via API
2. Store rules: `store.setRulesForCountry(countryCode, rules)`
3. Set selection: `store.setRulesSelection(countries, visualFilter)`
4. Rules panel renders filtered rules, grouped by category

---

## Tool-to-Visualization Mapping

| Tool | Visualization Type | Map Behavior |
|------|-------------------|--------------|
| `search_airports` | `markers` | With filters: loads ALL matching + highlights. Without: shows returned only |
| `find_airports_near_route` | `route_with_markers` | Shows route line, highlights chat airports |
| `find_airports_near_location` | `point_with_markers` | Shows locate center, highlights recommended |
| `get_airport_details` | `marker_with_details` | Centers map, opens details panel |
| `get_notification_for_airport` | `marker_with_details` | Centers map, opens details panel |
| `answer_rules_question` | None | Triggers rules panel |
| `browse_rules` | None | Triggers rules panel |
| `compare_rules_between_countries` | None | Triggers rules panel |

---

## Geocode Cache Integration

The geocode cache prevents text search from overwriting locate results:

```typescript
// When handling point_with_markers
handlePointWithMarkers(viz: Visualization): void {
  // Cache the geocode result BEFORE triggering locate
  geocodeCache.set(viz.label, viz.center.lat, viz.center.lon, viz.label);

  // Set store state
  store.getState().setLocate({
    query: viz.label,
    center: viz.center,
    radius: viz.radius
  });

  // Trigger locate search
  window.dispatchEvent(new CustomEvent('trigger-locate', {
    detail: {
      label: viz.label,
      lat: viz.center.lat,
      lon: viz.center.lon
    }
  }));
}
```

**Why needed:** After locate search, the search box shows the location label (e.g., "Brac, Croatia"). The debounced search handler would text-search this label and overwrite results. The cache tells the handler to do a locate search instead.

---

## Suggested Queries

When `suggested_queries` is present in `ui_payload`:

```typescript
interface SuggestedQuery {
  text: string;      // Display text
  tool: string;      // Expected tool
  category: string;  // Query category
  priority: number;  // Display order
}
```

**Rendering:**
```typescript
renderSuggestedQueries(queries: SuggestedQuery[]): void {
  const container = document.getElementById('suggested-queries');
  container.innerHTML = queries
    .sort((a, b) => b.priority - a.priority)
    .map(q => `<button class="suggested-query">${q.text}</button>`)
    .join('');

  // Wire up click handlers
  container.querySelectorAll('button').forEach((btn, i) => {
    btn.addEventListener('click', () => {
      this.sendMessage(queries[i].text);
    });
  });
}
```

---

## Session and Thread Management

### Thread ID (Conversation Memory)

The `thread_id` enables multi-turn conversations with context preservation:

```typescript
class ChatbotManager {
  private threadId: string | null = null;

  // On 'done' event, store the thread_id
  handleDoneEvent(data: { thread_id: string; session_id: string; tokens: TokenUsage }) {
    this.threadId = data.thread_id;
    this.displayTokenUsage(data.tokens);
  }

  // Include thread_id in subsequent requests
  async sendMessage(content: string) {
    const response = await fetch('/api/aviation-agent/chat/stream', {
      method: 'POST',
      body: JSON.stringify({
        messages: this.buildMessageHistory(content),
        thread_id: this.threadId  // null for first message, then reused
      })
    });
  }

  // Reset conversation (new thread)
  resetConversation() {
    this.threadId = null;
    this.messages = [];
  }
}
```

**Key behaviors:**
- First request: `thread_id: null` → backend generates new ID
- Subsequent requests: reuse `thread_id` from `done` event
- Reset: set `threadId = null` to start fresh conversation

### Session ID (Logging)

The `session_id` is used for conversation logging and analytics:

```typescript
// Extracted from 'done' event
// { "session_id": "session_1234567890", "thread_id": "thread_abc123", ... }

// Session ID format: session_{timestamp}
// Thread ID format: thread_{uuid}
```

---

## Token Tracking

The `done` event includes token usage statistics:

```typescript
interface TokenUsage {
  input: number;   // Prompt tokens (all LLM calls combined)
  output: number;  // Completion tokens (all LLM calls combined)
  total: number;   // input + output
}

// Example 'done' event data:
// {
//   "session_id": "session_1234567890",
//   "thread_id": "thread_abc123",
//   "tokens": { "input": 1250, "output": 450, "total": 1700 }
// }
```

**Display pattern:**
```typescript
displayTokenUsage(tokens: TokenUsage): void {
  const tokenDisplay = document.getElementById('token-count');
  if (tokenDisplay) {
    tokenDisplay.textContent = `${tokens.total} tokens`;
    tokenDisplay.title = `Input: ${tokens.input}, Output: ${tokens.output}`;
  }
}
```

**Token aggregation:** Tokens are summed across ALL LLM calls in a request:
- Planner LLM call
- Formatter LLM call
- Router LLM call (if rules query)
- Rules agent LLM call (if rules query)

---

## Multi-Turn Conversations

The backend supports multi-turn conversations via checkpointing:

```typescript
// First request (new conversation)
const response = await fetch('/api/aviation-agent/chat/stream', {
  method: 'POST',
  body: JSON.stringify({
    messages: [{ role: 'user', content: 'Find airports near Paris' }],
    thread_id: null  // Will be auto-generated
  })
});

// 'done' event returns thread_id
// { "session_id": "...", "thread_id": "thread_abc123", "tokens": {...} }

// Subsequent requests (continue conversation)
const response = await fetch('/api/aviation-agent/chat/stream', {
  method: 'POST',
  body: JSON.stringify({
    messages: [...previousMessages, { role: 'user', content: 'Show me ones with AVGAS' }],
    thread_id: 'thread_abc123'  // Use from previous response
  })
});
```

**Conversation context:** When `thread_id` is provided, the backend retrieves conversation history from the checkpoint store, enabling follow-up queries like "Show me ones with AVGAS" to understand context.

---

## Error Handling

### SSE Connection Errors

```typescript
eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  this.showError('Connection lost. Please try again.');
  eventSource.close();
};
```

### Error Events from Backend

```typescript
if (event.event === 'error') {
  this.showError(event.data.message);
}
```

### Graceful Degradation

If visualization fails, the chat response is still displayed. Errors are logged but don't block the conversation.

---

## Implementation Checklist for New Visualization Types

1. **Backend:** Tool returns `visualization` in result with new type
2. **LLMIntegration:** Add case in `handleVisualization()` switch
3. **Handler:** Implement `handleNewType()` method
4. **Store actions:** Determine which store actions are needed
5. **Events:** Determine if custom events are needed
6. **Test:** Verify map updates correctly

---

## Debugging

```javascript
// Browser console

// Check current chat state
chatbotManager.getMessages()

// Manually trigger visualization
llmIntegration.handleVisualization({
  type: 'markers',
  airports: store.getState().airports.slice(0, 5)
});

// Check geocode cache
geocodeCache.get('Brac, Croatia')
```
