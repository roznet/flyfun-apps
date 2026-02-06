//
//  NotamParsingTests.swift
//  FlyFunBriefTests
//
//  Tests that NotamParser.parse() correctly extracts fields from real NOTAM text.
//  Uses hand-crafted fixture data from Fixtures/notam_priority_samples.txt.
//

import Testing
import Foundation
import CoreLocation
@testable import RZFlight

struct NotamParsingTests {

    // MARK: - Fixture Loading

    private func loadFixtures() throws -> [NotamFixture] {
        try NotamFixtureLoader.load(filename: "notam_priority_samples.txt")
    }

    private func fixture(_ id: String) throws -> NotamFixture {
        try NotamFixtureLoader.loadFixture(id: id)
    }

    private func parseFixture(_ id: String) throws -> Notam {
        let fix = try fixture(id)
        guard let notam = NotamParser.parse(fix.rawText, source: "test") else {
            throw FixtureError.noFixturesFound("Failed to parse fixture '\(id)'")
        }
        return notam
    }

    // MARK: - All Fixtures Parse

    @Test func allFixturesParse() throws {
        let fixtures = try loadFixtures()
        #expect(fixtures.count == 10, "Expected 10 fixtures, got \(fixtures.count)")

        for fix in fixtures {
            let notam = NotamParser.parse(fix.rawText, source: "test")
            #expect(notam != nil, "Fixture '\(fix.id)' failed to parse")

            if let notam {
                // Verify expected Q-code matches (parser stores with Q prefix)
                if let expectedQCode = fix.expectedQCode {
                    #expect(notam.qCode == expectedQCode,
                        "Fixture '\(fix.id)': expected qCode \(expectedQCode), got \(notam.qCode ?? "nil")")
                }

                // Verify expected location matches
                if let expectedLocation = fix.expectedLocation {
                    #expect(notam.location == expectedLocation,
                        "Fixture '\(fix.id)': expected location \(expectedLocation), got \(notam.location)")
                }
            }
        }
    }

    // MARK: - Runway Closure

    @Test func parseRunwayClosure() throws {
        let notam = try parseFixture("rwy_closure_lfpg")

        #expect(notam.id == "A0101/24")
        #expect(notam.location == "LFPG")
        #expect(notam.qCode == "QMRLC")
        #expect(notam.fir == "LFFF")

        // Q-code info populated by QCodeLookup
        #expect(notam.qCodeInfo != nil, "qCodeInfo should be populated from Q-code lookup")
        if let info = notam.qCodeInfo {
            #expect(info.subjectCode == "MR", "Expected subject MR (Runway)")
            #expect(info.conditionCode == "LC", "Expected condition LC (Closed)")
        }

        // Verify dates parsed
        #expect(notam.effectiveFrom != nil, "effectiveFrom should be parsed")
        #expect(notam.effectiveTo != nil, "effectiveTo should be parsed")

        // Verify message
        #expect(notam.message.contains("RWY 09L/27R CLSD"))
    }

    // MARK: - ILS Unavailable

    @Test func parseILSUnavailable() throws {
        let notam = try parseFixture("ils_unavailable_egll")

        #expect(notam.id == "A0202/24")
        #expect(notam.location == "EGLL")
        #expect(notam.qCode == "QILAS")

        // This is the critical test: conditionCode="AS" is what priority rules use
        #expect(notam.qCodeInfo != nil, "qCodeInfo must be populated for priority rules")
        if let info = notam.qCodeInfo {
            #expect(info.subjectCode == "IL", "Expected subject IL (Localizer)")
            #expect(info.conditionCode == "AS", "Expected condition AS (Unserviceable)")
        }
    }

    // MARK: - Airspace Restriction

    @Test func parseAirspaceRestriction() throws {
        let notam = try parseFixture("airspace_restriction_lfff")

        #expect(notam.id == "A0303/24")
        #expect(notam.location == "LFFF")
        #expect(notam.qCode == "QRTCA")

        // Verify coordinates extracted from Q-line
        #expect(notam.coordinate != nil, "Should have coordinates from Q-line")
        if let coord = notam.coordinate {
            #expect(abs(coord.latitude - 48.75) < 0.1, "Latitude should be ~48.75")
            #expect(abs(coord.longitude - 2.33) < 0.1, "Longitude should be ~2.33")
        }

        // Verify altitude limits from F/G lines
        #expect(notam.lowerLimit == 2000, "Lower limit from F-line should be 2000")
        #expect(notam.upperLimit == 5000, "Upper limit from G-line should be 5000")
    }

    // MARK: - Scheduled NOTAM

    @Test func parseScheduledNOTAM() throws {
        let notam = try parseFixture("scheduled_notam_lfpt")

        #expect(notam.id == "A0909/24")
        #expect(notam.location == "LFPT")
        #expect(notam.qCode == "QMRLC")

        // Verify schedule text from D-line
        #expect(notam.scheduleText != nil, "Schedule text from D-line should be parsed")
        if let schedule = notam.scheduleText {
            #expect(schedule.contains("MON-FRI"), "Schedule should contain MON-FRI, got: \(schedule)")
        }
    }

    // MARK: - Permanent NOTAM

    @Test func parsePermanentNOTAM() throws {
        let notam = try parseFixture("facility_lfmd")

        #expect(notam.id == "A1010/24")
        #expect(notam.location == "LFMD")
        #expect(notam.qCode == "QFATT")

        // Verify PERM flag
        #expect(notam.isPermanent, "NOTAM with C) PERM should have isPermanent = true")
        #expect(notam.effectiveTo == nil, "Permanent NOTAM should have nil effectiveTo")
    }

    // MARK: - Obstacle NOTAM

    @Test func parseObstacleNOTAM() throws {
        let notam = try parseFixture("obstacle_warning_lfrn")

        #expect(notam.id == "A0606/24")
        #expect(notam.location == "LFRN")
        #expect(notam.qCode == "QOBCE")

        // Verify coordinates
        #expect(notam.coordinate != nil, "Obstacle should have coordinates")

        // Q-code info
        if let info = notam.qCodeInfo {
            #expect(info.subjectCode == "OB", "Expected subject OB (Obstacle)")
            #expect(info.conditionCode == "CE", "Expected condition CE (Erected)")
        }
    }

    // MARK: - Helicopter NOTAM

    @Test func parseHelicopterNOTAM() throws {
        let notam = try parseFixture("helicopter_heliport_lfpg")

        #expect(notam.id == "A0707/24")
        #expect(notam.location == "LFPG")
        #expect(notam.qCode == "QFHXX")

        // Verify Q-code subject is FH (Heliport)
        #expect(notam.qCodeSubject == "FH", "Q-code subject should be FH (Heliport)")
    }

    // MARK: - VOR Unserviceable

    @Test func parseVORUnserviceable() throws {
        let notam = try parseFixture("vor_unserviceable_lfmd")

        #expect(notam.id == "A0404/24")
        #expect(notam.location == "LFMD")
        #expect(notam.qCode == "QNVAS")

        if let info = notam.qCodeInfo {
            #expect(info.subjectCode == "NV", "Expected subject NV (VOR)")
            #expect(info.conditionCode == "AS", "Expected condition AS (Unserviceable)")
        }
    }

    // MARK: - Procedure Changed

    @Test func parseProcedureChanged() throws {
        let notam = try parseFixture("procedure_changed_egll")

        #expect(notam.id == "A0808/24")
        #expect(notam.location == "EGLL")
        #expect(notam.qCode == "QPICH")

        if let info = notam.qCodeInfo {
            #expect(info.subjectCode == "PI", "Expected subject PI (Instrument approach)")
            #expect(info.conditionCode == "CH", "Expected condition CH (Changed)")
        }
    }

    // MARK: - Parse Multiple NOTAMs

    @Test func parseMultipleNOTAMsFromText() throws {
        // Combine 3 fixture raw texts into one block
        let fixtures = try loadFixtures()
        let threeFixtures = Array(fixtures.prefix(3))
        let combinedText = threeFixtures.map { $0.rawText }.joined(separator: "\n\n")

        let notams = NotamParser.parseMany(combinedText, source: "test")
        #expect(notams.count == 3, "parseMany should return 3 NOTAMs from combined text, got \(notams.count)")
    }
}
