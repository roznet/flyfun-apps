# FlyFunBrief NOTAM System

> NOTAM domain, filtering, enrichment, priority evaluation, and identity matching.

## Intent

Provide comprehensive NOTAM management with user status tracking, intelligent filtering, dynamic priority evaluation, and cross-briefing status transfer. The system wraps RZFlight's Notam model with user-specific state and flight context.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       NotamDomain                            │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │ allNotams   │  │   filters    │  │  annotations      │   │
│  │ [Notam]     │  │  FilterState │  │  [id: Annotation] │   │
│  └─────────────┘  └──────────────┘  └───────────────────┘   │
│                            │                                 │
│                            ▼                                 │
│              ┌─────────────────────────┐                    │
│              │   enrichedNotams        │                    │
│              │   [EnrichedNotam]       │                    │
│              └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

## EnrichedNotam Model

Wraps RZFlight's Notam with user-specific display state and flight context:

```swift
struct EnrichedNotam: Identifiable {
    // Core NOTAM
    let notam: Notam              // RZFlight model

    // User state
    let status: NotamStatus       // read/unread/important/ignored/followUp
    let textNote: String?         // User annotation
    let isNew: Bool               // First time seen in this flight's history
    let isGloballyIgnored: Bool   // Matches global NOTAM ignore list
    let isAirportIgnored: Bool    // Airport is in airport ignore list

    // Flight context (computed at enrichment time)
    let routeDistanceNm: Double?  // Distance from route centerline
    let isAltitudeRelevant: Bool  // Overlaps cruise altitude ±2000ft
    let isActiveForFlight: Bool   // Active during flight window
    let priority: NotamPriority   // Computed priority from rules

    var id: String { notam.id }
    var identityKey: String { NotamIdentity.key(for: notam) }

    // Convenience computed properties
    var routeDistanceText: String?    // Formatted: "<1nm", "15nm"
    var isDistanceRelevant: Bool      // < 50nm from route
    var altitudeRangeText: String?    // Formatted: "SFC-FL100"
}

enum NotamStatus: Int16 {
    case unread = 0
    case read = 1
    case important = 2
    case ignored = 3
    case followUp = 4
}

struct NotamPriority: Comparable, Hashable, Sendable {
    let level: Int       // 1 = most critical
    let maxLevel: Int    // Profile's max (e.g., 5 for IFR, 3 for VFR)

    var isDefault: Bool { level == maxLevel }
    var isCritical: Bool { level == 1 }
    var label: String { "P\(level)" }     // "P1", "P2", etc.
    var iconName: String?                  // triangle for P1, circle for mid, nil for default
    var color: Color                       // red → orange → yellow → secondary
}
```

All flight context values are computed once during enrichment, keeping views simple and avoiding repeated calculations.

## NotamIdentity

Stable identity keys for matching NOTAMs across briefing updates:

```swift
enum NotamIdentity {
    /// Generate stable identity key
    /// Format: "ID|QCode|Location|EffectiveFrom"
    static func key(for notam: Notam) -> String {
        let parts = [
            notam.id,
            notam.qCode ?? "",
            notam.location ?? "",
            notam.effectiveFrom?.ISO8601 ?? ""
        ]
        return parts.joined(separator: "|")
    }

    /// Check if two NOTAMs represent the same real-world notice
    static func areEqual(_ a: Notam, _ b: Notam) -> Bool {
        return key(for: a) == key(for: b)
    }

    /// Transfer statuses from old briefing to new
    static func transferStatuses(
        from oldStatuses: [String: CDNotamStatus],
        to newNotams: [Notam]
    ) -> [String: NotamStatus]

    /// Find NOTAMs not seen in previous briefings
    static func findNewNotams(
        current: [Notam],
        previousKeys: Set<String>
    ) -> Set<String>
}
```

**Why identity keys?** NOTAM IDs can change between briefing sources or updates. The identity key captures the essential characteristics that make a NOTAM unique.

## NotamDomain

Central domain for NOTAM state and filtering (~657 lines).

### State

