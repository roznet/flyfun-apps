/**
 * API Adapter - Clean interface for all API communication
 * Uses Fetch API, transforms requests/responses to standard format
 */

import type { Airport, FilterConfig } from '../store/types';

/**
 * Standard API response format
 */
export interface APIResponse<T = any> {
  data: T;
  count?: number;
  filters_applied?: Record<string, any>;
  filter_profile?: Record<string, any>;
  visualization?: any;
}

/**
 * Route search response
 */
export interface RouteSearchResponse {
  route_airports: string[];
  segment_distance_nm: number;
  airports_found: number;
  total_nearby: number;
  filters_applied: Record<string, any>;
  airports: Array<{
    airport: Airport;
    segment_distance_nm?: number;
    enroute_distance_nm?: number;
    closest_segment?: [string, string];
  }>;
}

/**
 * Locate response
 */
export interface LocateResponse {
  found: boolean;
  count: number;
  center: {lat: number; lon: number; label: string};
  airports: Airport[];
  pretty?: string;
  filter_profile?: Record<string, any>;
  visualization?: any;
}

/**
 * API Adapter class
 */
export class APIAdapter {
  private baseURL: string;
  
  constructor(baseURL: string = '') {
    this.baseURL = baseURL;
  }
  
  /**
   * Transform filters to API query parameters
   */
  private transformFiltersToParams(filters: Partial<FilterConfig>): URLSearchParams {
    const params = new URLSearchParams();
    
    if (filters.country) params.set('country', filters.country);
    if (filters.has_procedures === true) params.set('has_procedures', 'true');
    if (filters.has_aip_data === true) params.set('has_aip_data', 'true');
    if (filters.has_hard_runway === true) params.set('has_hard_runway', 'true');
    if (filters.point_of_entry === true) params.set('point_of_entry', 'true');
    if (filters.has_avgas === true) params.set('has_avgas', 'true');
    if (filters.has_jet_a === true) params.set('has_jet_a', 'true');
    if (filters.max_runway_length_ft) params.set('max_runway_length_ft', String(filters.max_runway_length_ft));
    if (filters.min_runway_length_ft) params.set('min_runway_length_ft', String(filters.min_runway_length_ft));
    if (filters.max_landing_fee) params.set('max_landing_fee', String(filters.max_landing_fee));
    if (filters.aip_field) params.set('aip_field', filters.aip_field);
    if (filters.aip_value) params.set('aip_value', filters.aip_value);
    if (filters.aip_operator) params.set('aip_operator', filters.aip_operator);
    if (filters.limit) params.set('limit', String(filters.limit));
    if (filters.offset) params.set('offset', String(filters.offset));
    
    return params;
  }
  
