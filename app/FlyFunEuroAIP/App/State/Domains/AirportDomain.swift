//
//  AirportDomain.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import SwiftUI
import MapKit
import RZFlight
import OSLog
import RZUtilsSwift

/// Domain: Airport data, filters, and map state
/// This is a composed part of AppState, not a standalone ViewModel.
@Observable
@MainActor
final class AirportDomain {
    // MARK: - Dependencies
    /// Exposed for views that need to call repository methods directly (e.g., CountryPicker)
    let repository: AirportRepositoryProtocol
    
    // MARK: - Airport Data (already filtered by repository)
    var airports: [RZFlight.Airport] = []
    var selectedAirport: RZFlight.Airport?
    var searchResults: [RZFlight.Airport] = []
    var isSearching: Bool = false
    
    // MARK: - Filters (pure data, no DB logic)
    var filters: FilterConfig = .default
    
    // MARK: - Map State
    var mapPosition: MapCameraPosition = .region(.europe)
    var visibleRegion: MKCoordinateRegion?
    var legendMode: LegendMode = .airportType
    var highlights: [String: MapHighlight] = [:]
    var activeRoute: RouteVisualization?
    
    // MARK: - Procedure Lines
    /// Procedure lines for visualization (keyed by airport ICAO)
    var procedureLines: [String: [RZFlight.Airport.ProcedureLine]] = [:]
    private var procedureLinesLoadingTask: Task<Void, Never>?
    
    // MARK: - Cached Lookups (for legend coloring)
    /// Set of ICAOs that are border crossing points - loaded once at startup
    var borderCrossingICAOs: Set<String> = []
    
    // MARK: - Region Loading
    private var regionUpdateTask: Task<Void, Never>?
    
    // MARK: - Search State
    /// Track when search results are active to prevent region-based loading from overwriting them
    var isSearchActive: Bool = false
    
    // MARK: - Init
    
    init(repository: AirportRepositoryProtocol) {
        self.repository = repository
    }
    
    // MARK: - Region-Based Loading
    
    /// Called when map region changes - loads airports for visible area
    /// Uses debouncing to avoid excessive queries during pan/zoom
    /// Respects search state: won't overwrite search results unless search is cleared
    func onRegionChange(_ region: MKCoordinateRegion) {
        // Don't load if search is active - preserve search results
        guard !isSearchActive else {
            // Skip region load when search is active
            return
        }
        
        regionUpdateTask?.cancel()
        regionUpdateTask = Task {
            // Debounce: wait 300ms after last region change
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            
            visibleRegion = region
            try? await loadAirportsInRegion(region)
        }
    }
    
    /// Load airports within the visible map region
    private func loadAirportsInRegion(_ region: MKCoordinateRegion) async throws {
        // Calculate bounding box with some padding for smooth panning
        let paddedRegion = region.paddedBy(factor: 1.3)
        
        airports = try await repository.airportsInRegion(
            boundingBox: paddedRegion.boundingBox,
            filters: filters,
            limit: 500  // Cap markers for performance
        )
        Logger.app.info("Loaded \(self.airports.count) airports in region")
        
        // Load procedure lines if in procedure legend mode
        if legendMode == .procedures {
            await loadProcedureLines()
        }
    }
    
    /// Initial load - loads airports for default Europe view
    func load() async throws {
        // Load border crossing ICAOs for legend coloring
        borderCrossingICAOs = try await repository.borderCrossingICAOs()
        Logger.app.info("Loaded \(self.borderCrossingICAOs.count) border crossing ICAOs")
        
        let defaultRegion = MKCoordinateRegion.europe
        visibleRegion = defaultRegion
        try await loadAirportsInRegion(defaultRegion)
    }
    
    /// Check if an airport is a border crossing (uses cached set)
    func isBorderCrossing(_ airport: RZFlight.Airport) -> Bool {
        borderCrossingICAOs.contains(airport.icao)
    }
    
    // MARK: - Search
    
    func search(query: String) async throws {
        guard !query.isEmpty else {
            searchResults = []
            isSearchActive = false
            // Clear search state - allow region loading to resume
            if visibleRegion != nil {
                try? await loadAirportsInRegion(visibleRegion!)
            }
            return
        }
        
        isSearching = true
        defer { isSearching = false }
        
        // Check if it's a route query (e.g., "EGTF LFMD")
        if isRouteQuery(query) {
            try await searchRoute(query)
        } else {
            // Regular search - clear route state and set search active to preserve results
            activeRoute = nil
            highlights = highlights.filter { !$0.key.hasPrefix("route-") }
            isSearchActive = true
            searchResults = try await repository.searchAirports(query: query, limit: 50)
        }
    }
    
