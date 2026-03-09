/**
 * TypeScript type definitions for the application state
 */

/**
 * Airport data structure (matches API response)
 */
/**
 * GA Friendliness summary embedded in Airport (all personas pre-computed)
 */
export interface GAFriendlySummary {
  features: Record<string, number | null>;        // Raw feature scores
  persona_scores: Record<string, number | null>;  // Pre-computed scores for ALL personas
  review_count: number;
  last_review_utc?: string | null;
  tags?: string[] | null;
  summary_text?: string | null;
  notification_hassle?: string | null;
}

/**
 * Notification info for an airport (from chatbot tool responses)
 */
export interface NotificationSummary {
  notification_type?: string;  // 'h24', 'hours', 'on_request', etc.
  hours_notice?: number | null;
  is_h24?: boolean;
  is_on_request?: boolean;
  easiness_score?: number;  // 0-100
  summary?: string;
}

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
  // GA Friendliness data (populated when include_ga=true)
  ga?: GAFriendlySummary | null;
  // Notification data (from chatbot tool responses)
  notification?: NotificationSummary | null;
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
  // Fuel type filter: single-selection dropdown (avgas, jet_a, or null for no filter)
  fuel_type: 'avgas' | 'jet_a' | null;
  max_runway_length_ft: number | null;
  min_runway_length_ft: number | null;
  max_landing_fee: number | null;
  // Hospitality filters: at_airport (most restrictive) or vicinity (includes at_airport)
  hotel: 'at_airport' | 'vicinity' | null;
  restaurant: 'at_airport' | 'vicinity' | null;
  limit: number;
  offset: number;
  // Search radius/distance parameters (used for route corridor and locate radius)
  search_radius_nm: number;
  enroute_distance_max_nm: number | null;
}

/**
 * Legend mode types
 */
export type LegendMode = 'airport-type' | 'procedure-precision' | 'runway-length' | 'country' | 'relevance' | 'notification';

/**
 * Relevance bucket types (quartile-based)
 */
export type RelevanceBucket = 
  | 'top-quartile'      // Top 25% of scores
  | 'second-quartile'   // 50-75% percentile
  | 'third-quartile'    // 25-50% percentile
  | 'bottom-quartile'   // Bottom 25% of scores
  | 'unknown';          // No GA data

/**
 * Relevance bucket configuration (colors only - thresholds computed from quartiles)
 */
export interface RelevanceBucketConfig {
  id: RelevanceBucket;
  label: string;
  color: string;
}

// =============================================================================
// Legend Configuration Types
// =============================================================================

/**
 * Generic legend entry with match function.
 * Used to define how airports are classified into legend buckets.
 * Order matters - first match wins.
 */
export interface LegendEntry<TData = Airport> {
  id: string;
  label: string;
  color: string;
  /** Optional radius multiplier for marker size (default 1.0) */
  radiusMultiplier?: number;
  /** Match function - returns true if this entry applies to the data */
  match: (data: TData) => boolean;
}

/**
 * Legend configuration for a mode.
 * Contains ordered entries that define classification logic.
 */
export interface LegendConfig<TData = Airport> {
  mode: LegendMode;
  /** Display type: 'color' for filled circles, 'line' for procedure lines */
  displayType: 'color' | 'line';
  /** Ordered entries - first match wins */
  entries: LegendEntry<TData>[];
  /** If true, markers are transparent and lines are colored (e.g., procedure-precision) */
  useTransparentMarkers?: boolean;
}

/**
 * Simplified display bucket for legend panel.
 * Used when the full classification has many entries but the legend
 * should show fewer, grouped categories.
 */
export interface LegendDisplayBucket {
  id: string;
  label: string;
  color: string;
}

/**
 * Notification bucket IDs for type-safe classification
 */
export type NotificationBucketId =
  | 'h24'        // H24 operations - no notice required
  | 'easy'       // Easy: <=12h notice or operating hours only
  | 'moderate'   // Moderate: 13-24h notice or on-request
  | 'hassle'     // Hassle: 25-48h notice or business day
  | 'difficult'  // Difficult: >48h notice or not available
  | 'unknown';   // No notification data

/**
 * Airport type bucket IDs
 */
export type AirportTypeBucketId =
  | 'border-crossing'      // Point of entry (border crossing)
  | 'with-procedures'      // Has instrument procedures
  | 'without-procedures';  // No instrument procedures

/**
 * Runway length bucket IDs
 */
export type RunwayLengthBucketId =
  | 'long'     // >8000 ft
  | 'medium'   // 4000-8000 ft
  | 'short'    // <4000 ft
  | 'unknown'; // No runway data

/**
 * Country bucket IDs
 */
