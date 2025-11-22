/**
 * Visualization Engine - Handles map rendering based on state
 * Reactive to Zustand store changes, manages Leaflet map layers
 */

import type { Airport, LegendMode, Highlight, RouteState } from '../store/types';

// Leaflet types (will be imported when Leaflet is available)
declare const L: any;
type LeafletMap = any; // Leaflet Map type

/**
 * Marker style configuration
 */
interface MarkerStyle {
  color: string;
  radius: number;
  icon: any; // Leaflet Icon
}

/**
 * Visualization Engine class
 */
export class VisualizationEngine {
  private map: LeafletMap | null = null;
  private airportLayer: any = null;
  private procedureLayer: any = null;
  private routeLayer: any = null;
  private highlightLayer: any = null;
  private overlayLayer: any = null;
  
  private markers: globalThis.Map<string, {marker: any; airport: Airport; style: MarkerStyle}> = new globalThis.Map();
  private procedureLines: globalThis.Map<string, any[]> = new globalThis.Map();
  private routeLine: any = null;
  private routeMarkers: any[] = [];
  private highlights: globalThis.Map<string, any> = new globalThis.Map();
  
  /**
   * Initialize map and layers
   */
  initMap(containerId: string): void {
    if (typeof L === 'undefined') {
      console.error('Leaflet library not loaded');
      return;
    }
    
    // Initialize Leaflet map
    this.map = L.map(containerId).setView([50.0, 10.0], 5);
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(this.map);
    
    // Create layer groups
    this.airportLayer = L.layerGroup().addTo(this.map);
    this.procedureLayer = L.layerGroup().addTo(this.map);
    this.routeLayer = L.layerGroup().addTo(this.map);
    this.highlightLayer = L.layerGroup().addTo(this.map);
    this.overlayLayer = L.layerGroup().addTo(this.map);
    
    // Add scale control
    L.control.scale().addTo(this.map);
    
    console.log('Map initialized successfully');
  }
  
  /**
   * Update markers based on airports and legend mode
   */
  updateMarkers(airports: Airport[], legendMode: LegendMode): void {
    if (!this.map || !this.airportLayer) return;
    
    const currentIcaos = new Set(this.markers.keys());
    const newIcaos = new Set(airports.map(a => a.ident));
    
    // Remove markers not in new list
    currentIcaos.forEach(icao => {
      if (!newIcaos.has(icao)) {
        this.removeMarker(icao);
      }
    });
    
    // Add/update markers
    airports.forEach(airport => {
      if (this.markers.has(airport.ident)) {
        // Update existing marker (e.g., legend mode changed)
        this.updateMarker(airport, legendMode);
      } else {
        // Add new marker
        this.addMarker(airport, legendMode);
      }
    });
  }
  
  /**
   * Add marker to map
   */
  private addMarker(airport: Airport, legendMode: LegendMode): void {
    if (!airport.latitude_deg || !airport.longitude_deg) return;
    
    const style = this.getMarkerStyle(airport, legendMode);
    
    const marker = L.marker([airport.latitude_deg, airport.longitude_deg], {
      icon: style.icon
    });
    
    marker.bindPopup(this.createPopup(airport));
    marker.on('click', () => {
      // Dispatch action to select airport
      // This will be connected to Zustand store
      const event = new CustomEvent('airport-click', { detail: airport });
      window.dispatchEvent(event);
    });
    
    marker.addTo(this.airportLayer);
    
    this.markers.set(airport.ident, {
      marker,
      airport,
      style
    });
  }
  
  /**
   * Update marker appearance (without recreating)
   */
  private updateMarker(airport: Airport, legendMode: LegendMode): void {
    const entry = this.markers.get(airport.ident);
    if (!entry) return;
    
    const newStyle = this.getMarkerStyle(airport, legendMode);
    
    // Only update if style changed
    if (entry.style.color !== newStyle.color || entry.style.radius !== newStyle.radius) {
      entry.marker.setIcon(newStyle.icon);
      entry.style = newStyle;
    }
  }
  
