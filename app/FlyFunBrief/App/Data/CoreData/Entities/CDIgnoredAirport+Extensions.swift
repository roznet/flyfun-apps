//
//  CDIgnoredAirport+Extensions.swift
//  FlyFunBrief
//
//  Core Data CDIgnoredAirport entity convenience extensions.
//

import Foundation
import CoreData

extension CDIgnoredAirport {
    // MARK: - Convenience Initializer

    /// Create a new ignored airport entry
    @discardableResult
    static func create(
        in context: NSManagedObjectContext,
        icaoCode: String,
        reason: String? = nil
    ) -> CDIgnoredAirport {
        let ignored = CDIgnoredAirport(context: context)
        ignored.id = UUID()
        ignored.icaoCode = icaoCode.uppercased()
        ignored.reason = reason
        ignored.createdAt = Date()
        return ignored
    }

    // MARK: - Computed Properties

    /// Formatted creation date
    var formattedCreatedAt: String {
        guard let created = createdAt else { return "Unknown" }
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: created)
    }

    // MARK: - Fetch Requests

    /// Fetch request for all ignored airports, sorted by ICAO code
    static func allIgnoresFetchRequest() -> NSFetchRequest<CDIgnoredAirport> {
        let request = NSFetchRequest<CDIgnoredAirport>(entityName: "CDIgnoredAirport")
        request.sortDescriptors = [
            NSSortDescriptor(keyPath: \CDIgnoredAirport.icaoCode, ascending: true)
        ]
        return request
    }

    /// Find an ignored airport by ICAO code
    static func find(
        icaoCode: String,
        in context: NSManagedObjectContext
    ) -> CDIgnoredAirport? {
        let request = NSFetchRequest<CDIgnoredAirport>(entityName: "CDIgnoredAirport")
        request.predicate = NSPredicate(format: "icaoCode == %@", icaoCode.uppercased())
        request.fetchLimit = 1
        return try? context.fetch(request).first
    }

    /// Check if an airport ICAO code is ignored
    static func isIgnored(
        icaoCode: String,
        in context: NSManagedObjectContext
    ) -> Bool {
        find(icaoCode: icaoCode, in: context) != nil
    }
}
