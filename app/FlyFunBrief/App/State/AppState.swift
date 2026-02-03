//
//  AppState.swift
//  FlyFunBrief
//
//  Single source of truth for all app state.
//  Composes domain objects following FlyFunEuroAIP patterns.
//

import Foundation
import SwiftUI
import RZFlight
import CoreData
import CoreLocation
import OSLog
import FMDB

/// Single source of truth for all FlyFunBrief state
/// Composes domain objects to avoid becoming a god-class
///
/// Usage:
/// ```swift
/// @Environment(\.appState) private var state
/// state.flights.createFlight(origin: "LFPG", destination: "EGLL")
/// state.briefing.importBriefing(from: url)
/// ```
@Observable
@MainActor
final class AppState {
    // MARK: - Composed Domains

    /// Flight management (create, edit, archive)
    let flights: FlightDomain

    /// Current briefing, parsing state, and import handling
    let briefing: BriefingDomain

    /// NOTAM list, filtering, user annotations
    let notams: NotamDomain

    /// Navigation state (tabs, sheets, detail selection)
    let navigation: NavigationDomain

    /// User preferences
    let settings: SettingsDomain

    // MARK: - Services

    /// Service for API communication
    let briefingService: BriefingService

    /// Global NOTAM ignore list manager
    let ignoreListManager: IgnoreListManager

    /// Global NOTAM read tracking manager
    let globalReadManager: GlobalReadManager

    /// Core Data persistence controller with CloudKit sync
    let persistenceController: PersistenceController

    /// Flight repository for Core Data operations
    let flightRepository: FlightRepository

    /// Airport database for coordinate lookups
    let knownAirports: KnownAirports?

    // MARK: - Pending Import State

    /// Briefing waiting to be assigned to a flight (from share extension)
    var pendingBriefing: Briefing?

    // MARK: - Init

    init() {
        // Initialize persistence
        self.persistenceController = PersistenceController.shared
        self.flightRepository = FlightRepository(persistenceController: persistenceController)
        self.ignoreListManager = IgnoreListManager(persistenceController: persistenceController)
        self.globalReadManager = GlobalReadManager(persistenceController: persistenceController)

        // Initialize services
        self.briefingService = BriefingService()

        // Initialize airport database
        if let dbPath = Bundle.main.path(forResource: "airports", ofType: "db") {
            let db = FMDatabase(path: dbPath)
            if db.open() {
                self.knownAirports = KnownAirports(db: db)
                Logger.app.info("Initialized KnownAirports from bundled database")
            } else {
                self.knownAirports = nil
                Logger.app.warning("Failed to open airports.db - route display will be limited")
            }
        } else {
            self.knownAirports = nil
            Logger.app.warning("airports.db not found in bundle - route display will be limited")
        }

        // Initialize domains
        self.flights = FlightDomain(repository: flightRepository)
        self.briefing = BriefingDomain(service: briefingService)
        self.notams = NotamDomain(flightRepository: flightRepository, ignoreListManager: ignoreListManager, globalReadManager: globalReadManager)
        self.navigation = NavigationDomain()
        self.settings = SettingsDomain()

        // Wire up cross-domain communication
        setupCrossDomainWiring()

        // Sync settings to NotamDomain
        syncResurfaceSettings()
        syncPriorityProfile()

        // Configure service URLs from secrets
        Task {
            await briefingService.configure(baseURL: SecretsManager.shared.apiBaseURL)
        }
    }

    // MARK: - Cross-Domain Wiring

