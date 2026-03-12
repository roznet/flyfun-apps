/**
 * Zustand store for application state management
 */
import { create, StateCreator } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type {
  AppState,
  FilterConfig,
  LegendMode,
  Highlight,
  RouteState,
  LocateState,
  MapView,
  Airport,
  GAConfig,
  AirportGAScore,
  AirportGASummary,
  GAState,
  QuartileThresholds,
  CountryRules,
  RulesState,
  AuthUser,
  ChatUsageInfo,
  AuthState,
  TrialInfo
} from './types';
import { computeQuartileThresholds } from '../utils/relevance';

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
    fuel_type: null,
    max_runway_length_ft: null,
    min_runway_length_ft: null,
    max_landing_fee: null,
    hotel: null,
    restaurant: null,
    limit: 1000,
    offset: 0,
    search_radius_nm: 50,
    enroute_distance_max_nm: null
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
    center: [47.67, 9.51],
    zoom: 4
  },
  
  ui: {
    loading: false,
    error: null,
    searchQuery: '',
    activeTab: 'details'
  },
  
  ga: {
    config: null,
    configLoaded: false,
    configError: null,
    selectedPersona: 'ifr_touring_sr22',
    scores: new Map(),
    summaries: new Map(),
    isLoading: false,
    computedQuartiles: null
  },

  rules: {
    allRulesByCountry: {},
    activeCountries: [],
    visualFilter: null,
    textFilter: '',
    sectionState: {}
  },

  auth: {
    isAuthenticated: false,
    isLoading: true,
    user: null,
    chatUsage: null,
    trialInfo: null,
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
    sampleAirport: airports[0] ? { ident: airports[0].ident, iso_country: airports[0].iso_country } : null
  });

  const result = airports.filter(airport => {
    // Check country filter
    if (filters.country && airport.iso_country !== filters.country) {
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
    // TODO: Add more filters (fuel_type, runway length, landing fee)
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
  
  // GA Friendliness Actions
  setGAConfig: (config: GAConfig) => void;
  setGAConfigError: (error: string | null) => void;
  setGASelectedPersona: (personaId: string) => void;
  setGAScores: (scores: Record<string, AirportGAScore>) => void;
  setGASummary: (icao: string, summary: AirportGASummary) => void;
  setGALoading: (loading: boolean) => void;
  setGAComputedQuartiles: (quartiles: QuartileThresholds | null) => void;
  clearGAScores: () => void;

  // Rules / regulations actions
  setRulesForCountry: (countryCode: string, rules: CountryRules) => void;
  setRulesSelection: (countries: string[], visualFilter: RulesState['visualFilter']) => void;
  setRulesTextFilter: (text: string) => void;
  setRuleSectionState: (sectionId: string, expanded: boolean) => void;
  clearRules: () => void;

  // Auth actions
  setAuth: (user: AuthUser | null, chatUsage?: ChatUsageInfo | null) => void;
  setAuthLoading: (loading: boolean) => void;
  setTrialInfo: (info: TrialInfo | null) => void;
}

/**
 * Zustand store with actions
 */
// Create store factory function with proper types
type StoreState = AppState & StoreActions;
const createStore: StateCreator<StoreState, [], [["zustand/devtools", never]]> = (set, get) => ({
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
      ga: {
        ...initialState.ga,
        scores: new Map(),
        summaries: new Map()
      },
      rules: {
        ...initialState.rules
      },
      auth: {
        ...initialState.auth
      },
      
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
      },
      
      // --- GA Friendliness Actions ---
      
      // Set GA config from API
      setGAConfig: (config) => {
        set((state) => ({
          ga: {
            ...state.ga,
            config,
            configLoaded: true,
            configError: null
          }
        }));
      },
      
      // Set GA config error
      setGAConfigError: (error) => {
        set((state) => ({
          ga: {
            ...state.ga,
            configLoaded: true,
            configError: error
          }
        }));
      },
      
      // Set selected persona
      // Note: scores are now embedded in airport.ga.persona_scores with ALL personas pre-computed
      // So we only need to recompute quartile thresholds, not reload scores
      setGASelectedPersona: (personaId) => {
        set((state) => ({
          ga: {
            ...state.ga,
            selectedPersona: personaId,
            // Quartiles will be recomputed by PersonaManager.computeQuartiles()
            computedQuartiles: null
          }
        }));
      },
      
      // Set GA scores (batch update) and compute quartiles
      setGAScores: (scores) => {
        set((state) => {
          // Merge new scores with existing
          const newScoresMap = new Map(state.ga.scores);
          for (const [icao, score] of Object.entries(scores)) {
            newScoresMap.set(icao, score);
          }
          
          // Compute quartiles from updated scores
          const quartiles = computeQuartileThresholds(newScoresMap);
          
          return {
            ga: {
              ...state.ga,
              scores: newScoresMap,
              computedQuartiles: quartiles
            }
          };
        });
      },
      
      // Set GA summary for single airport
      setGASummary: (icao, summary) => {
        set((state) => {
          const newSummaries = new Map(state.ga.summaries);
          newSummaries.set(icao, summary);
          
          // Also update score in scores map if it exists
          const newScores = new Map(state.ga.scores);
          newScores.set(icao, {
            icao: summary.icao,
            has_data: summary.has_data,
            score: summary.score,
            features: summary.features,
            review_count: summary.review_count
          });
          
          // Recompute quartiles
          const quartiles = computeQuartileThresholds(newScores);
          
          return {
            ga: {
              ...state.ga,
              summaries: newSummaries,
              scores: newScores,
              computedQuartiles: quartiles
            }
          };
        });
      },
      
      // Set GA loading state
      setGALoading: (loading) => {
        set((state) => ({
          ga: {
            ...state.ga,
            isLoading: loading
          }
        }));
      },
      
      // Set computed quartiles (called by PersonaManager when airports/persona change)
      setGAComputedQuartiles: (quartiles) => {
        set((state) => ({
          ga: {
            ...state.ga,
            computedQuartiles: quartiles
          }
        }));
      },
      
      // Clear GA scores (e.g., on persona change)
      clearGAScores: () => {
        set((state) => ({
          ga: {
            ...state.ga,
            scores: new Map(),
            summaries: new Map(),
            computedQuartiles: null
          }
        }));
      },

      // --- Rules / regulations actions ---

      // Store full rules payload for a single country
      setRulesForCountry: (countryCode, rules) => {
        set((state) => ({
          rules: {
            ...state.rules,
            allRulesByCountry: {
              ...state.rules.allRulesByCountry,
              [countryCode]: {
                ...rules,
                country: countryCode
              }
            }
          }
        }));
      },

      // Set which countries are active in the Rules panel and the current visual filter
      setRulesSelection: (countries, visualFilter) => {
        set((state) => ({
          rules: {
            ...state.rules,
            activeCountries: countries,
            visualFilter: visualFilter || null
          }
        }));
      },

      // Update free-text filter for rules
      setRulesTextFilter: (text) => {
        set((state) => ({
          rules: {
            ...state.rules,
            textFilter: text
          }
        }));
      },

      // Persist expand/collapse state for a single rules section
      setRuleSectionState: (sectionId, expanded) => {
        set((state) => ({
          rules: {
            ...state.rules,
            sectionState: {
              ...state.rules.sectionState,
              [sectionId]: expanded
            }
          }
        }));
      },

      // Clear all rules state (used when chatbot resets rules panel)
      clearRules: () => {
        set({
          rules: {
            allRulesByCountry: {},
            activeCountries: [],
            visualFilter: null,
            textFilter: '',
            sectionState: {}
          }
        });
      },

      // --- Auth actions ---

      setAuth: (user, chatUsage) => {
        set((state) => ({
          auth: {
            isAuthenticated: !!user,
            isLoading: false,
            user: user,
            chatUsage: chatUsage ?? null,
            trialInfo: user ? null : state.auth.trialInfo,
          }
        }));
      },

      setAuthLoading: (loading) => {
        set((state) => ({
          auth: { ...state.auth, isLoading: loading }
        }));
      },

      setTrialInfo: (info) => {
        set((state) => ({
          auth: { ...state.auth, trialInfo: info }
        }));
      },
});

// Export store with devtools
// Devtools will gracefully handle cases where Redux DevTools extension isn't available
export const useStore = create<AppState & StoreActions>()(
  devtools(createStore, { name: 'AirportExplorerStore' })
);

