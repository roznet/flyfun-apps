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

### 3. Reactive Updates
- **Store Subscriptions**: Components subscribe to store changes
- **Automatic UI Updates**: UI updates automatically when state changes
- **Efficient Rendering**: Only updates what changed (no full re-renders)

### 4. Type Safety
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

Currently uses basic client-side filtering in `filterAirports()` function. This can be enhanced to:
- Call Python FilterEngine via API endpoint
- Port FilterEngine to TypeScript
- Add more filter types (fuel, runway length, landing fees, etc.)

### 2. Visualization Engine (`ts/engines/visualization-engine.ts`)

Manages Leaflet map rendering and all map-related operations.

#### Responsibilities

- **Map Initialization**: Creates and configures Leaflet map
- **Marker Management**: Creates, updates, and removes airport markers
- **Legend Modes**: Applies different marker styles based on legend mode
- **Route Rendering**: Draws route lines and waypoint markers
- **Highlight System**: Manages temporary highlights (e.g., locate center)
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

#### Legend Modes

The visualization engine supports multiple legend modes:

- **`airport-type`**: Colors by airport characteristics (border crossing, procedures)
- **`procedure-precision`**: Colors by procedure precision (ILS, RNAV, etc.)
- **`runway-length`**: Colors by runway length
- **`country`**: Colors by country

To add a new legend mode:
1. Add mode to `LegendMode` type in `types.ts`
2. Add styling logic in `updateMarkers()` method
3. Add UI control in `UIManager`

### 3. UI Manager (`ts/managers/ui-manager.ts`)

Handles all DOM interactions and updates UI based on state changes.

#### Responsibilities

- **Event Listeners**: Attaches event listeners to DOM elements
- **Reactive Updates**: Subscribes to store and updates UI when state changes
- **Filter Controls**: Manages filter UI controls (checkboxes, selects)
- **Search Handling**: Handles search input and triggers searches
- **Loading/Error States**: Displays loading indicators and error messages
- **Airport Details**: Updates airport details panel (placeholder)

#### Key Methods

- `init()` - Initialize UI manager
- `updateUI(state)` - Update UI based on state
- `updateFilterControls(filters)` - Sync filter controls with state
- `updateSearchInput(query)` - Update search input
- `updateLoadingState(loading)` - Update loading indicator
- `updateErrorState(error)` - Display error message
- `updateAirportCount(count)` - Update airport count display

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
- `chat(sessionId, message, history)` - Chat with LLM agent

### 5. LLM Integration (`ts/adapters/llm-integration.ts`)

Handles chatbot visualizations and filter profile application.

#### Visualization Types

The LLM can return different visualization types:

1. **`markers`**: Display airports as markers
   ```typescript
   {
     type: 'markers',
     data: Airport[],
     filter_profile?: FilterConfig
   }
   ```

2. **`route_with_markers`**: Display route with airports
   ```typescript
   {
     type: 'route_with_markers',
     route: { from: {icao, lat, lon}, to: {icao, lat, lon} },
     markers: Airport[],
     filter_profile?: FilterConfig
   }
   ```

3. **`point_with_markers`**: Display point location with airports
   ```typescript
   {
     type: 'point_with_markers',
     point: { lat, lng, label },
     markers: Airport[],
     filter_profile?: FilterConfig
   }
   ```

4. **`marker_with_details`**: Focus on specific airport
   ```typescript
   {
     type: 'marker_with_details',
     marker: { ident, lat, lon, zoom },
     filter_profile?: FilterConfig
   }
   ```

#### Adding New Visualization Types

1. Add type to `VisualizationData` interface in `types.ts`
2. Add handler method in `LLMIntegration` class
3. Update `visualizeData()` method to route to new handler
4. Update `VisualizationEngine` if new map elements needed

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

### LLM Visualization Flow

```
Chatbot sends visualization
  → LLMIntegration.visualizeData() called
  → LLMIntegration routes to appropriate handler
  → Handler calls store.setAirports() or store.setRoute()
  → If filter_profile present, applyFilterProfile() called
  → Store updates state
  → Store subscription fires
  → VisualizationEngine updates map
  → UIManager updates UI
```

