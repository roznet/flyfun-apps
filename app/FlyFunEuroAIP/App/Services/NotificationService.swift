//
//  NotificationService.swift
//  FlyFunEuroAIP
//
//  Service for accessing parsed notification/customs requirements.
//  Loads from bundled ga_notifications.db for offline-first access.
//

import Foundation
import FMDB
import OSLog
import RZUtilsSwift

/// Service for accessing notification requirements from bundled database
final class NotificationService: @unchecked Sendable {
    // MARK: - Private

    private let db: FMDatabase
    private var cache: [String: NotificationInfo] = [:]
    private let cacheQueue = DispatchQueue(label: "net.ro-z.flyfun.notification.cache")

    /// Whether the service is available
    let isAvailable: Bool

    // MARK: - Init

    init(databasePath: String) throws {
        let db = FMDatabase(path: databasePath)
        guard db.open() else {
            throw AppError.databaseOpenFailed(path: databasePath)
        }
        self.db = db
        self.isAvailable = true
        Logger.app.info("NotificationService initialized from \(databasePath)")
    }

    /// Initialize with bundled database
    static func createFromBundle() -> NotificationService? {
        guard let path = Bundle.main.path(forResource: "ga_notifications", ofType: "db") else {
            Logger.app.warning("ga_notifications.db not found in bundle")
            return nil
        }
        do {
            return try NotificationService(databasePath: path)
        } catch {
            Logger.app.error("Failed to initialize NotificationService: \(error)")
            return nil
        }
    }

    // MARK: - Preloading

    /// Preload all notifications into cache (call at startup)
    func preloadAll() async {
        let query = """
            SELECT icao, rule_type, notification_type, hours_notice,
                   operating_hours_start, operating_hours_end,
                   weekday_rules, summary, confidence, contact_info
            FROM ga_notification_requirements
            WHERE confidence > 0.5
        """

        guard let results = db.executeQuery(query, withArgumentsIn: []) else {
            Logger.app.error("Failed to query notifications for preload")
            return
        }

        var loaded = 0
        while results.next() {
            if let notification = parseRow(results) {
                cacheQueue.sync {
                    cache[notification.icao] = notification
                }
                loaded += 1
            }
        }
        results.close()
        Logger.app.info("Preloaded \(loaded) notifications into cache")
    }

    /// Number of cached notifications
    var cachedCount: Int {
        cacheQueue.sync { cache.count }
    }

    // MARK: - Single Lookup

    /// Get notification for a single airport (from cache, fast)
    func getNotification(icao: String) -> NotificationInfo? {
        cacheQueue.sync {
            cache[icao.uppercased()]
        }
    }

    /// Check if notification data exists for airport
    func hasNotification(icao: String) -> Bool {
        cacheQueue.sync {
            cache[icao.uppercased()] != nil
        }
    }

    // MARK: - Batch Lookup

    /// Get notifications for multiple airports (for legend mode)
    func getNotifications(icaos: [String]) -> [String: NotificationInfo] {
        cacheQueue.sync {
            var result: [String: NotificationInfo] = [:]
            for icao in icaos {
                if let notification = cache[icao.uppercased()] {
                    result[icao.uppercased()] = notification
                }
            }
            return result
        }
    }

    /// Get all ICAOs that have notification data
    func allICAOs() -> Set<String> {
        cacheQueue.sync {
            Set(cache.keys)
        }
    }

    // MARK: - Filtering

    /// Find airports matching notification criteria
    func findAirports(
        maxHoursNotice: Int? = nil,
        notificationType: NotificationInfo.NotificationType? = nil,
        limit: Int = 50
    ) -> [NotificationInfo] {
        cacheQueue.sync {
            var results = Array(cache.values)

            // Filter by notification type
            if let type = notificationType {
                results = results.filter { $0.notificationType == type }
            }

            // Filter by max hours notice
            if let maxHours = maxHoursNotice {
                results = results.filter { notification in
                    if notification.isH24 { return true }
                    if notification.isOnRequest { return true }
                    guard let hours = notification.maxNoticeHours else { return true }
                    return hours <= maxHours
                }
            }

            // Sort by easiness (easier first)
            results.sort { $0.easinessScore > $1.easinessScore }

            return Array(results.prefix(limit))
        }
    }

    // MARK: - Statistics

    /// Get notification statistics
    func getStatistics() -> NotificationStatistics {
        cacheQueue.sync {
            var byType: [NotificationInfo.NotificationType: Int] = [:]
            var totalHours = 0
            var hoursCount = 0

            for notification in cache.values {
                byType[notification.notificationType, default: 0] += 1
                if let hours = notification.hoursNotice {
                    totalHours += hours
                    hoursCount += 1
                }
            }

            return NotificationStatistics(
                total: cache.count,
                byType: byType,
                averageHoursNotice: hoursCount > 0 ? Double(totalHours) / Double(hoursCount) : nil
            )
        }
    }

    // MARK: - Private Helpers

    private func parseRow(_ rs: FMResultSet) -> NotificationInfo? {
        var row: [String: Any] = [:]

        row["icao"] = rs.string(forColumn: "icao")
        row["rule_type"] = rs.string(forColumn: "rule_type")
        row["notification_type"] = rs.string(forColumn: "notification_type")

        if !rs.columnIsNull("hours_notice") {
            row["hours_notice"] = Int(rs.int(forColumn: "hours_notice"))
        }

        row["operating_hours_start"] = rs.string(forColumn: "operating_hours_start")
        row["operating_hours_end"] = rs.string(forColumn: "operating_hours_end")
        row["weekday_rules"] = rs.string(forColumn: "weekday_rules")
        row["summary"] = rs.string(forColumn: "summary")
        row["confidence"] = rs.double(forColumn: "confidence")
        row["contact_info"] = rs.string(forColumn: "contact_info")

        return NotificationInfo(from: row)
    }
}

// MARK: - Statistics

struct NotificationStatistics: Sendable {
    let total: Int
    let byType: [NotificationInfo.NotificationType: Int]
    let averageHoursNotice: Double?

    var h24Count: Int { byType[.h24] ?? 0 }
    var hoursCount: Int { byType[.hours] ?? 0 }
    var onRequestCount: Int { byType[.onRequest] ?? 0 }
}
