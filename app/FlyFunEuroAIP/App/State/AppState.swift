//
//  AppState.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import SwiftUI
import MapKit
import RZFlight
import OSLog
import RZUtilsSwift

/// Single source of truth for all app state
/// Composes domain objects to avoid becoming a god-class
///
/// Usage:
/// ```swift
/// @Environment(\.appState) private var state
/// state.airports.select(airport)
/// state.navigation.showChat()
/// ```
@Observable
@MainActor
final class AppState {
    // MARK: - Composed Domains
    
    /// Airport data, filters, and map state
    let airports: AirportDomain
    
    /// Chat messages and streaming
    let chat: ChatDomain
    
    /// Navigation state (tabs, sheets, paths)
    let navigation: NavigationDomain
    
    /// System state (connectivity, errors, loading)
    let system: SystemDomain
    
    /// User preferences and session state
    let settings: SettingsDomain
    
    // MARK: - Dependencies (kept for reference)
    private let repository: AirportRepositoryProtocol
    
    // MARK: - Init
    
    init(
        repository: AirportRepositoryProtocol,
        connectivityMonitor: ConnectivityMonitor
    ) {
        self.repository = repository
        
        // Initialize domains
        self.airports = AirportDomain(repository: repository)
        self.chat = ChatDomain()
        self.navigation = NavigationDomain()
        self.system = SystemDomain(connectivityMonitor: connectivityMonitor)
        self.settings = SettingsDomain()
        
        // Wire up cross-domain communication
        setupCrossDomainWiring()
    }
    
    // MARK: - Cross-Domain Wiring
    
    private func setupCrossDomainWiring() {
        // Chat visualization → Airport visualization
        chat.onVisualization = { [weak self] payload in
            self?.airports.applyVisualization(payload)
        }
    }
    
    // MARK: - Lifecycle
    
    /// Called when app appears - initialize state
    func onAppear() async {
        Logger.app.info("AppState.onAppear")
        
        system.startMonitoring()
        system.setLoading(true)
        defer { system.setLoading(false) }
        
        // Restore session state if enabled
        if settings.restoreSessionOnLaunch {
            navigation.selectedTab = settings.lastTab
            airports.mapPosition = .region(settings.lastMapRegion)
            airports.filters = settings.defaultFilters
            airports.legendMode = settings.defaultLegendMode
        }
        
        do {
            try await airports.load()
            
            // Restore selected airport if any
            if settings.restoreSessionOnLaunch,
               let icao = settings.lastSelectedAirportICAO {
                if let airport = airports.airports.first(where: { $0.icao == icao }) {
                    airports.select(airport)
                }
            }
            
            Logger.app.info("AppState initialized successfully")
        } catch {
            system.setError(error)
            Logger.app.error("AppState initialization failed: \(error.localizedDescription)")
        }
    }
    
    /// Called when app disappears - save state
    func onDisappear() {
        Logger.app.info("AppState.onDisappear - saving session")
        
        settings.saveSessionState(
            mapRegion: airports.visibleRegion,
            selectedAirportICAO: airports.selectedAirport?.icao,
            selectedTab: navigation.selectedTab
        )
        
        system.stopMonitoring()
    }
}

// MARK: - Environment Key

private struct AppStateKey: EnvironmentKey {
    static let defaultValue: AppState? = nil
}

extension EnvironmentValues {
    var appState: AppState? {
        get { self[AppStateKey.self] }
        set { self[AppStateKey.self] = newValue }
    }
}

// MARK: - Preview Helper

extension AppState {
    /// Create a preview AppState with mock data
    @MainActor
    static func preview() -> AppState {
        // For previews, we need mock implementations
        // This will be fleshed out with PreviewFactory later
        fatalError("Use PreviewFactory.makeAppState() instead")
    }
}

