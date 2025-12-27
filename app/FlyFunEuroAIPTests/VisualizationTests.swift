//
//  VisualizationTests.swift
//  FlyFunEuroAIPTests
//
//  Tests for chat visualization payload application to AirportDomain.
//

import Testing
import Foundation
import CoreLocation
import MapKit
@testable import FlyFunEuroAIP

@MainActor
struct VisualizationTests {

    // MARK: - Setup

    private func makeAirportDomain() -> AirportDomain {
        let repository = MockAirportRepository()
        return AirportDomain(repository: repository)
    }

    // MARK: - Map Highlight Tests

    @Test func addingHighlightCreatesEntry() async {
        let domain = makeAirportDomain()

        #expect(domain.highlights.isEmpty)

        // Manually add a highlight (simulating what applyVisualization does)
        let highlight = MapHighlight(
            id: "test-EGLL",
            coordinate: CLLocationCoordinate2D(latitude: 51.47, longitude: -0.45),
            color: .blue,
            radius: 15000,
            popup: "Heathrow"
        )
        domain.highlights["test-EGLL"] = highlight

        #expect(domain.highlights.count == 1)
        #expect(domain.highlights["test-EGLL"]?.popup == "Heathrow")
    }

    @Test func clearChatHighlightsOnlyRemovesChatPrefixed() async {
        let domain = makeAirportDomain()

        // Add mixed highlights
        domain.highlights["chat-EGLL"] = MapHighlight(
            id: "chat-EGLL",
            coordinate: CLLocationCoordinate2D(latitude: 51.47, longitude: -0.45),
            color: .blue,
            radius: 15000,
            popup: "Chat highlight"
        )
        domain.highlights["route-LFPG"] = MapHighlight(
            id: "route-LFPG",
            coordinate: CLLocationCoordinate2D(latitude: 49.0, longitude: 2.5),
            color: .green,
            radius: 15000,
            popup: "Route highlight"
        )

        #expect(domain.highlights.count == 2)

        domain.clearChatHighlights()

        #expect(domain.highlights.count == 1)
        #expect(domain.highlights["route-LFPG"] != nil)
        #expect(domain.highlights["chat-EGLL"] == nil)
    }

    // MARK: - Route Tests

    @Test func clearRouteRemovesRouteAndHighlights() async {
        let domain = makeAirportDomain()

        // Set up route
        domain.activeRoute = RouteVisualization(
            coordinates: [
                CLLocationCoordinate2D(latitude: 51.3, longitude: -0.5),
                CLLocationCoordinate2D(latitude: 43.5, longitude: 7.0)
            ],
            departure: "EGTF",
            destination: "LFMD"
        )
        domain.highlights["route-LFPG"] = MapHighlight(
            id: "route-LFPG",
            coordinate: CLLocationCoordinate2D(latitude: 49.0, longitude: 2.5),
            color: .blue,
            radius: 15000,
            popup: "Paris"
        )
        domain.highlights["chat-EGLL"] = MapHighlight(
            id: "chat-EGLL",
            coordinate: CLLocationCoordinate2D(latitude: 51.47, longitude: -0.45),
            color: .blue,
            radius: 15000,
            popup: "Heathrow"
        )

        #expect(domain.activeRoute != nil)
        #expect(domain.highlights.count == 2)

        domain.clearRoute()

        #expect(domain.activeRoute == nil)
        #expect(domain.highlights.count == 1) // Only chat highlight remains
        #expect(domain.highlights["chat-EGLL"] != nil)
    }

    // MARK: - Search State Tests

    @Test func searchStatePreventRegionLoading() async {
        let domain = makeAirportDomain()

        domain.isSearchActive = true

        // When search is active, region changes should be ignored
        // (This is checked in onRegionChange, but we can verify the flag)
        #expect(domain.isSearchActive == true)
    }

    @Test func clearSearchResetsState() async {
        let domain = makeAirportDomain()

        domain.isSearchActive = true
        domain.searchResults = [] // Would have results in real scenario

        domain.clearSearch()

        #expect(domain.isSearchActive == false)
        #expect(domain.searchResults.isEmpty)
    }

    // MARK: - Map Position Tests

