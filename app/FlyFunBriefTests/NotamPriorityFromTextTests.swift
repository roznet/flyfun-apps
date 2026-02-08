//
//  NotamPriorityFromTextTests.swift
//  FlyFunBriefTests
//
//  End-to-end tests: real NOTAM text -> NotamParser.parse() -> NotamPriorityEvaluator -> priority level.
//  Validates that the full pipeline (parsing + qCodeInfo population + priority rules) works correctly.
//

import Testing
import Foundation
import CoreLocation
@testable import FlyFunBrief
@testable import RZFlight

struct NotamPriorityFromTextTests {

    // MARK: - Helpers

    private func parseFixture(_ id: String) throws -> Notam {
        let fix = try NotamFixtureLoader.loadFixture(id: id)
        guard let notam = NotamParser.parse(fix.rawText, source: "test") else {
            throw FixtureError.noFixturesFound("Failed to parse fixture '\(id)'")
        }
        return notam
    }

    private func makeContext(
        departureICAO: String? = nil,
        destinationICAO: String? = nil,
        alternateICAOs: [String] = [],
        cruiseAltitude: Int? = nil,
        routeCoordinates: [CLLocationCoordinate2D] = []
    ) -> FlightContext {
        FlightContext(
            routeCoordinates: routeCoordinates,
            departureICAO: departureICAO,
            destinationICAO: destinationICAO,
            alternateICAOs: alternateICAOs,
            cruiseAltitude: cruiseAltitude
        )
    }

    private var ifrEvaluator: NotamPriorityEvaluator {
        NotamPriorityEvaluator(profile: PriorityProfiles.ifr)
    }

    private var vfrEvaluator: NotamPriorityEvaluator {
        NotamPriorityEvaluator(profile: PriorityProfiles.vfr)
    }

    // MARK: - IFR Priority Tests

    @Test func ifrP1RunwayClosureAtDeparture() throws {
        let notam = try parseFixture("rwy_closure_lfpg")
        let context = makeContext(departureICAO: "LFPG")
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: 0.0, context: context)

