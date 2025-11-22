# State Management Architecture & Refactoring Plan

## Executive Summary

This document proposes a modern, consolidated architecture for filtering, map visualization, and state management that is robust, maintainable, and expandable. The architecture uses reactive state management, separation of concerns, and clean interfaces for UI, API, and LLM chatbot integration.

### Goals

1. **Single Source of Truth**: Unified state object for all application state
2. **Reactive Updates**: State changes automatically update UI and map
3. **Separated Concerns**: Clear boundaries between state, filters, visualization, API, and LLM
4. **Type Safety**: TypeScript or JSDoc types for all state and interfaces
5. **Extensibility**: Easy to add new filters, visualization modes, and features
6. **Testability**: State management logic easily testable in isolation
7. **Performance**: Efficient updates (no unnecessary re-renders/re-maps)

---

## 1. Architecture Overview

### 1.1 Core Principles

**Reactive State Management**:
- State changes trigger automatic updates to dependent systems
- Unidirectional data flow: State → UI/Map
- Immutable state updates (prevents accidental mutations)

**Separation of Concerns**:
- **State Store**: Single source of truth
- **Filter Engine**: Pure functions for filtering logic
- **Visualization Engine**: Handles map rendering based on state
- **API Adapter**: Handles all API communication
- **LLM Integration**: Clean interface for chatbot interactions
- **UI Components**: Reactive to state, dispatch actions

**Extensibility**:
- Plugin-based filter system (register new filters easily)
- Plugin-based visualization modes (register new legend modes)
- Event system for cross-cutting concerns (logging, analytics, etc.)

### 1.2 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Application State Store                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  VisualizationState {                                │  │
│  │    airports: Airport[]                               │  │
│  │    filters: FilterConfig                             │  │
│  │    legendMode: LegendMode                            │  │
│  │    highlights: Map<id, Highlight>                   │  │
│  │    route: RouteState | null                          │  │
│  │    locate: LocateState | null                       │  │
│  │    selectedAirport: Airport | null                   │  │
│  │    mapView: {center, zoom}                           │  │
│  │  }                                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                      ↓ (reactive)                            │
└─────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│  Filter Engine  │  │ Visualization  │  │   UI Manager   │
│  (Pure Logic)   │  │    Engine      │  │  (Reactive)    │
└────────────────┘  └────────────────┘  └────────────────┘
         ↓                    ↓                    ↓
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│  API Adapter   │  │  Map Renderer   │  │  DOM Updates   │
│  (HTTP Client) │  │  (Leaflet)      │  │  (Reactive)     │
└────────────────┘  └────────────────┘  └────────────────┘
         ↓                    ↓
┌────────────────┐  ┌────────────────┐
│  Backend API   │  │  LLM Chatbot   │
│  (FastAPI)     │  │  Integration   │
└────────────────┘  └────────────────┘
```

---

## 2. Core Components

### 2.1 State Store (`StateStore`)

**Purpose**: Single source of truth for all application state.

**Implementation**:
```javascript
class StateStore {
  constructor() {
    this.state = {
      // Airport data
      airports: [],
      filteredAirports: [],
      
      // Filter configuration
      filters: {
        country: null,
        has_procedures: null,
        has_aip_data: null,
        has_hard_runway: null,
        point_of_entry: null,
        aip_field: null,
        aip_value: null,
        aip_operator: 'contains',
        has_avgas: null,
        has_jet_a: null,
        max_runway_length_ft: null,
        min_runway_length_ft: null,
        max_landing_fee: null,
        limit: 1000,
        offset: 0
      },
      
      // Visualization configuration
      visualization: {
        legendMode: 'airport-type',
        highlights: new Map(),  // id → {type, lat, lng, options}
        overlays: new Map(),     // id → overlay object
        showProcedureLines: false,
        showRoute: false
      },
      
      // Route state
      route: {
        airports: null,           // [ICAO, ICAO, ...]
        distance_nm: 50,
        originalRouteAirports: null,
        isChatbotSelection: false,
        chatbotAirports: null
      },
      
      // Locate state
      locate: {
        query: null,
        center: null,              // {lat, lng, label}
        radiusNm: 50
      },
      
      // Selection state
      selectedAirport: null,
      
      // Map view state
      mapView: {
        center: [50.0, 10.0],
        zoom: 5
      },
      
      // UI state
      ui: {
        loading: false,
        error: null,
        searchQuery: '',
        activeTab: 'details'
      }
    };
    
    // Subscribers for reactive updates
    this.subscribers = new Set();
  }
  
  // Get current state (read-only)
  getState() {
    return Object.freeze(JSON.parse(JSON.stringify(this.state)));
  }
  
  // Subscribe to state changes
  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }
  
  // Dispatch action to update state
  dispatch(action) {
    const newState = this.reducer(this.state, action);
    if (newState !== this.state) {
      this.state = newState;
      this.notifySubscribers();
    }
  }
  
  // Reducer function (pure, immutable updates)
  reducer(state, action) {
    switch (action.type) {
      case 'SET_AIRPORTS':
        return {
          ...state,
          airports: action.payload,
          filteredAirports: this.filterAirports(action.payload, state.filters)
        };
        
      case 'SET_FILTERS':
        const newFilters = { ...state.filters, ...action.payload };
        return {
          ...state,
          filters: newFilters,
          filteredAirports: this.filterAirports(state.airports, newFilters)
        };
        
      case 'SET_LEGEND_MODE':
        return {
          ...state,
          visualization: {
            ...state.visualization,
            legendMode: action.payload
          }
        };
        
      case 'HIGHLIGHT_POINT':
        const highlights = new Map(state.visualization.highlights);
        highlights.set(action.payload.id, action.payload);
        return {
          ...state,
          visualization: {
            ...state.visualization,
            highlights
          }
        };
        
      // ... more actions
        
      default:
        return state;
    }
  }
  
  // Helper: Filter airports using FilterEngine
  filterAirports(airports, filters) {
    const filterEngine = new FilterEngine();
    return filterEngine.apply(airports, filters);
  }
  
  // Notify all subscribers
  notifySubscribers() {
    this.subscribers.forEach(callback => {
      callback(this.getState());
    });
  }
}
```

**Key Features**:
- Immutable state updates
- Reactive subscriptions
- Pure reducer functions
- Type-safe actions
- Single source of truth

### 2.2 Filter Engine (`FilterEngine`)

**Purpose**: Pure filtering logic, reusable across tools, API, and frontend.

**Implementation**:
```javascript
class FilterEngine {
  constructor(context = null) {
    this.context = context;  // ToolContext for enrichment data
    this.registry = new FilterRegistry();
  }
  
