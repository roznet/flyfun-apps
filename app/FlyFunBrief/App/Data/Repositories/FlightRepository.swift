//
//  FlightRepository.swift
//  FlyFunBrief
//
//  CRUD operations for Flight entities via Core Data.
//

import Foundation
import CoreData
import RZFlight
import OSLog

/// Repository for Flight CRUD operations
@MainActor
final class FlightRepository {
    // MARK: - Properties

    private let persistenceController: PersistenceController

    private var viewContext: NSManagedObjectContext {
        persistenceController.viewContext
    }

    // MARK: - Initialization

    init(persistenceController: PersistenceController = .shared) {
        self.persistenceController = persistenceController
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
    ) throws -> CDFlight {
        let flight = CDFlight.create(
            in: viewContext,
            origin: origin,
            destination: destination,
            departureTime: departureTime,
            durationHours: durationHours,
            routeICAOs: routeICAOs,
            cruiseAltitude: cruiseAltitude
        )

        try viewContext.save()
        Logger.persistence.info("Created flight: \(flight.displayTitle)")
        return flight
    }

    /// Update an existing flight
    func updateFlight(
        _ flight: CDFlight,
        origin: String? = nil,
        destination: String? = nil,
        departureTime: Date? = nil,
        durationHours: Double? = nil,
        routeICAOs: String? = nil,
        cruiseAltitude: Int32? = nil,
        isArchived: Bool? = nil
    ) throws {
        if let origin = origin { flight.origin = origin.uppercased() }
        if let destination = destination { flight.destination = destination.uppercased() }
        if let departureTime = departureTime { flight.departureTime = departureTime }
        if let durationHours = durationHours { flight.durationHours = durationHours }
        if let routeICAOs = routeICAOs { flight.routeICAOs = routeICAOs.uppercased() }
        if let cruiseAltitude = cruiseAltitude { flight.cruiseAltitude = cruiseAltitude }
        if let isArchived = isArchived { flight.isArchived = isArchived }

        try viewContext.save()
        Logger.persistence.info("Updated flight: \(flight.displayTitle)")
    }

    /// Delete a flight and all its briefings
    func deleteFlight(_ flight: CDFlight) throws {
        let title = flight.displayTitle
        viewContext.delete(flight)
        try viewContext.save()
        Logger.persistence.info("Deleted flight: \(title)")
    }

    /// Archive a flight
    func archiveFlight(_ flight: CDFlight) throws {
        try updateFlight(flight, isArchived: true)
    }

    /// Unarchive a flight
    func unarchiveFlight(_ flight: CDFlight) throws {
        try updateFlight(flight, isArchived: false)
    }

    /// Find flight by ID
    func findFlight(id: UUID) -> CDFlight? {
        CDFlight.find(id: id, in: viewContext)
    }

    // MARK: - Fetch

    /// Fetch all active (non-archived) flights
    func fetchActiveFlights() throws -> [CDFlight] {
        try viewContext.fetch(CDFlight.activeFlightsFetchRequest())
    }

    /// Fetch archived flights
    func fetchArchivedFlights() throws -> [CDFlight] {
        try viewContext.fetch(CDFlight.archivedFlightsFetchRequest())
    }

    // MARK: - Briefing Operations

    /// Import a briefing for a flight
    @discardableResult
    func importBriefing(
        _ briefing: Briefing,
        for flight: CDFlight
    ) throws -> CDBriefing {
        // Create the briefing
        let cdBriefing = try CDBriefing.create(in: viewContext, from: briefing, flight: flight)

        // Get previous briefing's statuses for status transfer
        let previousStatuses = getPreviousStatuses(for: flight, excluding: cdBriefing)

        // Create statuses for each NOTAM, transferring from previous where possible
        for notam in briefing.notams {
            let identityKey = NotamIdentity.key(for: notam)

            if let previousStatus = previousStatuses[identityKey] {
                // Copy status from previous briefing
                CDNotamStatus.copy(from: previousStatus, to: cdBriefing, notamId: notam.id, in: viewContext)
            } else {
                // New NOTAM, create fresh status
                CDNotamStatus.create(in: viewContext, notam: notam, briefing: cdBriefing, status: .unread)
            }
        }

        try viewContext.save()
        Logger.persistence.info("Imported briefing with \(briefing.notams.count) NOTAMs for flight \(flight.displayTitle)")

        return cdBriefing
    }

