//
//  SettingsDomain.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import SwiftUI
import MapKit

/// Domain: User preferences and persisted state
/// Uses @AppStorage for automatic persistence
/// This is a composed part of AppState, not a standalone ViewModel.
@Observable
@MainActor
final class SettingsDomain {
    
    // MARK: - Unit Preferences
    
    @ObservationIgnored
    @AppStorage("units.distance") private var _distanceUnit: String = DistanceUnit.nauticalMiles.rawValue
    
    @ObservationIgnored
    @AppStorage("units.altitude") private var _altitudeUnit: String = AltitudeUnit.feet.rawValue
    
    @ObservationIgnored
    @AppStorage("units.runway") private var _runwayUnit: String = RunwayUnit.feet.rawValue
    
    var distanceUnit: DistanceUnit {
        get { DistanceUnit(rawValue: _distanceUnit) ?? .nauticalMiles }
        set { _distanceUnit = newValue.rawValue }
    }
    
    var altitudeUnit: AltitudeUnit {
        get { AltitudeUnit(rawValue: _altitudeUnit) ?? .feet }
        set { _altitudeUnit = newValue.rawValue }
    }
    
    var runwayUnit: RunwayUnit {
        get { RunwayUnit(rawValue: _runwayUnit) ?? .feet }
        set { _runwayUnit = newValue.rawValue }
    }
    
    // MARK: - Default Filters
    
    @ObservationIgnored
    @AppStorage("defaults.legendMode") private var _defaultLegendMode: String = LegendMode.airportType.rawValue
    
    @ObservationIgnored
    @AppStorage("defaults.filterOnlyProcedures") private var _defaultOnlyProcedures: Bool = false
    
    @ObservationIgnored
    @AppStorage("defaults.filterOnlyBorderCrossing") private var _defaultOnlyBorderCrossing: Bool = false
    
    @ObservationIgnored
    @AppStorage("defaults.filterCountry") private var _defaultCountry: String = ""
    
    var defaultLegendMode: LegendMode {
        get { LegendMode(rawValue: _defaultLegendMode) ?? .airportType }
        set { _defaultLegendMode = newValue.rawValue }
    }
    
    var defaultFilters: FilterConfig {
        var config = FilterConfig.default
        if _defaultOnlyProcedures { config.hasProcedures = true }
        if _defaultOnlyBorderCrossing { config.pointOfEntry = true }
        if !_defaultCountry.isEmpty { config.country = _defaultCountry }
        return config
    }
    
    func setDefaultFilter(onlyProcedures: Bool) {
        _defaultOnlyProcedures = onlyProcedures
    }
    
    func setDefaultFilter(onlyBorderCrossing: Bool) {
        _defaultOnlyBorderCrossing = onlyBorderCrossing
    }
    
    func setDefaultFilter(country: String?) {
        _defaultCountry = country ?? ""
    }
    
    // MARK: - Last Session State (Restore on Launch)
    
    @ObservationIgnored
    @AppStorage("session.lastMapLatitude") private var _lastMapLatitude: Double = 50.0
    
    @ObservationIgnored
    @AppStorage("session.lastMapLongitude") private var _lastMapLongitude: Double = 10.0
    
    @ObservationIgnored
    @AppStorage("session.lastMapSpan") private var _lastMapSpan: Double = 30.0
    
    @ObservationIgnored
    @AppStorage("session.lastSelectedAirport") private var _lastSelectedAirport: String = ""
    
    @ObservationIgnored
    @AppStorage("session.lastTab") private var _lastTab: String = "map"
    
