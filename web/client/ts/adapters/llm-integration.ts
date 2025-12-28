/**
 * LLM Integration - Clean interface for chatbot interactions
 * Handles visualization data from LLM responses and applies filter profiles
 */

import { useStore } from '../store/store';
import type { Airport, FilterConfig } from '../store/types';
import { APIAdapter } from './api-adapter';

/**
 * Visualization types from LLM
 */
interface Visualization {
  type: 'markers' | 'route_with_markers' | 'marker_with_details' | 'point_with_markers';
  data?: Airport[];
  markers?: Airport[];
  route?: {
    from: {icao: string; lat?: number; lon?: number; latitude?: number; longitude?: number};
    to: {icao: string; lat?: number; lon?: number; latitude?: number; longitude?: number};
  };
  point?: {lat: number; lon?: number; lng?: number; label?: string};
  marker?: {ident: string; lat?: number; lon?: number; zoom?: number};
  filter_profile?: Partial<FilterConfig>;
  radius_nm?: number;  // Search radius for point_with_markers and route_with_markers
}

/**
 * LLM Integration class
 */
export class LLMIntegration {
  private store: ReturnType<typeof useStore>;
  private apiAdapter: APIAdapter;
  private uiManager: any; // UIManager reference (to avoid circular dependency)
  private visualizationEngine: any; // VisualizationEngine reference (to avoid circular dependency)
  
  constructor(store: ReturnType<typeof useStore>, apiAdapter: APIAdapter, uiManager: any, visualizationEngine?: any) {
    this.store = store;
    this.apiAdapter = apiAdapter;
    this.uiManager = uiManager;
    this.visualizationEngine = visualizationEngine;

    // Listen for clear-llm-highlights event (from UI manager when user initiates new search or clears filters)
    window.addEventListener('clear-llm-highlights', (() => {
      console.log('🔵 clear-llm-highlights event received');
      this.clearLLMHighlights();
    }) as EventListener);
  }
  
  /**
   * Set visualization engine (called after initialization)
   */
  setVisualizationEngine(engine: any): void {
    this.visualizationEngine = engine;
  }
  
  /**
   * Handle visualization from LLM response
   */
  handleVisualization(visualization: Visualization | Visualization[]): void {
    if (!visualization) {
      console.warn('LLMIntegration: No visualization provided');
      return;
    }
    
    // Handle array of visualizations - process first supported type
    if (Array.isArray(visualization)) {
      for (const viz of visualization) {
        if (viz && viz.type) {
          if (this.processVisualization(viz)) {
            return; // Successfully processed
          }
        }
      }
      console.error('No supported visualization type found in array');
      return;
    }
    
    // Handle single visualization
    if (!this.processVisualization(visualization)) {
      console.error(`Visualization type "${visualization.type}" not supported`);
    }
  }
  
  /**
   * Process a single visualization
   */
  private processVisualization(viz: Visualization): boolean {
    if (!viz || !viz.type) {
      return false;
    }
    
    switch (viz.type) {
      case 'markers':
        return this.handleMarkers(viz);
      case 'route_with_markers':
        return this.handleRouteWithMarkers(viz);
      case 'marker_with_details':
        return this.handleMarkerWithDetails(viz);
      case 'point_with_markers':
        return this.handlePointWithMarkers(viz);
      default:
        console.error(`Unknown visualization type: ${viz.type}`);
        return false;
    }
  }
  
  /**
   * Check if filter profile has meaningful filters (not just search_query or empty)
   * Meaningful filters: country, point_of_entry, has_avgas, has_jet_a, has_procedures, etc.
   */
  private hasMeaningfulFilters(filterProfile: Record<string, unknown> | undefined): boolean {
    if (!filterProfile || typeof filterProfile !== 'object') {
      return false;
    }

    // List of filter keys that would trigger loading all matching airports
    const meaningfulFilterKeys = [
      'country',
      'point_of_entry',
      'has_avgas',
      'has_jet_a',
      'has_procedures',
      'has_aip_data',
      'has_hard_runway',
      'min_runway_length_ft',
      'max_runway_length_ft',
      'max_landing_fee',
    ];

    return meaningfulFilterKeys.some(key => {
      const value = filterProfile[key];
      // Check if the value is truthy (for booleans) or non-empty (for strings/numbers)
      return value !== undefined && value !== null && value !== '' && value !== false;
    });
  }

