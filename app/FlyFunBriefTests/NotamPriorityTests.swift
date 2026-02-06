//
//  NotamPriorityTests.swift
//  FlyFunBriefTests
//
//  Tests for NOTAM priority evaluation system.
//  Uses JSON-decoded Notam objects to test individual rules and the evaluator chain.
//

import Testing
import Foundation
import CoreLocation
@testable import FlyFunBrief
@testable import RZFlight

struct NotamPriorityTests {

    // MARK: - Test Helpers

    /// Create a test NOTAM with specified properties via JSON decoding
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

    // MARK: - NotamPriority Struct Tests

    @Test func priorityComparison() {
        // Lower level = higher priority. Comparable: higher priority sorts first (lhs.level > rhs.level)
        let p1 = NotamPriority(level: 1, maxLevel: 5)
        let p3 = NotamPriority(level: 3, maxLevel: 5)
        let p5 = NotamPriority(level: 5, maxLevel: 5)

        #expect(p5 < p3, "P5 should be less than P3 (lower priority)")
        #expect(p3 < p1, "P3 should be less than P1 (lower priority)")
        #expect(p5 < p1, "P5 should be less than P1")
    }

    @Test func priorityProperties() {
        let critical = NotamPriority(level: 1, maxLevel: 5)
        #expect(critical.isCritical)
        #expect(!critical.isDefault)
        #expect(critical.iconName == "exclamationmark.triangle.fill")
        #expect(critical.label == "P1")

        let mid = NotamPriority(level: 3, maxLevel: 5)
        #expect(!mid.isCritical)
        #expect(!mid.isDefault)
        #expect(mid.iconName == "circle.fill")
        #expect(mid.label == "P3")

        let defaultPriority = NotamPriority.default(maxLevel: 5)
        #expect(!defaultPriority.isCritical)
        #expect(defaultPriority.isDefault)
        #expect(defaultPriority.iconName == nil)
        #expect(defaultPriority.label == "P5")
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

    // MARK: - IFR P3: Close + Altitude Rule Tests

    @Test func p3WhenCloseAndAltitudeOverlaps() throws {
        let notam = try makeNotam(
            latitude: 50.0,
            longitude: 1.0,
            lowerLimit: 33000,
            upperLimit: 37000
        )

        let context = makeContext(cruiseAltitude: 35000)
        let rule = IFRCloseAndAltitudeRelevant()
        let result = rule.evaluate(notam: notam, distanceNm: 5.0, context: context)

        #expect(result == 3, "Close + altitude overlap should return P3")
    }

    @Test func noMatchWhenFarFromRoute() throws {
        let notam = try makeNotam(
            latitude: 40.0,
            longitude: 10.0,
            lowerLimit: 33000,
            upperLimit: 37000
        )

        let context = makeContext(cruiseAltitude: 35000)
        let rule = IFRCloseAndAltitudeRelevant()
        let result = rule.evaluate(notam: notam, distanceNm: 51.0, context: context)

        #expect(result == nil, "Rule doesn't apply when beyond 10nm threshold")
    }

    @Test func noMatchWhenAltitudeDoesNotOverlap() throws {
        let notam = try makeNotam(
            lowerLimit: 0,
            upperLimit: 5000
        )

        let context = makeContext(cruiseAltitude: 35000)
        let rule = IFRCloseAndAltitudeRelevant()
        let result = rule.evaluate(notam: notam, distanceNm: 5.0, context: context)

        #expect(result == nil, "Altitude doesn't overlap cruise")
    }

    @Test func surfaceToUnlimitedNotAltitudeRelevant() throws {
        let notam = try makeNotam(
            lowerLimit: 0,
            upperLimit: 99900
        )

        let context = makeContext(cruiseAltitude: 35000)
        let rule = IFRCloseAndAltitudeRelevant()
        let result = rule.evaluate(notam: notam, distanceNm: 5.0, context: context)

        #expect(result == nil, "Surface to unlimited should not be altitude relevant")
    }

    // MARK: - IFR P1: Movement Area at Dep/Dest Tests

    @Test func p1ForRunwayClosureAtDestination() throws {
        let notam = try makeNotam(
            location: "EGLL",
            qCode: "QMRLC",
            customTags: ["closed"]
        )

        let context = makeContext(destinationICAO: "EGLL")
        let rule = IFRMovementAreaAtDepDest()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == 1, "Runway NOTAM at destination should be P1")
    }

