# Web App Architecture

> **Read this first** before working on any web app feature.

## Quick Reference

| Component | File | Purpose |
|-----------|------|---------|
| Store | `ts/store/store.ts` | Single source of truth (Zustand) |
| Types | `ts/store/types.ts` | All TypeScript type definitions |
| VisualizationEngine | `ts/engines/visualization-engine.ts` | Map rendering (Leaflet) |
| UIManager | `ts/managers/ui-manager.ts` | DOM updates, event handlers |
| ChatbotManager | `ts/managers/chatbot-manager.ts` | Chat UI, SSE event processing |
| LLMIntegration | `ts/adapters/llm-integration.ts` | Chatbot → Map visualization |
| APIAdapter | `ts/adapters/api-adapter.ts` | Backend API communication |
| Legend Configs | `ts/config/legend-configs.ts` | Shared legend configuration |
| Main | `ts/main.ts` | App bootstrap, event wiring |

**Related Design Docs:**
- `WEB_APP_STATE.md` - Store structure, actions, data flow
- `WEB_APP_MAP.md` - Map visualization, markers, routes
- `WEB_APP_LEGENDS.md` - Legend modes and configuration
- `WEB_APP_CHAT.md` - Chatbot integration, SSE streaming
- `WEB_APP_FILTERS.md` - Filter system, AIP filtering
- `AUTH_USAGE.md` - Authentication, chatbot gating, usage tracking

---

## Architecture Principles

### 1. Single Source of Truth

All application state lives in the Zustand store. No component maintains its own copy of shared state.

```
Store (Zustand)
    ↓ subscriptions
┌───────────────────────────────────────┐
│  VisualizationEngine  │  UIManager    │
│  (map updates)        │  (DOM updates)│
└───────────────────────────────────────┘
```

### 2. Unidirectional Data Flow

```
User Action → Store Action → State Change → Subscriptions → UI/Map Updates
```

**Never:**
- Update DOM directly from event handlers (go through store)
- Duplicate state in components
- Call component methods directly across boundaries (use events or store)

### 3. Separation of Concerns

| Layer | Responsibility | Never Does |
|-------|----------------|------------|
| Store | State management, filtering logic | DOM manipulation, API calls |
| VisualizationEngine | Leaflet map, markers, layers | State management, API calls |
| UIManager | DOM updates, user input handling | Map rendering, state storage |
| APIAdapter | HTTP requests to backend | State management, DOM updates |
| LLMIntegration | Chatbot → visualization bridge | Direct DOM manipulation |

---

## Component Communication

### Pattern 1: Store-Based (Primary)

Components communicate via store state changes:

```typescript
// Component A updates store
store.getState().setAirports(airports);

// Component B reacts via subscription (in main.ts)
store.subscribe((state) => {
  visualizationEngine.updateMarkers(state.filteredAirports, state.visualization.legendMode);
});
```

### Pattern 2: Custom Events (Cross-Component Actions)

For actions that span multiple components:

| Event | Purpose | Handler Location |
|-------|---------|------------------|
| `trigger-search` | Trigger search from anywhere | `main.ts` |
| `trigger-locate` | Trigger locate search | `main.ts` |
| `trigger-filter-refresh` | Load airports matching store filters | `main.ts` |
| `airport-click` | Open airport details panel | `main.ts` |
| `render-route` | Draw route on map | `main.ts` |
| `show-country-rules` | Display rules panel | `main.ts` |
| `reset-rules-panel` | Clear rules panel | `main.ts` |

```typescript
// Dispatch event
window.dispatchEvent(new CustomEvent('trigger-search', {
  detail: { query: 'EGKB LFPG' }
}));

// Handle in main.ts
window.addEventListener('trigger-search', (e) => {
  const { query } = e.detail;
  // ... handle search
});
```

### Pattern 3: Direct Injection (Limited)

Only for specific, controlled interactions:

```typescript
// LLMIntegration receives UIManager for filter sync
const llmIntegration = new LLMIntegration(uiManager);

// Only uses public API
llmIntegration.applyFilterProfile(filters); // → uiManager.syncFiltersToUI()
```

---

## Directory Structure

