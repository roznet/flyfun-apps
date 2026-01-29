//
//  CDGlobalNotamRead+Extensions.swift
//  FlyFunBrief
//
//  Core Data CDGlobalNotamRead entity convenience extensions.
//  Tracks global read status for NOTAMs across all briefings with resurface support.
//

import Foundation
import CoreData
import RZFlight

extension CDGlobalNotamRead {
    // MARK: - Private Helpers

    /// Shared DateFormatter for display (expensive to create, so cached)
    private static let lastReadDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()

    /// Find or create a global read record
    private static func findOrCreate(
        in context: NSManagedObjectContext,
        identityKey: String,
        notamId: String,
        routeHash: String?
    ) -> CDGlobalNotamRead {
        // Check if record already exists
        if let existing = find(identityKey: identityKey, in: context) {
            existing.lastReadAt = Date()
            existing.lastRouteHash = routeHash
            existing.readCount += 1
            return existing
        }

        // Create new record
        let record = CDGlobalNotamRead(context: context)
        record.id = UUID()
        record.notamId = notamId
        record.identityKey = identityKey
        record.lastReadAt = Date()
        record.lastRouteHash = routeHash
        record.readCount = 1

        return record
    }

    // MARK: - Convenience Initializer

    /// Create or update a global read record for a NOTAM
    @discardableResult
    static func markAsRead(
        in context: NSManagedObjectContext,
        notam: Notam,
        routeHash: String? = nil
    ) -> CDGlobalNotamRead {
        let identityKey = NotamIdentity.key(for: notam)
        return findOrCreate(in: context, identityKey: identityKey, notamId: notam.id, routeHash: routeHash)
    }

    /// Create from identity key (when original NOTAM is not available)
    @discardableResult
    static func markAsRead(
        in context: NSManagedObjectContext,
        identityKey: String,
        notamId: String,
        routeHash: String? = nil
    ) -> CDGlobalNotamRead {
        return findOrCreate(in: context, identityKey: identityKey, notamId: notamId, routeHash: routeHash)
    }

    // MARK: - Computed Properties

    /// Days since last read
    var daysSinceLastRead: Int {
        guard let lastRead = lastReadAt else { return Int.max }
        let calendar = Calendar.current
        let components = calendar.dateComponents([.day], from: lastRead, to: Date())
        return components.day ?? Int.max
    }

    /// Formatted last read date
    var formattedLastReadAt: String {
        guard let lastRead = lastReadAt else { return "Never" }
        return Self.lastReadDateFormatter.string(from: lastRead)
    }

    // MARK: - Fetch Requests

    /// Find a global read record by identity key
    static func find(
        identityKey: String,
        in context: NSManagedObjectContext
    ) -> CDGlobalNotamRead? {
        let request = NSFetchRequest<CDGlobalNotamRead>(entityName: "CDGlobalNotamRead")
        request.predicate = NSPredicate(format: "identityKey == %@", identityKey)
        request.fetchLimit = 1
        return try? context.fetch(request).first
    }

    /// Check if a NOTAM has been globally read
    static func hasBeenRead(
        identityKey: String,
        in context: NSManagedObjectContext
    ) -> Bool {
        let request = NSFetchRequest<CDGlobalNotamRead>(entityName: "CDGlobalNotamRead")
        request.predicate = NSPredicate(format: "identityKey == %@", identityKey)
        // Use count instead of fetch for efficiency
        return (try? context.count(for: request)) ?? 0 > 0
    }

    /// Fetch all global read records
    static func allReadsFetchRequest() -> NSFetchRequest<CDGlobalNotamRead> {
        let request = NSFetchRequest<CDGlobalNotamRead>(entityName: "CDGlobalNotamRead")
        request.sortDescriptors = [
            NSSortDescriptor(keyPath: \CDGlobalNotamRead.lastReadAt, ascending: false)
        ]
        return request
    }

    /// Fetch global reads within a time threshold (not stale)
    static func recentReadsFetchRequest(withinDays days: Int) -> NSFetchRequest<CDGlobalNotamRead>? {
        guard let cutoffDate = Calendar.current.date(byAdding: .day, value: -days, to: Date()) else {
            return nil
        }
        let request = NSFetchRequest<CDGlobalNotamRead>(entityName: "CDGlobalNotamRead")
        request.predicate = NSPredicate(format: "lastReadAt >= %@", cutoffDate as NSDate)
        request.sortDescriptors = [
            NSSortDescriptor(keyPath: \CDGlobalNotamRead.lastReadAt, ascending: false)
        ]
        return request
    }

    /// Fetch multiple global reads by identity keys
    static func findAll(
        identityKeys: Set<String>,
        in context: NSManagedObjectContext
    ) -> [String: CDGlobalNotamRead] {
        guard !identityKeys.isEmpty else { return [:] }

        let request = NSFetchRequest<CDGlobalNotamRead>(entityName: "CDGlobalNotamRead")
        request.predicate = NSPredicate(format: "identityKey IN %@", identityKeys)

        guard let results = try? context.fetch(request) else { return [:] }

        var dict: [String: CDGlobalNotamRead] = [:]
        for record in results {
            if let key = record.identityKey {
                dict[key] = record
            }
        }
        return dict
    }

    // MARK: - Cleanup

    /// Remove stale global reads older than threshold
    static func cleanupStale(olderThanDays days: Int, in context: NSManagedObjectContext) throws {
        guard let cutoffDate = Calendar.current.date(byAdding: .day, value: -days, to: Date()) else {
            // If we can't calculate the date, skip cleanup to avoid data loss
            return
        }

        let request = NSFetchRequest<CDGlobalNotamRead>(entityName: "CDGlobalNotamRead")
        request.predicate = NSPredicate(format: "lastReadAt < %@", cutoffDate as NSDate)

        let stale = try context.fetch(request)
        for item in stale {
            context.delete(item)
        }
    }
}
