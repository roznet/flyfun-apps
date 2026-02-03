//
//  NotamRowView.swift
//  FlyFunBrief
//
//  Compact NOTAM row for list display.
//

import SwiftUI
import RZFlight

/// Row view for NOTAM list with configurable display style
struct NotamRowView: View {
    @Environment(\.appState) private var appState
    let enrichedNotam: EnrichedNotam

    /// Convenience accessor for underlying NOTAM
    private var notam: Notam { enrichedNotam.notam }

    /// Current row style from app state
    private var rowStyle: NotamRowStyle {
        appState?.notams.rowStyle ?? .standard
    }

    var body: some View {
        HStack(spacing: 12) {
            statusIndicator
            content
            Spacer()
            badges
        }
        .padding(.vertical, rowStyle == .full ? 8 : 4)
        .opacity(enrichedNotam.isGloballyIgnored ? 0.5 : 1.0)
        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
            Button {
                appState?.notams.markAsRead(notam)
            } label: {
                Label("Read", systemImage: "checkmark")
            }
            .tint(.green)

            Button {
                appState?.notams.toggleImportant(notam)
            } label: {
                Label("Important", systemImage: "star")
            }
            .tint(.yellow)
        }
        .swipeActions(edge: .leading) {
            Button {
                appState?.notams.markAsIgnored(notam)
            } label: {
                Label("Ignore", systemImage: "xmark")
            }
            .tint(.secondary)
        }
    }

    // MARK: - Status Indicator

    private var statusIndicator: some View {
        Circle()
            .fill(statusColor)
            .frame(width: 10, height: 10)
    }

    private var statusColor: Color {
        switch enrichedNotam.status {
        case .unread:
            return .blue
        case .read:
            return .gray
        case .important:
            return .yellow
        case .ignore:
            return .secondary.opacity(0.5)
        case .followUp:
            return .orange
        }
    }

    // MARK: - Badges

    @ViewBuilder
    private var badges: some View {
        HStack(spacing: 4) {
            // Priority indicator
            priorityIcon

            if enrichedNotam.isGloballyIgnored {
                Image(systemName: "eye.slash")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    /// Priority icon based on computed priority
    @ViewBuilder
    private var priorityIcon: some View {
        let priority = enrichedNotam.priority
        if let iconName = priority.iconName {
            HStack(spacing: 2) {
                Image(systemName: iconName)
                    .font(.caption2)
                Text(priority.label)
                    .font(.caption2.weight(.medium))
            }
            .foregroundStyle(priority.color)
        }
    }

    // MARK: - Content

    private var content: some View {
        VStack(alignment: .leading, spacing: 4) {
            // Title row with inline ID for compact mode
            if rowStyle == .compact {
                compactTitleRow
            } else {
                // Title row: full width
                Text(notamTitle)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.primary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            // Detail row (location, ID, distance, altitude, inactive) - hidden in compact mode
            if rowStyle.showDetailRow {
                HStack(spacing: 8) {
                    // Location first - highlighted if airport, subdued if FIR/other
                    Text(notam.location)
                        .font(.caption.monospaced())
                        .foregroundStyle(isAirportLocation ? .primary : .tertiary)

                    Text(notam.id)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)

                    Spacer()

                    // Distance from route (highlighted if < 50nm)
                    if let distanceText = enrichedNotam.routeDistanceText {
                        Text(distanceText)
                            .font(.caption2)
                            .foregroundColor(enrichedNotam.isDistanceRelevant ? .blue : .gray)
                    }

                    // Altitude range (highlighted if includes cruise altitude ±2000ft)
                    if let altitudeText = enrichedNotam.altitudeRangeText {
                        Text(altitudeText)
                            .font(.caption2)
                            .foregroundColor(enrichedNotam.isAltitudeRelevant ? .blue : .gray)
                    }

                    // Inactive indicator (if flight time is set and NOTAM is inactive)
                    if !enrichedNotam.isActiveForFlight {
                        Text("Inactive")
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(.orange)
                    }
                }
            }

            // Message text - line limit varies by style
            if rowStyle.messageLineLimit > 0 {
                let charLimit = rowStyle == .full ? 500 : 120
                Text(notam.message.prefix(charLimit) + (notam.message.count > charLimit ? "..." : ""))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(rowStyle.messageLineLimit)
            }
        }
    }

    // MARK: - Compact Title Row

    /// Compact mode: title + ID on same line
    private var compactTitleRow: some View {
        HStack(spacing: 8) {
            Text(notamTitle)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.primary)
                .lineLimit(1)

            Spacer()

            Text(notam.id)
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)

            // Inactive indicator
            if !enrichedNotam.isActiveForFlight {
                Text("Inactive")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.orange)
            }
        }
    }

    // MARK: - Title Generation

    /// Generate a human-readable title from Q-code info or category
    private var notamTitle: String {
        // Best: use parsed Q-code display text from server
        if let qCodeInfo = notam.qCodeInfo {
            // displayText is like "Runway: Closed" - perfect for title
            return qCodeInfo.displayText
        }

        // Fallback: use primary category from categorization pipeline
        if let primary = notam.primaryCategory {
            let categoryTitle = formatCategory(primary)
            let tagText = formatTags(notam.customTags)
            if !tagText.isEmpty {
                return "\(categoryTitle): \(tagText)"
            }
            return categoryTitle
        }

        // Fall back to ICAO category
        if let category = notam.category {
            return category.displayName
        }

        return notam.location
    }

    /// Format primary category to title case
    private func formatCategory(_ category: String) -> String {
        switch category.lowercased() {
        case "runway": return "Runway"
        case "taxiway": return "Taxiway"
        case "apron": return "Apron"
        case "lighting": return "Lighting"
        case "navaid": return "Navaid"
        case "procedure": return "Procedure"
        case "airspace": return "Airspace"
        case "obstacle": return "Obstacle"
        case "communication": return "Comm"
        case "services": return "Services"
        case "warning": return "Warning"
        default: return category.capitalized
        }
    }

    /// Format tags into readable text
    private func formatTags(_ tags: [String]) -> String {
        // Priority tags to show
        let priorityTags = ["closed", "unserviceable", "limited", "unavailable",
                           "active", "changed", "work_in_progress"]

        // Find first priority tag
        for tag in priorityTags {
            if tags.contains(tag) {
                return formatTag(tag)
            }
        }

        // Show specific equipment tags
        let equipmentTags = ["vor", "ils", "dme", "ndb", "glideslope", "localizer",
                            "papi", "vasi", "approach", "sid", "star"]
        for tag in equipmentTags {
            if tags.contains(tag) {
                return tag.uppercased()
            }
        }

        return ""
    }

    /// Format a single tag
    private func formatTag(_ tag: String) -> String {
        switch tag {
        case "closed": return "Closed"
        case "unserviceable": return "U/S"
        case "limited": return "Limited"
        case "unavailable": return "Unavailable"
        case "active": return "Active"
        case "changed": return "Changed"
        case "work_in_progress": return "WIP"
        default: return tag.capitalized
        }
    }

    // MARK: - Location Type

    /// Whether the NOTAM scope is aerodrome (A) vs en-route (E) or warning (W)
    /// Uses the scope field from the Q-line which is the authoritative source
    private var isAirportLocation: Bool {
        // Scope from Q-line: A = Aerodrome, E = En-route, W = Nav Warning
        // Can contain multiple letters (e.g., "AE" for both)
        guard let scope = notam.scope else { return false }
        return scope.contains("A")
    }
}

// MARK: - Preview

#Preview {
    List {
        // Preview would need actual EnrichedNotam data
        Text("NotamRowView Preview")
    }
    .environment(\.appState, AppState.preview())
}
