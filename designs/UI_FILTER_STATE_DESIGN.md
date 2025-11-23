# UI, Filter, and State Management Design

## Overview

This document describes the architecture and design of the FlyFun Airport Explorer frontend, built with TypeScript, Zustand for state management, and Leaflet for map visualization. The system provides a reactive, maintainable, and extensible foundation for airport data exploration, filtering, and visualization.

## Architecture Principles

### 1. Single Source of Truth
- **Zustand Store**: All application state lives in a centralized Zustand store (`ts/store/store.ts`)
- **Unidirectional Data Flow**: State flows in one direction: User Action → Store → UI/Map Updates
- **No State Duplication**: State is never duplicated across components

### 2. Separation of Concerns
- **State Management**: Zustand store handles all state
- **Visualization**: VisualizationEngine handles map rendering
- **UI Management**: UIManager handles DOM updates
- **API Communication**: APIAdapter handles backend communication
- **LLM Integration**: LLMIntegration handles chatbot visualizations

### 3. Component Communication Patterns

**Direct Dependency Injection:**
- `LLMIntegration` receives `UIManager` as a constructor parameter (typed as `any` to avoid circular dependencies)
- `UIManager` is created first, then passed to `LLMIntegration` during initialization
- This allows controlled access but maintains separation of concerns

**Communication Methods:**
1. **Store Updates** (Primary): Components communicate via store state changes
   - LLMIntegration → `store.setAirports()` → Store subscription → VisualizationEngine updates
   - LLMIntegration → `store.setSearchQuery()` → Store subscription → UIManager updates UI

2. **Public API Methods** (Limited): Only specific public methods are exposed
   - `UIManager.syncFiltersToUI()` - Public method specifically for LLM to sync filter UI controls

3. **Events** (For Cross-Component Communication): Custom DOM events for loose coupling
   - `trigger-search` event - Allows any component to trigger a search (handled in `main.ts`)
   - `render-route` event - Allows route rendering from any component

**Design Pattern: LLMIntegration Communication**

LLMIntegration communicates with other components through:
- ✅ Store actions (preferred): `store.getState().setX()`
- ✅ Events: `window.dispatchEvent(new CustomEvent('trigger-search'))`
- ✅ Public APIs: `uiManager.syncFiltersToUI()`
- ❌ Never calls private methods like `handleSearch()` directly

### 4. Reactive Updates
- **Store Subscriptions**: Components subscribe to store changes
- **Automatic UI Updates**: UI updates automatically when state changes
- **Efficient Rendering**: Only updates what changed (no full re-renders)

### 5. Type Safety
- **TypeScript**: Full type safety throughout
- **Type Definitions**: All types defined in `ts/store/types.ts`
- **API Types**: Request/response types for all API calls

## Core Components

### 1. State Store (`ts/store/store.ts`)

The Zustand store is the single source of truth for all application state.

#### State Structure

```typescript
interface AppState {
  airports: Airport[];              // All airports from API
  filteredAirports: Airport[];      // Airports after filtering
  filters: FilterConfig;            // Current filter configuration
  visualization: {
    legendMode: LegendMode;         // Current legend mode
    highlights: Map<string, Highlight>; // Active highlights
    overlays: Map<string, any>;     // Map overlays
    showProcedureLines: boolean;    // Procedure lines visibility
    showRoute: boolean;             // Route visibility
  };
  route: RouteState | null;         // Current route state
  locate: LocateState | null;       // Current locate state
  selectedAirport: Airport | null;  // Selected airport for details
  mapView: MapView;                 // Map center and zoom
  ui: {
    loading: boolean;              // Loading state
    error: string | null;          // Error message
    searchQuery: string;           // Search input value
    activeTab: 'details' | 'aip' | 'rules'; // Active detail tab
  };
}
```

#### Store Actions

All state modifications go through store actions:

- `setAirports(airports)` - Set airports and auto-filter
- `setFilters(filters)` - Update filters and re-filter airports
- `setLegendMode(mode)` - Change legend mode
- `highlightPoint(highlight)` - Add highlight to map
- `removeHighlight(id)` - Remove highlight
- `clearHighlights()` - Clear all highlights
- `setRoute(route)` - Set current route
- `setLocate(locate)` - Set locate state
- `selectAirport(airport)` - Select airport for details
- `setMapView(view)` - Update map view
- `setLoading(loading)` - Set loading state
- `setError(error)` - Set error message
- `setSearchQuery(query)` - Update search query
- `setActiveTab(tab)` - Change active tab
- `clearFilters()` - Clear all filters
- `resetState()` - Reset entire state

#### Filtering Logic

Client-side filtering is performed in `filterAirports()` function in `store.ts`. Filters include:
- Country filter
- Boolean filters (has_procedures, has_aip_data, has_hard_runway, point_of_entry)
- Additional filters are applied on the backend via API

