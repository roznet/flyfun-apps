//
//  LeftOverlayContainer.swift
//  FlyFunEuroAIP
//
//  Container for left overlay that toggles between Search/Filter and Chat views
//

import SwiftUI

// MARK: - Filter Panel Content (for left overlay)

struct FilterPanelContent: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Feature Filters
                featureFiltersSection
                
                // Runway Filters
                runwayFiltersSection
                
                // Approach Filters
                approachFiltersSection
                
                // Country Filter
                countryFilterSection
                
                // Actions
                actionsSection
            }
            .padding()
        }
    }
    
    // MARK: - Feature Filters
    
    private var featureFiltersSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Features")
                .font(.headline)
                .padding(.bottom, 4)
            
            Toggle("IFR Procedures", isOn: hasProceduresBinding)
            Toggle("Border Crossing (Point of Entry)", isOn: pointOfEntryBinding)
            Toggle("Hard Runway", isOn: hasHardRunwayBinding)
            Toggle("Lighted Runway", isOn: hasLightedRunwayBinding)
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
    
    // MARK: - Runway Filters
    
    private var runwayFiltersSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Runway")
                .font(.headline)
                .padding(.bottom, 4)
            
            HStack {
                Text("Minimum Length")
                Spacer()
                Picker("Min Length", selection: minRunwayBinding) {
                    Text("Any").tag(nil as Int?)
                    Text("1000 ft").tag(1000 as Int?)
                    Text("2000 ft").tag(2000 as Int?)
                    Text("3000 ft").tag(3000 as Int?)
                    Text("4000 ft").tag(4000 as Int?)
                    Text("5000 ft").tag(5000 as Int?)
                    Text("6000 ft").tag(6000 as Int?)
                    Text("8000 ft").tag(8000 as Int?)
                }
                .labelsHidden()
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
    
    // MARK: - Approach Filters
    
    private var approachFiltersSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Approaches")
                .font(.headline)
                .padding(.bottom, 4)
            
            Toggle("Has ILS", isOn: hasILSBinding)
            Toggle("Has RNAV/GPS", isOn: hasRNAVBinding)
            Toggle("Precision Approach", isOn: hasPrecisionBinding)
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
    
    // MARK: - Country Filter
    
    private var countryFilterSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Location")
                .font(.headline)
                .padding(.bottom, 4)
            
            NavigationLink {
                CountryPickerView(selectedCountry: countryBinding)
            } label: {
                HStack {
                    Text("Country")
                    Spacer()
                    Text(state?.airports.filters.country ?? "All")
                        .foregroundStyle(.secondary)
                    Image(systemName: "chevron.right")
                        .foregroundStyle(.tertiary)
                        .font(.caption)
                }
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
    
    // MARK: - Actions
    
    private var actionsSection: some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    try? await state?.airports.applyFilters()
                }
            } label: {
                HStack {
                    Spacer()
                    Text("Apply Filters")
                        .bold()
                    Spacer()
                }
                .padding()
                .background(.blue, in: RoundedRectangle(cornerRadius: 10))
                .foregroundStyle(.white)
            }
            .disabled(state?.airports.filters.hasActiveFilters != true)
            
            Button {
                state?.airports.resetFilters()
            } label: {
                HStack {
                    Spacer()
                    Text("Reset")
                    Spacer()
                }
                .padding()
                .foregroundStyle(.secondary)
            }
            .disabled(state?.airports.filters.hasActiveFilters != true)
            
            if let count = state?.airports.filters.activeFilterCount, count > 0 {
                Text("\(count) filter\(count == 1 ? "" : "s") active")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
    }
    
    // MARK: - Bindings
    
    private var hasProceduresBinding: Binding<Bool> {
        Binding(
            get: { state?.airports.filters.hasProcedures ?? false },
            set: { newValue in
                state?.airports.filters.hasProcedures = newValue ? true : nil
                applyFiltersDebounced()
            }
        )
    }
    
    private var pointOfEntryBinding: Binding<Bool> {
        Binding(
            get: { state?.airports.filters.pointOfEntry ?? false },
            set: { newValue in
                state?.airports.filters.pointOfEntry = newValue ? true : nil
                applyFiltersDebounced()
            }
        )
    }
    
    private var hasHardRunwayBinding: Binding<Bool> {
        Binding(
            get: { state?.airports.filters.hasHardRunway ?? false },
            set: { newValue in
                state?.airports.filters.hasHardRunway = newValue ? true : nil
                applyFiltersDebounced()
            }
        )
    }
    
    private var hasLightedRunwayBinding: Binding<Bool> {
        Binding(
            get: { state?.airports.filters.hasLightedRunway ?? false },
            set: { newValue in
                state?.airports.filters.hasLightedRunway = newValue ? true : nil
                applyFiltersDebounced()
            }
        )
    }
    
    private var minRunwayBinding: Binding<Int?> {
        Binding(
            get: { state?.airports.filters.minRunwayLengthFt },
            set: { newValue in
                state?.airports.filters.minRunwayLengthFt = newValue
                applyFiltersDebounced()
            }
        )
    }
    
    private var hasILSBinding: Binding<Bool> {
        Binding(
            get: { state?.airports.filters.hasILS ?? false },
            set: { newValue in
                state?.airports.filters.hasILS = newValue ? true : nil
                applyFiltersDebounced()
            }
        )
    }
    
    private var hasRNAVBinding: Binding<Bool> {
        Binding(
            get: { state?.airports.filters.hasRNAV ?? false },
            set: { newValue in
                state?.airports.filters.hasRNAV = newValue ? true : nil
                applyFiltersDebounced()
            }
        )
    }
    
    private var hasPrecisionBinding: Binding<Bool> {
        Binding(
            get: { state?.airports.filters.hasPrecisionApproach ?? false },
            set: { newValue in
                state?.airports.filters.hasPrecisionApproach = newValue ? true : nil
                applyFiltersDebounced()
            }
        )
    }
    
    private var countryBinding: Binding<String?> {
        Binding(
            get: { state?.airports.filters.country },
            set: { newValue in
                state?.airports.filters.country = newValue
                applyFiltersDebounced()
            }
        )
    }
    
    // MARK: - Helpers
    
    private func applyFiltersDebounced() {
        Task {
            try? await Task.sleep(for: .milliseconds(300))
            try? await state?.airports.applyFilters()
        }
    }
}

