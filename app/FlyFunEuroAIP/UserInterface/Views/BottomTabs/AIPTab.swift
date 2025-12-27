//
//  AIPTab.swift
//  FlyFunEuroAIP
//
//  AIP entries tab showing AIP information for the airport
//

import SwiftUI
import RZFlight

struct AIPTab: View {
    @Environment(\.appState) private var state
    let airport: RZFlight.Airport

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Notification summary at top (if available)
                if let notification = state?.notificationService?.getNotification(icao: airport.icao) {
                    NotificationSummaryView(notification: notification)
                }

                if airport.aipEntries.isEmpty {
                    ContentUnavailableView {
                        Label("No AIP Data", systemImage: "doc.text")
                    } description: {
                        Text("No AIP entries available for \(airport.icao)")
                    }
                } else {
                    // Group by section - sort by rawValue
                    ForEach(Array(groupedEntries.keys.sorted(by: { $0.rawValue < $1.rawValue })), id: \.self) { section in
                        if let entries = groupedEntries[section] {
                            AIPSectionGroup(section: section, entries: entries)
                        }
                    }
                }
            }
            .padding()
        }
    }

    private var groupedEntries: [RZFlight.AIPEntry.Section: [RZFlight.AIPEntry]] {
        Dictionary(grouping: airport.aipEntries, by: { $0.section })
    }
}

// MARK: - Preview
// Note: Preview requires sample airport data - to be implemented with PreviewFactory

