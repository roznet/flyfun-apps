//
//  NotamPriorityTests.swift
//  FlyFunBriefTests
//
//  Tests for NOTAM priority evaluation system.
//

import Testing
import Foundation
import CoreLocation
@testable import FlyFunBrief
@testable import RZFlight

struct NotamPriorityTests {

    // MARK: - Test Helpers

    /// Create a test NOTAM with specified properties
    private func makeNotam(
        id: String = "A1234/24",
        location: String = "LFPG",
        qCode: String? = "QMRLC",
        latitude: Double? = nil,
        longitude: Double? = nil,
        lowerLimit: Int? = nil,
        upperLimit: Int? = nil,
        customTags: [String] = []
    ) throws -> Notam {
        let coordJson: String
        if let lat = latitude, let lon = longitude {
            coordJson = """
            "coordinate": {"latitude": \(lat), "longitude": \(lon)},
            """
        } else {
            coordJson = ""
        }

        let lowerJson = lowerLimit.map { "\"lower_limit\": \($0)," } ?? ""
        let upperJson = upperLimit.map { "\"upper_limit\": \($0)," } ?? ""
        let tagsJson = customTags.isEmpty ? "[]" : "[\(customTags.map { "\"\($0)\"" }.joined(separator: ", "))]"

        let json = """
        {
            "id": "\(id)",
            "location": "\(location)",
            "raw_text": "TEST NOTAM",
            "message": "Test message",
            "q_code": \(qCode.map { "\"\($0)\"" } ?? "null"),
            \(coordJson)
            \(lowerJson)
            \(upperJson)
            "is_permanent": false,
            "effective_from": "2024-01-15T00:00:00Z",
            "parsed_at": "2024-01-15T12:00:00Z",
            "parse_confidence": 1.0,
            "custom_categories": [],
            "custom_tags": \(tagsJson)
        }
        """

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(Notam.self, from: json.data(using: .utf8)!)
    }

    /// Create a test FlightContext
    private func makeContext(
        routeCoordinates: [CLLocationCoordinate2D] = [],
        departureICAO: String? = "LFPG",
        destinationICAO: String? = "EGLL",
        cruiseAltitude: Int? = 35000,
        departureTime: Date? = nil,
        arrivalTime: Date? = nil
    ) -> FlightContext {
        FlightContext(
            routeCoordinates: routeCoordinates,
            departureICAO: departureICAO,
            destinationICAO: destinationICAO,
            alternateICAOs: [],
            cruiseAltitude: cruiseAltitude,
            departureTime: departureTime,
            arrivalTime: arrivalTime
        )
    }

    // MARK: - NotamPriority Enum Tests

    @Test func priorityComparison() {
        #expect(NotamPriority.low < NotamPriority.normal)
        #expect(NotamPriority.normal < NotamPriority.high)
        #expect(NotamPriority.low < NotamPriority.high)
    }

    @Test func priorityIconNames() {
        #expect(NotamPriority.high.iconName == "exclamationmark.triangle.fill")
        #expect(NotamPriority.normal.iconName == nil)
        #expect(NotamPriority.low.iconName == "arrow.down.circle")
    }

    // MARK: - FlightContext Tests

    @Test func emptyContextHasNoValidRoute() {
        let context = FlightContext.empty
        #expect(!context.hasValidRoute)
        #expect(context.cruiseAltitudeRange == nil)
    }

    @Test func contextWithTwoPointsHasValidRoute() {
        let coords = [
            CLLocationCoordinate2D(latitude: 49.0, longitude: 2.5),
            CLLocationCoordinate2D(latitude: 51.5, longitude: -0.1)
        ]
        let context = makeContext(routeCoordinates: coords)
        #expect(context.hasValidRoute)
    }

    @Test func contextWithOnePointHasNoValidRoute() {
        let coords = [CLLocationCoordinate2D(latitude: 49.0, longitude: 2.5)]
        let context = makeContext(routeCoordinates: coords)
        #expect(!context.hasValidRoute)
    }

    @Test func cruiseAltitudeRangeIsCorrect() {
        let context = makeContext(cruiseAltitude: 35000)
        let range = context.cruiseAltitudeRange
        #expect(range != nil)
        #expect(range?.lowerBound == 33000)
        #expect(range?.upperBound == 37000)
    }

    @Test func noCruiseAltitudeGivesNilRange() {
        let context = makeContext(cruiseAltitude: nil)
        #expect(context.cruiseAltitudeRange == nil)
    }

    @Test func flightWindowCalculation() {
        let departure = Date()
        let arrival = departure.addingTimeInterval(3600) // 1 hour flight
        let context = makeContext(departureTime: departure, arrivalTime: arrival)

        let windowStart = context.flightWindowStart
        let windowEnd = context.flightWindowEnd

        #expect(windowStart != nil)
        #expect(windowEnd != nil)

        // Window should be departure - 2h to arrival + 2h
        let expectedStart = departure.addingTimeInterval(-2 * 3600)
        let expectedEnd = arrival.addingTimeInterval(2 * 3600)

        #expect(abs(windowStart!.timeIntervalSince(expectedStart)) < 1)
        #expect(abs(windowEnd!.timeIntervalSince(expectedEnd)) < 1)
    }

    // MARK: - High Priority: Close + Altitude Rule Tests

    @Test func highPriorityWhenCloseAndAltitudeOverlaps() throws {
        // NOTAM at FL350 (35000ft), within 10nm of route
        let notam = try makeNotam(
            latitude: 50.0,
            longitude: 1.0,
            lowerLimit: 33000,
            upperLimit: 37000
        )

        // Route from LFPG (49.0, 2.5) to EGLL (51.5, -0.1)
        let coords = [
            CLLocationCoordinate2D(latitude: 49.0, longitude: 2.5),
            CLLocationCoordinate2D(latitude: 51.5, longitude: -0.1)
        ]
        let context = makeContext(routeCoordinates: coords, cruiseAltitude: 35000)

        let rule = HighPriorityCloseAndRelevantAltitude()
        // Distance should be close since 50.0, 1.0 is near the route
        let distance = 5.0 // Simulated close distance
        let result = rule.evaluate(notam: notam, distanceNm: distance, context: context)

        #expect(result == .high)
    }

    @Test func noHighPriorityWhenFarFromRoute() throws {
        let notam = try makeNotam(
            latitude: 40.0, // Far from route
            longitude: 10.0,
            lowerLimit: 33000,
            upperLimit: 37000
        )

        let context = makeContext(cruiseAltitude: 35000)
        let rule = HighPriorityCloseAndRelevantAltitude()
        // Use distance > threshold (50nm) to be outside the high priority range
        let result = rule.evaluate(notam: notam, distanceNm: 51.0, context: context)

        #expect(result == nil) // Rule doesn't apply when beyond threshold
    }

    @Test func noHighPriorityWhenAltitudeDoesNotOverlap() throws {
        let notam = try makeNotam(
            lowerLimit: 0,
            upperLimit: 5000 // Low altitude NOTAM
        )

        let context = makeContext(cruiseAltitude: 35000)
        let rule = HighPriorityCloseAndRelevantAltitude()
        let result = rule.evaluate(notam: notam, distanceNm: 5.0, context: context)

        #expect(result == nil) // Altitude doesn't overlap
    }

    @Test func surfaceToUnlimitedNotHighPriority() throws {
        // Surface to unlimited (000/999) should not trigger altitude relevance
        let notam = try makeNotam(
            lowerLimit: 0,
            upperLimit: 99900
        )

        let context = makeContext(cruiseAltitude: 35000)
        let rule = HighPriorityCloseAndRelevantAltitude()
        let result = rule.evaluate(notam: notam, distanceNm: 5.0, context: context)

        #expect(result == nil)
    }

    // MARK: - High Priority: Runway Closure Rule Tests

    @Test func highPriorityForRunwayClosureAtDestination() throws {
        let notam = try makeNotam(
            location: "EGLL",
            qCode: "QMRLC", // MR = Movement area runway, LC = Closed
            customTags: ["closed"]
        )

        let context = makeContext(destinationICAO: "EGLL")
        let rule = HighPriorityRunwayClosureAtAirport()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == .high)
    }

    @Test func highPriorityForRunwayClosureAtDeparture() throws {
        let notam = try makeNotam(
            location: "LFPG",
            qCode: "QMRLC",
            customTags: ["closed"]
        )

        let context = makeContext(departureICAO: "LFPG")
        let rule = HighPriorityRunwayClosureAtAirport()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == .high)
    }

    @Test func noHighPriorityForClosureAtOtherAirport() throws {
        let notam = try makeNotam(
            location: "KJFK", // Not on route
            qCode: "QMRLC",
            customTags: ["closed"]
        )

        let context = makeContext(departureICAO: "LFPG", destinationICAO: "EGLL")
        let rule = HighPriorityRunwayClosureAtAirport()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == nil)
    }

    // MARK: - Low Priority: Obstacles Far Rule Tests

    @Test func lowPriorityForObstacleFarFromAirports() throws {
        let notam = try makeNotam(
            location: "LFRN", // Not departure or destination
            qCode: "QOBCE" // OB = Obstacle
        )

        let context = makeContext(departureICAO: "LFPG", destinationICAO: "EGLL")
        let rule = LowPriorityObstaclesFarFromAirports()
        let result = rule.evaluate(notam: notam, distanceNm: 50.0, context: context)

        #expect(result == .low)
    }

    @Test func obstacleNearDepartureNotLowPriority() throws {
        let notam = try makeNotam(
            location: "LFPG", // At departure
            qCode: "QOBCE"
        )

        let context = makeContext(departureICAO: "LFPG")
        let rule = LowPriorityObstaclesFarFromAirports()
        let result = rule.evaluate(notam: notam, distanceNm: 1.0, context: context)

        #expect(result == nil) // Not low priority when at airport
    }

    // MARK: - Low Priority: Helicopter Rule Tests

    @Test func lowPriorityForHelicopterNotams() throws {
        let notam = try makeNotam(qCode: "QFHXX") // FH = Heliport

        let context = makeContext()
        let rule = LowPriorityHelicopterNotams()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == .low)
    }

    @Test func nonHelicopterNotamNotLowPriority() throws {
        let notam = try makeNotam(qCode: "QMRLC") // Runway NOTAM

        let context = makeContext()
        let rule = LowPriorityHelicopterNotams()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == nil)
    }

    // MARK: - Priority Evaluator Chain Tests

    @Test func evaluatorReturnsNormalWhenNoRuleMatches() throws {
        let notam = try makeNotam(
            location: "LFRN",
            qCode: "QMXXX", // Generic movement NOTAM
            lowerLimit: 0,
            upperLimit: 1000
        )

        let context = makeContext(
            departureICAO: "LFPG",
            destinationICAO: "EGLL",
            cruiseAltitude: 35000
        )

        let evaluator = NotamPriorityEvaluator.shared
        let priority = evaluator.evaluate(notam: notam, distanceNm: 100.0, context: context)

        #expect(priority == .normal)
    }

    @Test func evaluatorReturnsFirstMatchingRulePriority() throws {
        // This NOTAM should match both helicopter (low) and be at destination
        // But helicopter rule should fire first in the chain
        let notam = try makeNotam(
            location: "EGLL",
            qCode: "QFHXX" // Helicopter NOTAM at destination
        )

        let context = makeContext(destinationICAO: "EGLL")

        let evaluator = NotamPriorityEvaluator.shared
        let priority = evaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        // Helicopter rule is after runway closure in the chain, so if it's a closure it would be high
        // But QFHXX is not a closure, so helicopter rule applies -> low
        #expect(priority == .low)
    }

    @Test func evaluatorWithEmptyContextReturnsNormal() throws {
        let notam = try makeNotam()
        let context = FlightContext.empty

        let evaluator = NotamPriorityEvaluator.shared
        let priority = evaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(priority == .normal)
    }
}
