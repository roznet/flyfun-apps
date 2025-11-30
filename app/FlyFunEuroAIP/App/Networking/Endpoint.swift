//
//  Endpoint.swift
//  FlyFunEuroAIP
//
//  Created for Phase 4: Online Integration
//

import Foundation

/// API endpoint definitions
/// Mirrors the Python FastAPI routes in web/server/api/
struct Endpoint {
    let path: String
    let queryItems: [URLQueryItem]?
    let headers: [String: String]
    let timeout: TimeInterval
    
    init(
        path: String,
        queryItems: [URLQueryItem]? = nil,
        headers: [String: String] = [:],
        timeout: TimeInterval = 30
    ) {
        self.path = path
        self.queryItems = queryItems
        self.headers = headers
        self.timeout = timeout
    }
}

// MARK: - Airport Endpoints

extension Endpoint {
    
    /// GET /api/airports - List airports with filters
    static func airports(
        filters: FilterConfig,
        limit: Int = 1000,
        offset: Int = 0,
        includeGA: Bool = false
    ) -> Endpoint {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "include_ga", value: String(includeGA))
        ]
        
        // Add filter parameters
        if let country = filters.country {
            queryItems.append(URLQueryItem(name: "country", value: country))
        }
        if filters.hasProcedures == true {
            queryItems.append(URLQueryItem(name: "has_procedures", value: "true"))
        }
        if filters.pointOfEntry == true {
            queryItems.append(URLQueryItem(name: "point_of_entry", value: "true"))
        }
        if filters.hasHardRunway == true {
            queryItems.append(URLQueryItem(name: "has_hard_runway", value: "true"))
        }
        if filters.hasLightedRunway == true {
            queryItems.append(URLQueryItem(name: "has_lighted_runway", value: "true"))
        }
        if let minLength = filters.minRunwayLengthFt {
            queryItems.append(URLQueryItem(name: "min_runway_length", value: String(minLength)))
        }
        if let maxLength = filters.maxRunwayLengthFt {
            queryItems.append(URLQueryItem(name: "max_runway_length", value: String(maxLength)))
        }
        if let aipField = filters.aipField {
            queryItems.append(URLQueryItem(name: "aip_field", value: aipField))
        }
        if filters.hasPrecisionApproach == true {
            queryItems.append(URLQueryItem(name: "has_precision_approach", value: "true"))
        }
        
        return Endpoint(path: "/api/airports", queryItems: queryItems)
    }
    
    /// GET /api/airports/{icao} - Get airport detail
    static func airportDetail(icao: String) -> Endpoint {
        Endpoint(path: "/api/airports/\(icao)")
    }
    
    /// GET /api/airports/search/{query} - Search airports
    static func searchAirports(query: String, limit: Int = 50) -> Endpoint {
        Endpoint(
            path: "/api/airports/search/\(query)",
            queryItems: [URLQueryItem(name: "limit", value: String(limit))]
        )
    }
    
    /// GET /api/airports/route-search - Find airports near a route
    static func routeSearch(
        from: String,
        to: String,
        distanceNm: Int = 30,
        filters: FilterConfig
    ) -> Endpoint {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "from_icao", value: from),
            URLQueryItem(name: "to_icao", value: to),
            URLQueryItem(name: "distance_nm", value: String(distanceNm))
        ]
        
        // Add filters
        if filters.hasProcedures == true {
            queryItems.append(URLQueryItem(name: "has_procedures", value: "true"))
        }
        if filters.pointOfEntry == true {
            queryItems.append(URLQueryItem(name: "point_of_entry", value: "true"))
        }
        if filters.hasHardRunway == true {
            queryItems.append(URLQueryItem(name: "has_hard_runway", value: "true"))
        }
        
        return Endpoint(path: "/api/airports/route-search", queryItems: queryItems)
    }
    
    /// GET /api/airports/locate - Find airports near a location
    static func locateAirports(
        latitude: Double,
        longitude: Double,
        radiusNm: Int = 50,
        filters: FilterConfig
    ) -> Endpoint {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "latitude", value: String(latitude)),
            URLQueryItem(name: "longitude", value: String(longitude)),
            URLQueryItem(name: "radius_nm", value: String(radiusNm))
        ]
        
        // Add filters
        if filters.hasProcedures == true {
            queryItems.append(URLQueryItem(name: "has_procedures", value: "true"))
        }
        if filters.pointOfEntry == true {
            queryItems.append(URLQueryItem(name: "point_of_entry", value: "true"))
        }
        
        return Endpoint(path: "/api/airports/locate", queryItems: queryItems)
    }
    
    /// GET /api/airports/{icao}/aip-entries - Get AIP entries for airport
    static func aipEntries(icao: String, section: String? = nil) -> Endpoint {
        var queryItems: [URLQueryItem] = []
        if let section = section {
            queryItems.append(URLQueryItem(name: "section", value: section))
        }
        return Endpoint(
            path: "/api/airports/\(icao)/aip-entries",
            queryItems: queryItems.isEmpty ? nil : queryItems
        )
    }
    
    /// GET /api/airports/{icao}/procedures - Get procedures for airport
    static func procedures(icao: String) -> Endpoint {
        Endpoint(path: "/api/airports/\(icao)/procedures")
    }
    
    /// GET /api/airports/{icao}/runways - Get runways for airport
    static func runways(icao: String) -> Endpoint {
        Endpoint(path: "/api/airports/\(icao)/runways")
    }
}

// MARK: - Filter Metadata Endpoints

extension Endpoint {
    
    /// GET /api/filters/countries - Get available countries
    static var countries: Endpoint {
        Endpoint(path: "/api/filters/countries")
    }
    
    /// GET /api/filters/all - Get all filter metadata
    static var filterMetadata: Endpoint {
        Endpoint(path: "/api/filters/all")
    }
    
    /// GET /api/filters/aip-fields - Get available AIP fields
    static var aipFields: Endpoint {
        Endpoint(path: "/api/filters/aip-fields")
    }
}

// MARK: - Rules Endpoints

extension Endpoint {
    
    /// GET /api/rules/{country_code} - Get rules for a country
    static func countryRules(countryCode: String) -> Endpoint {
        Endpoint(path: "/api/rules/\(countryCode)")
    }
}

// MARK: - Chat Endpoints

extension Endpoint {
    
    /// POST /api/aviation-agent/chat/stream - Stream chat response
    static var chatStream: Endpoint {
        Endpoint(
            path: "/api/aviation-agent/chat/stream",
            timeout: 120 // Longer timeout for streaming
        )
    }
    
    /// POST /api/aviation-agent/chat - Non-streaming chat
    static var chat: Endpoint {
        Endpoint(path: "/api/aviation-agent/chat")
    }
}

// MARK: - Statistics Endpoints

extension Endpoint {
    
    /// GET /api/statistics/overview - Get overview statistics
    static var statisticsOverview: Endpoint {
        Endpoint(path: "/api/statistics/overview")
    }
}

// MARK: - Health

extension Endpoint {
    
    /// GET /health - Health check
    static var health: Endpoint {
        Endpoint(path: "/health", timeout: 5)
    }
}

