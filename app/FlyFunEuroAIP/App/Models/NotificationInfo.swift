//
//  NotificationInfo.swift
//  FlyFunEuroAIP
//
//  Notification requirements for an airport.
//  Data comes from bundled ga_notifications.db
//

import Foundation
import SwiftUI

/// Notification requirements for an airport
struct NotificationInfo: Sendable, Equatable {
    /// Type of notification requirement
    enum NotificationType: String, Sendable, CaseIterable {
        case h24 = "h24"                    // 24/7 available, no notice needed
        case hours = "hours"                 // Requires X hours notice
        case onRequest = "on_request"        // Available on request
        case businessDay = "business_day"    // Business day notice required
        case notAvailable = "not_available"  // Not available
        case unknown = "unknown"             // Could not parse

        var displayName: String {
            switch self {
            case .h24: return "24/7"
            case .hours: return "Notice Required"
            case .onRequest: return "On Request"
            case .businessDay: return "Business Day"
            case .notAvailable: return "Unavailable"
            case .unknown: return "Unknown"
            }
        }

        var iconName: String {
            switch self {
            case .h24: return "checkmark.circle.fill"
            case .hours: return "clock.fill"
            case .onRequest: return "phone.fill"
            case .businessDay: return "calendar"
            case .notAvailable: return "xmark.circle.fill"
            case .unknown: return "questionmark.circle"
            }
        }
    }

    /// Type of rule (customs, immigration, etc.)
    enum RuleType: String, Sendable {
        case customs
        case immigration
        case ppr
        case pn
        case handling
    }

    let icao: String
    let ruleType: RuleType
    let notificationType: NotificationType
    let hoursNotice: Int?
    let operatingHoursStart: String?
    let operatingHoursEnd: String?
    let weekdayRules: [String: String]?
    let summary: String
    let confidence: Double
    let contactPhone: String?
    let contactEmail: String?

    // MARK: - Computed Properties

    /// Whether no prior notice is required
    var isH24: Bool {
        notificationType == .h24
    }

    /// Whether notification is on request / by arrangement
    var isOnRequest: Bool {
        notificationType == .onRequest
    }

    /// Display summary (truncated if needed)
    var displaySummary: String {
        if summary.count > 150 {
            return String(summary.prefix(150)) + "..."
        }
        return summary
    }

    /// Operating hours as formatted string
    var operatingHours: String? {
        guard let start = operatingHoursStart, let end = operatingHoursEnd else {
            return nil
        }
        return "\(start)-\(end)"
    }

    /// Maximum hours notice required (checking weekday rules too)
    var maxNoticeHours: Int? {
        if isH24 { return 0 }
        if isOnRequest { return nil }

        var maxHours = hoursNotice

        // Check weekday rules for higher values
        if let rules = weekdayRules {
            for (_, value) in rules {
                if let hours = parseHoursFromString(value) {
                    if maxHours == nil || hours > maxHours! {
                        maxHours = hours
                    }
                }
            }
        }

        return maxHours
    }

    /// Easiness score from 0-100 (higher = easier to access)
    var easinessScore: Double {
        switch notificationType {
        case .h24:
            return 100.0  // 24/7, no notice needed
        case .notAvailable:
            return 0.0    // Not available at all
        case .unknown:
            return 50.0   // Truly unknown
        case .onRequest:
            return 70.0   // Available but need to call ahead
        case .businessDay:
            // Business day notice - treat as ~24h
            return 55.0
        case .hours:
            // Has operating hours - check if advance notice is also required
            guard let maxHours = maxNoticeHours, maxHours > 0 else {
                // Operating hours only, no advance notice needed = easy
                return 85.0
            }
            // Advance notice required - score by hours
            switch maxHours {
            case 1...2: return 90.0
            case 3...12: return 80.0
            case 13...24: return 60.0
            case 25...48: return 40.0
            case 49...72: return 20.0
            default: return 10.0
            }
        }
    }

    /// Color for legend mode based on easiness
    var legendColor: Color {
        let score = easinessScore
        switch score {
        case 80...100: return .green
        case 60..<80: return .blue
        case 40..<60: return .orange
        default: return .red
        }
    }

    // MARK: - Private Helpers

    private func parseHoursFromString(_ value: String) -> Int? {
        // Parse strings like "24h notice", "48h", etc.
        let pattern = #"(\d+)\s*h"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
              let match = regex.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)),
              let range = Range(match.range(at: 1), in: value) else {
            return nil
        }
        return Int(value[range])
    }
}

// MARK: - Initialization from DB Row

extension NotificationInfo {
    /// Create from database row dictionary
    init?(from row: [String: Any]) {
        guard let icao = row["icao"] as? String else { return nil }

        self.icao = icao

        // Parse rule type
        if let ruleTypeStr = row["rule_type"] as? String,
           let ruleType = RuleType(rawValue: ruleTypeStr) {
            self.ruleType = ruleType
        } else {
            self.ruleType = .ppr
        }

        // Parse notification type
        if let notifTypeStr = row["notification_type"] as? String,
           let notifType = NotificationType(rawValue: notifTypeStr) {
            self.notificationType = notifType
        } else {
            self.notificationType = .unknown
        }

        self.hoursNotice = row["hours_notice"] as? Int
        self.operatingHoursStart = row["operating_hours_start"] as? String
        self.operatingHoursEnd = row["operating_hours_end"] as? String
        self.summary = row["summary"] as? String ?? ""
        self.confidence = row["confidence"] as? Double ?? 0.0

        // Parse weekday rules JSON
        if let weekdayJson = row["weekday_rules"] as? String,
           let data = weekdayJson.data(using: .utf8),
           let rules = try? JSONSerialization.jsonObject(with: data) as? [String: String] {
            self.weekdayRules = rules
        } else {
            self.weekdayRules = nil
        }

        // Parse contact info JSON
        if let contactJson = row["contact_info"] as? String,
           let data = contactJson.data(using: .utf8),
           let contact = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            self.contactPhone = contact["phone"] as? String
            self.contactEmail = contact["email"] as? String
        } else {
            self.contactPhone = nil
            self.contactEmail = nil
        }
    }
}
