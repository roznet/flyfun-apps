//
//  ContentView.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 26/10/2025.
//

import SwiftUI
import MapKit
import RZFlight

struct ContentView: View {
    @Environment(\.appState) private var state
    @Environment(\.horizontalSizeClass) private var sizeClass
    
    var body: some View {
        Group {
            if isRegularWidth {
                RegularLayout()
            } else {
                CompactLayout()
            }
        }
        .sheet(isPresented: filterSheetBinding) {
            FilterPanelView()
                .presentationDetents([.medium, .large])
        }
        // Search and Chat sheets (iPhone only - compact size class)
        .sheet(isPresented: searchSheetBinding) {
            NavigationStack {
                SearchView()
                    .navigationTitle("Search Airports")
                    .navigationBarTitleDisplayMode(.large)
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                state?.navigation.hideSearchSheet()
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
            }
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
        .onChange(of: state?.airports.selectedAirport) { _, newValue in
            // Auto-close search sheet on iPhone when airport is selected
            if !isRegularWidth && newValue != nil {
                state?.navigation.hideSearchSheet()
            }
        }
        .sheet(isPresented: chatSheetBinding) {
            NavigationStack {
                ChatView()
            }
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
        .overlay {
            // Error banner
            if let error = state?.system.error {
                VStack {
                    ErrorBanner(error: error) {
                        state?.system.clearError()
                    }
                    Spacer()
                }
            }
            
            // Offline banner
            if state?.system.connectivityMode == .offline && state?.settings.showOfflineBanner == true {
                VStack {
                    OfflineBanner()
                    Spacer()
                }
                .padding(.top, 50)  // Below error banner if both showing
            }
        }
    }
    
    // MARK: - Computed Properties
    
    private var isRegularWidth: Bool {
        sizeClass == .regular
    }
    
    private var filterSheetBinding: Binding<Bool> {
        Binding(
            get: { state?.navigation.showingFilters ?? false },
            set: { state?.navigation.showingFilters = $0 }
        )
    }
    
    // Search sheet binding (only used on compact/iPhone)
    private var searchSheetBinding: Binding<Bool> {
        Binding(
            get: { 
                // Only show search sheet on compact size class
                !isRegularWidth && (state?.navigation.showingSearchSheet ?? false)
            },
            set: { 
                if !isRegularWidth {
                    if $0 {
                        state?.navigation.showSearchSheet()
                    } else {
                        state?.navigation.hideSearchSheet()
                    }
                }
            }
        )
    }
    
    // Chat sheet binding (only used on compact/iPhone)
    private var chatSheetBinding: Binding<Bool> {
        Binding(
            get: { 
                // Only show chat sheet on compact size class
                !isRegularWidth && (state?.navigation.showingChat ?? false)
            },
            set: { 
                if !isRegularWidth {
                    if $0 {
                        state?.navigation.showChat()
                    } else {
                        state?.navigation.hideChat()
                    }
                }
            }
        )
    }
    
}

// MARK: - Regular Layout (iPad/Mac)

struct RegularLayout: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        ZStack {
            // Full screen map
            AirportMapView()
                .ignoresSafeArea()
            
            // Semi-transparent backdrop when overlay is visible (tap to dismiss)
            if state?.navigation.showingLeftOverlay == true {
                Color.black.opacity(0.3)
                    .ignoresSafeArea()
                    .onTapGesture {
                        state?.navigation.hideLeftOverlay()
                    }
                    .transition(.opacity)
            }
            
            // Left Overlay (slides in from left when visible)
            HStack(spacing: 0) {
                if state?.navigation.showingLeftOverlay == true {
                    LeftOverlayContainer()
                        .transition(.move(edge: .leading))
                        .zIndex(1) // Ensure overlay is above backdrop
                }
                Spacer()
            }
            
            // Bottom Tab Bar (overlay)
            VStack {
                Spacer()
                BottomTabBar()
            }
            
            // Floating Action Buttons (top-right corner)
            VStack {
                HStack {
                    Spacer()
                    RegularFloatingActionButtons()
                        .padding(.trailing, 16)
                        .padding(.top, 8)
                }
                .padding(.top, 8) // Safe area padding
                Spacer()
            }
        }
        .animation(.spring(response: 0.3, dampingFraction: 0.8), value: state?.navigation.showingLeftOverlay)
    }
}

// MARK: - Compact Layout (iPhone)