    private func setupCrossDomainWiring() {
        // When briefing is parsed, store in Core Data (or prompt for flight selection)
        briefing.onBriefingParsed = { [weak self] parsedBriefing in
            guard let self = self else { return nil }

            // If actively viewing a flight, import directly to that flight
            if self.navigation.isViewingFlight, let flight = self.flights.selectedFlight {
                return await self.flights.importBriefing(parsedBriefing, for: flight)
            }

            // No flight selected - store as pending and prompt user
            Logger.app.info("No flight selected - storing pending briefing for assignment")
            self.pendingBriefing = parsedBriefing

            // Show flight picker to let user choose
            self.navigation.showFlightPicker()

            return nil
        }

        // When briefing is loaded (from parsing or Core Data), update notams domain
        briefing.onBriefingLoaded = { [weak self] loadedBriefing in
            guard let self = self else { return }

            // Check if we have a Core Data briefing with status info
            if let cdBriefing = self.briefing.currentCDBriefing,
               let flight = cdBriefing.flight {
                let previousKeys = self.flights.getPreviousIdentityKeys(for: flight, excluding: cdBriefing)
                self.notams.setBriefing(loadedBriefing, cdBriefing: cdBriefing, previousKeys: previousKeys)
            } else {
                self.notams.setBriefing(loadedBriefing)
            }

            // Update flight context for priority evaluation
            self.updateFlightContext()

            self.navigation.showNotamList()
        }

        // When briefing is cleared, clear notams
        briefing.onBriefingCleared = { [weak self] in
            self?.notams.clearBriefing()
        }

        // When a flight is selected, enter flight view mode and load its latest briefing
        flights.onFlightSelected = { [weak self] flight in
            guard let self = self else { return }

            // Enter flight view mode
            if let flightId = flight.id {
                self.navigation.enterFlightView(flightId: flightId)
            }

            // Load latest briefing if available
            if let latestBriefing = flight.latestBriefing {
                self.briefing.loadBriefing(latestBriefing)
                // Note: updateFlightContext() will be called in onBriefingLoaded
            } else {
                // No briefing yet - still update context with flight info
                self.updateFlightContext()
            }
        }

        // When a briefing is imported to Core Data, notify briefing domain
        flights.onBriefingImported = { [weak self] cdBriefing in
            guard let self = self else { return }

            // Update the current CD briefing reference
            self.briefing.currentCDBriefing = cdBriefing

            // If the briefing is already decoded, refresh the notams
            if let briefing = cdBriefing.decodedBriefing,
               let flight = cdBriefing.flight {
                let previousKeys = self.flights.getPreviousIdentityKeys(for: flight, excluding: cdBriefing)
                self.notams.setBriefing(briefing, cdBriefing: cdBriefing, previousKeys: previousKeys)

                // Update flight context for priority evaluation
                self.updateFlightContext()
            }
        }
    }

    // MARK: - Pending Briefing Actions

    /// Assign pending briefing to a flight
    /// Called when user selects a flight from the picker after sharing
    func assignPendingBriefing(to flight: CDFlight) async {
        guard let briefingToAssign = pendingBriefing else {
            Logger.app.warning("No pending briefing to assign")
            return
        }

        Logger.app.info("Assigning pending briefing to flight: \(flight.displayTitle)")

        // Clear pending state
        pendingBriefing = nil

        // Dismiss the picker
        navigation.dismissSheet()

        // Select the flight
        flights.selectFlight(flight)

        // Import the briefing
        if let cdBriefing = await flights.importBriefing(briefingToAssign, for: flight) {
            // Update briefing domain
            briefing.currentCDBriefing = cdBriefing

            // Update notams
            let previousKeys = flights.getPreviousIdentityKeys(for: flight, excluding: cdBriefing)
            notams.setBriefing(briefingToAssign, cdBriefing: cdBriefing, previousKeys: previousKeys)

            // Update flight context for priority evaluation
            updateFlightContext()

            // Navigate to NOTAM list
            navigation.showNotamList()

            Logger.app.info("Successfully assigned briefing to flight")
        }
    }

    /// Create a new flight from the pending briefing's route
    func createFlightFromPendingBriefing() async {
        guard let briefingToAssign = pendingBriefing else {
            Logger.app.warning("No pending briefing to create flight from")
            return
        }

        Logger.app.info("Creating new flight from pending briefing")

        // Extract route info from briefing
        let origin = briefingToAssign.route?.departure ?? "XXXX"
        let destination = briefingToAssign.route?.destination ?? "XXXX"
        let departureTime = briefingToAssign.route?.departureTime

        // Create the flight
        guard let newFlight = await flights.createFlight(
            origin: origin,
            destination: destination,
            departureTime: departureTime
        ) else {
            Logger.app.error("Failed to create flight from pending briefing")
            return
        }

        // Now assign the briefing to this new flight
        await assignPendingBriefing(to: newFlight)
    }