```swift
@Observable @MainActor
final class NotamDomain {
    // Source data
    var allNotams: [Notam] = []
    var currentCDBriefing: CDBriefing?  // Core Data briefing for persistence
    var currentRoute: Route?

    // User state (persisted via Core Data through FlightRepository)
    var ignoredIdentityKeys: Set<String> = []   // global NOTAM ignore list
    var ignoredAirportCodes: Set<String> = []   // airport-level ignore list
    var previousIdentityKeys: Set<String> = []  // for "new" detection

    // Filter state
    var searchQuery: String = ""
    var grouping: NotamGrouping = .airport

    // Category filter (12 ICAO categories)
    var categoryFilter: CategoryFilter   // showMovement, showLighting, etc.

    // Smart filters
    var smartFilters: SmartFilters       // hideHelicopter, filterObstacles, scopeFilter

    // Other filters
    var statusFilter: StatusFilter = .all
    var priorityFilter: PriorityFilter         // Cumulative priority filter
    var visibilityFilter: VisibilityFilter  // showIgnored, showIgnoredAirports, showRead
    var routeFilter: RouteFilter            // isEnabled, corridorWidthNm
    var timeFilter: TimeFilter              // isEnabled, buffers

    // Flight context for priority evaluation
    var currentFlightContext: FlightContext = .empty

    // Computed
    var enrichedNotams: [EnrichedNotam]
    var filteredEnrichedNotams: [EnrichedNotam]
    var enrichedNotamsGroupedByAirport: [(String, [EnrichedNotam])]
    var enrichedNotamsGroupedByCategory: [(NotamCategory, [EnrichedNotam])]
    var enrichedNotamsGroupedByRouteSegment: [(RouteSegment, [EnrichedNotam])]
    var criticalPriorityCount: Int           // Count of P1 NOTAMs
    var priorityCountsByLevel: [Int: Int]    // Count per priority level

    // Priority profile
    var currentProfile: PriorityProfile      // Active profile (IFR or VFR)
}
```

### Filter Pipeline

```swift
var filteredEnrichedNotams: [EnrichedNotam] {
    enrichedNotams
        // 1a. Global NOTAM ignore filter
        .filter { showIgnored || !$0.isGloballyIgnored }
        // 1b. Airport ignore filter
        .filter { showIgnoredAirports || !$0.isAirportIgnored }
        // 2. Route corridor filter
        .filter { corridorFilter($0.notam) }
        // 3. Time window filter
        .filter { timeWindowFilter($0.notam) }
        // 4. Category filter
        .filter { categoryFilters.contains($0.icaoCategory ?? .otherInfo) }
        // 5. Smart filters (helicopter, obstacle, scope)
        .applySmartFilters()
        // 6. Text search
        .filter { searchQuery.isEmpty || $0.matchesSearch(searchQuery) }
        // 7. Status filter
        .filter { statusFilter.matches($0.status) }
        // 8. Visibility filters
        .filter { showRead || $0.status != .read }
        // 9. Priority filter
        .filter { priorityFilter.matches($0.priority) }
}
```

### Key Methods

```swift
// Set briefing and build enriched NOTAMs
func setBriefing(_ briefing: Briefing,
                  cdBriefing: CDBriefing?,
                  previousKeys: Set<String>,
                  ignoredKeys: Set<String>)

// Status updates
func setStatus(_ status: NotamStatus, for notam: Notam)
func toggleRead(_ notam: Notam)
func toggleImportant(_ notam: Notam)
func addNote(_ note: String, for notam: Notam)

// Bulk operations
func markAllAsRead()
func clearFilters()

// Computed stats
var unreadCount: Int
var importantCount: Int
var newNotamCount: Int
var hasActiveFilters: Bool
```

## Filtering Options

### Grouping

```swift
enum NotamGrouping {
    case none        // Flat list
    case airport     // Group by location ICAO
    case category    // Group by NotamCategory
    case routeOrder  // Group by route segment (Departure → En Route → Dest)
}
```

Route order grouping organizes NOTAMs spatially along the flight route:
- **Departure** - At or near departure airport
- **En Route** - Along route corridor, sorted by distance from departure
- **Destination** - At or near destination airport
- **Alternates** - At alternate airports
- **Distant** - More than 50nm from route centerline
- **No Coordinates** - NOTAMs without geographic data

### Status Filter

```swift
enum StatusFilter {
    case all
    case unread
    case important
    case followUp

    func matches(_ status: NotamStatus) -> Bool
}
```

### ICAO Category Filter