  // Apply filters to airports
  apply(airports, filters) {
    if (!filters || Object.keys(filters).length === 0) {
      return airports;
    }
    
    return airports.filter(airport => {
      return Object.entries(filters).every(([name, value]) => {
        if (value === null || value === undefined) {
          return true;  // Filter not set
        }
        
        const filter = this.registry.get(name);
        if (!filter) {
          console.warn(`Unknown filter: ${name}`);
          return true;  // Unknown filter, don't exclude
        }
        
        return filter.apply(airport, value, this.context);
      });
    });
  }
  
  // Get available filters
  getAvailableFilters() {
    return this.registry.listAll();
  }
  
  // Register new filter
  registerFilter(filter) {
    this.registry.register(filter);
  }
}

// Filter Registry (same as existing, but can be extended)
class FilterRegistry {
  static _filters = new Map();
  
  static register(filter) {
    this._filters.set(filter.name, filter);
  }
  
  static get(name) {
    return this._filters.get(name);
  }
  
  static listAll() {
    return Array.from(this._filters.keys());
  }
}
```

**Key Features**:
- Pure functions (no side effects)
- Reusable across tools, API, frontend
- Extensible (register new filters)
- Context-aware (enrichment data support)

### 2.3 Visualization Engine (`VisualizationEngine`)

**Purpose**: Handles map rendering based on state, manages legend modes, highlights, overlays.

**Implementation**:
```javascript
class VisualizationEngine {
  constructor(map, stateStore) {
    this.map = map;  // Leaflet map instance
    this.stateStore = stateStore;
    
    // Leaflet layers
    this.airportLayer = L.layerGroup().addTo(this.map);
    this.procedureLayer = L.layerGroup().addTo(this.map);
    this.routeLayer = L.layerGroup().addTo(this.map);
    this.highlightLayer = L.layerGroup().addTo(this.map);
    this.overlayLayer = L.layerGroup().addTo(this.map);
    
    // Marker storage
    this.markers = new Map();  // ICAO → {marker, airport, icon}
    
    // Subscribe to state changes
    this.unsubscribe = stateStore.subscribe((state) => {
      this.render(state);
    });
  }
  
  // Main render function (called on state changes)
  render(state) {
    // Update markers based on filtered airports
    this.updateMarkers(state.filteredAirports, state.visualization.legendMode);
    
    // Update highlights
    this.updateHighlights(state.visualization.highlights);
    
    // Update overlays
    this.updateOverlays(state.visualization.overlays);
    
    // Update route
    if (state.route.airports) {
      this.renderRoute(state.route);
    }
    
    // Update procedure lines
    if (state.visualization.showProcedureLines) {
      this.renderProcedureLines(state.filteredAirports);
    }
    
    // Update map view
    this.updateMapView(state.mapView);
  }
  
  // Update markers (efficient: only update changed markers)
  updateMarkers(airports, legendMode) {
    const currentIcaos = new Set(this.markers.keys());
    const newIcaos = new Set(airports.map(a => a.ident));
    
    // Remove markers not in new list
    currentIcaos.forEach(icao => {
      if (!newIcaos.has(icao)) {
        this.removeMarker(icao);
      }
    });
    
    // Add/update markers
    airports.forEach(airport => {
      if (this.markers.has(airport.ident)) {
        // Update existing marker (e.g., legend mode changed)
        this.updateMarker(airport, legendMode);
      } else {
        // Add new marker
        this.addMarker(airport, legendMode);
      }
    });
  }
  
  // Add marker (with icon based on legend mode)
  addMarker(airport, legendMode) {
    const {icon, color, radius} = this.getMarkerStyle(airport, legendMode);
    
    const marker = L.marker([airport.latitude_deg, airport.longitude_deg], {
      icon
    });
    
    marker.bindPopup(this.createPopup(airport));
    marker.on('click', () => {
      this.stateStore.dispatch({
        type: 'SELECT_AIRPORT',
        payload: airport
      });
    });
    
    marker.addTo(this.airportLayer);
    
    this.markers.set(airport.ident, {
      marker,
      airport,
      icon,
      color,
      radius
    });
  }
  
  // Update marker appearance (without recreating)
  updateMarker(airport, legendMode) {
    const entry = this.markers.get(airport.ident);
    if (!entry) return;
    
    const {icon, color, radius} = this.getMarkerStyle(airport, legendMode);
    
    // Only update if style changed
    if (entry.color !== color || entry.radius !== radius) {
      entry.marker.setIcon(icon);
      entry.color = color;
      entry.radius = radius;
    }
  }
  
  // Get marker style based on legend mode
  getMarkerStyle(airport, legendMode) {
    const styleEngine = new LegendModeStyleEngine();
    return styleEngine.getStyle(airport, legendMode);
  }
  
  // Highlight management
  updateHighlights(highlights) {
    // Remove highlights not in state
    this.highlightLayer.eachLayer(layer => {
      const id = layer.options.id;
      if (!highlights.has(id)) {
        this.highlightLayer.removeLayer(layer);
      }
    });
    
    // Add/update highlights
    highlights.forEach((highlight, id) => {
      if (!this.highlightLayer.getLayer(id)) {
        this.addHighlight(highlight);
      }
    });
  }
  
