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
    /// Check if a NOTAM is at departure or destination
    static func isAtDepDest(_ notam: Notam, context: FlightContext) -> Bool {
        notam.location == context.departureICAO ||
        notam.location == context.destinationICAO
    }

    /// Check if a condition code indicates closure
    static func isClosureCondition(_ notam: Notam) -> Bool {
        if let conditionCode = notam.qCodeInfo?.conditionCode,
           conditionCode.hasSuffix("C") {
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