    /// Cancel pending briefing import
    func cancelPendingBriefing() {
        pendingBriefing = nil
        navigation.dismissSheet()
        Logger.app.info("Cancelled pending briefing import")
    }

    // MARK: - Settings Sync

    /// Sync resurface settings from SettingsDomain to NotamDomain
    func syncResurfaceSettings() {
        notams.resurfaceSettings = settings.resurfaceSettings
    }

    /// Sync priority profile from SettingsDomain to NotamDomain
    func syncPriorityProfile() {
        notams.setProfile(settings.priorityProfile)

        // Wire up future changes
        settings.onProfileChanged = { [weak self] profile in
            self?.notams.setProfile(profile)
        }
    }

    // MARK: - Flight Context

    /// Build FlightContext from current flight and briefing for priority evaluation.
    ///
    /// This combines:
    /// - Route coordinates from CDFlight using KnownAirports lookups
    /// - Cruise altitude from CDFlight
    /// - Departure/arrival times from Route or CDFlight
    /// - Alternates from Route
    private func buildFlightContext() -> FlightContext {
        guard let flight = flights.selectedFlight else {
            return .empty
        }

        // Build route coordinates from CDFlight using KnownAirports
        var routeCoordinates: [CLLocationCoordinate2D] = []

        if let airports = knownAirports {
            // Origin
            if let origin = flight.origin,
               let airport = airports.airport(icao: origin, ensureRunway: false) {
                routeCoordinates.append(airport.coordinate)
            }

            // Intermediate waypoints from CDFlight
            for icao in flight.routeArray {
                if let airport = airports.airport(icao: icao, ensureRunway: false) {
                    routeCoordinates.append(airport.coordinate)
                }
            }

            // Destination
            if let destination = flight.destination,
               let airport = airports.airport(icao: destination, ensureRunway: false) {
                routeCoordinates.append(airport.coordinate)
            }
        }

        // Get times from flight
        let departureTime = flight.departureTime
        let arrivalTime: Date? = if let depTime = departureTime, flight.durationHours > 0 {
            depTime.addingTimeInterval(flight.durationHours * 3600)
        } else {
            nil
        }

        // Note: Alternates are not currently stored in CDFlight
        // Future enhancement: add alternates field to CDFlight
        let alternates: [String] = []

        return FlightContext(
            routeCoordinates: routeCoordinates,
            departureICAO: flight.origin,
            destinationICAO: flight.destination,
            alternateICAOs: alternates,
            cruiseAltitude: flight.cruiseAltitude > 0 ? Int(flight.cruiseAltitude) : nil,
            departureTime: departureTime,
            arrivalTime: arrivalTime
        )
    }

    /// Update the flight context for NOTAM priority evaluation.
    /// Call this after flight selection or briefing load.
    private func updateFlightContext() {
        let context = buildFlightContext()
        notams.setFlightContext(context)
        Logger.app.debug("Updated flight context: hasRoute=\(context.hasValidRoute), altitude=\(context.cruiseAltitude ?? 0)")
    }

    // MARK: - Lifecycle

    /// Called when app appears
    func onAppear() async {
        Logger.app.info("AppState.onAppear")

        // Load flights from Core Data
        await flights.loadFlights()

        // Restore settings
        settings.restore()

        // Cleanup expired ignores and stale global reads periodically
        try? ignoreListManager.cleanupExpired()
        try? globalReadManager.cleanupStale()

        Logger.app.info("AppState initialized successfully")
    }

    /// Called when app disappears
    func onDisappear() {
        Logger.app.info("AppState.onDisappear - saving state")
        settings.save()
        persistenceController.save()
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
        AppState()
    }
}