  addHighlight(highlight) {
    const marker = L.circleMarker([highlight.lat, highlight.lng], {
      radius: highlight.radius || 15,
      fillColor: highlight.color || '#ff0000',
      color: '#fff',
      weight: 3,
      opacity: 1,
      fillOpacity: 0.7,
      id: highlight.id
    });
    
    if (highlight.popup) {
      marker.bindPopup(highlight.popup);
    }
    
    marker.addTo(this.highlightLayer);
  }
  
  // ... more visualization methods
}
```

**Key Features**:
- Reactive to state changes
- Efficient updates (only update changed markers)
- In-place marker updates (no clearing/recreating)
- Separate layers for different visualization types
- Extensible legend mode system

### 2.4 API Adapter (`APIAdapter`)

**Purpose**: Clean interface for all API communication, handles request/response transformation.

**Implementation**:
```javascript
class APIAdapter {
  constructor(baseURL = '') {
    this.baseURL = baseURL;
    this.client = new APIClient(baseURL);
  }
  
  // Get airports with filters
  async getAirports(filters) {
    // Transform filters to API format
    const params = this.transformFiltersToParams(filters);
    const response = await this.client.get('/api/airports', { params });
    
    // Transform response to standard format
    return this.transformResponse(response);
  }
  
  // Search airports near route
  async searchAirportsNearRoute(routeAirports, distanceNm, filters) {
    const params = {
      airports: routeAirports.join(','),
      segment_distance_nm: distanceNm,
      ...this.transformFiltersToParams(filters)
    };
    
    const response = await this.client.get('/api/airports/route-search', { params });
    return this.transformRouteResponse(response);
  }
  
  // Locate airports
  async locateAirports(query, radiusNm, filters) {
    const params = {
      q: query,
      radius_nm: radiusNm,
      ...this.transformFiltersToParams(filters)
    };
    
    const response = await this.client.get('/api/airports/locate', { params });
    return this.transformLocateResponse(response);
  }
  
  // Transform filters to API parameters
  transformFiltersToParams(filters) {
    const params = {};
    
    // Map filter names to API parameter names
    if (filters.country) params.country = filters.country;
    if (filters.has_procedures === true) params.has_procedures = 'true';
    if (filters.has_aip_data === true) params.has_aip_data = 'true';
    if (filters.has_hard_runway === true) params.has_hard_runway = 'true';
    if (filters.point_of_entry === true) params.point_of_entry = 'true';
    if (filters.has_avgas === true) params.has_avgas = 'true';
    if (filters.has_jet_a === true) params.has_jet_a = 'true';
    if (filters.max_runway_length_ft) params.max_runway_length_ft = filters.max_runway_length_ft;
    if (filters.min_runway_length_ft) params.min_runway_length_ft = filters.min_runway_length_ft;
    if (filters.max_landing_fee) params.max_landing_fee = filters.max_landing_fee;
    if (filters.limit) params.limit = filters.limit;
    if (filters.offset) params.offset = filters.offset;
    
    return params;
  }
  
  // Transform API response to standard format
  transformResponse(response) {
    // Standardize response format
    return {
      airports: Array.isArray(response) ? response : response.airports || [],
      count: response.count || response.length || 0,
      filters_applied: response.filters_applied || {},
      filter_profile: response.filter_profile || {},
      visualization: response.visualization || null
    };
  }
  
  // ... more transformation methods
}
```

**Key Features**:
- Clean interface (hides API details)
- Request/response transformation
- Consistent response format
- Error handling
- Type-safe (with TypeScript)

### 2.5 LLM Integration (`LLMIntegration`)

**Purpose**: Clean interface for chatbot interactions, handles visualization data.

**Implementation**:
```javascript
class LLMIntegration {
  constructor(stateStore, visualizationEngine) {
    this.stateStore = stateStore;
    this.visualizationEngine = visualizationEngine;
  }
  
  // Handle chatbot visualization
  handleVisualization(visualization) {
    if (!visualization || !visualization.type) {
      return;
    }
    
    switch (visualization.type) {
      case 'markers':
        this.handleMarkers(visualization);
        break;
      case 'route_with_markers':
        this.handleRouteWithMarkers(visualization);
        break;
      case 'marker_with_details':
        this.handleMarkerWithDetails(visualization);
        break;
      case 'point_with_markers':
        this.handlePointWithMarkers(visualization);
        break;
      default:
        console.warn(`Unknown visualization type: ${visualization.type}`);
    }
  }
  
  // Handle markers visualization
  handleMarkers(visualization) {
    const airports = visualization.data || visualization.markers || [];
    
    // Update state with airports
    this.stateStore.dispatch({
      type: 'SET_AIRPORTS',
      payload: airports
    });
    
    // Apply filter profile if provided
    if (visualization.filter_profile) {
      this.applyFilterProfile(visualization.filter_profile);
    }
  }
  
  // Handle route with markers
  handleRouteWithMarkers(visualization) {
    const route = visualization.route;
    const airports = visualization.markers || [];
    
    // Set route state
    this.stateStore.dispatch({
      type: 'SET_ROUTE',
      payload: {
        airports: [route.from.icao, route.to.icao],
        distance_nm: 50,  // Default or from visualization
        originalRouteAirports: [
          {icao: route.from.icao, lat: route.from.lat, lng: route.from.lng},
          {icao: route.to.icao, lat: route.to.lat, lng: route.to.lng}
        ],
        isChatbotSelection: true,
        chatbotAirports: airports
      }
    });
    
    // Set airports
    this.stateStore.dispatch({
      type: 'SET_AIRPORTS',
      payload: airports
    });
    
    // Apply filter profile
    if (visualization.filter_profile) {
      this.applyFilterProfile(visualization.filter_profile);
    }
  }
  