  /**
   * Remove marker
   */
  private removeMarker(icao: string): void {
    const entry = this.markers.get(icao);
    if (entry) {
      this.airportLayer.removeLayer(entry.marker);
      this.markers.delete(icao);
    }
  }
  
  /**
   * Get marker style based on legend mode
   */
  private getMarkerStyle(airport: Airport, legendMode: LegendMode): MarkerStyle {
    let color = '#ffc107'; // Default: yellow
    let radius = 6;
    
    switch (legendMode) {
      case 'airport-type':
        if (airport.point_of_entry) {
          color = '#28a745'; // Green
          radius = 8;
        } else if (airport.has_procedures) {
          color = '#ffc107'; // Yellow
          radius = 7;
        } else {
          color = '#dc3545'; // Red
          radius = 6;
        }
        break;
        
      case 'runway-length':
        if (airport.longest_runway_length_ft) {
          if (airport.longest_runway_length_ft > 8000) {
            color = '#28a745'; // Green
            radius = 10;
          } else if (airport.longest_runway_length_ft > 4000) {
            color = '#ffc107'; // Yellow
            radius = 7;
          } else {
            color = '#dc3545'; // Red
            radius = 5;
          }
        } else {
          color = '#6c757d'; // Gray
          radius = 4;
        }
        break;
        
      case 'country':
        const icao = airport.ident || '';
        if (icao.startsWith('LF')) {
          color = '#007bff'; // Blue
          radius = 7;
        } else if (icao.startsWith('EG')) {
          color = '#dc3545'; // Red
          radius = 7;
        } else if (icao.startsWith('ED')) {
          color = '#28a745'; // Green
          radius = 7;
        } else {
          color = '#ffc107'; // Yellow
          radius = 6;
        }
        break;
        
      case 'procedure-precision':
        // Transparent markers, procedure lines shown separately
        color = 'rgba(128, 128, 128, 0.3)';
        radius = 6;
        break;
    }
    
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
    
    return { color, radius, icon };
  }
  
  /**
   * Create popup content for airport
   */
  private createPopup(airport: Airport): string {
    let content = `
      <div style="min-width: 200px;">
        <h6><strong>${airport.ident}</strong></h6>
        <p style="margin: 5px 0;">${airport.name || 'N/A'}</p>
    `;
    
    if (airport.municipality) {
      content += `<p style="margin: 2px 0; font-size: 0.9em; color: #666;">
        <i class="fas fa-map-marker-alt"></i> ${airport.municipality}
      </p>`;
    }
    
    if (airport.iso_country) {
      content += `<p style="margin: 2px 0; font-size: 0.9em; color: #666;">
        <i class="fas fa-flag"></i> ${airport.iso_country}
      </p>`;
    }
    
    if (airport.longest_runway_length_ft) {
      content += `<p style="margin: 2px 0; font-size: 0.9em; color: #ff6b35;">
        <i class="fas fa-ruler"></i> Longest runway: ${airport.longest_runway_length_ft.toLocaleString()} ft
      </p>`;
    }
    
    if (airport.procedure_count && airport.procedure_count > 0) {
      content += `<p style="margin: 2px 0; font-size: 0.9em; color: #28a745;">
        <i class="fas fa-route"></i> ${airport.procedure_count} procedures
      </p>`;
    }
    
    if (airport.point_of_entry) {
      content += `<p style="margin: 2px 0; font-size: 0.9em; color: #dc3545;">
        <i class="fas fa-passport"></i> Border Crossing
      </p>`;
    }
    
    // Add route distance if available
    if (airport._routeSegmentDistance !== undefined) {
      content += `<hr><div style="font-size: 0.9em; color: #007bff;">
        <strong>Route Distance:</strong> ${airport._routeSegmentDistance}nm<br>
        ${airport._closestSegment ? `<strong>Closest to:</strong> ${airport._closestSegment[0]} → ${airport._closestSegment[1]}` : ''}
        ${airport._routeEnrouteDistance !== undefined ? `<br><strong>Along-track:</strong> ${airport._routeEnrouteDistance}nm` : ''}
      </div>`;
    }
    
    content += '</div>';
    return content;
  }
  