### 2. Visualization Engine (`ts/engines/visualization-engine.ts`)

Manages Leaflet map rendering and all map-related operations.

#### Responsibilities

- **Map Initialization**: Creates and configures Leaflet map
- **Marker Management**: Creates, updates, and removes airport markers
- **Legend Modes**: Applies different marker styles based on legend mode
- **Route Rendering**: Draws route lines and waypoint markers
- **Highlight System**: Manages temporary highlights (e.g., locate center, route airports, LLM highlights)
- **Procedure Lines**: Renders procedure lines for airports
- **Layer Management**: Organizes map elements into layers

#### Key Methods

- `initMap(containerId)` - Initialize map
- `updateMarkers(airports, legendMode)` - Update airport markers
- `displayRoute(routeState)` - Display route on map
- `clearRoute()` - Remove route from map
- `updateHighlights(highlights)` - Update highlight markers
- `setView(lat, lng, zoom)` - Set map view
- `getMap()` - Get Leaflet map instance
- `fitBounds()` - Fit map bounds to show all airports

#### Legend Modes

- **`airport-type`**: Colors by airport characteristics (border crossing, procedures)
- **`procedure-precision`**: Colors by procedure precision (ILS, RNAV, etc.)
- **`runway-length`**: Colors by runway length
- **`country`**: Colors by country

### 3. UI Manager (`ts/managers/ui-manager.ts`)

Handles all DOM interactions and updates UI based on state changes.

#### Responsibilities

- **Event Listeners**: Attaches event listeners to DOM elements
- **Reactive Updates**: Subscribes to store and updates UI when state changes
- **Filter Controls**: Manages filter UI controls (checkboxes, selects)
- **Search Handling**: Handles search input and triggers searches
- **Loading/Error States**: Displays loading indicators and error messages
- **Airport Details**: Updates airport details panel

#### Key Methods

- `init()` - Initialize UI manager
- `updateUI(state)` - Update UI based on state
- `updateFilterControls(filters)` - Sync filter controls with state
- `updateSearchInput(query)` - Update search input
- `updateLoadingState(loading)` - Update loading indicator
- `updateErrorState(error)` - Display error message
- `updateAirportCount(count)` - Update airport count display
- `applyFilters()` - Trigger API call with current filters
- `handleSearch(query)` - Handle search input (private)
- `handleRouteSearch(routeAirports)` - Handle route search (private)
- `syncFiltersToUI(filters)` - Public method for LLM to sync filter UI

### 4. API Adapter (`ts/adapters/api-adapter.ts`)

Handles all communication with the backend API using Fetch API.

#### Endpoints

- `getAirports(filters)` - Get airports with filters
- `getAirportDetail(icao)` - Get airport details
- `searchAirports(query, limit)` - Search airports
- `searchAirportsNearRoute(route, distance, filters)` - Route search
- `locateAirports(query, radius, filters)` - Locate airports
- `locateAirportsByCenter(center, radius, filters)` - Locate by coordinates
- `getAirportProcedures(icao)` - Get airport procedures
- `getAirportRunways(icao)` - Get airport runways
- `getAirportAIPEntries(icao)` - Get AIP entries
- `getCountryRules(countryCode)` - Get country rules
- `getAllFilters()` - Get available filters metadata
- `getAIPFilterPresets()` - Get AIP filter presets
- `getAvailableAIPFields()` - Get available AIP fields

### 5. LLM Integration (`ts/adapters/llm-integration.ts`)

Handles chatbot visualizations and filter profile application.

#### Visualization Types

The LLM can return these visualization types:

1. **`markers`**: Display airports as markers
   - Sets airports in store via `store.setAirports()`
   - Applies filter profile if provided
   - Fits map bounds to show all airports

2. **`route_with_markers`**: Display route with airports
   - Clears old LLM highlights
   - Sets highlights for airports mentioned in chat
   - Updates search query in store
   - Triggers route search via `trigger-search` event
   - Shows all airports along route with highlights on chat airports

3. **`point_with_markers`**: Display point location with airports
   - Sets airports in store
   - Sets locate state with point coordinates
   - Applies filter profile if provided
   - Fits map bounds to show all airports

4. **`marker_with_details`**: Focus on specific airport
   - Updates search query in store
   - Triggers search via `trigger-search` event

## Data Flow

### User Action Flow

```
User clicks filter checkbox
  → UIManager event listener fires
  → UIManager calls store.setFilters()
  → Store updates filters and re-filters airports
  → Store subscription fires
  → VisualizationEngine.updateMarkers() called
  → Map markers update
  → UIManager.updateUI() called
  → DOM updates
```

### API Call Flow

```
User clicks "Apply Filters"
  → UIManager.applyFilters() called
  → UIManager calls store.setLoading(true)
  → APIAdapter.getAirports(filters) called
  → Fetch API request sent
  → Response received
  → UIManager calls store.setAirports(response.airports)
  → Store filters airports and updates state
  → Store subscription fires
  → VisualizationEngine updates markers
  → UIManager updates UI
```