## How to Enhance

### Adding a New Filter

1. **Add to FilterConfig** (`ts/store/types.ts`):
   ```typescript
   export interface FilterConfig {
     // ... existing filters
     new_filter?: boolean | string | number;
   }
   ```

2. **Add to API Adapter** (`ts/adapters/api-adapter.ts`):
   ```typescript
   async getAirports(filters: FilterConfig = {}): Promise<AirportsApiResponse> {
     const params = new URLSearchParams();
     // ... existing params
     if (filters.new_filter) params.append('new_filter', filters.new_filter.toString());
     // ...
   }
   ```

3. **Add to Filter Logic** (`ts/store/store.ts`):
   ```typescript
   function filterAirports(airports: Airport[], filters: Partial<FilterConfig>): Airport[] {
     return airports.filter(airport => {
       // ... existing filters
       if (filters.new_filter !== undefined && airport.new_property !== filters.new_filter) {
         return false;
       }
       return true;
     });
   }
   ```

4. **Add UI Control** (`ts/managers/ui-manager.ts`):
   ```typescript
   private initEventListeners(): void {
     // ... existing listeners
     document.getElementById('new-filter')?.addEventListener('change', (e) => {
       const target = e.target as HTMLInputElement;
       this.store.getState().setFilters({ new_filter: target.checked });
       this.applyFilters();
     });
   }
   ```

5. **Add to HTML** (`index.html`):
   ```html
   <input type="checkbox" id="new-filter" />
   <label for="new-filter">New Filter</label>
   ```

### Adding a New LLM Visualization Type

1. **Add to Types** (`ts/store/types.ts`):
   ```typescript
   export interface VisualizationData {
     type: 'markers' | 'route_with_markers' | 'point_with_markers' | 'marker_with_details' | 'new_type';
     // ... existing fields
     new_field?: NewType;
   }
   ```

2. **Add Handler** (`ts/adapters/llm-integration.ts`):
   ```typescript
   private handleNewType(viz: Visualization): boolean {
     // Extract data from visualization
     const data = viz.new_field;
     
     // Update store
     this.store.getState().setAirports(data.airports);
     
     // Apply filter profile if present
     if (viz.filter_profile) {
       this.applyFilterProfile(viz.filter_profile);
     }
     
     return true;
   }
   ```

3. **Route in visualizeData** (`ts/adapters/llm-integration.ts`):
   ```typescript
   public visualizeData(visualization: VisualizationData): void {
     switch (visualization.type) {
       // ... existing cases
       case 'new_type':
         this.handleNewType(visualization);
         break;
     }
   }
   ```

### Adding a New Data Display

1. **Add to AppState** (`ts/store/types.ts`):
   ```typescript
   export interface AppState {
     // ... existing state
     newData: NewDataType[];
   }
   ```

2. **Add Store Action** (`ts/store/store.ts`):
   ```typescript
   interface StoreActions {
     // ... existing actions
     setNewData: (data: NewDataType[]) => void;
   }
   
   // In store implementation:
   setNewData: (data) => {
     set({ newData: data });
   }
   ```

3. **Add UI Rendering** (`ts/managers/ui-manager.ts`):
   ```typescript
   private updateUI(state: AppState): void {
     // ... existing updates
     this.updateNewData(state.newData);
   }
   
   private updateNewData(data: NewDataType[]): void {
     const container = document.getElementById('new-data-container');
     if (container) {
       container.innerHTML = this.renderNewData(data);
     }
   }
   ```

4. **Subscribe to Changes** (`ts/managers/ui-manager.ts`):
   ```typescript
   init(): void {
     // ... existing subscriptions
     this.unsubscribe = this.store.subscribe((state) => {
       // ... existing updates
       if (state.newData !== lastNewData) {
         this.updateNewData(state.newData);
         lastNewData = state.newData;
       }
     });
   }
   ```

### Adding a New Feature

