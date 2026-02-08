//
//  IgnoreListView.swift
//  FlyFunBrief
//
//  View for managing the global NOTAM and airport ignore lists.
//

import SwiftUI
import OSLog

/// Which ignore list to display
enum IgnoreListMode: String, CaseIterable, Identifiable {
    case notams = "NOTAMs"
    case airports = "Airports"

    var id: String { rawValue }
}

/// View for the global NOTAM and airport ignore lists
struct IgnoreListView: View {
    @Environment(\.appState) private var appState
    @State private var mode: IgnoreListMode = .notams
    @State private var ignoredNotams: [CDIgnoredNotam] = []
    @State private var ignoredAirports: [CDIgnoredAirport] = []
    @State private var showExpired = false
    @State private var isLoading = false

    var body: some View {
        VStack(spacing: 0) {
            // Segmented picker
            Picker("List", selection: $mode) {
                ForEach(IgnoreListMode.allCases) { m in
                    Text(m.rawValue).tag(m)
                }
            }
            .pickerStyle(.segmented)
            .padding()

            // Content
            Group {
                if isLoading {
                    ProgressView("Loading...")
                } else {
                    switch mode {
                    case .notams:
                        notamIgnoreContent
                    case .airports:
                        airportIgnoreContent
                    }
                }
            }
            .frame(maxHeight: .infinity)
        }
        .navigationTitle("Ignore List")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                if mode == .notams {
                    notamToolbarMenu
                }
            }
        }
        .task {
            await loadAll()
        }
        .refreshable {
            await loadAll()
        }
    }

    // MARK: - NOTAM Ignore Content

    @ViewBuilder
    private var notamIgnoreContent: some View {
        if filteredNotams.isEmpty {
            ContentUnavailableView {
                Label("No Ignored NOTAMs", systemImage: "xmark.circle")
            } description: {
                Text("NOTAMs you ignore will appear here. You can ignore NOTAMs from the NOTAM list.")
            }
        } else {
            List {
                ForEach(filteredNotams, id: \.id) { ignored in
                    IgnoredNotamRowView(ignoredNotam: ignored)
                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                            Button(role: .destructive) {
                                removeNotamFromIgnoreList(ignored)
                            } label: {
                                Label("Remove", systemImage: "xmark.circle")
                            }
                        }
                }
            }
        }
    }

    // MARK: - Airport Ignore Content

    @ViewBuilder
    private var airportIgnoreContent: some View {
        if ignoredAirports.isEmpty {
            ContentUnavailableView {
                Label("No Ignored Airports", systemImage: "building.2")
            } description: {
                Text("Airports you ignore will appear here. Long-press an airport header in the NOTAM list to ignore all its NOTAMs.")
            }
        } else {
            List {
                ForEach(ignoredAirports, id: \.id) { ignored in
                    IgnoredAirportRowView(ignoredAirport: ignored)
                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                            Button(role: .destructive) {
                                removeAirportFromIgnoreList(ignored)
                            } label: {
                                Label("Remove", systemImage: "xmark.circle")
                            }
                        }
                }
            }
        }
    }

    // MARK: - Toolbar

    private var notamToolbarMenu: some View {
        Menu {
            Toggle("Show Expired", isOn: $showExpired)

            Divider()

            Button(role: .destructive) {
                cleanupExpired()
            } label: {
                Label("Remove Expired", systemImage: "trash")
            }
            .disabled(!hasExpiredEntries)
        } label: {
            Label("Options", systemImage: "ellipsis.circle")
        }
    }

    // MARK: - Computed Properties

    private var filteredNotams: [CDIgnoredNotam] {
        if showExpired {
            return ignoredNotams
        } else {
            return ignoredNotams.filter { !$0.isExpired }
        }
    }

    private var hasExpiredEntries: Bool {
        ignoredNotams.contains { $0.isExpired }
    }

    // MARK: - Loading

    private func loadAll() async {
        isLoading = true

        do {
            if let manager = appState?.ignoreListManager {
                ignoredNotams = try manager.fetchAllIgnores()
            }
            if let manager = appState?.airportIgnoreListManager {
                ignoredAirports = try manager.fetchAllIgnores()
            }
        } catch {
            Logger.app.error("Failed to load ignore lists: \(error.localizedDescription)")
        }

        isLoading = false
    }

    // MARK: - Actions

    private func removeNotamFromIgnoreList(_ ignored: CDIgnoredNotam) {
        Task {
            do {
                try appState?.ignoreListManager.removeFromIgnoreList(ignored)
                await loadAll()
            } catch {
                Logger.app.error("Failed to remove from ignore list: \(error.localizedDescription)")
            }
        }
    }

    private func removeAirportFromIgnoreList(_ ignored: CDIgnoredAirport) {
        Task {
            if let icao = ignored.icaoCode {
                await appState?.notams.removeAirportFromIgnoreList(icao)
                await loadAll()
            }
        }
    }

    private func cleanupExpired() {
        Task {
            do {
                try appState?.ignoreListManager.cleanupExpired()
                await loadAll()
            } catch {
                Logger.app.error("Failed to cleanup expired: \(error.localizedDescription)")
            }
        }
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        IgnoreListView()
    }
    .environment(\.appState, AppState.preview())
}
