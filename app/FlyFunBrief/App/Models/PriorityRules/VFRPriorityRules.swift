//
//  VFRPriorityRules.swift
//  FlyFunBrief
//
//  VFR priority rules for 3-level priority profile.
//

import Foundation
import RZFlight

// MARK: - VFR Priority Rules

/// VFR priority rules collection.
///
/// **P1**: Runway closure at dep/dest, airspace restrictions along route
/// **P2**: Lighting at dep/dest, navigation issues near route, conditions near route
/// **P3**: Default (unmatched)
enum VFRPriorityRules {
    static let all: [any ProfilePriorityRule] = [
        // P1 rules
        VFRRunwayClosureAtDepDest(),
        VFRAirspaceRestrictionsAlongRoute(),
        // P2 rules
        VFRLightingAtDepDest(),
        VFRNavigationNearRoute(),
        VFRConditionsNearRoute(),
    ]
}

// MARK: - P1 Rules

/// P1: Runway closure at departure or destination
struct VFRRunwayClosureAtDepDest: ProfilePriorityRule {
    let id = "vfr_p1_runway_closure"
    let name = "Runway closure at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard notam.location == context.departureICAO ||
              notam.location == context.destinationICAO else { return nil }

        guard let subject = notam.qCodeSubject else { return nil }

        // MR = Runway, MT = Taxiway
        guard subject == "MR" || subject == "MT" else { return nil }

        // Check for closure
        if let conditionCode = notam.qCodeInfo?.conditionCode,
           conditionCode.hasSuffix("C") {
            return 1
        }
        if notam.customTags.contains("closed") {
            return 1
        }

        return nil
    }
}

/// P1: Airspace restrictions along route
struct VFRAirspaceRestrictionsAlongRoute: ProfilePriorityRule {
    let id = "vfr_p1_airspace_restrictions"
    let name = "Airspace restrictions along route"

    private let corridorWidthNm: Double = 25.0

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard let subject = notam.qCodeSubject else { return nil }

        // Airspace restrictions: RA, RR, RT, AR
        let restrictionSubjects: Set<String> = ["RA", "RR", "RT", "AR"]
        guard restrictionSubjects.contains(subject) else { return nil }

        // Must be within corridor
        guard let distance = distanceNm, distance <= corridorWidthNm else { return nil }

        return 1
    }
}

// MARK: - P2 Rules

/// P2: Lighting at departure or destination
struct VFRLightingAtDepDest: ProfilePriorityRule {
    let id = "vfr_p2_lighting"
    let name = "Lighting at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard notam.location == context.departureICAO ||
              notam.location == context.destinationICAO else { return nil }

        guard let subject = notam.qCodeSubject else { return nil }

        // Lighting subjects: LA = approach, LB = beacon, LC = circuit,
        // LE = edge, LF = flood, LI = taxiway, LK = cat II/III
        let lightingSubjects: Set<String> = ["LA", "LB", "LC", "LE", "LF", "LI", "LK"]
        guard lightingSubjects.contains(subject) else { return nil }

        return 2
    }
}

/// P2: Navigation issues near route
struct VFRNavigationNearRoute: ProfilePriorityRule {
    let id = "vfr_p2_navigation"
    let name = "Navigation issues near route"

    private let corridorWidthNm: Double = 25.0

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard let subject = notam.qCodeSubject else { return nil }

        // Navigation aids: NV = VOR, ND = DME, NB = NDB, GN = GNSS
        let navSubjects: Set<String> = ["NV", "ND", "NB", "GN"]
        guard navSubjects.contains(subject) else { return nil }

        guard let distance = distanceNm, distance <= corridorWidthNm else { return nil }

        return 2
    }
}

/// P2: Various conditions near route
struct VFRConditionsNearRoute: ProfilePriorityRule {
    let id = "vfr_p2_near_route"
    let name = "Conditions near route"

    private let corridorWidthNm: Double = 10.0

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard let distance = distanceNm, distance <= corridorWidthNm else { return nil }

        // Any NOTAM with a Q-code very close to route
        guard notam.qCodeSubject != nil else { return nil }

        return 2
    }
}