1. **Define State** - Add to `AppState` if needed
2. **Add Store Actions** - Add actions to modify state
3. **Create UI Components** - Add DOM elements and event listeners
4. **Add API Endpoints** - If backend communication needed
5. **Update Visualization** - If map visualization needed
6. **Wire Everything** - Connect components in `main.ts`

## Filter Enhancement Guide

### Current Filtering

Currently uses basic client-side filtering in `filterAirports()` function. This works for simple filters but can be enhanced.

### Option 1: Enhanced Client-Side Filtering

Add more filter logic to `filterAirports()`:

```typescript
function filterAirports(airports: Airport[], filters: Partial<FilterConfig>): Airport[] {
  return airports.filter(airport => {
    // Country filter
    if (filters.country && airport.iso_country !== filters.country) return false;
    
    // Boolean filters
    if (filters.has_procedures !== undefined && airport.has_procedures !== filters.has_procedures) return false;
    if (filters.has_aip_data !== undefined && airport.has_aip_data !== filters.has_aip_data) return false;
    if (filters.has_hard_runway !== undefined && airport.has_hard_runway !== filters.has_hard_runway) return false;
    if (filters.point_of_entry !== undefined && airport.point_of_entry !== filters.point_of_entry) return false;
    
    // Fuel filters
    if (filters.has_avgas !== undefined && airport.has_avgas !== filters.has_avgas) return false;
    if (filters.has_jet_a !== undefined && airport.has_jet_a !== filters.has_jet_a) return false;
    
    // Runway length filters
    if (filters.min_runway_length_ft && airport.longest_runway_length_ft && 
        airport.longest_runway_length_ft < filters.min_runway_length_ft) return false;
    if (filters.max_runway_length_ft && airport.longest_runway_length_ft && 
        airport.longest_runway_length_ft > filters.max_runway_length_ft) return false;
    
    // Landing fee filter
    if (filters.max_landing_fee && airport.landing_fee && 
        airport.landing_fee > filters.max_landing_fee) return false;
    
    // AIP field filters
    if (filters.aip_field && filters.aip_value) {
      // Filter by AIP field value
      // Implementation depends on AIP data structure
    }
    
    return true;
  });
}
```

### Option 2: Python FilterEngine Integration

Create API endpoint that uses Python FilterEngine:

1. **Backend** (`web/server/api/airports.py`):
   ```python
   @router.post("/filter")
   async def filter_airports_endpoint(
       airports: List[Airport],
       filters: FilterConfig
   ):
       from shared.filtering import FilterEngine
       engine = FilterEngine()
       filtered = engine.filter(airports, filters)
       return {"airports": filtered}
   ```

2. **Frontend** (`ts/adapters/api-adapter.ts`):
   ```typescript
   async filterAirports(airports: Airport[], filters: FilterConfig): Promise<Airport[]> {
     const response = await this.request<{airports: Airport[]}>('/api/airports/filter', {
       method: 'POST',
       body: JSON.stringify({ airports, filters }),
     });
     return response.airports;
   }
   ```

3. **Update Store** (`ts/store/store.ts`):
   ```typescript
   setAirports: async (airports) => {
     const currentFilters = get().filters;
     const filtered = await apiAdapter.filterAirports(airports, currentFilters);
     set({ airports, filteredAirports: filtered });
   }
   ```

### Option 3: TypeScript FilterEngine Port

Port the Python FilterEngine to TypeScript for client-side filtering without API calls.

## LLM Visualization Enhancement

### Adding Custom Visualization Styles

1. **Add Style to VisualizationData**:
   ```typescript
   export interface VisualizationData {
     // ... existing fields
     style?: 'customs' | 'fuel' | 'new_style';
   }
   ```

2. **Handle Style in VisualizationEngine**:
   ```typescript
   private createAirportMarker(airport: Airport, legendMode: LegendMode, style?: string): Marker {
     // ... existing logic
     if (style === 'new_style') {
       // Custom styling for this visualization type
       color = '#custom-color';
       radius = 12;
     }
     // ...
   }
   ```

