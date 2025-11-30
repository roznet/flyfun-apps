/**
 * Main application entry point
 * Initializes all components and wires everything together
 */

import { useStore } from './store/store';
import { APIAdapter } from './adapters/api-adapter';
import { VisualizationEngine } from './engines/visualization-engine';
import { UIManager } from './managers/ui-manager';
import { LLMIntegration } from './adapters/llm-integration';
import { ChatbotManager } from './managers/chatbot-manager';
import { PersonaManager } from './managers/persona-manager';
import type { AppState, RouteState, MapView, FilterConfig } from './store/types';

// Global instances (for debugging/window access)
declare global {
  interface Window {
    appState: ReturnType<typeof useStore>;
    visualizationEngine: VisualizationEngine;
    uiManager: UIManager;
    llmIntegration: LLMIntegration;
    personaManager: PersonaManager;
  }
}

/**
 * Main application class
 */
class Application {
  private store: typeof useStore;
  private apiAdapter: APIAdapter;
  private visualizationEngine: VisualizationEngine;
  private uiManager: UIManager;
  private llmIntegration: LLMIntegration;
  private chatbotManager: ChatbotManager;
  private personaManager: PersonaManager;
  private currentSelectedIcao: string | null = null;
  private isUpdatingMapView: boolean = false; // Flag to prevent infinite loops
  private storeUnsubscribe?: () => void; // Store unsubscribe function
  
  constructor() {
    // Initialize store (Zustand hook)
    this.store = useStore;
    
    // Initialize API adapter
    this.apiAdapter = new APIAdapter('');
    
    // Initialize visualization engine
    this.visualizationEngine = new VisualizationEngine();
    
    // Initialize UI manager
    this.uiManager = new UIManager(this.store, this.apiAdapter);
    
    // Initialize LLM integration (pass visualization engine for fitBounds)
    this.llmIntegration = new LLMIntegration(this.store, this.apiAdapter, this.uiManager, this.visualizationEngine);
    
    // Initialize chatbot manager
    this.chatbotManager = new ChatbotManager(this.llmIntegration);
    
    // Initialize persona manager
    this.personaManager = new PersonaManager(this.apiAdapter);
    
    // Expose to window for debugging
    window.appState = this.store as any;
    window.visualizationEngine = this.visualizationEngine;
    window.uiManager = this.uiManager;
    window.llmIntegration = this.llmIntegration;
    window.personaManager = this.personaManager;
    (window as any).chatbotManager = this.chatbotManager;
  }
  
  /**
   * Initialize application
   */
  async init(): Promise<void> {
    console.log('Initializing Airport Explorer application...');
    
    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
      await new Promise(resolve => {
        document.addEventListener('DOMContentLoaded', resolve);
      });
    }
    
    // Initialize map
    this.initMap();
    
    // Subscribe to store changes
    this.subscribeToStore();
    
    // Initialize UI manager
    this.uiManager.init();
    
    // Initialize persona manager (async, loads GA config)
    this.personaManager.init().catch(error => {
      console.error('Failed to initialize PersonaManager:', error);
    });
    
    // Initialize event listeners
    this.initEventListeners();
    
    // Load initial data (if URL params present)
    await this.loadInitialState();
    