export type CountryBucketId =
  | 'france'   // LF prefix
  | 'uk'       // EG prefix
  | 'germany'  // ED prefix
  | 'other';   // All other countries

/**
 * Procedure precision bucket IDs (for procedure lines, not markers)
 */
export type ProcedurePrecisionBucketId =
  | 'precision'      // ILS
  | 'rnp'            // RNP/RNAV
  | 'non-precision'; // VOR/NDB

/**
 * Persona definition with weights
 */
export interface Persona {
  id: string;
  label: string;
  description: string;
  weights: Record<string, number>;
}

/**
 * GA configuration from API (source of truth)
 */
export interface GAConfig {
  feature_names: string[];
  feature_display_names: Record<string, string>;
  feature_descriptions: Record<string, string>;
  relevance_buckets: RelevanceBucketConfig[];
  personas: Persona[];
  default_persona: string;
  version: string;
}

/**
 * GA feature scores for an airport
 */
export interface GAFeatureScores {
  ga_cost_score: number | null;
  ga_review_score: number | null;
  ga_hassle_score: number | null;
  ga_ops_ifr_score: number | null;
  ga_ops_vfr_score: number | null;
  ga_access_score: number | null;
  ga_fun_score: number | null;
  ga_hospitality_score: number | null;
}

/**
 * GA score for a single airport
 */
export interface AirportGAScore {
  icao: string;
  has_data: boolean;
  score: number | null;
  features: GAFeatureScores | null;
  review_count: number;
}

/**
 * Full GA summary for an airport
 */
export interface AirportGASummary extends AirportGAScore {
  last_review_utc: string | null;
  tags: string[];
  summary_text: string | null;
  notification_summary: string | null;
  hassle_level: string | null;
  hotel_info: string | null;
  restaurant_info: string | null;
}

/**
 * Computed quartile thresholds
 */
export interface QuartileThresholds {
  q1: number;  // 25th percentile
  q2: number;  // 50th percentile (median)
  q3: number;  // 75th percentile
}

/**
 * GA Friendliness state
 */
export interface GAState {
  // Configuration from API
  config: GAConfig | null;
  configLoaded: boolean;
  configError: string | null;
  
  // Runtime state
  selectedPersona: string;
  scores: Map<string, AirportGAScore>;
  summaries: Map<string, AirportGASummary>;
  isLoading: boolean;
  
  // Computed from current scores (recalculated when scores change)
  computedQuartiles: QuartileThresholds | null;
}

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
  country?: string;  // ISO country code for filtering
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
 * Bounding box for viewport-based airport loading
 */
export interface BoundingBox {
  north: number;
  south: number;
  east: number;
  west: number;
}

/**
 * UI state
 */
export interface UIState {
  loading: boolean;
  error: string | null;
  searchQuery: string;
  activeTab: 'details' | 'aip' | 'rules' | 'relevance';
}

/**
 * Rules / country regulations state
 *
 * Note: we keep this fairly generic and close to the API / LLM payloads so that
 * UI code can render from it without duplicating structures. The store owns:
 * - full rules per country (as returned by the API)
 * - which countries are currently active/visible
 * - a "visual" filter coming from the LLM UI payload (e.g. tagsByCountry)
 * - a free-text filter from the Rules search box
 * - per-section expand/collapse state
 */

// Raw rules category (matches API structure closely)
export interface RulesCategory {
  name: string;
  count?: number;
  country?: string;
  rules: any[];
}

// Raw rules payload per country (matches API)
export interface CountryRules {
  country: string;
  total_rules?: number;
  categories: RulesCategory[];
}

// Visual filters coming from LLM UI payload
export interface RulesVisualFilter {
  tagsByCountry: Record<string, string[]>;
}

export interface RulesState {
  // All rules we have loaded, keyed by ISO country code
  allRulesByCountry: Record<string, CountryRules>;

  // Countries currently selected/visible in the Rules panel, in display order
  activeCountries: string[];

  // Visual filter from LLM (e.g. subset of tags per country for precise filtering)
  visualFilter: RulesVisualFilter | null;

  // Free-text filter from the Rules search box
  textFilter: string;

  // Expand/collapse state for individual sections (by sectionId)
  sectionState: Record<string, boolean>;
}

/**
 * Auth state
 */
export interface AuthUser {
  id: string;
  email: string;
  name: string;
  approved: boolean;
}

export interface ChatUsageInfo {
  used: number;
  limit: number;
}

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: AuthUser | null;
  chatUsage: ChatUsageInfo | null;
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
  
  // GA Friendliness state
  ga: GAState;

  // Country rules / regulations state
  rules: RulesState;

  // Authentication state
  auth: AuthState;
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

