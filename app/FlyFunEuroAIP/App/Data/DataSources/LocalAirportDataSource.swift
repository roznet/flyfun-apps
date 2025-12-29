//
//  LocalAirportDataSource.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import CoreLocation
import RZFlight
import FMDB
import OSLog
import RZUtilsSwift

/// Local data source using bundled SQLite database
/// Returns RZFlight.Airport directly - no conversion needed
///
/// IMPORTANT: All filtering logic lives HERE, not in FilterConfig.
/// FilterConfig is pure data; this class knows how to apply it.
final class LocalAirportDataSource: AirportRepositoryProtocol, @unchecked Sendable {
    // MARK: - Dependencies
    private let db: FMDatabase
    private let knownAirports: KnownAirports
    
    // MARK: - Init
    
    init(databasePath: String) throws {
        let db = FMDatabase(path: databasePath)
        guard db.open() else {
            throw AppError.databaseOpenFailed(path: databasePath)
        }
        self.db = db
        self.knownAirports = KnownAirports(db: db, where: "LENGTH(icao_code) = 4 and ISO_COUNTRY != 'RU'")
        
        // Bulk load all extended data upfront for efficient legend rendering
        // This is faster than loading per-airport: 4 queries vs ~16,000
        Logger.app.info("Loading extended airport data...")
        knownAirports.loadAllExtendedData()
        Logger.app.info("LocalAirportDataSource initialized with \(knownAirports.matching(needle: "").count) airports")
    }
    
    /// Initialize from an existing KnownAirports instance
    init(knownAirports: KnownAirports, db: FMDatabase) {
        self.knownAirports = knownAirports
        self.db = db
    }
    
    // MARK: - Region-Based Query (Primary for Map Performance)
    
    func airportsInRegion(
        boundingBox: BoundingBox,
        filters: FilterConfig,
        limit: Int
    ) async throws -> [RZFlight.Airport] {
        // Filter airports in the bounding box
        // Use matching with empty string to get all, then filter by region
        let regionAirports = knownAirports.airportsWithinBox(minCoord: boundingBox.minCoord, maxCoord: boundingBox.maxCoord)
        return Array(regionAirports.prefix(limit))
    }
    
    // MARK: - General Queries
    
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [RZFlight.Airport] {
        var airports: [RZFlight.Airport]
        
        // Use KnownAirports methods for DB-dependent filters
        if filters.pointOfEntry == true {
            airports = knownAirports.airportsWithBorderCrossing()
        } else if let aipField = filters.aipField {
            airports = knownAirports.airportsWithAIPField(aipField, useStandardized: true)
        } else {
            // Get all airports using matching with empty string
            airports = knownAirports.matching(needle: "")
        }
        
        // Apply cheap in-memory filters
        airports = applyInMemoryFilters(filters, to: airports)
        
        return Array(airports.prefix(limit))
    }
    
    func searchAirports(query: String, limit: Int) async throws -> [RZFlight.Airport] {
        return Array(knownAirports.matching(needle: query).prefix(limit))
    }
    
    func airportDetail(icao: String) async throws -> RZFlight.Airport? {
        return knownAirports.airportWithExtendedData(icao: icao)
    }
    
    func airportsNearRoute(from: String, to: String, distanceNm: Int, filters: FilterConfig) async throws -> RouteResult {
        let routeAirports = knownAirports.airportsNearRoute([from, to], within: Double(distanceNm))
        let filtered = applyInMemoryFilters(filters, to: routeAirports)
        return RouteResult(airports: filtered, departure: from, destination: to)
    }
    
    func airportsNearLocation(center: CLLocationCoordinate2D, radiusNm: Int, filters: FilterConfig) async throws -> [RZFlight.Airport] {
        // Use KnownAirports KDTree-based spatial query
        // Use 500 to ensure we get enough to filter by notification
        let nearbyAirports = knownAirports.nearest(coord: center, count: 500)
        
        // Filter by actual distance (KDTree returns approximate nearest, verify with haversine)
        let radiusMeters = Double(radiusNm) * 1852.0
        let filtered = nearbyAirports.filter { airport in
            let distance = center.distance(to: airport.coord)
            return distance <= radiusMeters
        }
        
        // Apply additional filters
        return applyInMemoryFilters(filters, to: filtered)
    }
    
    // MARK: - In-Memory Filtering (No DB Access)
    
    func applyInMemoryFilters(_ filters: FilterConfig, to airports: [RZFlight.Airport]) -> [RZFlight.Airport] {
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
    
    // MARK: - Metadata
    
    func availableCountries() async throws -> [String] {
        // Get all airports and extract unique countries
        let allAirports = knownAirports.matching(needle: "")
        let countries = Set(allAirports.compactMap { $0.country.isEmpty ? nil : $0.country })
        return countries.sorted()
    }
    
    func borderCrossingICAOs() async throws -> Set<String> {
        // Get all border crossing airports and return their ICAOs
        let borderCrossingAirports = knownAirports.airportsWithBorderCrossing()
        return Set(borderCrossingAirports.map(\.icao))
    }
}

