//
//  AirportDetailView.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import SwiftUI
import RZFlight
import MapKit

/// Detailed view of an airport showing runways, procedures, and AIP data
struct AirportDetailView: View {
    let airport: RZFlight.Airport
    @Environment(\.appState) private var state
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                headerSection
                
                Divider()
                
                // Quick Info
                quickInfoSection
                
                Divider()
                
                // Runways
                if !airport.runways.isEmpty {
                    runwaysSection
                    Divider()
                }
                
                // Procedures
                if !airport.procedures.isEmpty {
                    proceduresSection
                    Divider()
                }
                
                // AIP Entries
                if !airport.aipEntries.isEmpty {
                    aipSection
                }
                
                Spacer(minLength: 40)
            }
            .padding()
        }
        .navigationTitle(airport.icao)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    state?.airports.focusMap(on: airport.coord, span: 0.5)
                    dismiss()
                } label: {
                    Label("Show on Map", systemImage: "map")
                }
            }
        }
        #endif
    }
    
    // MARK: - Header Section
    
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(airport.icao)
                    .font(.largeTitle.bold())
                
                Spacer()
                
                // Airport type badge
                airportTypeBadge
            }
            
            Text(airport.name)
                .font(.title2)
                .foregroundStyle(.secondary)
            
            HStack {
                Image(systemName: "building.2")
                    .foregroundStyle(.secondary)
                Text(airport.city)
                if !airport.country.isEmpty {
                    Text("•")
                        .foregroundStyle(.tertiary)
                    Text(countryName(for: airport.country))
                }
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
        }
    }
    
    private var airportTypeBadge: some View {
        HStack(spacing: 4) {
            // Type badge
            Text(airport.type.displayName)
                .font(.caption.bold())
                .foregroundStyle(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(airportTypeColor, in: Capsule())
            
            if !airport.procedures.isEmpty {
                Label("IFR", systemImage: "airplane.circle.fill")
                    .font(.caption.bold())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.blue, in: Capsule())
            }
        }
    }
    
    private var airportTypeColor: Color {
        switch airport.type {
        case .large_airport: return .red
        case .medium_airport: return .orange
        case .small_airport: return .green
        case .seaplane_base: return .teal
        default: return .gray
        }
    }
    
    // MARK: - Quick Info Section
    
    private var quickInfoSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Quick Info")
                .font(.headline)
            
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                InfoCard(
                    icon: "location.fill",
                    title: "Coordinates",
                    value: formatCoordinates(airport.coord)
                )
                
                InfoCard(
                    icon: "arrow.up.to.line",
                    title: "Elevation",
                    value: formatElevation(airport.elevation_ft)
                )
                
                InfoCard(
                    icon: "road.lanes",
                    title: "Runways",
                    value: "\(airport.runways.count)"
                )
                
                InfoCard(
                    icon: "arrow.down.to.line.compact",
                    title: "Procedures",
                    value: "\(airport.procedures.count)"
                )
            }
        }
    }
    
    // MARK: - Runways Section
    
    private var runwaysSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Runways")
                .font(.headline)
            
            ForEach(airport.runways, id: \.ident) { runway in
                RunwayRow(runway: runway, settings: state?.settings)
            }
        }
    }
    
    // MARK: - Procedures Section
    
    private var proceduresSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Procedures")
                .font(.headline)
            
            // Group by type
            let grouped = Dictionary(grouping: airport.procedures) { $0.procedureType }
            
            ForEach(Array(grouped.keys.sorted(by: { $0.rawValue < $1.rawValue })), id: \.self) { type in
                if let procedures = grouped[type] {
                    ProcedureGroup(type: type, procedures: procedures)
                }
            }
        }
    }
    
    // MARK: - AIP Section
    
    private var aipSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("AIP Information")
                .font(.headline)
            
            // Group by section for better organization
            let grouped = Dictionary(grouping: airport.aipEntries) { $0.section }
            
            ForEach(Array(grouped.keys.sorted(by: { $0.rawValue < $1.rawValue })), id: \.self) { section in
                if let entries = grouped[section] {
                    AIPSectionGroup(section: section, entries: entries)
                }
            }
        }
    }
    
    // MARK: - Helpers
    
    private func formatCoordinates(_ coord: CLLocationCoordinate2D) -> String {
        let latDir = coord.latitude >= 0 ? "N" : "S"
        let lonDir = coord.longitude >= 0 ? "E" : "W"
        return String(format: "%.4f°%@ %.4f°%@", 
                      abs(coord.latitude), latDir,
                      abs(coord.longitude), lonDir)
    }
    
    private func formatElevation(_ feet: Int) -> String {
        if let settings = state?.settings {
            return settings.formatAltitude(feet)
        }
        return "\(feet) ft"
    }
    
    private func countryName(for code: String) -> String {
        Locale.current.localizedString(forRegionCode: code) ?? code
    }
}