    /// Get statuses from previous briefings keyed by identity key
    private func getPreviousStatuses(for flight: CDFlight, excluding currentBriefing: CDBriefing) -> [String: CDNotamStatus] {
        var statuses: [String: CDNotamStatus] = [:]

        for briefing in flight.sortedBriefings where briefing != currentBriefing {
            for (key, status) in briefing.statusesByIdentityKey {
                // Only take the first (most recent) status for each identity key
                if statuses[key] == nil {
                    statuses[key] = status
                }
            }
        }

        return statuses
    }

    /// Get identity keys from previous briefings
    func getPreviousIdentityKeys(for flight: CDFlight, excluding currentBriefing: CDBriefing?) -> Set<String> {
        var keys: Set<String> = []

        for briefing in flight.sortedBriefings {
            if let current = currentBriefing, briefing == current { continue }
            for key in briefing.statusesByIdentityKey.keys {
                keys.insert(key)
            }
        }

        return keys
    }

    // MARK: - Status Operations

    /// Update NOTAM status in a briefing
    func updateNotamStatus(
        _ notam: Notam,
        briefing: CDBriefing,
        status: NotamStatus,
        textNote: String? = nil
    ) throws {
        let identityKey = NotamIdentity.key(for: notam)

        if let cdStatus = CDNotamStatus.find(notamId: notam.id, briefing: briefing, in: viewContext) {
            cdStatus.statusEnum = status
            cdStatus.identityKey = identityKey
            if let note = textNote {
                cdStatus.textNote = note
            }
        } else {
            CDNotamStatus.create(in: viewContext, notam: notam, briefing: briefing, status: status)
        }

        try viewContext.save()
    }

    // MARK: - Flight-Level Status Propagation

    /// Propagate a status to all briefings in a flight (for important/followUp).
    ///
    /// This ensures that important and followUp statuses persist across briefings
    /// within the same flight, treating them as flight-level annotations.
    ///
    /// - Parameters:
    ///   - notam: The NOTAM to update
    ///   - status: The status to propagate (typically .important or .followUp)
    ///   - flight: The flight containing the briefings
    ///   - excludingBriefing: Optional briefing to skip (usually the current one, already updated)
    func propagateStatusAcrossBriefings(
        _ notam: Notam,
        status: NotamStatus,
        flight: CDFlight,
        excludingBriefing: CDBriefing? = nil
    ) throws {
        let identityKey = NotamIdentity.key(for: notam)

        for briefing in flight.sortedBriefings {
            // Skip the excluded briefing (already updated)
            if let exclude = excludingBriefing, briefing == exclude {
                continue
            }

            // Find existing status or create new one
            if let cdStatus = CDNotamStatus.find(identityKey: identityKey, briefing: briefing, in: viewContext) {
                // Update existing status
                cdStatus.statusEnum = status
            } else {
                // Create new status record - use the notam.id for this briefing
                // Note: The NOTAM might have a different ID in different briefings,
                // but we match by identityKey for consistency
                let newStatus = CDNotamStatus(context: viewContext)
                newStatus.id = UUID()
                newStatus.notamId = notam.id
                newStatus.identityKey = identityKey
                newStatus.status = status.rawValue
                newStatus.updatedAt = Date()
                newStatus.briefing = briefing
            }
        }

        try viewContext.save()
        Logger.persistence.info("Propagated \(status.rawValue) status across \(flight.sortedBriefings.count) briefings")
    }
}