/// Left overlay container that shows either Search/Filter or Chat based on navigation state
struct LeftOverlayContainer: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        VStack(spacing: 0) {
            // Toolbar with close button only (no toggle/filter buttons needed - use floating buttons)
            overlayToolbar
            
            // Content area - shows Search, Chat, or Filters
            Group {
                switch state?.navigation.leftOverlayMode ?? .search {
                case .search:
                    SearchView()
                case .chat:
                    ChatView()
                        .navigationBarHidden(true) // Remove navigation bar when in overlay
                        .toolbar(.hidden, for: .navigationBar) // Hide toolbar too
                case .filters:
                    FilterPanelContent()
                }
            }
        }
        .frame(width: overlayWidth)
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .shadow(color: .black.opacity(0.15), radius: 20, x: 4, y: 0)
    }
    
    // MARK: - Toolbar
    
    private var overlayToolbar: some View {
        HStack {
            // Title based on mode
            Text(overlayTitle)
                .font(.headline)
                .foregroundStyle(.primary)
            
            Spacer()
            
            // Close button (to dismiss overlay)
            Button {
                state?.navigation.hideLeftOverlay()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.regularMaterial)
    }
    
    // MARK: - Computed Properties
    
    private var overlayWidth: CGFloat {
        #if os(macOS)
        400
        #else
        350
        #endif
    }
    
    private var overlayTitle: String {
        switch state?.navigation.leftOverlayMode ?? .search {
        case .search:
            return "Search"
        case .chat:
            return "Chat"
        case .filters:
            return "Filters"
        }
    }
}

// MARK: - Preview

#Preview {
    LeftOverlayContainer()
        .frame(height: 600)
}




