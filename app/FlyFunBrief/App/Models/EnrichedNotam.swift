//
//  EnrichedNotam.swift
//  FlyFunBrief
//
//  Display model combining NOTAM data with user status, flight context, and computed priority.
//

import Foundation
import RZFlight

/// NOTAM enriched with user status, flight context, and computed priority for display.
///
/// This model combines:
/// - The raw NOTAM from RZFlight
/// - User-assigned status (read/important/etc.)
/// - Flight context relevance (distance, altitude, time)
/// - Computed priority based on rules
///
/// All context-dependent values are computed once at enrichment time,
/// keeping views simple and avoiding repeated calculations.
struct EnrichedNotam: Identifiable {
    // MARK: - Core NOTAM

    /// The underlying NOTAM from RZFlight
    let notam: Notam

    // MARK: - Identity

    /// Identity key for matching across briefings
    let identityKey: String

    // MARK: - User Status

    /// User-assigned status (read, important, etc.)
    var status: NotamStatus

    /// User's text note
    var textNote: String?

    /// When the status was last changed
    var statusChangedAt: Date?

    // MARK: - New NOTAM Indicator

    /// Whether this NOTAM is new (not seen in previous briefings)
    let isNew: Bool

    // MARK: - Ignored Status

    /// Whether this NOTAM matches a global ignore entry
    let isGloballyIgnored: Bool

    /// Whether this NOTAM's airport is in the airport ignore list
    let isAirportIgnored: Bool

    // MARK: - Flight Context (computed at enrichment time)

    /// Distance from route centerline in nautical miles.
    /// Nil if no route or NOTAM has no coordinates.
    let routeDistanceNm: Double?

    /// Whether the NOTAM altitude range overlaps cruise altitude ±2000ft.
    /// False if no cruise altitude set or NOTAM is surface-to-unlimited.
    let isAltitudeRelevant: Bool

    /// Whether the NOTAM is active during the flight window (±2h buffer).
    /// True if no flight time is set (assume potentially active).
    let isActiveForFlight: Bool

    /// Computed priority based on rules evaluation.
    let priority: NotamPriority

    // MARK: - Identifiable

    var id: String { notam.id }

    // MARK: - Initialization

    init(
        notam: Notam,
        status: NotamStatus = .unread,
        textNote: String? = nil,
        statusChangedAt: Date? = nil,
        isNew: Bool = false,
        isGloballyIgnored: Bool = false,
        isAirportIgnored: Bool = false,
        routeDistanceNm: Double? = nil,
        isAltitudeRelevant: Bool = false,
        isActiveForFlight: Bool = true,
        priority: NotamPriority = .default(maxLevel: PriorityProfiles.default.maxLevel)
    ) {
        self.notam = notam
        self.identityKey = NotamIdentity.key(for: notam)
        self.status = status
        self.textNote = textNote
        self.statusChangedAt = statusChangedAt
        self.isNew = isNew
        self.isGloballyIgnored = isGloballyIgnored
        self.isAirportIgnored = isAirportIgnored
        self.routeDistanceNm = routeDistanceNm
        self.isAltitudeRelevant = isAltitudeRelevant
        self.isActiveForFlight = isActiveForFlight
        self.priority = priority
    }

    // MARK: - Flight Context Display Helpers

    /// Formatted route distance text (e.g., "<1nm", "15nm")
    var routeDistanceText: String? {
        guard let distance = routeDistanceNm else { return nil }
        if distance < 1 {
            return "<1nm"
        } else {
            return String(format: "%.0fnm", distance)
        }
    }

    /// Whether the NOTAM is close enough to route to be highlighted (<50nm)
    var isDistanceRelevant: Bool {
        guard let distance = routeDistanceNm else { return false }
        return distance < 50
    }

    /// Whether the altitude range is constrained (not SFC-UNL or similar full ranges)
    var hasConstrainedAltitude: Bool {
        let lower = notam.lowerLimit ?? 0
        let upper = notam.upperLimit

        // SFC (0 or nil) to UNL (nil) or very high (FL999+) is not constrained
        if lower == 0 && (upper == nil || upper! >= 99900) {
            return false
        }
        return true
    }

    /// Formatted altitude range text (e.g., "SFC-FL100", "1000-5000ft")
    var altitudeRangeText: String? {
        let lower = notam.lowerLimit
        let upper = notam.upperLimit

        guard lower != nil || upper != nil else { return nil }

        let lowerText = formatAltitude(lower, isLower: true)
        let upperText = formatAltitude(upper, isLower: false)

        return "\(lowerText)-\(upperText)"
    }