### Route Search Flow

When a user types a route (e.g., "EGKB LFPG") in the search input:

```
1. User types in search-input field
   ↓
2. Input event listener fires → store.setSearchQuery() (immediate)
   ↓
3. Debounced handler (500ms) → handleSearch()
   ↓
4. Route detection: parseRouteFromQuery() checks for 4-letter ICAO codes
   ↓
5. If route detected → handleRouteSearch():
   - Fetches coordinates for route airports
   - Calls API: searchAirportsNearRoute()
   - Updates store: setAirports() + setRoute()
   ↓
6. Store subscription fires → VisualizationEngine:
   - updateMarkers() - Shows airports along route
   - displayRoute() - Draws route line
   - updateHighlights() - Shows route airport highlights
   ↓
7. UIManager.updateUI() - Updates search input display
```

**Key Details:**
- Route detection: All parts must be 4-letter ICAO codes (regex: `/^[A-Za-z]{4}$/`)
- Debouncing: 500ms delay prevents excessive API calls
- Route state: Stores both ICAO codes and coordinates for route line rendering
- Filter integration: Route search results are filtered by current filters

**Non-route search:** Falls back to text search via `searchAirports()` endpoint

### Search Input Synchronization

The search input field uses bidirectional synchronization between DOM and store.

**Source of Truth:** Store (`state.ui.searchQuery`)

**User Typing Flow:**
```
User types → Input event → store.setSearchQuery() → Store subscription → updateSearchInput() → DOM syncs
```

**Programmatic Updates:**
- Update store: `store.getState().setSearchQuery(query)` 
- UI syncs automatically via subscription
- No search is triggered (just display update)

**To Trigger Search:**
- Use `trigger-search` event which sets DOM value and dispatches input event

### LLM Visualization Flow

```
Chatbot sends visualization
  → LLMIntegration.handleVisualization() called
  → Routes to appropriate handler (markers, route_with_markers, etc.)
  → Handler updates store (setAirports, setRoute, highlightPoint, etc.)
  → If filter_profile present, applyFilterProfile() called
  → Store subscription fires
  → VisualizationEngine updates map
  → UIManager updates UI
```

**LLM Route with Markers Pattern:**
1. Clear old LLM highlights (`clearLLMHighlights()`)
2. Set highlights for chat airports (`highlightPoint()`)
3. Update search query in store (`setSearchQuery()`)
4. Apply filter profile if provided
5. Trigger route search via `trigger-search` event
6. Route search shows all airports, highlights show chat airports

## Filter Updates with Active Route

When filters are changed while a route is active:

```
Filter checkbox toggled
  → handleFilterChange() updates store filters
  → Detects active route (route exists, not chatbot selection)
  → Calls applyFilters()
  → applyRouteSearch() re-runs route search API with new filters
  → Store updates → Map updates reactively
```

This ensures filters work correctly with route searches by re-running the API call with updated filters.

## Common Patterns

### Pattern 1: Updating Display Value Only

```typescript
// Just update the store - UI syncs automatically
store.getState().setSearchQuery("EGKB LFPG");
// No search triggered, just display update
```

### Pattern 2: Triggering Search from Non-UI Code

```typescript
// Update store and trigger search
store.getState().setSearchQuery(query);
window.dispatchEvent(new CustomEvent('trigger-search', { 
  detail: { query } 
}));
```

### Pattern 3: Updating State and Reacting

```typescript
// Update store
store.getState().setAirports(airports);
// Store subscription automatically triggers:
// - VisualizationEngine.updateMarkers()
// - UIManager.updateUI()
```

## Best Practices

1. **Always use store actions** - Never modify state directly
2. **Type everything** - Use TypeScript types, avoid `any`
3. **Subscribe selectively** - Components subscribe to store for reactive updates
4. **Debounce updates** - Prevent rapid-fire updates
5. **Handle errors** - Always catch and display errors
6. **Use events for cross-component actions** - Loose coupling via custom events

## Troubleshooting

### Infinite Loops
- **Cause**: Store subscription triggers state update which triggers subscription
- **Fix**: Guards and state comparison (hash-based) prevent unnecessary updates

### Map Not Updating
- **Cause**: Store not updating or subscription not firing
- **Fix**: Verify store actions are called, check subscriptions in `main.ts`

### Performance Issues
- **Cause**: Too many updates or inefficient rendering
- **Fix**: Debouncing (50ms store subscriptions, 500ms search input), state hashing to detect actual changes

## References

- **Zustand Docs**: https://zustand-demo.pmnd.rs/
- **Leaflet Docs**: https://leafletjs.com/
- **TypeScript Docs**: https://www.typescriptlang.org/
- **Vite Docs**: https://vitejs.dev/
