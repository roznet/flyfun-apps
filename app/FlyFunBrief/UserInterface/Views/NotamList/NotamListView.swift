//
//  NotamListView.swift
//  FlyFunBrief
//
//  Displays the list of NOTAMs with grouping and filtering.
//

import SwiftUI
import RZFlight

/// Main NOTAM list view with grouping support
struct NotamListView: View {
    @Environment(\.appState) private var appState
    @State private var isSearchActive = false
    @FocusState private var isSearchFocused: Bool

    /// Track collapsed sections (expanded by default)
    @State private var collapsedSections: Set<String> = []

    var body: some View {
        Group {
            if let notams = appState?.notams, notams.allNotams.isEmpty {
                emptyState
            } else {
                notamList
            }
        }
        .overlay(alignment: .bottom) {
            floatingControls
        }
    }

    // MARK: - Floating Controls

    @ViewBuilder
    private var floatingControls: some View {
        let hasQuery = !(appState?.notams.searchQuery ?? "").isEmpty

        if isSearchActive || hasQuery {
            // Expanded search bar
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search NOTAMs", text: searchBinding)
                    .focused($isSearchFocused)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                if hasQuery {
                    Button {
                        appState?.notams.searchQuery = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                Button("Done") {
                    isSearchFocused = false
                    if !hasQuery {
                        isSearchActive = false
                    }
                }
                .font(.subheadline.weight(.medium))
            }
            .padding(10)
            .background(.bar, in: RoundedRectangle(cornerRadius: 12))
            .padding(.horizontal)
            .padding(.bottom, 8)
            .shadow(color: .black.opacity(0.1), radius: 4, y: 2)
            .transition(.move(edge: .bottom).combined(with: .opacity))
        } else {
            // Collapsed: row style + search buttons
            HStack(spacing: 12) {
                rowStyleButton
                searchButton
            }
            .padding(.bottom, 12)
            .transition(.scale.combined(with: .opacity))
        }
    }

    // MARK: - Row Style Button

    @ViewBuilder
    private var rowStyleButton: some View {
        let currentStyle = appState?.notams.rowStyle ?? .standard

        Menu {
            ForEach(NotamRowStyle.allCases) { style in
                Button {
                    appState?.notams.rowStyle = style
                } label: {
                    Label(style.rawValue, systemImage: style == currentStyle ? "checkmark" : "")
                }
            }
        } label: {
            Image(systemName: rowStyleIcon)
                .font(.body.weight(.medium))
                .padding(12)
                .background(.bar, in: Circle())
                .shadow(color: .black.opacity(0.15), radius: 4, y: 2)
        }
    }

    private var rowStyleIcon: String {
        switch appState?.notams.rowStyle ?? .standard {
        case .compact: return "rectangle.compress.vertical"
        case .standard: return "rectangle.split.1x2"
        case .full: return "rectangle.expand.vertical"
        }
    }

    // MARK: - Search Button

    @ViewBuilder
    private var searchButton: some View {
        Button {
            withAnimation {
                isSearchActive = true
            }
            isSearchFocused = true
        } label: {
            Image(systemName: "magnifyingglass")
                .font(.body.weight(.medium))
                .padding(12)
                .background(.bar, in: Circle())
                .shadow(color: .black.opacity(0.15), radius: 4, y: 2)
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        ContentUnavailableView {
            Label("No NOTAMs", systemImage: "doc.text")
        } description: {
            Text("Import a briefing to see NOTAMs.")
        }
    }

    // MARK: - NOTAM List

    @ViewBuilder
    private var notamList: some View {
        let grouping = appState?.notams.grouping ?? .airport
        let filteredNotams = appState?.notams.filteredEnrichedNotams ?? []

        if filteredNotams.isEmpty {
            ContentUnavailableView.search
        } else {
            List(selection: selectedNotamBinding) {
                switch grouping {
                case .none:
                    flatList(filteredNotams)
                case .airport:
                    airportGroupedList
                case .category:
                    categoryGroupedList
                case .routeOrder:
                    routeOrderGroupedList
                }
            }
            .listStyle(.insetGrouped)
            .contentMargins(.bottom, 60, for: .scrollContent)
        }
    }

    // MARK: - Flat List

    @ViewBuilder
    private func flatList(_ notams: [EnrichedNotam]) -> some View {
        ForEach(notams, id: \.notamId) { enrichedNotam in
            NotamRowView(enrichedNotam: enrichedNotam)
                .tag(enrichedNotam.notamId)
        }
    }

    // MARK: - Airport Grouped

    @ViewBuilder
    private var airportGroupedList: some View {
        let grouped = appState?.notams.enrichedNotamsGroupedByAirport ?? [:]
        let sortedKeys = grouped.keys.sorted()

        ForEach(sortedKeys, id: \.self) { airport in
            let isIgnored = appState?.notams.isAirportIgnored(airport) ?? false
            Section(isExpanded: sectionExpandedBinding(for: airport)) {
                if let notams = grouped[airport] {
                    ForEach(notams, id: \.notamId) { enrichedNotam in
                        NotamRowView(enrichedNotam: enrichedNotam)
                            .tag(enrichedNotam.notamId)
                    }
                }
            } header: {
                NotamSectionHeader(title: airport, count: grouped[airport]?.count ?? 0, isExpanded: sectionExpandedBinding(for: airport), isIgnored: isIgnored)
                    .contextMenu {
                        if isIgnored {
                            Button {
                                Task {
                                    await appState?.notams.removeAirportFromIgnoreList(airport)
                                }
                            } label: {
                                Label("Show \(airport) NOTAMs", systemImage: "eye")
                            }
                        } else {
                            Button(role: .destructive) {
                                Task {
                                    await appState?.notams.addAirportToIgnoreList(airport)
                                }
                            } label: {
                                Label("Ignore All \(airport) NOTAMs", systemImage: "eye.slash")
                            }
                        }
                    }
            }
        }
    }

    // MARK: - Category Grouped

    @ViewBuilder
    private var categoryGroupedList: some View {
        let grouped = appState?.notams.enrichedNotamsGroupedByCategory ?? [:]
        let sortedKeys = grouped.keys.sorted { $0.displayName < $1.displayName }

        ForEach(sortedKeys, id: \.self) { category in
            Section(isExpanded: sectionExpandedBinding(for: category.displayName)) {
                if let notams = grouped[category] {
                    ForEach(notams, id: \.notamId) { enrichedNotam in
                        NotamRowView(enrichedNotam: enrichedNotam)
                            .tag(enrichedNotam.notamId)
                    }
                }
            } header: {
                NotamSectionHeader(title: category.displayName, count: grouped[category]?.count ?? 0, isExpanded: sectionExpandedBinding(for: category.displayName))
            }
        }
    }

    // MARK: - Route Order Grouped

    @ViewBuilder
    private var routeOrderGroupedList: some View {
        let grouped = appState?.notams.enrichedNotamsGroupedByRouteSegment ?? []

        ForEach(grouped, id: \.segment) { item in
            Section(isExpanded: sectionExpandedBinding(for: item.segment.displayName)) {
                ForEach(item.notams, id: \.notamId) { enrichedNotam in
                    NotamRowView(enrichedNotam: enrichedNotam)
                        .tag(enrichedNotam.notamId)
                }
            } header: {
                RouteSegmentHeader(segment: item.segment, count: item.notams.count, isExpanded: sectionExpandedBinding(for: item.segment.displayName))
            }
        }
    }

    // MARK: - Section Expansion

    /// Creates a binding for section expanded state (true = expanded, false = collapsed)
    private func sectionExpandedBinding(for key: String) -> Binding<Bool> {
        Binding(
            get: { !collapsedSections.contains(key) },
            set: { isExpanded in
                if isExpanded {
                    collapsedSections.remove(key)
                } else {
                    collapsedSections.insert(key)
                }
            }
        )
    }

    // MARK: - Bindings

    private var searchBinding: Binding<String> {
        Binding(
            get: { appState?.notams.searchQuery ?? "" },
            set: { appState?.notams.searchQuery = $0 }
        )
    }

    private var selectedNotamBinding: Binding<String?> {
        Binding(
            get: { appState?.notams.selectedNotam?.id },
            set: { id in
                if let id, let notam = appState?.notams.allNotams.first(where: { $0.id == id }) {
                    appState?.notams.selectedNotam = notam

                    // Mark as read when selected
                    if appState?.settings.autoMarkAsRead == true {
                        appState?.notams.markAsRead(notam)
                    }

                    // On iPhone, present detail as sheet
                    // On iPad, NavigationSplitView handles it automatically via the detail column
                    // Note: We use userInterfaceIdiom instead of horizontalSizeClass because
                    // the content column in NavigationSplitView can report .compact even on iPad
                    if UIDevice.current.userInterfaceIdiom == .phone {
                        appState?.navigation.showNotamDetail(notamId: id)
                    }
                }
            }
        )
    }
}

// MARK: - Section Headers

struct NotamSectionHeader: View {
    let title: String
    let count: Int
    @Binding var isExpanded: Bool
    var isIgnored: Bool = false

    var body: some View {
        Button {
            withAnimation {
                isExpanded.toggle()
            }
        } label: {
            HStack {
                Text(title)
                    .font(.headline)
                    .strikethrough(isIgnored)
                if isIgnored {
                    Image(systemName: "eye.slash")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text("\(count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(.fill.tertiary, in: Capsule())
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .rotationEffect(.degrees(isExpanded ? 90 : 0))
            }
            .opacity(isIgnored ? 0.6 : 1.0)
        }
        .buttonStyle(.plain)
    }
}

struct RouteSegmentHeader: View {
    let segment: NotamRouteClassification.RouteSegment
    let count: Int
    @Binding var isExpanded: Bool

    var body: some View {
        Button {
            withAnimation {
                isExpanded.toggle()
            }
        } label: {
            HStack {
                Image(systemName: segment.icon)
                    .foregroundStyle(segmentColor)
                Text(segment.displayName)
                    .font(.headline)
                Spacer()
                Text("\(count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(.fill.tertiary, in: Capsule())
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .rotationEffect(.degrees(isExpanded ? 90 : 0))
            }
        }
        .buttonStyle(.plain)
    }

    private var segmentColor: Color {
        switch segment {
        case .departure: return .green
        case .enRoute: return .blue
        case .destination: return .orange
        case .alternates: return .purple
        case .distant: return .gray
        case .noCoordinate: return .secondary
        }
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        NotamListView()
    }
    .environment(\.appState, AppState.preview())
}
