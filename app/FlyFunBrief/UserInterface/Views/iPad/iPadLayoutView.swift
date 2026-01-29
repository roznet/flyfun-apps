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
                    appState?.navigation.exitFlightView()
                    appState?.briefing.clearBriefing()
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

                // Briefings section
                Section("Briefings") {
                    briefingsSection(flight: flight)
                }
            }

            // Filter sections (only if we have a briefing loaded)
            if appState?.briefing.currentBriefing != nil {
                Section("View Style") {
                    rowStylePicker
                }

                Section("Status Filter") {
                    statusFilterPicker
                }

                Section("Categories") {
                    categoryToggles
                }

                Section("Route Corridor") {
                    routeFilterControls
                }

                Section("Time Filter") {
                    timeFilterControls
                }

                Section("Visibility") {
                    visibilityToggles
                }

                Section("Grouping") {
                    groupingPicker
                }

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

    private var rowStylePicker: some View {
        Picker("Style", selection: rowStyleBinding) {
            ForEach(NotamRowStyle.allCases) { style in
                Text(style.rawValue).tag(style)
            }
        }
        .pickerStyle(.segmented)
    }

    private var statusFilterPicker: some View {
        Picker("Status", selection: statusFilterBinding) {
            ForEach(StatusFilter.allCases) { status in
                Text(status.rawValue).tag(status)
            }
        }
        .pickerStyle(.segmented)
    }

    @ViewBuilder
    private var categoryToggles: some View {
        // AGA - Ground
        Toggle("Movement Area", isOn: categoryBinding(\.showMovement))
        Toggle("Lighting", isOn: categoryBinding(\.showLighting))
        Toggle("Facilities", isOn: categoryBinding(\.showFacilities))
        // CNS - Navigation
        Toggle("Navigation", isOn: categoryBinding(\.showNavigation))
        Toggle("ILS/MLS", isOn: categoryBinding(\.showILS))
        Toggle("GNSS", isOn: categoryBinding(\.showGNSS))
        Toggle("Communications", isOn: categoryBinding(\.showCommunications))
        // ATM - Traffic
        Toggle("Airspace", isOn: categoryBinding(\.showAirspace))
        Toggle("Procedures", isOn: categoryBinding(\.showProcedures))
        Toggle("Services", isOn: categoryBinding(\.showServices))
        Toggle("Restrictions", isOn: categoryBinding(\.showRestrictions))
        // Other
        Toggle("Other Info", isOn: categoryBinding(\.showOther))
    }

    @ViewBuilder
    private var routeFilterControls: some View {
        Toggle("Filter by Route", isOn: routeEnabledBinding)

        if appState?.notams.routeFilter.isEnabled == true {
            Picker("Corridor Width", selection: corridorWidthBinding) {
                Text("10 nm").tag(10.0)
                Text("25 nm").tag(25.0)
                Text("50 nm").tag(50.0)
                Text("100 nm").tag(100.0)
            }
        }
    }

    @ViewBuilder
    private var timeFilterControls: some View {
        Toggle("Active at Flight Time", isOn: timeFilterEnabledBinding)

        if appState?.notams.timeFilter.isEnabled == true,
           let route = appState?.briefing.currentBriefing?.route,
           let depTime = route.departureTime {
            Text("Departure: \(formatDateTime(depTime))")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var visibilityToggles: some View {
        Toggle("Show Read", isOn: showReadBinding)
        Toggle("Show Ignored", isOn: showIgnoredBinding)
    }

    private var groupingPicker: some View {
        Picker("Group By", selection: groupingBinding) {
            ForEach(NotamGrouping.allCases) { grouping in
                Text(grouping.rawValue).tag(grouping)
            }
        }
        .pickerStyle(.segmented)
    }

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

    private var statusFilterBinding: Binding<StatusFilter> {
        Binding(
            get: { appState?.notams.statusFilter ?? .all },
            set: { appState?.notams.statusFilter = $0 }
        )
    }

    private var rowStyleBinding: Binding<NotamRowStyle> {
        Binding(
            get: { appState?.notams.rowStyle ?? .standard },
            set: { appState?.notams.rowStyle = $0 }
        )
    }

    private func categoryBinding(_ keyPath: WritableKeyPath<CategoryFilter, Bool>) -> Binding<Bool> {
        Binding(
            get: { appState?.notams.categoryFilter[keyPath: keyPath] ?? true },
            set: { appState?.notams.categoryFilter[keyPath: keyPath] = $0 }
        )
    }

    private var routeEnabledBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.routeFilter.isEnabled ?? false },
            set: { appState?.notams.routeFilter.isEnabled = $0 }
        )
    }

    private var corridorWidthBinding: Binding<Double> {
        Binding(
            get: { appState?.notams.routeFilter.corridorWidthNm ?? 25 },
            set: { appState?.notams.routeFilter.corridorWidthNm = $0 }
        )
    }

    private var timeFilterEnabledBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.timeFilter.isEnabled ?? false },
            set: { appState?.notams.timeFilter.isEnabled = $0 }
        )
    }

    private var showReadBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.visibilityFilter.showRead ?? true },
            set: { appState?.notams.visibilityFilter.showRead = $0 }
        )
    }

    private var showIgnoredBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.visibilityFilter.showIgnored ?? false },
            set: { appState?.notams.visibilityFilter.showIgnored = $0 }
        )
    }

    private var groupingBinding: Binding<NotamGrouping> {
        Binding(
            get: { appState?.notams.grouping ?? .airport },
            set: { appState?.notams.grouping = $0 }
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