    private func isRouteQuery(_ query: String) -> Bool {
        let parts = query.uppercased().split(separator: " ")
        return parts.count >= 2 &&
               parts.allSatisfy { $0.count == 4 && $0.allSatisfy { $0.isLetter } }
    }
    
    private func searchRoute(_ query: String) async throws {
        let icaos = query.uppercased().split(separator: " ").map(String.init)
        guard icaos.count >= 2, let from = icaos.first, let to = icaos.last else { return }
        
        // Mark search as active to prevent region loading from overwriting results
        isSearchActive = true
        
        // Clear previous route state
        activeRoute = nil
        highlights = highlights.filter { !$0.key.hasPrefix("route-") }
        
        let result = try await repository.airportsNearRoute(
            from: from, to: to, distanceNm: 50, filters: filters
        )
        airports = result.airports
        
        // Build route coordinates - ensure we have valid coordinates
        if let depAirport = try await repository.airportDetail(icao: from),
           let arrAirport = try await repository.airportDetail(icao: to) {
            activeRoute = RouteVisualization(
                coordinates: [depAirport.coord, arrAirport.coord],
                departure: from,
                destination: to
            )
            
            // Update visibleRegion to match route bounds
            let minLat = min(depAirport.coord.latitude, arrAirport.coord.latitude)
            let maxLat = max(depAirport.coord.latitude, arrAirport.coord.latitude)
            let minLon = min(depAirport.coord.longitude, arrAirport.coord.longitude)
            let maxLon = max(depAirport.coord.longitude, arrAirport.coord.longitude)
            
            visibleRegion = MKCoordinateRegion(
                center: CLLocationCoordinate2D(
                    latitude: (minLat + maxLat) / 2,
                    longitude: (minLon + maxLon) / 2
                ),
                span: MKCoordinateSpan(
                    latitudeDelta: (maxLat - minLat) * 1.5,
                    longitudeDelta: (maxLon - minLon) * 1.5
                )
            )
            
            fitMapToRoute()
        } else {
            Logger.app.warning("Could not load route airports: \(from) or \(to) not found")
            // Still show airports even if route line can't be drawn
        }
        
        Logger.app.info("Route search active - showing \(airports.count) airports within 50nm")
    }
    
    // MARK: - Selection
    
    func select(_ airport: RZFlight.Airport) {
        selectedAirport = airport
        focusMap(on: airport.coord)
    }
    
    func clearSelection() {
        selectedAirport = nil
    }
    
    // MARK: - Map Control
    
    func focusMap(on coordinate: CLLocationCoordinate2D, span: Double = 2.0) {
        let region = MKCoordinateRegion(
            center: coordinate,
            span: MKCoordinateSpan(latitudeDelta: span, longitudeDelta: span)
        )
        
        // Sync visibleRegion with mapPosition
        visibleRegion = region
        
        withAnimation(.snappy) {
            mapPosition = .region(region)
        }
    }
    
    private func fitMapToRoute() {
        guard let route = activeRoute, route.coordinates.count >= 2 else { return }
        
        let minLat = route.coordinates.map(\.latitude).min()!
        let maxLat = route.coordinates.map(\.latitude).max()!
        let minLon = route.coordinates.map(\.longitude).min()!
        let maxLon = route.coordinates.map(\.longitude).max()!
        
        let center = CLLocationCoordinate2D(
            latitude: (minLat + maxLat) / 2,
            longitude: (minLon + maxLon) / 2
        )
        let span = MKCoordinateSpan(
            latitudeDelta: (maxLat - minLat) * 1.5,
            longitudeDelta: (maxLon - minLon) * 1.5
        )
        
        let region = MKCoordinateRegion(center: center, span: span)
        
        // Sync visibleRegion with mapPosition
        visibleRegion = region
        
        withAnimation(.snappy) {
            mapPosition = .region(region)
        }
    }
    
    // MARK: - Route & Highlights
    
    func clearRoute() {
        activeRoute = nil
        // Clear route-related highlights but keep chat highlights
        highlights = highlights.filter { !$0.key.hasPrefix("route-") }
        // Clear search state when route is cleared
        isSearchActive = false
        // Reload airports for current region
        if let region = visibleRegion {
            Task {
                try? await loadAirportsInRegion(region)
            }
        }
    }
    
