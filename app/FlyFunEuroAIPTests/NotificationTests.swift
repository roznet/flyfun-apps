//
//  NotificationTests.swift
//  FlyFunEuroAIPTests
//
//  Tests for NotificationInfo model and NotificationService.
//

import Testing
import Foundation
import SwiftUI
import FMDB
@testable import FlyFunEuroAIP

// MARK: - NotificationInfo Model Tests

struct NotificationInfoTests {

    // MARK: - Initialization

    @Test func initFromRowWithValidData() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "rule_type": "customs",
            "notification_type": "hours",
            "hours_notice": 24,
            "summary": "24 hours notice required",
            "confidence": 0.9
        ]

        let notification = NotificationInfo(from: row)

        #expect(notification != nil)
        #expect(notification?.icao == "LFPG")
        #expect(notification?.ruleType == .customs)
        #expect(notification?.notificationType == .hours)
        #expect(notification?.hoursNotice == 24)
        #expect(notification?.summary == "24 hours notice required")
        #expect(notification?.confidence == 0.9)
    }

    @Test func initFromRowWithMissingICAOFails() {
        let row: [String: Any] = [
            "rule_type": "customs",
            "notification_type": "hours"
        ]

        let notification = NotificationInfo(from: row)
        #expect(notification == nil)
    }

    @Test func initFromRowWithUnknownNotificationType() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "invalid_type"
        ]

        let notification = NotificationInfo(from: row)

        #expect(notification != nil)
        #expect(notification?.notificationType == .unknown)
    }

    @Test func initFromRowWithContactInfo() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "contact_info": "{\"phone\":\"+33 1 23 45 67\",\"email\":\"test@airport.fr\"}"
        ]

        let notification = NotificationInfo(from: row)

        #expect(notification?.contactPhone == "+33 1 23 45 67")
        #expect(notification?.contactEmail == "test@airport.fr")
    }

    @Test func initFromRowWithOperatingHours() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "operating_hours_start": "0600",
            "operating_hours_end": "2200"
        ]

        let notification = NotificationInfo(from: row)

        #expect(notification?.operatingHours == "0600-2200")
    }

    // MARK: - Computed Properties

    @Test func isH24ReturnsTrueForH24Type() {
        let row: [String: Any] = [
            "icao": "EGLL",
            "notification_type": "h24"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.isH24 == true)
        #expect(notification.isOnRequest == false)
    }

    @Test func isOnRequestReturnsTrueForOnRequestType() {
        let row: [String: Any] = [
            "icao": "LFPO",
            "notification_type": "on_request"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.isOnRequest == true)
        #expect(notification.isH24 == false)
    }

    @Test func maxNoticeHoursReturnsHoursNotice() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "hours",
            "hours_notice": 48
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.maxNoticeHours == 48)
    }

    @Test func maxNoticeHoursReturnsZeroForH24() {
        let row: [String: Any] = [
            "icao": "EGLL",
            "notification_type": "h24",
            "hours_notice": 24  // Should be ignored for h24
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.maxNoticeHours == 0)
    }

    @Test func maxNoticeHoursReturnsNilForOnRequest() {
        let row: [String: Any] = [
            "icao": "LFPO",
            "notification_type": "on_request"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.maxNoticeHours == nil)
    }

    // MARK: - Easiness Score

    @Test func easinessScoreForH24Is100() {
        let row: [String: Any] = [
            "icao": "EGLL",
            "notification_type": "h24"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.easinessScore == 100.0)
    }

    @Test func easinessScoreForOnRequestIs70() {
        let row: [String: Any] = [
            "icao": "LFPO",
            "notification_type": "on_request"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.easinessScore == 70.0)
    }

    @Test func easinessScoreForShortNoticeIsHigh() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "hours",
            "hours_notice": 2
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.easinessScore == 90.0)
    }

    @Test func easinessScoreFor24HoursIsModerate() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "hours",
            "hours_notice": 24
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.easinessScore == 60.0)
    }

    @Test func easinessScoreForHoursWithNoNoticeIsEasy() {
        // LFAT case: has operating hours but no advance notice required
        let row: [String: Any] = [
            "icao": "LFAT",
            "notification_type": "hours",
            // hours_notice is nil - just operating hours constraint
            "operating_hours_start": "0800",
            "operating_hours_end": "1800"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.easinessScore == 85.0)
        #expect(notification.legendColor == .green)
    }

    @Test func easinessScoreForNotAvailableIsZero() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "not_available"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.easinessScore == 0.0)
        #expect(notification.legendColor == .red)
    }

    @Test func easinessScoreForBusinessDayIsModerate() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "business_day"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.easinessScore == 55.0)
        #expect(notification.legendColor == .orange)
    }

    @Test func easinessScoreForLongNoticeIsLow() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "hours",
            "hours_notice": 72
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.easinessScore == 20.0)
    }

    // MARK: - Legend Color

    @Test func legendColorGreenForHighScore() {
        let row: [String: Any] = [
            "icao": "EGLL",
            "notification_type": "h24"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.legendColor == .green)
    }

    @Test func legendColorBlueForModerateScore() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "on_request"  // 70 score = blue
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.legendColor == .blue)
    }

    @Test func legendColorOrangeForSomeHassle() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "hours",
            "hours_notice": 48  // 40 score = orange
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.legendColor == .orange)
    }

    @Test func legendColorRedForHighHassle() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "notification_type": "hours",
            "hours_notice": 96  // 10 score = red
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.legendColor == .red)
    }

    // MARK: - Display Summary

    @Test func displaySummaryTruncatesLongText() {
        let longSummary = String(repeating: "A", count: 200)
        let row: [String: Any] = [
            "icao": "LFPG",
            "summary": longSummary
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.displaySummary.count == 153)  // 150 + "..."
        #expect(notification.displaySummary.hasSuffix("..."))
    }

    @Test func displaySummaryPreservesShortText() {
        let row: [String: Any] = [
            "icao": "LFPG",
            "summary": "Short summary"
        ]

        let notification = NotificationInfo(from: row)!

        #expect(notification.displaySummary == "Short summary")
    }

    // MARK: - NotificationType Properties

    @Test func notificationTypeDisplayNames() {
        #expect(NotificationInfo.NotificationType.h24.displayName == "24/7")
        #expect(NotificationInfo.NotificationType.hours.displayName == "Notice Required")
        #expect(NotificationInfo.NotificationType.onRequest.displayName == "On Request")
        #expect(NotificationInfo.NotificationType.businessDay.displayName == "Business Day")
        #expect(NotificationInfo.NotificationType.notAvailable.displayName == "Unavailable")
        #expect(NotificationInfo.NotificationType.unknown.displayName == "Unknown")
    }

    @Test func notificationTypeIconNames() {
        #expect(NotificationInfo.NotificationType.h24.iconName == "checkmark.circle.fill")
        #expect(NotificationInfo.NotificationType.hours.iconName == "clock.fill")
        #expect(NotificationInfo.NotificationType.onRequest.iconName == "phone.fill")
        #expect(NotificationInfo.NotificationType.businessDay.iconName == "calendar")
        #expect(NotificationInfo.NotificationType.notAvailable.iconName == "xmark.circle.fill")
        #expect(NotificationInfo.NotificationType.unknown.iconName == "questionmark.circle")
    }
}

