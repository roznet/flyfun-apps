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

        // Clear previous chat visualizations
        this.clearChatVisualizations();

        this.currentVisualization = visualization;

        // Hide all other airports - only show chat results
        this.hideOtherAirports();

        // Handle array of visualizations (multi-leg routes)
        if (Array.isArray(visualization)) {
            console.log('Processing multiple visualizations:', visualization.length);
            visualization.forEach((viz, index) => {
                // Don't clear on subsequent visualizations
                if (index > 0) {
                    this.currentVisualization = viz;
                }
                this.visualizeSingle(viz);
            });
            return;
        }

        // Single visualization
        this.visualizeSingle(visualization);
    }

    /**
     * Hide all other airports on the map (show only chat results)
     */
    hideOtherAirports() {
        if (window.airportMap && window.airportMap.airportLayer && window.airportMap.map) {
            // Remove the airport layer from the map
            window.airportMap.airportLayer.remove();
            this.isFilteredMode = true;
            console.log('Hidden other airports - showing only chat results');
        }
    }

    /**
     * Show all airports again (restore normal view)
     */
    showAllAirports() {
        console.log('Restoring all airports view...');

        if (window.airportMap && window.airportMap.airportLayer && window.airportMap.map) {
            // Add the airport layer back to the map
            window.airportMap.airportLayer.addTo(window.airportMap.map);
            this.isFilteredMode = false;
            console.log('Restored all airports view');
        } else {
            console.warn('Airport map or layer not available');
        }
    }

    /**
     * Visualize a single visualization object
     */
    visualizeSingle(visualization) {
        if (!visualization) return;

        switch (visualization.type) {
            case 'markers':
                this.visualizeMarkers(visualization.data, visualization.style);
                break;
            case 'route_with_markers':
                this.visualizeRoute(visualization.route, visualization.markers);
                break;
            case 'marker_with_details':
                this.visualizeMarkerWithDetails(visualization.marker);
                break;
            default:
                console.warn('Unknown visualization type:', visualization.type);
        }
    }

    /**
     * Visualize multiple airport markers using native styling
     */
    visualizeMarkers(airports, style = 'default') {
        if (!airports || airports.length === 0) return;

        // Store airports for filtering
        this.chatAirports = airports;

        const bounds = [];

        airports.forEach(airport => {
            if (airport.latitude_deg && airport.longitude_deg) {
                const lat = airport.latitude_deg;
                const lon = airport.longitude_deg;

                // Create marker with native styling but add to chatLayers
                const marker = this.createNativeStyledMarker(airport);
                marker.addTo(this.chatLayers);

                // Add click event for airport details
                marker.on('click', () => {
                    if (window.app && window.app.loadAirportDetails) {
                        window.app.loadAirportDetails(airport.ident);
                    }
                });

                this.chatMarkers.push(marker);
                bounds.push([lat, lon]);
            }
        });

        // Fit map to show all markers
        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 10 });
        }

        // Show count in UI
        this.showVisualizationInfo(`Showing ${airports.length} airport(s) on map`);
    }

    /**
     * Visualize a route with markers along it using native styling
     */
    visualizeRoute(route, markers) {
        if (!route || !route.from || !route.to) return;

        // Store airports for filtering (markers contains airport data)
        this.chatAirports = markers || [];

        const fromLat = route.from.lat;
        const fromLon = route.from.lon;
        const toLat = route.to.lat;
        const toLon = route.to.lon;

        if (!fromLat || !fromLon || !toLat || !toLon) return;

        // Draw route line
        const routeLine = L.polyline(
            [[fromLat, fromLon], [toLat, toLon]],
            {
                color: '#007bff',
                weight: 4,
                opacity: 0.8,
                dashArray: '10, 5'
            }
        ).addTo(this.chatLayers);

        // Add route endpoint markers (special markers for departure/arrival)
        const departureMarker = this.createRouteEndpointMarker(
            [fromLat, fromLon],
            route.from.icao,
            'Departure',
            12,
            '#007bff'
        );
        departureMarker.addTo(this.chatLayers);
        this.chatMarkers.push(departureMarker);

        const arrivalMarker = this.createRouteEndpointMarker(
            [toLat, toLon],
            route.to.icao,
            'Destination',
            12,
            '#007bff'
        );
        arrivalMarker.addTo(this.chatLayers);
        this.chatMarkers.push(arrivalMarker);

        // Add airports along route with native styling and distance info
        if (markers && markers.length > 0) {
            markers.forEach(airportData => {
                if (airportData.latitude_deg && airportData.longitude_deg) {
                    const marker = this.createNativeStyledMarkerWithDistance(
                        airportData,
                        airportData.segment_distance_nm,
                        airportData.enroute_distance_nm
                    );
                    marker.addTo(this.chatLayers);

                    // Add click event
                    marker.on('click', () => {
                        if (window.app && window.app.loadAirportDetails) {
                            window.app.loadAirportDetails(airportData.ident);
                        }
                    });

                    this.chatMarkers.push(marker);
                }
            });
        }

        // Fit bounds to show entire route
        const bounds = [[fromLat, fromLon], [toLat, toLon]];
        if (markers) {
            markers.forEach(m => {
                if (m.latitude_deg && m.longitude_deg) {
                    bounds.push([m.latitude_deg, m.longitude_deg]);
                }
            });
        }
        this.map.fitBounds(bounds, { padding: [50, 50] });

        this.showVisualizationInfo(`Route from ${route.from.icao} to ${route.to.icao} with ${markers ? markers.length : 0} stop(s)`);
    }

    /**
     * Calculate distance between two points in nautical miles
     */
    calculateDistance(lat1, lon1, lat2, lon2) {
        const R = 3440.065; // Earth's radius in nautical miles
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                  Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                  Math.sin(dLon/2) * Math.sin(dLon/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    }

    /**
     * Visualize a single marker with detail view using native styling
     */
    visualizeMarkerWithDetails(markerData) {
        if (!markerData || !markerData.lat || !markerData.lon) return;

        // Create minimal airport object
        const airport = {
            ident: markerData.ident,
            latitude_deg: markerData.lat,
            longitude_deg: markerData.lon,
            name: markerData.name || markerData.ident,
            ...markerData // Include any other properties
        };

        // Create marker with native styling
        const marker = this.createNativeStyledMarker(airport);
        marker.addTo(this.chatLayers);

        // Add click event
        marker.on('click', () => {
            if (window.app && window.app.loadAirportDetails) {
                window.app.loadAirportDetails(airport.ident);
            }
        });

        this.chatMarkers.push(marker);

        // Zoom to marker with appropriate level
        const zoomLevel = markerData.zoom || 12;
        this.map.setView([markerData.lat, markerData.lon], zoomLevel);

        this.showVisualizationInfo(`Showing ${markerData.ident} on map`);
    }

    /**
     * Create a marker with native styling (same as map.js)
     */
    createNativeStyledMarker(airport) {
        // Get legend mode from global airportMap instance (not this.map which is Leaflet map)
        const legendMode = window.airportMap?.legendMode || 'airport-type';

        let color = '#ffc107'; // Default: yellow
        let radius = 6;

        if (legendMode === 'runway-length') {
            // Runway length legend mode
            if (airport.longest_runway_length_ft) {
                if (airport.longest_runway_length_ft > 8000) {
                    color = '#28a745'; // Green for long runways (>8000ft)
                    radius = 10;
                } else if (airport.longest_runway_length_ft > 4000) {
                    color = '#ffc107'; // Yellow for medium runways (4000-8000ft)
                    radius = 7;
                } else {
                    color = '#dc3545'; // Red for short runways (<4000ft)
                    radius = 5;
                }
            } else {
                color = '#6c757d'; // Gray for unknown
                radius = 4;
            }
        } else if (legendMode === 'country') {
            // Country legend mode (based on ICAO prefix)
            const icao = airport.ident || '';
            if (icao.startsWith('LF')) {
                color = '#007bff'; // Blue for France
                radius = 7;
            } else if (icao.startsWith('EG')) {
                color = '#dc3545'; // Red for United Kingdom
                radius = 7;
            } else if (icao.startsWith('ED')) {
                color = '#28a745'; // Green for Germany
                radius = 7;
            } else {
                color = '#ffc107'; // Yellow for other countries
                radius = 6;
            }
        } else {
            // Default airport type legend mode
            if (airport.point_of_entry) {
                color = '#28a745'; // Green for border crossing
                radius = 8;
            } else if (airport.has_procedures) {
                color = '#ffc107'; // Yellow for airports with procedures
                radius = 7;
            } else {
                color = '#dc3545'; // Red for other
                radius = 6;
            }
        }

        // Create custom icon
        const icon = L.divIcon({
            className: 'airport-marker',
            html: `<div style="
                width: ${radius * 2}px;
                height: ${radius * 2}px;
                background-color: ${color};
                border: 2px solid white;
                border-radius: 50%;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);
            "></div>`,
            iconSize: [radius * 2, radius * 2],
            iconAnchor: [radius, radius]
        });

        // Create marker with popup
        const marker = L.marker([airport.latitude_deg, airport.longitude_deg], { icon: icon });

        // Create popup content (same structure as map.js)
        const popupContent = this.createPopupContent(airport);
        marker.bindPopup(popupContent, {
            maxWidth: 300,
            maxHeight: 200
        });

        return marker;
    }

    /**
     * Create a marker with native styling and distance information
     */
    createNativeStyledMarkerWithDistance(airport, segmentDistanceNm, enrouteDistanceNm) {
        const marker = this.createNativeStyledMarker(airport);

        // Add distance to popup if available
        if (segmentDistanceNm !== undefined) {
            const popupContent = this.createPopupContent(airport) +
                `<hr><div style="font-size: 0.9em; color: #007bff;">
                    <strong>Route Distance:</strong> ${segmentDistanceNm.toFixed(1)}nm
                    ${enrouteDistanceNm !== undefined && enrouteDistanceNm !== null ? `<br><strong>Along-track:</strong> ${enrouteDistanceNm.toFixed(1)}nm` : ''}
                </div>`;
            marker.bindPopup(popupContent, {
                maxWidth: 300,
                maxHeight: 200
            });
        }

        return marker;
    }

    /**
     * Create route endpoint marker
     */
    createRouteEndpointMarker(latlng, icao, label, radius, color) {
        const icon = L.divIcon({
            className: 'route-endpoint-marker',
            html: `<div style="
                width: ${radius * 2}px;
                height: ${radius * 2}px;
                background-color: ${color};
                border: 3px solid white;
                border-radius: 50%;
                box-shadow: 0 2px 6px rgba(0,0,0,0.4);
            "></div>`,
            iconSize: [radius * 2, radius * 2],
            iconAnchor: [radius, radius]
        });

        const marker = L.marker(latlng, { icon: icon });
        marker.bindPopup(`<b>${label}:</b> ${icao}`);

        return marker;
    }

    /**
     * Create popup content (similar to map.js)
     */
    createPopupContent(airport) {
        let content = `<div style="min-width: 200px;">`;
        content += `<strong>${airport.ident}</strong><br>`;

        if (airport.name) {
            content += `${airport.name}<br>`;
        }

        if (airport.municipality) {
            content += `<i class="fas fa-map-marker-alt"></i> ${airport.municipality}`;
            if (airport.country) {
                content += `, ${airport.country}`;
            }
            content += `<br>`;
        }

        if (airport.longest_runway_length_ft) {
            content += `<i class="fas fa-plane"></i> Runway: ${airport.longest_runway_length_ft}ft<br>`;
        }

        if (airport.point_of_entry) {
            content += `<i class="fas fa-passport"></i> Customs Available<br>`;
        }

        content += `<br><small style="color: #666;"><i class="fas fa-info-circle"></i> Click for full details</small>`;
        content += `</div>`;

        return content;
    }

    /**
     * Clear all chat visualizations and restore normal view
     */
    clearChatVisualizations() {
        this.chatLayers.clearLayers();
        this.chatMarkers = [];
        this.currentVisualization = null;
        this.hideVisualizationInfo();

        // Restore all airports
        this.showAllAirports();
    }

    /**
     * Apply filters to chat-plotted airports
     */
    applyFiltersToChatAirports(filters) {
        if (!this.isFilteredMode || !this.chatAirports || this.chatAirports.length === 0) {
            return;
        }

        console.log('Applying filters to chat airports:', filters);

        // Filter the chat airports based on filter criteria
        let filteredAirports = this.chatAirports.filter(airport => {
            // Country filter
            if (filters.country && airport.iso_country !== filters.country) {
                return false;
            }

            // Has procedures filter
            if (filters.has_procedures && !airport.has_procedures) {
                return false;
            }

            // Has AIP data filter
            if (filters.has_aip_data && !airport.has_aip_data) {
                return false;
            }

            // Has hard runway filter
            if (filters.has_hard_runway && !airport.has_hard_runway) {
                return false;
            }

            // Border crossing filter
            if (filters.point_of_entry && !airport.point_of_entry) {
                return false;
            }

            return true;
        });

        console.log(`Filtered chat airports: ${filteredAirports.length} of ${this.chatAirports.length}`);

        // Clear existing chat markers
        this.chatLayers.clearLayers();
        this.chatMarkers = [];

        // Recreate visualization with filtered airports
        if (this.currentVisualization) {
            const vizType = this.currentVisualization.type;

            if (vizType === 'markers') {
                // For simple markers visualization
                this.visualizeMarkersOnly(filteredAirports);
            } else if (vizType === 'route_with_markers') {
                // For route visualization, need to preserve route line
                this.visualizeRouteWithFilteredMarkers(
                    this.currentVisualization.route,
                    filteredAirports
                );
            } else if (vizType === 'marker_with_details') {
                // Single marker - check if it passes filter
                if (filteredAirports.length > 0) {
                    this.visualizeMarkerWithDetails(this.currentVisualization.marker);
                } else {
                    this.showVisualizationInfo('No airports match the current filters');
                }
            }
        }

        // Update info banner
        if (filteredAirports.length === 0) {
            this.showVisualizationInfo('No airports match the current filters - adjust filters or use "Clear Chat" to reset');
        } else {
            this.showVisualizationInfo(`Showing ${filteredAirports.length} filtered airport(s) from chatbot results`);
        }
    }

    /**
     * Visualize markers only (without changing bounds or route)
     */
    visualizeMarkersOnly(airports) {
        if (!airports || airports.length === 0) return;

        airports.forEach(airport => {
            if (airport.latitude_deg && airport.longitude_deg) {
                const marker = this.createNativeStyledMarker(airport);
                marker.addTo(this.chatLayers);

                marker.on('click', () => {
                    if (window.app && window.app.loadAirportDetails) {
                        window.app.loadAirportDetails(airport.ident);
                    }
                });

                this.chatMarkers.push(marker);
            }
        });
    }

    /**
     * Visualize route with filtered markers (preserve route line)
     */
    visualizeRouteWithFilteredMarkers(route, filteredMarkers) {
        if (!route || !route.from || !route.to) return;

        const fromLat = route.from.lat;
        const fromLon = route.from.lon;
        const toLat = route.to.lat;
        const toLon = route.to.lon;

        if (!fromLat || !fromLon || !toLat || !toLon) return;

        // Draw route line
        const routeLine = L.polyline(
            [[fromLat, fromLon], [toLat, toLon]],
            {
                color: '#007bff',
                weight: 4,
                opacity: 0.8,
                dashArray: '10, 5'
            }
        ).addTo(this.chatLayers);

        // Add route endpoint markers
        const departureMarker = this.createRouteEndpointMarker(
            [fromLat, fromLon],
            route.from.icao,
            'Departure',
            12,
            '#007bff'
        );
        departureMarker.addTo(this.chatLayers);
        this.chatMarkers.push(departureMarker);

        const arrivalMarker = this.createRouteEndpointMarker(
            [toLat, toLon],
            route.to.icao,
            'Destination',
            12,
            '#007bff'
        );
        arrivalMarker.addTo(this.chatLayers);
        this.chatMarkers.push(arrivalMarker);

        // Add filtered airports along route
        if (filteredMarkers && filteredMarkers.length > 0) {
            filteredMarkers.forEach(airportData => {
                if (airportData.latitude_deg && airportData.longitude_deg) {
                    const marker = this.createNativeStyledMarkerWithDistance(
                        airportData,
                        airportData.segment_distance_nm,
                        airportData.enroute_distance_nm
                    );
                    marker.addTo(this.chatLayers);

                    marker.on('click', () => {
                        if (window.app && window.app.loadAirportDetails) {
                            window.app.loadAirportDetails(airportData.ident);
                        }
                    });

                    this.chatMarkers.push(marker);
                }
            });
        }
    }

    /**
     * Refresh chat markers to reflect current legend mode
     * This is called when the legend mode changes
     */
    refreshMarkersForLegendMode() {
        if (!this.currentVisualization) {
            return; // No active visualization to refresh
        }

        console.log('Refreshing chat markers for legend mode change');

        // Clear existing chat markers but keep the visualization data
        this.chatLayers.clearLayers();
        this.chatMarkers = [];

        // Re-visualize with the current legend mode
        this.visualizeSingle(this.currentVisualization);

        // Re-hide other airports if we're in filtered mode
        if (this.isFilteredMode) {
            console.log('Re-hiding other airports after legend change');
            if (window.airportMap && window.airportMap.airportLayer) {
                window.airportMap.airportLayer.remove();
            }
        }
    }

    /**
     * Show visualization info banner
     */
    showVisualizationInfo(message) {
        let infoBanner = document.getElementById('chat-viz-info');

        if (!infoBanner) {
            infoBanner = document.createElement('div');
            infoBanner.id = 'chat-viz-info';
            infoBanner.className = 'chat-visualization-info';
            document.querySelector('.map-container')?.appendChild(infoBanner);
        }

        infoBanner.innerHTML = `
            <i class="fas fa-filter"></i> ${message} (Filtered view - use "Clear Chat" to show all airports)
        `;
        infoBanner.style.display = 'block';
    }

    /**
     * Hide visualization info banner
     */
    hideVisualizationInfo() {
        const infoBanner = document.getElementById('chat-viz-info');
        if (infoBanner) {
            infoBanner.style.display = 'none';
        }
    }

    /**
     * Handle map click - suggest query to chatbot
     */
    onMapClick(latlng) {
        // Find nearest airport to click
        // This could be enhanced to find airports near the clicked location
        console.log('Map clicked at:', latlng);
    }

    /**
     * Export visualization as image (future feature)
     */
    exportVisualization() {
        // Could use leaflet-image or similar library
        console.log('Export visualization');
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
