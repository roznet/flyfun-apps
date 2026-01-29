//
//  FlightContext.swift
//  FlyFunBrief
//
//  Flight and route context for NOTAM priority evaluation.
//

import Foundation
import CoreLocation
import RZFlight

/// Context about the current flight used for NOTAM priority evaluation.
///
/// This captures all flight-related information needed to evaluate NOTAM relevance
/// and priority without requiring access to Core Data or AppState.
struct FlightContext {
    // MARK: - Route Geometry

    /// Route coordinates from origin through waypoints to destination.
    /// Built from CDFlight using KnownAirports coordinate lookup.
    let routeCoordinates: [CLLocationCoordinate2D]

    // MARK: - Airports

    /// Departure airport ICAO code
    let departureICAO: String?

    /// Destination airport ICAO code
    let destinationICAO: String?

    /// Alternate airport ICAO codes
    let alternateICAOs: [String]

    // MARK: - Altitude

    /// Cruise altitude in feet (from CDFlight)
    let cruiseAltitude: Int?

    // MARK: - Time

    /// Planned departure time
    let departureTime: Date?

    /// Estimated arrival time
    let arrivalTime: Date?

    // MARK: - Computed Properties

    /// Whether we have enough route info to calculate distances
    var hasValidRoute: Bool {
        routeCoordinates.count >= 2
    }

    /// Flight window start (departure - 2 hours buffer)
    var flightWindowStart: Date? {
        departureTime?.addingTimeInterval(-2 * 60 * 60)
    }

    /// Flight window end (arrival + 2 hours buffer, or departure + 2 hours if no arrival)
    var flightWindowEnd: Date? {
        guard let departure = departureTime else { return nil }
        let end = arrivalTime ?? departure
        return end.addingTimeInterval(2 * 60 * 60)
    }

    /// Cruise altitude range for relevance check (±2000 ft)
    var cruiseAltitudeRange: ClosedRange<Int>? {
        guard let cruise = cruiseAltitude, cruise > 0 else { return nil }
        return (cruise - 2000)...(cruise + 2000)
    }

    // MARK: - Initialization

    init(
        routeCoordinates: [CLLocationCoordinate2D] = [],
        departureICAO: String? = nil,
        destinationICAO: String? = nil,
        alternateICAOs: [String] = [],
        cruiseAltitude: Int? = nil,
        departureTime: Date? = nil,
        arrivalTime: Date? = nil
    ) {
        self.routeCoordinates = routeCoordinates
        self.departureICAO = departureICAO
        self.destinationICAO = destinationICAO
        self.alternateICAOs = alternateICAOs
        self.cruiseAltitude = cruiseAltitude
        self.departureTime = departureTime
        self.arrivalTime = arrivalTime
    }

    /// Empty context when no flight is selected
    static let empty = FlightContext()

    /// Route string for display (e.g., "LFPG EGLL")
    var routeDisplayString: String {
        var parts: [String] = []
        if let dep = departureICAO { parts.append(dep) }
        if let dest = destinationICAO { parts.append(dest) }
        parts.append(contentsOf: alternateICAOs)
        return parts.joined(separator: " ")
    }
}

// MARK: - NOTAM Route Classification

extension FlightContext {

    /// Classify a NOTAM's position relative to this flight route.
    ///
    /// Classification order:
    /// 1. Departure - location matches departure ICAO
    /// 2. Destination - location matches destination ICAO
    /// 3. Alternates - location matches any alternate
    /// 4. En Route - has coordinates, within threshold of route
    /// 5. Distant - has coordinates, beyond threshold from route
    /// 6. No Coordinate - no geographic data
    func classifyNotam(_ notam: Notam, distantThresholdNm: Double = 50.0) -> NotamRouteClassification {
        let locationUpper = notam.location.uppercased()

        // Check departure
        if let dep = departureICAO?.uppercased(), locationUpper == dep {
            return NotamRouteClassification(
                segment: .departure,
                perpendicularDistanceNm: 0,
                alongRouteDistanceNm: 0
            )
        }

        // Check destination
        if let dest = destinationICAO?.uppercased(), locationUpper == dest {
            return NotamRouteClassification(
                segment: .destination,
                perpendicularDistanceNm: 0,
                alongRouteDistanceNm: totalRouteLengthNm
            )
        }

        // Check alternates
        if alternateICAOs.contains(where: { $0.uppercased() == locationUpper }) {
            return NotamRouteClassification(
                segment: .alternates,
                perpendicularDistanceNm: nil,
                alongRouteDistanceNm: nil
            )
        }

        // Check coordinate-based classification
        guard let coord = notam.coordinate else {
            return NotamRouteClassification(
                segment: .noCoordinate,
                perpendicularDistanceNm: nil,
                alongRouteDistanceNm: nil
            )
        }

        // Need valid route for spatial classification
        guard hasValidRoute else {
            return NotamRouteClassification(
                segment: .noCoordinate,
                perpendicularDistanceNm: nil,
                alongRouteDistanceNm: nil
            )
        }

        // Project onto route
        let (perpDistance, alongDistance) = projectPoint(coord)

        // Classify based on perpendicular distance
        if perpDistance <= distantThresholdNm {
            return NotamRouteClassification(
                segment: .enRoute,
                perpendicularDistanceNm: perpDistance,
                alongRouteDistanceNm: alongDistance
            )
        } else {
            return NotamRouteClassification(
                segment: .distant,
                perpendicularDistanceNm: perpDistance,
                alongRouteDistanceNm: alongDistance
            )
        }
    }

