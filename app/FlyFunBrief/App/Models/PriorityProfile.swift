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
/// Two built-in profiles are provided: IFR (5 levels) and VFR (3 levels),
/// loaded from JSON configs in `configs/priority_profiles/`.
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

// MARK: - JSON Loading

extension PriorityProfile {

    /// Decode a priority profile from JSON data.
    static func fromJSON(_ data: Data) throws -> PriorityProfile {
        let decoded = try JSONDecoder().decode(ProfileJSON.self, from: data)

        let levelDescriptions = Dictionary(
            uniqueKeysWithValues: decoded.levelDescriptions.map { (Int($0.key)!, $0.value) }
        )

        return PriorityProfile(
            id: decoded.id,
            displayName: decoded.displayName,
            maxLevel: decoded.maxLevel,
            rules: decoded.rules,
            levelDescriptions: levelDescriptions
        )
    }

    /// Load a bundled profile by name (e.g., "ifr", "vfr").
    /// Fatal error if the resource is missing — this is a build-time guarantee.
    static func bundled(name: String, in bundle: Bundle = .main) -> PriorityProfile {
        guard let url = bundle.url(forResource: name, withExtension: "json") else {
            fatalError("Missing bundled priority profile: \(name).json")
        }
        do {
            let data = try Data(contentsOf: url)
            return try fromJSON(data)
        } catch {
            fatalError("Failed to load priority profile \(name).json: \(error)")
        }
    }

    /// JSON structure matching `configs/priority_profiles/*.json`
    private struct ProfileJSON: Decodable {
        let id: String
        let displayName: String
        let maxLevel: Int
        let levelDescriptions: [String: String]
        let rules: [QCodeMatchRule]

        private enum CodingKeys: String, CodingKey {
            case id
            case displayName = "display_name"
            case maxLevel = "max_level"
            case levelDescriptions = "level_descriptions"
            case rules
        }
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

    /// IFR profile loaded from bundled JSON config
    static let ifr = PriorityProfile.bundled(name: "ifr")

    /// VFR profile loaded from bundled JSON config
    static let vfr = PriorityProfile.bundled(name: "vfr")

    /// Default profile
    static let `default` = ifr

    /// Look up profile by ID, falling back to default
    static func profile(for id: String) -> PriorityProfile {
        all.first { $0.id == id } ?? `default`
    }
}
