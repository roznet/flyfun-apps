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
/// **P1**: Runway/taxiway/threshold conditions at dep/dest,
///         VFR procedure unavailable at dep/dest, airspace restrictions along route
/// **P2**: VFR procedure changed at dep/dest, rwy/twy limitations near route,
///         lighting at dep/dest, navigation issues near route, conditions near route
/// **P3**: Default (unmatched)
enum VFRPriorityRules {
    static let all: [any ProfilePriorityRule] = [
        // P1 rules
        VFRMovementAreaAtDepDest(),
        VFRProcedureUnavailableAtDepDest(),
        VFRAirspaceRestrictionsAlongRoute(),
        // P2 rules
        VFRProcedureChangedAtDepDest(),
        VFRMovementAreaLimitationsNearRoute(),
        VFRLightingAtDepDest(),
        VFRNavigationNearRoute(),
        VFRConditionsNearRoute(),
    ]
}

// MARK: - P1 Rules

/// P1: Any runway/taxiway/threshold NOTAM at departure or destination
struct VFRMovementAreaAtDepDest: ProfilePriorityRule {
    let id = "vfr_p1_movement_area"
    let name = "Runway/taxiway/threshold conditions at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }
        guard let subject = notam.qCodeSubject else { return nil }
        guard PriorityRuleHelpers.movementAreaSubjects.contains(subject) else { return nil }

        return 1
    }
}

/// P1: VFR procedure unavailable/closed/canceled at dep/dest
struct VFRProcedureUnavailableAtDepDest: ProfilePriorityRule {
    let id = "vfr_p1_procedure_unavailable"
    let name = "VFR procedure unavailable at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }
        guard let subject = notam.qCodeSubject else { return nil }
        guard PriorityRuleHelpers.vfrProcedureSubjects.contains(subject) else { return nil }
        guard PriorityRuleHelpers.isUnavailableCondition(notam) else { return nil }

        return 1
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

/// P2: VFR procedure changed/modified at dep/dest, or noise restriction
struct VFRProcedureChangedAtDepDest: ProfilePriorityRule {
    let id = "vfr_p2_procedure_changed"
    let name = "VFR procedure changed at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }
        guard let subject = notam.qCodeSubject else { return nil }

        // VFR procedure subjects with non-unavailable conditions (already P1 if unavailable)
        if PriorityRuleHelpers.vfrProcedureSubjects.contains(subject) {
            return 2
        }

        // Noise restriction at dep/dest
        if subject == "PN" {
            return 2
        }

        return nil
    }
}

/// P2: Runway/taxiway/threshold limitations at airports near route
struct VFRMovementAreaLimitationsNearRoute: ProfilePriorityRule {
    let id = "vfr_p2_movement_area_near_route"
    let name = "Runway/taxiway limitations near route"

    private let corridorWidthNm: Double = 50.0

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        // Skip dep/dest — already handled at P1
        guard !PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }
        guard let subject = notam.qCodeSubject else { return nil }
        guard PriorityRuleHelpers.movementAreaSubjects.contains(subject) else { return nil }
        guard let distance = distanceNm, distance <= corridorWidthNm else { return nil }
        guard PriorityRuleHelpers.isLimitationCondition(notam) else { return nil }

        return 2
    }
}

/// P2: Lighting at departure or destination
struct VFRLightingAtDepDest: ProfilePriorityRule {
    let id = "vfr_p2_lighting"
    let name = "Lighting at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }

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
