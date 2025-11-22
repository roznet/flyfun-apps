/**
 * Main application entry point
 * Initializes all components and wires everything together
 */

import { useStore } from './store/store';
import { APIAdapter } from './adapters/api-adapter';
import { VisualizationEngine } from './engines/visualization-engine';
import { UIManager } from './managers/ui-manager';
import { LLMIntegration } from './adapters/llm-integration';
import type { AppState, RouteState, MapView, FilterConfig } from './store/types';

// Global instances (for debugging/window access)
declare global {
  interface Window {
    appState: ReturnType<typeof useStore>;
    visualizationEngine: VisualizationEngine;
    uiManager: UIManager;
    llmIntegration: LLMIntegration;
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
    
    // Initialize LLM integration
    this.llmIntegration = new LLMIntegration(this.store, this.apiAdapter, this.uiManager);
    
    // Expose to window for debugging
    window.appState = this.store as any;
    window.visualizationEngine = this.visualizationEngine;
    window.uiManager = this.uiManager;
    window.llmIntegration = this.llmIntegration;
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
    let lastHighlightsHash: string = '';
    let lastRouteHash: string = '';
    
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
          if (state.filteredAirports !== lastAirports || state.visualization.legendMode !== lastLegendMode) {
            this.visualizationEngine.updateMarkers(
              state.filteredAirports,
              state.visualization.legendMode
            );
            
            lastAirports = state.filteredAirports;
            lastLegendMode = state.visualization.legendMode;
          }
          
          // Update highlights (only if changed)
          let highlights: any = state.visualization.highlights;
          if (!highlights) {
            highlights = new globalThis.Map();
          } else if (!(highlights instanceof globalThis.Map)) {
            // Convert plain object to Map if needed (from Zustand serialization)
            const entries = Object.entries(highlights as Record<string, any>);
            highlights = new globalThis.Map(entries);
          }
          const highlightsHash = JSON.stringify(Array.from((highlights as globalThis.Map<string, any>).entries()));
          if (highlightsHash !== lastHighlightsHash) {
            this.visualizationEngine.updateHighlights(highlights as any);
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
          
          // Update procedure lines if needed
          if (state.visualization.legendMode === 'procedure-precision' && state.visualization.showProcedureLines) {
            this.loadProcedureLines(state.filteredAirports);
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
   * Display airport details (placeholder - will be implemented)
   */
  private displayAirportDetails(data: {
    detail: any;
    procedures: any[];
    runways: any[];
    aipEntries: any[];
    rules: any;
  }): void {
    // TODO: Implement airport details panel display
    // This should render the details in the right panel
    console.log('Display airport details:', data);
    
    // For now, just show that it's working
    const infoContainer = document.getElementById('airport-info');
    if (infoContainer) {
      infoContainer.innerHTML = `
        <div class="text-center">
          <p>Airport details loading...</p>
          <small class="text-muted">This will be fully implemented in next phase</small>
        </div>
      `;
    }
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

// Start application
initApp().catch(error => {
  console.error('Failed to initialize application:', error);
});