// MARK: - NotificationService Tests

struct NotificationServiceTests {

    // MARK: - Initialization

    @Test func serviceCreatesFromBundle() async {
        // This test verifies the service can be created from the bundled DB
        // If the DB is not bundled (e.g., in test target), it should gracefully return nil
        let service = NotificationService.createFromBundle()

        // In test environment, bundle may not have the DB
        // Just verify it doesn't crash
        if service != nil {
            #expect(service?.isAvailable == true)
        }
    }

    // MARK: - Cache Behavior

    @Test func cachedCountReturnsZeroInitially() async throws {
        // Create a temp empty database for testing
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        // Create minimal test database
        let db = try createTestDatabase(at: tempPath)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)

        // Before preload, cache should be empty
        #expect(service.cachedCount == 0)
    }

    @Test func preloadPopulatesCache() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath)
        insertTestNotification(db: db, icao: "LFPG", type: "h24", confidence: 0.9)
        insertTestNotification(db: db, icao: "EGLL", type: "hours", confidence: 0.8)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        #expect(service.cachedCount == 2)
    }

    @Test func preloadFiltersLowConfidence() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath)
        insertTestNotification(db: db, icao: "LFPG", type: "h24", confidence: 0.9)
        insertTestNotification(db: db, icao: "EGLL", type: "hours", confidence: 0.3)  // Low confidence
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        #expect(service.cachedCount == 1)
        #expect(service.hasNotification(icao: "LFPG") == true)
        #expect(service.hasNotification(icao: "EGLL") == false)
    }

    // MARK: - Lookup

    @Test func getNotificationReturnsCorrectData() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath)
        insertTestNotification(db: db, icao: "LFPG", type: "h24", confidence: 0.9)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        let notification = service.getNotification(icao: "LFPG")

        #expect(notification != nil)
        #expect(notification?.icao == "LFPG")
        #expect(notification?.notificationType == .h24)
    }

    @Test func getNotificationIsCaseInsensitive() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath)
        insertTestNotification(db: db, icao: "LFPG", type: "h24", confidence: 0.9)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        #expect(service.getNotification(icao: "lfpg") != nil)
        #expect(service.getNotification(icao: "LFPG") != nil)
        #expect(service.getNotification(icao: "LfPg") != nil)
    }

    @Test func getNotificationReturnsNilForUnknown() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath)
        insertTestNotification(db: db, icao: "LFPG", type: "h24", confidence: 0.9)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        #expect(service.getNotification(icao: "ZZZZ") == nil)
    }

    // MARK: - Batch Lookup

    @Test func getNotificationsBatchReturnsMatching() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath)
        insertTestNotification(db: db, icao: "LFPG", type: "h24", confidence: 0.9)
        insertTestNotification(db: db, icao: "EGLL", type: "hours", confidence: 0.8)
        insertTestNotification(db: db, icao: "LFPO", type: "on_request", confidence: 0.7)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        let results = service.getNotifications(icaos: ["LFPG", "EGLL", "ZZZZ"])

        #expect(results.count == 2)
        #expect(results["LFPG"] != nil)
        #expect(results["EGLL"] != nil)
        #expect(results["ZZZZ"] == nil)
    }

    // MARK: - Filtering

    @Test func findAirportsFiltersbyType() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath)
        insertTestNotification(db: db, icao: "LFPG", type: "h24", confidence: 0.9)
        insertTestNotification(db: db, icao: "EGLL", type: "hours", confidence: 0.8)
        insertTestNotification(db: db, icao: "LFPO", type: "h24", confidence: 0.7)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        let h24Airports = service.findAirports(notificationType: .h24)

        #expect(h24Airports.count == 2)
        #expect(h24Airports.allSatisfy { $0.notificationType == .h24 })
    }

    @Test func findAirportsFiltersByMaxHours() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath, withHoursNotice: true)
        insertTestNotificationWithHours(db: db, icao: "LFPG", type: "hours", hours: 12, confidence: 0.9)
        insertTestNotificationWithHours(db: db, icao: "EGLL", type: "hours", hours: 48, confidence: 0.8)
        insertTestNotification(db: db, icao: "LFPO", type: "h24", confidence: 0.7)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        let results = service.findAirports(maxHoursNotice: 24)

        #expect(results.count == 2)  // LFPG (12h) and LFPO (h24)
    }

    @Test func findAirportsSortsByEasiness() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath, withHoursNotice: true)
        insertTestNotificationWithHours(db: db, icao: "LFPG", type: "hours", hours: 48, confidence: 0.9)
        insertTestNotification(db: db, icao: "EGLL", type: "h24", confidence: 0.8)
        insertTestNotificationWithHours(db: db, icao: "LFPO", type: "hours", hours: 12, confidence: 0.7)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        let results = service.findAirports()

        // Should be sorted by easiness: EGLL (h24=100), LFPO (12h=80), LFPG (48h=40)
        #expect(results[0].icao == "EGLL")
        #expect(results[1].icao == "LFPO")
        #expect(results[2].icao == "LFPG")
    }

    // MARK: - Statistics

    @Test func statisticsCountsByType() async throws {
        let tempPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("test_notifications_\(UUID().uuidString).db").path

        let db = try createTestDatabase(at: tempPath)
        insertTestNotification(db: db, icao: "LFPG", type: "h24", confidence: 0.9)
        insertTestNotification(db: db, icao: "EGLL", type: "h24", confidence: 0.8)
        insertTestNotification(db: db, icao: "LFPO", type: "hours", confidence: 0.7)
        defer {
            db.close()
            try? FileManager.default.removeItem(atPath: tempPath)
        }

        let service = try NotificationService(databasePath: tempPath)
        await service.preloadAll()

        let stats = service.getStatistics()

        #expect(stats.total == 3)
        #expect(stats.h24Count == 2)
        #expect(stats.hoursCount == 1)
    }

    // MARK: - Test Helpers

    private func createTestDatabase(at path: String, withHoursNotice: Bool = false) throws -> FMDatabase {
        let db = FMDatabase(path: path)
        guard db.open() else {
            throw NSError(domain: "TestError", code: 1, userInfo: [NSLocalizedDescriptionKey: "Failed to create test DB"])
        }

        let createSQL = """
            CREATE TABLE ga_notification_requirements (
                icao TEXT PRIMARY KEY,
                rule_type TEXT,
                notification_type TEXT,
                hours_notice INTEGER,
                operating_hours_start TEXT,
                operating_hours_end TEXT,
                weekday_rules TEXT,
                summary TEXT,
                confidence REAL,
                contact_info TEXT
            )
        """

        guard db.executeStatements(createSQL) else {
            throw NSError(domain: "TestError", code: 2, userInfo: [NSLocalizedDescriptionKey: "Failed to create table"])
        }

        return db
    }

    private func insertTestNotification(db: FMDatabase, icao: String, type: String, confidence: Double) {
        let sql = """
            INSERT INTO ga_notification_requirements (icao, rule_type, notification_type, summary, confidence)
            VALUES (?, 'customs', ?, 'Test summary', ?)
        """
        db.executeUpdate(sql, withArgumentsIn: [icao, type, confidence])
    }

    private func insertTestNotificationWithHours(db: FMDatabase, icao: String, type: String, hours: Int, confidence: Double) {
        let sql = """
            INSERT INTO ga_notification_requirements (icao, rule_type, notification_type, hours_notice, summary, confidence)
            VALUES (?, 'customs', ?, ?, 'Test summary', ?)
        """
        db.executeUpdate(sql, withArgumentsIn: [icao, type, hours, confidence])
    }
}

// MARK: - NotificationStatistics Tests

struct NotificationStatisticsTests {

    @Test func statisticsAccessors() {
        let stats = NotificationStatistics(
            total: 100,
            byType: [
                .h24: 30,
                .hours: 50,
                .onRequest: 20
            ],
            averageHoursNotice: 24.5
        )

        #expect(stats.total == 100)
        #expect(stats.h24Count == 30)
        #expect(stats.hoursCount == 50)
        #expect(stats.onRequestCount == 20)
        #expect(stats.averageHoursNotice == 24.5)
    }

    @Test func statisticsMissingTypeReturnsZero() {
        let stats = NotificationStatistics(
            total: 10,
            byType: [.h24: 10],
            averageHoursNotice: nil
        )

        #expect(stats.hoursCount == 0)
        #expect(stats.onRequestCount == 0)
    }
}
