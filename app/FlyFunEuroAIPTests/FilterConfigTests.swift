//
//  FilterConfigTests.swift
//  FlyFunEuroAIPTests
//
//  Tests for FilterConfig computed properties and state management.
//

import Testing
import Foundation
@testable import FlyFunEuroAIP

struct FilterConfigTests {

    // MARK: - Default State

    @Test func defaultFilterHasNoActiveFilters() {
        let config = FilterConfig.default
        #expect(config.hasActiveFilters == false)
        #expect(config.activeFilterCount == 0)
    }

    // MARK: - Active Filter Detection

    @Test func countryFilterIsActive() {
        var config = FilterConfig.default
        config.country = "FR"

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func proceduresFilterIsActive() {
        var config = FilterConfig.default
        config.hasProcedures = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func hardRunwayFilterIsActive() {
        var config = FilterConfig.default
        config.hasHardRunway = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func borderCrossingFilterIsActive() {
        var config = FilterConfig.default
        config.pointOfEntry = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func minRunwayLengthFilterIsActive() {
        var config = FilterConfig.default
        config.minRunwayLengthFt = 3000

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func maxRunwayLengthFilterIsActive() {
        var config = FilterConfig.default
        config.maxRunwayLengthFt = 8000

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func ilsFilterIsActive() {
        var config = FilterConfig.default
        config.hasILS = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func rnavFilterIsActive() {
        var config = FilterConfig.default
        config.hasRNAV = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func precisionApproachFilterIsActive() {
        var config = FilterConfig.default
        config.hasPrecisionApproach = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func aipFieldFilterIsActive() {
        var config = FilterConfig.default
        config.aipField = "fuel"

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func lightedRunwayFilterIsActive() {
        var config = FilterConfig.default
        config.hasLightedRunway = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func avgasFilterIsActive() {
        var config = FilterConfig.default
        config.hasAvgas = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func jetAFilterIsActive() {
        var config = FilterConfig.default
        config.hasJetA = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    @Test func maxLandingFeeFilterIsActive() {
        var config = FilterConfig.default
        config.maxLandingFee = 50.0

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 1)
    }

    // MARK: - Multiple Filters

    @Test func multipleFiltersAreCounted() {
        var config = FilterConfig.default
        config.country = "GB"
        config.hasProcedures = true
        config.minRunwayLengthFt = 2000
        config.hasILS = true

        #expect(config.hasActiveFilters == true)
        #expect(config.activeFilterCount == 4)
    }

    // MARK: - False Values Don't Count

    @Test func falseValuesAreNotActive() {
        var config = FilterConfig.default
        config.hasProcedures = false
        config.hasHardRunway = false
        config.pointOfEntry = false

        #expect(config.hasActiveFilters == false)
        #expect(config.activeFilterCount == 0)
    }

    // MARK: - Reset

    @Test func resetClearsAllFilters() {
        var config = FilterConfig(
            country: "FR",
            hasProcedures: true,
            hasHardRunway: true,
            minRunwayLengthFt: 3000
        )

        #expect(config.hasActiveFilters == true)

        config.reset()

        #expect(config.hasActiveFilters == false)
        #expect(config.country == nil)
        #expect(config.hasProcedures == nil)
        #expect(config.hasHardRunway == nil)
        #expect(config.minRunwayLengthFt == nil)
    }

    // MARK: - Description

    @Test func descriptionShowsActiveFilters() {
        var config = FilterConfig.default
        config.country = "FR"
        config.hasProcedures = true

        let description = config.description
        #expect(description.contains("Country: FR"))
        #expect(description.contains("Has procedures"))
    }

    @Test func emptyDescriptionForNoFilters() {
        let config = FilterConfig.default
        #expect(config.description == "No filters")
    }

    @Test func descriptionShowsFuelFilters() {
        var config = FilterConfig.default
        config.hasAvgas = true
        config.hasJetA = true

        let description = config.description
        #expect(description.contains("Has AVGAS"))
        #expect(description.contains("Has Jet-A"))
    }

    @Test func descriptionShowsLandingFee() {
        var config = FilterConfig.default
        config.maxLandingFee = 100.0

        let description = config.description
        #expect(description.contains("Landing fee ≤ €100"))
    }

    // MARK: - Codable

    @Test func filterConfigIsCodable() throws {
        let original = FilterConfig(
            country: "DE",
            hasProcedures: true,
            minRunwayLengthFt: 2500
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(original)

        let decoder = JSONDecoder()
        let decoded = try decoder.decode(FilterConfig.self, from: data)

        #expect(decoded == original)
    }

    // MARK: - Equatable

    @Test func filterConfigEquality() {
        let config1 = FilterConfig(country: "IT", hasProcedures: true)
        let config2 = FilterConfig(country: "IT", hasProcedures: true)
        let config3 = FilterConfig(country: "ES", hasProcedures: true)

        #expect(config1 == config2)
        #expect(config1 != config3)
    }
}
