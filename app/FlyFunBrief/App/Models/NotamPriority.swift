//
//  NotamPriority.swift
//  FlyFunBrief
//
//  NOTAM priority level and profile-driven priority evaluation.
//

import Foundation
import SwiftUI
import RZFlight

// MARK: - Priority Level

/// Priority level for a NOTAM, determined by the active priority profile.
///
/// Priority is computed dynamically based on the NOTAM's relevance to the
/// current flight using profile-specific rules. Level 1 is most critical;
/// maxLevel is the lowest (default for unmatched NOTAMs).
///
/// This is independent of user-assigned status (read/important/ignored).
struct NotamPriority: Comparable, Hashable, Sendable {
    /// Priority level (1 = most critical)
    let level: Int

    /// Maximum level in the profile (e.g., 5 for IFR, 3 for VFR)
    let maxLevel: Int

    /// Whether this is the default (lowest) priority
    var isDefault: Bool { level == maxLevel }

    /// Whether this is the most critical level
    var isCritical: Bool { level == 1 }

    /// Display label (e.g., "P1", "P2")
    var label: String { "P\(level)" }

    /// SF Symbol name for this priority level
    var iconName: String? {
        if isCritical { return "exclamationmark.triangle.fill" }
        if isDefault { return nil }
        return "circle.fill"
    }

    /// Display color, interpolated from red (P1) through orange/yellow to gray (default)
    var color: Color {
        if isDefault { return .secondary }
        if isCritical { return .red }
        if maxLevel <= 2 { return .orange }

        // Interpolate: P2 = orange, middle = yellow, near-default = secondary
        let ratio = Double(level - 1) / Double(maxLevel - 1)
        if ratio < 0.4 { return .orange }
        if ratio < 0.7 { return .yellow }
        return .secondary
    }

    /// Higher priority (lower level number) sorts first
    static func < (lhs: NotamPriority, rhs: NotamPriority) -> Bool {
        // Lower level = higher priority, so invert comparison
        lhs.level > rhs.level
    }

    /// Create default (lowest) priority for a profile
    static func `default`(maxLevel: Int) -> NotamPriority {
        NotamPriority(level: maxLevel, maxLevel: maxLevel)
    }
}

// MARK: - Priority Evaluator

/// Evaluates NOTAM priority using a profile's rules.
///
/// Usage:
/// ```swift
/// let evaluator = NotamPriorityEvaluator(profile: PriorityProfiles.ifr)
/// let priority = evaluator.evaluate(notam: notam, distanceNm: 5.0, context: flightContext)
/// ```
final class NotamPriorityEvaluator {
    /// The profile being used for evaluation
    private let profile: PriorityProfile

    init(profile: PriorityProfile) {
        self.profile = profile
    }

    /// Evaluate priority for a NOTAM.
    /// Rules are evaluated in order; first non-nil result wins.
    /// Returns the profile's default (maxLevel) if no rule matches.
    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> NotamPriority {
        for rule in profile.rules {
            if let level = rule.evaluate(notam: notam, distanceNm: distanceNm, context: context) {
                return NotamPriority(level: level, maxLevel: profile.maxLevel)
            }
        }
        return .default(maxLevel: profile.maxLevel)
    }
}