  /**
   * Add blue highlights for airports returned by the tool
   */
  private addAirportHighlights(airports: Airport[], label: string = 'Mentioned in chat'): number {
    const store = this.store as any;
    let highlightCount = 0;

    airports.forEach((airport: any) => {
      if (airport.ident && airport.latitude_deg && airport.longitude_deg) {
        store.getState().highlightPoint({
          id: `llm-airport-${airport.ident}`,
          type: 'airport' as const,
          lat: airport.latitude_deg,
          lng: airport.longitude_deg,
          color: '#007bff',
          radius: 15,
          popup: `<b>${airport.ident}</b><br>${airport.name || 'Airport'}<br><em>${label}</em>`,
          country: airport.iso_country || airport.country
        });
        highlightCount++;
      }
    });

    return highlightCount;
  }

  /**
   * Handle markers visualization
   *
   * Two modes:
   * 1. With meaningful filters (country, point_of_entry, etc.):
   *    - Apply filters to store → Load ALL matching airports via API → Highlight specific ones
   * 2. Without meaningful filters (just airport list):
   *    - Show returned airports → Fit bounds → Highlight them
   */
  private handleMarkers(viz: Visualization): boolean {
    // Airports returned by the tool (these will be highlighted)
    const toolAirports = viz.data || viz.markers || [];
    const filterProfile = viz.filter_profile as Record<string, unknown> | undefined;

    if (!Array.isArray(toolAirports) || toolAirports.length === 0) {
      console.error('LLMIntegration: markers visualization missing valid airports array', viz);
      return false;
    }

    const hasMeaningfulFilters = this.hasMeaningfulFilters(filterProfile);

    console.log('LLMIntegration: Handling markers visualization', {
      type: viz.type,
      toolAirportCount: toolAirports.length,
      hasMeaningfulFilters,
      filterProfile,
      toolAirports: toolAirports.slice(0, 3).map((a: any) => a.ident)
    });

    // Clear old LLM highlights
    this.clearLLMHighlights();

    const store = this.store as any;

    if (hasMeaningfulFilters) {
      // MODE 1: Has meaningful filters
      // Apply filters → Load ALL matching airports → Highlight specific ones

      console.log('🔵 Mode: Filters - applying filters and loading all matching airports');

      // 1. Apply filter profile to store (updates UI filter controls)
      this.applyFilterProfile(filterProfile!);

      // 2. Add blue highlights for the specific airports from the tool
      const highlightCount = this.addAirportHighlights(toolAirports, 'Recommended by assistant');
      console.log(`✅ Added blue highlights for ${highlightCount} recommended airports`);

      // 3. Dispatch event to load ALL airports matching the filters
      window.dispatchEvent(new CustomEvent('trigger-filter-refresh'));

    } else {
      // MODE 2: No meaningful filters (just airport list)
      // Show returned airports → Fit bounds → Highlight them

      console.log('🔵 Mode: No filters - showing returned airports directly');

      // 1. Set airports in store (shows only these airports)
      store.getState().setAirports(toolAirports);

      // 2. Add blue highlights for all returned airports
      const highlightCount = this.addAirportHighlights(toolAirports, 'Search result');
      console.log(`✅ Added blue highlights for ${highlightCount} airports`);

      // 3. Fit bounds to show all airports
      if (this.visualizationEngine && toolAirports.length > 0) {
        setTimeout(() => {
          this.visualizationEngine.fitBounds();
          console.log('LLMIntegration: Fitted map bounds to show all airports');
        }, 100);
      }
    }

    return true;
  }
  
