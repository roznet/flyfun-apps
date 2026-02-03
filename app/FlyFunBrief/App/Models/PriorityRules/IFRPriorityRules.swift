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
/// **P1**: Runway/taxiway closure at dep/dest, ILS/approach unavailable at dep/dest
/// **P2**: SID/STAR/procedure changes at dep/dest, airspace restrictions within corridor
/// **P3**: Within 10nm + altitude relevant, navaid issues along route
/// **P4**: Facilities/services/comms at dep/dest, conditions near route
/// **P5**: Default (unmatched)
enum IFRPriorityRules {
    static let all: [any ProfilePriorityRule] = [
        // P1 rules
        IFRRunwayClosureAtDepDest(),
        IFRApproachUnavailableAtDepDest(),
        // P2 rules
        IFRProcedureChangesAtDepDest(),
        IFRAirspaceRestrictionsInCorridor(),
        // P3 rules
        IFRCloseAndAltitudeRelevant(),
        IFRNavaidIssuesAlongRoute(),
        // P4 rules
        IFRFacilitiesAtDepDest(),
        IFRConditionsNearRoute(),
    ]
}

// MARK: - P1 Rules

/// P1: Runway/taxiway closure at departure or destination
struct IFRRunwayClosureAtDepDest: ProfilePriorityRule {
    let id = "ifr_p1_runway_closure"
    let name = "Runway/taxiway closure at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }

        // Check for runway/taxiway subjects with closure condition
        guard let subject = notam.qCodeSubject else { return nil }

        // MR = Runway, MT = Taxiway
        guard subject == "MR" || subject == "MT" else { return nil }
        guard PriorityRuleHelpers.isClosureCondition(notam) else { return nil }

        return 1
    }
}

/// P1: ILS/approach system unavailable at departure or destination
struct IFRApproachUnavailableAtDepDest: ProfilePriorityRule {
    let id = "ifr_p1_approach_unavailable"
    let name = "ILS/approach unavailable at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }

        guard let subject = notam.qCodeSubject else { return nil }

        // ILS subjects: IL (localizer), IG (glidepath/glideslope), IM (middle marker),
        // IO (outer marker), II (inner marker), IS (ILS), ID (DME/ILS)
        // Approach procedure: PA (approach procedure)
        let approachSubjects: Set<String> = ["IL", "IG", "IM", "IO", "II", "IS", "ID", "PA"]
        guard approachSubjects.contains(subject) else { return nil }

        // Check for unavailable/unserviceable conditions
        if let condCode = notam.qCodeInfo?.conditionCode {
            // AS = unserviceable, AH = not available, LC = closed
            if condCode == "AS" || condCode == "AH" || condCode.hasSuffix("C") {
                return 1
            }
        }

        return nil
    }
}

// MARK: - P2 Rules

/// P2: SID/STAR/procedure changes at departure or destination
struct IFRProcedureChangesAtDepDest: ProfilePriorityRule {
    let id = "ifr_p2_procedure_changes"
    let name = "SID/STAR/procedure changes at dep/dest"

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        guard PriorityRuleHelpers.isAtDepDest(notam, context: context) else { return nil }

        guard let subject = notam.qCodeSubject else { return nil }

        // PD = SID, PA = Approach, PS = STAR, PI = Instrument procedure,
        // PF = Final approach, PH = Holding, PM = Missed approach
        let procedureSubjects: Set<String> = ["PD", "PA", "PS", "PI", "PF", "PH", "PM"]
        guard procedureSubjects.contains(subject) else { return nil }

        return 2
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
