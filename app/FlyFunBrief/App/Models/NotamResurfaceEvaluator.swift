//
//  NotamResurfaceEvaluator.swift
//  FlyFunBrief
//
//  Evaluates resurface rules to determine if a globally-read NOTAM
//  should be treated as unread based on time and context changes.
//

import Foundation
import RZFlight

/// Evaluates NOTAM resurface rules using a chain of rules.
///
/// Usage:
/// ```swift
/// let evaluator = NotamResurfaceEvaluator.shared
/// let shouldResurface = evaluator.shouldResurface(
///     globalRead: globalReadRecord,
///     notam: notam,
///     context: flightContext,
///     settings: resurfaceSettings
/// )
/// ```
final class NotamResurfaceEvaluator {
    /// Shared instance with default rules
    static let shared = NotamResurfaceEvaluator()

    /// Ordered list of rules to evaluate
    private let rules: [NotamResurfaceRule]

    init(rules: [NotamResurfaceRule]? = nil) {
        self.rules = rules ?? Self.defaultRules
    }

    /// Evaluate whether a globally-read NOTAM should resurface.
    ///
    /// Rules are evaluated in order. If any rule returns `true`, the NOTAM
    /// resurfaces. If all rules return `false` or `nil`, it stays read.
    ///
    /// - Parameters:
    ///   - globalRead: The global read record from Core Data
    ///   - notam: The NOTAM being evaluated
    ///   - context: Current flight context
    ///   - settings: Resurface settings configuration
    /// - Returns: `true` if the NOTAM should be treated as unread
    func shouldResurface(
        globalRead: CDGlobalNotamRead,
        notam: Notam,
        context: FlightContext,
        settings: ResurfaceSettings
    ) -> Bool {
        for rule in rules {
            if let result = rule.shouldResurface(
                globalRead: globalRead,
                notam: notam,
                context: context,
                settings: settings
            ) {
                if result {
                    return true  // Resurface on first true
                }
            }
        }
        return false  // Default: stay read
    }

    /// Default rules in evaluation order
    static let defaultRules: [NotamResurfaceRule] = [
        TimeBasedResurfaceRule(),
        DistanceBasedResurfaceRule()
    ]
}

// MARK: - Convenience Extension

extension NotamResurfaceEvaluator {
    /// Check if a NOTAM is effectively read (has global read and doesn't resurface)
    ///
    /// - Parameters:
    ///   - identityKey: The NOTAM identity key
    ///   - notam: The NOTAM being evaluated
    ///   - globalReads: Dictionary of global read records by identity key
    ///   - context: Current flight context
    ///   - settings: Resurface settings configuration
    /// - Returns: `true` if the NOTAM should be treated as read
    func isEffectivelyRead(
        identityKey: String,
        notam: Notam,
        globalReads: [String: CDGlobalNotamRead],
        context: FlightContext,
        settings: ResurfaceSettings
    ) -> Bool {
        // Check if there's a global read record
        guard let globalRead = globalReads[identityKey] else {
            return false  // Never globally read
        }

        // Check if it should resurface
        if shouldResurface(globalRead: globalRead, notam: notam, context: context, settings: settings) {
            return false  // Should resurface = not effectively read
        }

        return true  // Has global read and doesn't resurface
    }
}
