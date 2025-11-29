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
        Map(
            position: mapPosition,
            selection: $selectedAirportID
        ) {
            // Airport markers
            ForEach(airports, id: \.icao) { airport in
                Marker(
                    airport.icao,
                    coordinate: airport.coord
                )
                .tint(markerColor(for: airport))
                .tag(airport.icao)
            }
            
            // Route polyline
            if let route = state?.airports.activeRoute {
                MapPolyline(coordinates: route.coordinates)
                    .stroke(.blue, lineWidth: 3)
            }
            
            // Highlights
            ForEach(Array(highlights.values), id: \.id) { highlight in
                MapCircle(center: highlight.coordinate, radius: highlight.radius)
                    .foregroundStyle(highlightColor(highlight.color).opacity(0.3))
                    .stroke(highlightColor(highlight.color), lineWidth: 2)
            }
        }
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
            }
        }
        .overlay(alignment: .topTrailing) {
            legendOverlay
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
    
    // MARK: - Marker Colors
    
    private func markerColor(for airport: RZFlight.Airport) -> Color {
        // Highlight selected airport
        if airport.icao == state?.airports.selectedAirport?.icao {
            return .red
        }
        
        switch legendMode {
        case .airportType:
            return airport.hasInstrumentProcedures ? .blue : .orange
        case .runwayLength:
            return runwayLengthColor(airport.maxRunwayLength)
        case .procedures:
            if airport.procedures.isEmpty { return .gray }
            let hasPrecision = airport.procedures.contains { $0.precisionCategory == .precision }
            return hasPrecision ? .green : .blue
        case .country:
            // Use a consistent color per country
            return countryColor(airport.country)
        }
    }
    
    private func runwayLengthColor(_ length: Int) -> Color {
        if length >= 8000 { return .green }
        if length >= 5000 { return .blue }
        if length >= 3000 { return .orange }
        return .red
    }
    
    private func countryColor(_ country: String?) -> Color {
        guard let country = country else { return .gray }
        // Simple hash-based color
        let hash = abs(country.hashValue)
        let colors: [Color] = [.blue, .green, .orange, .purple, .pink, .cyan, .mint, .indigo]
        return colors[hash % colors.count]
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
    
    // MARK: - Legend Overlay
    
    private var legendOverlay: some View {
        Menu {
            Picker("Legend", selection: legendModeBinding) {
                ForEach(LegendMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "paintpalette")
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

// MARK: - Preview

#Preview {
    AirportMapView()
}