    private func formatAltitude(_ feet: Int?, isLower: Bool) -> String {
        guard let feet = feet else {
            return isLower ? "SFC" : "UNL"
        }

        if feet == 0 {
            return "SFC"
        } else if feet >= 18000 {
            return "FL\(feet / 100)"
        } else if feet >= 1000 {
            return "\(feet / 1000)k"
        } else {
            return "\(feet)ft"
        }
    }

    // MARK: - Convenience Accessors

    /// NOTAM ID (e.g., "A1234/24")
    var notamId: String { notam.id }

    /// Location ICAO
    var location: String { notam.location }

    /// NOTAM message text
    var message: String { notam.message }

    /// Category from ICAO Q-code
    var category: NotamCategory? { notam.category }

    /// ICAO category derived from Q-code (preferred over category)
    var icaoCategory: NotamCategory? { notam.icaoCategory }

    /// Whether the NOTAM is permanent
    var isPermanent: Bool { notam.isPermanent }

    /// Effective from date
    var effectiveFrom: Date? { notam.effectiveFrom }

    /// Effective to date
    var effectiveTo: Date? { notam.effectiveTo }

    /// Whether active now
    var isActiveNow: Bool { notam.isActiveNow }

    /// Check if active during a time window
    func isActive(during start: Date, to end: Date) -> Bool {
        notam.isActive(during: start, to: end)
    }

    /// Has user note attached
    var hasNote: Bool {
        guard let note = textNote else { return false }
        return !note.isEmpty
    }
}

// MARK: - Array Extensions

extension Array where Element == EnrichedNotam {
    /// Filter by status
    func withStatus(_ status: NotamStatus) -> [EnrichedNotam] {
        filter { $0.status == status }
    }

    /// Filter to only new NOTAMs
    func onlyNew() -> [EnrichedNotam] {
        filter { $0.isNew }
    }

    /// Exclude globally ignored NOTAMs
    func excludingIgnored() -> [EnrichedNotam] {
        filter { !$0.isGloballyIgnored }
    }

    /// Exclude airport-ignored NOTAMs
    func excludingAirportIgnored() -> [EnrichedNotam] {
        filter { !$0.isAirportIgnored }
    }

    /// Group by airport
    func groupedByAirport() -> [String: [EnrichedNotam]] {
        Dictionary(grouping: self) { $0.location }
    }

    /// Group by category
    func groupedByCategory() -> [NotamCategory: [EnrichedNotam]] {
        var result: [NotamCategory: [EnrichedNotam]] = [:]
        for enriched in self {
            let key = enriched.icaoCategory ?? .otherInfo
            result[key, default: []].append(enriched)
        }
        return result
    }

    /// Sort by importance: high priority > new > important > unread > rest
    func sortedByImportance() -> [EnrichedNotam] {
        sorted { lhs, rhs in
            // High priority NOTAMs first
            if lhs.priority != rhs.priority {
                return lhs.priority > rhs.priority
            }
            // New NOTAMs next
            if lhs.isNew != rhs.isNew {
                return lhs.isNew
            }
            // Then by user status priority
            let statusPriority: [NotamStatus: Int] = [
                .important: 0,
                .followUp: 1,
                .unread: 2,
                .read: 3,
                .ignore: 4
            ]
            let lhsPriority = statusPriority[lhs.status] ?? 5
            let rhsPriority = statusPriority[rhs.status] ?? 5
            return lhsPriority < rhsPriority
        }
    }

    /// Filter by computed priority level
    func withPriorityLevel(_ level: Int) -> [EnrichedNotam] {
        filter { $0.priority.level == level }
    }

    /// Filter to critical priority only (P1)
    func criticalOnly() -> [EnrichedNotam] {
        filter { $0.priority.isCritical }
    }

    /// Count of critical priority NOTAMs (P1)
    var criticalPriorityCount: Int {
        filter { $0.priority.isCritical }.count
    }

    /// Count NOTAMs at each priority level
    func countsByLevel(maxLevel: Int) -> [Int: Int] {
        var counts: [Int: Int] = [:]
        for level in 1...maxLevel {
            counts[level] = 0
        }
        for notam in self {
            counts[notam.priority.level, default: 0] += 1
        }
        return counts
    }

    /// Count of new NOTAMs
    var newCount: Int {
        filter { $0.isNew }.count
    }

