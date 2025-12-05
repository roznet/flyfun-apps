//
//  RulesTab.swift
//  FlyFunEuroAIP
//
//  Rules tab showing country-specific rules for the airport
//

import SwiftUI
import RZFlight

struct RulesTab: View {
    let airport: RZFlight.Airport
    @Environment(\.appState) private var state
    @State private var rules: CountryRules?
    @State private var isLoading = false
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding()
                } else if let rules = rules {
                    rulesContent(rules)
                } else {
                    ContentUnavailableView {
                        Label("No Rules Data", systemImage: "book")
                    } description: {
                        Text("Country rules not available for \(airport.country)")
                    }
                }
            }
            .padding()
        }
        .task {
            await loadRules()
        }
    }
    
    private func rulesContent(_ rules: CountryRules) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Country Rules")
                .font(.headline)
            
            if let name = rules.countryName {
                InfoRow(label: "Country", value: name)
            }
            
            // Add more rule content here as CountryRules model expands
            Text("Rules data structure to be expanded")
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
    
    private func loadRules() async {
        guard !airport.country.isEmpty else { return }
        
        // TODO: Add countryRules method to AirportRepositoryProtocol
        // For now, rules will remain nil and show "No Rules Data"
        // This is a placeholder for future implementation
        // When implemented, set isLoading = true at start and false at end
    }
}

// MARK: - Country Rules Model

struct CountryRules: Sendable {
    let countryCode: String
    let countryName: String?
    // Add more fields as needed
}

// MARK: - Preview
// Note: Preview requires sample airport data - to be implemented with PreviewFactory