Uses RZFlight's `NotamCategory` enum, which maps 1:1 to ICAO Q-code subject classification.
Categories are determined by the first letter of the Q-code subject (characters 2-3 of Q-code).

**AGA - Aerodrome Ground Aids:**
- `.agaMovement` (M) - Runway, taxiway, apron conditions/closures
- `.agaLighting` (L) - ALS, PAPI, VASIS, runway/taxiway lights
- `.agaFacilities` (F) - Fuel, fire/rescue, de-icing, helicopter facilities

**CNS - Communications, Navigation, Surveillance:**
- `.navigation` (N) - VOR, DME, NDB, TACAN, VORTAC
- `.cnsILS` (I) - ILS, localizer, glide path, markers, MLS
- `.cnsGNSS` (G) - GNSS airfield and area-wide operations
- `.cnsCommunications` (C) - Radar, ADS-B, CPDLC, SELCAL

**ATM - Air Traffic Management:**
- `.atmAirspace` (A) - FIR, TMA, CTR, ATS routes, reporting points
- `.atmProcedures` (P) - SID, STAR, holding, instrument approaches
- `.atmServices` (S) - ATIS, ACC, TWR, approach/ground control
- `.airspaceRestrictions` (R) - Danger/prohibited/restricted areas, TRA

**Other:**
- `.otherInfo` (O) - Obstacles, obstacle lights, AIS, entry requirements

### Smart Filters

Q-code based filters with custom logic beyond simple category matching:

```swift
struct SmartFilters {
    /// Hide helicopter NOTAMs (Q-codes: FH, FP, LU, LW)
    /// Default: ON (hide helicopter)
    var hideHelicopter: Bool = true

    /// Filter obstacles to show only near airports
    /// Obstacle Q-codes: OB, OL
    var filterObstacles: Bool = true
    var obstacleDistanceNm: Double = 2.0  // Show within 2nm of dep/dest

    /// Filter by Q-line scope field
    var scopeFilter: ScopeFilter = .all  // A=Aerodrome, E=En-route, W=Warning
}
```

**Helicopter Filter:** Heliport-related NOTAMs (FATO, windsocks, helipad lighting) are hidden by default for fixed-wing operations.

**Obstacle Filter:** Obstacle NOTAMs (cranes, towers, construction) are typically only relevant near departure/destination airports. When enabled, obstacles beyond the threshold are filtered out, reducing clutter.

### Route Corridor Filter

Spatial filtering based on flight route:

```swift
func corridorFilter(_ notam: Notam) -> Bool {
    guard let route = currentBriefing?.route,
          let notamCoord = notam.coordinate else {
        return true  // No route or no coordinate = include
    }

    // Check distance from route centerline
    let distance = route.distanceFromCenterline(notamCoord)
    return distance <= corridorWidth.nauticalMilesToMeters
}
```

### Time Window Filter

Filter by NOTAM validity during flight window:

```swift
func timeWindowFilter(_ notam: Notam) -> Bool {
    guard let departure = currentFlight?.departureTime else {
        return true
    }

    let windowStart = departure.addingTimeInterval(-preFlightBuffer)
    let windowEnd = departure.addingTimeInterval(estimatedFlightDuration + postFlightBuffer)

    // NOTAM must overlap with flight window
    return notam.overlapsTimeWindow(start: windowStart, end: windowEnd)
}
```

## Ignore Lists

Two independent ignore systems, both persistent across briefings and flights:

### NOTAM Ignore List
Ignores individual NOTAMs by identity key. Auto-expires when NOTAM's `effectiveTo` passes.

```swift
func addToGlobalIgnoreList(_ notam: Notam, reason: String?) async
func removeFromGlobalIgnoreList(_ notam: Notam) async
func isGloballyIgnored(_ notam: Notam) -> Bool
```

### Airport Ignore List
Ignores all NOTAMs from a given airport by ICAO code. No expiration — persists until manually removed. Useful for filtering out large commercial airports (EGLL, LFPG) along routes.

```swift
func addAirportToIgnoreList(_ icaoCode: String, reason: String?) async
func removeAirportFromIgnoreList(_ icaoCode: String) async
func isAirportIgnored(_ icaoCode: String) -> Bool
```