```
web/client/ts/
├── main.ts                    # App bootstrap, subscriptions, event wiring
├── store/
│   ├── store.ts               # Zustand store definition
│   └── types.ts               # All TypeScript types
├── engines/
│   └── visualization-engine.ts # Leaflet map rendering
├── managers/
│   ├── ui-manager.ts          # DOM updates, user input
│   ├── chatbot-manager.ts     # Chat UI, SSE processing
│   └── persona-manager.ts     # GA persona management
├── adapters/
│   ├── api-adapter.ts         # Backend API client
│   └── llm-integration.ts     # Chatbot → visualization
├── config/
│   └── legend-configs.ts      # Legend mode configurations
└── utils/
    ├── legend-classifier.ts   # Legend classification utilities
    └── geocode-cache.ts       # Location → coordinates cache
```

---

## Initialization Flow

```typescript
// main.ts - App bootstrap
async function init() {
  // 1. Create components (order matters)
  const apiAdapter = new APIAdapter();
  const visualizationEngine = new VisualizationEngine();
  const uiManager = new UIManager(apiAdapter, visualizationEngine);
  const llmIntegration = new LLMIntegration(uiManager);
  const chatbotManager = new ChatbotManager(llmIntegration);
  // ChatbotManager subscribes to auth state — shows sign-in overlay or chat UI

  // 2. Check auth (non-blocking, chatbot reacts via store subscription)
  checkAuth(); // fetch /auth/me → setAuth() → renderAuthButton()

  // 3. Initialize map
  visualizationEngine.initMap('map');

  // 4. Wire up store subscriptions
  store.subscribe((state, prevState) => {
    // Debounced updates to prevent rapid-fire renders
    if (state.filteredAirports !== prevState.filteredAirports) {
      visualizationEngine.updateMarkers(...);
    }
  });

  // 4. Wire up custom events
  window.addEventListener('trigger-search', handleTriggerSearch);
  window.addEventListener('airport-click', handleAirportClick);
  // ... more events

  // 5. Initialize UI
  uiManager.init();

  // 6. Load initial data
  await loadInitialAirports();
}
```

---

## Key Invariants

### Store Invariants
- All state changes go through store actions
- `filteredAirports` is always derived from `airports` + `filters`
- Never mutate state directly (always use setters)

### Map Invariants
- Markers are managed by VisualizationEngine only
- Layer cleanup happens before adding new layers
- Highlights have unique IDs, duplicates are prevented

### Communication Invariants
- Components never call each other's private methods
- Cross-component actions use events or store
- No direct DOM manipulation from adapters

---

## Common Patterns

### Updating Display Only (No Search)

```typescript
// Just update store - UI syncs automatically
store.getState().setSearchQuery('EGKB LFPG');
// No search triggered, just display update
```

### Triggering Search Programmatically

```typescript
// Update store AND trigger search
store.getState().setSearchQuery(query);
window.dispatchEvent(new CustomEvent('trigger-search', { detail: { query } }));
```

### Reacting to State Changes

```typescript
// In main.ts subscription
store.subscribe((state, prevState) => {
  if (state.visualization.legendMode !== prevState.visualization.legendMode) {
    visualizationEngine.updateMarkers(state.filteredAirports, state.visualization.legendMode);
    uiManager.updateLegendDisplay(state.visualization.legendMode);
  }
});
```

---

## Debugging

### Store State
```javascript
// Browser console
window.store.getState()  // Current state
window.store.getState().airports.length  // Airport count
```

### Geocode Cache
```javascript
window.geocodeCache  // Inspect cached locations
```

### Events
```javascript
// Monitor custom events
window.addEventListener('trigger-search', (e) => console.log('Search:', e.detail));
```

---

## Anti-Patterns to Avoid

| Don't | Do Instead |
|-------|------------|
| Store state in component class | Use Zustand store |
| Call `uiManager.handleSearch()` from LLMIntegration | Dispatch `trigger-search` event |
| Update DOM directly from event handlers | Update store, let subscriptions handle DOM |
| Duplicate airport list in multiple places | Single `state.airports`, derive as needed |
| Import components circularly | Use events for cross-component communication |

---

## Performance Considerations

- **Debouncing**: Store subscriptions debounced at 50ms, search input at 500ms
- **State Hashing**: Hash-based comparison prevents unnecessary re-renders
- **Layer Cleanup**: Clear layers before adding new ones to prevent memory leaks
- **Bulk Operations**: Use `setGAScores()` for batch updates, not individual calls