  // Apply filter profile from chatbot
  applyFilterProfile(filterProfile) {
    const filters = {};
    
    // Map filter profile to filter state
    if (filterProfile.country) filters.country = filterProfile.country;
    if (filterProfile.has_procedures) filters.has_procedures = true;
    if (filterProfile.has_aip_data) filters.has_aip_data = true;
    if (filterProfile.has_hard_runway) filters.has_hard_runway = true;
    if (filterProfile.point_of_entry) filters.point_of_entry = true;
    if (filterProfile.has_avgas) filters.has_avgas = true;
    if (filterProfile.has_jet_a) filters.has_jet_a = true;
    if (filterProfile.max_runway_length_ft) filters.max_runway_length_ft = filterProfile.max_runway_length_ft;
    if (filterProfile.min_runway_length_ft) filters.min_runway_length_ft = filterProfile.min_runway_length_ft;
    if (filterProfile.max_landing_fee) filters.max_landing_fee = filterProfile.max_landing_fee;
    
    // Update filters in state
    this.stateStore.dispatch({
      type: 'SET_FILTERS',
      payload: filters
    });
    
    // Update UI controls (if needed)
    this.syncFiltersToUI(filters);
  }
  
  // Sync filters to UI controls
  syncFiltersToUI(filters) {
    // Update DOM controls to match filter state
    if (filters.country) {
      const select = document.getElementById('country-filter');
      if (select) select.value = filters.country;
    }
    
    if (filters.has_procedures) {
      const checkbox = document.getElementById('has-procedures');
      if (checkbox) checkbox.checked = true;
    }
    
    // ... update other controls
  }
}
```

**Key Features**:
- Clean interface for chatbot
- Handles all visualization types
- Applies filter profiles automatically
- Syncs with UI controls
- State-driven (updates state, visualization engine reacts)

### 2.6 UI Manager (`UIManager`)

**Purpose**: Reactive UI updates based on state, handles user interactions.

**Implementation**:
```javascript
class UIManager {
  constructor(stateStore) {
    this.stateStore = stateStore;
    
    // Subscribe to state changes
    this.unsubscribe = stateStore.subscribe((state) => {
      this.updateUI(state);
    });
    
    // Initialize event listeners
    this.initEventListeners();
  }
  
  // Update UI based on state
  updateUI(state) {
    // Update filter controls
    this.updateFilterControls(state.filters);
    
    // Update search input
    this.updateSearchInput(state.ui.searchQuery);
    
    // Update loading state
    this.updateLoadingState(state.ui.loading);
    
    // Update error state
    this.updateErrorState(state.ui.error);
    
    // Update airport details panel
    if (state.selectedAirport) {
      this.updateAirportDetails(state.selectedAirport);
    }
  }
  
  // Initialize event listeners
  initEventListeners() {
    // Filter controls
    document.getElementById('country-filter')?.addEventListener('change', (e) => {
      this.stateStore.dispatch({
        type: 'SET_FILTERS',
        payload: { country: e.target.value || null }
      });
    });
    
    document.getElementById('has-procedures')?.addEventListener('change', (e) => {
      this.stateStore.dispatch({
        type: 'SET_FILTERS',
        payload: { has_procedures: e.target.checked || null }
      });
    });
    
    // Search input
    document.getElementById('search-input')?.addEventListener('input', (e) => {
      this.stateStore.dispatch({
        type: 'SET_SEARCH_QUERY',
        payload: e.target.value
      });
    });
    
    // Legend mode
    document.getElementById('legend-mode-filter')?.addEventListener('change', (e) => {
      this.stateStore.dispatch({
        type: 'SET_LEGEND_MODE',
        payload: e.target.value
      });
    });
    
    // Apply filters button
    document.getElementById('apply-filters')?.addEventListener('click', () => {
      this.applyFilters();
    });
  }
  
  // Apply filters (trigger API call)
  async applyFilters() {
    const state = this.stateStore.getState();
    
    this.stateStore.dispatch({ type: 'SET_LOADING', payload: true });
    
    try {
      const apiAdapter = new APIAdapter();
      const response = await apiAdapter.getAirports(state.filters);
      
      this.stateStore.dispatch({
        type: 'SET_AIRPORTS',
        payload: response.airports
      });
      
      this.stateStore.dispatch({ type: 'SET_LOADING', payload: false });
    } catch (error) {
      this.stateStore.dispatch({
        type: 'SET_ERROR',
        payload: error.message
      });
      this.stateStore.dispatch({ type: 'SET_LOADING', payload: false });
    }
  }
  
  // Update filter controls to match state
  updateFilterControls(filters) {
    const countrySelect = document.getElementById('country-filter');
    if (countrySelect) countrySelect.value = filters.country || '';
    
    const hasProcedures = document.getElementById('has-procedures');
    if (hasProcedures) hasProcedures.checked = filters.has_procedures === true;
    
    // ... update other controls
  }
}
```

**Key Features**:
- Reactive to state changes
- Handles user interactions
- Dispatches actions to state store
- Updates UI based on state
- Clean separation from business logic

---

## 3. Integration Points

### 3.1 State → Visualization Flow

```
State Change (dispatch action)
  ↓
State Store updates state
  ↓
Visualization Engine (subscribed) receives new state
  ↓
Visualization Engine renders changes to map
  ↓
Map updates (markers, highlights, overlays, etc.)
```

### 3.2 User Interaction → State Flow

```
User clicks filter control
  ↓
UI Manager event listener
  ↓
Dispatch action to State Store
  ↓
State Store updates state
  ↓
State Store notifies subscribers
  ↓
Visualization Engine updates map
  ↓
UI Manager updates other UI elements
```

### 3.3 API → State Flow

```
User triggers API call (e.g., apply filters)
  ↓
UI Manager calls API Adapter
  ↓
API Adapter makes HTTP request
  ↓
API Adapter transforms response
  ↓
UI Manager dispatches action with response data
  ↓
State Store updates state with airports
  ↓
Visualization Engine renders airports on map
```

### 3.4 LLM → State Flow

```
Chatbot returns visualization data
  ↓
LLM Integration receives visualization
  ↓
LLM Integration dispatches actions to State Store
  ↓
State Store updates state (airports, route, filters)
  ↓
Visualization Engine renders visualization
  ↓