  /**
   * Handle route with markers visualization
   * Shows all airports along route via search, highlights specific airports from chat
   */
  private handleRouteWithMarkers(viz: Visualization): boolean {
    console.log('🔵 handleRouteWithMarkers called with viz:', viz);

    if (!viz.route || !viz.markers) {
      console.error('route_with_markers missing route or markers', {
        hasRoute: !!viz.route,
        hasMarkers: !!viz.markers,
        viz
      });
      return false;
    }

    const route = viz.route as Visualization['route'];
    const airports = (viz.markers || []) as Airport[];
    const fromIcao = route?.from?.icao;
    const toIcao = route?.to?.icao;

    console.log('🔵 Route data:', { fromIcao, toIcao, airportCount: airports.length });

    if (!fromIcao || !toIcao) {
      console.error('route_with_markers missing from/to ICAO codes');
      return false;
    }

    // Clear old LLM highlights (use prefix to identify them)
    this.clearLLMHighlights();
    console.log('🔵 Cleared old highlights');

    // Set highlights for airports mentioned in chat
    const store = this.store as any;
    let highlightCount = 0;
    airports.forEach((airport) => {
      console.log('🔵 Processing airport:', {
        ident: airport.ident,
        hasLat: !!airport.latitude_deg,
        hasLng: !!airport.longitude_deg,
        lat: airport.latitude_deg,
        lng: airport.longitude_deg
      });

      if (airport.ident && airport.latitude_deg && airport.longitude_deg) {
        store.getState().highlightPoint({
          id: `llm-airport-${airport.ident}`,
          type: 'airport' as const,
          lat: airport.latitude_deg,
          lng: airport.longitude_deg,
          color: '#007bff',
          radius: 15,
          popup: `<b>${airport.ident}</b><br>${airport.name || 'Airport'}<br><em>Mentioned in chat</em>`,
          country: airport.iso_country || airport.country  // Add country for filtering
        });
        highlightCount++;
        console.log(`🔵 Added highlight for ${airport.ident} (${airport.iso_country || airport.country || 'unknown'})`);
      }
    });

    console.log(`🔵 Total highlights added: ${highlightCount}`);
    
    // Build route query string for search
    const routeQuery = [fromIcao, toIcao].join(' ');
    
    // Update search query in store (will display in UI)
    store.getState().setSearchQuery(routeQuery);
    
    // Apply filter profile if provided (before triggering search)
    if (viz.filter_profile) {
      this.applyFilterProfile(viz.filter_profile);
    }
    
    // Trigger route search via event (uses normal search flow)
    // This will show all airports along route, with highlights on chat airports
    window.dispatchEvent(new CustomEvent('trigger-search', { 
      detail: { query: routeQuery } 
    }));
    
    console.log(`✅ LLM route visualization: route ${routeQuery}, highlighting ${airports.length} airports from chat`);
    return true;
  }
  
  /**
   * Clear LLM-specific highlights (those with 'llm-airport-' prefix)
   */
  private clearLLMHighlights(): void {
    const store = this.store as any;
    const state = store.getState();
    const highlights = state.visualization.highlights;

    // Collect IDs to remove first (avoid modifying Map during iteration)
    const idsToRemove: string[] = [];

    if (highlights instanceof globalThis.Map) {
      highlights.forEach((_, id: string) => {
        if (id.startsWith('llm-airport-') || id === 'llm-location-center') {
          idsToRemove.push(id);
        }
      });
    } else if (highlights && typeof highlights === 'object') {
      Object.keys(highlights).forEach((id: string) => {
        if (id.startsWith('llm-airport-') || id === 'llm-location-center') {
          idsToRemove.push(id);
        }
      });
    }

    // Remove collected IDs
    idsToRemove.forEach(id => {
      store.getState().removeHighlight(id);
    });
  }

  /**
   * Reset all visualizations (public method for clearing chat)
   * Complete reset - clears everything and loads all airports
   */
  async resetVisualization(): Promise<void> {
    const store = this.store as any;

    // Clear LLM highlights
    this.clearLLMHighlights();

    // Clear all highlights
    store.getState().clearHighlights();

    // Clear route
    store.getState().setRoute(null);

    // Clear locate state
    store.getState().setLocate(null);

    // Clear filters to default
    store.getState().clearFilters();

    // Clear search query
    store.getState().setSearchQuery('');

    // Load all airports with default filters (limit to 1000)
    try {
      store.getState().setLoading(true);
      const response = await this.apiAdapter.getAirports({ limit: 1000 });
      store.getState().setAirports(response.data);
      store.getState().setLoading(false);
      console.log(`✅ Complete reset - loaded ${response.data.length} airports`);
    } catch (error) {
      console.error('Error loading airports after reset:', error);
      store.getState().setAirports([]);
      store.getState().setLoading(false);
    }
  }
  
  /**
   * Handle marker with details visualization
   * Centers map on airport and displays details panel
   */
  private handleMarkerWithDetails(viz: Visualization): boolean {
    const ident = viz.marker?.ident;
    if (!ident) {
      console.error('marker_with_details missing ident');
      return false;
    }
    
    // Update search query in store (UI will sync automatically via subscription)
    const store = this.store as any;
    store.getState().setSearchQuery(ident);
    
    // 1. Trigger search to center map and show marker
    window.dispatchEvent(new CustomEvent('trigger-search', { detail: { query: ident } }));
    
    // 2. Trigger airport-click to load and display details panel
    // UIManager handles: selectAirport() + loadAirportDetails()
    window.dispatchEvent(new CustomEvent('airport-click', { detail: { ident } }));
    
    console.log(`✅ LLM marker_with_details: centered on ${ident} and loading details`);
    return true;
  }
  
