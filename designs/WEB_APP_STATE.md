# Web App State Management

> Zustand store architecture, state structure, actions, and data flow patterns.

## Quick Reference

| File | Purpose |
|------|---------|
| `ts/store/store.ts` | Zustand store definition and actions |
| `ts/store/types.ts` | All TypeScript type definitions |

**Key Exports:**
- `store` - Zustand store instance
- `AppState` - Root state type
- `FilterConfig` - Filter configuration type
- `Airport`, `RouteState`, `LocateState` - Domain types

**Prerequisites:** Read `WEB_APP_ARCHITECTURE.md` first.

---

## State Structure

```typescript
interface AppState {
  // Core data
  airports: Airport[];              // All airports from API
  filteredAirports: Airport[];      // After filtering (derived)
  filters: FilterConfig;            // Current filter settings

  // Map state
  visualization: {
    legendMode: LegendMode;         // Current legend mode
    highlights: Map<string, Highlight>; // Active highlights
    overlays: Map<string, Overlay>; // Map overlays
    showProcedureLines: boolean;    // Procedure lines toggle
    showRoute: boolean;             // Route visibility
  };

  // Search state
  route: RouteState | null;         // Active route search
  locate: LocateState | null;       // Active locate search
  selectedAirport: Airport | null;  // Selected for details
  mapView: MapView;                 // Center and zoom

  // UI state
  ui: {
    loading: boolean;
    error: string | null;
    searchQuery: string;            // Search input value
    activeTab: 'details' | 'aip' | 'rules' | 'relevance';
  };

  // Feature-specific state
  ga: GAState;                      // GA Friendliness
  rules: RulesState;                // Rules/Regulations

  // Authentication
  auth: AuthState;                  // Login state, user info, chat usage
}
```

---

## Key Types

### FilterConfig

```typescript
interface FilterConfig {
  // Location/distance
  country?: string;
  search_radius_nm?: number;        // Default: 50
  enroute_distance_max_nm?: number;

  // Capabilities
  has_procedures?: boolean;
  has_aip_data?: boolean;
  has_hard_runway?: boolean;
  point_of_entry?: boolean;

  // Fuel
  fuel_type?: 'avgas' | 'jet_a';    // Preferred (UI dropdown)
  has_avgas?: boolean;              // Legacy
  has_jet_a?: boolean;              // Legacy

  // Amenities
  hotel?: number;                   // -1=unknown, 0=none, 1=vicinity, 2=at_airport
  restaurant?: number;

  // Runway
  min_runway_length_ft?: number;
  max_runway_length_ft?: number;

  // Other
  max_landing_fee?: number;
  trip_distance?: number;
  exclude_large_airports?: boolean;

  // Notification
  max_hours_notice?: number;
}
```

### GAState

```typescript
interface GAState {
  config: GAConfig | null;              // From API
  configLoaded: boolean;
  configError: string | null;
  selectedPersona: string;              // e.g., 'ifr_touring_sr22'
  scores: Map<string, AirportGAScore>;  // ICAO → score
  summaries: Map<string, AirportGASummary>;
  isLoading: boolean;
  computedQuartiles: QuartileThresholds | null;
}
```

**PersonaManager Workflow:**
```
App starts
    ↓
PersonaManager.init()
    ↓
APIAdapter.getGAConfig() → store.setGAConfig()
    ↓
User selects persona (or default used)
    ↓
store.setGASelectedPersona() → clears computedQuartiles
    ↓
Airports displayed on map
    ↓
PersonaManager.loadScores(visibleICAOs)
    ↓
APIAdapter.getGAScores(icaos, persona) → store.setGAScores()
    ↓
PersonaManager.computeQuartiles() → store.setGAComputedQuartiles()
    ↓
Legend mode = 'relevance' → markers colored by quartile
```

**Quartile computation:** Scores are divided into quartiles (top 25%, second 25%, etc.) based on the visible airports. Thresholds are recomputed when:
- Persona changes
- Visible airports change significantly
- Scores are loaded for new airports

### RulesState

```typescript
interface RulesState {
  allRulesByCountry: Record<string, CountryRules>;
  activeCountries: string[];            // Display order
  visualFilter: RulesVisualFilter | null; // LLM-provided tag filter
  textFilter: string;                   // Free-text search
  sectionState: Record<string, boolean>; // Expand/collapse
}

interface RulesVisualFilter {
  tagsByCountry: Record<string, string[]>;
}
```

### AuthState

```typescript
interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;              // true until /auth/me resolves
  user: AuthUser | null;           // { id, email, name, approved }
  chatUsage: ChatUsageInfo | null; // { used, limit } for daily rate limit
}
```

See `AUTH_USAGE.md` for full auth architecture.