UI Manager updates UI controls
```

---

## 4. Migration Plan

### Phase 1: Foundation (Week 1-2)

**Goal**: Set up core architecture without breaking existing functionality.

**Tasks**:
1. Create `StateStore` class
2. Create `FilterEngine` wrapper (use existing FilterEngine)
3. Create `APIAdapter` class
4. Create basic `VisualizationEngine` skeleton
5. Create `UIManager` skeleton
6. **Parallel implementation**: Run new system alongside old system
7. Add feature flag to switch between old/new system

**Deliverables**:
- Core classes implemented
- Feature flag system
- Basic state management working
- No breaking changes to existing functionality

### Phase 2: State Migration (Week 3-4)

**Goal**: Migrate state management to new system.

**Tasks**:
1. Migrate filter state to StateStore
2. Migrate airport list state to StateStore
3. Migrate route state to StateStore
4. Migrate legend mode state to StateStore
5. Update FilterManager to use StateStore
6. Update AirportMap to use StateStore
7. Test state synchronization

**Deliverables**:
- All state in StateStore
- Old state management code marked as deprecated
- State synchronization working correctly

### Phase 3: Visualization Migration (Week 5-6)

**Goal**: Migrate map visualization to VisualizationEngine.

**Tasks**:
1. Implement marker management in VisualizationEngine
2. Implement highlight system
3. Implement overlay system
4. Implement legend mode updates (in-place, no clearing)
5. Migrate AirportMap to use VisualizationEngine
6. Remove old marker management code

**Deliverables**:
- VisualizationEngine fully functional
- Efficient marker updates (no clearing/recreating)
- Highlight system working
- Overlay system working

### Phase 4: API Integration (Week 7)

**Goal**: Migrate API calls to APIAdapter.

**Tasks**:
1. Implement all API methods in APIAdapter
2. Standardize response formats
3. Update UI Manager to use APIAdapter
4. Remove old API client code
5. Test all API endpoints

**Deliverables**:
- All API calls through APIAdapter
- Consistent response formats
- Error handling improved

### Phase 5: LLM Integration (Week 8)

**Goal**: Migrate chatbot integration to LLMIntegration.

**Tasks**:
1. Implement LLMIntegration class
2. Migrate visualization handling
3. Migrate filter profile application
4. Update chatbot.js to use LLMIntegration
5. Remove old chat-map-integration code

**Deliverables**:
- Clean LLM integration
- Filter profile sync working
- All visualization types supported

### Phase 6: UI Migration (Week 9)

**Goal**: Migrate UI updates to UIManager.

**Tasks**:
1. Implement all UI update methods
2. Migrate event listeners
3. Remove old UI update code
4. Test all user interactions

**Deliverables**:
- All UI updates reactive to state
- Clean event handling
- No direct DOM manipulation outside UIManager

### Phase 7: Cleanup & Optimization (Week 10)

**Goal**: Remove old code, optimize, add tests.

**Tasks**:
1. Remove deprecated code
2. Add unit tests for state management
3. Add integration tests
4. Performance optimization
5. Documentation
6. Code review

**Deliverables**:
- Clean codebase
- Tests passing
- Performance benchmarks met
- Documentation complete

---

## 5. Implementation Details

### 5.1 Type Safety

**Option 1: TypeScript**
```typescript
interface VisualizationState {
  airports: Airport[];
  filteredAirports: Airport[];
  filters: FilterConfig;
  visualization: VisualizationConfig;
  route: RouteState | null;
  locate: LocateState | null;
  selectedAirport: Airport | null;
  mapView: MapView;
  ui: UIState;
}

interface FilterConfig {
  country: string | null;
  has_procedures: boolean | null;
  // ... more filters
}

type Action = 
  | { type: 'SET_AIRPORTS'; payload: Airport[] }
  | { type: 'SET_FILTERS'; payload: Partial<FilterConfig> }
  | { type: 'SET_LEGEND_MODE'; payload: LegendMode }
  // ... more actions
```

**Option 2: JSDoc Types** (if not using TypeScript)
```javascript
/**
 * @typedef {Object} VisualizationState
 * @property {Airport[]} airports
 * @property {Airport[]} filteredAirports
 * @property {FilterConfig} filters
 * @property {VisualizationConfig} visualization
 * @property {RouteState|null} route
 * @property {LocateState|null} locate
 * @property {Airport|null} selectedAirport
 * @property {MapView} mapView
 * @property {UIState} ui
 */
```

### 5.2 Performance Optimizations

**Memoization**:
```javascript
class StateStore {
  constructor() {
    // ... existing code ...
    this.memoizedFilteredAirports = null;
    this.lastFiltersHash = null;
  }
  
  filterAirports(airports, filters) {
    const filtersHash = JSON.stringify(filters);
    
    // Return memoized result if filters haven't changed
    if (this.memoizedFilteredAirports && this.lastFiltersHash === filtersHash) {
      return this.memoizedFilteredAirports;
    }
    
    // Compute filtered airports
    const filtered = this.filterEngine.apply(airports, filters);
    
    // Memoize result
    this.memoizedFilteredAirports = filtered;
    this.lastFiltersHash = filtersHash;
    
    return filtered;
  }
}
```

**Debounced Updates**:
```javascript
class VisualizationEngine {
  constructor(map, stateStore) {
    // ... existing code ...
    this.updateTimeout = null;
  }
  
  render(state) {
    // Debounce rapid state changes
    if (this.updateTimeout) {
      clearTimeout(this.updateTimeout);
    }
    
    this.updateTimeout = setTimeout(() => {
      this.doRender(state);
    }, 16);  // ~60fps
  }
}
```

**Batch Marker Updates**:
```javascript
updateMarkers(airports, legendMode) {
  // Batch DOM updates
  const fragment = document.createDocumentFragment();
  
  // ... compute changes ...
  
  // Apply all changes at once
  requestAnimationFrame(() => {
    // Apply marker updates
  });
}
```

### 5.3 Error Handling

```javascript
class StateStore {
  dispatch(action) {
    try {
      const newState = this.reducer(this.state, action);
      if (newState !== this.state) {
        this.state = newState;
        this.notifySubscribers();
      }
    } catch (error) {
      console.error('State update error:', error);
      this.dispatch({
        type: 'SET_ERROR',
        payload: error.message
      });
    }
  }
}
```

### 5.4 State Persistence

```javascript
class StateStore {
  // Save state to localStorage
  saveToLocalStorage() {
    const serializable = {
      filters: this.state.filters,
      visualization: {
        legendMode: this.state.visualization.legendMode
      },
      mapView: this.state.mapView
    };
    
    localStorage.setItem('appState', JSON.stringify(serializable));
  }
  
