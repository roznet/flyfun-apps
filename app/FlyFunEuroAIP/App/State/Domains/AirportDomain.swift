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
    
    // MARK: - Cached Lookups (for legend coloring)
    /// Set of ICAOs that are border crossing points - loaded once at startup
    var borderCrossingICAOs: Set<String> = []
    
    // MARK: - Region Loading
    private var regionUpdateTask: Task<Void, Never>?
    
    // MARK: - Init
    
    init(repository: AirportRepositoryProtocol) {
        self.repository = repository
    }
    
    // MARK: - Region-Based Loading
    
    /// Called when map region changes - loads airports for visible area
    /// Uses debouncing to avoid excessive queries during pan/zoom
    func onRegionChange(_ region: MKCoordinateRegion) {
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
            return
        }
        
        isSearching = true
        defer { isSearching = false }
        
        // Check if it's a route query (e.g., "EGTF LFMD")
        if isRouteQuery(query) {
            try await searchRoute(query)
        } else {
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
        
        let result = try await repository.airportsNearRoute(
            from: from, to: to, distanceNm: 50, filters: filters
        )
        airports = result.airports
        
        // Build route coordinates
        if let depAirport = try await repository.airportDetail(icao: from),
           let arrAirport = try await repository.airportDetail(icao: to) {
            activeRoute = RouteVisualization(
                coordinates: [depAirport.coord, arrAirport.coord],
                departure: from,
                destination: to
            )
        }
        
        fitMapToRoute()
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
        withAnimation(.snappy) {
            mapPosition = .region(MKCoordinateRegion(
                center: coordinate,
                span: MKCoordinateSpan(latitudeDelta: span, longitudeDelta: span)
            ))
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
        
        withAnimation(.snappy) {
            mapPosition = .region(MKCoordinateRegion(center: center, span: span))
        }
    }
    
    // MARK: - Route & Highlights
    
    func clearRoute() {
        activeRoute = nil
        // Clear route-related highlights but keep chat highlights
        highlights = highlights.filter { !$0.key.hasPrefix("route-") }
    }
    
    func clearChatHighlights() {
        highlights = highlights.filter { !$0.key.hasPrefix("chat-") }
    }
    
    // MARK: - Visualization (from Chat)
    
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
        if let region = visibleRegion {
            try await loadAirportsInRegion(region)
        } else {
            try await load()
        }
    }
    
    func resetFilters() {
        filters.reset()
        Task {
            try? await applyFilters()
        }
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