  /**
   * Handle point with markers visualization
   * Shows all airports near location via search, highlights specific airports from chat
   */
  private handlePointWithMarkers(viz: Visualization): boolean {
    const recommendedAirports = (viz.markers || []) as Airport[];
    const pointData = viz.point;
    const radiusNm = viz.radius_nm || 50.0;

    if (!pointData) {
      console.error('point_with_markers missing point data');
      return false;
    }

    // Normalize lon/lng
    const pointLon = pointData.lon ?? pointData.lng;
    if (pointLon === undefined) {
      console.error('point_with_markers missing longitude');
      return false;
    }

    console.log('🔵 handlePointWithMarkers called with viz:', {
      point: pointData,
      radiusNm,
      recommendedCount: recommendedAirports.length
    });

    // Clear old LLM highlights
    this.clearLLMHighlights();

    const store = this.store as any;

    // Add location marker for the search point itself (e.g., "Bromley")
    store.getState().highlightPoint({
      id: 'llm-location-center',
      type: 'point' as const,
      lat: pointData.lat,
      lng: pointLon,
      popup: `<b>${pointData.label || 'Search Location'}</b><br>Search center point`
    });

    // Add blue highlights for recommended airports only (not all airports)
    let highlightCount = 0;
    recommendedAirports.forEach((airport) => {
      if (airport.ident && airport.latitude_deg && airport.longitude_deg) {
        store.getState().highlightPoint({
          id: `llm-airport-${airport.ident}`,
          type: 'airport' as const,
          lat: airport.latitude_deg,
          lng: airport.longitude_deg,
          color: '#007bff',
          radius: 15,
          popup: `<b>${airport.ident}</b><br>${airport.name || 'Airport'}<br><em>Recommended by assistant</em>`,
          country: airport.iso_country || airport.country
        });
        highlightCount++;
      }
    });

    console.log(`🔵 Added highlights for ${highlightCount} recommended airports`);

    // Set locate state with center point
    store.getState().setLocate({
      query: pointData.label || null,
      center: {
        lat: pointData.lat,
        lng: pointLon,
        label: pointData.label || 'Location'
      },
      radiusNm: radiusNm
    });

    // Update search radius in store (single source of truth)
    store.getState().setFilters({ search_radius_nm: radiusNm });

    // Apply filter profile if provided (before triggering search)
    const filterProfile = viz.filter_profile;
    if (filterProfile) {
      this.applyFilterProfile(filterProfile);
    }

    // Update search query in store (will display in UI)
    store.getState().setSearchQuery(pointData.label || '');

    // Trigger locate search via event (uses normal search flow to load ALL airports)
    // Radius is read from store.filters.search_radius_nm
    window.dispatchEvent(new CustomEvent('trigger-locate', {
      detail: {
        lat: pointData.lat,
        lon: pointLon,
        label: pointData.label
      }
    }));

    console.log(`✅ LLM point visualization: location "${pointData.label}", radius ${radiusNm}nm, highlighting ${recommendedAirports.length} recommended airports`);
    return true;
  }
  
  /**
   * Apply filter profile from chatbot
   */
  applyFilterProfile(filterProfile: unknown): void {
    if (!filterProfile || typeof filterProfile !== 'object' || filterProfile === null) {
      return;
    }
    
    const profile = filterProfile as Record<string, unknown>;
    console.log('Applying filter profile from chatbot:', profile);
    
    // Build filter object from profile
    const filters: Partial<FilterConfig> = {};
    
    // Map filter profile to filter config
    if (profile.country) filters.country = String(profile.country);
    if (profile.has_procedures) filters.has_procedures = Boolean(profile.has_procedures);
    if (profile.has_aip_data) filters.has_aip_data = Boolean(profile.has_aip_data);
    if (profile.has_hard_runway) filters.has_hard_runway = Boolean(profile.has_hard_runway);
    if (profile.point_of_entry) filters.point_of_entry = Boolean(profile.point_of_entry);
    if (profile.has_avgas) filters.has_avgas = Boolean(profile.has_avgas);
    if (profile.has_jet_a) filters.has_jet_a = Boolean(profile.has_jet_a);
    if (profile.max_runway_length_ft) filters.max_runway_length_ft = Number(profile.max_runway_length_ft);
    if (profile.min_runway_length_ft) filters.min_runway_length_ft = Number(profile.min_runway_length_ft);
    if (profile.max_landing_fee) filters.max_landing_fee = Number(profile.max_landing_fee);
    
    // Update store filters
    const store = this.store as any;
    store.getState().setFilters(filters);
    
    // Sync to UI controls (if uiManager available)
    if (this.uiManager && typeof this.uiManager.syncFiltersToUI === 'function') {
      this.uiManager.syncFiltersToUI(filters);
    }
  }
}

