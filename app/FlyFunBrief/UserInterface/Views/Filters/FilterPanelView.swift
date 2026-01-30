//
//  FilterPanelView.swift
//  FlyFunBrief
//
//  Smart filter panel for NOTAM filtering with route corridor support.
//

import SwiftUI
import RZFlight

/// Panel for configuring NOTAM filters
///
/// Organized with most-used filters at top:
/// - Status tabs and grouping options prominently displayed
/// - Advanced filters (route, time, categories) in collapsible sections
struct FilterPanelView: View {
    @Environment(\.appState) private var appState
    @Environment(\.dismiss) private var dismiss

    /// Track expanded state for advanced filter sections
    @State private var isRouteExpanded = false
    @State private var isTimeExpanded = false
    @State private var isSmartFiltersExpanded = false
    @State private var isCategoryExpanded = false
    @State private var isPriorityExpanded = false

    var body: some View {
        NavigationStack {
            Form {
                // MARK: - Quick Access (Top)
                // Status and grouping are the most used - always visible at top
                statusSection
                groupingSection
                visibilitySection

                // MARK: - Advanced Filters (Collapsible)
                advancedFiltersSection
            }
            .navigationTitle("Filters")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .cancellationAction) {
                    Button("Reset") {
                        appState?.notams.resetFilters()
                        // Reset expanded states
                        isRouteExpanded = false
                        isTimeExpanded = false
                        isSmartFiltersExpanded = false
                        isCategoryExpanded = false
                        isPriorityExpanded = false
                    }
                }
            }
            .onAppear {
                // Auto-expand sections that have active filters
                updateExpandedStates()
            }
        }
    }

    /// Auto-expand sections that have active filters
    private func updateExpandedStates() {
        if appState?.notams.routeFilter.isEnabled == true {
            isRouteExpanded = true
        }
        if appState?.notams.timeFilter.isEnabled == true {
            isTimeExpanded = true
        }
        if appState?.notams.smartFilters.hasActiveFilters == true {
            isSmartFiltersExpanded = true
        }
        if appState?.notams.categoryFilter.allEnabled == false {
            isCategoryExpanded = true
        }
        if appState?.notams.priorityFilter != .all {
            isPriorityExpanded = true
        }
    }

    // MARK: - Route Content (for DisclosureGroup)

    @ViewBuilder
    private var routeContent: some View {
        Toggle("Filter by Route", isOn: routeEnabledBinding)

        if appState?.notams.routeFilter.isEnabled == true {
            TextField("ICAO codes (e.g., LFPG EGLL)", text: routeStringBinding)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .font(.body.monospaced())

            VStack(alignment: .leading, spacing: 8) {
                Text("Corridor Width: \(Int(appState?.notams.routeFilter.corridorWidthNm ?? 25)) nm")
                    .font(.subheadline)

                Picker("Distance", selection: corridorWidthBinding) {
                    Text("10 nm").tag(10.0)
                    Text("25 nm").tag(25.0)
                    Text("50 nm").tag(50.0)
                    Text("100 nm").tag(100.0)
                }
                .pickerStyle(.segmented)
            }

            if let codes = appState?.notams.routeFilter.icaoCodes, !codes.isEmpty {
                HStack {
                    Text("Route:")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(codes.joined(separator: " → "))
                        .font(.caption.monospaced())
                }
            }
        }

        Text("Show only NOTAMs within the corridor distance of your route.")
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    // MARK: - Time Content (for DisclosureGroup)

    @ViewBuilder
    private var timeContent: some View {
        Toggle("Active at Flight Time", isOn: timeEnabledBinding)

        if appState?.notams.timeFilter.isEnabled == true {
            if let route = appState?.briefing.currentBriefing?.route,
               let depTime = route.departureTime {
                VStack(alignment: .leading, spacing: 4) {
                    Label(formatDateTime(depTime), systemImage: "airplane.departure")
                        .font(.subheadline)
                    if let arrTime = route.arrivalTime {
                        Label(formatDateTime(arrTime), systemImage: "airplane.arrival")
                            .font(.subheadline)
                    }
                }
                .foregroundStyle(.secondary)
            } else {
                Text("No flight time available")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }

        Text("Show only NOTAMs active during flight time window.")
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    private func formatDateTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "dd MMM HH:mm 'UTC'"
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter.string(from: date)
    }

    // MARK: - Smart Filters Content (for DisclosureGroup)

    @ViewBuilder
    private var smartFiltersContent: some View {
        // Helicopter filter
        Toggle("Hide Helicopter NOTAMs", isOn: hideHelicopterBinding)

        // Obstacle filter
        Toggle("Smart Obstacle Filter", isOn: filterObstaclesBinding)

        if appState?.notams.smartFilters.filterObstacles == true {
            HStack {
                Text("Show within")
                Picker("Distance", selection: obstacleDistanceBinding) {
                    Text("1 nm").tag(1.0)
                    Text("2 nm").tag(2.0)
                    Text("5 nm").tag(5.0)
                    Text("10 nm").tag(10.0)
                }
                .pickerStyle(.menu)
                Text("of airports")
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
        }

        // Scope filter
        Picker("Scope", selection: scopeFilterBinding) {
            ForEach(ScopeFilter.allCases) { scope in
                Text(scope.rawValue).tag(scope)
            }
        }

        VStack(alignment: .leading, spacing: 4) {
            if appState?.notams.smartFilters.hideHelicopter == true {
                Text("Helicopter NOTAMs (heliports, FATO, windsocks) hidden")
            }
            if appState?.notams.smartFilters.filterObstacles == true {
                Text("Obstacles shown only near departure/destination")
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }

    // MARK: - Category Content (for DisclosureGroup)

    @ViewBuilder
    private var categoryContent: some View {
        // Enable All button
        if appState?.notams.categoryFilter.allEnabled == false {
            Button("Enable All Categories") {
                appState?.notams.categoryFilter.enableAll()
            }
            .font(.subheadline)
        }

        // AGA Categories (Aerodrome Ground Aids)
        DisclosureGroup("AGA - Ground") {
            CategoryToggleRow(label: "Movement Area", systemImage: NotamCategory.agaMovement.icon, isOn: categoryBinding(\.showMovement))
            CategoryToggleRow(label: "Lighting", systemImage: NotamCategory.agaLighting.icon, isOn: categoryBinding(\.showLighting))
            CategoryToggleRow(label: "Facilities", systemImage: NotamCategory.agaFacilities.icon, isOn: categoryBinding(\.showFacilities))
        }

        // CNS Categories (Communications, Navigation, Surveillance)
        DisclosureGroup("CNS - Navigation") {
            CategoryToggleRow(label: "Navigation", systemImage: NotamCategory.navigation.icon, isOn: categoryBinding(\.showNavigation))
            CategoryToggleRow(label: "ILS/MLS", systemImage: NotamCategory.cnsILS.icon, isOn: categoryBinding(\.showILS))
            CategoryToggleRow(label: "GNSS", systemImage: NotamCategory.cnsGNSS.icon, isOn: categoryBinding(\.showGNSS))
            CategoryToggleRow(label: "Communications", systemImage: NotamCategory.cnsCommunications.icon, isOn: categoryBinding(\.showCommunications))
        }

        // ATM Categories (Air Traffic Management)
        DisclosureGroup("ATM - Traffic") {
            CategoryToggleRow(label: "Airspace", systemImage: NotamCategory.atmAirspace.icon, isOn: categoryBinding(\.showAirspace))
            CategoryToggleRow(label: "Procedures", systemImage: NotamCategory.atmProcedures.icon, isOn: categoryBinding(\.showProcedures))
            CategoryToggleRow(label: "Services", systemImage: NotamCategory.atmServices.icon, isOn: categoryBinding(\.showServices))
            CategoryToggleRow(label: "Restrictions", systemImage: NotamCategory.airspaceRestrictions.icon, isOn: categoryBinding(\.showRestrictions))
        }

        // Other
        CategoryToggleRow(label: "Other Info", systemImage: NotamCategory.otherInfo.icon, isOn: categoryBinding(\.showOther))

        Text("Based on ICAO Q-code subject classification")
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    // MARK: - Status Section (Prominent at Top)

    private var statusSection: some View {
        Section {
            Picker("Status", selection: statusFilterBinding) {
                ForEach(StatusFilter.allCases) { status in
                    Text(status.rawValue).tag(status)
                }
            }
            .pickerStyle(.segmented)

            // Quick stats row
            if let notams = appState?.notams {
                HStack(spacing: 16) {
                    StatBadge(label: "Unread", count: notams.unreadCount, color: .blue)
                    StatBadge(label: "Important", count: notams.importantCount, color: .orange)
                    StatBadge(label: "New", count: notams.newNotamCount, color: .green)
                }
                .padding(.vertical, 4)
            }
        } header: {
            Label("Status", systemImage: "checklist")
        }
    }

    // MARK: - Priority Content (for DisclosureGroup)

    @ViewBuilder
    private var priorityContent: some View {
        Picker("Priority", selection: priorityFilterBinding) {
            ForEach(PriorityFilter.allCases) { priority in
                HStack {
                    priorityIcon(for: priority)
                    Text(priority.rawValue)
                }
                .tag(priority)
            }
        }
        .pickerStyle(.segmented)

        if appState?.notams.highPriorityCount ?? 0 > 0 {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                    .font(.caption)
                Text("\(appState?.notams.highPriorityCount ?? 0) high priority NOTAMs")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }

        Text("Computed from route distance, altitude, and NOTAM type.")
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    @ViewBuilder
    private func priorityIcon(for filter: PriorityFilter) -> some View {
        switch filter {
        case .all:
            EmptyView()
        case .high:
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
                .font(.caption2)
        case .normal:
            EmptyView()
        case .low:
            Image(systemName: "arrow.down.circle")
                .foregroundStyle(.secondary)
                .font(.caption2)
        }
    }

    // MARK: - Visibility Section

    private var visibilitySection: some View {
        Section {
            Toggle("Show Read", isOn: showReadBinding)
            Toggle("Show Ignored", isOn: showIgnoredBinding)
        } header: {
            Label("Visibility", systemImage: "eye")
        }
    }

    // MARK: - Grouping Section (Prominent at Top)

    private var groupingSection: some View {
        Section {
            Picker("Group By", selection: groupingBinding) {
                ForEach(NotamGrouping.allCases) { grouping in
                    Label(grouping.rawValue, systemImage: grouping.icon)
                        .tag(grouping)
                }
            }
            .pickerStyle(.segmented)
        } header: {
            Label("Grouping", systemImage: "rectangle.3.group")
        } footer: {
            if appState?.notams.grouping == .routeOrder {
                Text("Sorted by position along route: Departure → En Route → Destination")
            }
        }
    }

    // MARK: - Advanced Filters Section (Collapsible)

    private var advancedFiltersSection: some View {
        Section {
            // Priority filter
            DisclosureGroup(isExpanded: $isPriorityExpanded) {
                priorityContent
            } label: {
                advancedFilterLabel(
                    title: "Priority",
                    icon: "bolt.fill",
                    isActive: appState?.notams.priorityFilter != .all
                )
            }

            // Route corridor filter
            DisclosureGroup(isExpanded: $isRouteExpanded) {
                routeContent
            } label: {
                advancedFilterLabel(
                    title: "Route Corridor",
                    icon: "point.topleft.down.to.point.bottomright.curvepath",
                    isActive: appState?.notams.routeFilter.isEnabled == true
                )
            }

            // Time filter
            DisclosureGroup(isExpanded: $isTimeExpanded) {
                timeContent
            } label: {
                advancedFilterLabel(
                    title: "Time Filter",
                    icon: "clock",
                    isActive: appState?.notams.timeFilter.isEnabled == true
                )
            }

            // Smart filters
            DisclosureGroup(isExpanded: $isSmartFiltersExpanded) {
                smartFiltersContent
            } label: {
                advancedFilterLabel(
                    title: "Smart Filters",
                    icon: "sparkles",
                    isActive: appState?.notams.smartFilters.hasActiveFilters == true
                )
            }

            // ICAO Categories (lighting, facilities, etc.)
            DisclosureGroup(isExpanded: $isCategoryExpanded) {
                categoryContent
            } label: {
                advancedFilterLabel(
                    title: "ICAO Categories",
                    icon: "tag",
                    isActive: appState?.notams.categoryFilter.allEnabled == false
                )
            }
        } header: {
            Label("Advanced Filters", systemImage: "slider.horizontal.3")
        }
    }

    /// Label for advanced filter disclosure groups with active indicator
    private func advancedFilterLabel(title: String, icon: String, isActive: Bool) -> some View {
        HStack {
            Label(title, systemImage: icon)
            Spacer()
            if isActive {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.orange)
                    .font(.caption)
            }
        }
    }

    // MARK: - Bindings

    private var routeEnabledBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.routeFilter.isEnabled ?? false },
            set: { appState?.notams.routeFilter.isEnabled = $0 }
        )
    }

    private var routeStringBinding: Binding<String> {
        Binding(
            get: { appState?.notams.routeFilter.routeString ?? "" },
            set: { appState?.notams.routeFilter.routeString = $0 }
        )
    }

    private var corridorWidthBinding: Binding<Double> {
        Binding(
            get: { appState?.notams.routeFilter.corridorWidthNm ?? 25 },
            set: { appState?.notams.routeFilter.corridorWidthNm = $0 }
        )
    }

    private var timeEnabledBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.timeFilter.isEnabled ?? false },
            set: { appState?.notams.timeFilter.isEnabled = $0 }
        )
    }

    private func categoryBinding(_ keyPath: WritableKeyPath<CategoryFilter, Bool>) -> Binding<Bool> {
        Binding(
            get: { appState?.notams.categoryFilter[keyPath: keyPath] ?? true },
            set: { appState?.notams.categoryFilter[keyPath: keyPath] = $0 }
        )
    }

    private var statusFilterBinding: Binding<StatusFilter> {
        Binding(
            get: { appState?.notams.statusFilter ?? .all },
            set: { appState?.notams.statusFilter = $0 }
        )
    }

    private var priorityFilterBinding: Binding<PriorityFilter> {
        Binding(
            get: { appState?.notams.priorityFilter ?? .all },
            set: { appState?.notams.priorityFilter = $0 }
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

    // MARK: - Smart Filter Bindings

    private var hideHelicopterBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.smartFilters.hideHelicopter ?? true },
            set: { appState?.notams.smartFilters.hideHelicopter = $0 }
        )
    }

    private var filterObstaclesBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.smartFilters.filterObstacles ?? true },
            set: { appState?.notams.smartFilters.filterObstacles = $0 }
        )
    }

    private var obstacleDistanceBinding: Binding<Double> {
        Binding(
            get: { appState?.notams.smartFilters.obstacleDistanceNm ?? 2.0 },
            set: { appState?.notams.smartFilters.obstacleDistanceNm = $0 }
        )
    }

    private var scopeFilterBinding: Binding<ScopeFilter> {
        Binding(
            get: { appState?.notams.smartFilters.scopeFilter ?? .all },
            set: { appState?.notams.smartFilters.scopeFilter = $0 }
        )
    }
}

