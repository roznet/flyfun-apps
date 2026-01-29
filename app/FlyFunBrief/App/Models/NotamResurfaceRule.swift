//
//  NotamResurfaceRule.swift
//  FlyFunBrief
//
//  Protocol for NOTAM resurface rules that determine when globally-read NOTAMs
//  should be treated as unread again based on time and context changes.
//

import Foundation
import RZFlight

// MARK: - Resurface Settings

/// Configuration for resurface rule evaluation
struct ResurfaceSettings {
    /// Days until a globally-read NOTAM resurfaces as unread
    var timeDays: Int = 7

    /// Distance threshold in nm for route proximity resurface
    var distanceNm: Double = 25.0

    /// Whether time-based resurfacing is enabled
    var timeResurfaceEnabled: Bool = true

    /// Whether distance-based resurfacing is enabled
    var distanceResurfaceEnabled: Bool = true

    static let `default` = ResurfaceSettings()
}

// MARK: - Resurface Rule Protocol

/// Protocol for NOTAM resurface rules.
///
/// Resurface rules determine when a globally-read NOTAM should be treated as
/// unread again. This allows NOTAMs to "resurface" when context changes
/// (e.g., time passes, or flying a different route).
///
/// Design mirrors NotamPriorityRule for consistency.
protocol NotamResurfaceRule {
    /// Unique identifier for this rule
    var id: String { get }

    /// Human-readable name for settings UI
    var name: String { get }

    /// Evaluate whether a globally-read NOTAM should resurface.
    ///
    /// - Parameters:
    ///   - globalRead: The global read record from Core Data
    ///   - notam: The NOTAM being evaluated
    ///   - context: Current flight context
    ///   - settings: Resurface settings configuration
    /// - Returns: `true` if the NOTAM should resurface (be treated as unread),
    ///            `false` if it should remain read, `nil` to defer to next rule
    func shouldResurface(
        globalRead: CDGlobalNotamRead,
        notam: Notam,
        context: FlightContext,
        settings: ResurfaceSettings
    ) -> Bool?
}