Both are loaded at enrichment time and set flags on `EnrichedNotam`:
- `isGloballyIgnored` — NOTAM identity key in NOTAM ignore list
- `isAirportIgnored` — NOTAM location in airport ignore list

Each has an independent visibility toggle in `VisibilityFilter`.

## Priority System

Profile-driven priority evaluation based on flight context. Priority is **independent** of user status and filtering - it's a computed property that helps users identify important NOTAMs.

### FlightContext

Captures all flight-related information for priority evaluation:

```swift
struct FlightContext {
    let routeCoordinates: [CLLocationCoordinate2D]  // Route geometry
    let departureICAO: String?
    let destinationICAO: String?
    let alternateICAOs: [String]
    let cruiseAltitude: Int?        // Feet
    let departureTime: Date?
    let arrivalTime: Date?

    var hasValidRoute: Bool         // >= 2 coordinates
    var flightWindowStart: Date?    // Departure - 2h
    var flightWindowEnd: Date?      // Arrival + 2h
    var cruiseAltitudeRange: ClosedRange<Int>?  // ±2000ft
}
```

The context is set by AppState when a flight is selected and passed to `NotamDomain.setFlightContext()`.

### Priority Profiles

Priority evaluation is driven by selectable profiles loaded from JSON config files (`configs/priority_profiles/*.json`). Each profile defines its own number of levels and evaluation rules. The active profile is persisted in UserDefaults via `SettingsDomain`.

```swift
struct PriorityProfile: Identifiable, Equatable {
    let id: String              // "ifr", "vfr"
    let displayName: String     // "IFR", "VFR"
    let maxLevel: Int           // 5 for IFR, 3 for VFR
    let rules: [any ProfilePriorityRule]
    let levelDescriptions: [Int: String]
    var levels: ClosedRange<Int> { 1...maxLevel }

    static func fromJSON(_ data: Data) throws -> PriorityProfile
    static func bundled(name: String) -> PriorityProfile
}

protocol ProfilePriorityRule {
    var id: String { get }
    var name: String { get }
    func evaluate(notam: Notam, distanceNm: Double?, context: FlightContext) -> Int?
}
```

Rules are evaluated in order; first non-nil result wins. Unmatched NOTAMs get the profile's `maxLevel` (lowest priority).

### JSON Rule Format

All rules use a single `QCodeMatchRule` struct decoded from JSON. Each rule is a conjunction of optional filters — all present filters must match:

```json
{
    "id": "ifr_p2_airspace_restrictions",
    "name": "Airspace restrictions within corridor",
    "type": "q_code_match",
    "level": 2,
    "subjects": ["RA", "RR", "RT"],
    "max_distance_nm": 50,
    "altitude_check": "if_available"
}
```

**Available filters:**
- `subjects` — Q-code subject must be in set (e.g., `["MR", "MT", "MX"]`)
- `condition_filter` — `"unavailable"` (closed/canceled) or `"limitation"` (L-prefix conditions)
- `location` — `"dep_dest"` or `"not_dep_dest"`
- `max_distance_nm` — maximum distance from route
- `altitude_check` — `"if_available"` (permissive when no altitude set) or `"required"` (must overlap)
- `no_altitude_fallback_distance_nm` — fallback distance when altitude check is required but no cruise altitude

The JSON configs in `configs/priority_profiles/` are the **single source of truth** shared with the Python evaluator (`tools/priority_evaluator.py`). Copies are bundled in `app/FlyFunBrief/Resources/PriorityProfiles/`.

### IFR Profile (5 levels, 13 rules)

| Level | Description | Rules |
|-------|-------------|-------|
| P1 | Critical | Runway/taxiway at dep/dest, ILS/procedure unavailable at dep/dest |
| P2 | Important | ILS/procedure changed at dep/dest, airspace restrictions in corridor, rwy/twy closed near route |
| P3 | Relevant | ATS/RNAV route changes, movement area limits near route, close NOTAMs at altitude, navaids, procedure unavailable near route |
| P4 | Nearby | Facilities/services at dep/dest, other dep/dest NOTAMs, conditions near route |
| P5 | Default | Unmatched NOTAMs |

### VFR Profile (3 levels, 11 rules)

