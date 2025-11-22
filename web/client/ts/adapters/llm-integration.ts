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
  point?: {lat: number; lng: number; label: string};
  marker?: {ident: string; lat?: number; lon?: number; zoom?: number};
  filter_profile?: Partial<FilterConfig>;
}

/**
 * LLM Integration class
 */
export class LLMIntegration {
  private store: ReturnType<typeof useStore>;
  private apiAdapter: APIAdapter;
  private uiManager: any; // UIManager reference (to avoid circular dependency)
  
  constructor(store: ReturnType<typeof useStore>, apiAdapter: APIAdapter, uiManager: any) {
    this.store = store;
    this.apiAdapter = apiAdapter;
    this.uiManager = uiManager;
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
   * Handle markers visualization
   */
  private handleMarkers(viz: Visualization): boolean {
    const airports = viz.data || viz.markers || [];
    
    if (!Array.isArray(airports) || airports.length === 0) {
      console.error('markers visualization missing valid airports array');
      return false;
    }
    
    // Update store with airports
    (this.store as any).getState().setAirports(airports);
    
    // Apply filter profile if provided
    const filterProfile = viz.filter_profile as Partial<FilterConfig> | undefined;
    if (filterProfile) {
      this.applyFilterProfile(filterProfile);
    }
    
    return true;
  }
  
  /**
   * Handle route with markers visualization
   */
  private handleRouteWithMarkers(viz: Visualization): boolean {
    if (!viz.route || !viz.markers) {
      console.error('route_with_markers missing route or markers');
      return false;
    }
    
    const route = viz.route as Visualization['route'];
    const airports = (viz.markers || []) as Airport[];
    const fromIcao = route?.from?.icao;
    const toIcao = route?.to?.icao;
    
    if (!fromIcao || !toIcao) {
      console.error('route_with_markers missing from/to ICAO codes');
      return false;
    }
    
    // Normalize route airport coordinates
    const fromLat = route.from.lat || route.from.latitude || 0;
    const fromLng = route.from.lon || route.from.longitude || 0;
    const toLat = route.to.lat || route.to.latitude || 0;
    const toLng = route.to.lon || route.to.longitude || 0;
    
    const originalRouteAirports = [
      {
        icao: fromIcao,
        lat: fromLat,
        lng: fromLng
      },
      {
        icao: toIcao,
        lat: toLat,
        lng: toLng
      }
    ];
    
    // Get distance from UI or use default
    const distanceInput = document.getElementById('route-distance') as HTMLInputElement;
    const distanceNm = distanceInput ? parseFloat(distanceInput.value) || 50.0 : 50.0;
    
    // Set route state (chatbot selection)
    const store = this.store as any;
    store.getState().setRoute({
      airports: [fromIcao, toIcao],
      distance_nm: distanceNm,
      originalRouteAirports,
      isChatbotSelection: true,
      chatbotAirports: airports
    });
    
    // Update store with chatbot's selected airports
    store.getState().setAirports(airports);
    
    // Apply filter profile if provided
    if (viz.filter_profile) {
      this.applyFilterProfile(viz.filter_profile);
    }
    
    // Dispatch event to render route
    const event = new CustomEvent('render-route', {
      detail: { route: { airports: [fromIcao, toIcao], distance_nm: distanceNm, originalRouteAirports } }
    });
    window.dispatchEvent(event);
    
    console.log(`✅ LLM route visualization: ${airports.length} airports from chatbot`);
    return true;
  }
  
  /**
   * Handle marker with details visualization
   */
  private handleMarkerWithDetails(viz: Visualization): boolean {
    const ident = viz.marker?.ident;
    if (!ident) {
      console.error('marker_with_details missing ident');
      return false;
    }
    
    // Update search input
    const searchInput = document.getElementById('search-input') as HTMLInputElement;
    if (searchInput) {
      searchInput.value = ident;
    }
    
    // Trigger search for this airport
    const event = new CustomEvent('trigger-search', { detail: { query: ident } });
    window.dispatchEvent(event);
    
    return true;
  }
  
  /**
   * Handle point with markers visualization
   */
  private handlePointWithMarkers(viz: Visualization): boolean {
    const airports = (viz.markers || []) as Airport[];
    const pointData = viz.point as {lat: number; lng: number; label?: string} | undefined;
    
    if (!Array.isArray(airports) || airports.length === 0) {
      console.error('point_with_markers missing valid airports array');
      return false;
    }
    
    // Update store with airports
    const store = this.store as any;
    store.getState().setAirports(airports as Airport[]);
    
    // Set locate state if point provided
    if (pointData) {
      (this.store as any).getState().setLocate({
        query: pointData.label || null,
        center: {
          lat: pointData.lat,
          lng: pointData.lng,
          label: pointData.label || 'Location'
        },
        radiusNm: 50.0 // Default, will be updated from filter profile if provided
      });
    }
    
    // Apply filter profile if provided
    const filterProfile = viz.filter_profile;
    if (filterProfile) {
      this.applyFilterProfile(filterProfile);
    }
    
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