    /// Group NOTAMs by route segment using this flight context.
    func groupNotamsByRouteSegment(
        _ notams: [Notam],
        distantThresholdNm: Double = 50.0
    ) -> [NotamRouteClassification.RouteSegment: [(notam: Notam, classification: NotamRouteClassification)]] {
        var result: [NotamRouteClassification.RouteSegment: [(Notam, NotamRouteClassification)]] = [:]

        // Initialize all segments
        for segment in NotamRouteClassification.RouteSegment.allCases {
            result[segment] = []
        }

        // Classify each NOTAM
        for notam in notams {
            let classification = classifyNotam(notam, distantThresholdNm: distantThresholdNm)
            result[classification.segment, default: []].append((notam, classification))
        }

        // Sort en-route by along-route distance
        result[.enRoute] = result[.enRoute]?.sorted { lhs, rhs in
            let lhsDist = lhs.1.alongRouteDistanceNm ?? 0
            let rhsDist = rhs.1.alongRouteDistanceNm ?? 0
            return lhsDist < rhsDist
        }

        // Sort distant by perpendicular distance (closest first)
        result[.distant] = result[.distant]?.sorted { lhs, rhs in
            let lhsDist = lhs.1.perpendicularDistanceNm ?? Double.infinity
            let rhsDist = rhs.1.perpendicularDistanceNm ?? Double.infinity
            return lhsDist < rhsDist
        }

        return result
    }

    // MARK: - Route Geometry Helpers

    /// Total route length in nautical miles
    var totalRouteLengthNm: Double {
        guard routeCoordinates.count >= 2 else { return 0 }
        var total = 0.0
        for i in 0..<(routeCoordinates.count - 1) {
            total += directDistanceNm(from: routeCoordinates[i], to: routeCoordinates[i + 1])
        }
        return total
    }

    /// Project a point onto the route, returning perpendicular and along-route distances.
    private func projectPoint(_ coordinate: CLLocationCoordinate2D) -> (perpendicularNm: Double, alongRouteNm: Double) {
        guard routeCoordinates.count >= 2 else { return (.infinity, 0) }

        var bestPerpDistance = Double.infinity
        var bestAlongDistance = 0.0
        var cumulativeDistance = 0.0

        for i in 0..<(routeCoordinates.count - 1) {
            let segmentStart = routeCoordinates[i]
            let segmentEnd = routeCoordinates[i + 1]
            let segmentLength = directDistanceNm(from: segmentStart, to: segmentEnd)

            let (perpDistance, ratio) = perpendicularDistanceAndRatio(
                from: coordinate,
                toSegmentStart: segmentStart,
                segmentEnd: segmentEnd
            )

            if perpDistance < bestPerpDistance {
                bestPerpDistance = perpDistance
                bestAlongDistance = cumulativeDistance + (ratio * segmentLength)
            }

            cumulativeDistance += segmentLength
        }

        return (bestPerpDistance, bestAlongDistance)
    }

    /// Calculate direct distance between two coordinates in nautical miles.
    private func directDistanceNm(from p1: CLLocationCoordinate2D, to p2: CLLocationCoordinate2D) -> Double {
        let loc1 = CLLocation(latitude: p1.latitude, longitude: p1.longitude)
        let loc2 = CLLocation(latitude: p2.latitude, longitude: p2.longitude)
        return loc1.distance(from: loc2) / 1852.0
    }

    /// Calculate perpendicular distance and projection ratio from a point to a segment.
    private func perpendicularDistanceAndRatio(
        from point: CLLocationCoordinate2D,
        toSegmentStart start: CLLocationCoordinate2D,
        segmentEnd end: CLLocationCoordinate2D
    ) -> (distance: Double, ratio: Double) {
        let A = point.latitude - start.latitude
        let B = point.longitude - start.longitude
        let C = end.latitude - start.latitude
        let D = end.longitude - start.longitude

        let dot = A * C + B * D
        let lenSq = C * C + D * D
        let param = lenSq > 0 ? dot / lenSq : -1

        var closestLat: Double
        var closestLon: Double
        var clampedParam: Double

        if param < 0 {
            closestLat = start.latitude
            closestLon = start.longitude
            clampedParam = 0
        } else if param > 1 {
            closestLat = end.latitude
            closestLon = end.longitude
            clampedParam = 1
        } else {
            closestLat = start.latitude + param * C
            closestLon = start.longitude + param * D
            clampedParam = param
        }

        let distanceNm = directDistanceNm(
            from: point,
            to: CLLocationCoordinate2D(latitude: closestLat, longitude: closestLon)
        )

        return (distanceNm, clampedParam)
    }

    /// Calculate minimum distance from a point to the route in nautical miles.
    func minimumDistanceToRoute(from point: CLLocationCoordinate2D) -> Double {
        guard hasValidRoute else { return .infinity }
        return projectPoint(point).perpendicularNm
    }

    /// Check if a coordinate is within the route corridor.
    func isWithinCorridor(_ coordinate: CLLocationCoordinate2D, corridorWidthNm: Double) -> Bool {
        minimumDistanceToRoute(from: coordinate) <= corridorWidthNm
    }

    /// Get departure coordinate (first point in route).
    var departureCoordinate: CLLocationCoordinate2D? {
        routeCoordinates.first
    }

    /// Get destination coordinate (last point in route).
    var destinationCoordinate: CLLocationCoordinate2D? {
        routeCoordinates.last
    }
}
