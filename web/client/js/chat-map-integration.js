/**
 * Chat-Map Integration
 * Handles visualization of chatbot results on the Leaflet map
 * 
 * All visualizations are delegated to FilterManager to ensure consistent
 * behavior with UI filters and unified airport handling.
 */

class ChatMapIntegration {
    constructor(map) {
        this.map = map;
        // Keep track of visualization state
        this.currentVisualization = null;
    }

    /**
     * Visualize data on the map based on chatbot response
     * 
     * All visualization types are delegated to FilterManager:
     * - route_with_markers → filterManager.handleRouteSearch() or handleRouteWithChatbotAirports()
     * - marker_with_details → filterManager.handleSearch()
     * - markers → filterManager.updateMapWithAirports()
     */
    visualizeData(visualization) {
        if (!visualization) {
            console.warn('ChatMapIntegration.visualizeData: No visualization provided');
            return;
        }

        console.log('ChatMapIntegration.visualizeData called with:', visualization);

        // Handle array of visualizations - process first supported type
        if (Array.isArray(visualization)) {
            console.log('Array visualization detected, processing first supported type...');
            for (const viz of visualization) {
                if (viz && viz.type) {
                    if (this._delegateVisualization(viz)) {
                        return; // Successfully delegated, stop processing
                    }
                }
            }
            console.error('❌ No supported visualization type found in array');
            return;
        }

        // Handle single visualization
        if (!this._delegateVisualization(visualization)) {
            const vizType = visualization?.type || 'unknown';
            console.error(`❌ Visualization type "${vizType}" is not yet supported by FilterManager`);
        }
    }

    /**
     * Delegate a single visualization to FilterManager
     * Returns true if successfully delegated, false otherwise
     */
    _delegateVisualization(viz) {
        if (!viz || !viz.type) {
            console.warn('Invalid visualization object:', viz);
            return false;
        }

        switch (viz.type) {
            case 'route_with_markers':
                return this._handleRouteWithMarkers(viz);
            case 'marker_with_details':
                return this._handleMarkerWithDetails(viz);
            case 'markers':
                return this._handleMarkers(viz);
            default:
                console.error(`❌ Visualization type "${viz.type}" is not yet supported by FilterManager`);
                return false;
        }
    }

    /**
     * Handle route_with_markers visualization
     * Delegates to FilterManager while preserving chatbot's airport selection
     */
    _handleRouteWithMarkers(viz) {
        if (!viz.route || !viz.markers) {
            console.error('route_with_markers missing route or markers');
            return false;
        }

        // Use chatbot's pre-selected airports instead of re-fetching all route airports
        if (this.handleRouteWithChatbotAirports(viz)) {
            console.log('✅ Successfully handled route with chatbot-selected airports');
            this.currentVisualization = viz;
            return true;
        }

        // Fallback: try simple route delegation (without preserving chatbot airports)
        const route = viz.route;
        const fromIcao = route?.from?.icao;
        const toIcao = route?.to?.icao;

        if (fromIcao && toIcao && typeof filterManager !== 'undefined' && filterManager?.handleRouteSearch) {
            try {
                console.log(`✅ Delegating route ${fromIcao} → ${toIcao} to FilterManager (simple mode)`);
                filterManager.handleRouteSearch([fromIcao, toIcao]);
                this.currentVisualization = viz;
                return true;
            } catch (e) {
                console.error('❌ Route handoff to FilterManager failed:', e);
            }
        }

        return false;
    }

    /**
     * Handle marker_with_details visualization
     * Delegates to FilterManager.handleSearch()
     */
    _handleMarkerWithDetails(viz) {
        const ident = viz.marker?.ident || viz.marker?.icao;
        if (!ident) {
            console.error('marker_with_details missing ident');
            return false;
        }

        if (typeof filterManager === 'undefined' || !filterManager?.handleSearch) {
            console.error('FilterManager.handleSearch not available');
            return false;
        }

        try {
            console.log(`✅ Delegating search for ${ident} to FilterManager`);
            // Update search box for UX coherence
            const searchInput = document.getElementById('search-input');
            if (searchInput) searchInput.value = ident;
            filterManager.handleSearch(ident);
            this.currentVisualization = viz;
            return true;
        } catch (e) {
            console.error('❌ Ident handoff to FilterManager failed:', e);
            return false;
        }
    }

