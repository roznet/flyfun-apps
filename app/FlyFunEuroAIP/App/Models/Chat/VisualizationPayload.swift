//
//  VisualizationPayload.swift
//  FlyFunEuroAIP
//
//  Visualization data from the chatbot for map display.
//  Sent via ui_payload SSE event.
//

import Foundation
import CoreLocation

/// Visualization payload from chatbot API - instructs map what to display
/// Note: This is different from the internal VisualizationPayload in AirportDomain
struct ChatVisualizationPayload: Sendable {
    /// Kind of visualization (airport, route, list, etc.)
    let kind: Kind
    
    /// Visualization data (markers, routes, highlights)
    let visualization: VisualizationData?
    
    /// Filter configuration suggested by the chatbot
    let filters: ChatFilters?
    
    /// List of airport ICAOs to highlight
    let airports: [String]?
    
    /// Raw data from API
    let raw: [String: Any]
    
    enum Kind: String, Sendable {
        case airport
        case route
        case list
        case search
        case unknown
    }
    
    init(from dict: [String: Any]) {
        self.raw = dict
        
        // Parse kind
        if let kindStr = dict["kind"] as? String {
            self.kind = Kind(rawValue: kindStr) ?? .unknown
        } else {
            self.kind = .unknown
        }
        
        // Parse visualization
        if let vizDict = dict["visualization"] as? [String: Any] {
            self.visualization = VisualizationData(from: vizDict)
        } else if let mcpRaw = dict["mcp_raw"] as? [String: Any],
                  let vizDict = mcpRaw["visualization"] as? [String: Any] {
            self.visualization = VisualizationData(from: vizDict)
        } else {
            self.visualization = nil
        }
        
        // Parse filters
        if let filtersDict = dict["filters"] as? [String: Any] {
            self.filters = ChatFilters(from: filtersDict)
        } else {
            self.filters = nil
        }
        
        // Parse airports list
        self.airports = dict["airports"] as? [String]
    }
}

// MARK: - Visualization Data

/// Map visualization instructions
struct VisualizationData: Sendable {
    /// Markers to display on map
    let markers: [MapMarker]?
    
    /// Route to display
    let route: RouteData?
    
    /// Center point for the map
    let center: Coordinate?
    
    /// Zoom level suggestion
    let zoom: Double?
    
    init(from dict: [String: Any]) {
        // Parse markers
        if let markersArray = dict["markers"] as? [[String: Any]] {
            self.markers = markersArray.compactMap { MapMarker(from: $0) }
        } else {
            self.markers = nil
        }
        
        // Parse route
        if let routeDict = dict["route"] as? [String: Any] {
            self.route = RouteData(from: routeDict)
        } else {
            self.route = nil
        }
        
        // Parse center
        if let centerDict = dict["center"] as? [String: Any],
           let lat = centerDict["latitude"] as? Double ?? centerDict["lat"] as? Double,
           let lon = centerDict["longitude"] as? Double ?? centerDict["lon"] as? Double {
            self.center = Coordinate(latitude: lat, longitude: lon)
        } else {
            self.center = nil
        }
        
        self.zoom = dict["zoom"] as? Double
    }
}

// MARK: - Map Marker

struct MapMarker: Sendable, Identifiable {
    let id: String
    let icao: String
    let name: String?
    let coordinate: Coordinate
    let style: MarkerStyle?
    
    enum MarkerStyle: String, Sendable {
        case departure
        case destination
        case alternate
        case waypoint
        case result
        case highlight
        case `default`
    }
    
