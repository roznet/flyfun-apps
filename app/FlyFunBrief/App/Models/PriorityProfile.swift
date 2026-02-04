//
//  PriorityProfile.swift
//  FlyFunBrief
//
//  Profile-driven NOTAM priority system with configurable rule sets.
//

import Foundation
import SwiftUI
import RZFlight

// MARK: - Priority Profile

/// A named set of priority rules that defines how NOTAMs are ranked.
///
/// Profiles contain N priority levels (1 = most critical) and a set of rules
/// that assign each NOTAM to a level. Unmatched NOTAMs receive the profile's
/// lowest priority (maxLevel).
///
/// Two built-in profiles are provided: IFR (5 levels) and VFR (3 levels).
struct PriorityProfile: Identifiable, Equatable {
    /// Unique identifier (e.g., "ifr", "vfr")
    let id: String

    /// Display name (e.g., "IFR", "VFR")
    let displayName: String

    /// Number of priority levels (e.g., 5 for IFR, 3 for VFR)
    let maxLevel: Int

    /// Ordered rules evaluated to determine priority
    let rules: [any ProfilePriorityRule]

    /// Human-readable description for each level (1-indexed)
    let levelDescriptions: [Int: String]

    /// Range of valid priority levels
    var levels: ClosedRange<Int> { 1...maxLevel }

    static func == (lhs: PriorityProfile, rhs: PriorityProfile) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - Priority Rule Protocol

/// Protocol for profile-specific priority rules.
///
/// Each rule evaluates a NOTAM and returns an integer level (1 = most critical)
/// or nil to defer to subsequent rules. First non-nil result wins.
protocol ProfilePriorityRule {
    /// Unique identifier for this rule
    var id: String { get }

    /// Human-readable name
    var name: String { get }

    /// Evaluate the rule for a NOTAM in the given flight context.
    /// - Returns: Priority level (1 = most critical) if rule applies, nil to defer
    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int?
}

// MARK: - Available Profiles

/// Registry of available priority profiles.
enum PriorityProfiles {
    /// All available profiles
    static let all: [PriorityProfile] = [ifr, vfr]

    /// IFR profile with 5 priority levels
    static let ifr = PriorityProfile(
        id: "ifr",
        displayName: "IFR",
        maxLevel: 5,
        rules: IFRPriorityRules.all,
        levelDescriptions: [
            1: "Runway/taxiway at dep/dest, ILS/procedure unavailable at dep/dest",
            2: "ILS/procedure changed at dep/dest, airspace restrictions, rwy/twy limits near route",
            3: "Nearby NOTAMs at relevant altitude, navaid issues along route",
            4: "Facilities/services/comms at dep/dest, conditions near route",
            5: "Other NOTAMs"
        ]
    )

    /// VFR profile with 3 priority levels
    static let vfr = PriorityProfile(
        id: "vfr",
        displayName: "VFR",
        maxLevel: 3,
        rules: VFRPriorityRules.all,
        levelDescriptions: [
            1: "Runway/taxiway at dep/dest, VFR procedure unavailable, airspace restrictions",
            2: "VFR procedure changed, rwy/twy limits near route, lighting, navigation",
            3: "Other NOTAMs"
        ]
    )

    /// Default profile
    static let `default` = ifr

    /// Look up profile by ID, falling back to default
    static func profile(for id: String) -> PriorityProfile {
        all.first { $0.id == id } ?? `default`
    }
}