---

## Store Actions

### Core Actions

```typescript
// Airport data
setAirports(airports: Airport[]): void    // Sets airports + auto-filters
setFilters(filters: Partial<FilterConfig>): void  // Updates filters + re-filters

// Map visualization
setLegendMode(mode: LegendMode): void
highlightPoint(highlight: Highlight): void
removeHighlight(id: string): void
clearHighlights(): void

// Search state
setRoute(route: RouteState | null): void
setLocate(locate: LocateState | null): void
selectAirport(airport: Airport | null): void
setMapView(view: MapView): void

// UI state
setLoading(loading: boolean): void
setError(error: string | null): void
setSearchQuery(query: string): void
setActiveTab(tab: string): void

// Reset
clearFilters(): void                      // Resets to defaults
resetState(): void                        // Full reset
```

### GA Friendliness Actions

```typescript
setGAConfig(config: GAConfig): void
setGAConfigError(error: string): void
setGASelectedPersona(personaId: string): void
setGAScores(scores: Map<string, AirportGAScore>): void  // Batch update
setGASummary(icao: string, summary: AirportGASummary): void
setGALoading(loading: boolean): void
setGAComputedQuartiles(quartiles: QuartileThresholds): void
clearGAScores(): void
```

### Rules Actions

```typescript
setRulesForCountry(countryCode: string, rules: CountryRules): void
setRulesSelection(countries: string[], visualFilter?: RulesVisualFilter): void
setRulesTextFilter(text: string): void
setRuleSectionState(sectionId: string, expanded: boolean): void
clearRules(): void
```

### Auth Actions

```typescript
setAuth(user: AuthUser | null, chatUsage?: ChatUsageInfo): void  // Set after /auth/me
setAuthLoading(loading: boolean): void
```

---

## Data Flow Patterns

### Filter Change Flow

```
User toggles filter checkbox
    ↓
UIManager.handleFilterChange()
    ↓
store.setFilters({ has_procedures: true })
    ↓
Store: updates filters, calls filterAirports()
    ↓
Store: updates filteredAirports
    ↓
Subscription fires in main.ts
    ↓
VisualizationEngine.updateMarkers()
    ↓
Map updates with filtered airports
```

### Search Flow

```
User types in search input
    ↓
Input event → store.setSearchQuery() (immediate)
    ↓
Debounced handler (500ms) → handleSearch()
    ↓
Route detection: parseRouteFromQuery()
    ↓
If route: handleRouteSearch()
    - API: searchAirportsNearRoute()
    - store.setAirports() + store.setRoute()
    ↓
If not route: text search
    - API: searchAirports()
    - store.setAirports()
    ↓
Subscription → VisualizationEngine updates
```

### LLM Visualization Flow

```
Chatbot receives ui_payload SSE event
    ↓
ChatbotManager.handleUIPayload()
    ↓
LLMIntegration.applySuggestedLegend(tool, filters)
    ↓
LLMIntegration.handleVisualization(visualization)
    ↓
Routes to handler based on visualization.type:
    - handleMarkers()
    - handleRouteWithMarkers()
    - handlePointWithMarkers()
    - handleMarkerWithDetails()
    ↓
Handler updates store (setAirports, setRoute, highlightPoint, etc.)
    ↓
Subscription → VisualizationEngine/UIManager update
```

---

## Filtering Logic

### Backend vs Client-Side

**Backend Filtering (Authoritative):**
All filtering is done by `FilterEngine` on the server. Both REST API and LangGraph tools use the same engine.

**Client-Side Filtering (Display Only):**
The `filterAirports()` function in store provides immediate UI feedback for basic filters. This is NOT authoritative.

```typescript
// store.ts - Client-side filtering (for immediate display)
function filterAirports(airports: Airport[], filters: FilterConfig): Airport[] {
  return airports.filter(airport => {
    // Country filter
    if (filters.country && airport.country !== filters.country) return false;

    // Boolean filters
    if (filters.has_procedures && !airport.has_procedures) return false;
    if (filters.has_aip_data && !airport.has_aip_data) return false;
    if (filters.has_hard_runway && !airport.has_hard_runway) return false;
    if (filters.point_of_entry && !airport.point_of_entry) return false;

    return true;
  });
}
```

### Backend-Only Filters

These filters require API calls (not available client-side):
- `fuel_type`, `has_avgas`, `has_jet_a`
- `hotel`, `restaurant`
- `min_runway_length_ft`, `max_runway_length_ft`
- `max_landing_fee`
- `trip_distance`, `exclude_large_airports`
- `max_hours_notice`

---

## Subscriptions

### Pattern: Debounced Subscriptions