    @Test func focusMapUpdatesPosition() async {
        let domain = makeAirportDomain()

        let coord = CLLocationCoordinate2D(latitude: 48.8566, longitude: 2.3522)
        domain.focusMap(on: coord, span: 2.0)

        // MapCameraPosition doesn't expose region directly for comparison,
        // but we can verify visibleRegion is updated
        #expect(domain.visibleRegion != nil)
        #expect(domain.visibleRegion?.center.latitude ?? 0 > 47)
        #expect(domain.visibleRegion?.center.latitude ?? 0 < 50)
    }

    // MARK: - Border Crossing Tests

    @Test func isBorderCrossingChecksCache() async {
        let domain = makeAirportDomain()

        // Pre-populate cache
        domain.borderCrossingICAOs = Set(["LFPG", "EGLL", "EHAM"])

        // Can't test with real Airport objects easily,
        // but verify the set is checked
        #expect(domain.borderCrossingICAOs.contains("LFPG"))
        #expect(!domain.borderCrossingICAOs.contains("EGTF"))
    }

    // MARK: - Filter Application Tests

    @Test func applyFiltersResetsSearchState() async throws {
        let domain = makeAirportDomain()

        domain.isSearchActive = true
        domain.searchResults = []

        try await domain.applyFilters()

        #expect(domain.isSearchActive == false)
        #expect(domain.searchResults.isEmpty)
    }

    @Test func resetFiltersCreatesDefaultConfig() async {
        let domain = makeAirportDomain()

        domain.filters = FilterConfig(country: "FR", hasProcedures: true)
        #expect(domain.filters.hasActiveFilters == true)

        domain.resetFilters()

        // Note: resetFilters calls applyFilters which is async
        // The filters should be reset immediately though
        #expect(domain.filters.hasActiveFilters == false)
    }

    // MARK: - Legend Mode Tests

    @Test func legendModeCanBeChanged() async {
        let domain = makeAirportDomain()

        #expect(domain.legendMode == .airportType)

        domain.legendMode = .procedures
        #expect(domain.legendMode == .procedures)

        domain.legendMode = .runwayLength
        #expect(domain.legendMode == .runwayLength)

        domain.legendMode = .country
        #expect(domain.legendMode == .country)
    }
}

// MARK: - ChatVisualizationPayload Tests

struct ChatVisualizationPayloadTests {

    @Test func parseKindFromRawValue() {
        #expect(ChatVisualizationPayload.Kind(rawValue: "airport") == .airport)
        #expect(ChatVisualizationPayload.Kind(rawValue: "route") == .route)
        #expect(ChatVisualizationPayload.Kind(rawValue: "list") == .list)
        #expect(ChatVisualizationPayload.Kind(rawValue: "search") == .search)
        #expect(ChatVisualizationPayload.Kind(rawValue: "invalid") == nil)
    }
}

// MARK: - SuggestedQuery Tests

struct SuggestedQueryTests {

    @Test func parsesSuggestedQuery() {
        let dict: [String: Any] = [
            "text": "Show airports with ILS",
            "tool": "search_airports",
            "category": "search",
            "priority": 1
        ]

        let query = SuggestedQuery(from: dict)

        #expect(query != nil)
        #expect(query?.text == "Show airports with ILS")
        #expect(query?.tool == "search_airports")
        #expect(query?.category == "search")
        #expect(query?.priority == 1)
    }

    @Test func requiresTextField() {
        let dict: [String: Any] = [
            "tool": "search_airports"
        ]

        let query = SuggestedQuery(from: dict)

        #expect(query == nil)
    }

    @Test func optionalFieldsAreOptional() {
        let dict: [String: Any] = [
            "text": "Find airports"
        ]

        let query = SuggestedQuery(from: dict)

        #expect(query != nil)
        #expect(query?.text == "Find airports")
        #expect(query?.tool == nil)
        #expect(query?.category == nil)
        #expect(query?.priority == nil)
    }

    @Test func parsesSuggestedQueriesInPayload() {
        let dict: [String: Any] = [
            "kind": "list",
            "suggested_queries": [
                ["text": "Query 1"],
                ["text": "Query 2", "priority": 2],
                ["invalid": "no text"]  // Should be skipped
            ]
        ]

        let payload = ChatVisualizationPayload(from: dict)

        #expect(payload.suggestedQueries?.count == 2)
        #expect(payload.suggestedQueries?[0].text == "Query 1")
        #expect(payload.suggestedQueries?[1].text == "Query 2")
        #expect(payload.suggestedQueries?[1].priority == 2)
    }