    @Test func p1ForRunwayClosureAtDeparture() throws {
        let notam = try makeNotam(
            location: "LFPG",
            qCode: "QMRLC",
            customTags: ["closed"]
        )

        let context = makeContext(departureICAO: "LFPG")
        let rule = IFRMovementAreaAtDepDest()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == 1, "Runway NOTAM at departure should be P1")
    }

    @Test func noP1ForClosureAtOtherAirport() throws {
        let notam = try makeNotam(
            location: "KJFK",
            qCode: "QMRLC",
            customTags: ["closed"]
        )

        let context = makeContext(departureICAO: "LFPG", destinationICAO: "EGLL")
        let rule = IFRMovementAreaAtDepDest()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == nil, "NOTAM at unrelated airport should not match")
    }

    // MARK: - IFR P4: Facilities at Dep/Dest

    @Test func p4ForFacilityAtDepDest() throws {
        let notam = try makeNotam(
            location: "LFPG",
            qCode: "QFATT"
        )

        let context = makeContext(departureICAO: "LFPG")
        let rule = IFRFacilitiesAtDepDest()
        let result = rule.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(result == 4, "Facility at departure should be P4")
    }

    // MARK: - Helicopter NOTAM (default priority, no specific rule)

    @Test func helicopterNotamAtDepDestGetsDefaultOrFacility() throws {
        let notam = try makeNotam(
            location: "EGLL",
            qCode: "QFHXX"
        )

        let context = makeContext(destinationICAO: "EGLL")
        let evaluator = NotamPriorityEvaluator(profile: PriorityProfiles.ifr)
        let priority = evaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        // FH subject is in the facility subjects set (FA, FF, FS) — no, FH is not.
        // So helicopter NOTAM at dep/dest falls to default
        #expect(priority.level >= 4, "Helicopter NOTAM should be low priority")
    }

    // MARK: - Priority Evaluator Chain Tests

    @Test func evaluatorReturnsDefaultWhenNoRuleMatches() throws {
        let notam = try makeNotam(
            location: "LFRN",
            qCode: "QMXXX",
            lowerLimit: 0,
            upperLimit: 1000
        )

        let context = makeContext(
            departureICAO: "LFPG",
            destinationICAO: "EGLL",
            cruiseAltitude: 35000
        )

        let evaluator = NotamPriorityEvaluator(profile: PriorityProfiles.ifr)
        let priority = evaluator.evaluate(notam: notam, distanceNm: 100.0, context: context)

        #expect(priority.isDefault, "Unmatched NOTAM should get default priority")
        #expect(priority.level == 5, "IFR default level should be 5")
    }

    @Test func evaluatorWithEmptyContextReturnsDefault() throws {
        let notam = try makeNotam()
        let context = FlightContext.empty

        let evaluator = NotamPriorityEvaluator(profile: PriorityProfiles.ifr)
        let priority = evaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(priority.isDefault, "Empty context should yield default priority")
    }

    @Test func evaluatorReturnsFirstMatchingRulePriority() throws {
        // Movement area at departure should be P1
        let notam = try makeNotam(
            location: "LFPG",
            qCode: "QMRLC"
        )

        let context = makeContext(departureICAO: "LFPG")
        let evaluator = NotamPriorityEvaluator(profile: PriorityProfiles.ifr)
        let priority = evaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(priority.level == 1, "Movement area at departure should be P1")
        #expect(priority.isCritical)
    }
}
