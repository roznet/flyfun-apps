/**
 * Zustand store for application state management
 */
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type { AppState, FilterConfig, LegendMode, Highlight, RouteState, LocateState, MapView, Airport } from './types';

/**
 * Initial state
 */
const initialState: AppState = {
  airports: [],
  filteredAirports: [],
  
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
  
  visualization: {
    legendMode: 'airport-type',
    highlights: new Map(),
    overlays: new Map(),
    showProcedureLines: false,
    showRoute: false
  },
  
  route: null,
  locate: null,
  selectedAirport: null,
  
  mapView: {
    center: [50.0, 10.0],
    zoom: 5
  },
  
  ui: {
    loading: false,
    error: null,
    searchQuery: '',
    activeTab: 'details'
  }
};

/**
 * Filter airports based on current filters
 * This will be implemented using the FilterEngine from shared/filtering
 */
function filterAirports(airports: Airport[], filters: Partial<FilterConfig>): Airport[] {
  // TODO: Integrate with shared/filtering/FilterEngine
  // For now, basic filtering
  console.log('filterAirports called:', {
    airportCount: airports.length,
    filters: filters,
    sampleAirport: airports[0] ? { ident: airports[0].ident, iso_country: airports[0].iso_country, country: (airports[0] as any).country } : null
  });

  const result = airports.filter(airport => {
    // Check country - handle both 'iso_country' (from API) and 'country' (from chatbot)
    const airportCountry = airport.iso_country || (airport as any).country;
    if (filters.country && airportCountry !== filters.country) {
      return false;
    }
    // Use truthy checks to handle undefined/null properties
    if (filters.has_procedures === true && !airport.has_procedures) {
      return false;
    }
    if (filters.has_procedures === false && airport.has_procedures === true) {
      return false;
    }
    if (filters.has_aip_data === true && !airport.has_aip_data) {
      return false;
    }
    if (filters.has_aip_data === false && airport.has_aip_data === true) {
      return false;
    }
    if (filters.has_hard_runway === true && !airport.has_hard_runway) {
      return false;
    }
    if (filters.has_hard_runway === false && airport.has_hard_runway === true) {
      return false;
    }
    if (filters.point_of_entry === true && !airport.point_of_entry) {
      return false;
    }
    if (filters.point_of_entry === false && airport.point_of_entry === true) {
      return false;
    }
    // TODO: Add more filters (has_avgas, has_jet_a, runway length, landing fee)
    return true;
  });

  console.log('filterAirports result:', result.length, 'airports');
  return result;
}

/**
 * Zustand store type
 */
interface StoreActions {
  // Actions
  setAirports: (airports: Airport[]) => void;
  setFilters: (filters: Partial<FilterConfig>) => void;
  setLegendMode: (mode: LegendMode) => void;
  highlightPoint: (highlight: Highlight) => void;
  removeHighlight: (id: string) => void;
  clearHighlights: () => void;
  setRoute: (route: RouteState | null) => void;
  setLocate: (locate: LocateState | null) => void;
  selectAirport: (airport: Airport | null) => void;
  setMapView: (view: MapView) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSearchQuery: (query: string) => void;
  setActiveTab: (tab: AppState['ui']['activeTab']) => void;
  clearFilters: () => void;
  resetState: () => void;
}

/**
 * Zustand store with actions
 */
