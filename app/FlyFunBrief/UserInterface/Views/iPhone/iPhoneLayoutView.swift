//
//  iPhoneLayoutView.swift
//  FlyFunBrief
//
//  iPhone layout with tab bar navigation.
//

import SwiftUI
import RZFlight

/// iPhone layout with compact NOTAM list and tab navigation
struct iPhoneLayoutView: View {
    @Environment(\.appState) private var appState

    var body: some View {
        Group {
            if appState?.navigation.isViewingFlight == true {
                // Flight view mode - show NOTAM list with navigation
                FlightNotamView()
            } else {
                // Tab navigation mode
                tabNavigationView
            }
        }
        .sheet(item: sheetBinding) { sheet in
            sheetContent(for: sheet)
        }
    }

    // MARK: - Tab Navigation View

    private var tabNavigationView: some View {
        TabView(selection: tabBinding) {
            FlightsTab()
                .tabItem {
                    Label("Flights", systemImage: "airplane")
                }
                .tag(AppTab.flights)

            IgnoredTab()
                .tabItem {
                    Label("Ignored", systemImage: "xmark.circle")
                }
                .tag(AppTab.ignored)

            SettingsTab()
                .tabItem {
                    Label("Settings", systemImage: "gearshape")
                }
                .tag(AppTab.settings)
        }
    }

    // MARK: - Bindings

    private var tabBinding: Binding<AppTab> {
        Binding(
            get: { appState?.navigation.selectedTab ?? .flights },
            set: { appState?.navigation.selectedTab = $0 }
        )
    }

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
        case .notamDetail(let notamId):
            if let notam = appState?.notams.allNotams.first(where: { $0.id == notamId }) {
                NotamDetailView(notam: notam)
            }
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
}

// MARK: - Flights Tab

struct FlightsTab: View {
    var body: some View {
        NavigationStack {
            FlightListView()
        }
    }
}

// MARK: - Flight NOTAM View (when viewing a flight)