| Level | Description | Rules |
|-------|-------------|-------|
| P1 | Critical | Runway/taxiway at dep/dest, VFR procedure unavailable at dep/dest, airspace restrictions along route |
| P2 | Relevant | ATS route changes, VFR procedure changed at dep/dest, rwy/twy limits near route, lighting at dep/dest, navigation near route, procedure unavailable near route, other dep/dest NOTAMs, conditions near route |
| P3 | Default | Unmatched NOTAMs |

### Priority Filter

Cumulative filter: selecting level N shows P1 through PN.

```swift
struct PriorityFilter: Equatable {
    var maxVisibleLevel: Int?      // nil = show all
    var profileMaxLevel: Int
    var isActive: Bool { maxVisibleLevel != nil }

    func matches(_ priority: NotamPriority) -> Bool {
        guard let max = maxVisibleLevel else { return true }
        return priority.level <= max
    }

    var chipLabel: String?         // e.g., "P1-P2" for compact filter bar
}

// Usage
notamDomain.priorityFilter.maxVisibleLevel = 2  // Show P1 + P2 only
```

### Profile Selection Flow

```
SettingsDomain.priorityProfileId (UserDefaults)
    ↓
AppState.syncPriorityProfile()
    ↓
NotamDomain.setProfile(profile)
    ↓
Re-enriches all NOTAMs with new profile's rules
    ↓
PriorityFilter.profileMaxLevel updated
```

### UI Display

- **P1 (critical)**: Red warning triangle icon
- **P2-P(N-1)**: Colored circle, interpolated from orange → yellow → secondary
- **Default (maxLevel)**: No icon, secondary color

Icons appear in the NOTAM row as `priority.label` ("P1") with `priority.color`.

### Enrichment Flow

```
AppState builds FlightContext from CDFlight + KnownAirports
    ↓
NotamDomain.setFlightContext(context) + setProfile(profile)
    ↓
EnrichedNotam.enrich(profile:) called with active profile
    ↓
For each NOTAM:
  1. Compute route distance using RouteGeometry
  2. Check altitude relevance against cruise ±2000ft
  3. Check if active during flight window
  4. Evaluate profile's priority rules chain (first match wins)
    ↓
EnrichedNotam created with NotamPriority(level:maxLevel:)
```

## Usage Examples

### Build enriched NOTAMs from Core Data briefing

```swift
func setBriefing(_ briefing: Briefing, cdBriefing: CDBriefing, previousKeys: Set<String>) {
    allNotams = briefing.notams
    currentRoute = briefing.route
    currentCDBriefing = cdBriefing
    previousIdentityKeys = previousKeys

    // Build enriched NOTAMs using Core Data statuses
    let statuses = cdBriefing.statusesByNotamId
    enrichedNotams = EnrichedNotam.enrich(
        notams: allNotams,
        statuses: statuses,
        previousIdentityKeys: previousKeys,
        ignoredKeys: ignoredIdentityKeys,
        ignoredAirports: ignoredAirportCodes,
        profile: currentProfile
    )
}
```

### Update NOTAM status

```swift
func setStatus(_ status: NotamStatus, for notam: Notam) {
    guard let cdBriefing = currentCDBriefing else {
        Logger.app.warning("Cannot set status without Core Data briefing")
        return
    }

    do {
        try flightRepository.updateNotamStatus(notam, briefing: cdBriefing, status: status)
        refreshEnrichedNotams()
    } catch {
        Logger.app.error("Failed to update NOTAM status: \(error.localizedDescription)")
    }
}
```

### Filter by multiple criteria

```swift
// Show only unread runway NOTAMs within corridor
notamDomain.statusFilter = .unread
notamDomain.categoryFilters = [.runway]
notamDomain.corridorWidth = 15.0  // Narrow corridor
notamDomain.showRead = false

// Access filtered results
let notams = notamDomain.filteredEnrichedNotams
```

## UI Components

### NotamRowView
Displays single NOTAM in list with:
- Status indicator (unread dot, important star)
- Priority label and icon (P1=red triangle, P2+=colored circle, default=none)
- Distance from route (highlighted if < 50nm)
- Altitude range (highlighted if overlaps cruise ±2000ft)
- "Inactive" badge if NOTAM inactive during flight window
- Swipe actions for status changes

All display values are pre-computed in EnrichedNotam - the view only renders.

### NotamDetailView
Full NOTAM detail sheet:
- Complete message text
- Q-code breakdown
- Map view (if coordinates available)
- Status buttons (read/important/ignore)
- Note editor
- Global ignore option