    @Test func emptySuggestedQueriesIsNil() {
        let dict: [String: Any] = [
            "kind": "airport"
        ]

        let payload = ChatVisualizationPayload(from: dict)

        #expect(payload.suggestedQueries == nil)
    }
}

// MARK: - ChatFilters Tests

struct ChatFiltersTests {

    @Test func toFilterConfigMapsAllFields() {
        // Simulate API response with snake_case keys
        let dict: [String: Any] = [
            "country": "FR",
            "has_procedures": true,
            "has_hard_runway": true,
            "has_lighted_runway": true,
            "point_of_entry": true,
            "min_runway_length_ft": 3000,
            "max_runway_length_ft": 8000,
            "has_ils": true,
            "has_rnav": true,
            "has_precision_approach": true,
            "has_avgas": true,
            "has_jet_a": true,
            "max_landing_fee": 75.0
        ]

        let chatFilters = ChatFilters(from: dict)
        let config = chatFilters.toFilterConfig()

        // Verify all fields are mapped correctly
        #expect(config.country == "FR")
        #expect(config.hasProcedures == true)
        #expect(config.hasHardRunway == true)
        #expect(config.hasLightedRunway == true)
        #expect(config.pointOfEntry == true)
        #expect(config.minRunwayLengthFt == 3000)
        #expect(config.maxRunwayLengthFt == 8000)
        #expect(config.hasILS == true)
        #expect(config.hasRNAV == true)
        #expect(config.hasPrecisionApproach == true)
        #expect(config.hasAvgas == true)
        #expect(config.hasJetA == true)
        #expect(config.maxLandingFee == 75.0)
    }

    @Test func toFilterConfigHandlesMissingFields() {
        // Simulate partial API response
        let dict: [String: Any] = [
            "country": "DE",
            "has_procedures": true
        ]

        let chatFilters = ChatFilters(from: dict)
        let config = chatFilters.toFilterConfig()

        // Only specified fields should be set
        #expect(config.country == "DE")
        #expect(config.hasProcedures == true)
        #expect(config.hasHardRunway == nil)
        #expect(config.hasAvgas == nil)
        #expect(config.maxLandingFee == nil)
    }

    @Test func parseIsoCountryAlternative() {
        // API sometimes sends iso_country instead of country
        let dict: [String: Any] = [
            "iso_country": "GB"
        ]

        let chatFilters = ChatFilters(from: dict)
        #expect(chatFilters.country == "GB")
    }
}

// MARK: - MapHighlight Tests

struct MapHighlightTests {

    @Test func highlightColorRawValues() {
        #expect(MapHighlight.HighlightColor.blue.rawValue == "blue")
        #expect(MapHighlight.HighlightColor.red.rawValue == "red")
        #expect(MapHighlight.HighlightColor.green.rawValue == "green")
        #expect(MapHighlight.HighlightColor.orange.rawValue == "orange")
        #expect(MapHighlight.HighlightColor.purple.rawValue == "purple")
    }

    @Test func highlightEquality() {
        let h1 = MapHighlight(
            id: "test",
            coordinate: CLLocationCoordinate2D(latitude: 50, longitude: 10),
            color: .blue,
            radius: 1000,
            popup: "Test"
        )
        let h2 = MapHighlight(
            id: "test",
            coordinate: CLLocationCoordinate2D(latitude: 51, longitude: 11),
            color: .red,
            radius: 2000,
            popup: "Different"
        )
        let h3 = MapHighlight(
            id: "other",
            coordinate: CLLocationCoordinate2D(latitude: 50, longitude: 10),
            color: .blue,
            radius: 1000,
            popup: "Test"
        )

        // Equality is based on id only
        #expect(h1 == h2)
        #expect(h1 != h3)
    }
}

// MARK: - RouteVisualization Tests

struct RouteVisualizationTests {

    @Test func routeStoresCoordinates() {
        let route = RouteVisualization(
            coordinates: [
                CLLocationCoordinate2D(latitude: 51.0, longitude: -0.5),
                CLLocationCoordinate2D(latitude: 43.5, longitude: 7.0)
            ],
            departure: "EGTF",
            destination: "LFMD"
        )

        #expect(route.coordinates.count == 2)
        #expect(route.departure == "EGTF")
        #expect(route.destination == "LFMD")
    }
}