```typescript
// main.ts
let updateTimeout: number | null = null;

store.subscribe((state, prevState) => {
  // Debounce rapid updates
  if (updateTimeout) clearTimeout(updateTimeout);

  updateTimeout = setTimeout(() => {
    // Check what changed and update accordingly
    if (state.filteredAirports !== prevState.filteredAirports) {
      visualizationEngine.updateMarkers(
        state.filteredAirports,
        state.visualization.legendMode
      );
    }

    if (state.visualization.legendMode !== prevState.visualization.legendMode) {
      uiManager.updateLegendDisplay(state.visualization.legendMode);
    }
  }, 50); // 50ms debounce
});
```

### Pattern: Hash-Based Change Detection

```typescript
// Prevent unnecessary updates by hashing state
function hashState(state: Partial<AppState>): string {
  return JSON.stringify({
    airportCount: state.airports?.length,
    filters: state.filters,
    legendMode: state.visualization?.legendMode,
  });
}

let lastHash = '';
store.subscribe((state) => {
  const hash = hashState(state);
  if (hash === lastHash) return; // No actual change
  lastHash = hash;
  // ... perform updates
});
```

### Debouncing Strategy Summary

| Context | Delay | Rationale |
|---------|-------|-----------|
| Store subscriptions | 50ms | Prevent rapid re-renders during filter changes |
| Search input | 500ms | Allow user to finish typing before API call |
| Distance input | `change` event | Only trigger on blur/Enter, not every keystroke |
| GA score loading | Per-request | Load scores for visible airports, deduplicate requests |

---

## Search Input Synchronization

The search input uses bidirectional sync between DOM and store.

**Source of truth:** Store (`state.ui.searchQuery`)

**User Typing Flow:**
```
User types → Input event → store.setSearchQuery() → Subscription → updateSearchInput() → DOM syncs
```

**Programmatic Updates (display only):**
```typescript
// Just update display - no search triggered
store.getState().setSearchQuery('EGKB LFPG');
```

**Programmatic Updates (with search):**
```typescript
// Update display AND trigger search
store.getState().setSearchQuery(query);
window.dispatchEvent(new CustomEvent('trigger-search', { detail: { query } }));
```

**Key behaviors:**
- Store is always source of truth
- `setSearchQuery()` alone does NOT trigger search
- Use `trigger-search` event to actually perform search
- Geocode cache prevents locate results from being overwritten (see Geocode Cache section)

---

## Distance Values

Distance inputs are stored in the store as part of `FilterConfig`:

```typescript
interface FilterConfig {
  search_radius_nm?: number;        // Default: 50
  enroute_distance_max_nm?: number; // Default: null
}
```

**Flow:**
```
Distance input changed
    ↓
handleFilterChange({ search_radius_nm: value })
    ↓
store.setFilters()
    ↓
If route active: applyRouteSearch() with new distance
If locate active: applyLocateWithCenter() with new distance
    ↓
API call uses distance from store.filters.search_radius_nm
```

**Key Details:**
- Uses `change` event (fires on blur/Enter), not `input` (every keystroke)
- `clearFilters()` resets to defaults (50nm, null)
- All search functions read distance from store, not DOM

---

## Geocode Cache

The geocode cache (`ts/utils/geocode-cache.ts`) prevents text search from overwriting locate results.

**Problem Solved:**
```
Without cache:
1. Chatbot: "airports near Brac, Croatia"
2. trigger-locate → loads 15 airports
3. Search box shows "Brac, Croatia"
4. Debounced search fires (500ms)
5. Text search "Brac, Croatia" → 0 matches
6. Results overwritten ❌

With cache:
1. Chatbot: "airports near Brac, Croatia"
2. trigger-locate → caches "Brac, Croatia" → coords → loads 15 airports
3. Debounced search fires
4. Cache hit → locate search with cached coords
5. Same airports displayed ✅
```

**API:**
```typescript
// Cache a geocode result
geocodeCache.set(searchText, lat, lon, label);

// Check cache before text search
const cached = geocodeCache.get(searchText);
if (cached) {
  // Do locate search with cached.lat, cached.lon
} else {
  // Do text search
}
```

---

## Best Practices

### Do
- Always use store actions to modify state
- Subscribe selectively (check what changed)
- Debounce rapid updates
- Use batch updates for multiple changes (`setGAScores` for many airports)

### Don't
- Mutate state directly
- Store the same data in multiple places
- Skip the store and update components directly
- Trigger API calls from within store actions

---

## Debugging

```javascript
// Browser console
store.getState()                          // Full state
store.getState().airports.length          // Airport count
store.getState().filters                  // Current filters
store.getState().ga.selectedPersona       // Selected GA persona
store.getState().rules.activeCountries    // Active rule countries
```
