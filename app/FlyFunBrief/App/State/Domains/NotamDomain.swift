//
//  NotamDomain.swift
//  FlyFunBrief
//
//  Manages NOTAM list, filtering, and user annotations.
//

import Foundation
import RZFlight
import CoreLocation
import OSLog

/// Status filter options
enum StatusFilter: String, CaseIterable, Identifiable {
    case all = "All"
    case unread = "Unread"
    case important = "Important"
    case followUp = "Follow Up"

    var id: String { rawValue }
}

/// Grouping options for NOTAM list
enum NotamGrouping: String, CaseIterable, Identifiable {
    case none = "None"
    case airport = "Airport"
    case category = "Category"
    case routeOrder = "Route Order"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .none: return "list.bullet"
        case .airport: return "building.2"
        case .category: return "folder"
        case .routeOrder: return "point.topleft.down.to.point.bottomright.curvepath"
        }
    }
}

/// Row display style for NOTAM list
enum NotamRowStyle: String, CaseIterable, Identifiable {
    case compact = "Compact"
    case standard = "Standard"
    case full = "Full"

    var id: String { rawValue }

    /// Maximum lines for message text in each style
    var messageLineLimit: Int {
        switch self {
        case .compact: return 0    // No message shown
        case .standard: return 2
        case .full: return 8
        }
    }

    /// Whether to show detailed info row
    var showDetailRow: Bool {
        switch self {
        case .compact: return false
        case .standard, .full: return true
        }
    }
}

/// Route corridor filter configuration
struct RouteFilter: Equatable {
    /// Space-separated ICAO codes defining the route
    var routeString: String = ""

    /// Corridor half-width in nautical miles
    var corridorWidthNm: Double = 25

    /// Whether route filtering is enabled
    var isEnabled: Bool = false

    /// Parsed ICAO codes
    var icaoCodes: [String] {
        routeString
            .uppercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { $0.count >= 3 && $0.count <= 4 }
    }
}

/// Category filter - which ICAO NOTAM categories to show
/// Categories map 1:1 to Q-code subject first letter per q_codes.json
struct CategoryFilter: Equatable {
    // 12 ICAO categories based on Q-code subject first letter
    var showAirspace: Bool = true        // A - ATM Airspace
    var showCommunications: Bool = true  // C - CNS Communications
    var showFacilities: Bool = true      // F - AGA Facilities
    var showGNSS: Bool = true            // G - CNS GNSS
    var showILS: Bool = true             // I - CNS ILS/MLS
    var showLighting: Bool = true        // L - AGA Lighting
    var showMovement: Bool = true        // M - AGA Movement (runway, taxiway)
    var showNavigation: Bool = true      // N - Navigation (VOR, DME, NDB)
    var showOther: Bool = true           // O - Other (obstacles, AIS)
    var showProcedures: Bool = true      // P - ATM Procedures (SID, STAR)
    var showRestrictions: Bool = true    // R - Airspace Restrictions
    var showServices: Bool = true        // S - ATM Services

    /// Returns enabled categories
    var enabledCategories: Set<NotamCategory> {
        var categories: Set<NotamCategory> = []
        if showAirspace { categories.insert(.atmAirspace) }
        if showCommunications { categories.insert(.cnsCommunications) }
        if showFacilities { categories.insert(.agaFacilities) }
        if showGNSS { categories.insert(.cnsGNSS) }
        if showILS { categories.insert(.cnsILS) }
        if showLighting { categories.insert(.agaLighting) }
        if showMovement { categories.insert(.agaMovement) }
        if showNavigation { categories.insert(.navigation) }
        if showOther { categories.insert(.otherInfo) }
        if showProcedures { categories.insert(.atmProcedures) }
        if showRestrictions { categories.insert(.airspaceRestrictions) }
        if showServices { categories.insert(.atmServices) }
        return categories
    }

    /// Whether all categories are enabled
    var allEnabled: Bool {
        showAirspace && showCommunications && showFacilities && showGNSS &&
        showILS && showLighting && showMovement && showNavigation &&
        showOther && showProcedures && showRestrictions && showServices
    }

    /// Enable all categories
    mutating func enableAll() {
        showAirspace = true
        showCommunications = true
        showFacilities = true
        showGNSS = true
        showILS = true
        showLighting = true
        showMovement = true
        showNavigation = true
        showOther = true
        showProcedures = true
        showRestrictions = true
        showServices = true
    }
}

