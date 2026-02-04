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

    var body: some View {
        Group {
            if let notams = appState?.notams, notams.allNotams.isEmpty {
                emptyState
            } else {
                notamList
            }
        }
        .overlay(alignment: .bottom) {
            floatingSearchBar
        }
    }

    // MARK: - Floating Search Bar

    @ViewBuilder
    private var floatingSearchBar: some View {
        let hasQuery = !(appState?.notams.searchQuery ?? "").isEmpty

        if isSearchActive || hasQuery {
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
            .padding(.bottom, 12)
            .transition(.scale.combined(with: .opacity))
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
            Section {
                if let notams = grouped[airport] {
                    ForEach(notams, id: \.notamId) { enrichedNotam in
                        NotamRowView(enrichedNotam: enrichedNotam)
                            .tag(enrichedNotam.notamId)
                    }
                }
            } header: {
                NotamSectionHeader(title: airport, count: grouped[airport]?.count ?? 0)
            }
        }
    }

    // MARK: - Category Grouped

    @ViewBuilder
    private var categoryGroupedList: some View {
        let grouped = appState?.notams.enrichedNotamsGroupedByCategory ?? [:]
        let sortedKeys = grouped.keys.sorted { $0.displayName < $1.displayName }

        ForEach(sortedKeys, id: \.self) { category in
            Section {
                if let notams = grouped[category] {
                    ForEach(notams, id: \.notamId) { enrichedNotam in
                        NotamRowView(enrichedNotam: enrichedNotam)
                            .tag(enrichedNotam.notamId)
                    }
                }
            } header: {
                NotamSectionHeader(title: category.displayName, count: grouped[category]?.count ?? 0)
            }
        }
    }

    // MARK: - Route Order Grouped

    @ViewBuilder
    private var routeOrderGroupedList: some View {
        let grouped = appState?.notams.enrichedNotamsGroupedByRouteSegment ?? []

        ForEach(grouped, id: \.segment) { item in
            Section {
                ForEach(item.notams, id: \.notamId) { enrichedNotam in
                    NotamRowView(enrichedNotam: enrichedNotam)
                        .tag(enrichedNotam.notamId)
                }
            } header: {
                RouteSegmentHeader(segment: item.segment, count: item.notams.count)
            }
        }
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

    var body: some View {
        HStack {
            Text(title)
                .font(.headline)
            Spacer()
            Text("\(count)")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(.fill.tertiary, in: Capsule())
        }
    }
}

struct RouteSegmentHeader: View {
    let segment: NotamRouteClassification.RouteSegment
    let count: Int

    var body: some View {
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
        }
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
