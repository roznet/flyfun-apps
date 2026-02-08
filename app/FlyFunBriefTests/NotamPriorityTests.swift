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

    /// Create a test NOTAM with specified properties via JSON decoding.
    /// Automatically generates `q_code_info` from `qCode` when it has >= 5 chars.
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

        // Build q_code_info from qCode when possible (need >= 5 chars: Q + 2 subject + 2 condition)
        let qCodeInfoJson: String
        if let qc = qCode, qc.count >= 5 {
            let subjectCode = String(qc[qc.index(qc.startIndex, offsetBy: 1)..<qc.index(qc.startIndex, offsetBy: 3)])
            let conditionCode = String(qc[qc.index(qc.startIndex, offsetBy: 3)..<qc.index(qc.startIndex, offsetBy: 5)])
            qCodeInfoJson = """
            "q_code_info": {
                "q_code": "\(qc)",
                "subject_code": "\(subjectCode)",
                "subject_meaning": "Test",
                "subject_phrase": "test",
                "subject_category": "Test",
                "condition_code": "\(conditionCode)",
                "condition_meaning": "Test",
                "condition_phrase": "test",
                "condition_category": "Test",
                "display_text": "Test: Test",
                "short_text": "TEST",
                "is_checklist": false,
                "is_plain_language": false
            },
            """
        } else {
            qCodeInfoJson = ""
        }

        let json = """
        {
            "id": "\(id)",
            "location": "\(location)",
            "raw_text": "TEST NOTAM",
            "message": "Test message",
            "q_code": \(qCode.map { "\"\($0)\"" } ?? "null"),
            \(qCodeInfoJson)
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

    // MARK: - JSON Profile Loading Tests

    @Test func ifrProfileLoadsCorrectly() {
        let profile = PriorityProfiles.ifr
        #expect(profile.id == "ifr")
        #expect(profile.displayName == "IFR")
        #expect(profile.maxLevel == 5)
        #expect(profile.rules.count == 13)
        #expect(profile.levelDescriptions.count == 5)
    }

    @Test func vfrProfileLoadsCorrectly() {
        let profile = PriorityProfiles.vfr
        #expect(profile.id == "vfr")
        #expect(profile.displayName == "VFR")
        #expect(profile.maxLevel == 3)
        #expect(profile.rules.count == 11)
        #expect(profile.levelDescriptions.count == 3)
    }

    @Test func profileFromJSONRoundTrip() throws {
        let json = """
        {
            "id": "test",
            "display_name": "Test Profile",
            "max_level": 2,
            "level_descriptions": {"1": "Important", "2": "Other"},
            "rules": [
                {
                    "id": "test_rule",
                    "name": "Test Rule",
                    "type": "q_code_match",
                    "level": 1,
                    "subjects": ["MR"]
                }
            ]
        }
        """.data(using: .utf8)!

        let profile = try PriorityProfile.fromJSON(json)
        #expect(profile.id == "test")
        #expect(profile.maxLevel == 2)
        #expect(profile.rules.count == 1)
        #expect(profile.rules[0].id == "test_rule")
        #expect(profile.levelDescriptions[1] == "Important")
    }

    // MARK: - QCodeMatchRule Filter Tests

    @Test func subjectFilter() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "subjects": ["MR", "MT"]}
        """)
        let context = makeContext()

        let runwayNotam = try makeNotam(qCode: "QMRLC")
        #expect(rule.evaluate(notam: runwayNotam, distanceNm: nil, context: context) == 1)

        let navaidNotam = try makeNotam(qCode: "QNVAS")
        #expect(rule.evaluate(notam: navaidNotam, distanceNm: nil, context: context) == nil)
    }

    @Test func conditionFilterUnavailable() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "condition_filter": "unavailable"}
        """)
        let context = makeContext()

        // LC = closed = unavailable
        let closedNotam = try makeNotam(qCode: "QMRLC")
        #expect(rule.evaluate(notam: closedNotam, distanceNm: nil, context: context) == 1)

        // CH = changed, not unavailable
        let changedNotam = try makeNotam(qCode: "QMRCH")
        #expect(rule.evaluate(notam: changedNotam, distanceNm: nil, context: context) == nil)

        // Custom tag "closed" also triggers unavailable
        let taggedNotam = try makeNotam(qCode: "QMRCH", customTags: ["closed"])
        #expect(rule.evaluate(notam: taggedNotam, distanceNm: nil, context: context) == 1)
    }

    @Test func conditionFilterLimitation() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "condition_filter": "limitation"}
        """)
        let context = makeContext()

        // LC = closed, starts with L = limitation
        let closedNotam = try makeNotam(qCode: "QMRLC")
        #expect(rule.evaluate(notam: closedNotam, distanceNm: nil, context: context) == 1)

        // LR = reduced length, starts with L = limitation
        let reducedNotam = try makeNotam(qCode: "QMRLR")
        #expect(rule.evaluate(notam: reducedNotam, distanceNm: nil, context: context) == 1)

        // CH = changed, not limitation
        let changedNotam = try makeNotam(qCode: "QMRCH")
        #expect(rule.evaluate(notam: changedNotam, distanceNm: nil, context: context) == nil)
    }

    @Test func locationFilterDepDest() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "location": "dep_dest"}
        """)
        let context = makeContext(departureICAO: "LFPG", destinationICAO: "EGLL")

        let atDep = try makeNotam(location: "LFPG")
        #expect(rule.evaluate(notam: atDep, distanceNm: nil, context: context) == 1)

        let atDest = try makeNotam(location: "EGLL")
        #expect(rule.evaluate(notam: atDest, distanceNm: nil, context: context) == 1)

        let elsewhere = try makeNotam(location: "KJFK")
        #expect(rule.evaluate(notam: elsewhere, distanceNm: nil, context: context) == nil)
    }

    @Test func locationFilterNotDepDest() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "location": "not_dep_dest"}
        """)
        let context = makeContext(departureICAO: "LFPG", destinationICAO: "EGLL")

        let atDep = try makeNotam(location: "LFPG")
        #expect(rule.evaluate(notam: atDep, distanceNm: nil, context: context) == nil)

        let elsewhere = try makeNotam(location: "EGTF")
        #expect(rule.evaluate(notam: elsewhere, distanceNm: nil, context: context) == 1)
    }

    @Test func distanceFilter() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "max_distance_nm": 25}
        """)
        let context = makeContext()

        let notam = try makeNotam()
        #expect(rule.evaluate(notam: notam, distanceNm: 20.0, context: context) == 1)
        #expect(rule.evaluate(notam: notam, distanceNm: 25.0, context: context) == 1)
        #expect(rule.evaluate(notam: notam, distanceNm: 26.0, context: context) == nil)
        #expect(rule.evaluate(notam: notam, distanceNm: nil, context: context) == nil)
    }

    @Test func altitudeCheckIfAvailable() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "max_distance_nm": 50, "altitude_check": "if_available"}
        """)

        // With cruise altitude set, must overlap
        let contextWithAlt = makeContext(cruiseAltitude: 35000)
        let overlapping = try makeNotam(lowerLimit: 33000, upperLimit: 37000)
        #expect(rule.evaluate(notam: overlapping, distanceNm: 10.0, context: contextWithAlt) == 1)

        let nonOverlapping = try makeNotam(lowerLimit: 0, upperLimit: 5000)
        #expect(rule.evaluate(notam: nonOverlapping, distanceNm: 10.0, context: contextWithAlt) == nil)

        // Without cruise altitude, pass through (if_available = permissive)
        let contextNoAlt = makeContext(cruiseAltitude: nil)
        #expect(rule.evaluate(notam: nonOverlapping, distanceNm: 10.0, context: contextNoAlt) == 1)
    }

    @Test func altitudeCheckRequired() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "max_distance_nm": 10, "altitude_check": "required", "no_altitude_fallback_distance_nm": 5}
        """)

        // With cruise altitude, must overlap
        let contextWithAlt = makeContext(cruiseAltitude: 35000)
        let overlapping = try makeNotam(lowerLimit: 33000, upperLimit: 37000)
        #expect(rule.evaluate(notam: overlapping, distanceNm: 5.0, context: contextWithAlt) == 1)

        let nonOverlapping = try makeNotam(lowerLimit: 0, upperLimit: 5000)
        #expect(rule.evaluate(notam: nonOverlapping, distanceNm: 5.0, context: contextWithAlt) == nil)

        // Without cruise altitude, fallback to distance check
        let contextNoAlt = makeContext(cruiseAltitude: nil)
        let notam = try makeNotam()
        #expect(rule.evaluate(notam: notam, distanceNm: 4.0, context: contextNoAlt) == 1, "Within fallback distance")
        #expect(rule.evaluate(notam: notam, distanceNm: 6.0, context: contextNoAlt) == nil, "Beyond fallback distance")
    }

    @Test func surfaceToUnlimitedNotAltitudeRelevant() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1, "max_distance_nm": 50, "altitude_check": "if_available"}
        """)

        let context = makeContext(cruiseAltitude: 35000)
        let surfaceToUnlimited = try makeNotam(lowerLimit: 0, upperLimit: 99900)
        #expect(rule.evaluate(notam: surfaceToUnlimited, distanceNm: 5.0, context: context) == nil)
    }

    @Test func noQCodeSubjectReturnsNil() throws {
        let rule = try decodeRule("""
        {"id": "t", "name": "t", "type": "q_code_match", "level": 1}
        """)
        let context = makeContext()

        let noQCode = try makeNotam(qCode: nil)
        #expect(rule.evaluate(notam: noQCode, distanceNm: nil, context: context) == nil)

        let shortQCode = try makeNotam(qCode: "QM")
        #expect(rule.evaluate(notam: shortQCode, distanceNm: nil, context: context) == nil)
    }

    // MARK: - Evaluator Integration Tests

    @Test func evaluatorReturnsP1ForRunwayAtDeparture() throws {
        let notam = try makeNotam(location: "LFPG", qCode: "QMRLC")
        let context = makeContext(departureICAO: "LFPG")
        let evaluator = NotamPriorityEvaluator(profile: PriorityProfiles.ifr)
        let priority = evaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(priority.level == 1, "Movement area at departure should be P1")
        #expect(priority.isCritical)
    }

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

    @Test func helicopterNotamAtDepDestGetsDefault() throws {
        let notam = try makeNotam(location: "EGLL", qCode: "QFHXX")
        let context = makeContext(destinationICAO: "EGLL")
        let evaluator = NotamPriorityEvaluator(profile: PriorityProfiles.ifr)
        let priority = evaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        // FH subject is not in any IFR rule's subject set, but ifr_p4_other_dep_dest
        // catches any Q-code at dep/dest
        #expect(priority.level == 4, "Helicopter NOTAM at dep/dest should be P4 (other dep/dest)")
    }

    // MARK: - Helper

    private func decodeRule(_ json: String) throws -> QCodeMatchRule {
        try JSONDecoder().decode(QCodeMatchRule.self, from: json.data(using: .utf8)!)
    }
}