  /**
   * Make HTTP request
   */
  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseURL}${endpoint}`;
    
    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        ...options
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }
  
  /**
   * Get airports with filters
   */
  async getAirports(filters: Partial<FilterConfig> = {}): Promise<APIResponse<Airport[]>> {
    const params = this.transformFiltersToParams(filters);
    const queryString = params.toString();
    const endpoint = `/api/airports/${queryString ? '?' + queryString : ''}`;
    
    const data = await this.request<Airport[]>(endpoint);
    
    return {
      data: Array.isArray(data) ? data : [],
      count: Array.isArray(data) ? data.length : 0
    };
  }
  
  /**
   * Search airports by query
   */
  async searchAirports(query: string, limit: number = 20): Promise<APIResponse<Airport[]>> {
    const endpoint = `/api/airports/search/${encodeURIComponent(query)}?limit=${limit}`;
    const data = await this.request<Airport[]>(endpoint);
    
    return {
      data: Array.isArray(data) ? data : [],
      count: Array.isArray(data) ? data.length : 0
    };
  }
  
  /**
   * Search airports near route
   */
  async searchAirportsNearRoute(
    routeAirports: string[],
    distanceNm: number = 50.0,
    filters: Partial<FilterConfig> = {}
  ): Promise<RouteSearchResponse> {
    const params = new URLSearchParams();
    params.set('airports', routeAirports.join(','));
    params.set('segment_distance_nm', String(distanceNm));
    
    // Add filter parameters
    const filterParams = this.transformFiltersToParams(filters);
    filterParams.forEach((value, key) => {
      params.set(key, value);
    });
    
    // Add enroute distance if in filters
    if (filters.enroute_distance_max_nm) {
      params.set('enroute_distance_max_nm', String(filters.enroute_distance_max_nm));
    }
    
    const endpoint = `/api/airports/route-search?${params.toString()}`;
    return await this.request<RouteSearchResponse>(endpoint);
  }
  
  /**
   * Locate airports near a location
   */
  async locateAirports(
    query: string,
    radiusNm: number = 50.0,
    filters: Partial<FilterConfig> = {}
  ): Promise<LocateResponse> {
    const params = new URLSearchParams();
    params.set('q', query);
    params.set('radius_nm', String(radiusNm));
    
    // Add filter parameters
    const filterParams = this.transformFiltersToParams(filters);
    filterParams.forEach((value, key) => {
      params.set(key, value);
    });
    
    const endpoint = `/api/airports/locate?${params.toString()}`;
    return await this.request<LocateResponse>(endpoint);
  }
  
  /**
   * Locate airports by center coordinates
   */
  async locateAirportsByCenter(
    center: {lat: number; lon: number; label?: string},
    radiusNm: number = 50.0,
    filters: Partial<FilterConfig> = {}
  ): Promise<LocateResponse> {
    const params = new URLSearchParams();
    params.set('radius_nm', String(radiusNm));
    params.set('center_lat', String(center.lat));
    params.set('center_lon', String(center.lon));
    if (center.label) params.set('q', center.label);
    
    // Add filter parameters
    const filterParams = this.transformFiltersToParams(filters);
    filterParams.forEach((value, key) => {
      params.set(key, value);
    });
    
    const endpoint = `/api/airports/locate?${params.toString()}`;
    return await this.request<LocateResponse>(endpoint);
  }
  
  /**
   * Get airport details
   */
  async getAirportDetail(icao: string): Promise<any> {
    const endpoint = `/api/airports/${icao}`;
    return await this.request(endpoint);
  }
  
  /**
   * Get airport AIP entries
   */
  async getAirportAIPEntries(icao: string, filters: {section?: string; std_field?: string} = {}): Promise<any[]> {
    const params = new URLSearchParams();
    if (filters.section) params.set('section', filters.section);
    if (filters.std_field) params.set('std_field', filters.std_field);
    
    const queryString = params.toString();
    const endpoint = `/api/airports/${icao}/aip-entries${queryString ? '?' + queryString : ''}`;
    return await this.request<any[]>(endpoint);
  }
  
  /**
   * Get airport procedures
   */
  async getAirportProcedures(icao: string, filters: {procedure_type?: string; runway?: string} = {}): Promise<any[]> {
    const params = new URLSearchParams();
    if (filters.procedure_type) params.set('procedure_type', filters.procedure_type);
    if (filters.runway) params.set('runway', filters.runway);
    
    const queryString = params.toString();
    const endpoint = `/api/airports/${icao}/procedures${queryString ? '?' + queryString : ''}`;
    return await this.request<any[]>(endpoint);
  }
  
  /**
   * Get airport runways
   */
  async getAirportRunways(icao: string): Promise<any[]> {
    const endpoint = `/api/airports/${icao}/runways`;
    return await this.request<any[]>(endpoint);
  }
  
  /**
   * Get bulk procedure lines
   */
  async getBulkProcedureLines(airports: string[], distanceNm: number = 10.0): Promise<Record<string, any>> {
    const endpoint = '/api/airports/bulk/procedure-lines';
    return await this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify({
        airports,
        distance_nm: distanceNm
      })
    });
  }
  
  /**
   * Get country rules
   */
  async getCountryRules(countryCode: string): Promise<any> {
    if (!countryCode) return null;
    const endpoint = `/api/rules/${encodeURIComponent(countryCode)}`;
    return await this.request(endpoint);
  }
  
  /**
   * Get available filters metadata
   */
  async getAllFilters(): Promise<any> {
    const endpoint = '/api/filters/all';
    return await this.request(endpoint);
  }
  
  /**
   * Get AIP filter presets
   */
  async getAIPFilterPresets(): Promise<any[]> {
    const endpoint = '/api/airports/aip-filter-presets';
    return await this.request<any[]>(endpoint);
  }
  
  /**
   * Get available AIP fields
   */
  async getAvailableAIPFields(): Promise<any[]> {
    const endpoint = '/api/filters/aip-fields';
    return await this.request<any[]>(endpoint);
  }
}

