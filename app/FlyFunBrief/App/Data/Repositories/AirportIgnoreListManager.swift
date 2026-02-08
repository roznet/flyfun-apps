//
//  AirportIgnoreListManager.swift
//  FlyFunBrief
//
//  Manages the airport-level ignore list via Core Data.
//

import Foundation
import CoreData
import OSLog

/// Manager for the airport-level ignore list
@MainActor
final class AirportIgnoreListManager {
    // MARK: - Properties

    private let persistenceController: PersistenceController

    private var viewContext: NSManagedObjectContext {
        persistenceController.viewContext
    }

    /// Cache of ignored ICAO codes for fast lookup
    private var ignoredCodesCache: Set<String>?

    // MARK: - Initialization

    init(persistenceController: PersistenceController = .shared) {
        self.persistenceController = persistenceController
    }

    // MARK: - Ignore Operations

    /// Add an airport to the ignore list
    @discardableResult
    func addToIgnoreList(icaoCode: String, reason: String? = nil) throws -> CDIgnoredAirport {
        let uppercased = icaoCode.uppercased()

        // Prevent duplicates
        if let existing = CDIgnoredAirport.find(icaoCode: uppercased, in: viewContext) {
            Logger.persistence.info("Airport \(uppercased) already in ignore list")
            return existing
        }

        let ignored = CDIgnoredAirport.create(in: viewContext, icaoCode: uppercased, reason: reason)
        try viewContext.save()

        invalidateCache()

        Logger.persistence.info("Added airport \(uppercased) to ignore list")
        return ignored
    }

    /// Remove an airport from the ignore list
    func removeFromIgnoreList(_ ignored: CDIgnoredAirport) throws {
        let icao = ignored.icaoCode ?? "unknown"
        viewContext.delete(ignored)
        try viewContext.save()

        invalidateCache()

        Logger.persistence.info("Removed airport \(icao) from ignore list")
    }

    /// Remove an airport from the ignore list by ICAO code
    func removeFromIgnoreList(icaoCode: String) throws {
        guard let ignored = CDIgnoredAirport.find(icaoCode: icaoCode, in: viewContext) else {
            return
        }
        try removeFromIgnoreList(ignored)
    }

    /// Check if an airport is in the ignore list
    func isIgnored(icaoCode: String) -> Bool {
        let uppercased = icaoCode.uppercased()
        if let cache = ignoredCodesCache {
            return cache.contains(uppercased)
        }
        return CDIgnoredAirport.isIgnored(icaoCode: uppercased, in: viewContext)
    }

    // MARK: - Fetch

    /// Fetch all ignored airports
    func fetchAllIgnores() throws -> [CDIgnoredAirport] {
        try viewContext.fetch(CDIgnoredAirport.allIgnoresFetchRequest())
    }

    /// Get all ignored ICAO codes as a set (for filtering)
    func getIgnoredAirportCodes() throws -> Set<String> {
        if let cache = ignoredCodesCache {
            return cache
        }

        let ignores = try fetchAllIgnores()
        let codes = Set(ignores.compactMap { $0.icaoCode?.uppercased() })

        ignoredCodesCache = codes
        return codes
    }

    // MARK: - Cache Management

    /// Invalidate the ignored codes cache
    func invalidateCache() {
        ignoredCodesCache = nil
    }

    /// Refresh the cache
    func refreshCache() throws {
        let ignores = try fetchAllIgnores()
        ignoredCodesCache = Set(ignores.compactMap { $0.icaoCode?.uppercased() })
    }
}
