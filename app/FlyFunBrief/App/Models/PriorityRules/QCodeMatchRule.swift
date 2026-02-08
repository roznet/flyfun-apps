//
//  QCodeMatchRule.swift
//  FlyFunBrief
//
//  Generic priority rule decoded from JSON configs.
//  Replaces hardcoded IFR/VFR rule structs with a single Decodable type.
//

import Foundation
import RZFlight

// MARK: - QCodeMatchRule

/// A priority rule decoded from a JSON profile config.
///
/// Each rule is a conjunction of optional filters: all present filters must match
/// for the rule to fire. Absent filters are skipped ("don't care").
///
/// Mirrors the `q_code_match` rule type in `configs/priority_profiles/*.json`
/// and the evaluation logic in `tools/priority_evaluator.py`.
struct QCodeMatchRule: ProfilePriorityRule, Decodable {
    let id: String
    let name: String
    let level: Int

    /// Optional Q-code subject filter (e.g., ["MR", "MT", "MX"])
    let subjects: Set<String>?

    /// Optional condition filter (unavailable or limitation)
    let conditionFilter: ConditionFilter?

    /// Optional location filter (dep/dest or not dep/dest)
    let location: LocationFilter?

    /// Maximum distance from route in nautical miles
    let maxDistanceNm: Double?

    /// Altitude check mode
    let altitudeCheck: AltitudeCheck?

    /// Fallback distance when altitude check is required but no cruise altitude is set
    let noAltitudeFallbackDistanceNm: Double?

    // MARK: - Filter Enums

    enum ConditionFilter: String, Decodable {
        case unavailable
        case limitation
    }

    enum LocationFilter: String, Decodable {
        case depDest = "dep_dest"
        case notDepDest = "not_dep_dest"
    }

    enum AltitudeCheck: String, Decodable {
        case ifAvailable = "if_available"
        case required
    }

    // MARK: - CodingKeys

    private enum CodingKeys: String, CodingKey {
        case id, name, level, subjects
        case conditionFilter = "condition_filter"
        case location
        case maxDistanceNm = "max_distance_nm"
        case altitudeCheck = "altitude_check"
        case noAltitudeFallbackDistanceNm = "no_altitude_fallback_distance_nm"
    }

    // MARK: - Evaluation

    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int? {
        // All rules require a Q-code subject
        guard let subject = notam.qCodeSubject else { return nil }

        // Subject filter
        if let subjects, !subjects.contains(subject) {
            return nil
        }

        // Condition filter
        if let conditionFilter {
            switch conditionFilter {
            case .unavailable:
                guard Self.isUnavailableCondition(notam) else { return nil }
            case .limitation:
                guard Self.isLimitationCondition(notam) else { return nil }
            }
        }

        // Location filter
        if let location {
            let atDepDest = Self.isAtDepDest(notam, context: context)
            switch location {
            case .depDest:
                guard atDepDest else { return nil }
            case .notDepDest:
                guard !atDepDest else { return nil }
            }
        }

        // Distance filter
        if let maxDistanceNm {
            guard let distance = distanceNm, distance <= maxDistanceNm else { return nil }
        }

        // Altitude check
        if let altitudeCheck {
            guard Self.checkAltitude(
                altitudeCheck,
                notam: notam,
                distanceNm: distanceNm,
                context: context,
                fallbackDistanceNm: noAltitudeFallbackDistanceNm
            ) else { return nil }
        }

        return level
    }

    // MARK: - Helpers

    /// Check if NOTAM location matches departure or destination
    private static func isAtDepDest(_ notam: Notam, context: FlightContext) -> Bool {
        notam.location == context.departureICAO ||
        notam.location == context.destinationICAO
    }

    /// Conditions indicating unavailable/closed/canceled
    private static let unavailableConditions: Set<String> = ["AS", "AU", "LC", "LI", "LV", "CN"]

    /// Check if a NOTAM has an unavailable/closed/canceled condition
    private static func isUnavailableCondition(_ notam: Notam) -> Bool {
        if let conditionCode = notam.qCodeInfo?.conditionCode,
           unavailableConditions.contains(conditionCode) {
            return true
        }
        return notam.customTags.contains("closed")
    }

    /// Check if a NOTAM has a limitation condition (L* or closed tag)
    private static func isLimitationCondition(_ notam: Notam) -> Bool {
        if let conditionCode = notam.qCodeInfo?.conditionCode,
           conditionCode.hasPrefix("L") {
            return true
        }
        return notam.customTags.contains("closed")
    }

    /// Check if NOTAM altitude range overlaps cruise altitude +/- 2000ft
    private static func isAltitudeRelevant(_ notam: Notam, context: FlightContext) -> Bool {
        guard let cruiseRange = context.cruiseAltitudeRange else { return false }
        let notamLower = notam.lowerLimit ?? 0
        let notamUpper = notam.upperLimit ?? 99999
        // Skip surface-to-unlimited NOTAMs
        if notamLower == 0 && notamUpper >= 99900 { return false }
        return cruiseRange.lowerBound <= notamUpper && cruiseRange.upperBound >= notamLower
    }

    /// Handle altitude_check: "if_available" or "required"
    private static func checkAltitude(
        _ check: AltitudeCheck,
        notam: Notam,
        distanceNm: Double?,
        context: FlightContext,
        fallbackDistanceNm: Double?
    ) -> Bool {
        switch check {
        case .ifAvailable:
            // Pass if no cruise altitude is set
            if context.cruiseAltitudeRange == nil { return true }
            return isAltitudeRelevant(notam, context: context)

        case .required:
            if context.cruiseAltitudeRange != nil {
                return isAltitudeRelevant(notam, context: context)
            }
            // No cruise altitude: use fallback distance if configured
            if let fallback = fallbackDistanceNm, let distance = distanceNm {
                return distance <= fallback
            }
            return false
        }
    }
}
