//
//  NotificationSummaryView.swift
//  FlyFunEuroAIP
//
//  Displays parsed notification/customs requirements summary.
//

import SwiftUI

struct NotificationSummaryView: View {
    let notification: NotificationInfo

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header with type and icon
            HStack {
                Image(systemName: notification.notificationType.iconName)
                    .font(.title2)
                    .foregroundColor(iconColor)

                VStack(alignment: .leading, spacing: 2) {
                    Text(notification.notificationType.displayName)
                        .font(.headline)

                    if let hours = notification.hoursNotice {
                        Text("\(hours) hours notice required")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                // Easiness badge
                EasinessBadge(score: notification.easinessScore)
            }

            Divider()

            // Summary text
            if !notification.summary.isEmpty {
                Text(notification.summary)
                    .font(.body)
                    .foregroundStyle(.primary)
            }

            // Operating hours if available
            if let hours = notification.operatingHours {
                HStack {
                    Image(systemName: "clock")
                        .foregroundStyle(.secondary)
                    Text("Operating hours: \(hours)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            // Contact info if available
            if notification.contactPhone != nil || notification.contactEmail != nil {
                HStack(spacing: 16) {
                    if let phone = notification.contactPhone {
                        Link(destination: URL(string: "tel:\(phone)")!) {
                            Label(phone, systemImage: "phone.fill")
                                .font(.caption)
                        }
                    }
                    if let email = notification.contactEmail {
                        Link(destination: URL(string: "mailto:\(email)")!) {
                            Label(email, systemImage: "envelope.fill")
                                .font(.caption)
                        }
                    }
                }
            }

            // Confidence indicator
            if notification.confidence < 0.9 {
                HStack {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundColor(.orange)
                    Text("Confidence: \(Int(notification.confidence * 100))% - Verify with official sources")
                        .font(.caption)
                        .foregroundColor(.orange)
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }

    private var iconColor: Color {
        switch notification.notificationType {
        case .h24: return .green
        case .hours: return .blue
        case .onRequest: return .orange
        case .businessDay: return .purple
        case .notAvailable: return .red
        case .unknown: return .gray
        }
    }
}

// MARK: - Easiness Badge

struct EasinessBadge: View {
    let score: Double

    var body: some View {
        Text(label)
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.2))
            .foregroundColor(color)
            .cornerRadius(8)
    }

    private var label: String {
        switch score {
        case 80...100: return "Easy"
        case 60..<80: return "Moderate"
        case 40..<60: return "Some hassle"
        default: return "High hassle"
        }
    }

    private var color: Color {
        switch score {
        case 80...100: return .green
        case 60..<80: return .blue
        case 40..<60: return .orange
        default: return .red
        }
    }
}

// MARK: - Compact Summary View (for inline display)

struct NotificationCompactView: View {
    let notification: NotificationInfo

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: notification.notificationType.iconName)
                .foregroundColor(iconColor)

            VStack(alignment: .leading, spacing: 2) {
                Text(notification.notificationType.displayName)
                    .font(.subheadline.bold())

                if let hours = notification.hoursNotice {
                    Text("\(hours)h notice")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            EasinessBadge(score: notification.easinessScore)
        }
        .padding(.vertical, 8)
    }

    private var iconColor: Color {
        switch notification.notificationType {
        case .h24: return .green
        case .hours: return .blue
        case .onRequest: return .orange
        case .businessDay: return .purple
        case .notAvailable: return .red
        case .unknown: return .gray
        }
    }
}

// MARK: - Preview

#Preview("Full Summary") {
    VStack {
        NotificationSummaryView(
            notification: NotificationInfo(from: [
                "icao": "LFPG",
                "rule_type": "customs",
                "notification_type": "hours",
                "hours_notice": 24,
                "summary": "Customs clearance available with 24 hours advance notice. Contact Airport Authority for PPR arrangements.",
                "confidence": 0.85,
                "contact_info": "{\"phone\":\"+33 1 23 45 67 89\",\"email\":\"customs@airport.fr\"}"
            ])!
        )

        NotificationSummaryView(
            notification: NotificationInfo(from: [
                "icao": "EGLL",
                "rule_type": "customs",
                "notification_type": "h24",
                "summary": "24/7 customs and immigration available.",
                "confidence": 0.95
            ])!
        )
    }
    .padding()
}

#Preview("Compact") {
    NotificationCompactView(
        notification: NotificationInfo(from: [
            "icao": "LFPG",
            "rule_type": "customs",
            "notification_type": "hours",
            "hours_notice": 24,
            "summary": "24h notice required",
            "confidence": 0.9
        ])!
    )
    .padding()
}