/// Smart filters based on Q-code subject codes
/// These apply additional logic beyond simple category matching
struct SmartFilters: Equatable {
    // MARK: - Helicopter Filter
    /// Hide helicopter-related NOTAMs (Q-codes: FH, FP, LU, LW)
    /// Default OFF = show helicopter NOTAMs
    var hideHelicopter: Bool = true

    // MARK: - Obstacle Filter
    /// Special handling for obstacles (Q-codes: OB, OL)
    /// When enabled, only show obstacles within threshold of departure/destination
    var filterObstacles: Bool = true

    /// Distance threshold for obstacles in nautical miles
    var obstacleDistanceNm: Double = 2.0

    // MARK: - Scope Filter
    /// Filter by Q-line scope field
    var scopeFilter: ScopeFilter = .all

    /// Whether any smart filter is active
    var hasActiveFilters: Bool {
        hideHelicopter || filterObstacles || scopeFilter != .all
    }
}

/// Scope filter options from Q-line
enum ScopeFilter: String, CaseIterable, Identifiable {
    case all = "All"
    case aerodrome = "Aerodrome"      // A - Aerodrome scope
    case enroute = "En Route"         // E - En-route scope
    case warning = "Warning"          // W - Navigation warning

    var id: String { rawValue }

    /// Q-line scope codes that match this filter
    var matchingCodes: Set<Character> {
        switch self {
        case .all: return ["A", "E", "W"]
        case .aerodrome: return ["A"]
        case .enroute: return ["E"]
        case .warning: return ["W"]
        }
    }
}

/// Visibility filter - which statuses to show/hide
struct VisibilityFilter: Equatable {
    var showIgnored: Bool = false
    var showRead: Bool = true
}

/// Priority filter options
enum PriorityFilter: String, CaseIterable, Identifiable {
    case all = "All"
    case high = "High"
    case normal = "Normal"
    case low = "Low"

    var id: String { rawValue }

    /// Check if a priority matches this filter
    func matches(_ priority: NotamPriority) -> Bool {
        switch self {
        case .all: return true
        case .high: return priority == .high
        case .normal: return priority == .normal
        case .low: return priority == .low
        }
    }
}

/// Time filter - filter NOTAMs by validity at flight time
struct TimeFilter: Equatable {
    /// Whether time filtering is enabled
    var isEnabled: Bool = false

    /// Buffer time before departure (minutes)
    var preFlightBufferMinutes: Int = 60

    /// Buffer time after arrival (minutes)
    var postFlightBufferMinutes: Int = 60
}

/// Domain for NOTAM list management
@Observable
@MainActor
final class NotamDomain {
    // MARK: - State

    /// All NOTAMs from current briefing
    private(set) var allNotams: [Notam] = []

    /// Enriched NOTAMs with status (for display)
    private(set) var enrichedNotams: [EnrichedNotam] = []

    /// Current route from briefing (for spatial filtering)
    private(set) var currentRoute: Route?

    /// Briefing ID for current set of NOTAMs
    private(set) var briefingId: String?

    /// Current Core Data briefing (if available)
    private(set) var currentCDBriefing: CDBriefing?

    /// Currently selected NOTAM for detail view
    var selectedNotam: Notam?

    /// Currently selected enriched NOTAM
    var selectedEnrichedNotam: EnrichedNotam?

    /// Current grouping
    var grouping: NotamGrouping = .airport

    /// Row display style
    var rowStyle: NotamRowStyle = .standard

    /// Text search query
    var searchQuery: String = ""

    /// Identity keys from previous briefings (for new NOTAM detection)
    private(set) var previousIdentityKeys: Set<String> = []

    /// Globally ignored identity keys
    private(set) var ignoredIdentityKeys: Set<String> = []

    // MARK: - Filter State

    /// Route corridor filter
    var routeFilter = RouteFilter()

    /// Category filter
    var categoryFilter = CategoryFilter()

    /// Status filter
    var statusFilter: StatusFilter = .all

    /// Visibility filter
    var visibilityFilter = VisibilityFilter()

    /// Time filter - filter by validity at flight time
    var timeFilter = TimeFilter()

    /// Smart filters (helicopter, obstacle, scope)
    var smartFilters = SmartFilters()