  /**
   * Update highlights
   */
  updateHighlights(highlights: globalThis.Map<string, Highlight> | Record<string, Highlight> | null | undefined): void {
    if (!this.highlightLayer) return;
    
    // Convert to Map if it's a plain object (from Zustand serialization)
    let highlightsMap: globalThis.Map<string, Highlight>;
    if (!highlights) {
      highlightsMap = new globalThis.Map();
    } else if (highlights instanceof globalThis.Map) {
      highlightsMap = highlights;
    } else {
      // Convert plain object to Map
      highlightsMap = new globalThis.Map(Object.entries(highlights as Record<string, Highlight>));
    }
    
    // Remove highlights not in state
    this.highlightLayer.eachLayer((layer: any) => {
      const id = layer.options?.id;
      if (id && !highlightsMap.has(id)) {
        this.highlightLayer.removeLayer(layer);
        this.highlights.delete(id);
      }
    });
    
    // Add/update highlights
    highlightsMap.forEach((highlight: Highlight, id: string) => {
      if (!this.highlights.has(id)) {
        this.addHighlight(highlight);
      }
    });
  }
  
  /**
   * Add highlight
   */
  private addHighlight(highlight: Highlight): void {
    const marker = L.circleMarker([highlight.lat, highlight.lng], {
      radius: highlight.radius || 15,
      fillColor: highlight.color || '#ff0000',
      color: '#fff',
      weight: 3,
      opacity: 1,
      fillOpacity: 0.7,
      id: highlight.id
    });
    
    if (highlight.popup) {
      marker.bindPopup(highlight.popup);
    }
    
    marker.addTo(this.highlightLayer);
    this.highlights.set(highlight.id, marker);
  }
  
  /**
   * Display route
   */
  displayRoute(route: RouteState): void {
    if (!route.airports || route.airports.length < 1) {
      this.clearRoute();
      return;
    }
    
    this.clearRoute();
    
    if (!this.routeLayer) return;
    
    // Get route coordinates
    const routeCoordinates: [number, number][] = [];
    const routeMarkers: any[] = [];
    
    for (const icao of route.airports) {
      // Try to get coordinates from original route airports
      let latlng: [number, number] | null = null;
      
      if (route.originalRouteAirports) {
        const original = route.originalRouteAirports.find(a => a.icao === icao);
        if (original) {
          latlng = [original.lat, original.lng];
        }
      }
      
      // Fall back to marker if available
      if (!latlng) {
        const entry = this.markers.get(icao);
        if (entry) {
          const pos = entry.marker.getLatLng();
          latlng = [pos.lat, pos.lng];
        }
      }
      
      if (latlng) {
        routeCoordinates.push(latlng);
        
        // Create route marker
        const routeMarker = L.circleMarker(latlng, {
          radius: 12,
          fillColor: '#007bff',
          color: '#ffffff',
          weight: 3,
          opacity: 1,
          fillOpacity: 0.8
        }).addTo(this.routeLayer);
        
        const popupText = route.airports.length === 1
          ? `<b>Search Center: ${icao}</b><br>Distance: ${route.distance_nm}nm radius`
          : `<b>Route Airport: ${icao}</b><br>Distance: ${route.distance_nm}nm corridor`;
        routeMarker.bindPopup(popupText);
        routeMarkers.push(routeMarker);
      }
    }
    
    // Draw route line if multiple airports
    if (routeCoordinates.length >= 2) {
      this.routeLine = L.polyline(routeCoordinates, {
        color: '#007bff',
        weight: 4,
        opacity: 0.8,
        dashArray: '10, 5'
      }).addTo(this.routeLayer);
      
      this.routeLine.bindPopup(`<b>Route: ${route.airports.join(' → ')}</b><br>Search corridor: ${route.distance_nm}nm`);
    }
    
    this.routeMarkers = routeMarkers;
    
    // Fit bounds
    if (this.routeLine && this.map) {
      this.map.fitBounds(this.routeLine.getBounds(), { padding: [20, 20] });
    } else if (routeCoordinates.length === 1 && this.map) {
      this.map.setView(routeCoordinates[0], 8);
    }
  }
  