    init?(from dict: [String: Any]) {
        guard let icao = dict["icao"] as? String ?? dict["ident"] as? String else {
            return nil
        }
        
        // Get coordinates
        guard let lat = dict["latitude"] as? Double ?? dict["lat"] as? Double ?? dict["latitude_deg"] as? Double,
              let lon = dict["longitude"] as? Double ?? dict["lon"] as? Double ?? dict["longitude_deg"] as? Double else {
            return nil
        }
        
        self.id = icao
        self.icao = icao
        self.name = dict["name"] as? String
        self.coordinate = Coordinate(latitude: lat, longitude: lon)
        
        if let styleStr = dict["style"] as? String {
            self.style = MarkerStyle(rawValue: styleStr)
        } else {
            self.style = nil
        }
    }
}

// MARK: - Route Data

struct RouteData: Sendable {
    let departure: String?
    let destination: String?
    let departureCoord: Coordinate?
    let destinationCoord: Coordinate?
    let waypoints: [String]?
    let coordinates: [Coordinate]?
    
    init(from dict: [String: Any]) {
        // Parse departure - can be string or object with icao/lat/lon
        if let fromDict = dict["from"] as? [String: Any] {
            self.departure = fromDict["icao"] as? String
            if let lat = fromDict["lat"] as? Double ?? fromDict["latitude"] as? Double,
               let lon = fromDict["lon"] as? Double ?? fromDict["longitude"] as? Double {
                self.departureCoord = Coordinate(latitude: lat, longitude: lon)
            } else {
                self.departureCoord = nil
            }
        } else {
            self.departure = dict["departure"] as? String ?? dict["from"] as? String
            self.departureCoord = nil
        }
        
        // Parse destination - can be string or object with icao/lat/lon
        if let toDict = dict["to"] as? [String: Any] {
            self.destination = toDict["icao"] as? String
            if let lat = toDict["lat"] as? Double ?? toDict["latitude"] as? Double,
               let lon = toDict["lon"] as? Double ?? toDict["longitude"] as? Double {
                self.destinationCoord = Coordinate(latitude: lat, longitude: lon)
            } else {
                self.destinationCoord = nil
            }
        } else {
            self.destination = dict["destination"] as? String ?? dict["to"] as? String
            self.destinationCoord = nil
        }
        
        self.waypoints = dict["waypoints"] as? [String]
        
        if let coordsArray = dict["coordinates"] as? [[Double]] {
            self.coordinates = coordsArray.compactMap { arr in
                guard arr.count >= 2 else { return nil }
                return Coordinate(latitude: arr[0], longitude: arr[1])
            }
        } else if let coordsArray = dict["coordinates"] as? [[String: Any]] {
            self.coordinates = coordsArray.compactMap { dict in
                guard let lat = dict["latitude"] as? Double ?? dict["lat"] as? Double,
                      let lon = dict["longitude"] as? Double ?? dict["lon"] as? Double else {
                    return nil
                }
                return Coordinate(latitude: lat, longitude: lon)
            }
        } else {
            self.coordinates = nil
        }
    }
}

// MARK: - Coordinate

struct Coordinate: Sendable {
    let latitude: Double
    let longitude: Double
    
    var clLocationCoordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}

// MARK: - Chat Filters

/// Filters suggested by the chatbot
struct ChatFilters: Sendable {
    let country: String?
    let hasProcedures: Bool?
    let hasHardRunway: Bool?
    let pointOfEntry: Bool?
    let minRunwayLengthFt: Int?
    
    init(from dict: [String: Any]) {
        self.country = dict["country"] as? String ?? dict["iso_country"] as? String
        self.hasProcedures = dict["has_procedures"] as? Bool
        self.hasHardRunway = dict["has_hard_runway"] as? Bool
        self.pointOfEntry = dict["point_of_entry"] as? Bool
        self.minRunwayLengthFt = dict["min_runway_length_ft"] as? Int
    }
    
    /// Convert to FilterConfig
    func toFilterConfig() -> FilterConfig {
        var config = FilterConfig()
        config.country = country
        config.hasProcedures = hasProcedures
        config.hasHardRunway = hasHardRunway
        config.pointOfEntry = pointOfEntry
        config.minRunwayLengthFt = minRunwayLengthFt
        return config
    }
}