  // Load state from localStorage
  loadFromLocalStorage() {
    const saved = localStorage.getItem('appState');
    if (saved) {
      const state = JSON.parse(saved);
      this.dispatch({ type: 'RESTORE_STATE', payload: state });
    }
  }
  
  // Save state to URL
  saveToURL() {
    const params = new URLSearchParams();
    
    // Serialize filters
    Object.entries(this.state.filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        params.set(key, String(value));
      }
    });
    
    // Serialize visualization
    params.set('legend', this.state.visualization.legendMode);
    
    // Update URL
    window.history.replaceState({}, '', `?${params.toString()}`);
  }
}
```

---

## 6. Testing Strategy

### 6.1 Unit Tests

**State Store Tests**:
```javascript
describe('StateStore', () => {
  it('should update state when action dispatched', () => {
    const store = new StateStore();
    store.dispatch({ type: 'SET_FILTERS', payload: { country: 'FR' } });
    
    const state = store.getState();
    expect(state.filters.country).toBe('FR');
  });
  
  it('should notify subscribers on state change', () => {
    const store = new StateStore();
    const callback = jest.fn();
    store.subscribe(callback);
    
    store.dispatch({ type: 'SET_FILTERS', payload: { country: 'FR' } });
    
    expect(callback).toHaveBeenCalled();
  });
});
```

**Filter Engine Tests**:
```javascript
describe('FilterEngine', () => {
  it('should filter airports by country', () => {
    const engine = new FilterEngine();
    const airports = [
      { ident: 'EGTF', iso_country: 'GB' },
      { ident: 'LFPG', iso_country: 'FR' }
    ];
    
    const filtered = engine.apply(airports, { country: 'FR' });
    
    expect(filtered).toHaveLength(1);
    expect(filtered[0].ident).toBe('LFPG');
  });
});
```

### 6.2 Integration Tests

**State → Visualization Flow**:
```javascript
describe('State to Visualization Integration', () => {
  it('should update map when airports change', () => {
    const store = new StateStore();
    const map = createMockMap();
    const engine = new VisualizationEngine(map, store);
    
    store.dispatch({
      type: 'SET_AIRPORTS',
      payload: [{ ident: 'EGTF', latitude_deg: 51.348, longitude_deg: -0.559 }]
    });
    
    expect(map.addMarker).toHaveBeenCalled();
  });
});
```

### 6.3 E2E Tests

**User Interaction Flow**:
```javascript
describe('Filter Application E2E', () => {
  it('should filter airports when user selects country', async () => {
    // Setup
    const page = await setupPage();
    
    // User action
    await page.select('#country-filter', 'FR');
    await page.click('#apply-filters');
    
    // Assert
    await page.waitForSelector('.airport-marker');
    const markers = await page.$$('.airport-marker');
    expect(markers.length).toBeGreaterThan(0);
  });
});
```

---

## 7. Benefits of New Architecture

### 7.1 Maintainability

- **Single Source of Truth**: All state in one place
- **Clear Separation**: Each component has a single responsibility
- **Type Safety**: TypeScript/JSDoc prevents errors
- **Testable**: Pure functions easy to test

### 7.2 Extensibility

- **Plugin System**: Easy to add new filters, legend modes
- **Event System**: Cross-cutting concerns (logging, analytics)
- **Modular**: Components can be replaced/upgraded independently

### 7.3 Performance

- **Efficient Updates**: Only update what changed
- **Memoization**: Avoid redundant computations
- **Debouncing**: Smooth UI updates
- **Batch Operations**: Minimize DOM/Leaflet operations

### 7.4 Developer Experience

- **Clear Data Flow**: Easy to understand and debug
- **Predictable**: State changes are explicit and traceable
- **Tooling**: Can add Redux DevTools-like debugging
- **Documentation**: Self-documenting through types

---

## 8. Next Steps

1. **Review & Approve**: Review this architecture with team
2. **Create Implementation Branch**: Set up feature branch
3. **Start Phase 1**: Begin foundation work
4. **Incremental Migration**: Migrate piece by piece
5. **Continuous Testing**: Test after each phase
6. **Documentation**: Document as we go

---

## 9. Open Questions

1. **TypeScript Migration**: Should we migrate to TypeScript now or later?
2. **State Persistence**: What level of state should be persisted?
3. **Performance Targets**: What are acceptable performance benchmarks?
4. **Backward Compatibility**: How long to maintain old code?
5. **Feature Flags**: Which feature flag system to use?

---

## 10. Implementation Decisions & Alternatives

### 10.1 TypeScript vs JavaScript

**Recommendation: Use TypeScript** ✅

**Why TypeScript?**:
- **Type Safety**: Catches errors at compile time (not runtime)
- **Better IDE Support**: Autocomplete, refactoring, navigation
- **Self-Documenting**: Types serve as documentation
- **Easier Refactoring**: Rename/restructure with confidence
- **Modern Standard**: Industry standard for large JavaScript projects
- **Gradual Migration**: Can migrate incrementally (`.ts` and `.js` can coexist)

**Current State**:
- Existing codebase: Pure JavaScript
- Python backend (type hints available)
- No TypeScript tooling set up

**Migration Strategy**:
1. **Option A: Gradual Migration** (Recommended)
   - Keep existing `.js` files
   - Write new code in `.ts`
   - Convert files incrementally
   - Add `// @ts-check` to `.js` files for basic checking
   - **Pros**: No breaking changes, incremental migration
   - **Cons**: Mixed codebase temporarily