    /// Airport coordinates for route filtering (populated from briefing or external source)
    var airportCoordinates: [String: CLLocationCoordinate2D] = [:]

    /// Flight context for priority evaluation (set by AppState when flight is selected)
    private(set) var currentFlightContext: FlightContext = .empty

    // MARK: - Priority Filter

    /// Priority filter - which priorities to show
    var priorityFilter: PriorityFilter = .all

    // MARK: - Computed Properties

    /// Whether any filters are active
    var hasActiveFilters: Bool {
        routeFilter.isEnabled ||
        !categoryFilter.allEnabled ||
        statusFilter != .all ||
        priorityFilter != .all ||
        !visibilityFilter.showRead ||
        visibilityFilter.showIgnored ||
        timeFilter.isEnabled ||
        smartFilters.hasActiveFilters ||
        !searchQuery.isEmpty
    }

    /// Filtered and sorted NOTAMs based on current settings
    var filteredNotams: [Notam] {
        var notams = allNotams

        // 1. Apply route corridor filter
        if routeFilter.isEnabled && !routeFilter.icaoCodes.isEmpty {
            if let route = currentRoute {
                // Use route from briefing
                notams = notams.alongRoute(route, withinNm: routeFilter.corridorWidthNm)
            } else if !airportCoordinates.isEmpty {
                // Use manually entered route with coordinates
                notams = notams.alongRoute(
                    icaoCodes: routeFilter.routeString,
                    withinNm: routeFilter.corridorWidthNm,
                    airportCoordinates: airportCoordinates
                )
            }
        }

        // 2. Apply category filter
        if !categoryFilter.allEnabled {
            let enabled = categoryFilter.enabledCategories
            notams = notams.filter { notam in
                guard let category = notam.icaoCategory else { return categoryFilter.showOther }
                return enabled.contains(category)
            }
        }

        // 3. Apply smart filters
        notams = applySmartFilters(to: notams)

        // 4. Apply text search
        if !searchQuery.isEmpty {
            notams = notams.containing(searchQuery)
        }

        // 5. Apply status filter
        switch statusFilter {
        case .all:
            break
        case .unread:
            notams = notams.filter { enrichedNotam(for: $0)?.status == .unread }
        case .important:
            notams = notams.filter { enrichedNotam(for: $0)?.status == .important }
        case .followUp:
            notams = notams.filter { enrichedNotam(for: $0)?.status == .followUp }
        }

        // 6. Apply visibility filter
        if !visibilityFilter.showIgnored {
            notams = notams.filter { enrichedNotam(for: $0)?.status != .ignore }
        }
        if !visibilityFilter.showRead {
            notams = notams.filter { enrichedNotam(for: $0)?.status != .read }
        }

        return notams
    }