// Create store factory function
const createStore = (set: any, get: any) => ({
      // Initialize state properly - Maps don't serialize to JSON
      airports: [],
      filteredAirports: [],
      filters: { ...initialState.filters },
      visualization: {
        ...initialState.visualization,
        highlights: new Map(),
        overlays: new Map()
      },
      route: null,
      locate: null,
      selectedAirport: null,
      mapView: { ...initialState.mapView },
      ui: { ...initialState.ui },
      
      // Set airports and auto-filter
      setAirports: (airports) => {
        const currentState = get();
        const filtered = filterAirports(airports, currentState.filters);
        // Only update if airports actually changed
        if (currentState.airports === airports && currentState.filteredAirports === filtered) {
          return; // No change, skip update
        }
        set((state) => {
          // Ensure highlights is a Map
          let highlights = state.visualization.highlights;
          if (!(highlights instanceof globalThis.Map)) {
            if (highlights && typeof highlights === 'object') {
              highlights = new globalThis.Map(Object.entries(highlights as Record<string, Highlight>));
            } else {
              highlights = new globalThis.Map();
            }
          }
          return {
            airports,
            filteredAirports: filtered,
            visualization: {
              ...state.visualization,
              highlights
            }
          };
        });
      },
      
      // Update filters and re-filter airports
      setFilters: (filters) => {
        const currentState = get();
        const newFilters = { ...currentState.filters, ...filters };
        // Check if filters actually changed
        const filtersChanged = JSON.stringify(currentState.filters) !== JSON.stringify(newFilters);
        if (!filtersChanged && currentState.airports.length > 0) {
          return; // No change, skip update
        }
        const filtered = filterAirports(currentState.airports, newFilters);
        set((state) => {
          // Ensure highlights is a Map
          let highlights = state.visualization.highlights;
          if (!(highlights instanceof globalThis.Map)) {
            if (highlights && typeof highlights === 'object') {
              highlights = new globalThis.Map(Object.entries(highlights as Record<string, Highlight>));
            } else {
              highlights = new globalThis.Map();
            }
          }
          return {
            filters: newFilters,
            filteredAirports: filtered,
            visualization: {
              ...state.visualization,
              highlights
            }
          };
        });
      },
      
      // Set legend mode
      setLegendMode: (mode) => {
        set((state) => {
          // Ensure highlights is a Map
          let highlights = state.visualization.highlights;
          if (!(highlights instanceof globalThis.Map)) {
            if (highlights && typeof highlights === 'object') {
              highlights = new globalThis.Map(Object.entries(highlights as Record<string, Highlight>));
            } else {
              highlights = new globalThis.Map();
            }
          }
          // Automatically enable procedure lines when legend mode is 'procedure-precision'
          const showProcedureLines = mode === 'procedure-precision';
          return {
            visualization: {
              ...state.visualization,
              legendMode: mode,
              showProcedureLines,
              highlights
            }
          };
        });
      },
      
      // Highlight management
      highlightPoint: (highlight) => {
        set((state) => {
          // Convert highlights to Map if it's a plain object (from serialization)
          let highlights: globalThis.Map<string, Highlight>;
          if (state.visualization.highlights instanceof globalThis.Map) {
            highlights = new globalThis.Map(state.visualization.highlights);
          } else if (state.visualization.highlights && typeof state.visualization.highlights === 'object') {
            highlights = new globalThis.Map(Object.entries(state.visualization.highlights as Record<string, Highlight>));
          } else {
            highlights = new globalThis.Map();
          }
          highlights.set(highlight.id, highlight);
          return {
            visualization: {
              ...state.visualization,
              highlights
            }
          };
        });
      },
      
      removeHighlight: (id) => {
        set((state) => {
          // Convert highlights to Map if it's a plain object
          let highlights: globalThis.Map<string, Highlight>;
          if (state.visualization.highlights instanceof globalThis.Map) {
            highlights = new globalThis.Map(state.visualization.highlights);
          } else if (state.visualization.highlights && typeof state.visualization.highlights === 'object') {
            highlights = new globalThis.Map(Object.entries(state.visualization.highlights as Record<string, Highlight>));
          } else {
            highlights = new globalThis.Map();
          }
          highlights.delete(id);
          return {
            visualization: {
              ...state.visualization,
              highlights
            }
          };
        });
      },
      
      clearHighlights: () => {
        set((state) => ({
          visualization: {
            ...state.visualization,
            highlights: new globalThis.Map()
          }
        }));
      },
      
      // Route state
      setRoute: (route) => {
        set({ route });
      },
      
      // Locate state
      setLocate: (locate) => {
        set({ locate });
      },
      
      // Airport selection
      selectAirport: (airport) => {
        set({ selectedAirport: airport });
      },
      
      // Map view
      setMapView: (view) => {
        const currentState = get();
        // Only update if view actually changed
        if (currentState.mapView &&
            currentState.mapView.center[0] === view.center[0] &&
            currentState.mapView.center[1] === view.center[1] &&
            currentState.mapView.zoom === view.zoom) {
          return; // No change, skip update
        }
        set({ mapView: view });
      },
      
      // UI state
      setLoading: (loading) => {
        set((state) => ({
          ui: { ...state.ui, loading }
        }));
      },
      
      setError: (error) => {
        set((state) => ({
          ui: { ...state.ui, error }
        }));
      },
      
      setSearchQuery: (query) => {
        set((state) => ({
          ui: { ...state.ui, searchQuery: query }
        }));
      },
      
      setActiveTab: (tab) => {
        set((state) => ({
          ui: { ...state.ui, activeTab: tab }
        }));
      },
      
      // Clear filters
      clearFilters: () => {
        const clearedFilters = { ...initialState.filters };
        const filtered = filterAirports(get().airports, clearedFilters);
        set({
          filters: clearedFilters,
          filteredAirports: filtered
        });
      },
      
      // Reset entire state
      resetState: () => {
        set(initialState);
      }
});

// Export store with devtools
// Devtools will gracefully handle cases where Redux DevTools extension isn't available
export const useStore = create<AppState & StoreActions>()(
  devtools(createStore, { name: 'AirportExplorerStore' })
);