2. **Option B: Full Migration Now**
   - Convert all `.js` to `.ts` before refactoring
   - **Pros**: Clean slate, consistent codebase
   - **Cons**: Large upfront effort, delays refactoring

**Recommendation**: **Option A** - Use TypeScript for new architecture code, migrate existing files incrementally.

**Setup Required**:
```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "lib": ["ES2020", "DOM"],
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "moduleResolution": "node",
    "resolveJsonModule": true,
    "noEmit": true,
    "allowJs": true,
    "checkJs": false  // Gradually enable
  },
  "include": ["web/client/js/**/*"],
  "exclude": ["node_modules"]
}
```

**Alternatives to TypeScript**:
- **JSDoc with `@ts-check`**: Type checking without compilation
  - **Pros**: No build step, works with existing JS
  - **Cons**: Limited type safety, no advanced features
- **Flow**: Facebook's type system
  - **Pros**: Similar to TypeScript
  - **Cons**: Less popular, smaller ecosystem
- **Pure JavaScript with Tests**: Rely on tests for safety
  - **Pros**: No new tools needed
  - **Cons**: Runtime errors only, no compile-time safety

### 10.2 State Management Approach

**Current Recommendation: Custom StateStore (Redux-like pattern)**

**Alternatives**:

1. **Redux Toolkit** (Industry Standard)
   ```javascript
   import { createSlice, configureStore } from '@reduxjs/toolkit';
   
   const visualizationSlice = createSlice({
     name: 'visualization',
     initialState: { airports: [], filters: {} },
     reducers: {
       setAirports: (state, action) => {
         state.airports = action.payload;
       }
     }
   });
   
   const store = configureStore({
     reducer: { visualization: visualizationSlice.reducer }
   });
   ```
   
   **Pros**:
   - Battle-tested, industry standard
   - Excellent DevTools
   - Large ecosystem
   - Good documentation
   
   **Cons**:
   - Additional dependency (~30KB)
   - Learning curve
   - May be overkill for this use case
   
   **Verdict**: Good choice if you want proven patterns, but adds complexity.

2. **Zustand** (Lightweight Alternative)
   ```javascript
   import create from 'zustand';
   
   const useStore = create((set) => ({
     airports: [],
     setAirports: (airports) => set({ airports })
   }));
   ```
   
   **Pros**:
   - Very lightweight (~1KB)
   - Simple API
   - No boilerplate
   - Good TypeScript support
   
   **Cons**:
   - Less mature than Redux
   - Smaller ecosystem
   
   **Verdict**: Excellent choice for simpler state management needs.

3. **Custom StateStore** (Current Recommendation)
   
   **Pros**:
   - Tailored to exact needs
   - No external dependencies
   - Full control
   - Can keep it simple
   
   **Cons**:
   - Must implement everything yourself
   - No DevTools
   - More code to maintain
   - Risk of reinventing wheel
   
   **Verdict**: Good if you want minimal dependencies and full control.

**Updated Recommendation**: **Consider Zustand** - It's lightweight, modern, and strikes a good balance. Only go custom if you have specific requirements that Zustand can't handle.

### 10.3 Reactivity Pattern

**Current Recommendation: Subscriber Pattern**

**Alternatives**:

1. **Subscriber Pattern** (Current)
   ```javascript
   store.subscribe(callback);
   ```
   - **Pros**: Simple, explicit, easy to debug
   - **Cons**: Manual subscription management

2. **Proxy-based Reactivity** (Vue-like)
   ```javascript
   const state = new Proxy({}, {
     set(target, prop, value) {
       target[prop] = value;
       notifySubscribers();
     }
   });
   ```
   - **Pros**: Automatic reactivity
   - **Cons**: Proxy performance overhead, less explicit

3. **Observable Pattern** (RxJS)
   ```javascript
   import { Observable } from 'rxjs';
   
   const state$ = new Observable(subscriber => {
     // ...
   });
   ```
   - **Pros**: Powerful, composable
   - **Cons**: Large dependency, learning curve, may be overkill

**Verdict**: Subscriber pattern is fine for this use case. Consider Proxy-based if you want automatic reactivity.

### 10.4 UI Update Strategy

**Current Recommendation: Manual DOM Updates in UIManager**

**Alternatives**:

1. **Manual DOM Updates** (Current)
   - **Pros**: Full control, no framework overhead
   - **Cons**: More code, manual synchronization

2. **React/Preact** (Component-based)
   ```jsx
   function FilterPanel({ filters, onFilterChange }) {
     return (
       <select value={filters.country} onChange={onFilterChange}>
         {/* ... */}
       </select>
     );
   }
   ```
   - **Pros**: Reactive UI, component reusability, ecosystem
   - **Cons**: Major rewrite, framework overhead, JSX compilation
   
   **Verdict**: Only if you want a full React migration (major undertaking).

3. **Lit** (Web Components)
   ```javascript
   class FilterPanel extends LitElement {
     static properties = { filters: { type: Object } };
     render() { return html`...`; }
   }
   ```
   - **Pros**: Standards-based, no framework, reusable components
   - **Cons**: Smaller ecosystem, different paradigm
   
   **Verdict**: Good middle ground if you want components without React.

**Current Recommendation**: **Keep manual DOM updates** for now. The UI is simple enough that React/component framework isn't necessary. Consider migrating to React/Lit later if UI complexity grows.

### 10.5 API Communication Pattern

**Current Recommendation: Adapter Pattern with Fetch**

**Alternatives**:

1. **Adapter with Fetch** (Current)
   - **Pros**: Native browser API, simple
   - **Cons**: No request cancellation, manual retry logic

2. **Axios**
   ```javascript
   const api = axios.create({ baseURL: '/api' });
   ```
   - **Pros**: Request cancellation, interceptors, retry logic
   - **Cons**: Additional dependency (~13KB)
   
   **Verdict**: Good choice if you need advanced features. Fetch is fine for basic needs.

