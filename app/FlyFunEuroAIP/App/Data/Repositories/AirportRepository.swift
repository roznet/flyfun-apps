//
//  AirportRepository.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import CoreLocation
import MapKit
import RZFlight
import OSLog
import RZUtilsSwift

// MARK: - Protocol

/// Protocol for airport data access - abstracts offline/online sources
/// All methods return RZFlight types directly
///
/// IMPORTANT: Filtering is done HERE, not in FilterConfig.
/// This keeps FilterConfig pure (no DB dependencies).
protocol AirportRepositoryProtocol: Sendable {
    // MARK: - Region-Based Queries (for map performance)
    
    /// Get airports within a bounding box - PRIMARY method for map display
    func airportsInRegion(
        boundingBox: BoundingBox,
        filters: FilterConfig,
        limit: Int
    ) async throws -> [RZFlight.Airport]
    
    // MARK: - General Queries
    
    /// Get airports matching filters (no region constraint)
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [RZFlight.Airport]
    
    /// Search airports by query string (ICAO, name, city)
    func searchAirports(query: String, limit: Int) async throws -> [RZFlight.Airport]
    
    /// Get airport with extended data (runways, procedures, AIP entries)
    func airportDetail(icao: String) async throws -> RZFlight.Airport?
    
    // MARK: - Route & Location
    
    /// Find airports along a route
    func airportsNearRoute(from: String, to: String, distanceNm: Int, filters: FilterConfig) async throws -> RouteResult
    
    /// Find airports near a coordinate
    func airportsNearLocation(center: CLLocationCoordinate2D, radiusNm: Int, filters: FilterConfig) async throws -> [RZFlight.Airport]
    
    // MARK: - In-Memory Filtering
    
    /// Apply cheap in-memory filters only (no DB access)
    func applyInMemoryFilters(_ filters: FilterConfig, to airports: [RZFlight.Airport]) -> [RZFlight.Airport]
    
    // MARK: - Metadata
    
    /// Get list of available countries in the database
    func availableCountries() async throws -> [String]
    
    /// Get set of ICAOs that are border crossing points
    func borderCrossingICAOs() async throws -> Set<String>
}

// MARK: - Data Source Strategy

/// Strategy for choosing data source based on connectivity
enum DataSourceStrategy: String, Sendable {
    case localOnly      // Always use local (offline mode)
    case remotePreferred  // Try remote first, fallback to local
    case localPreferred   // Try local first, use remote for missing data
}

// MARK: - Unified Repository

/// Main repository that switches between offline/online sources
/// Uses strategy pattern for flexible data source selection
@Observable
@MainActor
final class AirportRepository: AirportRepositoryProtocol {
    // MARK: - State
    private(set) var connectivityMode: ConnectivityMode = .offline
    private(set) var strategy: DataSourceStrategy = .localOnly
    
    // MARK: - Dependencies
    private let localDataSource: LocalAirportDataSource
    private var remoteDataSource: RemoteAirportDataSource?
    private let connectivityMonitor: ConnectivityMonitor
    
    // MARK: - Configuration
    
    /// Base URL for the API (configurable)
    static var apiBaseURL: String = "https://maps.flyfun.aero"
    
    // MARK: - Init
    
    init(localDataSource: LocalAirportDataSource, connectivityMonitor: ConnectivityMonitor) {
        self.localDataSource = localDataSource
        self.connectivityMonitor = connectivityMonitor
    }
    
    // MARK: - Remote Setup
    
    /// Initialize the remote data source (call when online)
    func setupRemoteDataSource() {
        guard remoteDataSource == nil else { return }
        
        do {
            remoteDataSource = try RemoteAirportDataSource(baseURLString: Self.apiBaseURL)
            Logger.app.info("Remote data source initialized")
        } catch {
            Logger.app.error("Failed to initialize remote data source: \(error.localizedDescription)")
        }
    }
    
    /// Update strategy based on connectivity and user preference
    func updateStrategy(preferRemote: Bool = false) {
        switch connectivityMode {
        case .offline:
            strategy = .localOnly
        case .online, .hybrid:
            strategy = preferRemote ? .remotePreferred : .localPreferred
            // Lazily initialize remote data source when we go online
            if strategy != .localOnly {
                setupRemoteDataSource()
            }
        }
        Logger.app.info("Repository strategy: \(strategy.rawValue)")
    }
    
