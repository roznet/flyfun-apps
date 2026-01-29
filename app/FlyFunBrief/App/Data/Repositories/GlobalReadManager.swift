//
//  GlobalReadManager.swift
//  FlyFunBrief
//
//  Manages global NOTAM read tracking via Core Data.
//  Tracks when NOTAMs were read globally (across all briefings) for resurface logic.
//

import Foundation
import CoreData
import RZFlight
import OSLog

/// Manager for global NOTAM read tracking
@MainActor
final class GlobalReadManager {
    // MARK: - Properties

    private let persistenceController: PersistenceController

    private var viewContext: NSManagedObjectContext {
        persistenceController.viewContext
    }

    /// Cache of global read records keyed by identity key
    private var globalReadsCache: [String: CDGlobalNotamRead]?

    // MARK: - Initialization

    init(persistenceController: PersistenceController = .shared) {
        self.persistenceController = persistenceController
    }

    // MARK: - Read Operations

    /// Mark a NOTAM as globally read
    @discardableResult
    func markAsRead(_ notam: Notam, routeHash: String? = nil) throws -> CDGlobalNotamRead {
        let record = CDGlobalNotamRead.markAsRead(in: viewContext, notam: notam, routeHash: routeHash)
        try viewContext.save()

        // Invalidate cache
        invalidateCache()

        Logger.persistence.info("Marked NOTAM \(notam.id) as globally read")
        return record
    }

    /// Mark a NOTAM as globally read by identity key
    @discardableResult
    func markAsRead(identityKey: String, notamId: String, routeHash: String? = nil) throws -> CDGlobalNotamRead {
        let record = CDGlobalNotamRead.markAsRead(in: viewContext, identityKey: identityKey, notamId: notamId, routeHash: routeHash)
        try viewContext.save()

        // Invalidate cache
        invalidateCache()

        Logger.persistence.info("Marked NOTAM \(notamId) (key: \(identityKey)) as globally read")
        return record
    }

    /// Get the global read record for a NOTAM identity key
    func getReadRecord(identityKey: String) -> CDGlobalNotamRead? {
        // Use cache if available
        if let cache = globalReadsCache {
            return cache[identityKey]
        }

        return CDGlobalNotamRead.find(identityKey: identityKey, in: viewContext)
    }

    /// Check if a NOTAM has been globally read
    func hasBeenRead(_ notam: Notam) -> Bool {
        let identityKey = NotamIdentity.key(for: notam)
        return hasBeenRead(identityKey: identityKey)
    }

    /// Check if an identity key has been globally read
    func hasBeenRead(identityKey: String) -> Bool {
        // Use cache for performance
        if let cache = globalReadsCache {
            return cache[identityKey] != nil
        }

        return CDGlobalNotamRead.hasBeenRead(identityKey: identityKey, in: viewContext)
    }

    // MARK: - Bulk Operations

    /// Get all global read records as a dictionary keyed by identity key
    func getReadRecords() throws -> [String: CDGlobalNotamRead] {
        // Return cached if available
        if let cache = globalReadsCache {
            return cache
        }

        let results = try viewContext.fetch(CDGlobalNotamRead.allReadsFetchRequest())
        var dict: [String: CDGlobalNotamRead] = [:]
        for record in results {
            if let key = record.identityKey {
                dict[key] = record
            }
        }

        // Update cache
        globalReadsCache = dict

        return dict
    }

    /// Get global read records for specific identity keys
    func getReadRecords(for identityKeys: Set<String>) -> [String: CDGlobalNotamRead] {
        // Use cache if available
        if let cache = globalReadsCache {
            return cache.filter { identityKeys.contains($0.key) }
        }

        return CDGlobalNotamRead.findAll(identityKeys: identityKeys, in: viewContext)
    }

    /// Get all global read identity keys as a set
    func getReadIdentityKeys() throws -> Set<String> {
        let records = try getReadRecords()
        return Set(records.keys)
    }

    // MARK: - Cleanup

    /// Remove stale global reads older than threshold (default: 90 days)
    func cleanupStale(olderThanDays days: Int = 90) throws {
        try CDGlobalNotamRead.cleanupStale(olderThanDays: days, in: viewContext)
        try viewContext.save()

        // Invalidate cache
        invalidateCache()

        Logger.persistence.info("Cleaned up global reads older than \(days) days")
    }

    // MARK: - Cache Management

    /// Invalidate the global reads cache
    func invalidateCache() {
        globalReadsCache = nil
    }

    /// Refresh the cache
    func refreshCache() throws {
        let results = try viewContext.fetch(CDGlobalNotamRead.allReadsFetchRequest())
        var dict: [String: CDGlobalNotamRead] = [:]
        for record in results {
            if let key = record.identityKey {
                dict[key] = record
            }
        }
        globalReadsCache = dict
    }
}