    /// Filtered enriched NOTAMs based on current settings
    var filteredEnrichedNotams: [EnrichedNotam] {
        var notams = enrichedNotams

        // 1. Apply global ignore filter first (unless showing ignored)
        if !visibilityFilter.showIgnored {
            notams = notams.excludingIgnored()
        }

        // 2. Apply route corridor filter (filter underlying Notam objects)
        if routeFilter.isEnabled && !routeFilter.icaoCodes.isEmpty {
            let routeFilteredIds: Set<String>
            if let route = currentRoute {
                routeFilteredIds = Set(allNotams.alongRoute(route, withinNm: routeFilter.corridorWidthNm).map { $0.id })
            } else if !airportCoordinates.isEmpty {
                routeFilteredIds = Set(allNotams.alongRoute(
                    icaoCodes: routeFilter.routeString,
                    withinNm: routeFilter.corridorWidthNm,
                    airportCoordinates: airportCoordinates
                ).map { $0.id })
            } else {
                routeFilteredIds = Set(allNotams.map { $0.id })
            }
            notams = notams.filter { routeFilteredIds.contains($0.notamId) }
        }

        // 3. Apply time filter (filter by validity at flight time)
        if timeFilter.isEnabled, let route = currentRoute, let depTime = route.departureTime {
            let preBuffer = TimeInterval(timeFilter.preFlightBufferMinutes * 60)
            let postBuffer = TimeInterval(timeFilter.postFlightBufferMinutes * 60)
            let windowStart = depTime.addingTimeInterval(-preBuffer)
            let windowEnd = (route.arrivalTime ?? depTime).addingTimeInterval(postBuffer)

            notams = notams.filter { enriched in
                enriched.isActive(during: windowStart, to: windowEnd)
            }
        }

        // 4. Apply category filter
        if !categoryFilter.allEnabled {
            let enabled = categoryFilter.enabledCategories
            notams = notams.filter { enriched in
                guard let category = enriched.icaoCategory else { return categoryFilter.showOther }
                return enabled.contains(category)
            }
        }

        // 5. Apply smart filters
        notams = applySmartFilters(to: notams)

        // 6. Apply text search
        if !searchQuery.isEmpty {
            let searchLower = searchQuery.lowercased()
            notams = notams.filter { enriched in
                enriched.message.lowercased().contains(searchLower) ||
                enriched.notamId.lowercased().contains(searchLower) ||
                enriched.location.lowercased().contains(searchLower)
            }
        }

        // 7. Apply status filter
        switch statusFilter {
        case .all:
            break
        case .unread:
            notams = notams.filter { $0.status == .unread }
        case .important:
            notams = notams.filter { $0.status == .important }
        case .followUp:
            notams = notams.filter { $0.status == .followUp }
        }

        // 8. Apply visibility filter (local ignore status)
        if !visibilityFilter.showIgnored {
            notams = notams.filter { $0.status != .ignore }
        }
        if !visibilityFilter.showRead {
            notams = notams.filter { $0.status != .read }
        }

        // 9. Apply priority filter
        if priorityFilter != .all {
            notams = notams.filter { priorityFilter.matches($0.priority) }
        }

        return notams
    }

    /// NOTAMs grouped by airport
    var notamsGroupedByAirport: [String: [Notam]] {
        filteredNotams.groupedByAirport()
    }

    /// Enriched NOTAMs grouped by airport
    var enrichedNotamsGroupedByAirport: [String: [EnrichedNotam]] {
        filteredEnrichedNotams.groupedByAirport()
    }

    /// NOTAMs grouped by category
    var notamsGroupedByCategory: [NotamCategory: [Notam]] {
        filteredNotams.groupedByCategory()
    }

    /// Enriched NOTAMs grouped by category
    var enrichedNotamsGroupedByCategory: [NotamCategory: [EnrichedNotam]] {
        filteredEnrichedNotams.groupedByCategory()
    }

    /// Enriched NOTAMs grouped by route segment
    ///
    /// Returns NOTAMs organized by: Departure, En Route (sorted by distance), Destination,
    /// Alternates, Distant (>50nm), No Coordinates
    var enrichedNotamsGroupedByRouteSegment: [(segment: NotamRouteClassification.RouteSegment, notams: [EnrichedNotam])] {
        guard let route = currentRoute else {
            // No route - put everything in noCoordinate segment
            return [(.noCoordinate, filteredEnrichedNotams)]
        }

        // Classify underlying NOTAMs
        let notamArray = filteredEnrichedNotams.map { $0.notam }
        let classified = notamArray.groupedByRouteSegment(route: route, distantThresholdNm: 50.0)

        // Map back to EnrichedNotam, preserving order
        let enrichedById = Dictionary(uniqueKeysWithValues: filteredEnrichedNotams.map { ($0.notamId, $0) })

        var result: [(NotamRouteClassification.RouteSegment, [EnrichedNotam])] = []

        // Add segments in display order
        for segment in NotamRouteClassification.RouteSegment.allCases {
            guard let items = classified[segment], !items.isEmpty else { continue }
            let enrichedItems = items.compactMap { enrichedById[$0.notam.id] }
            if !enrichedItems.isEmpty {
                result.append((segment, enrichedItems))
            }
        }

        return result
    }

    /// Count of unread NOTAMs
    var unreadCount: Int {
        enrichedNotams.unreadCount
    }

    /// Count of important NOTAMs
    var importantCount: Int {
        enrichedNotams.importantCount
    }

    /// Count of new NOTAMs (not seen in previous briefings)
    var newNotamCount: Int {
        enrichedNotams.newCount
    }

    /// Count of high priority NOTAMs
    var highPriorityCount: Int {
        enrichedNotams.highPriorityCount
    }

    // MARK: - Dependencies

    private let flightRepository: FlightRepository
    private var ignoreListManager: IgnoreListManager?
    private var globalReadManager: GlobalReadManager?

