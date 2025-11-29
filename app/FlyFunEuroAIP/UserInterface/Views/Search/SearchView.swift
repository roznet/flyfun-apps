//
//  SearchView.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import SwiftUI
import RZFlight

/// Search view for finding airports by ICAO, name, or route
struct SearchView: View {
    @Environment(\.appState) private var state
    @State private var searchText = ""
    @FocusState private var isSearchFocused: Bool
    
    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            searchBar
            
            // Content
            if searchText.isEmpty {
                recentAndSuggestions
            } else if state?.airports.isSearching == true {
                loadingView
            } else if searchResults.isEmpty {
                emptyResultsView
            } else {
                searchResultsList
            }
        }
    }
    
    // MARK: - Search Bar
    
    private var searchBar: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
            
            TextField("Search airports or route (e.g., EGTF LFMD)", text: $searchText)
                .textFieldStyle(.plain)
                .focused($isSearchFocused)
                .autocorrectionDisabled()
                #if os(iOS)
                .textInputAutocapitalization(.characters)
                #endif
                .onSubmit {
                    performSearch()
                }
                .onChange(of: searchText) { _, newValue in
                    // Debounced search
                    Task {
                        try? await Task.sleep(for: .milliseconds(300))
                        if searchText == newValue {
                            performSearch()
                        }
                    }
                }
            
            if !searchText.isEmpty {
                Button {
                    searchText = ""
                    state?.airports.searchResults = []
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(.ultraThinMaterial)
    }
    
    // MARK: - Results List
    
    private var searchResultsList: some View {
        List {
            // Route result section
            if isRouteQuery(searchText) {
                routeSection
            }
            
            // Airport results
            Section {
                ForEach(searchResults, id: \.icao) { airport in
                    AirportSearchRow(airport: airport) {
                        selectAirport(airport)
                    }
                }
            } header: {
                if !searchResults.isEmpty {
                    Text("\(searchResults.count) airports found")
                }
            }
        }
        .listStyle(.plain)
    }
    
    private var routeSection: some View {
        Section {
            Button {
                // Search as route
                Task {
                    try? await state?.airports.search(query: searchText)
                }
            } label: {
                HStack {
                    Image(systemName: "point.topLeft.down.to.point.bottomright.curvepath")
                        .foregroundStyle(.blue)
                    
                    VStack(alignment: .leading) {
                        Text("Search as Route")
                            .font(.headline)
                        Text("Find airports along \(searchText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    
                    Spacer()
                    
                    Image(systemName: "chevron.right")
                        .foregroundStyle(.secondary)
                }
            }
            .foregroundStyle(.primary)
        } header: {
            Text("Route Search")
        }
    }
    
    // MARK: - Recent & Suggestions
    
    private var recentAndSuggestions: some View {
        List {
            // Quick filters
            Section {
                quickFilterButton(title: "Border Crossings", icon: "airplane.departure") {
                    state?.airports.filters.pointOfEntry = true
                    Task { try? await state?.airports.applyFilters() }
                }
                
                quickFilterButton(title: "IFR Airports", icon: "airplane.circle") {
                    state?.airports.filters.hasProcedures = true
                    Task { try? await state?.airports.applyFilters() }
                }
                
                quickFilterButton(title: "Large Airports (8000ft+)", icon: "road.lanes") {
                    state?.airports.filters.minRunwayLengthFt = 8000
                    Task { try? await state?.airports.applyFilters() }
                }
            } header: {
                Text("Quick Filters")
            }
            
            // Example searches
            Section {
                exampleSearchButton("EGLL", description: "London Heathrow")
                exampleSearchButton("LFPG", description: "Paris CDG")
                exampleSearchButton("EGTF LFMD", description: "Fairoaks to Cannes")
            } header: {
                Text("Examples")
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
    }
    
    private func quickFilterButton(title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Image(systemName: icon)
                    .foregroundStyle(.blue)
                    .frame(width: 24)
                Text(title)
                Spacer()
                Image(systemName: "chevron.right")
                    .foregroundStyle(.secondary)
            }
        }
        .foregroundStyle(.primary)
    }
    
    private func exampleSearchButton(_ query: String, description: String) -> some View {
        Button {
            searchText = query
            performSearch()
        } label: {
            HStack {
                VStack(alignment: .leading) {
                    Text(query)
                        .font(.headline.monospaced())
                    Text(description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
        }
        .foregroundStyle(.primary)
    }
    
    // MARK: - Empty & Loading
    
    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
            Text("Searching...")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var emptyResultsView: some View {
        ContentUnavailableView {
            Label("No Results", systemImage: "magnifyingglass")
        } description: {
            Text("No airports found for \"\(searchText)\"")
        } actions: {
            if isRouteQuery(searchText) {
                Button("Try as Route Search") {
                    Task {
                        try? await state?.airports.search(query: searchText)
                    }
                }
            }
        }
    }
    
    // MARK: - Helpers
    
    private var searchResults: [RZFlight.Airport] {
        state?.airports.searchResults ?? []
    }
    
    private func performSearch() {
        guard !searchText.isEmpty else { return }
        Task {
            try? await state?.airports.search(query: searchText)
        }
    }
    
    private func selectAirport(_ airport: RZFlight.Airport) {
        state?.airports.select(airport)
        isSearchFocused = false
    }
    
    private func isRouteQuery(_ query: String) -> Bool {
        let parts = query.uppercased().split(separator: " ")
        return parts.count >= 2 &&
               parts.allSatisfy { $0.count == 4 && $0.allSatisfy { $0.isLetter } }
    }
}

// MARK: - Airport Search Row

struct AirportSearchRow: View {
    let airport: RZFlight.Airport
    let onSelect: () -> Void
    
    var body: some View {
        Button(action: onSelect) {
            HStack {
                // Airport type indicator
                Circle()
                    .fill(airport.hasInstrumentProcedures ? .blue : .orange)
                    .frame(width: 10, height: 10)
                
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(airport.icao)
                            .font(.headline.monospaced())
                        
                        if airport.hasInstrumentProcedures {
                            Text("IFR")
                                .font(.caption2.bold())
                                .foregroundStyle(.white)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(.blue, in: Capsule())
                        }
                    }
                    
                    Text(airport.name)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    
                    if !airport.city.isEmpty || !airport.country.isEmpty {
                        Text("\(airport.city), \(airport.country)")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
                
                Spacer()
                
                Image(systemName: "chevron.right")
                    .foregroundStyle(.secondary)
            }
        }
        .foregroundStyle(.primary)
    }
}

// MARK: - Preview

#Preview {
    SearchView()
}