3. **React Query / TanStack Query** (for React apps)
   - **Pros**: Caching, automatic refetching, background updates
   - **Cons**: React-specific, overkill if not using React

### 10.6 Potential Downsides & Risks

**1. Over-Engineering Risk**
- **Risk**: Building more than needed
- **Mitigation**: Start simple, add complexity only when needed
- **Check**: Can we solve the problem with less code?

**2. Migration Complexity**
- **Risk**: Breaking existing functionality during migration
- **Mitigation**: Feature flags, parallel implementation, incremental migration
- **Check**: Can we test each phase independently?

**3. Performance Overhead**
- **Risk**: Reactive updates might cause unnecessary re-renders
- **Mitigation**: Memoization, debouncing, batch updates
- **Check**: Profile performance, optimize hot paths

**4. Learning Curve**
- **Risk**: Team needs to learn new patterns
- **Mitigation**: Documentation, code review, pair programming
- **Check**: Is the team comfortable with the chosen approach?

**5. Maintenance Burden**
- **Risk**: More code to maintain
- **Mitigation**: Keep it simple, good tests, documentation
- **Check**: Is the architecture simpler than the current mess?

**6. TypeScript Migration Complexity**
- **Risk**: Converting existing JS to TS can be time-consuming
- **Mitigation**: Gradual migration, `allowJs: true`, start with new files
- **Check**: Can we ship features while migrating?

### 10.7 Alternative Architectures

**Alternative 1: MVC Pattern**
```
Model (State) → View (UI) ← Controller (Event Handlers)
```
- **Pros**: Familiar pattern, clear separation
- **Cons**: Less reactive, more boilerplate
- **Verdict**: Good but less modern than reactive pattern

**Alternative 2: Event-Driven Architecture**
```javascript
EventBus.on('airports-changed', (airports) => {
  // Update UI
  // Update map
});
```
- **Pros**: Decoupled components
- **Cons**: Hard to trace event flow, can become spaghetti
- **Verdict**: Good for simple cases, but state management is better

**Alternative 3: Micro-Frontend Architecture**
- Split into separate apps (filters, map, chatbot)
- **Pros**: Independent deployment, team autonomy
- **Cons**: Complex integration, overhead
- **Verdict**: Overkill for this project size

**Alternative 4: Keep Current Architecture, Just Fix Issues**
- Add missing filters to API
- Fix state synchronization
- Add highlighting system
- **Pros**: Minimal changes, low risk
- **Cons**: Technical debt remains, harder to extend
- **Verdict**: Short-term fix, but long-term pain

### 10.8 Decisions Required

**Decision 1: TypeScript** ✅ **RECOMMENDED**
- [ ] Use TypeScript for new architecture code
- [ ] Migrate existing files incrementally
- [ ] Setup: `tsconfig.json`, build tooling

**Decision 2: State Management Library**
- [ ] **Zustand** (Recommended: Lightweight, modern)
- [ ] Redux Toolkit (If you want industry standard)
- [ ] Custom StateStore (If you want full control)

**Decision 3: Reactivity Pattern**
- [ ] **Subscriber Pattern** (Recommended: Simple, explicit)
- [ ] Proxy-based (If you want automatic reactivity)

**Decision 4: UI Framework**
- [ ] **Manual DOM Updates** (Recommended: Simple enough)
- [ ] React/Preact (If you want component-based UI)
- [ ] Lit (If you want web components)

**Decision 5: API Client**
- [ ] **Fetch API** (Recommended: Native, simple)
- [ ] Axios (If you need advanced features)

**Decision 6: Migration Strategy**
- [ ] **Gradual with Feature Flags** (Recommended: Low risk)
- [ ] Big Bang Migration (If you want clean slate)

**Decision 7: Scope of Refactoring**
- [ ] **Full Architecture** (Recommended: Long-term benefit)
- [ ] Incremental Fixes Only (If time-constrained)

### 10.9 Recommended Technology Stack

**Core**:
- ✅ **TypeScript** - Type safety
- ✅ **Zustand** - State management (or custom if you prefer)
- ✅ **Subscriber Pattern** - Reactivity
- ✅ **Fetch API** - HTTP client
- ✅ **Manual DOM Updates** - UI (simple enough)
- ✅ **Leaflet** - Map rendering (keep existing)

**Tooling**:
- **Vite** or **esbuild** - Build tool (if TypeScript compilation needed)
- **ESLint** - Code quality
- **Prettier** - Code formatting
- **Jest** or **Vitest** - Testing

**Migration Tools**:
- **Feature Flags** - Gradual rollout
- **Parallel Implementation** - Run old/new side by side

### 10.10 Cost-Benefit Analysis

**Costs**:
- Development time: ~10 weeks (as outlined)
- Learning curve: Team needs to understand new patterns
- Migration risk: Potential bugs during transition
- Testing effort: Need comprehensive tests

**Benefits**:
- Maintainability: Easier to understand and modify
- Extensibility: Easy to add new features
- Performance: More efficient updates
- Type Safety: Catch errors early
- Developer Experience: Better tooling, autocomplete

**ROI Calculation**:
- **Initial Investment**: 10 weeks development
- **Ongoing Savings**: 
  - Faster feature development (estimated 30% faster)
  - Fewer bugs (estimated 50% reduction)
  - Easier onboarding (estimated 40% faster)
- **Break-even**: ~6-8 months after migration

**Verdict**: Worth it if you plan to maintain/extend this application long-term.

---

## 11. References

- Existing codebase analysis: `FILTERING_AND_STATE_REVIEW.md`
- Filter engine: `shared/filtering/filter_engine.py`
- Current state management: `web/client/js/filters.js`, `web/client/js/map.js`
- API endpoints: `web/server/api/airports.py`

**Technology References**:
- TypeScript: https://www.typescriptlang.org/
- Zustand: https://github.com/pmndrs/zustand
- Redux Toolkit: https://redux-toolkit.js.org/
- React: https://react.dev/
- Lit: https://lit.dev/

