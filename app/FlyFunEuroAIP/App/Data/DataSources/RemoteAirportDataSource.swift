//
//  RemoteAirportDataSource.swift
//  FlyFunEuroAIP
//
//  Remote data source using API.
//  Implements same protocol as LocalAirportDataSource for seamless switching.
//

import Foundation
import CoreLocation
import RZFlight
import OSLog
import RZUtilsSwift

/// Remote data source using the FlyFun EuroAIP API
/// Returns RZFlight models by converting API responses through adapters
final class RemoteAirportDataSource: AirportRepositoryProtocol, @unchecked Sendable {
    
    // MARK: - Dependencies
    
    private let apiClient: APIClient
    
    // MARK: - Cache
    
    /// Cache border crossing ICAOs from API (loaded once)
    private var borderCrossingCache: Set<String>?
    
    // MARK: - Init
    
    init(apiClient: APIClient) {
        self.apiClient = apiClient
        Logger.app.info("RemoteAirportDataSource initialized with base URL: \(apiClient.baseURL.absoluteString)")
    }
    
    /// Convenience initializer with URL string
    convenience init(baseURLString: String) throws {
        let apiClient = try APIClient(baseURLString: baseURLString)
        self.init(apiClient: apiClient)
    }
    
    // MARK: - Region-Based Query
    
    func airportsInRegion(
        boundingBox: BoundingBox,
        filters: FilterConfig,
        limit: Int
    ) async throws -> [RZFlight.Airport] {
        // API doesn't have bounding box endpoint yet
        // For now, get all airports with filters and filter client-side
        // TODO: Add bounding box endpoint to API
        
        let endpoint = Endpoint.airports(filters: filters, limit: limit)
        let response: [APIAirportSummary] = try await apiClient.get(endpoint)
        
        // Filter by bounding box client-side
        let filtered = response.filter { airport in
            guard let lat = airport.latitudeDeg, let lon = airport.longitudeDeg else {
                return false
            }
            return boundingBox.contains(CLLocationCoordinate2D(latitude: lat, longitude: lon))
        }
        
        return filtered.map { APIAirportAdapter.toRZFlight($0) }
    }
    
    // MARK: - General Queries
    
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [RZFlight.Airport] {
        let endpoint = Endpoint.airports(filters: filters, limit: limit)
        let response: [APIAirportSummary] = try await apiClient.get(endpoint)
        return response.map { APIAirportAdapter.toRZFlight($0) }
    }
    
    func searchAirports(query: String, limit: Int) async throws -> [RZFlight.Airport] {
        let endpoint = Endpoint.searchAirports(query: query, limit: limit)
        let response: [APIAirportSummary] = try await apiClient.get(endpoint)
        return response.map { APIAirportAdapter.toRZFlight($0) }
    }
    
    func airportDetail(icao: String) async throws -> RZFlight.Airport? {
        let endpoint = Endpoint.airportDetail(icao: icao)
        let response: APIAirportDetail = try await apiClient.get(endpoint)
        return APIAirportAdapter.toRZFlightWithExtendedData(response)
    }
    
    // MARK: - Route & Location
    
    func airportsNearRoute(from: String, to: String, distanceNm: Int, filters: FilterConfig) async throws -> RouteResult {
        let endpoint = Endpoint.routeSearch(from: from, to: to, distanceNm: distanceNm, filters: filters)
        let response: APIRouteSearchResponse = try await apiClient.get(endpoint)
        return APIRouteResultAdapter.toRouteResult(response)
    }
    
    func airportsNearLocation(center: CLLocationCoordinate2D, radiusNm: Int, filters: FilterConfig) async throws -> [RZFlight.Airport] {
        let endpoint = Endpoint.locateAirports(
            latitude: center.latitude,
            longitude: center.longitude,
            radiusNm: radiusNm,
            filters: filters
        )
        let response: APILocateResponse = try await apiClient.get(endpoint)
        return response.airports.map { APIAirportAdapter.toRZFlight($0) }
    }
    
    // MARK: - In-Memory Filtering
    
    func applyInMemoryFilters(_ filters: FilterConfig, to airports: [RZFlight.Airport]) -> [RZFlight.Airport] {
        // For remote data source, filtering is done server-side
        // This method is mostly for compatibility with the protocol
        // Only apply filters that might not be supported by the API
        
        var result = airports
        
        // Country filter (usually done server-side, but double-check)
        if let country = filters.country {
            result = result.filter { $0.country == country }
        }
        
        return result
    }
    
    // MARK: - Metadata
    
    func availableCountries() async throws -> [String] {
        struct CountryResponse: Codable {
            let code: String
            let name: String
            let count: Int
        }
        
        let response: [CountryResponse] = try await apiClient.get(Endpoint.countries)
        return response.map(\.code).sorted()
    }
    
    func borderCrossingICAOs() async throws -> Set<String> {
        // Check cache first
        if let cached = borderCrossingCache {
            return cached
        }
        
        // Load border crossing airports from API
        let filters = FilterConfig(pointOfEntry: true)
        let endpoint = Endpoint.airports(filters: filters, limit: 5000)
        let response: [APIAirportSummary] = try await apiClient.get(endpoint)
        
        let icaos = Set(response.map(\.ident))
        borderCrossingCache = icaos
        
        Logger.app.info("Loaded \(icaos.count) border crossing ICAOs from API")
        return icaos
    }
}

// MARK: - Health Check

extension RemoteAirportDataSource {
    
    /// Check if the API is reachable
    func isAPIAvailable() async -> Bool {
        do {
            struct HealthResponse: Codable {
                let status: String
            }
            let response: HealthResponse = try await apiClient.get(Endpoint.health)
            return response.status == "ok"
        } catch {
            Logger.app.warning("API health check failed: \(error.localizedDescription)")
            return false
        }
    }
}