    /// Resurface settings for 3-tier status resolution
    var resurfaceSettings: ResurfaceSettings = .default

    /// Cached global read records keyed by identity key
    private var globalReads: [String: CDGlobalNotamRead] = [:]

    // MARK: - Init

    init(flightRepository: FlightRepository, ignoreListManager: IgnoreListManager? = nil, globalReadManager: GlobalReadManager? = nil) {
        self.flightRepository = flightRepository
        self.ignoreListManager = ignoreListManager
        self.globalReadManager = globalReadManager
    }

    /// Update the ignore list manager reference
    func setIgnoreListManager(_ manager: IgnoreListManager) {
        self.ignoreListManager = manager
    }

    /// Update the global read manager reference
    func setGlobalReadManager(_ manager: GlobalReadManager) {
        self.globalReadManager = manager
    }

    /// Update the flight context for priority evaluation.
    ///
    /// Call this when the flight is selected or updated. The context is used
    /// to compute route distance, altitude relevance, and priority for each NOTAM.
    ///
    /// - Parameter context: The flight context, or nil to clear
    func setFlightContext(_ context: FlightContext?) {
        self.currentFlightContext = context ?? .empty
        // Re-enrich NOTAMs with new context
        refreshEnrichedNotams()
    }

    // MARK: - Actions

    /// Set NOTAMs from a loaded briefing (standalone mode without Core Data flight)
    /// Note: In this mode, status persistence is not available.
    /// Use setBriefing(_:cdBriefing:previousKeys:) for full functionality.
    func setBriefing(_ briefing: Briefing) {
        self.briefingId = briefing.id
        self.allNotams = briefing.notams
        self.currentRoute = briefing.route
        self.currentCDBriefing = nil
        self.selectedNotam = nil
        self.selectedEnrichedNotam = nil
        self.previousIdentityKeys = []

        // Pre-populate route filter from briefing route
        if let route = briefing.route {
            var routeAirports = [route.departure, route.destination]
            routeAirports.append(contentsOf: route.alternates)
            routeFilter.routeString = routeAirports.joined(separator: " ")

            // Extract coordinates from route for filtering
            if let depCoord = route.departureCoordinate {
                airportCoordinates[route.departure.uppercased()] = depCoord
            }
            if let destCoord = route.destinationCoordinate {
                airportCoordinates[route.destination.uppercased()] = destCoord
            }
        }

        // Build enriched NOTAMs (standalone mode - all unread)
        Task {
            await loadIgnoredKeys()
            await loadGlobalReads()
            buildEnrichedNotamsStandalone()
        }

        Logger.app.info("NotamDomain loaded \(briefing.notams.count) NOTAMs (standalone mode)")
    }

    /// Set NOTAMs from a Core Data briefing with status tracking
    func setBriefing(_ briefing: Briefing, cdBriefing: CDBriefing, previousKeys: Set<String>) {
        self.briefingId = briefing.id
        self.allNotams = briefing.notams
        self.currentRoute = briefing.route
        self.currentCDBriefing = cdBriefing
        self.selectedNotam = nil
        self.selectedEnrichedNotam = nil
        self.previousIdentityKeys = previousKeys

        // Pre-populate route filter from briefing route
        if let route = briefing.route {
            var routeAirports = [route.departure, route.destination]
            routeAirports.append(contentsOf: route.alternates)
            routeFilter.routeString = routeAirports.joined(separator: " ")

            // Extract coordinates from route for filtering
            if let depCoord = route.departureCoordinate {
                airportCoordinates[route.departure.uppercased()] = depCoord
            }
            if let destCoord = route.destinationCoordinate {
                airportCoordinates[route.destination.uppercased()] = destCoord
            }
        }

        // Build enriched NOTAMs from Core Data statuses
        Task {
            await loadIgnoredKeys()
            await loadGlobalReads()
            buildEnrichedNotamsFromCoreData()
        }

        Logger.app.info("NotamDomain loaded \(briefing.notams.count) NOTAMs from Core Data")
    }

    /// Load globally ignored identity keys
    private func loadIgnoredKeys() async {
        guard let manager = ignoreListManager else {
            ignoredIdentityKeys = []
            return
        }

        do {
            ignoredIdentityKeys = try manager.getIgnoredIdentityKeys()
        } catch {
            Logger.app.error("Failed to load ignored keys: \(error.localizedDescription)")
            ignoredIdentityKeys = []
        }
    }