    /// Count of unread NOTAMs
    var unreadCount: Int {
        filter { $0.status == .unread }.count
    }

    /// Count of important NOTAMs
    var importantCount: Int {
        filter { $0.status == .important }.count
    }
}

// MARK: - Builder from Core Data

extension EnrichedNotam {
    /// Create enriched NOTAMs from a briefing with statuses and flight context.
    ///
    /// This is the primary factory method. It computes all context-dependent values
    /// (distance, altitude relevance, priority) once at creation time.
    ///
    /// - Parameters:
    ///   - notams: Raw NOTAMs from RZFlight
    ///   - statuses: User statuses keyed by NOTAM ID
    ///   - previousIdentityKeys: Identity keys from previous briefings (for "new" detection)
    ///   - ignoredKeys: Globally ignored identity keys
    ///   - flightContext: Flight/route context for relevance computation (optional)
    /// - Returns: Array of enriched NOTAMs with all computed properties
    static func enrich(
        notams: [Notam],
        statuses: [String: CDNotamStatus],
        previousIdentityKeys: Set<String>,
        ignoredKeys: Set<String>,
        ignoredAirports: Set<String> = [],
        flightContext: FlightContext? = nil,
        profile: PriorityProfile = PriorityProfiles.default
    ) -> [EnrichedNotam] {
        let context = flightContext ?? .empty
        let evaluator = NotamPriorityEvaluator(profile: profile)

        return notams.map { notam in
            let identityKey = NotamIdentity.key(for: notam)
            let cdStatus = statuses[notam.id]

            // Compute route distance
            let routeDistance = computeRouteDistance(for: notam, context: context)

            // Compute altitude relevance
            let altitudeRelevant = computeAltitudeRelevance(for: notam, context: context)

            // Compute time/activity relevance
            let activeForFlight = computeActiveForFlight(for: notam, context: context)

            // Evaluate priority using rules
            let priority = evaluator.evaluate(
                notam: notam,
                distanceNm: routeDistance,
                context: context
            )

            return EnrichedNotam(
                notam: notam,
                status: cdStatus?.statusEnum ?? .unread,
                textNote: cdStatus?.textNote,
                statusChangedAt: cdStatus?.updatedAt,
                isNew: !previousIdentityKeys.contains(identityKey),
                isGloballyIgnored: ignoredKeys.contains(identityKey),
                isAirportIgnored: ignoredAirports.contains(notam.location.uppercased()),
                routeDistanceNm: routeDistance,
                isAltitudeRelevant: altitudeRelevant,
                isActiveForFlight: activeForFlight,
                priority: priority
            )
        }
    }

    /// Create enriched NOTAMs with 3-tier status resolution.
    ///
    /// This method implements the 3-tier status system:
    /// 1. Briefing status (CDNotamStatus) - if not unread, use it
    /// 2. Global read (CDGlobalNotamRead) - if exists and doesn't resurface, use read
    /// 3. Unread (default)
    ///
    /// - Parameters:
    ///   - notams: Raw NOTAMs from RZFlight
    ///   - statuses: User statuses keyed by NOTAM ID (briefing-level)
    ///   - globalReads: Global read records keyed by identity key
    ///   - previousIdentityKeys: Identity keys from previous briefings (for "new" detection)
    ///   - ignoredKeys: Globally ignored identity keys
    ///   - flightContext: Flight/route context for relevance computation
    ///   - resurfaceEvaluator: Evaluator for resurface rules
    ///   - resurfaceSettings: Configuration for resurface rules
    /// - Returns: Array of enriched NOTAMs with resolved statuses
    static func enrichWithGlobalReads(
        notams: [Notam],
        statuses: [String: CDNotamStatus],
        globalReads: [String: CDGlobalNotamRead],
        previousIdentityKeys: Set<String>,
        ignoredKeys: Set<String>,
        ignoredAirports: Set<String> = [],
        flightContext: FlightContext,
        resurfaceEvaluator: NotamResurfaceEvaluator,
        resurfaceSettings: ResurfaceSettings,
        profile: PriorityProfile = PriorityProfiles.default
    ) -> [EnrichedNotam] {
        let priorityEvaluator = NotamPriorityEvaluator(profile: profile)

        return notams.map { notam in
            let identityKey = NotamIdentity.key(for: notam)
            let cdStatus = statuses[notam.id]

            // Compute route distance
            let routeDistance = computeRouteDistance(for: notam, context: flightContext)

            // Compute altitude relevance
            let altitudeRelevant = computeAltitudeRelevance(for: notam, context: flightContext)

            // Compute time/activity relevance
            let activeForFlight = computeActiveForFlight(for: notam, context: flightContext)

            // Evaluate priority using rules
            let priority = priorityEvaluator.evaluate(
                notam: notam,
                distanceNm: routeDistance,
                context: flightContext
            )

            // 3-tier status resolution
            let resolvedStatus = resolveEffectiveStatus(
                briefingStatus: cdStatus?.statusEnum,
                identityKey: identityKey,
                notam: notam,
                globalReads: globalReads,
                context: flightContext,
                resurfaceEvaluator: resurfaceEvaluator,
                resurfaceSettings: resurfaceSettings
            )

            return EnrichedNotam(
                notam: notam,
                status: resolvedStatus,
                textNote: cdStatus?.textNote,
                statusChangedAt: cdStatus?.updatedAt,
                isNew: !previousIdentityKeys.contains(identityKey),
                isGloballyIgnored: ignoredKeys.contains(identityKey),
                isAirportIgnored: ignoredAirports.contains(notam.location.uppercased()),
                routeDistanceNm: routeDistance,
                isAltitudeRelevant: altitudeRelevant,
                isActiveForFlight: activeForFlight,
                priority: priority
            )
        }
    }