struct CompactLayout: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        ZStack {
            // Map as background
            AirportMapView()
                .ignoresSafeArea()
            
            // Bottom Tab Bar (overlay)
            VStack {
                Spacer()
                BottomTabBar()
            }
            
            // Floating Action Buttons (top-right corner)
            VStack {
                HStack {
                    Spacer()
                    FloatingActionButtons()
                        .padding(.trailing, 16)
                        .padding(.top, 8)
                }
                .padding(.top, 8) // Safe area padding
                Spacer()
            }
        }
    }
}

// MARK: - Floating Action Buttons (iPhone)

struct FloatingActionButtons: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        VStack(spacing: 12) {
            // Search button
            FloatingActionButton(
                icon: "magnifyingglass",
                label: "Search",
                color: .blue
            ) {
                state?.navigation.showSearchSheet()
            }
            
            // Chat button
            FloatingActionButton(
                icon: "bubble.left.and.bubble.right",
                label: "Chat",
                color: .green
            ) {
                state?.navigation.showChat()
            }
            
            // Filters button (if has active filters, show indicator)
            FloatingActionButton(
                icon: state?.airports.filters.hasActiveFilters == true 
                    ? "line.3.horizontal.decrease.circle.fill"
                    : "line.3.horizontal.decrease.circle",
                label: "Filters",
                color: state?.airports.filters.hasActiveFilters == true ? .orange : .gray
            ) {
                state?.navigation.toggleFilters()
            }
        }
        .padding(.top, 8)
    }
}

// MARK: - Floating Action Buttons (iPad/Mac)

struct RegularFloatingActionButtons: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        VStack(spacing: 12) {
            // Search button
            FloatingActionButton(
                icon: "magnifyingglass",
                label: "Search",
                color: .blue
            ) {
                state?.navigation.showSearchInLeftOverlay()
            }
            
            // Chat button
            FloatingActionButton(
                icon: "bubble.left.and.bubble.right",
                label: "Chat",
                color: .green
            ) {
                state?.navigation.showChatInLeftOverlay()
            }
            
            // Filters button (if has active filters, show indicator)
            FloatingActionButton(
                icon: state?.airports.filters.hasActiveFilters == true 
                    ? "line.3.horizontal.decrease.circle.fill"
                    : "line.3.horizontal.decrease.circle",
                label: "Filters",
                color: state?.airports.filters.hasActiveFilters == true ? .orange : .gray
            ) {
                // Show search overlay (filters are accessed from search) and open filter sheet
                state?.navigation.showSearchInLeftOverlay()
                // Small delay to let overlay animate in, then show filter sheet
                Task {
                    try? await Task.sleep(for: .milliseconds(200))
                    state?.navigation.showFilters()
                }
            }
        }
        .padding(.top, 8)
    }
}

// MARK: - Floating Action Button

struct FloatingActionButton: View {
    let icon: String
    let label: String
    let color: Color
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(.white)
                .frame(width: 50, height: 50)
                .background(color, in: Circle())
                .shadow(color: .black.opacity(0.25), radius: 8, x: 0, y: 4)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Sidebar View

struct SidebarView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        SearchView()
            .navigationTitle("Airports")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        state?.navigation.toggleChat()
                    } label: {
                        Label("Chat", systemImage: "bubble.left.and.bubble.right")
                    }
                }
                
                #if os(iOS)
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        state?.navigation.toggleFilters()
                    } label: {
                        Label("Filters", systemImage: filterIcon)
                    }
                }
                #endif
            }
    }
    
    private var filterIcon: String {
        state?.airports.filters.hasActiveFilters == true
            ? "line.3.horizontal.decrease.circle.fill"
            : "line.3.horizontal.decrease.circle"
    }
}

// MARK: - Floating Search Bar (Compact)

struct FloatingSearchBar: View {
    @Environment(\.appState) private var state
    @State private var searchText = ""
    @State private var isExpanded = false
    
    var body: some View {
        VStack(spacing: 0) {
            // Search field
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                
                TextField("Search airports...", text: $searchText)
                    .textFieldStyle(.plain)
                    .onSubmit {
                        Task {
                            try? await state?.airports.search(query: searchText)
                            isExpanded = true
                        }
                    }
                
                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                        state?.airports.searchResults = []
                        isExpanded = false
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                }
                
                Button {
                    state?.navigation.toggleFilters()
                } label: {
                    Image(systemName: filterIcon)
                        .foregroundStyle(state?.airports.filters.hasActiveFilters == true ? .blue : .secondary)
                }
            }
            .padding()
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
            
