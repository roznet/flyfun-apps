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
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var selectedAirportID: String?
    
    private var isCompact: Bool {
        sizeClass == .compact
    }
    
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
                        isSelected: airport.icao == state?.airports.selectedAirport?.icao,
                        isBorderCrossing: state?.airports.isBorderCrossing(airport) ?? false
                    )
                }
                .tag(airport.icao)
            }
            
            // Route polyline
            if let route = state?.airports.activeRoute {
                MapPolyline(coordinates: route.coordinates)
                    .stroke(.blue.opacity(0.8), lineWidth: 4)
            }
            
            // Procedure lines (when in procedure legend mode)
            if currentLegendMode == .procedures {
                ForEach(Array(procedureLines.keys), id: \.self) { icao in
                    if let lines = procedureLines[icao] {
                        ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                            MapPolyline(coordinates: [line.startCoordinate, line.endCoordinate])
                                .stroke(procedureLineColor(line.precisionCategory), lineWidth: 3)
                        }
                    }
                }
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
            // Update visibleRegion when map camera changes to keep it in sync
            state?.airports.visibleRegion = context.region
            state?.airports.onRegionChange(context.region)
        }
        .onChange(of: selectedAirportID) { _, newValue in
            if let icao = newValue,
               let airport = airports.first(where: { $0.icao == icao }) {
                state?.airports.select(airport)
                state?.navigation.showAirportDetail()
            }
        }
        .onChange(of: currentLegendMode) { oldValue, newValue in
            // Load procedure lines when switching to procedure mode
            if newValue == .procedures && oldValue != .procedures {
                Task {
                    await state?.airports.loadProcedureLines()
                }
            }
            // Clear procedure lines when switching away from procedure mode
            else if newValue != .procedures && oldValue == .procedures {
                state?.airports.clearProcedureLines()
            }
        }
        // Legend overlays - always at bottom: selector on left, key on right
        .overlay(alignment: .bottomTrailing) {
            legendKeyOverlay
        }
        .overlay(alignment: .bottomLeading) {
            legendOverlay
        }
        .overlay(alignment: .bottom) {
            // Route info bar - position above legend
            if state?.airports.activeRoute != nil {
                routeInfoBar
                    .padding(.bottom, bottomPadding + 80) // Space for legend
            }
        }
    }
    
    // MARK: - Computed Properties
    
    /// Get airports to display on map
    /// Priority: searchResults (if search active) > airports (route/region-based)
    private var airports: [RZFlight.Airport] {
        guard let state = state else { return [] }
        
        // If search is active and has results, show search results
        if state.airports.isSearchActive && !state.airports.searchResults.isEmpty {
            return state.airports.searchResults
        }
        
        // Otherwise show the main airports array (route results or region-based)
        return state.airports.airports
    }
    
    private var highlights: [String: MapHighlight] {
        state?.airports.highlights ?? [:]
    }
    
    private var procedureLines: [String: [RZFlight.Airport.ProcedureLine]] {
        state?.airports.procedureLines ?? [:]
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
    
    /// Get color for procedure line based on precision category
    /// Matches web app: Yellow = Precision (ILS), Blue = RNAV, White = Non-Precision
    private func procedureLineColor(_ category: RZFlight.Procedure.PrecisionCategory) -> Color {
        switch category {
        case .precision:
            return Color(red: 1.0, green: 1.0, blue: 0.0) // Yellow (#ffff00) for ILS
        case .rnav:
            return Color(red: 0.0, green: 0.5, blue: 1.0) // Blue (#0000ff) for RNAV/GPS
        case .nonPrecision:
            return .white // White (#ffffff) for VOR/NDB
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
        .padding(.bottom, bottomPadding) // Space for bottom tab bar
    }
    
    private var bottomPadding: CGFloat {
        // If bottom tab bar is showing, add space for it (300px content + ~60px tab bar)
        if state?.navigation.showingBottomTabBar == true {
            return 360
        }
        // Otherwise just safe area padding
        return 20
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
        .padding(.bottom, bottomPadding) // Space for bottom tab bar
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
/// Matches web app legend behavior
struct AirportMarkerView: View {
    let airport: RZFlight.Airport
    let legendMode: LegendMode
    let isSelected: Bool
    let isBorderCrossing: Bool
    
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
            // Only show in airport-type mode for non-border-crossing IFR airports
            if legendMode == .airportType && airport.hasInstrumentProcedures && !isBorderCrossing {
                Circle()
                    .fill(.white)
                    .frame(width: 5, height: 5)
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
            return 14 // Fixed size for country mode
        }
    }
    
    /// Airport Type mode: Border Crossing > IFR > VFR
    private var airportTypeSize: CGFloat {
        if isBorderCrossing { return 16 }
        if airport.hasInstrumentProcedures { return 14 }
        return 12
    }
    
    /// Runway Length mode: Size by longest runway
    private var runwayLengthSize: CGFloat {
        let maxLength = longestRunwayFt
        if maxLength > 8000 { return 20 }
        if maxLength > 4000 { return 14 }
        return 10
    }
    
    /// Procedures mode: Size by procedure count
    private var procedureSize: CGFloat {
        let count = airport.procedures.count
        if count >= 10 { return 20 }
        if count >= 5 { return 16 }
        if count >= 1 { return 12 }
        return 8 // VFR only
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
    
    /// Airport Type mode - matches web app:
    /// - Green (#28a745) = Border Crossing
    /// - Yellow (#ffc107) = Has procedures (IFR)
    /// - Red (#dc3545) = VFR only
    private var airportTypeColor: Color {
        if isBorderCrossing {
            return Color(red: 0.157, green: 0.655, blue: 0.271) // #28a745 Green
        }
        if airport.hasInstrumentProcedures {
            return Color(red: 1.0, green: 0.757, blue: 0.027) // #ffc107 Yellow
        }
        return Color(red: 0.863, green: 0.208, blue: 0.271) // #dc3545 Red
    }
    
    /// Runway Length mode - matches web app:
    /// - Green = > 8000 ft
    /// - Yellow = 4000-8000 ft
    /// - Red = < 4000 ft
    private var runwayLengthColor: Color {
        let maxLength = longestRunwayFt
        if maxLength > 8000 {
            return Color(red: 0.157, green: 0.655, blue: 0.271) // Green
        }
        if maxLength > 4000 {
            return Color(red: 1.0, green: 0.757, blue: 0.027) // Yellow
        }
        return Color(red: 0.863, green: 0.208, blue: 0.271) // Red
    }
    
    /// Procedures mode - by precision category
    private var procedureColor: Color {
        if airport.procedures.isEmpty {
            return .gray
        }
        let hasPrecision = airport.procedures.contains { $0.precisionCategory == .precision }
        let hasRNAV = airport.procedures.contains { $0.precisionCategory == .rnav }
        if hasPrecision {
            return Color(red: 1.0, green: 1.0, blue: 0.0) // Yellow for ILS
        }
        if hasRNAV {
            return Color(red: 0.0, green: 0.5, blue: 1.0) // Blue for RNAV
        }
        return .orange // Non-precision
    }
    
    /// Country mode - consistent color per country
    private var countryColor: Color {
        let hash = abs(airport.country.hashValue)
        let colors: [Color] = [
            .blue, .green, .orange, .purple, .pink,
            .cyan, .mint, .indigo, .teal, .brown
        ]
        return colors[hash % colors.count]
    }
    
    // MARK: - Helpers
    
    /// Get longest runway length in feet
    private var longestRunwayFt: Int {
        airport.runways.map(\.length_ft).max() ?? 0
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
    
    /// Legend key items showing what colors/sizes mean - matches web app
    var legendItems: [LegendItem] {
        switch self {
        case .airportType:
            return [
                LegendItem(color: Color(red: 0.157, green: 0.655, blue: 0.271), size: 16, label: "Border Crossing"),
                LegendItem(color: Color(red: 1.0, green: 0.757, blue: 0.027), size: 14, label: "IFR (with procedures)"),
                LegendItem(color: Color(red: 0.863, green: 0.208, blue: 0.271), size: 12, label: "VFR only"),
            ]
        case .runwayLength:
            return [
                LegendItem(color: Color(red: 0.157, green: 0.655, blue: 0.271), size: 20, label: ">8000 ft"),
                LegendItem(color: Color(red: 1.0, green: 0.757, blue: 0.027), size: 14, label: "4000-8000 ft"),
                LegendItem(color: Color(red: 0.863, green: 0.208, blue: 0.271), size: 10, label: "<4000 ft"),
            ]
        case .procedures:
            return [
                LegendItem(color: Color(red: 1.0, green: 1.0, blue: 0.0), size: 16, label: "Precision (ILS)"),
                LegendItem(color: Color(red: 0.0, green: 0.5, blue: 1.0), size: 14, label: "RNAV/GPS"),
                LegendItem(color: .orange, size: 12, label: "Non-precision"),
                LegendItem(color: .gray, size: 8, label: "VFR only"),
            ]
        case .country:
            return [
                LegendItem(color: .blue, size: 14, label: "Colored by country"),
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
