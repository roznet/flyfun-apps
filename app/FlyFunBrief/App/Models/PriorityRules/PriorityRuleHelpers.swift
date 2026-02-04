//
//  PriorityRuleHelpers.swift
//  FlyFunBrief
//
//  Shared helper functions for priority rule evaluation.
//

import Foundation
import RZFlight

// MARK: - Priority Rule Helpers

/// Shared helpers used by both IFR and VFR priority rules.
enum PriorityRuleHelpers {

    // MARK: - Subject Sets

    /// Movement area subjects: MR = Runway, MT = Threshold, MX = Taxiway(s)
    static let movementAreaSubjects: Set<String> = ["MR", "MT", "MX"]

    /// ILS/MLS subjects
    static let ilsSubjects: Set<String> = [
        "IL", // Localizer
        "IG", // Glide path
        "IM", // Middle marker
        "IO", // Outer marker
        "II", // Inner marker
        "IS", // ILS Cat I
        "IT", // ILS Cat II
        "IU", // ILS Cat III
        "ID", // DME/ILS
        "IW", // MLS
        "IX", // Locator outer (ILS)
        "IY", // Locator middle (ILS)
    ]

    /// Core IFR procedure subjects (directly flown procedures)
    static let ifrCoreProcedureSubjects: Set<String> = [
        "PI", // Instrument approach procedure
        "PA", // STAR
        "PD", // SID
        "PU", // Missed approach
        "PH", // Holding procedure
    ]

    /// Supporting IFR procedure subjects (parameters/ancillary procedures)
    static let ifrSupportingProcedureSubjects: Set<String> = [
        "PM", // Aerodrome operating minima
        "PO", // OCA/OCH
        "PT", // Transition altitude/level
        "PX", // Minimum holding altitude
        "PF", // Flow control procedure
        "PR", // Radio failure procedure
        "PC", // Contingency procedures
        "PL", // Flight plan processing
        "PN", // Noise operating restriction
        "PZ", // ADIZ procedure
    ]

    /// VFR procedure subjects
    static let vfrProcedureSubjects: Set<String> = [
        "PB", // Standard VFR arrival
        "PE", // Standard VFR departure
        "PK", // VFR approach procedure
    ]

    // MARK: - Condition Checks

    /// Conditions indicating something is unavailable/closed/canceled
    /// (AS = unserviceable, AU = not available, LC = closed,
    ///  LI = closed to IFR, LV = closed to VFR, CN = canceled)
    static let unavailableConditions: Set<String> = ["AS", "AU", "LC", "LI", "LV", "CN"]

    /// Check if a NOTAM has an unavailable/closed/canceled condition
    static func isUnavailableCondition(_ notam: Notam) -> Bool {
        if let conditionCode = notam.qCodeInfo?.conditionCode,
           unavailableConditions.contains(conditionCode) {
            return true
        }
        if notam.customTags.contains("closed") {
            return true
        }
        return false
    }

    // MARK: - Location & Altitude Checks

    /// Check if a NOTAM is at departure or destination
    static func isAtDepDest(_ notam: Notam, context: FlightContext) -> Bool {
        notam.location == context.departureICAO ||
        notam.location == context.destinationICAO
    }

    /// Check if a condition code indicates a limitation (L* conditions:
    /// closed, unsafe, restricted, reduced length, etc.)
    static func isLimitationCondition(_ notam: Notam) -> Bool {
        if let conditionCode = notam.qCodeInfo?.conditionCode,
           conditionCode.hasPrefix("L") {
            return true
        }
        if notam.customTags.contains("closed") {
            return true
        }
        return false
    }

    /// Check if NOTAM altitude overlaps cruise altitude
    static func isAltitudeRelevant(_ notam: Notam, context: FlightContext) -> Bool {
        guard let cruiseRange = context.cruiseAltitudeRange else { return false }
        let notamLower = notam.lowerLimit ?? 0
        let notamUpper = notam.upperLimit ?? 99999
        if notamLower == 0 && notamUpper >= 99900 { return false }
        return cruiseRange.lowerBound <= notamUpper && cruiseRange.upperBound >= notamLower
    }
}
