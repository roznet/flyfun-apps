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
   - `trigger-locate` event - Allows any component to trigger a locate search (handled in `main.ts`)
   - `render-route` event - Allows route rendering from any component
   - `reset-rules-panel` event - Clears rules panel state
   - `show-country-rules` event - Displays country rules in Rules panel
   - `airport-click` event - Triggers airport selection and details loading
   - `display-airport-details` event - Displays airport details in right panel

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
    overlays: Map<string, Overlay>; // Map overlays
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
    activeTab: 'details' | 'aip' | 'rules' | 'relevance'; // Active detail tab
  };
  ga: GAState;                      // GA Friendliness state
  rules: RulesState;                // Rules/Regulations state
}
```

#### Store Actions

All state modifications go through store actions:

**Core Actions:**
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

**GA Friendliness Actions:**
- `setGAConfig(config)` - Set GA config from API
- `setGAConfigError(error)` - Set GA config error
- `setGASelectedPersona(personaId)` - Set selected persona
- `setGAScores(scores)` - Set GA scores (batch update) and compute quartiles
- `setGASummary(icao, summary)` - Set GA summary for single airport
- `setGALoading(loading)` - Set GA loading state
- `setGAComputedQuartiles(quartiles)` - Set computed quartile thresholds
- `clearGAScores()` - Clear GA scores

**Rules/Regulations Actions:**
- `setRulesForCountry(countryCode, rules)` - Store rules for a country
- `setRulesSelection(countries, visualFilter)` - Set active countries and visual filter
- `setRulesTextFilter(text)` - Update free-text filter
- `setRuleSectionState(sectionId, expanded)` - Persist expand/collapse state
- `clearRules()` - Clear all rules state

#### Filtering Logic

Client-side filtering is performed in `filterAirports()` function in `store.ts`. Currently implements basic filtering with a TODO to integrate with the shared `FilterEngine` from the Python backend (`shared/filtering/filter_engine.py`).

**Current Implementation:**
- Country filter
- Boolean filters (has_procedures, has_aip_data, has_hard_runway, point_of_entry)
- Additional filters (has_avgas, has_jet_a, runway length, landing fee) are applied on the backend via API

**Future Enhancement:**
- Integration with shared FilterEngine for consistent filtering logic across frontend and backend

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
- `loadBulkProcedureLines(airports, apiAdapter)` - Load procedure lines in bulk for multiple airports
- `clearProcedureLines()` - Clear all procedure lines
- `getRelevanceColor(airport)` - Get color based on GA relevance score and quartiles (private)
- `getNotificationColor(airport)` - Get color based on notification requirements (private)

#### Legend Modes

- **`airport-type`**: Colors by airport characteristics (border crossing, procedures)
- **`procedure-precision`**: Colors by procedure precision (ILS, RNAV, etc.)
- **`runway-length`**: Colors by runway length
- **`country`**: Colors by country
- **`relevance`**: Colors by GA Friendliness relevance score (quartile-based, persona-specific)
- **`notification`**: Colors by notification requirements (H24, hours notice, on request)

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

**Initialization & Core:**
- `init()` - Initialize UI manager
- `updateUI(state)` - Update UI based on state
- `updateFilterControls(filters)` - Sync filter controls with state
- `updateSearchInput(query)` - Update search input
- `updateLoadingState(loading)` - Update loading indicator
- `updateErrorState(error)` - Display error message
- `updateAirportCount(count)` - Update airport count display
- `applyFilters()` - Trigger API call with current filters
- `syncFiltersToUI(filters)` - Public method for LLM to sync filter UI

**Search & Route:**
- `handleSearch(query)` - Handle search input (private)
- `handleRouteSearch(routeAirports)` - Handle route search (private)
- `applyRouteSearch(route)` - Apply route search with current filters (private)
- `applyLocateWithCenter(locate)` - Apply locate search with cached center (private)

**AIP Filtering:**
- `loadAIPFilters()` - Load AIP fields and presets from API
- `wireUpAIPFilters()` - Wire up AIP filter control event listeners
- `handleAIPFieldChange()` - Handle AIP field/operator/value changes
- `applyAIPPreset(preset)` - Apply AIP filter preset
- `clearAIPFilter()` - Clear AIP filter
- `updateActiveAIPFilter(field, operator, value)` - Update active filter display

**Persona/GA Management:**
- `populatePersonaSelector()` - Populate persona selector dropdown from GA config
- `updatePersonaSelectorVisibility(legendMode)` - Update persona selector visibility (now always visible)
- `triggerGAScoresLoad()` - Trigger loading of GA scores for visible airports

### 4. API Adapter (`ts/adapters/api-adapter.ts`)

Handles all communication with the backend API using Fetch API.

#### Endpoints

**Airport Data:**
- `getAirports(filters)` - Get airports with filters
- `getAirportDetail(icao)` - Get airport details
- `searchAirports(query, limit)` - Search airports
- `searchAirportsNearRoute(route, distance, filters)` - Route search
- `locateAirports(query, radius, filters)` - Locate airports
- `locateAirportsByCenter(center, radius, filters)` - Locate by coordinates
- `getAirportProcedures(icao)` - Get airport procedures
- `getAirportRunways(icao)` - Get airport runways
- `getAirportAIPEntries(icao)` - Get AIP entries
- `getBulkProcedureLines(airports, distanceNm)` - Get procedure lines for multiple airports

**Filters & Metadata:**
- `getAllFilters()` - Get available filters metadata
- `getAIPFilterPresets()` - Get AIP filter presets
- `getAvailableAIPFields()` - Get available AIP fields

**Rules/Regulations:**
- `getCountryRules(countryCode)` - Get country rules

**GA Friendliness:**
- `getGAConfig()` - Get GA configuration (features, personas, buckets)
- `getGAPersonas()` - Get list of available personas
- `getGAScores(icaos, persona)` - Get GA scores for multiple airports (max 200)
- `getGASummary(icao, persona)` - Get full GA summary for single airport
- `getGAHealth()` - Check GA service health

### 5. LLM Integration (`ts/adapters/llm-integration.ts`)

Handles chatbot visualizations and filter profile application.

#### Visualization Types

The LLM can return these visualization types:

1. **`markers`**: Display airports as markers
   - Sets airports in store via `store.setAirports()`
   - Applies filter profile if provided
   - Fits map bounds to show all airports
   - Supports `style` field (e.g., "customs") for special highlighting

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
   - Triggers locate search via `trigger-locate` event
   - Shows all airports within radius with highlights on recommended airports

4. **`marker_with_details`**: Focus on specific airport
   - Updates search query in store
   - Triggers search via `trigger-search` event (centers map, shows marker)
   - Triggers `airport-click` event (loads and displays details panel)

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
- Single-airport routes: Supported (for locate-style searches with distance radius)
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

## GA Friendliness State Management

### Overview

The GA (General Aviation) Friendliness system provides persona-based relevance scoring for airports. Scores are pre-computed for all personas and embedded in airport data, with quartile thresholds computed dynamically based on visible airports.

### State Structure

```typescript
interface GAState {
  config: GAConfig | null;              // GA configuration from API
  configLoaded: boolean;                // Whether config has been loaded
  configError: string | null;           // Error loading config
  selectedPersona: string;               // Current persona ID (e.g., 'ifr_touring_sr22')
  scores: Map<string, AirportGAScore>;  // GA scores per airport (ICAO -> score)
  summaries: Map<string, AirportGASummary>; // Full GA summaries per airport
  isLoading: boolean;                    // Loading state
  computedQuartiles: QuartileThresholds | null; // Quartile thresholds for relevance coloring
}
```

### Data Flow

**Initialization:**
```
App starts → PersonaManager.init() → APIAdapter.getGAConfig() → store.setGAConfig()
```

**Persona Selection:**
```
User selects persona → store.setGASelectedPersona() → Quartiles reset → PersonaManager.computeQuartiles()
```

**Score Loading:**
```
Airports displayed → PersonaManager.loadScores(icaos) → APIAdapter.getGAScores() → store.setGAScores()
→ Quartiles computed → store.setGAComputedQuartiles()
```

**Relevance Coloring:**
```
Legend mode = 'relevance' → VisualizationEngine.getRelevanceColor() → 
Uses airport.ga.persona_scores[selectedPersona] → Compares to quartiles → Returns bucket color
```

### Key Concepts

- **Personas**: Pre-defined GA pilot profiles with feature weights (e.g., IFR Touring SR22, VFR Day Trip)
- **Quartiles**: Dynamic thresholds (Q1, Q2, Q3) computed from visible airport scores
- **Relevance Buckets**: Four quartiles (top, second, third, bottom) plus "unknown" for airports without data
- **Embedded Scores**: All persona scores are pre-computed and embedded in `airport.ga.persona_scores`

## Rules/Regulations State Management

### Overview

The Rules system manages country-specific aviation regulations, with support for LLM-provided visual filters and free-text search.

### State Structure

```typescript
interface RulesState {
  allRulesByCountry: Record<string, CountryRules>; // All loaded rules, keyed by ISO country code
  activeCountries: string[];                     // Currently selected countries (display order)
  visualFilter: RulesVisualFilter | null;        // LLM-provided visual filter (categoriesByCountry)
  textFilter: string;                             // Free-text filter from Rules search box
  sectionState: Record<string, boolean>;          // Expand/collapse state per section (sectionId -> expanded)
}
```

### Data Flow

**Loading Rules:**
```
LLM sends 'show-country-rules' event → main.ts loads rules → APIAdapter.getCountryRules() → 
store.setRulesForCountry() → store.setRulesSelection() → Rules panel renders
```

**Visual Filtering:**
```
LLM provides categoriesByCountry → store.setRulesSelection(countries, visualFilter) → 
Rules panel filters to show only specified categories per country
```

**Text Filtering:**
```
User types in Rules search box → store.setRulesTextFilter() → Rules panel re-renders → 
Filters rules by question, answer, tags, category name, country
```

**Section State:**
```
User expands/collapses section → store.setRuleSectionState() → State persisted in localStorage → 
Restored on next render
```

### Key Concepts

- **Visual Filter**: LLM can provide `categoriesByCountry` to show only relevant categories
- **Text Filter**: Free-text search across question, answer, tags, category, and country
- **Section State**: Expand/collapse state persisted per section ID
- **Store-Driven Rendering**: Rules panel renders from centralized store state, not direct API calls

## AIP Filtering System

### Overview

AIP (Aeronautical Information Publication) filtering allows users to filter airports by specific AIP field values using operators (contains, equals, not_empty, starts_with, ends_with).

### Data Flow

**Loading Metadata:**
```
UIManager.init() → loadAIPFilters() → 
APIAdapter.getAvailableAIPFields() + getAIPFilterPresets() → 
Populates field select and preset buttons
```

**Applying Filter:**
```
User selects field/operator/value → handleAIPFieldChange() → store.setFilters() → 
Active filter displayed → API call includes AIP filter parameters
```

**Presets:**
```
User clicks preset button → applyAIPPreset() → Sets field/operator/value → handleAIPFieldChange()
```

### Key Concepts

- **Presets**: Pre-defined common AIP filters (e.g., "Has Customs", "Has Fuel")
- **Operators**: contains, equals, not_empty, starts_with, ends_with
- **Active Filter Display**: Shows current AIP filter in UI when active
- **Backend Filtering**: AIP filters are applied on backend, not client-side

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
