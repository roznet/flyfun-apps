//
//  MapTypes.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import MapKit
import CoreLocation
import RZFlight

// MARK: - Bounding Box

/// Geographic bounding box for region-based queries
struct BoundingBox: Sendable, Equatable {
    /// Southwest corner (minimum latitude and longitude)
    let minCoord: CLLocationCoordinate2D
    /// Northeast corner (maximum latitude and longitude)
    let maxCoord: CLLocationCoordinate2D
    
    // MARK: - Convenience Accessors
    
    var minLatitude: Double { minCoord.latitude }
    var maxLatitude: Double { maxCoord.latitude }
    var minLongitude: Double { minCoord.longitude }
    var maxLongitude: Double { maxCoord.longitude }
    
    // MARK: - Initializers
    
    init(minCoord: CLLocationCoordinate2D, maxCoord: CLLocationCoordinate2D) {
        self.minCoord = minCoord
        self.maxCoord = maxCoord
    }
    
    init(minLatitude: Double, maxLatitude: Double, minLongitude: Double, maxLongitude: Double) {
        self.minCoord = CLLocationCoordinate2D(latitude: minLatitude, longitude: minLongitude)
        self.maxCoord = CLLocationCoordinate2D(latitude: maxLatitude, longitude: maxLongitude)
    }
    
    // MARK: - Queries
    
    /// Check if a coordinate is within this bounding box
    func contains(_ coordinate: CLLocationCoordinate2D) -> Bool {
        coordinate.latitude >= minLatitude &&
        coordinate.latitude <= maxLatitude &&
        coordinate.longitude >= minLongitude &&
        coordinate.longitude <= maxLongitude
    }
    
    /// Check if an airport is within this bounding box
    func contains(_ airport: RZFlight.Airport) -> Bool {
        contains(airport.coord)
    }
}

// MARK: - MKCoordinateRegion Extensions

extension MKCoordinateRegion {
    /// Convert region to bounding box
    var boundingBox: BoundingBox {
        BoundingBox(
            minCoord: CLLocationCoordinate2D(
                latitude: center.latitude - span.latitudeDelta / 2,
                longitude: center.longitude - span.longitudeDelta / 2
            ),
            maxCoord: CLLocationCoordinate2D(
                latitude: center.latitude + span.latitudeDelta / 2,
                longitude: center.longitude + span.longitudeDelta / 2
            )
        )
    }
    
    /// Expand region by a factor (for prefetching beyond visible area)
    func paddedBy(factor: Double) -> MKCoordinateRegion {
        MKCoordinateRegion(
            center: center,
            span: MKCoordinateSpan(
                latitudeDelta: span.latitudeDelta * factor,
                longitudeDelta: span.longitudeDelta * factor
            )
        )
    }
    
    /// Default Europe region
    static let europe = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 50.0, longitude: 10.0),
        span: MKCoordinateSpan(latitudeDelta: 30, longitudeDelta: 40)
    )
}

// MARK: - Route Result

/// Route search result wrapper
struct RouteResult: Sendable {
    let airports: [RZFlight.Airport]
    let departure: String
    let destination: String
}

// MARK: - Map Highlight

/// Highlight overlay on the map (e.g., from chat visualization)
struct MapHighlight: Identifiable, Sendable, Equatable {
    let id: String
    let coordinate: CLLocationCoordinate2D
    let color: HighlightColor
    let radius: Double  // meters
    let popup: String?
    
    enum HighlightColor: String, Sendable, Equatable {
        case blue, red, green, orange, purple
    }
    
    static func == (lhs: MapHighlight, rhs: MapHighlight) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - Route Visualization

/// Route polyline for map display
struct RouteVisualization: Sendable, Equatable {
    let coordinates: [CLLocationCoordinate2D]
    let departure: String
    let destination: String
    
    static func == (lhs: RouteVisualization, rhs: RouteVisualization) -> Bool {
        lhs.departure == rhs.departure && lhs.destination == rhs.destination
    }
}

// MARK: - Legend Mode

/// Color coding mode for airport markers
enum LegendMode: String, CaseIterable, Identifiable, Sendable, Codable {
    case airportType = "Airport Type"
    case runwayLength = "Runway Length"
    case procedures = "IFR Procedures"
    case country = "Country"
    case notification = "Notification"

    var id: String { rawValue }
}

// MARK: - Connectivity Mode

/// Network connectivity state
enum ConnectivityMode: String, Equatable, Sendable {
    case offline        // No network, local DB only
    case online         // Network available, prefer API
    case hybrid         // Online with local cache fallback
}

// MARK: - CLLocationCoordinate2D Extensions

extension CLLocationCoordinate2D: @retroactive Equatable {
    public static func == (lhs: CLLocationCoordinate2D, rhs: CLLocationCoordinate2D) -> Bool {
        lhs.latitude == rhs.latitude && lhs.longitude == rhs.longitude
    }
}

extension CLLocationCoordinate2D {
    /// Haversine distance to another coordinate in meters
    func distance(to other: CLLocationCoordinate2D) -> Double {
        let location1 = CLLocation(latitude: latitude, longitude: longitude)
        let location2 = CLLocation(latitude: other.latitude, longitude: other.longitude)
        return location1.distance(from: location2)
    }
}

