//
//  RouteHasher.swift
//  FlyFunBrief
//
//  Generates consistent route hashes for comparing flight routes.
//  Used by resurface rules to detect when a NOTAM is being viewed on a different route.
//

import Foundation
import RZFlight

/// Generates route hashes for flight route comparison
enum RouteHasher {
    /// Generate a route hash from flight context
    ///
    /// Format: "DEP-DEST[-ALT1][-ALT2]..." with ICAOs sorted for alternates
    static func hash(from context: FlightContext) -> String {
        var components: [String] = []

        if let dep = context.departureICAO {
            components.append(dep.uppercased())
        }
        if let dest = context.destinationICAO {
            components.append(dest.uppercased())
        }

        // Sort alternates for consistent hashing
        let sortedAlternates = context.alternateICAOs.map { $0.uppercased() }.sorted()
        components.append(contentsOf: sortedAlternates)

        return components.joined(separator: "-")
    }

    /// Generate a route hash from a CDFlight
    static func hash(from flight: CDFlight) -> String {
        var components: [String] = []

        if let origin = flight.origin {
            components.append(origin.uppercased())
        }
        if let destination = flight.destination {
            components.append(destination.uppercased())
        }

        return components.joined(separator: "-")
    }

    /// Generate a route hash from a Route
    static func hash(from route: Route) -> String {
        var components: [String] = []

        components.append(route.departure.uppercased())
        components.append(route.destination.uppercased())

        // Sort alternates for consistent hashing
        let sortedAlternates = route.alternates.map { $0.uppercased() }.sorted()
        components.append(contentsOf: sortedAlternates)

        return components.joined(separator: "-")
    }

    /// Check if two route hashes represent different routes
    ///
    /// Returns true if the routes are meaningfully different (different dep/dest).
    /// Minor differences like alternates may not count as "different" for
    /// resurface purposes.
    static func areDifferentRoutes(_ hash1: String?, _ hash2: String?) -> Bool {
        guard let h1 = hash1, let h2 = hash2 else {
            // If either hash is missing, consider them different
            return true
        }

        // Extract departure-destination (first two components)
        let components1 = h1.split(separator: "-")
        let components2 = h2.split(separator: "-")

        // Must have at least departure and destination
        guard components1.count >= 2, components2.count >= 2 else {
            return true
        }

        // Compare departure and destination only
        let depDest1 = "\(components1[0])-\(components1[1])"
        let depDest2 = "\(components2[0])-\(components2[1])"

        return depDest1 != depDest2
    }
}
