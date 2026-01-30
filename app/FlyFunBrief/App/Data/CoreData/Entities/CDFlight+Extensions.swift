//
//  CDFlight+Extensions.swift
//  FlyFunBrief
//
//  Core Data CDFlight entity convenience extensions.
//

import Foundation
import CoreData

extension CDFlight {
    // MARK: - Convenience Initializer

    /// Create a new flight with required fields
    @discardableResult
    static func create(
        in context: NSManagedObjectContext,
        origin: String,
        destination: String,
        departureTime: Date? = nil,
        durationHours: Double? = nil,
        routeICAOs: String? = nil,
        cruiseAltitude: Int32? = nil
    ) -> CDFlight {
        let flight = CDFlight(context: context)
        flight.id = UUID()
        flight.origin = origin.uppercased()
        flight.destination = destination.uppercased()
        flight.departureTime = departureTime
        flight.durationHours = durationHours ?? 0
        flight.routeICAOs = routeICAOs?.uppercased()
        flight.cruiseAltitude = cruiseAltitude ?? 0
        flight.createdAt = Date()
        flight.isArchived = false
        return flight
    }

    // MARK: - Computed Properties

    /// Route as array of ICAO codes
    var routeArray: [String] {
        get {
            guard let route = routeICAOs, !route.isEmpty else { return [] }
            return route.components(separatedBy: " ").filter { !$0.isEmpty }
        }
        set {
            routeICAOs = newValue.isEmpty ? nil : newValue.joined(separator: " ")
        }
    }

    /// Display title for the flight
    var displayTitle: String {
        guard let origin = origin, let destination = destination else {
            return "Unknown Flight"
        }
        return "\(origin) \u{2192} \(destination)"
    }

    /// All briefings sorted by import date (newest first)
    var sortedBriefings: [CDBriefing] {
        guard let briefingsSet = briefings as? Set<CDBriefing> else { return [] }
        return briefingsSet.sorted { ($0.importedAt ?? .distantPast) > ($1.importedAt ?? .distantPast) }
    }

    /// The most recent briefing
    var latestBriefing: CDBriefing? {
        sortedBriefings.first
    }

    /// Count of unread NOTAMs across all briefings in latest briefing
    var unreadNotamCount: Int {
        guard let latest = latestBriefing,
              let statuses = latest.notamStatuses as? Set<CDNotamStatus> else { return 0 }
        return statuses.filter { $0.status == NotamStatus.unread.rawValue }.count
    }

    /// Count of new NOTAMs (not seen in previous briefings)
    var newNotamCount: Int {
        // This will be computed when loading the briefing by checking identity keys
        // For display, we track this in the briefing itself
        guard let latest = latestBriefing,
              let statuses = latest.notamStatuses as? Set<CDNotamStatus> else { return 0 }
        return statuses.filter { $0.status == NotamStatus.unread.rawValue }.count
    }

    // MARK: - Fetch Requests

    /// Fetch request for all non-archived flights
    /// Note: Results need to be sorted in memory with `sortedByDepartureDate()` for proper nil-first ordering
    static func activeFlightsFetchRequest() -> NSFetchRequest<CDFlight> {
        let request = NSFetchRequest<CDFlight>(entityName: "CDFlight")
        request.predicate = NSPredicate(format: "isArchived == NO")
        // Basic sort by createdAt as fallback; proper sort applied in memory
        request.sortDescriptors = [
            NSSortDescriptor(keyPath: \CDFlight.createdAt, ascending: false)
        ]
        return request
    }

    /// Fetch request for archived flights
    /// Note: Results need to be sorted in memory with `sortedByDepartureDate()` for proper nil-first ordering
    static func archivedFlightsFetchRequest() -> NSFetchRequest<CDFlight> {
        let request = NSFetchRequest<CDFlight>(entityName: "CDFlight")
        request.predicate = NSPredicate(format: "isArchived == YES")
        // Basic sort by createdAt as fallback; proper sort applied in memory
        request.sortDescriptors = [
            NSSortDescriptor(keyPath: \CDFlight.createdAt, ascending: false)
        ]
        return request
    }

    // MARK: - Sorting

    /// Sort flights by departure date: nil dates first, then most recent to oldest
    static func sortedByDepartureDate(_ flights: [CDFlight]) -> [CDFlight] {
        flights.sorted { lhs, rhs in
            switch (lhs.departureTime, rhs.departureTime) {
            case (nil, nil):
                // Both nil: sort by createdAt descending
                return (lhs.createdAt ?? .distantPast) > (rhs.createdAt ?? .distantPast)
            case (nil, _):
                // Left is nil: comes first
                return true
            case (_, nil):
                // Right is nil: right comes first
                return false
            case let (lhsDate?, rhsDate?):
                // Both have dates: most recent first
                return lhsDate > rhsDate
            }
        }
    }

    /// Find a flight by ID
    static func find(id: UUID, in context: NSManagedObjectContext) -> CDFlight? {
        let request = NSFetchRequest<CDFlight>(entityName: "CDFlight")
        request.predicate = NSPredicate(format: "id == %@", id as CVarArg)
        request.fetchLimit = 1
        return try? context.fetch(request).first
    }
}
