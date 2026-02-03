//
//  SharedFilterContent.swift
//  FlyFunBrief
//
//  Shared filter content views used by both iPhone (sheet) and iPad (sidebar).
//

import SwiftUI
import RZFlight

// MARK: - Filter Content Container

/// Container for all filter sections - use in both iPhone sheet and iPad sidebar
struct FilterSectionsContent: View {
    @Environment(\.appState) private var appState

    /// Track expanded state for advanced filter sections
    @Binding var isRouteExpanded: Bool
    @Binding var isTimeExpanded: Bool
    @Binding var isSmartFiltersExpanded: Bool
    @Binding var isCategoryExpanded: Bool
    @Binding var isPriorityExpanded: Bool

    var body: some View {
        // MARK: - Quick Access (Top)
        FilterStatusSection()
        FilterGroupingSection()
        FilterVisibilitySection()

        // MARK: - Advanced Filters (Collapsible)
        FilterAdvancedSection(
            isRouteExpanded: $isRouteExpanded,
            isTimeExpanded: $isTimeExpanded,
            isSmartFiltersExpanded: $isSmartFiltersExpanded,
            isCategoryExpanded: $isCategoryExpanded,
            isPriorityExpanded: $isPriorityExpanded
        )
    }
}

// MARK: - Status Section

struct FilterStatusSection: View {
    @Environment(\.appState) private var appState

    var body: some View {
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

    private var statusFilterBinding: Binding<StatusFilter> {
        Binding(
            get: { appState?.notams.statusFilter ?? .all },
            set: { appState?.notams.statusFilter = $0 }
        )
    }
}

// MARK: - Grouping Section

struct FilterGroupingSection: View {
    @Environment(\.appState) private var appState

    var body: some View {
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

    private var groupingBinding: Binding<NotamGrouping> {
        Binding(
            get: { appState?.notams.grouping ?? .airport },
            set: { appState?.notams.grouping = $0 }
        )
    }
}

// MARK: - Visibility Section

struct FilterVisibilitySection: View {
    @Environment(\.appState) private var appState

    var body: some View {
        Section {
            Toggle("Show Read", isOn: showReadBinding)
            Toggle("Show Ignored", isOn: showIgnoredBinding)
        } header: {
            Label("Visibility", systemImage: "eye")
        }
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
}

// MARK: - Advanced Filters Section

struct FilterAdvancedSection: View {
    @Environment(\.appState) private var appState

    @Binding var isRouteExpanded: Bool
    @Binding var isTimeExpanded: Bool
    @Binding var isSmartFiltersExpanded: Bool
    @Binding var isCategoryExpanded: Bool
    @Binding var isPriorityExpanded: Bool

    var body: some View {
        Section {
            // Priority filter
            DisclosureGroup(isExpanded: $isPriorityExpanded) {
                FilterPriorityContent()
            } label: {
                advancedFilterLabel(
                    title: "Priority",
                    icon: "bolt.fill",
                    isActive: appState?.notams.priorityFilter.isActive == true
                )
            }

            // Route corridor filter
            DisclosureGroup(isExpanded: $isRouteExpanded) {
                FilterRouteContent()
            } label: {
                advancedFilterLabel(
                    title: "Route Corridor",
                    icon: "point.topleft.down.to.point.bottomright.curvepath",
                    isActive: appState?.notams.routeFilter.isEnabled == true
                )
            }

            // Time filter
            DisclosureGroup(isExpanded: $isTimeExpanded) {
                FilterTimeContent()
            } label: {
                advancedFilterLabel(
                    title: "Time Filter",
                    icon: "clock",
                    isActive: appState?.notams.timeFilter.isEnabled == true
                )
            }

            // Smart filters
            DisclosureGroup(isExpanded: $isSmartFiltersExpanded) {
                FilterSmartContent()
            } label: {
                advancedFilterLabel(
                    title: "Smart Filters",
                    icon: "sparkles",
                    isActive: appState?.notams.smartFilters.hasActiveFilters == true
                )
            }

            // ICAO Categories
            DisclosureGroup(isExpanded: $isCategoryExpanded) {
                FilterCategoryContent()
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
}

// MARK: - Priority Content

struct FilterPriorityContent: View {
    @Environment(\.appState) private var appState

    private var profile: PriorityProfile {
        appState?.notams.currentProfile ?? PriorityProfiles.default
    }

    private var counts: [Int: Int] {
        appState?.notams.priorityCountsByLevel ?? [:]
    }

    var body: some View {
        // Profile picker
        Picker("Profile", selection: profileBinding) {
            ForEach(PriorityProfiles.all) { p in
                Text(p.displayName).tag(p.id)
            }
        }
        .pickerStyle(.segmented)

        // Cumulative level filter buttons
        HStack(spacing: 6) {
            levelButton(label: "All", level: nil)
            ForEach(Array(profile.levels), id: \.self) { level in
                let priority = NotamPriority(level: level, maxLevel: profile.maxLevel)
                levelButton(label: priority.label, level: level, color: priority.color, count: counts[level] ?? 0)
            }
        }

        // Level descriptions
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(profile.levels), id: \.self) { level in
                if let desc = profile.levelDescriptions[level] {
                    HStack(alignment: .top, spacing: 6) {
                        let priority = NotamPriority(level: level, maxLevel: profile.maxLevel)
                        Text(priority.label)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(priority.color)
                            .frame(width: 24, alignment: .leading)
                        Text(desc)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(.top, 4)

        Text("Priority computed from route distance, altitude, and NOTAM type.")
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    @ViewBuilder
    private func levelButton(label: String, level: Int?, color: Color = .primary, count: Int = 0) -> some View {
        let isSelected = appState?.notams.priorityFilter.maxVisibleLevel == level
        Button {
            appState?.notams.priorityFilter.maxVisibleLevel = level
        } label: {
            VStack(spacing: 2) {
                Text(label)
                    .font(.caption.weight(.medium))
                if level != nil && count > 0 {
                    Text("\(count)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
            .background(isSelected ? color.opacity(0.2) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? color : .secondary.opacity(0.3), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .foregroundStyle(isSelected ? color : .primary)
    }

    private var profileBinding: Binding<String> {
        Binding(
            get: { appState?.settings.priorityProfileId ?? PriorityProfiles.default.id },
            set: { appState?.settings.priorityProfileId = $0 }
        )
    }
}

// MARK: - Route Content

struct FilterRouteContent: View {
    @Environment(\.appState) private var appState

    var body: some View {
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
}

// MARK: - Time Content

struct FilterTimeContent: View {
    @Environment(\.appState) private var appState

    var body: some View {
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

    private var timeEnabledBinding: Binding<Bool> {
        Binding(
            get: { appState?.notams.timeFilter.isEnabled ?? false },
            set: { appState?.notams.timeFilter.isEnabled = $0 }
        )
    }
}

// MARK: - Smart Filters Content

struct FilterSmartContent: View {
    @Environment(\.appState) private var appState

    var body: some View {
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

// MARK: - Category Content

struct FilterCategoryContent: View {
    @Environment(\.appState) private var appState

    var body: some View {
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

    private func categoryBinding(_ keyPath: WritableKeyPath<CategoryFilter, Bool>) -> Binding<Bool> {
        Binding(
            get: { appState?.notams.categoryFilter[keyPath: keyPath] ?? true },
            set: { appState?.notams.categoryFilter[keyPath: keyPath] = $0 }
        )
    }
}