    /// Clear search results and resume normal region-based loading
    func clearSearch() {
        searchResults = []
        isSearchActive = false
        // Reload airports for current region
        if let region = visibleRegion {
            Task {
                try? await loadAirportsInRegion(region)
            }
        } else {
            Task {
                try? await load()
            }
        }
    }
    
    func clearChatHighlights() {
        highlights = highlights.filter { !$0.key.hasPrefix("chat-") }
    }
    
    // MARK: - Visualization (from Chat)
    
    /// Apply visualization from chat API response
    func applyVisualization(_ chatPayload: ChatVisualizationPayload) {
        Logger.app.info("Applying chat visualization: \(chatPayload.kind.rawValue)")
        
        // Clear previous chat highlights
        clearChatHighlights()
        
        // Apply filters if provided
        if let chatFilters = chatPayload.filters {
            filters = chatFilters.toFilterConfig()
        }
        
        // Apply visualization data
        if let viz = chatPayload.visualization {
            // Handle markers
            if let markers = viz.markers, !markers.isEmpty {
                // Add highlights for each marker
                for marker in markers {
                    let id = "chat-\(marker.icao)"
                    highlights[id] = MapHighlight(
                        id: id,
                        coordinate: marker.coordinate.clLocationCoordinate,
                        color: colorForMarkerStyle(marker.style),
                        radius: 15000,
                        popup: marker.name ?? marker.icao
                    )
                }
                
                // Fit map to show all markers
                if markers.count > 1 {
                    fitMapToMarkers(markers)
                } else if let first = markers.first {
                    focusMap(on: first.coordinate.clLocationCoordinate, span: 2.0)
                }
            }
            
            // Handle route
            if let route = viz.route {
                // Prefer using coordinates directly from the payload
                if let depCoord = route.departureCoord,
                   let destCoord = route.destinationCoord {
                    activeRoute = RouteVisualization(
                        coordinates: [depCoord.clLocationCoordinate, destCoord.clLocationCoordinate],
                        departure: route.departure ?? "DEP",
                        destination: route.destination ?? "DEST"
                    )
                    Logger.app.info("Route created from coordinates: \(route.departure ?? "?") to \(route.destination ?? "?")")
                    fitMapToRoute()
                }
                // Fallback: try to find airports in current list
                else if let departure = route.departure,
                        let destination = route.destination,
                        let depAirport = airports.first(where: { $0.icao == departure }),
                        let destAirport = airports.first(where: { $0.icao == destination }) {
                    activeRoute = RouteVisualization(
                        coordinates: [depAirport.coord, destAirport.coord],
                        departure: departure,
                        destination: destination
                    )
                    Logger.app.info("Route created from airport lookup: \(departure) to \(destination)")
                    fitMapToRoute()
                } else {
                    Logger.app.warning("Could not create route - no coordinates and airports not found")
                }
            }
            
            // Handle center point
            if let center = viz.center {
                focusMap(on: center.clLocationCoordinate, span: viz.zoom ?? 5.0)
            }
        }
        
        // Handle airports list (for highlighting)
        if let airportICAOs = chatPayload.airports {
            for icao in airportICAOs {
                let id = "chat-\(icao)"
                // Find the airport to get its coordinate
                if let airport = airports.first(where: { $0.icao == icao }) {
                    highlights[id] = MapHighlight(
                        id: id,
                        coordinate: airport.coord,
                        color: .blue,
                        radius: 15000,
                        popup: airport.name
                    )
                }
            }
        }
    }
    
    private func colorForMarkerStyle(_ style: MapMarker.MarkerStyle?) -> MapHighlight.HighlightColor {
        switch style {
        case .departure: return .green
        case .destination: return .red
        case .alternate: return .orange
        case .waypoint: return .purple
        case .result: return .blue
        case .highlight: return .orange
        case .default, .none: return .blue
        }
    }
    
    private func fitMapToMarkers(_ markers: [MapMarker]) {
        guard !markers.isEmpty else { return }
        
        let coords = markers.map { $0.coordinate.clLocationCoordinate }
        let minLat = coords.map(\.latitude).min() ?? 0
        let maxLat = coords.map(\.latitude).max() ?? 0
        let minLon = coords.map(\.longitude).min() ?? 0
        let maxLon = coords.map(\.longitude).max() ?? 0
        
        let center = CLLocationCoordinate2D(
            latitude: (minLat + maxLat) / 2,
            longitude: (minLon + maxLon) / 2
        )
        let span = MKCoordinateSpan(
            latitudeDelta: (maxLat - minLat) * 1.5 + 0.5,
            longitudeDelta: (maxLon - minLon) * 1.5 + 0.5
        )
        
        mapPosition = .region(MKCoordinateRegion(center: center, span: span))
    }
    