### FilterPanelView
Comprehensive filter configuration:
- **Smart Filters** - Helicopter toggle, obstacle distance, scope picker
- **ICAO Categories** - 12 categories in collapsible groups (AGA, CNS, ATM)
- **Route Filter** - Corridor width, ICAO codes
- **Time Filter** - Active at flight time
- **Status Filter** - All/unread/important/followUp
- **Priority Filter** - Profile picker (segmented IFR/VFR) + cumulative level buttons (All/P1/P2/../PN) with per-level count badges + level descriptions
- **Visibility** - Show read, show ignored NOTAMs, show ignored airports
- **Grouping** - None/airport/category/route order

### SettingsView
Priority Profile section with:
- Profile picker (IFR/VFR)
- Level descriptions for the selected profile

## Gotchas

1. **Always use identity keys** - Not NOTAM IDs for matching
2. **Enrichment is expensive** - Cache and only rebuild when needed
3. **Three ignore mechanisms** - Global NOTAM ignore (by identity key), airport ignore (by ICAO code), and per-NOTAM ignore status are all independent
4. **"New" is flight-scoped** - Compared to all previous briefings for this flight
5. **Filter order matters** - Route corridor first (expensive) then cheap filters
6. **Use icaoCategory, not category** - The `icaoCategory` computed property derives from Q-code, with fallback to stored category
7. **Smart filters need route** - Obstacle filtering requires departure/destination coordinates
8. **Helicopter filter is default ON** - Unlike other filters, helicopter NOTAMs are hidden by default
9. **Priority vs Status** - Priority is computed from flight context and profile rules; Status is user-assigned. Both are independent.
10. **FlightContext must be set** - Call `setFlightContext()` when flight changes, otherwise priority defaults to profile's maxLevel
11. **Profile change re-enriches** - Switching profiles triggers full re-enrichment since priority levels differ between profiles
12. **Cumulative filtering** - Priority filter is cumulative: selecting P2 shows P1+P2, not just P2
13. **Single-level edge case** - A profile with maxLevel=1 has P1 that is both `isCritical` and `isDefault`; `isCritical` takes precedence for color/icon
14. **Priority never persisted** - Priority is computed at enrichment time from the active profile, never stored in Core Data
15. **JSON configs are source of truth** - Priority rules live in `configs/priority_profiles/*.json`, shared with Python evaluator. Bundled copies in `app/FlyFunBrief/Resources/PriorityProfiles/` must be kept in sync
16. **Airport ignore uses ICAO code** - Matched against `notam.location.uppercased()`, not identity key. No expiration unlike NOTAM ignores
17. **Airport ignore has own visibility toggle** - `showIgnoredAirports` is separate from `showIgnored` (NOTAM-level); both default to false

## References

- Key code: `app/FlyFunBrief/App/State/Domains/NotamDomain.swift`
- Priority: `app/FlyFunBrief/App/Models/NotamPriority.swift`
- Profiles: `app/FlyFunBrief/App/Models/PriorityProfile.swift`
- Rule engine: `app/FlyFunBrief/App/Models/PriorityRules/QCodeMatchRule.swift`
- JSON configs: `configs/priority_profiles/ifr.json`, `configs/priority_profiles/vfr.json`
- Bundled copies: `app/FlyFunBrief/Resources/PriorityProfiles/`
- Python evaluator: `tools/priority_evaluator.py`
- Flight context: `app/FlyFunBrief/App/Models/FlightContext.swift`
- Enriched model: `app/FlyFunBrief/App/Models/EnrichedNotam.swift`
- Settings: `app/FlyFunBrief/App/State/Domains/SettingsDomain.swift`
- Row view: `app/FlyFunBrief/UserInterface/Views/NotamList/NotamRowView.swift`
- Filter UI: `app/FlyFunBrief/UserInterface/Views/Filters/SharedFilterContent.swift`
- Ignore list UI: `app/FlyFunBrief/UserInterface/Views/IgnoreList/IgnoreListView.swift`
- Airport ignore manager: `app/FlyFunBrief/App/Data/Repositories/AirportIgnoreListManager.swift`
- Related: [BRIEFING_APP_DATA.md](BRIEFING_APP_DATA.md) for persistence
