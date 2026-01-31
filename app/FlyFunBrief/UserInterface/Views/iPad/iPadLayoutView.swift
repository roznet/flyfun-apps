//
//  iPadLayoutView.swift
//  FlyFunBrief
//
//  iPad layout with NavigationSplitView for side-by-side browsing.
//

import SwiftUI
import RZFlight

/// iPad layout with sidebar and detail panel
struct iPadLayoutView: View {
    @Environment(\.appState) private var appState
    @State private var columnVisibility: NavigationSplitViewVisibility = .all
    @State private var isBriefingsExpanded = false

    // Advanced filter disclosure group states (shared with FilterSectionsContent)
    @State private var isRouteExpanded = false
    @State private var isTimeExpanded = false
    @State private var isSmartFiltersExpanded = false
    @State private var isCategoryExpanded = false
    @State private var isPriorityExpanded = false

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            // Sidebar: Navigation tabs or Flight context (filters + briefing selector)
            if appState?.navigation.isViewingFlight == true {
                flightContextSidebar
            } else {
                navigationSidebar
            }
        } content: {
            // Content: NOTAM list, flight list, etc.
            contentColumn
                .navigationSplitViewColumnWidth(min: 350, ideal: 450, max: 550)
        } detail: {
            // Detail: Selected NOTAM or flight details
            detailContent
                .navigationSplitViewColumnWidth(min: 350, ideal: 450, max: 600)
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    appState?.navigation.showImportSheet()
                } label: {
                    Label("Import", systemImage: "square.and.arrow.down")
                }
                .disabled(appState?.flights.selectedFlight == nil)
            }
        }
        .sheet(item: sheetBinding) { sheet in
            sheetContent(for: sheet)
        }
    }

    // MARK: - Navigation Sidebar (Tab Selection)

    @ViewBuilder
    private var navigationSidebar: some View {
        List(selection: Binding(
            get: { appState?.navigation.selectedTab },
            set: { if let tab = $0 { appState?.navigation.selectedTab = tab } }
        )) {
            Section {
                Label("Flights", systemImage: "airplane")
                    .tag(AppTab.flights)

                Label("Ignored", systemImage: "xmark.circle")
                    .tag(AppTab.ignored)

                Label("Settings", systemImage: "gearshape")
                    .tag(AppTab.settings)
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("FlyFunBrief")
    }

    // MARK: - Flight Context Sidebar (Flight Info + Briefings + Filters)

    @ViewBuilder
    private var flightContextSidebar: some View {
        List {
            // Back button
            Section {
                Button {
                    // Exit flight view - order doesn't matter now since
                    // selectFlight no longer auto-enters flight view
                    appState?.navigation.exitFlightView()
                    appState?.briefing.clearBriefing()
                    appState?.flights.clearSelection()
                } label: {
                    Label("Back to Flights", systemImage: "chevron.left")
                }
                .buttonStyle(.plain)
            }

            // Flight info section (editable summary)
            if let flight = appState?.flights.selectedFlight {
                Section("Flight") {
                    flightInfoSection(flight: flight)
                }
            }

            // Filter sections (only if we have a briefing loaded)
            // Uses shared filter content from SharedFilterContent.swift
            if appState?.briefing.currentBriefing != nil {
                FilterSectionsContent(
                    isRouteExpanded: $isRouteExpanded,
                    isTimeExpanded: $isTimeExpanded,
                    isSmartFiltersExpanded: $isSmartFiltersExpanded,
                    isCategoryExpanded: $isCategoryExpanded,
                    isPriorityExpanded: $isPriorityExpanded
                )

                // Reset filters
                if appState?.notams.hasActiveFilters == true {
                    Section {
                        Button(role: .destructive) {
                            appState?.notams.resetFilters()
                        } label: {
                            Label("Reset All Filters", systemImage: "xmark.circle")
                        }
                    }
                }
            }

            // Briefings section (at bottom for less frequent access)
            if let flight = appState?.flights.selectedFlight {
                Section("Briefings") {
                    briefingsSection(flight: flight)
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle(sidebarTitle)
    }

    // MARK: - Flight Info Section

    @ViewBuilder
    private func flightInfoSection(flight: CDFlight) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Route (tappable to edit)
            Button {
                if let id = flight.id {
                    appState?.navigation.showEditFlight(flightId: id)
                }
            } label: {
                HStack {
                    Text(flight.origin ?? "")
                        .font(.headline.monospaced())
                    Image(systemName: "arrow.right")
                        .foregroundStyle(.secondary)
                    Text(flight.destination ?? "")
                        .font(.headline.monospaced())
                    Spacer()
                    Image(systemName: "pencil")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .buttonStyle(.plain)

            // Departure time
            if let depTime = flight.departureTime {
                Label(formatDateTime(depTime), systemImage: "clock")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Route waypoints
            if !flight.routeArray.isEmpty {
                Text(flight.routeArray.joined(separator: " "))
                    .font(.caption.monospaced())
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 4)
    }

    // MARK: - Briefings Section

    @ViewBuilder
    private func briefingsSection(flight: CDFlight) -> some View {
        let briefings = flight.sortedBriefings
        let currentBriefing = appState?.briefing.currentCDBriefing
        let olderBriefings = briefings.filter { $0.id != currentBriefing?.id }

        if briefings.isEmpty {
            Button {
                appState?.navigation.showImportSheet()
            } label: {
                Label("Import First Briefing", systemImage: "square.and.arrow.down")
            }
        } else {
            // Current briefing (always visible)
            if let current = currentBriefing {
                briefingRow(current, isCurrent: true)
            }

            // Older briefings (expandable)
            if !olderBriefings.isEmpty {
                Button {
                    withAnimation {
                        isBriefingsExpanded.toggle()
                    }
                } label: {
                    HStack {
                        Text("Previous Briefings (\(olderBriefings.count))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Image(systemName: isBriefingsExpanded ? "chevron.up" : "chevron.down")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .buttonStyle(.plain)

                if isBriefingsExpanded {
                    ForEach(olderBriefings, id: \.id) { briefing in
                        briefingRow(briefing, isCurrent: false)
                    }
                }
            }

            // Import button (always visible)
            Button {
                appState?.navigation.showImportSheet()
            } label: {
                Label("Import New Briefing", systemImage: "plus")
                    .font(.caption)
            }
        }
    }

    @ViewBuilder
    private func briefingRow(_ briefing: CDBriefing, isCurrent: Bool) -> some View {
        Button {
            appState?.briefing.loadBriefing(briefing)
        } label: {
            HStack {
                if briefing.isLatest {
                    Image(systemName: "star.fill")
                        .foregroundStyle(.yellow)
                        .font(.caption)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(briefing.formattedImportDate)
                        .font(.subheadline)
                    Text("\(briefing.notamCount) NOTAMs")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                if isCurrent {
                    Image(systemName: "checkmark")
                        .foregroundStyle(.blue)
                }
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: - Filter Controls

    // MARK: - Sidebar Title

    private var sidebarTitle: String {
        if let flight = appState?.flights.selectedFlight {
            return "\(flight.origin ?? "") → \(flight.destination ?? "")"
        }
        return "Flight"
    }

    // MARK: - Content Column

    @ViewBuilder
    private var contentColumn: some View {
        if appState?.navigation.isViewingFlight == true {
            // Viewing a flight - show NOTAMs
            NotamListView()
        } else {
            // Tab-based content
            switch appState?.navigation.selectedTab {
            case .flights:
                FlightListView()
            case .ignored:
                IgnoreListView()
            case .settings:
                SettingsView()
            case .none:
                ContentUnavailableView("Select a section", systemImage: "sidebar.left")
            }
        }
    }

    // MARK: - Detail Content

    @ViewBuilder
    private var detailContent: some View {
        if let notam = appState?.notams.selectedNotam {
            NotamDetailView(notam: notam)
        } else if appState?.navigation.isViewingFlight == true {
            // Viewing flight - prompt to select NOTAM
            if appState?.briefing.currentBriefing != nil {
                ContentUnavailableView {
                    Label("Select a NOTAM", systemImage: "doc.text.magnifyingglass")
                } description: {
                    Text("Choose a NOTAM from the list to see details.")
                }
            } else {
                ContentUnavailableView {
                    Label("No Briefing Loaded", systemImage: "doc.badge.plus")
                } description: {
                    Text("Import a briefing to view NOTAMs.")
                } actions: {
                    Button {
                        appState?.navigation.showImportSheet()
                    } label: {
                        Label("Import Briefing", systemImage: "square.and.arrow.down")
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        } else if appState?.navigation.selectedTab == .flights {
            if let flight = appState?.flights.selectedFlight {
                FlightDetailView(flight: flight)
            } else {
                ContentUnavailableView {
                    Label("Select a Flight", systemImage: "airplane")
                } description: {
                    Text("Choose a flight from the list to see details.")
                }
            }
        } else {
            ContentUnavailableView {
                Label("Welcome to FlyFunBrief", systemImage: "airplane")
            } description: {
                Text("Select a flight to view and manage your NOTAMs.")
            }
        }
    }

    // MARK: - Bindings

    private var sheetBinding: Binding<AppSheet?> {
        Binding(
            get: { appState?.navigation.presentedSheet },
            set: { appState?.navigation.presentedSheet = $0 }
        )
    }

    // MARK: - Sheet Content

    @ViewBuilder
    private func sheetContent(for sheet: AppSheet) -> some View {
        switch sheet {
        case .importBriefing:
            ImportBriefingView()
        case .notamDetail:
            // On iPad, detail shows in split view, not sheet
            EmptyView()
        case .filterOptions:
            FilterPanelView()
        case .settings:
            SettingsView()
        case .newFlight:
            NavigationStack {
                FlightEditorView(mode: .create)
            }
        case .editFlight(let flightId):
            if let flight = appState?.flights.flights.first(where: { $0.id == flightId }) {
                NavigationStack {
                    FlightEditorView(mode: .edit(flight))
                }
            }
        case .flightPicker:
            FlightPickerView()
        }
    }

    // MARK: - Helpers

    private func formatDateTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "dd MMM HH:mm 'UTC'"
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter.string(from: date)
    }
}

// MARK: - Preview

#Preview {
    iPadLayoutView()
        .environment(\.appState, AppState.preview())
}