    /// Apply internal visualization payload (for programmatic use)
    func applyVisualization(_ payload: VisualizationPayload) {
        switch payload.kind {
        case .markers:
            airports = payload.airports
            clearChatHighlights()
            addHighlights(for: payload.airports, prefix: "chat")
            
        case .routeWithMarkers:
            airports = payload.airports
            if let route = payload.route {
                activeRoute = route
            }
            addHighlights(for: payload.airports, prefix: "route")
            fitMapToRoute()
            
        case .markerWithDetails:
            if let first = payload.airports.first {
                selectedAirport = first
                focusMap(on: first.coord, span: 0.5)
            }
            
        case .regionFocus:
            if let point = payload.point {
                focusMap(on: point, span: 5.0)
            }
        }
        
        // Apply filter profile if provided
        if let filterProfile = payload.filterProfile {
            filters = filterProfile
        }
    }
    
    private func addHighlights(for airports: [RZFlight.Airport], prefix: String) {
        for airport in airports {
            let id = "\(prefix)-\(airport.icao)"
            highlights[id] = MapHighlight(
                id: id,
                coordinate: airport.coord,
                color: .blue,
                radius: 20000,
                popup: airport.name
            )
        }
    }
    
    // MARK: - Filter Actions
    
    func applyFilters() async throws {
        // Clear search state when filters are applied - filters take precedence
        isSearchActive = false
        searchResults = []
        
        // Clear route state when filters are applied
        activeRoute = nil
        highlights = highlights.filter { !$0.key.hasPrefix("route-") }
        
        // Use current visible region, or fallback to default Europe region
        // visibleRegion is kept in sync by onMapCameraChange, so it should be current
        let region: MKCoordinateRegion
        if let visible = visibleRegion {
            region = visible
        } else {
            // Fallback to default Europe region if visibleRegion hasn't been set yet
            region = .europe
            visibleRegion = region
        }
        
        try await loadAirportsInRegion(region)
    }
    
    func resetFilters() {
        filters.reset()
        Task {
            try? await applyFilters()
        }
    }
    
    // MARK: - Procedure Lines Loading
    
    /// Load procedure lines for visible airports
    /// Only loads for airports that have procedures and aren't already loaded
    func loadProcedureLines() async {
        // Cancel any existing loading task
        procedureLinesLoadingTask?.cancel()
        
        procedureLinesLoadingTask = Task {
            // Filter to airports with procedures that don't have lines loaded yet
            let airportsToLoad = airports.filter { airport in
                !airport.procedures.isEmpty && procedureLines[airport.icao] == nil
            }
            
            // Limit to reasonable number for performance
            let airportsToProcess = Array(airportsToLoad.prefix(50))
            
            for airport in airportsToProcess {
                guard !Task.isCancelled else { break }
                
                // Get procedure lines from the airport
                let result = airport.procedureLines(distanceNm: 10.0)
                if !result.procedureLines.isEmpty {
                    procedureLines[airport.icao] = result.procedureLines
                }
            }
            
            Logger.app.info("Loaded procedure lines for \(procedureLines.count) airports")
        }
        
        await procedureLinesLoadingTask?.value
    }
    
    /// Clear procedure lines (e.g., when switching away from procedure legend mode)
    func clearProcedureLines() {
        procedureLines.removeAll()
        procedureLinesLoadingTask?.cancel()
        procedureLinesLoadingTask = nil
    }
    
    // MARK: - Metadata Loading
    
    /// Load available countries from the repository
    func loadAvailableCountries() async -> [String] {
        do {
            return try await repository.availableCountries()
        } catch {
            Logger.app.error("Failed to load countries: \(error.localizedDescription)")
            return []
        }
    }
}

// MARK: - Visualization Payload

/// Payload for chat-driven map visualization
struct VisualizationPayload: Sendable {
    enum Kind: Sendable {
        case markers
        case routeWithMarkers
        case markerWithDetails
        case regionFocus
    }
    
    let kind: Kind
    let airports: [RZFlight.Airport]
    let route: RouteVisualization?
    let point: CLLocationCoordinate2D?
    let filterProfile: FilterConfig?
    
    init(
        kind: Kind,
        airports: [RZFlight.Airport] = [],
        route: RouteVisualization? = nil,
        point: CLLocationCoordinate2D? = nil,
        filterProfile: FilterConfig? = nil
    ) {
        self.kind = kind
        self.airports = airports
        self.route = route
        self.point = point
        self.filterProfile = filterProfile
    }
}

