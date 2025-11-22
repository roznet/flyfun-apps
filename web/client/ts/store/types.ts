/**
 * TypeScript type definitions for the application state
 */

/**
 * Airport data structure (matches API response)
 */
export interface Airport {
  ident: string;
  name?: string;
  municipality?: string;
  iso_country?: string;
  latitude_deg?: number;
  longitude_deg?: number;
  longest_runway_length_ft?: number;
  point_of_entry?: boolean;
  has_procedures?: boolean;
  has_aip_data?: boolean;
  has_hard_runway?: boolean;
  procedure_count?: number;
  runway_count?: number;
  // Route-specific metadata
  _routeSegmentDistance?: number;
  _routeEnrouteDistance?: number;
  _closestSegment?: [string, string];
}

/**
 * Filter configuration
 */
export interface FilterConfig {
  country: string | null;
  has_procedures: boolean | null;
  has_aip_data: boolean | null;
  has_hard_runway: boolean | null;
  point_of_entry: boolean | null;
  aip_field: string | null;
  aip_value: string | null;
  aip_operator: 'contains' | 'equals' | 'not_empty' | 'starts_with' | 'ends_with';
  has_avgas: boolean | null;
  has_jet_a: boolean | null;
  max_runway_length_ft: number | null;
  min_runway_length_ft: number | null;
  max_landing_fee: number | null;
  limit: number;
  offset: number;
  // Route-specific filters (not part of standard FilterConfig but used in API)
  enroute_distance_max_nm?: number;
}

/**
 * Legend mode types
 */
export type LegendMode = 'airport-type' | 'procedure-precision' | 'runway-length' | 'country';

/**
 * Highlight data
 */
export interface Highlight {
  id: string;
  type: 'point' | 'airport';
  lat: number;
  lng: number;
  color?: string;
  radius?: number;
  popup?: string;
}

/**
 * Overlay data
 */
export interface Overlay {
  id: string;
  type: 'circle' | 'polygon' | 'polyline';
  data: any; // Leaflet layer data
}

/**
 * Visualization configuration
 */
export interface VisualizationConfig {
  legendMode: LegendMode;
  highlights: Map<string, Highlight>;
  overlays: Map<string, Overlay>;
  showProcedureLines: boolean;
  showRoute: boolean;
}

/**
 * Route state
 */
export interface RouteState {
  airports: string[] | null; // ICAO codes
  distance_nm: number;
  originalRouteAirports: Array<{icao: string; lat: number; lng: number}> | null;
  isChatbotSelection: boolean;
  chatbotAirports: Airport[] | null;
}

/**
 * Locate state
 */
export interface LocateState {
  query: string | null;
  center: {lat: number; lng: number; label: string} | null;
  radiusNm: number;
}

/**
 * Map view state
 */
export interface MapView {
  center: [number, number]; // [lat, lng]
  zoom: number;
}

/**
 * UI state
 */
export interface UIState {
  loading: boolean;
  error: string | null;
  searchQuery: string;
  activeTab: 'details' | 'aip' | 'rules';
}

/**
 * Complete application state
 */
export interface AppState {
  // Airport data
  airports: Airport[];
  filteredAirports: Airport[];
  
  // Filter configuration
  filters: FilterConfig;
  
  // Visualization configuration
  visualization: VisualizationConfig;
  
  // Route state
  route: RouteState | null;
  
  // Locate state
  locate: LocateState | null;
  
  // Selection state
  selectedAirport: Airport | null;
  
  // Map view state
  mapView: MapView;
  
  // UI state
  ui: UIState;
}

/**
 * Action types for state updates
 */
export type AppAction =
  | { type: 'SET_AIRPORTS'; payload: Airport[] }
  | { type: 'SET_FILTERS'; payload: Partial<FilterConfig> }
  | { type: 'SET_LEGEND_MODE'; payload: LegendMode }
  | { type: 'HIGHLIGHT_POINT'; payload: Highlight }
  | { type: 'REMOVE_HIGHLIGHT'; payload: string }
  | { type: 'CLEAR_HIGHLIGHTS' }
  | { type: 'SET_ROUTE'; payload: RouteState | null }
  | { type: 'SET_LOCATE'; payload: LocateState | null }
  | { type: 'SELECT_AIRPORT'; payload: Airport | null }
  | { type: 'SET_MAP_VIEW'; payload: MapView }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_SEARCH_QUERY'; payload: string }
  | { type: 'SET_ACTIVE_TAB'; payload: UIState['activeTab'] }
  | { type: 'CLEAR_FILTERS' }
  | { type: 'RESET_STATE' };