            // Expanded results
            if isExpanded && !searchResults.isEmpty {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(searchResults.prefix(10), id: \.icao) { airport in
                            Button {
                                state?.airports.select(airport)
                                isExpanded = false
                            } label: {
                                CompactSearchRow(airport: airport)
                            }
                            .foregroundStyle(.primary)
                            
                            Divider()
                        }
                    }
                }
                .frame(maxHeight: 300)
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
                .padding(.top, 4)
            }
        }
    }
    
    private var filterIcon: String {
        state?.airports.filters.hasActiveFilters == true
            ? "line.3.horizontal.decrease.circle.fill"
            : "line.3.horizontal.decrease.circle"
    }
    
    private var searchResults: [RZFlight.Airport] {
        state?.airports.searchResults ?? []
    }
}

struct CompactSearchRow: View {
    let airport: RZFlight.Airport
    
    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                        Text(airport.icao)
                    .font(.headline.monospaced())
                Text(airport.name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .foregroundStyle(.tertiary)
        }
        .padding()
    }
}

// MARK: - Compact Toolbar

struct CompactToolbar: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        HStack(spacing: 20) {
            // Legend mode
            Menu {
                Picker("Legend", selection: legendModeBinding) {
                    ForEach(LegendMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
            } label: {
                VStack(spacing: 4) {
                    Image(systemName: "paintpalette")
                    Text("Legend")
                        .font(.caption2)
                }
            }
            
            // Filters
            Button {
                state?.navigation.toggleFilters()
            } label: {
                VStack(spacing: 4) {
                    Image(systemName: filterIcon)
                    Text("Filters")
                        .font(.caption2)
                }
            }
            
            // Chat / Assistant
            Button {
                state?.navigation.toggleChat()
            } label: {
                VStack(spacing: 4) {
                    Image(systemName: "bubble.left.and.bubble.right")
                    Text("Chat")
                        .font(.caption2)
                }
            }
            
            // Clear route (if active)
            if state?.airports.activeRoute != nil {
                Button {
                    state?.airports.clearRoute()
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: "xmark.circle")
                        Text("Clear")
                            .font(.caption2)
                    }
                }
            }
        }
        .padding()
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .padding()
    }
    
    private var filterIcon: String {
        state?.airports.filters.hasActiveFilters == true
            ? "line.3.horizontal.decrease.circle.fill"
            : "line.3.horizontal.decrease.circle"
    }
    
    private var legendModeBinding: Binding<LegendMode> {
        Binding(
            get: { state?.airports.legendMode ?? .airportType },
            set: { state?.airports.legendMode = $0 }
        )
    }
    }
    
// MARK: - Error & Offline Banners

struct ErrorBanner: View {
    let error: AppError
    let onDismiss: () -> Void
    
    var body: some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.yellow)
            Text(error.localizedDescription)
                .font(.caption)
            Spacer()
            Button(action: onDismiss) {
                Image(systemName: "xmark.circle.fill")
            }
        }
        .padding()
        .background(.red.opacity(0.9))
        .foregroundStyle(.white)
    }
}

struct OfflineBanner: View {
    var body: some View {
        HStack {
            Image(systemName: "wifi.slash")
            Text("Offline Mode - Using cached data")
                .font(.caption)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.9))
        .foregroundStyle(.white)
        .clipShape(Capsule())
    }
}

// MARK: - HSplitView Helper

struct HSplitViewOrHStack<Content: View>: View {
    @ViewBuilder let content: () -> Content
    
    var body: some View {
        #if os(macOS)
        HSplitView {
            content()
        }
        #else
        HStack(spacing: 0) {
            content()
        }
        #endif
    }
}

// MARK: - RZFlight Extensions

extension RZFlight.Airport {
    var hasInstrumentProcedures: Bool {
        !procedures.isEmpty
    }
    
    var maxRunwayLength: Int {
        // TODO: Access actual runway length from RZFlight
        0
    }
}

// MARK: - Preview

#Preview("Regular") {
    ContentView()
        .environment(\.horizontalSizeClass, .regular)
}

#Preview("Compact") {
    ContentView()
        .environment(\.horizontalSizeClass, .compact)
}