    console.log('Application initialized successfully');
  }
  
  /**
   * Initialize map
   */
  private initMap(): void {
    const mapContainer = document.getElementById('map');
    if (!mapContainer) {
      console.error('Map container not found. Looking for element with id="map"');
      // Try to find alternative container
      const altContainer = document.querySelector('[id*="map"]');
      if (altContainer) {
        console.warn('Found alternative map container:', altContainer.id);
      }
      return;
    }
    
    // Wait for Leaflet to be available
    // @ts-ignore - L is a global from Leaflet CDN
    if (typeof window.L === 'undefined') {
      console.error('Leaflet library not loaded. Make sure Leaflet CDN is included before this script.');
      // Retry after a short delay
      setTimeout(() => {
        // @ts-ignore
        if (typeof window.L !== 'undefined') {
          console.log('Leaflet loaded, initializing map...');
          this.visualizationEngine.initMap('map');
        } else {
          console.error('Leaflet still not loaded after retry');
        }
      }, 100);
      return;
    }
    
    console.log('Initializing map...');
    this.visualizationEngine.initMap('map');
    console.log('Map initialized successfully');
  }
  
  /**
   * Subscribe to store changes for visualization updates
   */
  private subscribeToStore(): void {
    // Subscribe to filtered airports changes
    let lastAirports: any[] = [];
    let lastLegendMode: string = '';
    let lastSelectedPersona: string = '';
    let lastHighlightsHash: string = '';
    let lastRouteHash: string = '';
    let lastLocateHash: string = '';
    let lastProcedureLinesHash: string = ''; // Track loaded procedure lines
    
    // Zustand's subscribe - listens to all state changes
    // Use debounce to prevent infinite loops
    let updateTimeout: number | null = null;
    const unsubscribe = this.store.subscribe((state: AppState) => {
      // Debounce to prevent rapid-fire updates
      if (updateTimeout) {
        clearTimeout(updateTimeout);
      }
      
      updateTimeout = window.setTimeout(() => {
        try {
          // Update markers if airports changed
          // Use JSON comparison to detect actual changes, not just reference changes
          const currentAirportsHash = JSON.stringify(state.filteredAirports.map(a => a.ident).sort());
          const lastAirportsHash = JSON.stringify(lastAirports.map((a: any) => a.ident).sort());
          const airportsChanged = currentAirportsHash !== lastAirportsHash;
          const legendModeChanged = state.visualization.legendMode !== lastLegendMode;
          const personaChanged = state.ga.selectedPersona !== lastSelectedPersona;
          
          // Capture previous legend mode BEFORE updating it (needed for procedure lines clearing)
          const wasProcedurePrecision = lastLegendMode === 'procedure-precision';
          const isProcedurePrecision = state.visualization.legendMode === 'procedure-precision';
          
          // Update markers when airports, legend mode, or persona changes (persona affects relevance coloring)
          const needsMarkerUpdate = airportsChanged || legendModeChanged || 
            (personaChanged && state.visualization.legendMode === 'relevance');
          
          if (needsMarkerUpdate) {
            console.log('Store subscription: Updating markers', {
              airportCount: state.filteredAirports.length,
              legendMode: state.visualization.legendMode,
              airportsChanged,
              legendModeChanged,
              personaChanged,
              selectedPersona: state.ga.selectedPersona
            });
            
            const shouldFitBounds = airportsChanged && state.filteredAirports.length > 0;
            this.visualizationEngine.updateMarkers(
              state.filteredAirports,
              state.visualization.legendMode,
              shouldFitBounds // Auto-fit bounds when airports change from chatbot
            );
            
            lastAirports = [...state.filteredAirports]; // Copy array for comparison
            lastLegendMode = state.visualization.legendMode;
            lastSelectedPersona = state.ga.selectedPersona;
          }
          
          // Build reference point highlights from route/locate state
          // These are automatically maintained based on route and locate state
          const referenceHighlights = new globalThis.Map<string, any>();
          
          // Add locate center highlight if present
          if (state.locate && state.locate.center) {
            const center = state.locate.center;
            referenceHighlights.set('locate-center', {
              id: 'locate-center',
              type: 'point' as const,
              lat: center.lat,
              lng: center.lng,
              color: '#007bff',
              radius: 14,
              popup: `<b>Locate Center</b><br>${center.label || 'Search origin'}<br>Radius: ${state.locate.radiusNm}nm`
            });
          }
          
          // Add route airport highlights if present
          if (state.route && state.route.originalRouteAirports) {
            state.route.originalRouteAirports.forEach((airport) => {
              const id = `route-airport-${airport.icao}`;
              referenceHighlights.set(id, {
                id,
                type: 'airport' as const,
                lat: airport.lat,
                lng: airport.lng,
                color: '#007bff',
                radius: 14,
                popup: `<b>Route Airport: ${airport.icao}</b><br>Input airport for route search`
              });
            });
          }
          
          // Merge reference highlights with user highlights (user highlights take precedence)
          let highlights: any = state.visualization.highlights;
          if (!highlights) {
            highlights = new globalThis.Map();
          } else if (!(highlights instanceof globalThis.Map)) {
            // Convert plain object to Map if needed (from Zustand serialization)
            const entries = Object.entries(highlights as Record<string, any>);
            highlights = new globalThis.Map(entries);
          }
          
          // Remove old reference highlights that are no longer valid
          const combinedHighlights = new globalThis.Map<string, any>(highlights);
          // Remove any old reference highlights
          combinedHighlights.forEach((_, id: string) => {
            if (id.startsWith('locate-center') || id.startsWith('route-airport-')) {
              combinedHighlights.delete(id);
            }
          });
          // Add current reference highlights
          referenceHighlights.forEach((highlight, id) => {
            combinedHighlights.set(id, highlight);
          });

          // Filter highlights by country if country filter is set
          let filteredHighlights = combinedHighlights;
          if (state.filters.country) {
            filteredHighlights = new globalThis.Map<string, any>();
            combinedHighlights.forEach((highlight, id) => {
              // Keep highlights that match the country filter or have no country (e.g., generic points, reference highlights)
              if (!highlight.country || highlight.country === state.filters.country) {
                filteredHighlights.set(id, highlight);
              }
            });
          }

          const highlightsHash = JSON.stringify(Array.from(filteredHighlights.entries()));
          if (highlightsHash !== lastHighlightsHash) {
            this.visualizationEngine.updateHighlights(filteredHighlights as any);
            lastHighlightsHash = highlightsHash;
          }
          
          // Update route (only if changed)
          const routeHash = JSON.stringify(state.route);
          if (routeHash !== lastRouteHash) {
            if (state.route) {
              this.visualizationEngine.displayRoute(state.route);
            } else {
              this.visualizationEngine.clearRoute();
            }
            lastRouteHash = routeHash;
          }
          
          // Handle procedure lines based on legend mode
          if (legendModeChanged && wasProcedurePrecision && !isProcedurePrecision) {
            // Clear procedure lines when switching away from procedure-precision mode
            console.log('Clearing procedure lines - legend mode changed away from procedure-precision', {
              previousMode: lastLegendMode,
              newMode: state.visualization.legendMode
            });
            this.visualizationEngine.clearProcedureLines();
            lastProcedureLinesHash = ''; // Reset hash
          } else if (isProcedurePrecision && state.visualization.showProcedureLines) {
            // Load procedure lines when in procedure-precision mode
            // Only reload if airports changed OR if legend mode just changed TO procedure-precision
            const currentProcedureLinesHash = currentAirportsHash; // Use airports hash as proxy
            const shouldLoadProcedureLines = (legendModeChanged && isProcedurePrecision) || 
              (airportsChanged && currentProcedureLinesHash !== lastProcedureLinesHash);
            
            if (shouldLoadProcedureLines) {
              console.log('Loading procedure lines - procedure-precision mode', {
                airportCount: state.filteredAirports.length,
                legendModeChanged,
                airportsChanged,
                justSwitchedToPrecision: legendModeChanged && isProcedurePrecision
              });
              this.loadProcedureLines(state.filteredAirports);
              lastProcedureLinesHash = currentProcedureLinesHash;
            }
          }
          
          // NOTE: We don't update map view here to prevent infinite loops
          // Map view is only updated from map events (moveend/zoomend) or initial load
        } catch (error) {
          console.error('Error in store subscription callback:', error);
        }
      }, 50); // Debounce 50ms to batch updates
    });
    
    // Store unsubscribe function (though we never need to unsubscribe in this case)
    this.storeUnsubscribe = unsubscribe;
  }
  
  /**
   * Get store instance (helper)
   */
  getStore() {
    return this.store;
  }
  
  /**
   * Initialize event listeners
   */
  private initEventListeners(): void {
    // Right panel collapse button
    const rightPanelCollapseBtn = document.getElementById('right-panel-collapse');
    if (rightPanelCollapseBtn) {
      rightPanelCollapseBtn.addEventListener('click', () => {
        this.toggleRightPanel();
      });
    }
    // Reset zoom event
    window.addEventListener('reset-zoom', () => {
      this.visualizationEngine.fitBounds();
    });
    
    // Render route event (from LLM integration)
    window.addEventListener('render-route', ((e: CustomEvent<{route: RouteState}>) => {
      this.visualizationEngine.displayRoute(e.detail.route);
    }) as EventListener);
    
    // Trigger search event
    window.addEventListener('trigger-search', ((e: CustomEvent<{query: string}>) => {
      // This will be handled by UI Manager's search handler
      const searchInput = document.getElementById('search-input') as HTMLInputElement;
      if (searchInput) {
        searchInput.value = e.detail.query;
        searchInput.dispatchEvent(new Event('input'));
      }
    }) as EventListener);
    
    // Relevance tab listener - reload GA data when tab is shown (in case persona changed)
    const relevanceTab = document.getElementById('relevance-tab');
    if (relevanceTab) {
      relevanceTab.addEventListener('shown.bs.tab', () => {
        if (this.currentSelectedIcao) {
          this.loadGARelevanceData(this.currentSelectedIcao);
        }
      });
    }
    
    // Persona selector listener - reload GA relevance data when persona changes
    const personaSelector = document.getElementById('persona-selector');
    if (personaSelector) {
      personaSelector.addEventListener('change', () => {
        // Check if relevance tab is currently active and an airport is selected
        const relevancePanel = document.getElementById('relevance-panel');
        if (relevancePanel?.classList.contains('show') && this.currentSelectedIcao) {
          this.loadGARelevanceData(this.currentSelectedIcao);
        }
      });
    }
    
    // Display airport details event
    window.addEventListener('display-airport-details', ((e: Event) => {
      const customEvent = e as CustomEvent<{
        detail: any;
        procedures: any[];
        runways: any[];
        aipEntries: any[];
        rules: any;
      }>;
      this.displayAirportDetails(customEvent.detail);
    }) as EventListener);
    
    // Map move/zoom events for URL sync
    // Use a flag to prevent infinite loops
    const map = this.visualizationEngine.getMap();
    if (map) {
      // Debounce map view updates to prevent infinite loops
      let mapUpdateTimeout: number | null = null;
      
      map.on('moveend zoomend', () => {
        // Skip if we're updating from store (to prevent infinite loop)
        if (this.isUpdatingMapView) {
          return;
        }
        
        // Debounce to prevent rapid-fire updates
        if (mapUpdateTimeout) {
          clearTimeout(mapUpdateTimeout);
        }
        
        mapUpdateTimeout = window.setTimeout(() => {
          const center = map.getCenter();
          const zoom = map.getZoom();
          const store = this.store as any;
          const currentState = store.getState();
          
          // Only update if view actually changed
          const currentView = currentState.mapView;
          if (!currentView || 
              Math.abs(currentView.center[0] - center.lat) > 0.0001 ||
              Math.abs(currentView.center[1] - center.lng) > 0.0001 ||
              currentView.zoom !== zoom) {
            store.getState().setMapView({
              center: [center.lat, center.lng],
              zoom
            });
          }
        }, 300); // Debounce 300ms
        // URL sync will be handled separately
      });
    }
  }
  
  /**
   * Load initial state from URL parameters
   */
  private async loadInitialState(): Promise<void> {
    const urlParams = new URLSearchParams(window.location.search);
    
    // Load filters from URL
    const filters: Partial<FilterConfig> = {};
    
    if (urlParams.has('country')) {
      filters.country = urlParams.get('country')!;
    }
    
    if (urlParams.has('has_procedures')) {
      filters.has_procedures = urlParams.get('has_procedures') === 'true';
    }
    
    if (urlParams.has('has_aip_data')) {
      filters.has_aip_data = urlParams.get('has_aip_data') === 'true';
    }
    
    if (urlParams.has('has_hard_runway')) {
      filters.has_hard_runway = urlParams.get('has_hard_runway') === 'true';
    }
    
    if (urlParams.has('border_crossing_only') || urlParams.has('point_of_entry')) {
      filters.point_of_entry = true;
    }
    
    if (urlParams.has('max_airports')) {
      filters.limit = parseInt(urlParams.get('max_airports')!, 10);
    }
    
    // Apply filters if any (only if there are actual filter values)
    const hasFilters = Object.entries(filters).some(([key, value]) => value !== null && value !== undefined && value !== '');
    if (hasFilters) {
      const store = this.store as any;
      store.getState().setFilters(filters);
    }
    
    // Load legend mode
    if (urlParams.has('legend')) {
      const legendMode = urlParams.get('legend') as any;
      const store = this.store as any;
      store.getState().setLegendMode(legendMode);
    }
    
    // Load search query (don't trigger search automatically, just set the value)
    if (urlParams.has('search')) {
      const searchQuery = decodeURIComponent(urlParams.get('search')!);
      const store = this.store as any;
      store.getState().setSearchQuery(searchQuery);
      const searchInput = document.getElementById('search-input') as HTMLInputElement;
      if (searchInput) {
        searchInput.value = searchQuery;
      }
    }
    
    // Load map view (skip store update to avoid loop, just set the view directly)
    if (urlParams.has('center') && urlParams.has('zoom')) {
      const centerParts = urlParams.get('center')!.split(',');
      if (centerParts.length === 2) {
        const lat = parseFloat(centerParts[0]);
        const lng = parseFloat(centerParts[1]);
        const zoom = parseInt(urlParams.get('zoom')!, 10);
        
        if (!isNaN(lat) && !isNaN(lng) && !isNaN(zoom)) {
          // Don't update store during init to avoid loops, just set view
          this.isUpdatingMapView = true;
          this.visualizationEngine.setView(lat, lng, zoom);
          setTimeout(() => {
            this.isUpdatingMapView = false;
            // Now update store
            const store = this.store as any;
            store.getState().setMapView({ center: [lat, lng], zoom });
          }, 100);
        }
      }
    }
    
    // Load initial airports if no search/route
    if (!urlParams.has('search') && !urlParams.has('route')) {
      await this.loadInitialAirports();
    }
  }
  
  /**
   * Load initial airports
   */
  private async loadInitialAirports(): Promise<void> {
    const state = this.store.getState();
    
    // Only load if filters are applied
    const hasFilters = Object.values(state.filters).some(value => 
      value !== null && value !== undefined && value !== ''
    );
    
    if (hasFilters) {
      this.store.getState().setLoading(true);
      try {
        const response = await this.apiAdapter.getAirports(state.filters);
        this.store.getState().setAirports(response.data);
        this.store.getState().setLoading(false);
      } catch (error: any) {
        console.error('Error loading initial airports:', error);
        this.store.getState().setError('Error loading airports: ' + (error.message || 'Unknown error'));
        this.store.getState().setLoading(false);
      }
    }
  }
  
  /**
   * Load procedure lines for airports
   */
  private async loadProcedureLines(airports: any[]): Promise<void> {
    // This will be called automatically when legend mode is 'procedure-precision'
    await this.visualizationEngine.loadBulkProcedureLines(airports, this.apiAdapter);
  }
  
  /**
   * Toggle right panel collapse
   */
  private toggleRightPanel(): void {
    const rightPanel = document.querySelector('.right-panel');
    const rightPanelCol = document.querySelector('.right-panel-col');
    const mapCol = document.querySelector('.map-column-col');
    const leftPanelCol = document.querySelector('.left-panel-col');

    if (rightPanel && rightPanelCol && mapCol && leftPanelCol) {
      // Toggle collapsed state
      const isCollapsed = rightPanel.classList.contains('collapsed');
      
      rightPanel.classList.toggle('collapsed');
      rightPanelCol.classList.toggle('collapsed');
      mapCol.classList.toggle('map-expanded');
      leftPanelCol.classList.toggle('with-expanded-map');

      console.log(`Right panel ${!isCollapsed ? 'collapsed' : 'expanded'}`);

      // Invalidate map size after panel resize (with delay to allow CSS transition)
      setTimeout(() => {
        this.invalidateMapSize();
      }, 300); // Match CSS transition duration
    }
  }
  
  /**
   * Invalidate map size (call after layout changes)
   */
  private invalidateMapSize(): void {
    const map = this.visualizationEngine.getMap();
    if (map && typeof map.invalidateSize === 'function') {
      map.invalidateSize();
    }
  }
  
  /**
   * Display airport details
   */
  private displayAirportDetails(data: {
    detail: any;
    procedures: any[];
    runways: any[];
    aipEntries: any[];
    rules: any;
  }): void {
    const airport = data.detail;
    const { procedures, runways, aipEntries, rules } = data;
    
    const infoContainer = document.getElementById('airport-info');
    const airportContent = document.getElementById('airport-content');
    const noSelectionContainer = document.getElementById('no-selection');
    
    if (!airport) {
      // Hide tabbed content, show "no selection" message
      if (airportContent) (airportContent as HTMLElement).style.display = 'none';
      if (noSelectionContainer) (noSelectionContainer as HTMLElement).style.display = 'block';
      return;
    }
    
    // Show tabbed content, hide "no selection" message
    if (airportContent) (airportContent as HTMLElement).style.display = 'flex';
    if (noSelectionContainer) (noSelectionContainer as HTMLElement).style.display = 'none';
    
    if (!infoContainer) return;
    
    let html = '';
    
    // Add links section
    const links: string[] = [];
    if (airport.home_link) {
      links.push(`<a href="${this.escapeAttribute(airport.home_link)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline-primary btn-sm me-2">
        <i class="fas fa-home"></i> Home Page
      </a>`);
    }
    if (airport.wikipedia_link) {
      links.push(`<a href="${this.escapeAttribute(airport.wikipedia_link)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline-info btn-sm me-2">
        <i class="fab fa-wikipedia-w"></i> Wikipedia
      </a>`);
    }
    
    // Always add EuroGA and Airfield Directory links
    links.push(`<a href="https://airports.euroga.org/search.php?icao=${this.escapeAttribute(airport.ident || '')}" target="_blank" rel="noopener noreferrer" class="btn btn-outline-success btn-sm me-2">
      <i class="fas fa-plane"></i> EuroGA
    </a>`);
    
    links.push(`<a href="https://airfield.directory/airfield/${this.escapeAttribute(airport.ident || '')}" target="_blank" rel="noopener noreferrer" class="btn btn-outline-success btn-sm me-2">
      <i class="fas fa-plane"></i> Airfield Directory
    </a>`);
    
    // Add Google Maps "Nearby Restaurants" link
    if (airport.latitude_deg !== undefined && airport.longitude_deg !== undefined) {
      const q = encodeURIComponent('restaurants');
      const zoom = 14;
      const lat = airport.latitude_deg;
      const lon = airport.longitude_deg;
      links.push(`<a href="https://www.google.com/maps/search/${q}/@${lat},${lon},${zoom}z" target="_blank" rel="noopener noreferrer" class="btn btn-outline-danger btn-sm me-2">
        <i class="fas fa-utensils"></i> Nearby Restaurants
      </a>`);
    }
    
    if (links.length > 0) {
      html += `
        <div class="airport-detail-section">
          <h6><i class="fas fa-link"></i> Links</h6>
          <div class="d-flex flex-wrap gap-2">
            ${links.join('')}
          </div>
        </div>
      `;
    }
    
    // Add basic information
    html += `
      <div class="airport-detail-section">
        <h6><i class="fas fa-info-circle"></i> Basic Information</h6>
        <table class="table table-sm">
          <tr><td><strong>ICAO:</strong></td><td>${this.escapeHtml(airport.ident || 'N/A')}</td></tr>
          <tr><td><strong>Name:</strong></td><td>${this.escapeHtml(airport.name || 'N/A')}</td></tr>
          <tr><td><strong>Type:</strong></td><td>${this.escapeHtml(airport.type || 'N/A')}</td></tr>
          <tr><td><strong>Country:</strong></td><td>${this.escapeHtml(airport.iso_country || 'N/A')}</td></tr>
          <tr><td><strong>Region:</strong></td><td>${this.escapeHtml(airport.iso_region || 'N/A')}</td></tr>
          <tr><td><strong>Municipality:</strong></td><td>${this.escapeHtml(airport.municipality || 'N/A')}</td></tr>
          <tr><td><strong>Coordinates:</strong></td><td>${airport.latitude_deg?.toFixed(4) || 'N/A'}, ${airport.longitude_deg?.toFixed(4) || 'N/A'}</td></tr>
          <tr><td><strong>Elevation:</strong></td><td>${airport.elevation_ft || 'N/A'} ft</td></tr>
        </table>
      </div>
    `;
    
    // Add runways section
    if (runways && runways.length > 0) {
      html += `
        <div class="airport-detail-section">
          <h6><i class="fas fa-plane"></i> Runways (${runways.length})</h6>
      `;
      
      runways.forEach((runway: any) => {
        html += `
          <div class="runway-info">
            <strong>${this.escapeHtml(runway.le_ident || 'N/A')}/${this.escapeHtml(runway.he_ident || 'N/A')}</strong><br>
            Length: ${runway.length_ft || 'N/A'} ft<br>
            Width: ${runway.width_ft || 'N/A'} ft<br>
            Surface: ${this.escapeHtml(runway.surface || 'N/A')}<br>
            ${runway.lighted ? 'Lighted' : 'Not lighted'}
          </div>
        `;
      });
      
      html += '</div>';
    }
    
    // Add procedures section
    if (procedures && procedures.length > 0) {
      html += `
        <div class="airport-detail-section">
          <h6><i class="fas fa-route"></i> Procedures (${procedures.length})</h6>
      `;
      
      // Group procedures by type
      const proceduresByType: Record<string, any[]> = {};
      procedures.forEach((proc: any) => {
        const type = proc.procedure_type || 'Unknown';
        if (!proceduresByType[type]) {
          proceduresByType[type] = [];
        }
        proceduresByType[type].push(proc);
      });
      
      Object.entries(proceduresByType).forEach(([type, procs]) => {
        html += `<h6 class="mt-2">${this.escapeHtml(type.charAt(0).toUpperCase() + type.slice(1))} (${procs.length})</h6>`;
        procs.forEach((proc: any) => {
          const badgeClass = this.getProcedureBadgeClass(proc.procedure_type, proc.approach_type);
          html += `<span class="badge ${badgeClass} procedure-badge">${this.escapeHtml(proc.name || 'Unnamed')}</span>`;
        });
      });
      
      html += '</div>';
    }
    
    // Add sources section
    if (airport.sources && Array.isArray(airport.sources) && airport.sources.length > 0) {
      html += `
        <div class="airport-detail-section">
          <h6><i class="fas fa-database"></i> Data Sources</h6>
          ${airport.sources.map((source: any) => `<span class="badge bg-secondary me-1">${this.escapeHtml(String(source))}</span>`).join('')}
        </div>
      `;
    }
    
    infoContainer.innerHTML = html;
    
    // Display AIP data and rules
    this.displayAIPData(aipEntries);
    this.displayCountryRules(rules, airport.iso_country);
    
    // Track selected airport and load GA relevance data
    this.currentSelectedIcao = airport.ident;
    this.loadGARelevanceData(airport.ident);
  }
  
  /**
   * Display AIP data
   */
  private displayAIPData(aipEntries: any[]): void {
    const aipContentContainer = document.getElementById('aip-data-content');
    
    if (!aipContentContainer) return;
    
    if (!aipEntries || aipEntries.length === 0) {
      aipContentContainer.innerHTML = '<div class="text-center text-muted py-4"><i class="fas fa-info-circle"></i> No AIP data available</div>';
      return;
    }
    
    // Group by standardized field section
    const entriesBySection: Record<string, any[]> = {};
    aipEntries.forEach((entry: any) => {
      let section = 'Other';
      if (entry.std_field_id) {
        const sectionId = Math.floor(entry.std_field_id / 100) * 100;
        switch (sectionId) {
          case 200: section = 'Admin'; break;
          case 300: section = 'Operational'; break;
          case 400: section = 'Handling'; break;
          case 500: section = 'Passenger'; break;
          default: section = 'Other'; break;
        }
      } else {
        section = entry.section || 'Other';
      }
      
      if (!entriesBySection[section]) {
        entriesBySection[section] = [];
      }
      entriesBySection[section].push(entry);
    });
    
    let html = '';
    Object.entries(entriesBySection).forEach(([section, entries]) => {
      const sectionId = `aip-section-${section.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
      html += `
        <div class="aip-section" data-section="${this.escapeAttribute(section)}">
          <div class="aip-section-header" onclick="window.toggleAIPSection('${sectionId}')">
            <span>
              <i class="fas fa-chevron-right aip-section-toggle" id="toggle-${sectionId}"></i>
              ${this.escapeHtml(section)} (${entries.length})
            </span>
          </div>
          <div class="aip-section-content" id="${sectionId}">
      `;
      
      entries.forEach((entry: any) => {
        const fieldName = entry.std_field || entry.field;
        const entryId = `aip-entry-${entry.std_field_id || entry.field || Math.random()}`;
        html += `
          <div class="aip-entry" id="${entryId}" data-field="${this.escapeAttribute(fieldName || '')}" data-value="${this.escapeAttribute(entry.value || '')}">
            <strong>${this.escapeHtml(fieldName || 'Unknown')}:</strong> ${this.escapeHtml(entry.value || 'N/A')}
            ${entry.alt_value ? `<br><em>${this.escapeHtml(entry.alt_value)}</em>` : ''}
          </div>
        `;
      });
      
      html += `
          </div>
        </div>
      `;
    });
    
    aipContentContainer.innerHTML = html;
    this.initializeAIPFilter();
  }
  
  /**
   * Display country rules
   */
  private displayCountryRules(rulesData: any, countryCode?: string): void {
    const rulesContainer = document.getElementById('rules-content');
    const rulesSummary = document.getElementById('rules-summary');
    
    if (!rulesContainer) return;
    
    const code = countryCode ? countryCode.toUpperCase() : null;
    
    if (!code) {
      if (rulesSummary) {
        rulesSummary.textContent = '';
      }
      rulesContainer.innerHTML = '<div class="text-center text-muted py-4"><i class="fas fa-info-circle"></i> No country information available for this airport.</div>';
      return;
    }
    
    if (!rulesData || !Array.isArray(rulesData.categories) || rulesData.categories.length === 0) {
      if (rulesSummary) {
        rulesSummary.textContent = `No published rules available for ${code}.`;
      }
      rulesContainer.innerHTML = '<div class="text-center text-muted py-4"><i class="fas fa-info-circle"></i> No rules available for this country.</div>';
      return;
    }
    
    if (rulesSummary) {
      const totalCategories = rulesData.categories.length;
      rulesSummary.textContent = `Rules for ${code}: ${rulesData.total_rules || 0} answers across ${totalCategories} ${totalCategories === 1 ? 'category' : 'categories'}.`;
    }
    
    let html = '';
    
    rulesData.categories.forEach((category: any) => {
      const sectionId = this.buildRuleSectionId(code, category.name);
      const toggleId = `rules-toggle-${sectionId}`;
      
      html += `
        <div class="rules-section" data-category="${this.escapeAttribute(category.name || 'General')}">
          <div class="rules-section-header" onclick="window.toggleRuleSection('${sectionId}')">
            <span>
              <i class="fas fa-chevron-right rules-section-toggle" id="${toggleId}"></i>
              ${this.escapeHtml(category.name || 'General')} (${category.count || 0})
            </span>
          </div>
          <div class="rules-section-content" id="${sectionId}">
      `;
      
      if (category.rules && Array.isArray(category.rules)) {
        category.rules.forEach((rule: any) => {
          const question = this.escapeHtml(rule.question_text || 'Untitled rule');
          const answerText = this.escapeHtml(this.stripHtml(rule.answer_html) || 'No answer available.');
          const tagsHtml = (rule.tags || [])
            .map((tag: any) => `<span class="badge bg-secondary">${this.escapeHtml(String(tag))}</span>`)
            .join(' ');
          const linksHtml = (rule.links || [])
            .map((link: any) => {
              const rawUrl = String(link || '');
              let label = rawUrl;
              try {
                const parsed = new URL(rawUrl, window.location.origin);
                label = parsed.hostname.replace(/^www\./i, '') || parsed.href;
              } catch (e) {
                label = rawUrl;
              }
              const safeUrl = this.escapeAttribute(rawUrl);
              return `<a href="${safeUrl}" class="me-2" target="_blank" rel="noopener noreferrer">${this.escapeHtml(label)}</a>`;
            })
            .join(' ');
          
          const metaParts: string[] = [];
          if (rule.last_reviewed) {
            metaParts.push(`Last reviewed: ${this.escapeHtml(rule.last_reviewed)}`);
          }
          if (rule.confidence) {
            metaParts.push(`Confidence: ${this.escapeHtml(rule.confidence)}`);
          }
          
          html += `
            <div class="rules-entry">
              <span class="rule-question"><i class="fas fa-gavel me-2"></i>${question}</span>
              <div class="rule-answer">${answerText}</div>
              ${tagsHtml ? `<div class="mb-2">${tagsHtml}</div>` : ''}
              ${linksHtml ? `<div class="rule-links"><i class="fas fa-link me-1"></i>${linksHtml}</div>` : ''}
              ${metaParts.length ? `<div class="text-muted small">${metaParts.join(' • ')}</div>` : ''}
            </div>
          `;
        });
      }
      
      html += `
          </div>
        </div>
      `;
    });
    
    rulesContainer.innerHTML = html;
    this.initializeRuleSections();
    this.initializeRulesFilter();
  }
  
  /**
   * Helper methods
   */
  private escapeHtml(value: any): string {
    if (value === null || value === undefined) {
      return '';
    }
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  
  private escapeAttribute(value: any): string {
    return this.escapeHtml(value);
  }
  
  private stripHtml(html: any): string {
    if (!html) {
      return '';
    }
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = String(html);
    return tempDiv.textContent || tempDiv.innerText || '';
  }
  
  private getProcedureBadgeClass(procedureType?: string, approachType?: string): string {
    if (procedureType === 'approach') {
      switch (approachType?.toUpperCase()) {
        case 'ILS': return 'bg-success';
        case 'RNAV': return 'bg-primary';
        case 'VOR': return 'bg-info';
        case 'NDB': return 'bg-warning';
        default: return 'bg-secondary';
      }
    } else if (procedureType === 'departure') {
      return 'bg-danger';
    } else if (procedureType === 'arrival') {
      return 'bg-warning';
    }
    return 'bg-secondary';
  }
  
  private buildRuleSectionId(countryCode: string, categoryName?: string): string {
    const slug = (categoryName || 'general')
      .toString()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
    return `rules-${countryCode}-${slug || 'general'}`;
  }
  
  /**
   * Load and display GA relevance data for an airport
   */
  private async loadGARelevanceData(icao: string): Promise<void> {
    const loadingEl = document.getElementById('relevance-loading');
    const dataEl = document.getElementById('relevance-data');
    const noDataEl = document.getElementById('relevance-no-data');
    
    if (!loadingEl || !dataEl || !noDataEl) return;
    
    // Show loading state
    loadingEl.style.display = 'block';
    dataEl.style.display = 'none';
    noDataEl.style.display = 'none';
    
    try {
      const persona = useStore.getState().ga.selectedPersona;
      const summary = await this.apiAdapter.getGASummary(icao, persona);
      
      if (!summary.has_data) {
        loadingEl.style.display = 'none';
        noDataEl.style.display = 'block';
        return;
      }
      
      // Get feature display names from config
      const config = useStore.getState().ga.config;
      const displayNames = config?.feature_display_names || {};
      const descriptions = config?.feature_descriptions || {};
      
      // Build the HTML
      let html = '';
      
      // Overall score section
      html += `
        <div class="airport-detail-section">
          <h6><i class="fas fa-star"></i> Overall Score</h6>
          <div class="d-flex align-items-center gap-3 mb-2">
            <div class="relevance-score-badge" style="
              background: linear-gradient(135deg, ${this.getScoreColor(summary.score)} 0%, ${this.getScoreColorDark(summary.score)} 100%);
              color: white;
              padding: 8px 16px;
              border-radius: 8px;
              font-size: 1.5em;
              font-weight: bold;
            ">
              ${summary.score !== null ? (summary.score * 100).toFixed(0) : 'N/A'}%
            </div>
            <div class="text-muted small">
              Based on ${summary.review_count || 0} review${summary.review_count !== 1 ? 's' : ''}
              ${summary.last_review_utc ? `<br>Last review: ${this.formatReviewDate(summary.last_review_utc)}` : ''}
            </div>
          </div>
        </div>
      `;
      
      // Feature breakdown section
      if (summary.features) {
        html += `
          <div class="airport-detail-section">
            <h6><i class="fas fa-chart-bar"></i> Feature Breakdown</h6>
            <table class="table table-sm">
        `;
        
        for (const [featureName, value] of Object.entries(summary.features)) {
          const displayName = displayNames[featureName] || featureName.replace(/_/g, ' ').replace('ga ', '');
          const description = descriptions[featureName] || '';
          const percentage = value !== null ? (value * 100).toFixed(0) : 'N/A';
          const barWidth = value !== null ? Math.max(5, value * 100) : 0;
          const barColor = value !== null ? this.getScoreColor(value) : '#ccc';
          
          html += `
            <tr title="${this.escapeAttribute(description)}">
              <td style="width: 40%"><strong>${this.escapeHtml(displayName)}</strong></td>
              <td style="width: 45%">
                <div class="progress" style="height: 8px;">
                  <div class="progress-bar" role="progressbar" 
                       style="width: ${barWidth}%; background-color: ${barColor};"
                       aria-valuenow="${barWidth}" aria-valuemin="0" aria-valuemax="100">
                  </div>
                </div>
              </td>
              <td style="width: 15%; text-align: right;">${percentage}${value !== null ? '%' : ''}</td>
            </tr>
          `;
        }
        
        html += `
            </table>
          </div>
        `;
      }
      
      // Tags section
      if (summary.tags && summary.tags.length > 0) {
        html += `
          <div class="airport-detail-section">
            <h6><i class="fas fa-tags"></i> Review Tags</h6>
            <div class="d-flex flex-wrap gap-1">
              ${summary.tags.map(tag => 
                `<span class="badge bg-secondary">${this.escapeHtml(tag)}</span>`
              ).join('')}
            </div>
          </div>
        `;
      }
      
      // Summary text section
      if (summary.summary_text) {
        html += `
          <div class="airport-detail-section">
            <h6><i class="fas fa-quote-left"></i> Summary</h6>
            <p class="text-muted small">${this.escapeHtml(summary.summary_text)}</p>
          </div>
        `;
      }
      
      // Notification/hassle section
      if (summary.notification_summary || summary.hassle_level) {
        html += `
          <div class="airport-detail-section">
            <h6><i class="fas fa-clipboard-list"></i> Requirements</h6>
        `;
        if (summary.hassle_level) {
          html += `<p><strong>Hassle Level:</strong> ${this.escapeHtml(summary.hassle_level)}</p>`;
        }
        if (summary.notification_summary) {
          html += `<p class="text-muted small">${this.escapeHtml(summary.notification_summary)}</p>`;
        }
        html += `</div>`;
      }
      
      // Hotel/Restaurant info
      if (summary.hotel_info || summary.restaurant_info) {
        html += `
          <div class="airport-detail-section">
            <h6><i class="fas fa-concierge-bell"></i> Amenities</h6>
        `;
        if (summary.hotel_info) {
          html += `<p><strong>Hotels:</strong> ${this.escapeHtml(summary.hotel_info)}</p>`;
        }
        if (summary.restaurant_info) {
          html += `<p><strong>Restaurants:</strong> ${this.escapeHtml(summary.restaurant_info)}</p>`;
        }
        html += `</div>`;
      }
      
      dataEl.innerHTML = html;
      loadingEl.style.display = 'none';
      dataEl.style.display = 'block';
      
    } catch (error) {
      console.error('[Application] Failed to load GA relevance data:', error);
      loadingEl.style.display = 'none';
      noDataEl.style.display = 'block';
    }
  }
  
  /**
   * Get color based on score (0-1)
   */
  private getScoreColor(score: number | null): string {
    if (score === null) return '#95a5a6';
    if (score >= 0.75) return '#27ae60';
    if (score >= 0.50) return '#3498db';
    if (score >= 0.25) return '#f39c12';
    return '#e74c3c';
  }
  
  /**
   * Get darker color for gradient
   */
  private getScoreColorDark(score: number | null): string {
    if (score === null) return '#7f8c8d';
    if (score >= 0.75) return '#1e8449';
    if (score >= 0.50) return '#2471a3';
    if (score >= 0.25) return '#d68910';
    return '#c0392b';
  }
  
  /**
   * Format review date from various formats
   * Handles formats like "2025-08-28 07:27:20 UTC"
   */
  private formatReviewDate(dateStr: string): string {
    try {
      // Remove "UTC" suffix and replace space with "T" for ISO format
      const normalized = dateStr
        .replace(' UTC', 'Z')
        .replace(' ', 'T');
      
      const date = new Date(normalized);
      
      if (isNaN(date.getTime())) {
        // If still invalid, try parsing as-is without the UTC part
        const withoutUtc = dateStr.replace(' UTC', '').replace('UTC', '');
        const fallbackDate = new Date(withoutUtc);
        
        if (isNaN(fallbackDate.getTime())) {
          return dateStr; // Return original if all parsing fails
        }
        return fallbackDate.toLocaleDateString();
      }
      
      return date.toLocaleDateString();
    } catch {
      return dateStr; // Return original on error
    }
  }
  
  /**
   * Initialize AIP filter
   */
  private initializeAIPFilter(): void {
    const filterInput = document.getElementById('aip-filter-input');
    const clearButton = document.getElementById('aip-filter-clear');
    
    if (!filterInput) return;
    
    // Remove existing listeners by cloning and replacing
    const newFilterInput = filterInput.cloneNode(true) as HTMLInputElement;
    filterInput.parentNode?.replaceChild(newFilterInput, filterInput);
    
    const newClearButton = clearButton ? (clearButton.cloneNode(true) as HTMLButtonElement) : null;
    if (clearButton && newClearButton) {
      clearButton.parentNode?.replaceChild(newClearButton, clearButton);
    }
    
    newFilterInput.addEventListener('input', (e) => {
      this.handleAIPFilter(e as any);
    });
    
    if (newClearButton) {
      newClearButton.addEventListener('click', () => {
        newFilterInput.value = '';
        this.handleAIPFilter({ target: { value: '' } } as any);
      });
    }
    
    // Load saved section states
    this.loadAIPSectionStates();
  }
  
  /**
   * Handle AIP filter
   */
  private handleAIPFilter(event: { target: { value: string } }): void {
    const filterText = (event.target.value || '').toLowerCase();
    const entries = document.querySelectorAll('.aip-entry');
    
    entries.forEach((entry) => {
      const fieldName = (entry as HTMLElement).dataset.field || '';
      const value = (entry as HTMLElement).dataset.value || '';
      const altValue = entry.querySelector('em')?.textContent || '';
      
      const matches = fieldName.toLowerCase().includes(filterText) || 
                     value.toLowerCase().includes(filterText) ||
                     altValue.toLowerCase().includes(filterText);
      
      if (matches) {
        entry.classList.remove('hidden');
        if (filterText) {
          entry.classList.add('highlight');
        } else {
          entry.classList.remove('highlight');
        }
        
        const section = entry.closest('.aip-section');
        if (section) {
          const content = section.querySelector('.aip-section-content');
          const toggle = section.querySelector('.aip-section-toggle');
          if (content) content.classList.add('expanded');
          if (toggle) toggle.classList.add('expanded');
        }
      } else {
        entry.classList.add('hidden');
        entry.classList.remove('highlight');
      }
    });
    
    // Hide sections that have no visible entries
    const sections = document.querySelectorAll('.aip-section');
    sections.forEach((section) => {
      const visibleEntries = section.querySelectorAll('.aip-entry:not(.hidden)');
      (section as HTMLElement).style.display = visibleEntries.length === 0 ? 'none' : 'block';
    });
  }
  
  /**
   * Load AIP section states
   */
  private loadAIPSectionStates(): void {
    try {
      const states = JSON.parse(localStorage.getItem('aipSectionStates') || '{}');
      Object.entries(states).forEach(([sectionId, isExpanded]) => {
        const content = document.getElementById(sectionId);
        const toggle = document.getElementById(`toggle-${sectionId}`);
        if (content && toggle) {
          if (isExpanded) {
            content.classList.add('expanded');
            toggle.classList.add('expanded');
          } else {
            content.classList.remove('expanded');
            toggle.classList.remove('expanded');
          }
        }
      });
    } catch (e) {
      console.error('Error loading AIP section states:', e);
    }
  }
  
  /**
   * Initialize rule sections
   */
  private initializeRuleSections(): void {
    this.loadRuleSectionStates();
  }
  
  /**
   * Load rule section states
   */
  private loadRuleSectionStates(): void {
    try {
      const sections = document.querySelectorAll('.rules-section-content');
      if (!sections.length) return;
      
      const states = JSON.parse(localStorage.getItem('ruleSectionStates') || '{}');
      const hasStoredState = Object.keys(states).length > 0;
      
      sections.forEach((section, index) => {
        const sectionId = (section as HTMLElement).id;
        const toggle = document.getElementById(`rules-toggle-${sectionId}`);
        const isExpanded = states[sectionId];
        const shouldExpand = isExpanded === true || (!hasStoredState && index === 0);
        
        if (shouldExpand) {
          section.classList.add('expanded');
          if (toggle) toggle.classList.add('expanded');
          if (!hasStoredState && index === 0) {
            this.saveRuleSectionState(sectionId, true);
          }
        } else {
          section.classList.remove('expanded');
          if (toggle) toggle.classList.remove('expanded');
        }
      });
    } catch (e) {
      console.error('Error loading rule section states:', e);
    }
  }
  
  /**
   * Save rule section state
   */
  private saveRuleSectionState(sectionId: string, isExpanded: boolean): void {
    try {
      const states = JSON.parse(localStorage.getItem('ruleSectionStates') || '{}');
      states[sectionId] = isExpanded;
      localStorage.setItem('ruleSectionStates', JSON.stringify(states));
    } catch (e) {
      console.error('Error saving rule section state:', e);
    }
  }
  
  /**
   * Initialize rules filter
   */
  private initializeRulesFilter(): void {
    const filterInput = document.getElementById('rules-filter-input');
    const clearButton = document.getElementById('rules-filter-clear');
    
    if (!filterInput) return;
    
    // Remove existing listeners by cloning and replacing
    const newFilterInput = filterInput.cloneNode(true) as HTMLInputElement;
    filterInput.parentNode?.replaceChild(newFilterInput, filterInput);
    
    const newClearButton = clearButton ? (clearButton.cloneNode(true) as HTMLButtonElement) : null;
    if (clearButton && newClearButton) {
      clearButton.parentNode?.replaceChild(newClearButton, clearButton);
    }
    
    newFilterInput.value = ''; // Clear any stale value
    
    newFilterInput.addEventListener('input', (e) => {
      this.handleRulesFilter(e as any);
    });
    
    if (newClearButton) {
      newClearButton.addEventListener('click', () => {
        newFilterInput.value = '';
        this.handleRulesFilter({ target: { value: '' } } as any);
      });
    }
  }
  
  /**
   * Handle rules filter
   */
  private handleRulesFilter(event: { target: { value: string } }): void {
    const filterText = (event.target.value || '').toLowerCase();
    const entries = document.querySelectorAll('.rules-entry');
    
    const matchedSections = new Set<string>();
    
    entries.forEach((entry) => {
      const question = entry.querySelector('.rule-question')?.textContent || '';
      const answer = entry.querySelector('.rule-answer')?.textContent || '';
      const tags = Array.from(entry.querySelectorAll('.badge')).map(b => b.textContent || '').join(' ');
      const meta = entry.querySelector('.text-muted')?.textContent || '';
      const category = entry.closest('.rules-section')?.getAttribute('data-category') || '';
      
      const combined = `${question} ${answer} ${tags} ${meta} ${category}`.toLowerCase();
      const matches = combined.includes(filterText);
      
      if (matches) {
        entry.classList.remove('hidden');
        entry.classList.toggle('highlight', Boolean(filterText));
        const sectionContent = entry.closest('.rules-section-content');
        if (sectionContent) {
          matchedSections.add((sectionContent as HTMLElement).id);
        }
      } else {
        entry.classList.add('hidden');
        entry.classList.remove('highlight');
      }
    });
    
    // Expand matched sections, collapse others if filter active
    const sections = document.querySelectorAll('.rules-section-content');
    sections.forEach((section) => {
      const sectionId = (section as HTMLElement).id;
      const toggle = document.getElementById(`rules-toggle-${sectionId}`);
      const visibleEntries = section.querySelectorAll('.rules-entry:not(.hidden)');
      const sectionElement = section.parentElement as HTMLElement;
      
      if (filterText) {
        const shouldExpand = matchedSections.has(sectionId) || visibleEntries.length > 0;
        if (shouldExpand) {
          section.classList.add('expanded');
          if (toggle) toggle.classList.add('expanded');
        } else {
          section.classList.remove('expanded');
          if (toggle) toggle.classList.remove('expanded');
        }
        if (sectionElement) {
          sectionElement.style.display = visibleEntries.length > 0 ? 'block' : 'none';
        }
      } else {
        // Restore visibility when filter cleared
        if (sectionElement) {
          sectionElement.style.display = 'block';
        }
      }
    });
  }
  
  /**
   * Public method to handle LLM visualizations (for chatbot integration)
   */
  handleLLMVisualization(visualization: any): void {
    this.llmIntegration.handleVisualization(visualization);
  }
}

/**
 * Initialize application when DOM is ready
 */
let app: Application | null = null;

async function initApp(): Promise<void> {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      app = new Application();
      app.init();
    });
  } else {
    app = new Application();
    await app.init();
  }
}

// Export for use in chatbot
(window as any).handleLLMVisualization = (visualization: any) => {
  if (app) {
    app.handleLLMVisualization(visualization);
  } else {
    console.warn('Application not initialized yet');
  }
};

// Global functions for HTML onclick handlers
(window as any).toggleAIPSection = (sectionId: string) => {
  const content = document.getElementById(sectionId);
  const toggle = document.getElementById(`toggle-${sectionId}`);
  if (!content || !toggle) return;
  
  const isExpanded = content.classList.contains('expanded');
  if (isExpanded) {
    content.classList.remove('expanded');
    toggle.classList.remove('expanded');
  } else {
    content.classList.add('expanded');
    toggle.classList.add('expanded');
  }
  
  // Save state
  try {
    const states = JSON.parse(localStorage.getItem('aipSectionStates') || '{}');
    states[sectionId] = !isExpanded;
    localStorage.setItem('aipSectionStates', JSON.stringify(states));
  } catch (e) {
    console.error('Error saving AIP section state:', e);
  }
};

(window as any).toggleRuleSection = (sectionId: string) => {
  const content = document.getElementById(sectionId);
  const toggle = document.getElementById(`rules-toggle-${sectionId}`);
  if (!content || !toggle) return;
  
  const isExpanded = content.classList.contains('expanded');
  if (isExpanded) {
    content.classList.remove('expanded');
    toggle.classList.remove('expanded');
  } else {
    content.classList.add('expanded');
    toggle.classList.add('expanded');
  }
  
  // Save state
  try {
    const states = JSON.parse(localStorage.getItem('ruleSectionStates') || '{}');
    states[sectionId] = !isExpanded;
    localStorage.setItem('ruleSectionStates', JSON.stringify(states));
  } catch (e) {
    console.error('Error saving rule section state:', e);
  }
};

// Start application
initApp().catch(error => {
  console.error('Failed to initialize application:', error);
});

// Hot Module Replacement (HMR) support
if (import.meta.hot) {
  import.meta.hot.accept(() => {
    console.log('HMR update detected - preserving application state');
    // Don't reload the page, let Vite handle the module updates
  });

  // Dispose handler to clean up before updates
  import.meta.hot.dispose(() => {
    console.log('HMR disposing old module');
  });
}