        #expect(priority.level == 1, "Runway closure at departure should be P1, got P\(priority.level)")
        #expect(priority.isCritical)
    }

    @Test func ifrP1ILSUnavailableAtDestination() throws {
        // Critical test: exercises qCodeInfo.conditionCode="AS" path, not customTags
        let notam = try parseFixture("ils_unavailable_egll")
        let context = makeContext(destinationICAO: "EGLL")
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: 0.0, context: context)

        // Verify this works through qCodeInfo (conditionCode "AS" = unserviceable)
        #expect(notam.qCodeInfo?.conditionCode == "AS",
            "Precondition: qCodeInfo.conditionCode must be 'AS' for this test to be meaningful")
        #expect(priority.level == 1, "ILS unavailable at destination should be IFR P1, got P\(priority.level)")
        #expect(priority.isCritical)
    }

    @Test func ifrP2AirspaceRestrictionInCorridor() throws {
        let notam = try parseFixture("airspace_restriction_lfff")
        let context = makeContext(cruiseAltitude: 5000)
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: 10.0, context: context)

        #expect(priority.level == 2, "Airspace restriction within corridor at relevant altitude should be IFR P2, got P\(priority.level)")
    }

    @Test func ifrP3TaxiwayLimitationNearRoute() throws {
        let notam = try parseFixture("taxiway_limit_egtf")
        let context = makeContext(departureICAO: "LFPG", destinationICAO: "EGLL")
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: 30.0, context: context)

        // JSON splits: P2 for unavailable ≤20nm, P3 for limitation ≤50nm
        #expect(priority.level == 3, "Taxiway limitation near route (not at dep/dest) should be IFR P3, got P\(priority.level)")
    }

    @Test func ifrP2ProcedureChangedAtDestination() throws {
        let notam = try parseFixture("procedure_changed_egll")
        let context = makeContext(destinationICAO: "EGLL")
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: 0.0, context: context)

        #expect(priority.level == 2, "Procedure changed at destination should be IFR P2, got P\(priority.level)")
    }

    @Test func ifrP3NavaidIssuesAlongRoute() throws {
        let notam = try parseFixture("vor_unserviceable_lfmd")
        let context = makeContext(departureICAO: "LFPG", destinationICAO: "EGLL")
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: 20.0, context: context)

        #expect(priority.level == 3, "VOR unserviceable along route should be IFR P3, got P\(priority.level)")
    }

    @Test func ifrP4FacilityAtDestination() throws {
        let notam = try parseFixture("facility_lfmd")
        let context = makeContext(destinationICAO: "LFMD")
        // Use nil distance: we're testing the dep/dest facility rule, not distance-based rules
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(priority.level == 4, "Facility at destination should be IFR P4, got P\(priority.level)")
    }

    @Test func ifrP4ForHelicopterAtDepDest() throws {
        let notam = try parseFixture("helicopter_heliport_lfpg")
        let context = makeContext(departureICAO: "LFPG")
        // Use nil distance: helicopter subject (FH) doesn't match specific dep/dest rules
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        // FH doesn't match specific subject rules, but ifr_p4_other_dep_dest catches all Q-codes at dep/dest
        #expect(priority.level == 4, "Helicopter NOTAM at dep/dest should be IFR P4, got P\(priority.level)")
    }

    // MARK: - VFR Priority Tests

    @Test func vfrP1RunwayClosureAtDeparture() throws {
        let notam = try parseFixture("rwy_closure_lfpg")
        let context = makeContext(departureICAO: "LFPG")
        let priority = vfrEvaluator.evaluate(notam: notam, distanceNm: 0.0, context: context)

        #expect(priority.level == 1, "Runway closure at departure should be VFR P1, got P\(priority.level)")
        #expect(priority.isCritical)
    }

    @Test func vfrP1AirspaceRestrictionAlongRoute() throws {
        let notam = try parseFixture("airspace_restriction_lfff")
        let context = makeContext()
        let priority = vfrEvaluator.evaluate(notam: notam, distanceNm: 10.0, context: context)

        #expect(priority.level == 1, "Airspace restriction along route should be VFR P1, got P\(priority.level)")
    }

    @Test func vfrP2ForILSUnavailableAtDepDest() throws {
        // VFR doesn't have ILS-specific rules, but catch-all dep/dest rule applies
        let notam = try parseFixture("ils_unavailable_egll")
        let context = makeContext(destinationICAO: "EGLL")
        let priority = vfrEvaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        // vfr_p2_other_dep_dest catches any Q-code at dep/dest
        #expect(priority.level == 2, "ILS at dep/dest should be VFR P2 (other dep/dest), got P\(priority.level)")
    }

    @Test func vfrP2TaxiwayLimitationNearRoute() throws {
        let notam = try parseFixture("taxiway_limit_egtf")
        let context = makeContext(departureICAO: "LFPG", destinationICAO: "EGLL")
        let priority = vfrEvaluator.evaluate(notam: notam, distanceNm: 30.0, context: context)

        #expect(priority.level == 2, "Taxiway limitation near route should be VFR P2, got P\(priority.level)")
    }

    // MARK: - IFR vs VFR Comparison Tests

    @Test func comparisonAirspaceRestriction() throws {
        let notam = try parseFixture("airspace_restriction_lfff")
        let context = makeContext(cruiseAltitude: 5000)

        let ifrPriority = ifrEvaluator.evaluate(notam: notam, distanceNm: 10.0, context: context)
        let vfrPriority = vfrEvaluator.evaluate(notam: notam, distanceNm: 10.0, context: context)

        #expect(ifrPriority.level == 2, "Airspace restriction should be IFR P2")
        #expect(vfrPriority.level == 1, "Airspace restriction should be VFR P1")
        #expect(vfrPriority.level < ifrPriority.level,
            "VFR should treat airspace restrictions as higher priority than IFR")
    }

    @Test func comparisonILSUnavailable() throws {
        let notam = try parseFixture("ils_unavailable_egll")
        let context = makeContext(destinationICAO: "EGLL")

        let ifrPriority = ifrEvaluator.evaluate(notam: notam, distanceNm: nil, context: context)
        let vfrPriority = vfrEvaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(ifrPriority.level == 1, "ILS unavailable should be IFR P1")
        // VFR has no ILS-specific rules, but catch-all dep/dest rule gives P2
        #expect(vfrPriority.level == 2, "ILS unavailable at dep/dest should be VFR P2 (other dep/dest)")
    }

    // MARK: - Context Sensitivity Tests

    @Test func sameNotamDifferentContext() throws {
        let notam = try parseFixture("rwy_closure_lfpg")

        // At departure: P1
        let atDep = makeContext(departureICAO: "LFPG")
        let p1 = ifrEvaluator.evaluate(notam: notam, distanceNm: 0.0, context: atDep)
        #expect(p1.level == 1, "At departure should be P1")

        // Near route (not dep/dest): P3 (movement area limitation, JSON splits P2/P3)
        let nearRoute = makeContext(departureICAO: "EGLL", destinationICAO: "EHAM")
        let p3 = ifrEvaluator.evaluate(notam: notam, distanceNm: 30.0, context: nearRoute)
        #expect(p3.level == 3, "Near route but not at dep/dest should be P3")

        // Far from route: default
        let farAway = makeContext(departureICAO: "EGLL", destinationICAO: "EHAM")
        let pDefault = ifrEvaluator.evaluate(notam: notam, distanceNm: 100.0, context: farAway)
        #expect(pDefault.isDefault, "Far from route should be default priority")
    }

    @Test func emptyContextGivesDefault() throws {
        let notam = try parseFixture("rwy_closure_lfpg")
        let context = FlightContext.empty
        let priority = ifrEvaluator.evaluate(notam: notam, distanceNm: nil, context: context)

        #expect(priority.isDefault, "Empty context should yield default priority")
    }
}