    /// Load global read records
    private func loadGlobalReads() async {
        guard let manager = globalReadManager else {
            globalReads = [:]
            return
        }

        do {
            globalReads = try manager.getReadRecords()
        } catch {
            Logger.app.error("Failed to load global reads: \(error.localizedDescription)")
            globalReads = [:]
        }
    }

    /// Build enriched NOTAMs for standalone mode (no Core Data)
    /// All NOTAMs start as unread in this mode
    private func buildEnrichedNotamsStandalone() {
        enrichedNotams = EnrichedNotam.enrich(
            notams: allNotams,
            statuses: [:],  // No Core Data statuses
            previousIdentityKeys: previousIdentityKeys,
            ignoredKeys: ignoredIdentityKeys,
            flightContext: currentFlightContext
        )
    }

    /// Build enriched NOTAMs from Core Data statuses with 3-tier status resolution.
    ///
    /// Status resolution priority:
    /// 1. Briefing status (CDNotamStatus) - if not unread, use it
    /// 2. Global read (CDGlobalNotamRead) - if exists and doesn't resurface, use read
    /// 3. Unread (default)
    private func buildEnrichedNotamsFromCoreData() {
        guard let cdBriefing = currentCDBriefing else {
            buildEnrichedNotamsStandalone()
            return
        }

        let statuses = cdBriefing.statusesByNotamId
        let resurfaceEvaluator = NotamResurfaceEvaluator.shared

        enrichedNotams = EnrichedNotam.enrichWithGlobalReads(
            notams: allNotams,
            statuses: statuses,
            globalReads: globalReads,
            previousIdentityKeys: previousIdentityKeys,
            ignoredKeys: ignoredIdentityKeys,
            flightContext: currentFlightContext,
            resurfaceEvaluator: resurfaceEvaluator,
            resurfaceSettings: resurfaceSettings
        )
    }

    /// Refresh enriched NOTAMs (call after status changes)
    func refreshEnrichedNotams() {
        if currentCDBriefing != nil {
            buildEnrichedNotamsFromCoreData()
        } else {
            buildEnrichedNotamsStandalone()
        }
    }

    /// Clear all NOTAMs
    func clearBriefing() {
        allNotams = []
        enrichedNotams = []
        currentRoute = nil
        briefingId = nil
        currentCDBriefing = nil
        selectedNotam = nil
        selectedEnrichedNotam = nil
        airportCoordinates = [:]
        previousIdentityKeys = []
    }

    /// Reset all filters to defaults
    func resetFilters() {
        routeFilter = RouteFilter()
        categoryFilter = CategoryFilter()
        statusFilter = .all
        priorityFilter = .all
        visibilityFilter = VisibilityFilter()
        timeFilter = TimeFilter()
        smartFilters = SmartFilters()
        searchQuery = ""

        // Re-populate route from briefing if available
        if let route = currentRoute {
            var routeAirports = [route.departure, route.destination]
            routeAirports.append(contentsOf: route.alternates)
            routeFilter.routeString = routeAirports.joined(separator: " ")
        }
    }

    /// Get enriched NOTAM for a given notam
    func enrichedNotam(for notam: Notam) -> EnrichedNotam? {
        enrichedNotams.first { $0.notamId == notam.id }
    }

    /// Update status for a NOTAM (persists to Core Data)
    ///
    /// Implements 3-tier status propagation:
    /// - `read`: Also marks globally read for cross-briefing status
    /// - `important/followUp`: Propagates to all briefings in this flight
    func setStatus(_ status: NotamStatus, for notam: Notam) {
        guard let cdBriefing = currentCDBriefing else {
            Logger.app.warning("Cannot set status without Core Data briefing")
            return
        }

        do {
            // Update briefing-level status
            try flightRepository.updateNotamStatus(notam, briefing: cdBriefing, status: status)

            // Handle status-specific propagation
            switch status {
            case .read:
                // Also mark globally read
                try markGloballyRead(notam)

            case .important, .followUp:
                // Propagate to all briefings in this flight
                try propagateStatusAcrossBriefings(notam, status: status)

            case .unread, .ignore:
                // No additional propagation needed
                break
            }

            refreshEnrichedNotams()
        } catch {
            Logger.app.error("Failed to update NOTAM status: \(error.localizedDescription)")
        }
    }

