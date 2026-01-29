//
//  DistanceBasedResurfaceRule.swift
//  FlyFunBrief
//
//  Resurface rule that treats globally-read NOTAMs as unread
//  when viewing on a different route and within proximity threshold.
//

import Foundation
import CoreLocation
import RZFlight

/// Resurfaces NOTAMs that are within X nm of the current route
/// when the route is different from when they were last read.
///
/// This ensures users see relevant NOTAMs when flying a new route,
/// even if they've read them before on a different route.
///
/// Note: This rule only applies to enroute (E) and warning (W) NOTAMs.
/// Aerodrome (A) NOTAMs are excluded because airports are always at fixed
/// locations and origin/destination airports are always close to the route.
struct DistanceBasedResurfaceRule: NotamResurfaceRule {
    let id = "distance_based"
    let name = "Distance-based resurface"

    func shouldResurface(
        globalRead: CDGlobalNotamRead,
        notam: Notam,
        context: FlightContext,
        settings: ResurfaceSettings
    ) -> Bool? {
        guard settings.distanceResurfaceEnabled else {
            return nil  // Defer to next rule
        }

        // Skip aerodrome NOTAMs - they're at fixed locations and origin/destination
        // airports are always close to the route, so distance-based resurface
        // doesn't make sense for them
        if notam.scope == "A" {
            return nil  // Defer to next rule (time-based will still apply)
        }

        // Only apply if we're on a different route
        let currentRouteHash = RouteHasher.hash(from: context)
        guard RouteHasher.areDifferentRoutes(globalRead.lastRouteHash, currentRouteHash) else {
            // Same route - no need to resurface based on distance
            return nil
        }

        // Check if NOTAM is within distance threshold of current route
        guard context.hasValidRoute,
              let notamCoordinate = notam.coordinate else {
            // Can't evaluate distance - defer to next rule
            return nil
        }

        let distanceNm = RouteGeometry.minimumDistanceToRoute(
            from: notamCoordinate,
            routePoints: context.routeCoordinates
        )

        // Resurface if within threshold
        return distanceNm <= settings.distanceNm
    }
}
