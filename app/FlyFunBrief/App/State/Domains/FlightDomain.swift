//
//  FlightDomain.swift
//  FlyFunBrief
//
//  Manages flight list state and operations.
//

import Foundation
import CoreData
import RZFlight
import OSLog

/// Domain for flight list management
@Observable
@MainActor
final class FlightDomain {
    // MARK: - State

    /// All active (non-archived) flights
    private(set) var flights: [CDFlight] = []

    /// Archived flights (loaded on demand)
    private(set) var archivedFlights: [CDFlight] = []

    /// Currently selected flight
    var selectedFlight: CDFlight?

    /// Whether flights are loading
    private(set) var isLoading = false

    /// Error from last operation
    private(set) var lastError: Error?

    // MARK: - Callbacks

    /// Called when a flight is selected
    var onFlightSelected: ((CDFlight) -> Void)?

    /// Called when a new briefing is imported
    var onBriefingImported: ((CDBriefing) -> Void)?

    // MARK: - Dependencies

    private let repository: FlightRepository

    // MARK: - Initialization

    init(repository: FlightRepository) {
        self.repository = repository
    }

    // MARK: - Loading

    /// Load all active flights
    func loadFlights() async {
        isLoading = true
        lastError = nil

        do {
            flights = try repository.fetchActiveFlights()
            Logger.app.info("Loaded \(self.flights.count) active flights")
        } catch {
            Logger.app.error("Failed to load flights: \(error.localizedDescription)")
            lastError = error
        }

        isLoading = false
    }

    /// Load archived flights
    func loadArchivedFlights() async {
        do {
            archivedFlights = try repository.fetchArchivedFlights()
            Logger.app.info("Loaded \(self.archivedFlights.count) archived flights")
        } catch {
            Logger.app.error("Failed to load archived flights: \(error.localizedDescription)")
            lastError = error
        }
    }

    /// Refresh flights from Core Data
    func refresh() async {
        await loadFlights()
    }

    // MARK: - Flight CRUD

    /// Create a new flight
    @discardableResult
    func createFlight(
        origin: String,
        destination: String,
        departureTime: Date? = nil,
        durationHours: Double? = nil,
        routeICAOs: String? = nil,
        cruiseAltitude: Int32? = nil
    ) async -> CDFlight? {
        lastError = nil

        do {
            let flight = try repository.createFlight(
                origin: origin,
                destination: destination,
                departureTime: departureTime,
                durationHours: durationHours,
                routeICAOs: routeICAOs,
                cruiseAltitude: cruiseAltitude
            )

            // Reload flights to get sorted list
            await loadFlights()

            return flight
        } catch {
            Logger.app.error("Failed to create flight: \(error.localizedDescription)")
            lastError = error
            return nil
        }
    }

    /// Update a flight
    func updateFlight(
        _ flight: CDFlight,
        origin: String? = nil,
        destination: String? = nil,
        departureTime: Date? = nil,
        durationHours: Double? = nil,
        routeICAOs: String? = nil,
        cruiseAltitude: Int32? = nil
    ) async {
        lastError = nil

        do {
            try repository.updateFlight(
                flight,
                origin: origin,
                destination: destination,
                departureTime: departureTime,
                durationHours: durationHours,
                routeICAOs: routeICAOs,
                cruiseAltitude: cruiseAltitude
            )

            // Reload to update sorting
            await loadFlights()
        } catch {
            Logger.app.error("Failed to update flight: \(error.localizedDescription)")
            lastError = error
        }
    }

    /// Delete a flight
    func deleteFlight(_ flight: CDFlight) async {
        lastError = nil

        // Deselect if currently selected
        if selectedFlight == flight {
            selectedFlight = nil
        }

        do {
            try repository.deleteFlight(flight)
            await loadFlights()
        } catch {
            Logger.app.error("Failed to delete flight: \(error.localizedDescription)")
            lastError = error
        }
    }

    /// Archive a flight
    func archiveFlight(_ flight: CDFlight) async {
        lastError = nil

        // Deselect if currently selected
        if selectedFlight == flight {
            selectedFlight = nil
        }

        do {
            try repository.archiveFlight(flight)
            await loadFlights()
        } catch {
            Logger.app.error("Failed to archive flight: \(error.localizedDescription)")
            lastError = error
        }
    }

    /// Unarchive a flight
    func unarchiveFlight(_ flight: CDFlight) async {
        lastError = nil

        do {
            try repository.unarchiveFlight(flight)
            await loadFlights()
            await loadArchivedFlights()
        } catch {
            Logger.app.error("Failed to unarchive flight: \(error.localizedDescription)")
            lastError = error
        }
    }

    // MARK: - Selection

    /// Select a flight for preview (does NOT enter flight view)
    func selectFlight(_ flight: CDFlight) {
        selectedFlight = flight
    }

    /// Select a flight AND enter flight view mode
    func openFlight(_ flight: CDFlight) {
        selectedFlight = flight
        onFlightSelected?(flight)
    }

    /// Clear flight selection
    func clearSelection() {
        selectedFlight = nil
    }

    // MARK: - Briefing Import

    /// Import a briefing for the selected flight
    @discardableResult
    func importBriefing(_ briefing: Briefing) async -> CDBriefing? {
        guard let flight = selectedFlight else {
            Logger.app.error("No flight selected for briefing import")
            return nil
        }

        return await importBriefing(briefing, for: flight)
    }

    /// Import a briefing for a specific flight
    @discardableResult
    func importBriefing(_ briefing: Briefing, for flight: CDFlight) async -> CDBriefing? {
        lastError = nil

        do {
            let cdBriefing = try repository.importBriefing(briefing, for: flight)

            // Refresh flights to update counts
            await loadFlights()

            onBriefingImported?(cdBriefing)
            return cdBriefing
        } catch {
            Logger.app.error("Failed to import briefing: \(error.localizedDescription)")
            lastError = error
            return nil
        }
    }

    // MARK: - Flight from Briefing

    /// Create a flight from a briefing (auto-populate from route)
    @discardableResult
    func createFlightFromBriefing(_ briefing: Briefing) async -> CDFlight? {
        guard let route = briefing.route else {
            Logger.app.error("Briefing has no route, cannot create flight")
            return nil
        }

        // Build route string from all airports
        var routeICAOs = [route.departure, route.destination]
        routeICAOs.append(contentsOf: route.alternates)

        let flight = await createFlight(
            origin: route.departure,
            destination: route.destination,
            departureTime: route.departureTime,
            routeICAOs: routeICAOs.joined(separator: " ")
        )

        if let flight = flight {
            selectFlight(flight)
        }

        return flight
    }

    // MARK: - Helpers

    /// Get previous identity keys for a flight (for new NOTAM detection)
    func getPreviousIdentityKeys(for flight: CDFlight, excluding briefing: CDBriefing?) -> Set<String> {
        repository.getPreviousIdentityKeys(for: flight, excluding: briefing)
    }
}