// MARK: - Supporting Views

struct InfoCard: View {
    let icon: String
    let title: String
    let value: String
    
    var body: some View {
        HStack {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(.blue)
                .frame(width: 30)
            
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.subheadline.bold())
            }
            
            Spacer()
        }
        .padding()
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
}

struct RunwayRow: View {
    let runway: RZFlight.Runway
    let settings: SettingsDomain?
    
    var body: some View {
        HStack {
            // Runway identifier
            VStack(alignment: .leading) {
                Text(runway.ident)
                    .font(.headline.monospaced())
                
                HStack(spacing: 4) {
                    if runway.isHardSurface {
                        Label("Hard", systemImage: "rectangle.fill")
                            .font(.caption2)
                            .foregroundStyle(.green)
                    }
                    if runway.lighted {
                        Label("Lighted", systemImage: "lightbulb.fill")
                            .font(.caption2)
                            .foregroundStyle(.yellow)
                    }
                }
            }
            
            Spacer()
            
            // Dimensions
            VStack(alignment: .trailing) {
                Text(formatLength(runway.length_ft))
                    .font(.subheadline.bold())
                if runway.width_ft > 0 {
                    Text("× \(runway.width_ft) ft wide")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
    
    private func formatLength(_ feet: Int) -> String {
        if let settings = settings {
            return settings.formatRunwayLength(feet)
        }
        return "\(feet) ft"
    }
}

struct ProcedureGroup: View {
    let type: RZFlight.Procedure.ProcedureType
    let procedures: [RZFlight.Procedure]
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(type.displayName)
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)
            
            ForEach(procedures, id: \.name) { procedure in
                ProcedureRow(procedure: procedure)
            }
        }
    }
}

struct ProcedureRow: View {
    let procedure: RZFlight.Procedure
    
    var body: some View {
        HStack {
            // Precision indicator
            Circle()
                .fill(precisionColor)
                .frame(width: 8, height: 8)
            
            Text(procedure.name)
                .font(.subheadline)
            
            Spacer()
            
            if let approachType = procedure.approachType {
                Text(approachType.rawValue)
                    .font(.caption.bold())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(approachTypeColor(approachType), in: Capsule())
            }
        }
        .padding(.vertical, 4)
    }
    
    private var precisionColor: Color {
        switch procedure.precisionCategory {
        case .precision: return .green
        case .rnav: return .blue
        case .nonPrecision: return .orange
        }
    }
    
    private func approachTypeColor(_ type: RZFlight.Procedure.ApproachType) -> Color {
        switch type {
        case .ils: return .green
        case .rnav, .rnp: return .blue
        case .vor, .ndb, .loc: return .orange
        default: return .gray
        }
    }
}

struct AIPSectionGroup: View {
    let section: RZFlight.AIPEntry.Section
    let entries: [RZFlight.AIPEntry]
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(section.displayName)
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)
            
            // Use enumerated to get unique IDs since entry.ident is airport ICAO
            ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                AIPEntryRow(entry: entry)
            }
        }
    }
}

struct AIPEntryRow: View {
    let entry: RZFlight.AIPEntry
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(entry.effectiveFieldName)
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            
            Text(entry.effectiveValue)
                .font(.subheadline)
                .textSelection(.enabled)
        }
        .padding(.vertical, 4)
    }
}


// MARK: - RZFlight Extensions

extension RZFlight.Airport.AirportType {
    var displayName: String {
        switch self {
        case .large_airport: return "Large"
        case .medium_airport: return "Medium"
        case .small_airport: return "Small"
        case .seaplane_base: return "Seaplane"
        case .balloonport: return "Balloon"
        case .closed: return "Closed"
        case .none: return "Other"
        }
    }
}

extension RZFlight.Procedure.ProcedureType {
    var displayName: String {
        switch self {
        case .approach: return "Approaches"
        case .departure: return "Departures (SID)"
        case .arrival: return "Arrivals (STAR)"
        }
    }
}

extension RZFlight.Runway {
    /// Combined runway identifier (e.g., "09/27")
    var ident: String {
        "\(le.ident)/\(he.ident)"
    }
}


// MARK: - Preview

#Preview {
    NavigationStack {
        // Use a placeholder for preview
        Text("Airport Detail Preview")
    }
}