    // MARK: - Connectivity Observation
    
    func startObservingConnectivity() {
        Task {
            for await mode in connectivityMonitor.modeStream {
                self.connectivityMode = mode
                self.updateStrategy()
                Logger.sync.info("Repository connectivity: \(mode.rawValue)")
            }
        }
    }
    
    // MARK: - Active Data Source
    
    /// Get the active data source based on current strategy
    private var activeDataSource: AirportRepositoryProtocol {
        switch strategy {
        case .localOnly, .localPreferred:
            return localDataSource
        case .remotePreferred:
            return remoteDataSource ?? localDataSource
        }
    }
    
    // MARK: - AirportRepositoryProtocol
    
    nonisolated func airportsInRegion(
        boundingBox: BoundingBox,
        filters: FilterConfig,
        limit: Int
    ) async throws -> [RZFlight.Airport] {
        // Always use local for region queries (faster, works offline)
        return try await localDataSource.airportsInRegion(boundingBox: boundingBox, filters: filters, limit: limit)
    }
    
    nonisolated func airports(matching filters: FilterConfig, limit: Int) async throws -> [RZFlight.Airport] {
        return try await localDataSource.airports(matching: filters, limit: limit)
    }
    
    nonisolated func searchAirports(query: String, limit: Int) async throws -> [RZFlight.Airport] {
        return try await localDataSource.searchAirports(query: query, limit: limit)
    }
    
    nonisolated func airportDetail(icao: String) async throws -> RZFlight.Airport? {
        // Use local for detail - it has full data loaded
        return try await localDataSource.airportDetail(icao: icao)
    }
    
    nonisolated func airportsNearRoute(from: String, to: String, distanceNm: Int, filters: FilterConfig) async throws -> RouteResult {
        return try await localDataSource.airportsNearRoute(from: from, to: to, distanceNm: distanceNm, filters: filters)
    }
    
    nonisolated func airportsNearLocation(center: CLLocationCoordinate2D, radiusNm: Int, filters: FilterConfig) async throws -> [RZFlight.Airport] {
        return try await localDataSource.airportsNearLocation(center: center, radiusNm: radiusNm, filters: filters)
    }
    
    nonisolated func applyInMemoryFilters(_ filters: FilterConfig, to airports: [RZFlight.Airport]) -> [RZFlight.Airport] {
        var result = airports
        
        if let country = filters.country {
            result = result.inCountry(country)
        }
        if filters.hasHardRunway == true {
            result = result.withHardRunways()
        }
        if filters.hasProcedures == true {
            result = result.withProcedures()
        }
        if filters.hasPrecisionApproach == true {
            result = result.withPrecisionApproaches()
        }
        if let minLength = filters.minRunwayLengthFt {
            result = result.withRunwayLength(minimumFeet: minLength)
        }
        if let minLength = filters.minRunwayLengthFt, let maxLength = filters.maxRunwayLengthFt {
            result = result.withRunwayLength(minimumFeet: minLength, maximumFeet: maxLength)
        } else if let maxLength = filters.maxRunwayLengthFt {
            result = result.withRunwayLength(minimumFeet: 0, maximumFeet: maxLength)
        }
        if filters.hasLightedRunway == true {
            result = result.withLightedRunways()
        }
        
        return result
    }
    
    nonisolated func availableCountries() async throws -> [String] {
        return try await localDataSource.availableCountries()
    }
    
    nonisolated func borderCrossingICAOs() async throws -> Set<String> {
        return try await localDataSource.borderCrossingICAOs()
    }
    
    // MARK: - Remote-Only Methods
    
    /// Check if remote API is available
    func checkAPIAvailability() async -> Bool {
        guard let remote = remoteDataSource else {
            setupRemoteDataSource()
            guard let remote = remoteDataSource else { return false }
            return await remote.isAPIAvailable()
        }
        return await remote.isAPIAvailable()
    }
}