3. **Apply in LLM Integration**:
   ```typescript
   private handleMarkers(viz: Visualization): boolean {
     // ... existing logic
     // Style is automatically passed through to visualization engine
     return true;
   }
   ```

## Performance Considerations

### Debouncing

- **Store Subscriptions**: Debounced to prevent rapid-fire updates
- **Map Events**: Debounced to prevent infinite loops
- **Search Input**: Debounced to prevent excessive API calls

### Efficient Updates

- **Marker Updates**: Only updates changed markers, doesn't clear/recreate all
- **State Comparison**: Compares state hashes before updating
- **Selective Subscriptions**: Only subscribes to relevant state slices

### Optimization Tips

1. **Use Selectors**: Subscribe to specific state slices instead of entire state
2. **Memoization**: Cache expensive computations
3. **Batch Updates**: Group multiple state updates together
4. **Lazy Loading**: Load data only when needed

## Testing

### Unit Testing

Test individual components in isolation:

```typescript
// Example: Test filter function
describe('filterAirports', () => {
  it('filters by country', () => {
    const airports = [/* test data */];
    const filters = { country: 'FR' };
    const result = filterAirports(airports, filters);
    expect(result.every(a => a.iso_country === 'FR')).toBe(true);
  });
});
```

### Integration Testing

Test component interactions:

```typescript
// Example: Test filter application flow
describe('Filter Application', () => {
  it('updates map when filter changes', () => {
    const store = useStore.getState();
    store.setFilters({ country: 'FR' });
    // Verify map markers updated
  });
});
```

## Debugging

### Browser Console

Access components via window:

```javascript
// View current state
window.appState.getState()

// Access components
window.visualizationEngine
window.uiManager
window.llmIntegration

// Manually trigger actions
window.appState.getState().setFilters({ country: 'FR' })
```

### Zustand DevTools

If Redux DevTools extension installed:
- View state changes
- Time-travel through state
- Export/import state

## Common Patterns

### Pattern 1: Adding a New Filter

1. Add to `FilterConfig` type
2. Add to API adapter parameter building
3. Add to `filterAirports()` function
4. Add UI control in `UIManager`
5. Add HTML element

### Pattern 2: Adding a New Map Element

1. Add layer to `VisualizationEngine`
2. Add update method
3. Subscribe to relevant state in `main.ts`
4. Call update method from subscription

### Pattern 3: Adding a New API Endpoint

1. Add method to `APIAdapter`
2. Add types for request/response
3. Call from `UIManager` or `LLMIntegration`
4. Update store with response

## Migration Notes

### From Old JavaScript

The old JavaScript code (`js/` directory) is still present but commented out in `index.html`. To fully migrate:

1. Test all features work with new TypeScript code
2. Remove old JavaScript files
3. Clean up commented code in `index.html`
4. Update any remaining references

### Backward Compatibility

- **API**: No changes to backend API
- **LLM Agent**: No changes to LangChain agent
- **Data Format**: Same data structures

## Best Practices

1. **Always use store actions** - Never modify state directly
2. **Type everything** - Use TypeScript types, avoid `any`
3. **Subscribe selectively** - Only subscribe to needed state slices
4. **Debounce updates** - Prevent rapid-fire updates
5. **Handle errors** - Always catch and display errors
6. **Test incrementally** - Test each feature as you add it

## Troubleshooting

### Infinite Loops

- **Cause**: Store subscription triggers state update which triggers subscription
- **Fix**: Add guards, debouncing, or remove circular updates

### Map Not Updating

- **Cause**: Store not updating or subscription not firing
- **Fix**: Check store actions are called, verify subscriptions

### Type Errors

- **Cause**: Type mismatches or missing types
- **Fix**: Add proper types, use type assertions carefully

### Performance Issues

- **Cause**: Too many updates or inefficient rendering
- **Fix**: Add debouncing, optimize subscriptions, batch updates

## References

- **Zustand Docs**: https://zustand-demo.pmnd.rs/
- **Leaflet Docs**: https://leafletjs.com/
- **TypeScript Docs**: https://www.typescriptlang.org/
- **Vite Docs**: https://vitejs.dev/