    /// Mark a NOTAM as globally read
    private func markGloballyRead(_ notam: Notam) throws {
        guard let manager = globalReadManager else {
            Logger.app.debug("GlobalReadManager not available - skipping global read")
            return
        }

        // Generate route hash from current context
        let routeHash = RouteHasher.hash(from: currentFlightContext)

        _ = try manager.markAsRead(notam, routeHash: routeHash.isEmpty ? nil : routeHash)

        // Update local cache
        let identityKey = NotamIdentity.key(for: notam)
        if let record = manager.getReadRecord(identityKey: identityKey) {
            globalReads[identityKey] = record
        }

        Logger.app.debug("Marked NOTAM \(notam.id) as globally read")
    }

    /// Propagate important/followUp status to all briefings in this flight
    private func propagateStatusAcrossBriefings(_ notam: Notam, status: NotamStatus) throws {
        guard let cdBriefing = currentCDBriefing,
              let flight = cdBriefing.flight else {
            return
        }

        try flightRepository.propagateStatusAcrossBriefings(
            notam,
            status: status,
            flight: flight,
            excludingBriefing: cdBriefing
        )

        Logger.app.debug("Propagated \(status.displayName) status for NOTAM \(notam.id) across flight briefings")
    }

    /// Add a text note to a NOTAM (persists to Core Data)
    func setNote(_ note: String?, for notam: Notam) {
        guard let cdBriefing = currentCDBriefing else {
            Logger.app.warning("Cannot set note without Core Data briefing")
            return
        }

        // Get current status to preserve it
        let currentStatus = enrichedNotam(for: notam)?.status ?? .unread

        do {
            try flightRepository.updateNotamStatus(notam, briefing: cdBriefing, status: currentStatus, textNote: note)
            refreshEnrichedNotams()
        } catch {
            Logger.app.error("Failed to update NOTAM note: \(error.localizedDescription)")
        }
    }

    /// Mark a NOTAM as read
    func markAsRead(_ notam: Notam) {
        if enrichedNotam(for: notam)?.status == .unread {
            setStatus(.read, for: notam)
        }
    }

    /// Toggle important status
    func toggleImportant(_ notam: Notam) {
        let current = enrichedNotam(for: notam)?.status ?? .unread
        let newStatus: NotamStatus = (current == .important) ? .read : .important
        setStatus(newStatus, for: notam)
    }

    /// Mark NOTAM as ignored (local status)
    func markAsIgnored(_ notam: Notam) {
        setStatus(.ignore, for: notam)
    }

    /// Add NOTAM to the global ignore list
    func addToGlobalIgnoreList(_ notam: Notam, reason: String? = nil) async {
        guard let manager = ignoreListManager else {
            Logger.app.warning("IgnoreListManager not available")
            return
        }

        do {
            _ = try manager.addToIgnoreList(notam, reason: reason)

            // Refresh ignored keys and enriched NOTAMs
            await loadIgnoredKeys()
            refreshEnrichedNotams()

            Logger.app.info("Added NOTAM \(notam.id) to global ignore list")
        } catch {
            Logger.app.error("Failed to add to ignore list: \(error.localizedDescription)")
        }
    }

    /// Remove NOTAM from the global ignore list
    func removeFromGlobalIgnoreList(_ notam: Notam) async {
        guard let manager = ignoreListManager else { return }

        let identityKey = NotamIdentity.key(for: notam)

        do {
            try manager.removeFromIgnoreList(identityKey: identityKey)

            // Refresh ignored keys and enriched NOTAMs
            await loadIgnoredKeys()
            refreshEnrichedNotams()

            Logger.app.info("Removed NOTAM \(notam.id) from global ignore list")
        } catch {
            Logger.app.error("Failed to remove from ignore list: \(error.localizedDescription)")
        }
    }

    /// Check if a NOTAM is globally ignored
    func isGloballyIgnored(_ notam: Notam) -> Bool {
        let identityKey = NotamIdentity.key(for: notam)
        return ignoredIdentityKeys.contains(identityKey)
    }

    // MARK: - Smart Filter Helpers

    /// Q-code subjects for helicopter-related NOTAMs
    private static let helicopterSubjects: Set<String> = ["FH", "FP", "LU", "LW"]

