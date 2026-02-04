//
//  IFRPriorityRules.swift
//  FlyFunBrief
//
//  IFR priority rules for 5-level priority profile.
//

import Foundation
import RZFlight

// MARK: - IFR Priority Rules

/// IFR priority rules collection.
///
/// **P1**: Runway/taxiway/threshold conditions at dep/dest,
///         ILS/procedure unavailable at dep/dest
/// **P2**: ILS/procedure changed at dep/dest, supporting procedures at dep/dest,
///         airspace restrictions within corridor, rwy/twy limitations near route
/// **P3**: Within 10nm + altitude relevant, navaid issues along route
/// **P4**: Facilities/services/comms at dep/dest, conditions near route
/// **P5**: Default (unmatched)
enum IFRPriorityRules {
    static let all: [any ProfilePriorityRule] = [
        // P1 rules
        IFRMovementAreaAtDepDest(),
        IFRProcedureUnavailableAtDepDest(),
        // P2 rules
        IFRProcedureChangedAtDepDest(),
        IFRAirspaceRestrictionsInCorridor(),
        IFRMovementAreaLimitationsNearRoute(),
        // P3 rules
        IFRCloseAndAltitudeRelevant(),
        IFRNavaidIssuesAlongRoute(),
        // P4 rules
        IFRFacilitiesAtDepDest(),
        IFRConditionsNearRoute(),
    ]
}

// MARK: - P1 Rules

/// P1: Any runway/taxiway/threshold NOTAM at departure or destination
struct IFRMovementAreaAtDepDest: ProfilePriorityRule {
    let id = "ifr_p1_movement_area"
    let name = "Runway/taxiway/threshold conditions at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }
        guard let subject = notam.qCodeSubject else { return nil }
        guard PriorityRuleHelpers.movementAreaSubjects.contains(subject) else { return nil }

        return 1
    }
}

/// P1: ILS/MLS or core procedure unavailable/closed/canceled at dep/dest
struct IFRProcedureUnavailableAtDepDest: ProfilePriorityRule {
    let id = "ifr_p1_procedure_unavailable"
    let name = "ILS/procedure unavailable at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }
        guard let subject = notam.qCodeSubject else { return nil }

        let p1Subjects = PriorityRuleHelpers.ilsSubjects
            .union(PriorityRuleHelpers.ifrCoreProcedureSubjects)
        guard p1Subjects.contains(subject) else { return nil }
        guard PriorityRuleHelpers.isUnavailableCondition(notam) else { return nil }

        return 1
    }
}

// MARK: - P2 Rules

/// P2: ILS/MLS or core procedure changed/modified at dep/dest,
///     or any supporting procedure at dep/dest
struct IFRProcedureChangedAtDepDest: ProfilePriorityRule {
    let id = "ifr_p2_procedure_changed"
    let name = "ILS/procedure changed at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }
        guard let subject = notam.qCodeSubject else { return nil }

        // Core ILS/procedure subjects with non-unavailable conditions (already P1 if unavailable)
        let coreSubjects = PriorityRuleHelpers.ilsSubjects
            .union(PriorityRuleHelpers.ifrCoreProcedureSubjects)
        if coreSubjects.contains(subject) {
            return 2
        }

        // Supporting procedure subjects with any condition
        if PriorityRuleHelpers.ifrSupportingProcedureSubjects.contains(subject) {
            return 2
        }

        return nil
    }
}

/// P2: Airspace restrictions within route corridor
struct IFRAirspaceRestrictionsInCorridor: ProfilePriorityRule {
    let id = "ifr_p2_airspace_restrictions"
    let name = "Airspace restrictions within corridor"

    /// Corridor width for airspace restriction checks
    private let corridorWidthNm: Double = 50.0

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard let subject = notam.qCodeSubject else { return nil }

        // R-type subjects: RA = restricted area, RR = restricted route,
        // RT = TEMPO restricted area, AR = NOTAM area
        let restrictionSubjects: Set<String> = ["RA", "RR", "RT", "AR"]
        guard restrictionSubjects.contains(subject) else { return nil }

        // Must be within corridor
        guard let distance = distanceNm, distance <= corridorWidthNm else { return nil }

        // Check altitude relevance if we have altitude info
        if PriorityRuleHelpers.isAltitudeRelevant(notam, context: context) {
            return 2
        }

        // If no cruise altitude set but within corridor, still P2
        if context.cruiseAltitudeRange == nil {
            return 2
        }

        return nil
    }
}

/// P2: Runway/taxiway/threshold limitations at airports near route
struct IFRMovementAreaLimitationsNearRoute: ProfilePriorityRule {
    let id = "ifr_p2_movement_area_near_route"
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

// MARK: - P3 Rules

/// P3: NOTAM within 10nm of route at relevant altitude
struct IFRCloseAndAltitudeRelevant: ProfilePriorityRule {
    let id = "ifr_p3_close_altitude"
    let name = "Close to route at flight altitude"

    private let distanceThresholdNm: Double = 10.0

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard let distance = distanceNm, distance <= distanceThresholdNm else { return nil }

        if PriorityRuleHelpers.isAltitudeRelevant(notam, context: context) {
            return 3
        }

        // No cruise altitude but very close
        if context.cruiseAltitudeRange == nil && distance <= 5.0 {
            return 3
        }

        return nil
    }
}

/// P3: Navaid issues along route
struct IFRNavaidIssuesAlongRoute: ProfilePriorityRule {
    let id = "ifr_p3_navaid_issues"
    let name = "Navaid issues along route"

    private let corridorWidthNm: Double = 25.0

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard let subject = notam.qCodeSubject else { return nil }

        // Navigation aids: NV = VOR, ND = DME, NB = NDB, NT = TACAN, NL = NDB/locator
        let navaidSubjects: Set<String> = ["NV", "ND", "NB", "NT", "NL"]
        guard navaidSubjects.contains(subject) else { return nil }

        // Must be within corridor of route
        guard let distance = distanceNm, distance <= corridorWidthNm else { return nil }

        return 3
    }
}

// MARK: - P4 Rules

/// P4: Facilities/services/comms at departure or destination
struct IFRFacilitiesAtDepDest: ProfilePriorityRule {
    let id = "ifr_p4_facilities"
    let name = "Facilities/services at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }

        guard let subject = notam.qCodeSubject else { return nil }

        // Facilities: FA = aerodrome, FF = firefighting, FS = fuel/services
        // Communications: CA = ATC, CO = comm freq, CS = service
        // Services: SA = ATC, SS = service, SE = radar
        // Lighting: LA = approach, LB = beacon, LC = circuit, LI = taxiway
        let facilitySubjects: Set<String> = [
            "FA", "FF", "FS",
            "CA", "CO", "CS",
            "SA", "SS", "SE",
            "LA", "LB", "LC", "LI"
        ]
        guard facilitySubjects.contains(subject) else { return nil }

        return 4
    }
}

/// P4: Various conditions near route (within 50nm)
struct IFRConditionsNearRoute: ProfilePriorityRule {
    let id = "ifr_p4_near_route"
    let name = "Conditions near route"

    private let corridorWidthNm: Double = 50.0

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard let distance = distanceNm, distance <= corridorWidthNm else { return nil }

        // Any NOTAM within corridor that hasn't been caught by higher rules
        // gets P4 if it has a Q-code (meaningful NOTAM)
        guard notam.qCodeSubject != nil else { return nil }

        // Check altitude relevance when available
        if context.cruiseAltitudeRange != nil {
            if PriorityRuleHelpers.isAltitudeRelevant(notam, context: context) {
                return 4
            }
            return nil
        }

        return 4
    }
}
