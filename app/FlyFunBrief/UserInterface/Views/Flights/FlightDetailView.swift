//
//  FlightDetailView.swift
//  FlyFunBrief
//
//  Detail view for a single flight with briefing history.
//

import SwiftUI
import CoreData

/// Detail view for a flight
struct FlightDetailView: View {
    @Environment(\.appState) private var appState
    let flight: CDFlight

    @State private var showingEditor = false
    @State private var showingImport = false

    var body: some View {
        List {
            // Flight info section
            Section {
                flightInfoRows
            }

            // Briefings section
            Section {
                briefingsList
            } header: {
                HStack {
                    Text("Briefings")
                    Spacer()
                    Button {
                        showingImport = true
                    } label: {
                        Label("Import", systemImage: "square.and.arrow.down")
                            .font(.caption)
                    }
                }
            }

            // Quick stats section
            if let latest = flight.latestBriefing {
                Section("Latest Briefing Stats") {
                    statsRows(for: latest)
                }
            }
        }
        .navigationTitle(flight.displayTitle)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showingEditor = true
                } label: {
                    Label("Edit", systemImage: "pencil")
                }
            }
        }
        .sheet(isPresented: $showingEditor) {
            NavigationStack {
                FlightEditorView(mode: .edit(flight))
            }
        }
        .sheet(isPresented: $showingImport) {
            ImportBriefingView()
        }
        .onAppear {
            // Select for preview - this no longer has side effects
            appState?.flights.selectFlight(flight)
        }
    }

    // MARK: - Flight Info

    @ViewBuilder
    private var flightInfoRows: some View {
        LabeledContent("Route") {
            Text(flight.displayTitle)
                .foregroundStyle(.primary)
        }

        if let departureTime = flight.departureTime {
            LabeledContent("Departure") {
                Text(formattedDateTime(departureTime))
            }
        }

        if flight.durationHours > 0 {
            LabeledContent("Duration") {
                Text(formattedDuration(flight.durationHours))
            }
        }

        if !flight.routeArray.isEmpty {
            LabeledContent("Waypoints") {
                Text(flight.routeArray.joined(separator: " "))
                    .foregroundStyle(.secondary)
            }
        }

        if let createdAt = flight.createdAt {
            LabeledContent("Created") {
                Text(formattedDateTime(createdAt))
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Briefings List

    @ViewBuilder
    private var briefingsList: some View {
        let briefings = flight.sortedBriefings

        if briefings.isEmpty {
            Text("No briefings imported yet")
                .foregroundStyle(.secondary)
                .italic()
        } else {
            ForEach(briefings, id: \.id) { briefing in
                NavigationLink {
                    BriefingDetailView(briefing: briefing)
                } label: {
                    BriefingRowView(briefing: briefing)
                }
            }
        }
    }

    // MARK: - Stats

    @ViewBuilder
    private func statsRows(for briefing: CDBriefing) -> some View {
        let notamCount = briefing.notamCount
        let statusesByNotamId = briefing.statusesByNotamId
        let unreadCount = statusesByNotamId.values.filter { $0.statusEnum == .unread }.count
        let importantCount = statusesByNotamId.values.filter { $0.statusEnum == .important }.count

        LabeledContent("Total NOTAMs") {
            Text("\(notamCount)")
        }

        LabeledContent("Unread") {
            Text("\(unreadCount)")
                .foregroundStyle(unreadCount > 0 ? .blue : .secondary)
        }

        LabeledContent("Marked Important") {
            Text("\(importantCount)")
                .foregroundStyle(importantCount > 0 ? .yellow : .secondary)
        }
    }

    // MARK: - Formatting

    private func formattedDateTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }

    private func formattedDuration(_ hours: Double) -> String {
        let totalMinutes = Int(hours * 60)
        let h = totalMinutes / 60
        let m = totalMinutes % 60
        if h > 0 && m > 0 {
            return "\(h)h \(m)m"
        } else if h > 0 {
            return "\(h)h"
        } else {
            return "\(m)m"
        }
    }
}

// MARK: - Briefing Row View

struct BriefingRowView: View {
    let briefing: CDBriefing

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                if briefing.isLatest {
                    Image(systemName: "star.fill")
                        .foregroundStyle(.yellow)
                        .font(.caption)
                }

                Text(briefing.formattedImportDate)
                    .font(.subheadline)

                Spacer()

                Text("\(briefing.notamCount) NOTAMs")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let summary = briefing.routeSummary {
                Text(summary)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Briefing Detail View

struct BriefingDetailView: View {
    @Environment(\.appState) private var appState
    let briefing: CDBriefing

    var body: some View {
        Group {
            if let decoded = briefing.decodedBriefing {
                NotamListView()
                    .onAppear {
                        appState?.notams.setBriefing(decoded)
                    }
            } else {
                ContentUnavailableView {
                    Label("Unable to Load", systemImage: "exclamationmark.triangle")
                } description: {
                    Text("Failed to decode briefing data.")
                }
            }
        }
        .navigationTitle("Briefing")
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Preview

struct FlightDetailView_Previews: PreviewProvider {
    static var previews: some View {
        let context = PersistenceController.preview.viewContext
        let flight = CDFlight.create(
            in: context,
            origin: "LFPG",
            destination: "EGLL",
            departureTime: Date().addingTimeInterval(86400),
            durationHours: 1.5
        )
        return NavigationStack {
            FlightDetailView(flight: flight)
        }
        .environment(\.appState, AppState.preview())
    }
}
