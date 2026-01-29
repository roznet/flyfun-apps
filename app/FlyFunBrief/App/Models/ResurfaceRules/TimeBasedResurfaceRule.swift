//
//  TimeBasedResurfaceRule.swift
//  FlyFunBrief
//
//  Resurface rule that treats globally-read NOTAMs as unread
//  after a configurable time threshold has passed.
//

import Foundation
import RZFlight

/// Resurfaces NOTAMs that were read more than X days ago.
///
/// This ensures users periodically re-review NOTAMs even if they've
/// been read before, as NOTAM relevance can change over time.
struct TimeBasedResurfaceRule: NotamResurfaceRule {
    let id = "time_based"
    let name = "Time-based resurface"

    func shouldResurface(
        globalRead: CDGlobalNotamRead,
        notam: Notam,
        context: FlightContext,
        settings: ResurfaceSettings
    ) -> Bool? {
        guard settings.timeResurfaceEnabled else {
            return nil  // Defer to next rule
        }

        guard let lastReadAt = globalRead.lastReadAt else {
            // No read date recorded - treat as should resurface
            return true
        }

        let daysSinceRead = globalRead.daysSinceLastRead
        return daysSinceRead > settings.timeDays
    }
}
