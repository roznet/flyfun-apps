//
//  AirportMapView.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import SwiftUI
import MapKit
import RZFlight

/// Main map view showing airports with markers, routes, and highlights
struct AirportMapView: View {
    @Environment(\.appState) private var state
    @State private var selectedAirportID: String?
    
    var body: some View {
        let currentLegendMode = state?.airports.legendMode ?? .airportType
        
        Map(
            position: mapPosition,
            selection: $selectedAirportID
        ) {
            // Airport markers using custom Annotation for full flexibility
            ForEach(airports, id: \.icao) { airport in
                Annotation(airport.icao, coordinate: airport.coord) {
                    AirportMarkerView(
                        airport: airport,
                        legendMode: currentLegendMode,
                        isSelected: airport.icao == state?.airports.selectedAirport?.icao
                    )
                }
                .tag(airport.icao)
            }
            
            // Route polyline
            if let route = state?.airports.activeRoute {
                MapPolyline(coordinates: route.coordinates)
                    .stroke(.blue.opacity(0.8), lineWidth: 4)
            }
            
            // Highlights (from chat visualization)
            ForEach(Array(highlights.values), id: \.id) { highlight in
                MapCircle(center: highlight.coordinate, radius: highlight.radius)
                    .foregroundStyle(highlightColor(highlight.color).opacity(0.2))
                    .stroke(highlightColor(highlight.color), lineWidth: 2)
            }
        }
        .id(currentLegendMode) // Force map to re-render when legend changes
        .mapStyle(.standard(elevation: .realistic))
        .mapControls {
            MapCompass()
            MapScaleView()
            #if os(iOS)
            MapUserLocationButton()
            #endif
        }
        .onMapCameraChange(frequency: .onEnd) { context in
            state?.airports.onRegionChange(context.region)
        }
        .onChange(of: selectedAirportID) { _, newValue in
            if let icao = newValue,
               let airport = airports.first(where: { $0.icao == icao }) {
                state?.airports.select(airport)
                state?.navigation.showAirportDetail()
            }
        }
        .overlay(alignment: .topTrailing) {
            legendOverlay
        }
        .overlay(alignment: .topLeading) {
            legendKeyOverlay
        }
        .overlay(alignment: .bottom) {
            if state?.airports.activeRoute != nil {
                routeInfoBar
            }
        }
    }
    
    // MARK: - Computed Properties
    
    private var airports: [RZFlight.Airport] {
        state?.airports.airports ?? []
    }
    
    private var highlights: [String: MapHighlight] {
        state?.airports.highlights ?? [:]
    }
    
    private var mapPosition: Binding<MapCameraPosition> {
        Binding(
            get: { state?.airports.mapPosition ?? .automatic },
            set: { state?.airports.mapPosition = $0 }
        )
    }
    
    private var legendMode: LegendMode {
        state?.airports.legendMode ?? .airportType
    }
    
    private func highlightColor(_ color: MapHighlight.HighlightColor) -> Color {
        switch color {
        case .blue: return .blue
        case .red: return .red
        case .green: return .green
        case .orange: return .orange
        case .purple: return .purple
        }
    }
    
    // MARK: - Legend Mode Picker
    