struct FlightNotamView: View {
    @Environment(\.appState) private var appState

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottomTrailing) {
                NotamListView()

                // Floating filter button for quick access
                floatingFilterButton
            }
            .navigationTitle(navigationTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        appState?.navigation.exitFlightView()
                        appState?.briefing.clearBriefing()
                        appState?.flights.clearSelection()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "chevron.left")
                            Text("Flights")
                        }
                    }
                }

                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        briefingMenu
                        Divider()
                        filterMenu
                    } label: {
                        Label("Options", systemImage: "ellipsis.circle")
                    }
                }
            }
        }
    }

    // MARK: - Floating Filter Button

    private var floatingFilterButton: some View {
        Button {
            appState?.navigation.showFilterOptions()
        } label: {
            ZStack {
                Circle()
                    .fill(Color.accentColor)
                    .frame(width: 56, height: 56)
                    .shadow(color: .black.opacity(0.2), radius: 4, x: 0, y: 2)

                Image(systemName: "slider.horizontal.3")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(.white)

                // Badge showing active filter count
                if let activeCount = activeFilterCount, activeCount > 0 {
                    Text("\(activeCount)")
                        .font(.caption2.bold())
                        .foregroundStyle(.white)
                        .padding(5)
                        .background(Color.orange)
                        .clipShape(Circle())
                        .offset(x: 18, y: -18)
                }
            }
        }
        .padding(.trailing, 16)
        .padding(.bottom, 16)
    }

    /// Count of active filters for badge display
    private var activeFilterCount: Int? {
        guard let notams = appState?.notams else { return nil }

        var count = 0
        if notams.routeFilter.isEnabled { count += 1 }
        if notams.timeFilter.isEnabled { count += 1 }
        if notams.statusFilter != .all { count += 1 }
        if notams.priorityFilter.isActive { count += 1 }
        if !notams.categoryFilter.allEnabled { count += 1 }
        if notams.smartFilters.hasActiveFilters { count += 1 }
        if !notams.visibilityFilter.showRead { count += 1 }
        if notams.visibilityFilter.showIgnored { count += 1 }

        return count
    }

    private var navigationTitle: String {
        if let flight = appState?.flights.selectedFlight {
            return "\(flight.origin ?? "") → \(flight.destination ?? "")"
        }
        return "NOTAMs"
    }

    // MARK: - Briefing Menu

    @ViewBuilder
    private var briefingMenu: some View {
        if let flight = appState?.flights.selectedFlight {
            let briefings = flight.sortedBriefings

            Section("Briefings") {
                ForEach(briefings, id: \.id) { briefing in
                    Button {
                        appState?.briefing.loadBriefing(briefing)
                    } label: {
                        HStack {
                            if briefing.isLatest {
                                Image(systemName: "star.fill")
                            }
                            Text(briefing.formattedImportDate)
                            Text("(\(briefing.notamCount))")
                            if appState?.briefing.currentCDBriefing?.id == briefing.id {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }

                Button {
                    appState?.navigation.showImportSheet()
                } label: {
                    Label("Import New Briefing", systemImage: "square.and.arrow.down")
                }
            }
        }
    }

    // MARK: - Filter Menu

    @ViewBuilder
    private var filterMenu: some View {
        Section("View Style") {
            ForEach(NotamRowStyle.allCases) { style in
                Button {
                    appState?.notams.rowStyle = style
                } label: {
                    if appState?.notams.rowStyle == style {
                        Label(style.rawValue, systemImage: "checkmark")
                    } else {
                        Text(style.rawValue)
                    }
                }
            }
        }

        Divider()

        Section("Status") {
            ForEach(StatusFilter.allCases) { status in
                Button {
                    appState?.notams.statusFilter = status
                } label: {
                    if appState?.notams.statusFilter == status {
                        Label(status.rawValue, systemImage: "checkmark")
                    } else {
                        Text(status.rawValue)
                    }
                }
            }
        }

        Divider()

        Button {
            appState?.navigation.showFilterOptions()
        } label: {
            Label("More Filters...", systemImage: "slider.horizontal.3")
        }
    }
}

// MARK: - Ignored Tab

struct IgnoredTab: View {
    var body: some View {
        NavigationStack {
            IgnoreListView()
        }
    }
}

// MARK: - Settings Tab

struct SettingsTab: View {
    var body: some View {
        NavigationStack {
            SettingsView()
                .navigationTitle("Settings")
        }
    }
}

// MARK: - Flight Picker View

struct FlightPickerView: View {
    @Environment(\.appState) private var appState
    @Environment(\.dismiss) private var dismiss

    /// Whether we have a pending briefing to assign
    private var hasPendingBriefing: Bool {
        appState?.pendingBriefing != nil
    }

    /// Route from pending briefing
    private var pendingRoute: RZFlight.Route? {
        appState?.pendingBriefing?.route
    }

    /// Route summary from pending briefing
    private var pendingRouteSummary: String? {
        guard let route = pendingRoute else { return nil }
        return "\(route.departure) → \(route.destination)"
    }

    /// Whether the briefing has origin/destination info for filtering
    private var hasRouteFilter: Bool {
        guard let route = pendingRoute else { return false }
        return !route.departure.isEmpty && !route.destination.isEmpty
    }

    /// Flights filtered by pending briefing route (if available)
    private var filteredFlights: [CDFlight] {
        guard let allFlights = appState?.flights.flights else { return [] }

        // If no pending briefing or no route filter, return all
        if !hasPendingBriefing || !hasRouteFilter {
            return allFlights
        }

        // Filter to matching origin/destination
        guard let route = pendingRoute else { return allFlights }
        let briefingOrigin = route.departure.uppercased()
        let briefingDest = route.destination.uppercased()

        return allFlights.filter { flight in
            flight.origin?.uppercased() == briefingOrigin &&
            flight.destination?.uppercased() == briefingDest
        }
    }

    /// Flights that don't match the filter (for "other flights" section)
    private var otherFlights: [CDFlight] {
        guard let allFlights = appState?.flights.flights else { return [] }
        guard hasPendingBriefing && hasRouteFilter else { return [] }

        guard let route = pendingRoute else { return [] }
        let briefingOrigin = route.departure.uppercased()
        let briefingDest = route.destination.uppercased()

        return allFlights.filter { flight in
            flight.origin?.uppercased() != briefingOrigin ||
            flight.destination?.uppercased() != briefingDest
        }
    }

    var body: some View {
        NavigationStack {
            List {
                // Show pending briefing info if present
                if hasPendingBriefing {
                    Section {
                        VStack(alignment: .leading, spacing: 4) {
                            Label("Briefing Ready to Import", systemImage: "doc.text.fill")
                                .font(.headline)
                            if let route = pendingRouteSummary {
                                Text(route)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                            Text("Select a flight or create a new one")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }

                // Matching flights (or all flights if no filter)
                if !filteredFlights.isEmpty {
                    Section(matchingSectionHeader) {
                        ForEach(filteredFlights, id: \.id) { flight in
                            Button {
                                selectFlight(flight)
                            } label: {
                                FlightRowView(flight: flight)
                            }
                        }
                    }
                } else if hasPendingBriefing && hasRouteFilter {
                    // No matching flights for this route
                    Section("Matching Flights") {
                        Text("No flights match this route")
                            .foregroundStyle(.secondary)
                    }
                } else if !hasPendingBriefing {
                    Text("No flights available")
                        .foregroundStyle(.secondary)
                }

                // Other flights (when filtering is active)
                if !otherFlights.isEmpty {
                    Section("Other Flights") {
                        ForEach(otherFlights, id: \.id) { flight in
                            Button {
                                selectFlight(flight)
                            } label: {
                                FlightRowView(flight: flight)
                            }
                        }
                    }
                }

                // Create new flight section
                Section {
                    if hasPendingBriefing {
                        // Option to create flight from briefing route
                        Button {
                            Task {
                                await appState?.createFlightFromPendingBriefing()
                            }
                        } label: {
                            Label("Create Flight from Briefing", systemImage: "plus.circle.fill")
                        }
                        .tint(.accentColor)
                    }

                    Button {
                        if hasPendingBriefing {
                            appState?.cancelPendingBriefing()
                        }
                        dismiss()
                        appState?.navigation.showNewFlight()
                    } label: {
                        Label("Create New Flight Manually", systemImage: "plus")
                    }
                }
            }
            .navigationTitle(hasPendingBriefing ? "Import Briefing" : "Select Flight")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        if hasPendingBriefing {
                            appState?.cancelPendingBriefing()
                        } else {
                            dismiss()
                        }
                    }
                }
            }
        }
    }

    /// Header for the matching flights section
    private var matchingSectionHeader: String {
        if !hasPendingBriefing {
            return ""
        }
        if hasRouteFilter {
            return "Matching Flights"
        }
        return "Existing Flights"
    }

    private func selectFlight(_ flight: CDFlight) {
        if hasPendingBriefing {
            // Assign pending briefing to this flight
            Task {
                await appState?.assignPendingBriefing(to: flight)
            }
        } else {
            // Normal flight selection
            appState?.flights.selectFlight(flight)
            dismiss()
        }
    }
}

// MARK: - Preview

#Preview {
    iPhoneLayoutView()
        .environment(\.appState, AppState.preview())
}