    /// Q-code subjects for obstacle NOTAMs
    private static let obstacleSubjects: Set<String> = ["OB", "OL"]

    /// Apply smart filters to raw NOTAM array
    private func applySmartFilters(to notams: [Notam]) -> [Notam] {
        var result = notams

        // 1. Helicopter filter - hide if enabled
        if smartFilters.hideHelicopter {
            result = result.filter { notam in
                guard let subject = notam.qCodeSubject else { return true }
                return !Self.helicopterSubjects.contains(subject)
            }
        }

        // 2. Obstacle filter - only show obstacles near departure/destination
        if smartFilters.filterObstacles, let route = currentRoute {
            let depCoord = route.departureCoordinate
            let destCoord = route.destinationCoordinate

            result = result.filter { notam in
                guard let subject = notam.qCodeSubject,
                      Self.obstacleSubjects.contains(subject) else {
                    // Not an obstacle - keep it
                    return true
                }

                // Obstacle NOTAM - check if near dep/dest
                guard let notamCoord = notam.coordinate else {
                    // No coordinates - include by default for safety
                    return true
                }

                let notamLoc = CLLocation(
                    latitude: notamCoord.latitude,
                    longitude: notamCoord.longitude
                )

                // Check distance to departure
                if let coord = depCoord {
                    let depLoc = CLLocation(latitude: coord.latitude, longitude: coord.longitude)
                    let distNm = notamLoc.distance(from: depLoc) / 1852.0
                    if distNm <= smartFilters.obstacleDistanceNm {
                        return true
                    }
                }

                // Check distance to destination
                if let coord = destCoord {
                    let destLoc = CLLocation(latitude: coord.latitude, longitude: coord.longitude)
                    let distNm = notamLoc.distance(from: destLoc) / 1852.0
                    if distNm <= smartFilters.obstacleDistanceNm {
                        return true
                    }
                }

                // Obstacle too far from airports
                return false
            }
        }

        // 3. Scope filter
        if smartFilters.scopeFilter != .all {
            let matchingCodes = smartFilters.scopeFilter.matchingCodes
            result = result.filter { notam in
                guard let scope = notam.scope, !scope.isEmpty else {
                    // No scope info - include by default
                    return true
                }
                // Check if any character in scope matches the filter
                return scope.uppercased().contains { matchingCodes.contains($0) }
            }
        }

        return result
    }

    /// Apply smart filters to enriched NOTAM array
    private func applySmartFilters(to notams: [EnrichedNotam]) -> [EnrichedNotam] {
        var result = notams

        // 1. Helicopter filter
        if smartFilters.hideHelicopter {
            result = result.filter { enriched in
                guard let subject = enriched.notam.qCodeSubject else { return true }
                return !Self.helicopterSubjects.contains(subject)
            }
        }

        // 2. Obstacle filter
        if smartFilters.filterObstacles, let route = currentRoute {
            let depCoord = route.departureCoordinate
            let destCoord = route.destinationCoordinate

            result = result.filter { enriched in
                let notam = enriched.notam
                guard let subject = notam.qCodeSubject,
                      Self.obstacleSubjects.contains(subject) else {
                    return true
                }

                guard let notamCoord = notam.coordinate else {
                    return true
                }

                let notamLoc = CLLocation(
                    latitude: notamCoord.latitude,
                    longitude: notamCoord.longitude
                )

                if let coord = depCoord {
                    let depLoc = CLLocation(latitude: coord.latitude, longitude: coord.longitude)
                    if notamLoc.distance(from: depLoc) / 1852.0 <= smartFilters.obstacleDistanceNm {
                        return true
                    }
                }

                if let coord = destCoord {
                    let destLoc = CLLocation(latitude: coord.latitude, longitude: coord.longitude)
                    if notamLoc.distance(from: destLoc) / 1852.0 <= smartFilters.obstacleDistanceNm {
                        return true
                    }
                }

                return false
            }
        }

        // 3. Scope filter
        if smartFilters.scopeFilter != .all {
            let matchingCodes = smartFilters.scopeFilter.matchingCodes
            result = result.filter { enriched in
                guard let scope = enriched.notam.scope, !scope.isEmpty else {
                    return true
                }
                return scope.uppercased().contains { matchingCodes.contains($0) }
            }
        }

        return result
    }
}