    private var legendOverlay: some View {
        Menu {
            Picker("Legend", selection: legendModeBinding) {
                ForEach(LegendMode.allCases) { mode in
                    Label(mode.rawValue, systemImage: mode.icon)
                        .tag(mode)
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: legendMode.icon)
                Text(legendMode.rawValue)
                    .font(.caption)
            }
            .padding(8)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
        .padding()
    }
    
    private var legendModeBinding: Binding<LegendMode> {
        Binding(
            get: { state?.airports.legendMode ?? .airportType },
            set: { state?.airports.legendMode = $0 }
        )
    }
    
    // MARK: - Legend Key (Color/Size explanation)
    
    private var legendKeyOverlay: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(legendMode.legendItems, id: \.label) { item in
                HStack(spacing: 6) {
                    Circle()
                        .fill(item.color)
                        .frame(width: item.size, height: item.size)
                    Text(item.label)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(8)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
        .padding()
    }
    
    // MARK: - Route Info Bar
    
    private var routeInfoBar: some View {
        HStack {
            if let route = state?.airports.activeRoute {
                Image(systemName: "airplane.departure")
                Text(route.departure)
                    .bold()
                Image(systemName: "arrow.right")
                Text(route.destination)
                    .bold()
                Image(systemName: "airplane.arrival")
                
                Spacer()
                
                Button {
                    state?.airports.clearRoute()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .font(.caption)
        .padding()
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
        .padding()
    }
}

// MARK: - Custom Airport Marker View

/// Custom marker that supports variable color AND size based on legend mode
struct AirportMarkerView: View {
    let airport: RZFlight.Airport
    let legendMode: LegendMode
    let isSelected: Bool
    
    var body: some View {
        ZStack {
            // Main circle with size based on legend mode
            Circle()
                .fill(markerColor.gradient)
                .frame(width: markerSize, height: markerSize)
                .shadow(color: markerColor.opacity(0.5), radius: isSelected ? 8 : 2)
            
            // Selection ring
            if isSelected {
                Circle()
                    .stroke(Color.white, lineWidth: 3)
                    .frame(width: markerSize + 6, height: markerSize + 6)
            }
            
            // IFR indicator dot (small white dot for airports with procedures)
            if airport.hasInstrumentProcedures && legendMode != .procedures {
                Circle()
                    .fill(.white)
                    .frame(width: 6, height: 6)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: isSelected)
    }
    
    // MARK: - Size Calculation
    
    private var markerSize: CGFloat {
        switch legendMode {
        case .airportType:
            return airportTypeSize
        case .runwayLength:
            return runwayLengthSize
        case .procedures:
            return procedureSize
        case .country:
            return 16 // Fixed size for country mode
        }
    }
    
    private var airportTypeSize: CGFloat {
        switch airport.type {
        case .large_airport: return 24
        case .medium_airport: return 18
        case .small_airport: return 12
        case .seaplane_base: return 14
        default: return 10
        }
    }
    
    private var runwayLengthSize: CGFloat {
        let maxLength = airport.runways.map(\.length_ft).max() ?? 0
        // Scale from 8 to 28 based on runway length
        if maxLength >= 10000 { return 28 }
        if maxLength >= 8000 { return 24 }
        if maxLength >= 6000 { return 20 }
        if maxLength >= 4000 { return 16 }
        if maxLength >= 2000 { return 12 }
        return 8
    }
    
    private var procedureSize: CGFloat {
        let count = airport.procedures.count
        if count >= 10 { return 24 }
        if count >= 5 { return 18 }
        if count >= 1 { return 14 }
        return 8 // No procedures
    }
    
    // MARK: - Color Calculation
    
    private var markerColor: Color {
        switch legendMode {
        case .airportType:
            return airportTypeColor
        case .runwayLength:
            return runwayLengthColor
        case .procedures:
            return procedureColor
        case .country:
            return countryColor
        }
    }
    
    private var airportTypeColor: Color {
        switch airport.type {
        case .large_airport: return .red
        case .medium_airport: return .orange
        case .small_airport: return .green
        case .seaplane_base: return .teal
        case .balloonport: return .purple
        case .closed: return .gray
        case .none: return .gray
        }
    }
    
    private var runwayLengthColor: Color {
        let maxLength = airport.runways.map(\.length_ft).max() ?? 0
        if maxLength >= 8000 { return .green }
        if maxLength >= 5000 { return .blue }
        if maxLength >= 3000 { return .orange }
        return .red
    }
    
    private var procedureColor: Color {
        if airport.procedures.isEmpty { return .gray }
        let hasPrecision = airport.procedures.contains { $0.precisionCategory == .precision }
        let hasRNAV = airport.procedures.contains { $0.precisionCategory == .rnav }
        if hasPrecision { return .green }
        if hasRNAV { return .blue }
        return .orange
    }
    
    private var countryColor: Color {
        // Consistent color per country using hash
        let hash = abs(airport.country.hashValue)
        let colors: [Color] = [
            .blue, .green, .orange, .purple, .pink,
            .cyan, .mint, .indigo, .teal, .brown
        ]
        return colors[hash % colors.count]
    }
}

// MARK: - Legend Mode Extensions

extension LegendMode {
    var icon: String {
        switch self {
        case .airportType: return "airplane.circle"
        case .runwayLength: return "road.lanes"
        case .procedures: return "arrow.down.to.line.compact"
        case .country: return "flag"
        }
    }
    
    /// Legend key items showing what colors/sizes mean
    var legendItems: [LegendItem] {
        switch self {
        case .airportType:
            return [
                LegendItem(color: .red, size: 24, label: "Large"),
                LegendItem(color: .orange, size: 18, label: "Medium"),
                LegendItem(color: .green, size: 12, label: "Small"),
                LegendItem(color: .teal, size: 14, label: "Seaplane"),
            ]
        case .runwayLength:
            return [
                LegendItem(color: .green, size: 24, label: "≥8000 ft"),
                LegendItem(color: .blue, size: 18, label: "5000-8000 ft"),
                LegendItem(color: .orange, size: 14, label: "3000-5000 ft"),
                LegendItem(color: .red, size: 10, label: "<3000 ft"),
            ]
        case .procedures:
            return [
                LegendItem(color: .green, size: 20, label: "Precision (ILS)"),
                LegendItem(color: .blue, size: 16, label: "RNAV/GPS"),
                LegendItem(color: .orange, size: 12, label: "Non-precision"),
                LegendItem(color: .gray, size: 8, label: "VFR only"),
            ]
        case .country:
            return [
                LegendItem(color: .blue, size: 16, label: "Colored by country"),
            ]
        }
    }
}

struct LegendItem {
    let color: Color
    let size: CGFloat
    let label: String
}

// MARK: - Preview

#Preview {
    AirportMapView()
}