// MARK: - Category Toggle Row

struct CategoryToggleRow: View {
    let label: String
    let systemImage: String
    @Binding var isOn: Bool

    var body: some View {
        Toggle(isOn: $isOn) {
            Label(label, systemImage: systemImage)
        }
    }
}

// MARK: - Compact Filter Bar (for inline use)

struct CompactFilterBar: View {
    @Environment(\.appState) private var appState

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // Active filter chips
                if appState?.notams.routeFilter.isEnabled == true {
                    FilterChip(
                        label: "Route: \(Int(appState?.notams.routeFilter.corridorWidthNm ?? 25))nm",
                        isActive: true
                    ) {
                        appState?.notams.routeFilter.isEnabled = false
                    }
                }

                if appState?.notams.statusFilter != .all {
                    FilterChip(
                        label: appState?.notams.statusFilter.rawValue ?? "",
                        isActive: true
                    ) {
                        appState?.notams.statusFilter = .all
                    }
                }

                if appState?.notams.priorityFilter != .all {
                    FilterChip(
                        label: "Priority: \(appState?.notams.priorityFilter.rawValue ?? "")",
                        isActive: true
                    ) {
                        appState?.notams.priorityFilter = .all
                    }
                }

                if appState?.notams.categoryFilter.allEnabled == false {
                    FilterChip(
                        label: "Categories",
                        isActive: true
                    ) {
                        appState?.notams.categoryFilter.enableAll()
                    }
                }
            }
            .padding(.horizontal)
        }
    }
}

struct FilterChip: View {
    let label: String
    let isActive: Bool
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.caption)

            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
                    .font(.caption)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(isActive ? Color.accentColor.opacity(0.2) : Color.secondary.opacity(0.1))
        .foregroundStyle(isActive ? .primary : .secondary)
        .clipShape(Capsule())
    }
}

// MARK: - Stat Badge

/// Small badge displaying a count with label for the status section
struct StatBadge: View {
    let label: String
    let count: Int
    let color: Color

    var body: some View {
        VStack(spacing: 2) {
            Text("\(count)")
                .font(.headline)
                .foregroundStyle(count > 0 ? color : .secondary)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Preview

#Preview {
    FilterPanelView()
        .environment(\.appState, AppState.preview())
}
