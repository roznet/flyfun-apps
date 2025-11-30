//
//  APIAirportAdapter.swift
//  FlyFunEuroAIP
//
//  Converts API response models to RZFlight models.
//  This is the ONLY place where API models are converted - the rest of the app uses RZFlight types.
//

import Foundation
import CoreLocation
import RZFlight

// MARK: - Airport Adapter

enum APIAirportAdapter {
    
    /// Convert API summary to RZFlight.Airport (basic data only)
    static func toRZFlight(_ api: APIAirportSummary) -> Airport {
        let airport = Airport(
            location: CLLocationCoordinate2D(
                latitude: api.latitudeDeg ?? 0,
                longitude: api.longitudeDeg ?? 0
            ),
            icao: api.ident
        )
        
        // Set basic properties that Airport exposes
        // Note: Some properties may need RZFlight enhancement for proper initialization
        // For now, we create a basic Airport and rely on the fact that
        // summary responses include computed properties like hasProcedures
        
        return airport
    }
    
    /// Convert API detail response to RZFlight.Airport with full data
    static func toRZFlightWithExtendedData(_ api: APIAirportDetail) -> Airport {
        let airport = Airport(
            location: CLLocationCoordinate2D(
                latitude: api.latitudeDeg ?? 0,
                longitude: api.longitudeDeg ?? 0
            ),
            icao: api.ident
        )
        
        // Note: Full conversion requires RZFlight to expose initializers for these properties
        // This is tracked in the implementation plan as a proposed RZFlight enhancement
        // For now, the airport will have basic location data
        // Extended data (runways, procedures, AIP) would need RZFlight modifications
        
        return airport
    }
}

// MARK: - Runway Adapter

enum APIRunwayAdapter {
    
    /// Convert API runway to RZFlight.Runway
    /// Note: This requires RZFlight to expose an API-friendly initializer
    static func toRZFlight(_ api: APIRunway) -> Runway? {
        // RZFlight.Runway currently only has FMResultSet initializer
        // This would need a proposed enhancement to RZFlight
        // For now, return nil and log a warning
        
        // TODO: Implement when RZFlight exposes API-friendly initializer
        // Proposal tracked in IOS_APP_IMPLEMENTATION.md
        return nil
    }
}

// MARK: - Procedure Adapter

enum APIProcedureAdapter {
    
    /// Convert API procedure to RZFlight.Procedure
    /// Note: This requires RZFlight to expose an API-friendly initializer
    static func toRZFlight(_ api: APIProcedure) -> Procedure? {
        // RZFlight.Procedure currently only has FMResultSet initializer
        // This would need a proposed enhancement to RZFlight
        
        // TODO: Implement when RZFlight exposes API-friendly initializer
        return nil
    }
}

// MARK: - AIP Entry Adapter

enum APIAIPEntryAdapter {
    
    /// Convert API AIP entry to RZFlight.AIPEntry
    /// Note: This requires RZFlight to expose an API-friendly initializer
    static func toRZFlight(_ api: APIAIPEntry) -> AIPEntry? {
        // RZFlight.AIPEntry currently only has FMResultSet initializer
        
        // TODO: Implement when RZFlight exposes API-friendly initializer
        return nil
    }
}

// MARK: - Route Result Adapter

enum APIRouteResultAdapter {
    
    /// Convert API route search response to RouteResult
    static func toRouteResult(_ api: APIRouteSearchResponse) -> RouteResult {
        let airports = api.airports.map { APIAirportAdapter.toRZFlight($0) }
        return RouteResult(
            airports: airports,
            departure: api.departure?.ident ?? "",
            destination: api.destination?.ident ?? ""
        )
    }
}

// MARK: - Wrapper for API Airports with Metadata

/// Temporary wrapper that holds API data until RZFlight can be enhanced
/// This allows us to pass through API-specific fields that RZFlight.Airport doesn't have
struct EnrichedAirport {
    let airport: Airport
    let apiData: APIAirportSummary
    
    // Computed properties from API data
    var hasProcedures: Bool { apiData.hasProcedures }
    var hasRunways: Bool { apiData.hasRunways }
    var hasAipData: Bool { apiData.hasAipData }
    var pointOfEntry: Bool { apiData.pointOfEntry ?? false }
    var longestRunwayLengthFt: Int { apiData.longestRunwayLengthFt ?? 0 }
    var procedureCount: Int { apiData.procedureCount }
    var runwayCount: Int { apiData.runwayCount }
    var country: String { apiData.isoCountry ?? "" }
    var city: String { apiData.municipality ?? "" }
    var name: String { apiData.name ?? apiData.ident }
}

// MARK: - Extension for Building Airports from API

extension Airport {
    /// Create an Airport from API summary data
    /// Note: This creates a minimal Airport - enhanced version requires RZFlight changes
    static func fromAPISummary(_ api: APIAirportSummary) -> Airport {
        APIAirportAdapter.toRZFlight(api)
    }
    
    /// Create an Airport from API detail data with runways/procedures/AIP
    static func fromAPIDetail(_ api: APIAirportDetail) -> Airport {
        APIAirportAdapter.toRZFlightWithExtendedData(api)
    }
}