    /// Resolve the effective status for a NOTAM using 3-tier logic.
    ///
    /// - Parameters:
    ///   - briefingStatus: Status from CDNotamStatus (nil if no status record)
    ///   - identityKey: The NOTAM's identity key
    ///   - notam: The NOTAM being evaluated
    ///   - globalReads: Global read records keyed by identity key
    ///   - context: Current flight context
    ///   - resurfaceEvaluator: Evaluator for resurface rules
    ///   - resurfaceSettings: Configuration for resurface rules
    /// - Returns: The resolved status to display
    private static func resolveEffectiveStatus(
        briefingStatus: NotamStatus?,
        identityKey: String,
        notam: Notam,
        globalReads: [String: CDGlobalNotamRead],
        context: FlightContext,
        resurfaceEvaluator: NotamResurfaceEvaluator,
        resurfaceSettings: ResurfaceSettings
    ) -> NotamStatus {
        // Tier 1: If briefing status is explicitly set (not unread), use it
        // Important, followUp, read, ignore all take precedence
        if let status = briefingStatus, status != .unread {
            return status
        }

        // Tier 2: Check global read status
        guard let globalRead = globalReads[identityKey] else {
            // No global read record - unread
            return .unread
        }

        // Check if the NOTAM should resurface
        if resurfaceEvaluator.shouldResurface(
            globalRead: globalRead,
            notam: notam,
            context: context,
            settings: resurfaceSettings
        ) {
            // Resurface - treat as unread
            return .unread
        }

        // Has global read and doesn't resurface - effectively read
        return .read
    }

    // MARK: - Context Computation Helpers

    /// Compute perpendicular distance from NOTAM to route centerline
    private static func computeRouteDistance(for notam: Notam, context: FlightContext) -> Double? {
        guard context.hasValidRoute,
              let coordinate = notam.coordinate else {
            return nil
        }

        return RouteGeometry.minimumDistanceToRoute(
            from: coordinate,
            routePoints: context.routeCoordinates
        )
    }

    /// Check if NOTAM altitude range overlaps with cruise altitude ±2000ft
    private static func computeAltitudeRelevance(for notam: Notam, context: FlightContext) -> Bool {
        guard let cruiseRange = context.cruiseAltitudeRange else {
            return false
        }

        let notamLower = notam.lowerLimit ?? 0
        let notamUpper = notam.upperLimit ?? 99999

        // Skip surface-to-unlimited (always includes all altitudes, not useful)
        if notamLower == 0 && notamUpper >= 99900 {
            return false
        }

        // Check if ranges overlap
        return cruiseRange.lowerBound <= notamUpper && cruiseRange.upperBound >= notamLower
    }

    /// Check if NOTAM is active during flight window
    private static func computeActiveForFlight(for notam: Notam, context: FlightContext) -> Bool {
        guard let windowStart = context.flightWindowStart,
              let windowEnd = context.flightWindowEnd else {
            // No flight time set - assume potentially active
            return true
        }

        return notam.isActive(during: windowStart, to: windowEnd)
    }
}
