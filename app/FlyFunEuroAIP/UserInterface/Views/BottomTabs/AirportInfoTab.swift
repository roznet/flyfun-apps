//
//  AirportInfoTab.swift
//  FlyFunEuroAIP
//
//  Airport Info tab showing basic info, runways, and procedures
//

import SwiftUI
import RZFlight

struct AirportInfoTab: View {
    let airport: RZFlight.Airport
    @Environment(\.appState) private var state
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Basic Info
                basicInfoSection
                
                // Runways
                if !airport.runways.isEmpty {
                    runwaysSection
                }
                
                // Procedures
                if !airport.procedures.isEmpty {
                    proceduresSection
                }
            }
            .padding()
        }
    }
    
    // MARK: - Basic Info
    
    private var basicInfoSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Airport Information")
                .font(.headline)
            
            InfoRow(label: "ICAO", value: airport.icao)
            InfoRow(label: "Name", value: airport.name)
            if !airport.city.isEmpty {
                InfoRow(label: "City", value: airport.city)
            }
            if !airport.country.isEmpty {
                InfoRow(label: "Country", value: airport.country)
            }
            if airport.elevation_ft > 0 {
                InfoRow(label: "Elevation", value: "\(airport.elevation_ft) ft")
            }
        }
        .padding()
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
    
    // MARK: - Runways
    
    private var runwaysSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Runways")
                .font(.headline)
            
            ForEach(airport.runways, id: \.ident) { runway in
                RunwayRow(runway: runway, settings: state?.settings)
            }
        }
        .padding()
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
    
    // MARK: - Procedures
    
    private var proceduresSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Procedures")
                .font(.headline)
            
            let approaches = airport.procedures.filter { $0.isApproach }
            let departures = airport.procedures.filter { $0.isDeparture }
            
            if !approaches.isEmpty {
                Text("Approaches")
                    .font(.subheadline.bold())
                    .foregroundStyle(.secondary)
                
                ForEach(approaches, id: \.name) { procedure in
                    ProcedureRow(procedure: procedure)
                }
            }
            
            if !departures.isEmpty {
                Text("Departures")
                    .font(.subheadline.bold())
                    .foregroundStyle(.secondary)
                    .padding(.top, 8)
                
                ForEach(departures, id: \.name) { procedure in
                    ProcedureRow(procedure: procedure)
                }
            }
        }
        .padding()
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Info Row

struct InfoRow: View {
    let label: String
    let value: String
    
    var body: some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .bold()
        }
    }
}

// MARK: - Preview
// Note: Preview requires sample airport data - to be implemented with PreviewFactory

