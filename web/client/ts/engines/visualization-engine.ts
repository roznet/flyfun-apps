/**
 * Visualization Engine - Handles map rendering based on state
 * Reactive to Zustand store changes, manages Leaflet map layers
 */

import type { Airport, LegendMode, Highlight, RouteState, GAFriendlySummary } from '../store/types';
import { useStore } from '../store/store';

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
    // Order matters: layers added first render below layers added later
    // We want highlights (reference points) below airport markers so legend colors are visible
    this.highlightLayer = L.layerGroup().addTo(this.map); // Reference points (locate center, route airports)
    this.airportLayer = L.layerGroup().addTo(this.map);   // Airport markers (on top of highlights)
    this.procedureLayer = L.layerGroup().addTo(this.map); // Procedure lines
    this.routeLayer = L.layerGroup().addTo(this.map);     // Route lines
    this.overlayLayer = L.layerGroup().addTo(this.map);   // Other overlays
    
    // Add scale control
    L.control.scale().addTo(this.map);
    
    console.log('Map initialized successfully');
  }
  
  /**
   * Update markers based on airports and legend mode
   */
  updateMarkers(airports: Airport[], legendMode: LegendMode, shouldFitBounds: boolean = false): void {
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
    
    // Fit bounds if requested and we have markers
    if (shouldFitBounds && this.markers.size > 0) {
      // Use setTimeout to ensure markers are rendered before fitting bounds
      setTimeout(() => {
        this.fitBounds();
      }, 100);
    }
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
        
      case 'relevance':
        color = this.getRelevanceColor(airport);
        radius = 7;
        break;

      case 'notification':
        color = this.getNotificationColor(airport);
        radius = 7;
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
   * Get relevance color based on GA scores (using embedded airport.ga data)
   */
  private getRelevanceColor(airport: Airport): string {
    const state = useStore.getState();
    const selectedPersona = state.ga.selectedPersona;
    const quartiles = state.ga.computedQuartiles;
    const buckets = state.ga.config?.relevance_buckets;
    
    // Default colors if config not loaded
    const defaultColors = {
      'top-quartile': '#27ae60',      // Green
      'second-quartile': '#3498db',   // Blue
      'third-quartile': '#f39c12',    // Orange
      'bottom-quartile': '#e74c3c',   // Red
      'unknown': '#95a5a6'            // Gray
    };
    
    const getColor = (bucketId: string): string => {
      const bucket = buckets?.find(b => b.id === bucketId);
      return bucket?.color || defaultColors[bucketId as keyof typeof defaultColors] || '#95a5a6';
    };
    
    // No GA data on airport = unknown
    if (!airport.ga) {
      return getColor('unknown');
    }
    
    // Get the score for the selected persona
    const score = airport.ga.persona_scores?.[selectedPersona];
    
    // No score for this persona = unknown
    if (score === null || score === undefined) {
      return getColor('unknown');
    }
    
    // No quartiles computed yet = show all as unknown
    if (!quartiles) {
      return getColor('unknown');
    }
    
    // Assign bucket based on quartile thresholds
    if (score >= quartiles.q3) {
      return getColor('top-quartile');
    } else if (score >= quartiles.q2) {
      return getColor('second-quartile');
    } else if (score >= quartiles.q1) {
      return getColor('third-quartile');
    } else {
      return getColor('bottom-quartile');
    }
  }

  /**
   * Get notification color based on hours notice required
   * Green: H24, operating hours only (no advance notice), or ≤12h notice
   * Blue: On request or 13-24h notice
   * Yellow/Orange: 25-48h notice or business day
   * Red: >48h notice or not available
   * Gray: Unknown/no data
   */
  private getNotificationColor(airport: Airport): string {
    const notification = airport.notification;

    // No notification data
    if (!notification) {
      return '#95a5a6'; // Gray
    }

    // H24 - no notice required
    if (notification.is_h24) {
      return '#28a745'; // Green
    }

    // Not available
    if (notification.notification_type === 'not_available') {
      return '#dc3545'; // Red
    }

    // On request - need to call ahead
    if (notification.is_on_request) {
      return '#007bff'; // Blue - moderate hassle
    }

    // Business day notice
    if (notification.notification_type === 'business_day') {
      return '#ffc107'; // Yellow - some hassle
    }

    const hours = notification.hours_notice;

    // "hours" type with no hours_notice = operating hours only, no advance notice needed
    if (hours === null || hours === undefined) {
      if (notification.notification_type === 'hours') {
        return '#28a745'; // Green - just operating hours constraint
      }
      return '#95a5a6'; // Gray - truly unknown
    }

    // Color based on hours
    if (hours <= 12) {
      return '#28a745'; // Green - easy, ≤12h
    } else if (hours <= 24) {
      return '#007bff'; // Blue - moderate, 13-24h
    } else if (hours <= 48) {
      return '#ffc107'; // Yellow - some hassle, 25-48h
    } else {
      return '#dc3545'; // Red - difficult, >48h
    }
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
    // Reference points (locate center, route airports) use larger blue dots
    // Default styling for reference points vs other highlights
    const isReferencePoint = highlight.id.startsWith('locate-center') || highlight.id.startsWith('route-airport-');
    
    const radius = highlight.radius || (isReferencePoint ? 14 : 15);
    const fillColor = highlight.color || (isReferencePoint ? '#007bff' : '#ff0000');
    const weight = isReferencePoint ? 3 : 3;
    const fillOpacity = isReferencePoint ? 0.6 : 0.7; // Slightly transparent so airport colors show through
    
    const marker = L.circleMarker([highlight.lat, highlight.lng], {
      radius,
      fillColor,
      color: '#ffffff',
      weight,
      opacity: 1,
      fillOpacity,
      id: highlight.id,
      // Ensure reference points are clickable but don't interfere with airport markers
      interactive: true
    });
    
    if (highlight.popup) {
      marker.bindPopup(highlight.popup);
    } else if (isReferencePoint) {
      // Add default popup for reference points
      if (highlight.id.startsWith('locate-center')) {
        marker.bindPopup('<b>Locate Center</b><br>Search origin point');
      } else if (highlight.id.startsWith('route-airport-')) {
        const icao = highlight.id.replace('route-airport-', '');
        marker.bindPopup(`<b>Route Airport: ${icao}</b><br>Input airport`);
      }
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
    if (!this.map || this.markers.size === 0) {
      console.warn('VisualizationEngine: Cannot fit bounds - no map or markers');
      return;
    }
    
    try {
      const markers = Array.from(this.markers.values()).map(e => e.marker).filter(m => m != null);
      if (markers.length === 0) {
        console.warn('VisualizationEngine: No valid markers to fit bounds');
        return;
      }
      
      const group = L.featureGroup(markers);
      const bounds = group.getBounds();
      
      // Ensure bounds are valid
      if (!bounds.isValid()) {
        console.warn('VisualizationEngine: Invalid bounds, skipping fitBounds');
        return;
      }
      
      // Fit bounds with padding (10% padding around all markers)
      this.map.fitBounds(bounds.pad(0.1), {
        maxZoom: 12 // Don't zoom in too close
      });
      
      console.log('VisualizationEngine: Fitted bounds to show all markers', {
        markerCount: markers.length,
        bounds: bounds.toBBoxString()
      });
    } catch (error) {
      console.error('VisualizationEngine: Error fitting bounds', error);
    }
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
  
  /**
   * Clear procedure lines
   */
  clearProcedureLines(): void {
    if (this.procedureLayer) {
      this.procedureLayer.clearLayers();
    }
    this.procedureLines.clear();
  }
}