  /**
   * Clear route
   */
  clearRoute(): void {
    if (this.routeLayer) {
      this.routeLayer.clearLayers();
    }
    this.routeLine = null;
    this.routeMarkers = [];
  }
  
  /**
   * Load procedure lines in bulk
   */
  async loadBulkProcedureLines(airports: Airport[], apiAdapter: any): Promise<void> {
    if (!this.procedureLayer) return;
    
    const airportsWithProcedures = airports.filter(a => a.has_procedures);
    if (airportsWithProcedures.length === 0) return;
    
    const icaoCodes = airportsWithProcedures.map(a => a.ident);
    
    try {
      const bulkData = await apiAdapter.getBulkProcedureLines(icaoCodes, 10.0);
      
      // Process each airport's procedure lines
      airportsWithProcedures.forEach(airport => {
        const procedureData = bulkData[airport.ident];
        if (procedureData && procedureData.procedure_lines) {
          this.addProcedureLines(airport, procedureData.procedure_lines);
        }
      });
    } catch (error) {
      console.error('Error loading bulk procedure lines:', error);
    }
  }
  
  /**
   * Add procedure lines for an airport
   */
  private addProcedureLines(airport: Airport, lines: any[]): void {
    if (!this.procedureLayer) return;
    
    const existingLines = this.procedureLines.get(airport.ident) || [];
    
    lines.forEach(lineData => {
      const lineColor = this.getProcedureLineColor(lineData.precision_category);
      
      const line = L.polyline([
        [lineData.start_lat, lineData.start_lon],
        [lineData.end_lat, lineData.end_lon]
      ], {
        color: lineColor,
        weight: 3,
        opacity: 0.8
      });
      
      line.bindPopup(`
        <div style="min-width: 200px;">
          <h6><strong>${airport.ident} ${lineData.runway_end}</strong></h6>
          <p><strong>Approach:</strong> ${lineData.procedure_name || 'N/A'}</p>
          <p><strong>Type:</strong> ${lineData.approach_type}</p>
        </div>
      `);
      
      line.addTo(this.procedureLayer);
      existingLines.push(line);
    });
    
    this.procedureLines.set(airport.ident, existingLines);
  }
  
  /**
   * Get procedure line color based on precision category
   */
  private getProcedureLineColor(category: string): string {
    switch (category) {
      case 'precision': return '#ffff00'; // Yellow for ILS
      case 'rnp': return '#0000ff'; // Blue for RNP/RNAV
      case 'non-precision': return '#ffffff'; // White for VOR/NDB
      default: return '#ffffff';
    }
  }
  
  /**
   * Fit bounds to show all markers
   */
  fitBounds(): void {
    if (!this.map || this.markers.size === 0) return;
    
    const group = L.featureGroup(Array.from(this.markers.values()).map(e => e.marker));
    this.map.fitBounds(group.getBounds().pad(0.1));
  }
  
  /**
   * Set map view
   */
  setView(lat: number, lng: number, zoom: number): void {
    if (this.map) {
      this.map.setView([lat, lng], zoom);
    }
  }
  
  /**
   * Get map instance
   */
  getMap(): LeafletMap | null {
    return this.map;
  }
  
  /**
   * Clear all markers
   */
  clearMarkers(): void {
    if (this.airportLayer) {
      this.airportLayer.clearLayers();
    }
    if (this.procedureLayer) {
      this.procedureLayer.clearLayers();
    }
    this.markers.clear();
    this.procedureLines.clear();
  }
}

