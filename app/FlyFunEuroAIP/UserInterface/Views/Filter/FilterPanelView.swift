//
//  FilterPanelView.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import SwiftUI

/// Filter panel for filtering airports on the map
struct FilterPanelView: View {
    @Environment(\.appState) private var state
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        NavigationStack {
            Form {
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
            .navigationTitle("Filters")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Reset") {
                        state?.airports.resetFilters()
                    }
                    .disabled(state?.airports.filters.hasActiveFilters != true)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .bold()
                }
            }
            #endif
        }
    }
    
    // MARK: - Feature Filters
    
    private var featureFiltersSection: some View {
        Section {
            Toggle("IFR Procedures", isOn: hasProceduresBinding)
            Toggle("Border Crossing (Point of Entry)", isOn: pointOfEntryBinding)
            Toggle("Hard Runway", isOn: hasHardRunwayBinding)
            Toggle("Lighted Runway", isOn: hasLightedRunwayBinding)
        } header: {
            Text("Features")
        } footer: {
            Text("Filter airports by available features")
        }
    }
    
    // MARK: - Runway Filters
    
    private var runwayFiltersSection: some View {
        Section {
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
        } header: {
            Text("Runway")
        }
    }
    
    // MARK: - Approach Filters
    
    private var approachFiltersSection: some View {
        Section {
            Toggle("Has ILS", isOn: hasILSBinding)
            Toggle("Has RNAV/GPS", isOn: hasRNAVBinding)
            Toggle("Precision Approach", isOn: hasPrecisionBinding)
        } header: {
            Text("Approaches")
        }
    }
    
    // MARK: - Country Filter
    
    private var countryFilterSection: some View {
        Section {
            NavigationLink {
                CountryPickerView(selectedCountry: countryBinding)
            } label: {
                HStack {
                    Text("Country")
                    Spacer()
                    Text(state?.airports.filters.country ?? "All")
                        .foregroundStyle(.secondary)
                }
            }
        } header: {
            Text("Location")
        }
    }
    
    // MARK: - Actions
    
    private var actionsSection: some View {
        Section {
            Button {
                Task {
                    try? await state?.airports.applyFilters()
                    dismiss()
                }
            } label: {
                HStack {
                    Spacer()
                    Text("Apply Filters")
                        .bold()
                    Spacer()
                }
            }
            .disabled(state?.airports.filters.hasActiveFilters != true)
        } footer: {
            if let count = state?.airports.filters.activeFilterCount, count > 0 {
                Text("\(count) filter\(count == 1 ? "" : "s") active")
            }
        }
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
        // Apply filters with a small delay for better UX
        Task {
            try? await Task.sleep(for: .milliseconds(300))
            try? await state?.airports.applyFilters()
        }
    }
}

// MARK: - Country Picker

struct CountryPickerView: View {
    @Binding var selectedCountry: String?
    @Environment(\.appState) private var state
    @Environment(\.dismiss) private var dismiss
    @State private var searchText = ""
    @State private var countries: [String] = []
    
    var body: some View {
        List {
            // "All" option
            Button {
                selectedCountry = nil
                dismiss()
            } label: {
                HStack {
                    Text("All Countries")
                    Spacer()
                    if selectedCountry == nil {
                        Image(systemName: "checkmark")
                            .foregroundStyle(.blue)
                    }
                }
            }
            .foregroundStyle(.primary)
            
            // Country list
            ForEach(filteredCountries, id: \.self) { country in
                Button {
                    selectedCountry = country
                    dismiss()
                } label: {
                    HStack {
                        Text(countryName(for: country))
                        Spacer()
                        Text(country)
                            .foregroundStyle(.secondary)
                        if selectedCountry == country {
                            Image(systemName: "checkmark")
                                .foregroundStyle(.blue)
                        }
                    }
                }
                .foregroundStyle(.primary)
            }
        }
        .searchable(text: $searchText, prompt: "Search countries")
        .navigationTitle("Country")
        .task {
            // Load available countries from the repository via the domain
            countries = await state?.airports.loadAvailableCountries() ?? []
        }
    }
    
    private var filteredCountries: [String] {
        if searchText.isEmpty {
            return countries
        }
        return countries.filter { country in
            country.localizedCaseInsensitiveContains(searchText) ||
            countryName(for: country).localizedCaseInsensitiveContains(searchText)
        }
    }
    
    private func countryName(for code: String) -> String {
        Locale.current.localizedString(forRegionCode: code) ?? code
    }
}

// MARK: - Preview

#Preview {
    FilterPanelView()
}

