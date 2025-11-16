/**
 * Chat-Map Integration
 * Handles visualization of chatbot results on the Leaflet map
 */

class ChatMapIntegration {
    constructor(map) {
        this.map = map;
        this.chatMarkers = [];
        this.chatLayers = L.layerGroup();
        this.chatLayers.addTo(this.map);

        // Keep track of visualization state
        this.currentVisualization = null;
        this.isFilteredMode = false; // Track if we're showing only chat results
        this.chatAirports = []; // Store full airport data for filtering
    }

    /**
     * Visualize data on the map based on chatbot response
     */
    visualizeData(visualization) {
        if (!visualization) return;

        // Prefer using existing UI pipelines via FilterManager for consistency:
        // - route_with_markers → trigger route search with from/to
        // - marker_with_details → trigger search by ident
        // This function needs to convert the visualization object to a call to set up the filtermanager.

        // Helper to use route flow through FilterManager
        const handleRouteViaFilters = (routeObj) => {
            const fromIcao = routeObj?.from?.icao;
            const toIcao = routeObj?.to?.icao;
            if (fromIcao && toIcao && typeof filterManager !== 'undefined' && filterManager?.handleRouteSearch) {
                // Let the unified route pipeline render markers/route and apply filters
                try {
                    // Do not rely on search-input parsing; call the route handler directly
                    filterManager.handleRouteSearch([fromIcao, toIcao]);
                    return true;
                } catch (e) {
                    console.warn('Route handoff to FilterManager failed, falling back to overlay:', e);
                }
            }
            return false;
        };

        // Helper to use search flow through FilterManager
        const handleIdentViaSearch = (ident) => {
            if (ident && typeof filterManager !== 'undefined' && filterManager?.handleSearch) {
                try {
                    // Update search box for UX coherence
                    const searchInput = document.getElementById('search-input');
                    if (searchInput) searchInput.value = ident;
                    filterManager.handleSearch(ident);
                    return true;
                } catch (e) {
                    console.warn('Ident handoff to FilterManager failed, falling back to overlay:', e);
                }
            }
            return false;
        };

        // Array visualizations: prefer the first route or marker-with-details item
        if (Array.isArray(visualization)) {
            // Try to find a route visualization first
            const firstRoute = visualization.find(v => v && v.type === 'route_with_markers');
            if (firstRoute && handleRouteViaFilters(firstRoute.route)) {
                return;
            }
            // Then try single-marker detail visualization
            const firstDetail = visualization.find(v => v && v.type === 'marker_with_details');
            if (firstDetail && handleIdentViaSearch(firstDetail.marker?.ident)) {
                return;
            }
            // Otherwise, fall back to overlay rendering for all
            this.clearChatVisualizations();
            this.currentVisualization = null;
            visualization.forEach(viz => this.visualizeSingle(viz));
            return;
        }

        // Single visualization routing
        if (visualization && visualization.type === 'route_with_markers') {
            if (handleRouteViaFilters(visualization.route)) {
                return;
            }
        } else if (visualization && visualization.type === 'marker_with_details') {
            if (handleIdentViaSearch(visualization.marker?.ident)) {
                return;
            }
        }

    }

}

// Global instance (will be initialized in app.js)
let chatMapIntegration = null;

function initChatMapIntegration(map) {
    chatMapIntegration = new ChatMapIntegration(map);
    console.log('Chat-Map integration initialized');
    return chatMapIntegration;
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ChatMapIntegration, initChatMapIntegration };
}