    var lastMapRegion: MKCoordinateRegion {
        get {
            MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: _lastMapLatitude, longitude: _lastMapLongitude),
                span: MKCoordinateSpan(latitudeDelta: _lastMapSpan, longitudeDelta: _lastMapSpan)
            )
        }
        set {
            _lastMapLatitude = newValue.center.latitude
            _lastMapLongitude = newValue.center.longitude
            _lastMapSpan = newValue.span.latitudeDelta
        }
    }
    
    var lastSelectedAirportICAO: String? {
        get { _lastSelectedAirport.isEmpty ? nil : _lastSelectedAirport }
        set { _lastSelectedAirport = newValue ?? "" }
    }
    
    var lastTab: NavigationDomain.Tab {
        get { NavigationDomain.Tab(rawValue: _lastTab) ?? .map }
        set { _lastTab = newValue.rawValue }
    }
    
    // MARK: - Behavior Preferences
    
    @ObservationIgnored
    @AppStorage("behavior.restoreSession") var restoreSessionOnLaunch: Bool = true
    
    @ObservationIgnored
    @AppStorage("behavior.autoSync") var autoSyncDatabase: Bool = true
    
    @ObservationIgnored
    @AppStorage("behavior.showOfflineBanner") var showOfflineBanner: Bool = true
    
    // MARK: - Chatbot Preferences
    
    @ObservationIgnored
    @AppStorage("chatbot.saveHistory") var saveChatHistory: Bool = false
    
    @ObservationIgnored
    @AppStorage("chatbot.showThinking") var showChatbotThinking: Bool = true
    
    // MARK: - Init
    
    init() {}
    
    // MARK: - Actions
    
    /// Save current session state for restoration
    func saveSessionState(
        mapRegion: MKCoordinateRegion?,
        selectedAirportICAO: String?,
        selectedTab: NavigationDomain.Tab
    ) {
        if let region = mapRegion {
            lastMapRegion = region
        }
        lastSelectedAirportICAO = selectedAirportICAO
        lastTab = selectedTab
    }
    
    // MARK: - Unit Types
    
    enum DistanceUnit: String, CaseIterable, Identifiable, Sendable {
        case nauticalMiles = "nm"
        case kilometers = "km"
        case miles = "mi"
        
        var id: String { rawValue }
        
        var displayName: String {
            switch self {
            case .nauticalMiles: return "Nautical Miles"
            case .kilometers: return "Kilometers"
            case .miles: return "Miles"
            }
        }
        
        var abbreviation: String {
            switch self {
            case .nauticalMiles: return "NM"
            case .kilometers: return "km"
            case .miles: return "mi"
            }
        }
    }
    
    enum AltitudeUnit: String, CaseIterable, Identifiable, Sendable {
        case feet = "feet"
        case meters = "meters"
        
        var id: String { rawValue }
        
        var displayName: String {
            switch self {
            case .feet: return "Feet"
            case .meters: return "Meters"
            }
        }
        
        var abbreviation: String {
            switch self {
            case .feet: return "ft"
            case .meters: return "m"
            }
        }
    }
    
    enum RunwayUnit: String, CaseIterable, Identifiable, Sendable {
        case feet = "feet"
        case meters = "meters"
        
        var id: String { rawValue }
        
        var displayName: String {
            switch self {
            case .feet: return "Feet"
            case .meters: return "Meters"
            }
        }
        
        var abbreviation: String {
            switch self {
            case .feet: return "ft"
            case .meters: return "m"
            }
        }
    }
}

// MARK: - Unit Conversion Helpers

extension SettingsDomain {
    /// Convert distance to user's preferred unit
    func formatDistance(_ nauticalMiles: Double) -> String {
        switch distanceUnit {
        case .nauticalMiles:
            return String(format: "%.1f NM", nauticalMiles)
        case .kilometers:
            return String(format: "%.1f km", nauticalMiles * 1.852)
        case .miles:
            return String(format: "%.1f mi", nauticalMiles * 1.15078)
        }
    }
    
    /// Convert altitude to user's preferred unit
    func formatAltitude(_ feet: Int) -> String {
        switch altitudeUnit {
        case .feet:
            return "\(feet) ft"
        case .meters:
            return "\(Int(Double(feet) * 0.3048)) m"
        }
    }
    
    /// Convert runway length to user's preferred unit
    func formatRunwayLength(_ feet: Int) -> String {
        switch runwayUnit {
        case .feet:
            return "\(feet) ft"
        case .meters:
            return "\(Int(Double(feet) * 0.3048)) m"
        }
    }
}