    /**
     * Handle markers visualization (array of airports without route)
     * Delegates to FilterManager.updateMapWithAirports()
     */
    _handleMarkers(viz) {
        const airports = viz.data || viz.markers || [];
        if (!Array.isArray(airports) || airports.length === 0) {
            console.error('markers visualization missing valid airports array');
            return false;
        }

        if (typeof filterManager === 'undefined' || !filterManager?.updateMapWithAirports) {
            console.error('FilterManager.updateMapWithAirports not available');
            return false;
        }

        try {
            console.log(`✅ Delegating ${airports.length} airports to FilterManager.updateMapWithAirports`);
            filterManager.updateMapWithAirports(airports, false);
            this.currentVisualization = viz;
            return true;
        } catch (e) {
            console.error('❌ Markers handoff to FilterManager failed:', e);
            return false;
        }
    }

    /**
     * Handle route visualization with chatbot's pre-selected airports
     * This integrates with FilterManager while preserving the chatbot's airport selection
     */
    handleRouteWithChatbotAirports(visualization) {
        try {
            if (!visualization || !visualization.route || !visualization.markers) {
                return false;
            }

            const route = visualization.route;
            let markers = visualization.markers;
            const fromIcao = route.from?.icao;
            const toIcao = route.to?.icao;

            if (!fromIcao || !toIcao || !filterManager) {
                return false;
            }

            console.log(`Integrating chatbot route ${fromIcao} → ${toIcao} with ${markers.length} airports into FilterManager`);

            // Normalize markers: ensure icao field exists (some tools use 'ident' instead)
            // Also ensure lat/lng fields for FilterManager compatibility
            markers = markers.map(m => ({
                ...m,
                icao: m.icao || m.ident,  // Use ident as fallback for icao
                lat: m.lat || m.latitude_deg,
                lng: m.lng || m.longitude_deg || m.lon
            }));

            // Normalize route airport objects for displayRoute (needs icao, lat, lng)
            const normalizedRouteAirports = [
                {
                    icao: fromIcao,
                    lat: route.from.lat || route.from.latitude || route.from.latitude_deg,
                    lng: route.from.lng || route.from.lon || route.from.longitude || route.from.longitude_deg
                },
                {
                    icao: toIcao,
                    lat: route.to.lat || route.to.latitude || route.to.latitude_deg,
                    lng: route.to.lng || route.to.lon || route.to.longitude || route.to.longitude_deg
                }
            ];

            console.log('Normalized route airports:', normalizedRouteAirports);

            // Set FilterManager's route state (so filters can be reapplied)
            filterManager.currentRoute = {
                airports: [fromIcao, toIcao],
                originalRouteAirports: normalizedRouteAirports,
                isChatbotSelection: true,  // FLAG: This is from chatbot, don't re-query
                chatbotAirports: markers   // Store chatbot's original selection
            };

            // Update FilterManager's stored airports with chatbot's selection
            filterManager.airports = markers;

            // Update the map with chatbot's airports (using FilterManager's method for consistency)
            filterManager.updateMapWithAirports(markers, false);

            // Draw the route line using airportMap's displayRoute method
            if (window.airportMap) {
                // Extract route airport ICAOs
                const routeAirports = [fromIcao, toIcao];
                // Use a default distance for display (won't affect the markers already shown)
                const distanceNm = 50;
                window.airportMap.displayRoute(routeAirports, distanceNm, true, normalizedRouteAirports);
            }

            console.log(`✅ FilterManager now has ${markers.length} chatbot-selected airports. Filters will work on these.`);
            return true;

        } catch (e) {
            console.error('Error in handleRouteWithChatbotAirports:', e);
            return false;
        }
    }

    /**
     * Clear all chat visualizations
     * Note: Since all visualizations are now handled by FilterManager,
     * this mainly clears the internal state tracking
     */
    clearChatVisualizations() {
        console.log('Clearing chat visualization state...');
        this.currentVisualization = null;
        // FilterManager handles the actual map clearing via its own methods
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
