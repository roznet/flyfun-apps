//
//  FilterPanelView.swift
//  FlyFunBrief
//
//  Smart filter panel for NOTAM filtering with route corridor support.
//  Uses shared filter content from SharedFilterContent.swift.
//

import SwiftUI
import RZFlight

/// Panel for configuring NOTAM filters (iPhone sheet presentation)
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
                FilterSectionsContent(
                    isRouteExpanded: $isRouteExpanded,
                    isTimeExpanded: $isTimeExpanded,
                    isSmartFiltersExpanded: $isSmartFiltersExpanded,
                    isCategoryExpanded: $isCategoryExpanded,
                    isPriorityExpanded: $isPriorityExpanded
                )
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
        if appState?.notams.priorityFilter.isActive == true {
            isPriorityExpanded = true
        }
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

                if let chipLabel = appState?.notams.priorityFilter.chipLabel {
                    let profileName = appState?.notams.currentProfile.displayName ?? ""
                    FilterChip(
                        label: "\(profileName) \(chipLabel)",
                        isActive: true
                    ) {
                        appState?.notams.priorityFilter.maxVisibleLevel = nil
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
