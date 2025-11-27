# FlyFun EuroAIP iOS/macOS App Design

## Executive Summary

This document describes the architecture and design for the FlyFun EuroAIP native app targeting iOS, iPadOS, and macOS. The app will replicate most web functionality with a key differentiator: **offline/online hybrid operation**.

**Core Principles:**
- **Offline-first**: Full functionality with bundled database when offline
- **Online-enhanced**: Live data, full chatbot, and sync when online
- **Shared logic**: Abstract common code between offline/online modes
- **Adaptive UI**: Responsive layouts for iPhone, iPad, and Mac
- **RZFlight-first**: Maximize reuse of existing RZFlight models and functionality

---

## ⚠️ Critical Design Rule: RZFlight Model Reuse

### Philosophy

The app MUST maximize reuse of models and functionality from the [RZFlight Swift package](https://github.com/roznet/rzflight). RZFlight is the Swift equivalent of `euro_aip` in Python - they share the same database schema and conceptual model.

### Rules

1. **Use RZFlight models directly** - Do NOT create duplicate Airport, Runway, Procedure, or AIPEntry models in the app. Use `RZFlight.Airport`, `RZFlight.Runway`, etc.

2. **Use KnownAirports as the primary data interface** - All airport queries should go through `KnownAirports`, not raw SQL.

3. **Extend RZFlight, not the app** - If functionality exists in `euro_aip` (Python) but not in RZFlight (Swift), propose an enhancement to RZFlight rather than implementing it in the app.

4. **App-specific types only when necessary** - Only create app-level types for:
   - UI-specific state (e.g., `MapHighlight`, `VisualizationPayload`)
   - API response models (for online mode)
   - App configuration (e.g., `FilterConfig` for UI binding)

### Available RZFlight Models

| Model | Description | Key Features |
|-------|-------------|--------------|
| `Airport` | Complete airport data | name, icao, coord, country, type, runways[], procedures[], aipEntries[], elevation_ft, iataCode, etc. |
| `Runway` | Runway with both ends | length_ft, width_ft, surface, lighted, closed, le/he RunwayEnds, isHardSurface |
| `Procedure` | IFR procedures | procedureType (approach/departure/arrival), approachType (ILS/RNAV/etc.), precisionCategory |
| `AIPEntry` | AIP field data | section, field, value, standardField, isStandardized |
| `KnownAirports` | Main query interface | KDTree-based spatial queries, filtering, route search |

### Available KnownAirports Methods

```swift
// Basic queries
func airport(icao:ensureRunway:ensureProcedures:ensureAIP:) -> Airport?
func airportWithExtendedData(icao:) -> Airport?

// Spatial queries
func nearestAirport(coord:) -> Airport?
func nearest(coord:count:) -> [Airport]
func nearestMatching(coord:needle:count:) -> [Airport]
func matching(needle:) -> [Airport]

// Feature queries
func airportsWithBorderCrossing() -> [Airport]
func airportsWithBorderCrossing(near:within:limit:) -> [Airport]
func airportsWithApproach(_:near:within:limit:) -> [Airport]
func airportsWithPrecisionApproaches(near:within:limit:) -> [Airport]
func airportsWithAIPField(_:useStandardized:) -> [Airport]
func airportsNearRoute(_:within:) -> [Airport]
```

### Available Array<Airport> Extensions

```swift
func borderCrossingOnly(db:) -> [Airport]
func withRunwayLength(minimumFeet:) -> [Airport]
func withRunwayLength(minimumFeet:maximumFeet:) -> [Airport]
func withProcedures() -> [Airport]
func withApproaches() -> [Airport]
func withPrecisionApproaches() -> [Airport]
func withHardRunways() -> [Airport]
func withLightedRunways() -> [Airport]
func inCountry(_:) -> [Airport]
func matching(_:) -> [Airport]
```

### Gap Analysis: RZFlight vs euro_aip

Features that may need to be added to RZFlight (enhance library, not app):

| Feature | euro_aip (Python) | RZFlight (Swift) | Action |
|---------|------------------|------------------|--------|
| Fuel filtering (AVGAS/Jet-A) | ✅ | ❌ | Add to RZFlight |
| Landing fee filtering | ✅ | ❌ | Add to RZFlight |
| AIP field value filtering | ✅ | ⚠️ Partial | Enhance in RZFlight |
| Country list query | ✅ | ❌ | Add to RZFlight |
| Filter config application | ✅ | ❌ | Add to RZFlight |

---

## 1. Architecture Overview

### 1.1 Platform Requirements

| Platform | Minimum Version | Notes |
|----------|-----------------|-------|
| **iOS** | 18.0+ | Latest SwiftUI, Observation framework |
| **iPadOS** | 18.0+ | Full NavigationSplitView support |
| **macOS** | 15.0+ | Native Catalyst-free experience |
| **watchOS** | N/A | Not targeted |
| **visionOS** | Consider future | Spatial computing ready |

**Why Latest Only:**
- Use `@Observable` macro (no legacy `ObservableObject`)
- Native `@Environment` injection
- SwiftData for caching
- Apple Intelligence integration for offline chatbot
- Modern MapKit with `MapContentBuilder`
- No backward compatibility complexity

### 1.2 High-Level Architecture

**Single Source of Truth: `AppState`**

```
┌──────────────────────────────────────────────────────────────────┐
│                         SwiftUI Views                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ MapView  │ │SearchView│ │FilterView│ │ ChatView │            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       └────────────┴────────────┴────────────┘                    │
│                            │                                      │
│                   @Environment(\.appState)                        │
│                            ▼                                      │
├──────────────────────────────────────────────────────────────────┤
│                   AppState (@Observable)                          │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                 SINGLE SOURCE OF TRUTH                       ││
│  │                                                              ││
│  │  // Airport Data                                             ││
│  │  var airports: [Airport]                                     ││
│  │  var selectedAirport: Airport?                               ││
│  │  var airports: [Airport] // already filtered by repo         ││
│  │                                                              ││
│  │  // Filters                                                  ││
│  │  var filters: FilterConfig                                   ││
│  │                                                              ││
│  │  // Map State                                                ││
│  │  var mapRegion: MKCoordinateRegion                           ││
│  │  var legendMode: LegendMode                                  ││
│  │  var highlights: [String: MapHighlight]                      ││
│  │  var activeRoute: RouteVisualization?                        ││
│  │                                                              ││
│  │  // Chat State                                               ││
│  │  var chatMessages: [ChatMessage]                             ││
│  │  var isStreaming: Bool                                       ││
│  │                                                              ││
│  │  // UI State                                                 ││
│  │  var isLoading: Bool                                         ││
│  │  var connectivityMode: ConnectivityMode                      ││
│  │  var navigationPath: NavigationPath                          ││
│  └──────────────────────────────────────────────────────────────┘│
│                            │                                      │
├────────────────────────────┴─────────────────────────────────────┤
│                        Repository Layer                           │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                    AirportRepository                         ││
│  │  - Unified API for data access                               ││
│  │  - Abstracts offline/online sources                          ││
│  │  - Returns RZFlight.Airport directly                         ││
│  └────────────┬─────────────────────────────┬───────────────────┘│
│               │                             │                     │
│  ┌────────────┴───────────┐    ┌───────────┴──────────────────┐ │
│  │   LocalDataSource      │    │     RemoteDataSource         │ │
│  │   (KnownAirports)      │    │   (API → RZFlight Adapter)   │ │
│  └────────────────────────┘    └──────────────────────────────┘ │
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│                       Chatbot Layer                               │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                  ChatbotService                              ││
│  │  ┌────────────────────┐  ┌─────────────────────────────────┐││
│  │  │OfflineChatbot      │  │OnlineChatbot                    │││
│  │  │(Apple Intelligence)│  │(API streaming)                  │││
│  │  └────────────────────┘  └─────────────────────────────────┘││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│                     Core Services                                 │
│  ┌────────────┐ ┌─────────────┐ ┌──────────────┐ ┌────────────┐ │
│  │Connectivity│ │ SyncService │ │  SwiftData   │ │Preferences │ │
│  │  Monitor   │ │             │ │   Cache      │ │            │ │
│  └────────────┘ └─────────────┘ └──────────────┘ └────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 1.3 Design Patterns

| Pattern | Purpose | Implementation |
|---------|---------|----------------|
| **Single Store** | One source of truth for all app state | `AppState` with `@Observable` |
| **Repository** | Abstract data sources (offline/online) | `AirportRepository` protocol |
| **Strategy** | Swap chatbot implementations | `ChatbotService` protocol |
| **Environment DI** | Inject dependencies into views | `@Environment(\.appState)` |
| **Coordinator** | View-specific logic without state | Thin coordinators if needed |

### 1.4 Connectivity Modes

```swift
enum ConnectivityMode: Equatable, Sendable {
    case offline        // No network, local DB only
    case online         // Network available, prefer API
    case hybrid         // Online with local cache fallback
}
```

**Mode Behavior:**

| Feature | Offline | Online |
|---------|---------|--------|
| Airport search | Local DB | API (latest data) |
| Airport details | Local DB | API |
| Filters | Local DB | API |
| Procedures | Local DB | API |
| AIP entries | Local DB (cached) | API |
| Chatbot | Apple Intelligence | Full API streaming |
| Map data | Cached tiles | Live tiles |
| Sync | N/A | Background sync |

### 1.5 Modern Swift Features Used

| Feature | Usage |
|---------|-------|
| `@Observable` | AppState - granular UI updates |
| `@Environment` | Dependency injection |
| `NavigationStack` | Programmatic navigation |
| `SwiftData` | Caching API responses |
| `async/await` | All async operations |
| `AsyncStream` | SSE streaming |
| Apple Intelligence | Offline chatbot |
| MapKit SwiftUI | Native map with `Map { }` builder |

---

## 2. Data Layer Design

### 2.1 Repository Pattern

**Important:** The repository returns `RZFlight.Airport` directly, not app-specific types.

```swift
import RZFlight

/// Protocol for airport data access - abstracts offline/online sources
/// All methods return RZFlight types directly
/// 
/// IMPORTANT: Filtering is done HERE, not in FilterConfig.
/// This keeps FilterConfig pure (no DB dependencies).
protocol AirportRepositoryProtocol {
    // MARK: - Airport Queries (returns RZFlight.Airport)
    
    /// Get airports matching filters - repository handles DB-dependent filters
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [Airport]
    
    /// Search airports by query string
    func searchAirports(query: String, limit: Int) async throws -> [Airport]
    
    /// Get airport with extended data (runways, procedures, AIP entries)
    func airportDetail(icao: String) async throws -> Airport?
    
    // MARK: - Route & Location (returns RZFlight.Airport)
    func airportsNearRoute(from: String, to: String, distanceNm: Int, filters: FilterConfig) async throws -> RouteResult
    func airportsNearLocation(center: CLLocationCoordinate2D, radiusNm: Int, filters: FilterConfig) async throws -> [Airport]
    
    // MARK: - In-Memory Filtering (for already-loaded airports)
    /// Apply cheap in-memory filters only (no DB access)
    /// Used for client-side filtering of already-fetched results
    func applyInMemoryFilters(_ filters: FilterConfig, to airports: [Airport]) -> [Airport]
    
    // MARK: - Extended Data
    func countryRules(for countryCode: String) async throws -> CountryRules?
    
    // MARK: - Metadata
    func availableCountries() async throws -> [String]
    func filterMetadata() async throws -> FilterMetadata
}

/// Route result wrapper
struct RouteResult {
    let airports: [Airport]  // RZFlight.Airport
    let departure: String
    let destination: String
}
```

### 2.2 Local Data Source

Leverages existing `RZFlight` library with `KnownAirports`. **Use RZFlight types directly.**

```swift
import RZFlight

/// Local data source using bundled SQLite database
/// Returns RZFlight.Airport directly - no conversion needed
/// 
/// IMPORTANT: All filtering logic lives HERE, not in FilterConfig.
/// FilterConfig is pure data; this class knows how to apply it.
final class LocalAirportDataSource: AirportRepositoryProtocol {
    private let db: FMDatabase
    private let knownAirports: KnownAirports
    
    init(databasePath: String) throws {
        self.db = FMDatabase(path: databasePath)
        guard db.open() else { throw DataSourceError.databaseOpenFailed }
        self.knownAirports = KnownAirports(db: db)
    }
    
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [Airport] {
        var airports: [Airport]
        
        // Use KnownAirports methods for DB-dependent filters
        if filters.pointOfEntry == true {
            airports = knownAirports.airportsWithBorderCrossing()
        } else if let aipField = filters.aipField {
            airports = knownAirports.airportsWithAIPField(aipField, useStandardized: true)
        } else {
            airports = Array(knownAirports.known.values)
        }
        
        // Apply cheap in-memory filters (no DB access)
        airports = applyInMemoryFilters(filters, to: airports)
        
        return Array(airports.prefix(limit))
    }
    
    func searchAirports(query: String, limit: Int) async throws -> [Airport] {
        return Array(knownAirports.matching(needle: query).prefix(limit))
    }
    
    func airportsNearRoute(from: String, to: String, distanceNm: Int, filters: FilterConfig) async throws -> RouteResult {
        let routeAirports = knownAirports.airportsNearRoute([from, to], within: Double(distanceNm))
        let filtered = applyInMemoryFilters(filters, to: routeAirports)
        return RouteResult(airports: filtered, departure: from, destination: to)
    }
    
    func airportDetail(icao: String) async throws -> Airport? {
        return knownAirports.airportWithExtendedData(icao: icao)
    }
    
    // MARK: - In-Memory Filtering (No DB Access)
    
    /// Apply only the filters that don't require DB access
    /// Uses RZFlight Array<Airport> extensions
    func applyInMemoryFilters(_ filters: FilterConfig, to airports: [Airport]) -> [Airport] {
        var result = airports
        
        // These use RZFlight extensions - NO DB parameter
        if let country = filters.country {
            result = result.inCountry(country)
        }
        if filters.hasHardRunway == true {
            result = result.withHardRunways()
        }
        if filters.hasProcedures == true {
            result = result.withProcedures()
        }
        if let minLength = filters.minRunwayLengthFt {
            result = result.withRunwayLength(minimumFeet: minLength)
        }
        if let maxLength = filters.maxRunwayLengthFt {
            result = result.withRunwayLength(minimumFeet: 0, maximumFeet: maxLength)
        }
        // Note: pointOfEntry, hasAvgas, hasJetA, aipField require DB
        // Those are handled in airports(matching:) above
        
        return result
    }
    
    // ... other methods
}
```

### 2.3 Remote Data Source (With API → RZFlight Adapters)

The remote data source fetches from the API and **converts responses to RZFlight models**.

```swift
import RZFlight

/// Remote data source using web API
/// Converts all API responses to RZFlight models for consistency
final class RemoteAirportDataSource: AirportRepositoryProtocol {
    private let apiClient: APIClient
    private let baseURL: URL
    
    init(baseURL: URL = URL(string: "https://maps.flyfun.aero/api")!) {
        self.baseURL = baseURL
        self.apiClient = APIClient()
    }
    
    func getAirports(filters: FilterConfig, limit: Int) async throws -> [Airport] {
        let endpoint = AirportEndpoint.list(filters: filters, limit: limit)
        let response: APIAirportListResponse = try await apiClient.request(endpoint)
        
        // Convert API response to RZFlight.Airport
        return response.airports.map { APIAirportAdapter.toRZFlight($0) }
    }
    
    func getAirportDetail(icao: String) async throws -> Airport? {
        let endpoint = AirportEndpoint.detail(icao: icao)
        let response: APIAirportDetailResponse = try await apiClient.request(endpoint)
        
        // Convert with extended data (runways, procedures, AIP entries)
        return APIAirportAdapter.toRZFlightWithExtendedData(response)
    }
    
    // ... other methods follow same pattern
}
```

### 2.4 API Response Models (Internal Only)

These models match the API JSON structure. They are **internal** and converted to RZFlight immediately.

```swift
/// Internal: API response structure (DO NOT expose outside adapter)
struct APIAirportListResponse: Decodable {
    let airports: [APIAirport]
    let total: Int
    let page: Int
}

/// Internal: API airport structure
struct APIAirport: Decodable {
    let ident: String
    let name: String?
    let municipality: String?
    let iso_country: String?
    let latitude_deg: Double?
    let longitude_deg: Double?
    let elevation_ft: Int?
    let type: String?
    let continent: String?
    let iata_code: String?
    let longest_runway_length_ft: Int?
    let point_of_entry: Bool?
    let has_procedures: Bool?
    let has_aip_data: Bool?
    let procedure_count: Int?
    let runway_count: Int?
}

/// Internal: API runway structure
struct APIRunway: Decodable {
    let length_ft: Int
    let width_ft: Int?
    let surface: String?
    let lighted: Bool?
    let closed: Bool?
    let le_ident: String?
    let he_ident: String?
    let le_heading_degT: Double?
    let he_heading_degT: Double?
    // ... other fields
}

/// Internal: API procedure structure  
struct APIProcedure: Decodable {
    let name: String
    let procedure_type: String
    let approach_type: String?
    let runway_ident: String?
    // ... other fields
}
```

### 2.5 API → RZFlight Adapters

Adapters convert API responses to RZFlight models. This ensures **one model type throughout the app**.

```swift
import RZFlight

/// Converts API responses to RZFlight models
enum APIAirportAdapter {
    
    /// Convert API airport to RZFlight.Airport
    static func toRZFlight(_ api: APIAirport) -> Airport {
        // Create Airport using the coordinate-based initializer
        var airport = Airport(
            location: CLLocationCoordinate2D(
                latitude: api.latitude_deg ?? 0,
                longitude: api.longitude_deg ?? 0
            ),
            icao: api.ident
        )
        
        // Note: RZFlight.Airport is a struct with let properties
        // For API responses, we may need to use a different initializer
        // or propose an API-friendly initializer to RZFlight
        
        return airport
    }
    
    /// Convert API airport with extended data
    static func toRZFlightWithExtendedData(_ response: APIAirportDetailResponse) -> Airport {
        var airport = toRZFlight(response.airport)
        
        // Convert and attach runways
        airport.runways = response.runways.map { toRZFlight($0) }
        
        // Convert and attach procedures
        airport.procedures = response.procedures.map { toRZFlight($0) }
        
        // Convert and attach AIP entries
        airport.aipEntries = response.aip_entries.map { toRZFlight($0) }
        
        return airport
    }
    
    /// Convert API runway to RZFlight.Runway
    static func toRZFlight(_ api: APIRunway) -> Runway {
        // Build Runway matching RZFlight structure
        // May need to propose Runway initializer to RZFlight
    }
    
    /// Convert API procedure to RZFlight.Procedure
    static func toRZFlight(_ api: APIProcedure) -> Procedure {
        let procedureType = Procedure.ProcedureType(rawValue: api.procedure_type) ?? .approach
        let approachType = api.approach_type.flatMap { Procedure.ApproachType(rawValue: $0) }
        
        return Procedure(
            name: api.name,
            procedureType: procedureType,
            approachType: approachType,
            runwayIdent: api.runway_ident
        )
    }
    
    /// Convert API AIP entry to RZFlight.AIPEntry
    static func toRZFlight(_ api: APIAIPEntry) -> AIPEntry {
        let section = AIPEntry.Section(rawValue: api.section) ?? .operational
        
        return AIPEntry(
            ident: api.airport_icao,
            section: section,
            field: api.field,
            value: api.value,
            altValue: api.alt_value
        )
    }
}
```

### 2.6 RZFlight Initializer Enhancements (Proposed)

The current RZFlight models are primarily designed for database loading. For API usage, we may need to propose these enhancements:

```swift
// Proposed addition to RZFlight.Airport
extension Airport {
    /// Initialize from API-style data (proposed for RZFlight)
    public init(
        icao: String,
        name: String,
        city: String,
        country: String,
        latitude: Double,
        longitude: Double,
        elevation_ft: Int = 0,
        type: AirportType = .none,
        continent: Continent = .none,
        iataCode: String? = nil,
        runways: [Runway] = [],
        procedures: [Procedure] = [],
        aipEntries: [AIPEntry] = []
    ) {
        // Full memberwise initializer
    }
}

// Proposed addition to RZFlight.Runway
extension Runway {
    /// Initialize from API-style data (proposed for RZFlight)
    public init(
        length_ft: Int,
        width_ft: Int,
        surface: String,
        lighted: Bool,
        closed: Bool,
        le: RunwayEnd,
        he: RunwayEnd
    ) {
        // Memberwise initializer
    }
}
```
```

### 2.4 Unified Repository

```swift
/// Main repository that switches between offline/online sources
final class AirportRepository: AirportRepositoryProtocol, ObservableObject {
    @Published private(set) var connectivityMode: ConnectivityMode = .offline
    
    private let localDataSource: LocalAirportDataSource
    private let remoteDataSource: RemoteAirportDataSource
    private let connectivityMonitor: ConnectivityMonitor
    
    private var activeSource: AirportRepositoryProtocol {
        switch connectivityMode {
        case .offline: return localDataSource
        case .online, .hybrid: return remoteDataSource
        }
    }
    
    func getAirports(filters: FilterConfig, limit: Int) async throws -> [Airport] {
        do {
            return try await activeSource.getAirports(filters: filters, limit: limit)
        } catch {
            // Fallback to local on network error (hybrid mode)
            if connectivityMode == .hybrid {
                return try await localDataSource.getAirports(filters: filters, limit: limit)
            }
            throw error
        }
    }
}
```

---

## 3. Models

### 3.1 RZFlight Models (USE THESE - DO NOT DUPLICATE)

The app uses models directly from [RZFlight](https://github.com/roznet/rzflight). **Do NOT create duplicate model types.**

```swift
import RZFlight

// ✅ CORRECT: Use RZFlight types directly
let airport: RZFlight.Airport
let runways: [RZFlight.Runway]
let procedures: [RZFlight.Procedure]
let entries: [RZFlight.AIPEntry]

// ❌ WRONG: Don't create app-level duplicates
// struct AppAirport { ... }  // NO!
```

**RZFlight.Airport** already provides:
- `icao`, `name`, `city`, `country`, `coord`
- `runways: [Runway]`, `procedures: [Procedure]`, `aipEntries: [AIPEntry]`
- `elevation_ft`, `type`, `continent`, `iataCode`
- `approaches`, `departures`, `arrivals` (computed)
- `isBorderCrossing(db:)`, `hasCustoms(db:)`
- Conforms to `Identifiable`, `Hashable`, `Codable`

**RZFlight.Runway** already provides:
- `length_ft`, `width_ft`, `surface`, `lighted`, `closed`
- `le`, `he` (RunwayEnd with coordinates, headings)
- `isHardSurface` (computed)
- `ident1`, `ident2` (runway identifiers)

**RZFlight.Procedure** already provides:
- `name`, `procedureType` (approach/departure/arrival)
- `approachType` (ILS/RNAV/VOR/NDB/etc.)
- `precisionCategory` (precision/rnav/non-precision)
- `fullRunwayIdent`, `isApproach`, `isDeparture`, `isArrival`

**RZFlight.AIPEntry** already provides:
- `section` (admin/operational/handling/passenger)
- `field`, `value`, `standardField`, `mappingScore`
- `isStandardized`, `effectiveFieldName`, `effectiveValue`

### 3.2 App-Specific Types (Only When Necessary)

Only create app-level types for things NOT in RZFlight:
```

```swift
/// App-specific: Filter configuration for UI binding
/// PURE DATA - no DB dependencies, no apply() method
struct FilterConfig: Codable, Equatable, Sendable {
    var country: String?
    var hasProcedures: Bool?
    var hasAIPData: Bool?
    var hasHardRunway: Bool?
    var pointOfEntry: Bool?
    var hasAvgas: Bool?
    var hasJetA: Bool?
    var minRunwayLengthFt: Int?
    var maxRunwayLengthFt: Int?
    var maxLandingFee: Int?
    var aipField: String?
    var aipValue: String?
    var aipOperator: AIPOperator?
    
    enum AIPOperator: String, Codable, Sendable {
        case contains, equals, notEmpty, startsWith, endsWith
    }
    
    static let `default` = FilterConfig()
    
    /// Check if any filters are active
    var hasActiveFilters: Bool {
        country != nil || hasProcedures != nil || hasAIPData != nil ||
        hasHardRunway != nil || pointOfEntry != nil || hasAvgas != nil ||
        hasJetA != nil || minRunwayLengthFt != nil || maxRunwayLengthFt != nil ||
        maxLandingFee != nil || aipField != nil
    }
    
    // NOTE: No apply(to:db:) method!
    // Filtering is done by the repository, not by FilterConfig.
    // This keeps FilterConfig pure and free of storage dependencies.
}

/// App-specific: Map visualization highlight
struct MapHighlight: Identifiable {
    let id: String
    let coordinate: CLLocationCoordinate2D
    let color: Color
    let radius: Double
    let popup: String?
}

/// App-specific: Route visualization
struct RouteVisualization {
    let coordinates: [CLLocationCoordinate2D]
    let departure: String  // ICAO
    let destination: String  // ICAO
}

/// App-specific: API response wrapper (for online mode)
struct APIAirportResponse: Codable {
    let airports: [Airport]  // Uses RZFlight.Airport
    let total: Int
    let page: Int
}
```

---

## 4. Chatbot Design

### 4.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      ChatbotService Protocol                     │
│    sendMessage(_:) -> AsyncThrowingStream<ChatEvent, Error>     │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────────┐
│   OnlineChatbotService  │     │    OfflineChatbotService        │
│                         │     │                                 │
│  - SSE from web API     │     │  - LLMBackend (abstracted)      │
│  - Server does planning │     │  - Local tool execution         │
│  - Full capabilities    │     │  - Subset of capabilities       │
└─────────────────────────┘     └────────────────┬────────────────┘
                                                 │
                                                 ▼
                                ┌─────────────────────────────────┐
                                │      LLMBackend Protocol        │
                                │  (Swappable AI implementation)  │
                                ├─────────────────────────────────┤
                                │ - AppleIntelligenceBackend      │
                                │ - LlamaBackend (llama.cpp)      │
                                │ - MLXBackend                    │
                                │ - KeywordFallbackBackend        │
                                └─────────────────────────────────┘

                    SHARED ACROSS ONLINE/OFFLINE:
                    ┌─────────────────────────────────────────┐
                    │           ToolCatalog                   │
                    │  - Same tool definitions everywhere     │
                    │  - Same argument schemas                │
                    │  - Same visualization output types      │
                    └─────────────────────────────────────────┘
```

**Key Design Decisions:**
- **Offline AI is POST-1.0** - abstraction exists, implementation deferred
- **LLM backend is swappable** - can use Apple Intelligence, llama.cpp, MLX, or keyword fallback
- **Shared tool catalog** - avoid grammar drift between online/offline

### 4.2 Shared Tool Catalog

**Critical:** Online and offline use the **same tool definitions**. The server's tool catalog is the source of truth; the client mirrors it.

```swift
/// Shared tool definitions - SAME schema as server
/// Source of truth: shared/aviation_agent/tools.py
enum ToolCatalog {
    
    // MARK: - Tool Definitions
    
    static let allTools: [ToolDefinition] = [
        searchAirports,
        getAirportInfo,
        findAirportsNearRoute,
        findAirportsInCountry,
        findAirportsNearLocation,
        getAirportProcedures,
        getCountryRules
    ]
    
    static let searchAirports = ToolDefinition(
        name: "search_airports",
        description: "Search airports by ICAO code, name, or city",
        parameters: [
            .init(name: "query", type: .string, required: true,
                  description: "Search query (ICAO, name, or city)"),
            .init(name: "limit", type: .integer, required: false,
                  description: "Max results", defaultValue: 50),
            .init(name: "filters", type: .object, required: false,
                  description: "Optional FilterConfig")
        ],
        outputType: .airportList,
        availableOffline: true
    )
    
    static let getAirportInfo = ToolDefinition(
        name: "get_airport_info",
        description: "Get detailed information about a specific airport",
        parameters: [
            .init(name: "icao", type: .string, required: true,
                  description: "4-letter ICAO code")
        ],
        outputType: .airportDetail,
        availableOffline: true
    )
    
    static let findAirportsNearRoute = ToolDefinition(
        name: "find_airports_near_route",
        description: "Find airports along a route between two points",
        parameters: [
            .init(name: "departure", type: .string, required: true,
                  description: "Departure ICAO"),
            .init(name: "destination", type: .string, required: true,
                  description: "Destination ICAO"),
            .init(name: "distance_nm", type: .integer, required: false,
                  description: "Distance from route in NM", defaultValue: 50),
            .init(name: "filters", type: .object, required: false,
                  description: "Optional FilterConfig")
        ],
        outputType: .routeWithAirports,
        availableOffline: true  // Uses local DB
    )
    
    // ... more tools
    
    // MARK: - Offline Availability
    
    static var offlineTools: [ToolDefinition] {
        allTools.filter { $0.availableOffline }
    }
}

/// Tool definition matching server schema
struct ToolDefinition: Codable, Identifiable {
    let name: String
    let description: String
    let parameters: [ParameterDefinition]
    let outputType: OutputType
    let availableOffline: Bool
    
    var id: String { name }
    
    enum OutputType: String, Codable {
        case airportList
        case airportDetail
        case routeWithAirports
        case countryRules
        case text
    }
}

struct ParameterDefinition: Codable {
    let name: String
    let type: ParameterType
    let required: Bool
    let description: String
    let defaultValue: AnyCodable?
    
    enum ParameterType: String, Codable {
        case string, integer, number, boolean, object, array
    }
}
```

### 4.3 ChatbotService Protocol

```swift
/// Protocol for chatbot implementations
protocol ChatbotService: Sendable {
    var isOnline: Bool { get }
    var capabilities: ChatbotCapabilities { get }
    
    func sendMessage(_ message: String) -> AsyncThrowingStream<ChatEvent, Error>
    func clearHistory()
}

/// Chatbot capabilities (varies by mode)
struct ChatbotCapabilities: Sendable {
    let supportsStreaming: Bool
    let supportsToolCalls: Bool
    let supportsVisualization: Bool
    let availableTools: [String]  // Tool names from ToolCatalog
    let maxContextLength: Int
    
    static let online = ChatbotCapabilities(
        supportsStreaming: true,
        supportsToolCalls: true,
        supportsVisualization: true,
        availableTools: ToolCatalog.allTools.map(\.name),
        maxContextLength: 128_000
    )
    
    static let offline = ChatbotCapabilities(
        supportsStreaming: true,
        supportsToolCalls: true,
        supportsVisualization: true,
        availableTools: ToolCatalog.offlineTools.map(\.name),
        maxContextLength: 8_192
    )
    
    static let fallback = ChatbotCapabilities(
        supportsStreaming: false,
        supportsToolCalls: true,
        supportsVisualization: true,
        availableTools: ToolCatalog.offlineTools.map(\.name),
        maxContextLength: 0  // No LLM
    )
}
```

### 4.4 Online Chatbot (Full Functionality)

```swift
/// Online chatbot using web API (SSE streaming)
/// Server handles all planning and tool execution
final class OnlineChatbotService: ChatbotService {
    private let apiClient: APIClient
    private var sessionId: String?
    private var conversationHistory: [ChatMessage] = []
    
    var isOnline: Bool { true }
    var capabilities: ChatbotCapabilities { .online }
    
    func sendMessage(_ message: String) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                let request = ChatRequest(messages: conversationHistory + [.user(message)])
                
                for try await event in apiClient.streamSSE(endpoint: .chatStream(request)) {
                    switch event {
                    case .plan(let plan):
                        continuation.yield(.thinking(plan.reasoning))
                    case .toolCallStart(let name, let args):
                        continuation.yield(.toolCall(name: name, args: args))
                    case .message(let chunk):
                        continuation.yield(.content(chunk))
                    case .uiPayload(let payload):
                        continuation.yield(.visualization(VisualizationPayload(from: payload)))
                    case .done(let tokenInfo):
                        continuation.yield(.done(tokenInfo))
                        continuation.finish()
                    case .error(let error):
                        continuation.finish(throwing: ChatbotError.apiError(error))
                    }
                }
            }
        }
    }
    
    func clearHistory() {
        conversationHistory = []
        sessionId = nil
    }
}
```

### 4.5 LLM Backend Abstraction (For Future Offline AI)

**This is the key abstraction for swappable AI backends.**

```swift
/// Protocol for on-device LLM backends
/// Implementations: AppleIntelligence, llama.cpp, MLX, keyword fallback
protocol LLMBackend: Sendable {
    /// Check if this backend is available on current device
    static var isAvailable: Bool { get }
    
    /// Human-readable name for UI
    var name: String { get }
    
    /// Generate a streaming response
    func generate(
        prompt: String,
        systemPrompt: String?,
        maxTokens: Int
    ) -> AsyncThrowingStream<String, Error>
    
    /// Classify user intent (for tool selection)
    func classifyIntent(
        message: String,
        availableTools: [ToolDefinition]
    ) async throws -> IntentClassification
    
    /// Extract tool arguments from user message
    func extractArguments(
        message: String,
        tool: ToolDefinition
    ) async throws -> [String: Any]
}

/// Result of intent classification
struct IntentClassification {
    let suggestedTool: String?
    let confidence: Double
    let reasoning: String?
}

// MARK: - Backend Implementations

/// Apple Intelligence backend (iOS 18.1+, device-gated)
/// POST-1.0: Implementation deferred
@available(iOS 18.1, macOS 15.1, *)
final class AppleIntelligenceBackend: LLMBackend {
    static var isAvailable: Bool {
        // Check device capability
        // Apple Intelligence is not available on all devices
        false  // TODO: Check actual API availability
    }
    
    var name: String { "Apple Intelligence" }
    
    func generate(prompt: String, systemPrompt: String?, maxTokens: Int) -> AsyncThrowingStream<String, Error> {
        // TODO: Implement when Apple Intelligence API is stable
        fatalError("Not implemented - POST-1.0")
    }
    
    func classifyIntent(message: String, availableTools: [ToolDefinition]) async throws -> IntentClassification {
        fatalError("Not implemented - POST-1.0")
    }
    
    func extractArguments(message: String, tool: ToolDefinition) async throws -> [String: Any] {
        fatalError("Not implemented - POST-1.0")
    }
}

/// llama.cpp backend (future option)
/// Could use small models like Llama 3.2 1B, Phi-3 mini, etc.
final class LlamaCppBackend: LLMBackend {
    static var isAvailable: Bool {
        // Check if model file exists in app bundle or downloaded
        false  // TODO: Implement
    }
    
    var name: String { "Local LLM (llama.cpp)" }
    
    // TODO: Implement using llama.cpp Swift bindings
    func generate(prompt: String, systemPrompt: String?, maxTokens: Int) -> AsyncThrowingStream<String, Error> {
        fatalError("Not implemented - POST-1.0")
    }
    
    func classifyIntent(message: String, availableTools: [ToolDefinition]) async throws -> IntentClassification {
        fatalError("Not implemented - POST-1.0")
    }
    
    func extractArguments(message: String, tool: ToolDefinition) async throws -> [String: Any] {
        fatalError("Not implemented - POST-1.0")
    }
}

/// Keyword-based fallback (always available, no AI)
/// This is the 1.0 offline implementation
final class KeywordFallbackBackend: LLMBackend {
    static var isAvailable: Bool { true }  // Always available
    
    var name: String { "Basic (No AI)" }
    
    func generate(prompt: String, systemPrompt: String?, maxTokens: Int) -> AsyncThrowingStream<String, Error> {
        // No generation capability - return empty stream
        AsyncThrowingStream { $0.finish() }
    }
    
    func classifyIntent(message: String, availableTools: [ToolDefinition]) async throws -> IntentClassification {
        // Pattern matching for common queries
        let lower = message.lowercased()
        
        if lower.contains("between") || lower.contains("route") || 
           lower.contains("from") && lower.contains("to") {
            return IntentClassification(
                suggestedTool: "find_airports_near_route",
                confidence: 0.8,
                reasoning: "Detected route keywords"
            )
        }
        
        // Check for ICAO code pattern
        let icaoPattern = try! NSRegularExpression(pattern: "\\b[A-Z]{4}\\b")
        let range = NSRange(message.startIndex..., in: message)
        if icaoPattern.firstMatch(in: message.uppercased(), range: range) != nil {
            return IntentClassification(
                suggestedTool: "get_airport_info",
                confidence: 0.9,
                reasoning: "Detected ICAO code"
            )
        }
        
        if lower.contains("search") || lower.contains("find") || lower.contains("airports") {
            return IntentClassification(
                suggestedTool: "search_airports",
                confidence: 0.7,
                reasoning: "Detected search intent"
            )
        }
        
        return IntentClassification(
            suggestedTool: nil,
            confidence: 0.0,
            reasoning: "No pattern matched"
        )
    }
    
    func extractArguments(message: String, tool: ToolDefinition) async throws -> [String: Any] {
        // Simple extraction based on tool type
        switch tool.name {
        case "get_airport_info":
            // Extract ICAO code
            let pattern = try! NSRegularExpression(pattern: "\\b([A-Z]{4})\\b")
            let range = NSRange(message.startIndex..., in: message)
            if let match = pattern.firstMatch(in: message.uppercased(), range: range),
               let icaoRange = Range(match.range(at: 1), in: message.uppercased()) {
                return ["icao": String(message.uppercased()[icaoRange])]
            }
            
        case "find_airports_near_route":
            // Extract two ICAO codes
            let pattern = try! NSRegularExpression(pattern: "\\b([A-Z]{4})\\b")
            let range = NSRange(message.startIndex..., in: message)
            let matches = pattern.matches(in: message.uppercased(), range: range)
            if matches.count >= 2,
               let dep = Range(matches[0].range(at: 1), in: message.uppercased()),
               let dest = Range(matches[1].range(at: 1), in: message.uppercased()) {
                return [
                    "departure": String(message.uppercased()[dep]),
                    "destination": String(message.uppercased()[dest])
                ]
            }
            
        case "search_airports":
            // Use entire message as query (minus common words)
            let cleaned = message
                .replacingOccurrences(of: "search", with: "", options: .caseInsensitive)
                .replacingOccurrences(of: "find", with: "", options: .caseInsensitive)
                .replacingOccurrences(of: "airports", with: "", options: .caseInsensitive)
                .trimmingCharacters(in: .whitespaces)
            return ["query": cleaned.isEmpty ? message : cleaned]
            
        default:
            break
        }
        
        return [:]
    }
}
```

### 4.6 Offline Chatbot Service

```swift
/// Offline chatbot - uses LLMBackend abstraction
/// 1.0: Uses KeywordFallbackBackend
/// Future: Can swap in AppleIntelligence, llama.cpp, etc.
final class OfflineChatbotService: ChatbotService {
    private let backend: any LLMBackend
    private let toolExecutor: ToolExecutor
    private var conversationHistory: [ChatMessage] = []
    
    var isOnline: Bool { false }
    var capabilities: ChatbotCapabilities {
        backend is KeywordFallbackBackend ? .fallback : .offline
    }
    
    init(backend: any LLMBackend, repository: AirportRepositoryProtocol) {
        self.backend = backend
        self.toolExecutor = ToolExecutor(repository: repository)
    }
    
    func sendMessage(_ message: String) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    // 1. Classify intent using backend
                    let intent = try await backend.classifyIntent(
                        message: message,
                        availableTools: ToolCatalog.offlineTools
                    )
                    
                    if let reasoning = intent.reasoning {
                        continuation.yield(.thinking(reasoning))
                    }
                    
                    // 2. Execute tool if suggested
                    if let toolName = intent.suggestedTool,
                       let tool = ToolCatalog.offlineTools.first(where: { $0.name == toolName }) {
                        
                        // Extract arguments
                        let args = try await backend.extractArguments(message: message, tool: tool)
                        continuation.yield(.toolCall(name: toolName, args: args))
                        
                        // Execute tool
                        let result = try await toolExecutor.execute(tool: tool, arguments: args)
                        
                        // Generate response (if backend supports it)
                        if !(backend is KeywordFallbackBackend) {
                            let prompt = buildResponsePrompt(toolResult: result, originalMessage: message)
                            for try await token in backend.generate(prompt: prompt, systemPrompt: nil, maxTokens: 500) {
                                continuation.yield(.content(token))
                            }
                        } else {
                            // Keyword fallback: template response
                            let response = buildTemplateResponse(toolResult: result, tool: tool)
                            continuation.yield(.content(response))
                        }
                        
                        // Emit visualization
                        if let viz = result.visualization {
                            continuation.yield(.visualization(viz))
                        }
                    } else {
                        // No tool matched
                        if backend is KeywordFallbackBackend {
                            continuation.yield(.content(
                                "I can help you search for airports, get airport information, " +
                                "or find airports along a route. Try asking about a specific " +
                                "ICAO code like EGLL or search for airports in a country."
                            ))
                        } else {
                            // Let LLM generate a response
                            for try await token in backend.generate(
                                prompt: message,
                                systemPrompt: "You are an aviation assistant.",
                                maxTokens: 500
                            ) {
                                continuation.yield(.content(token))
                            }
                        }
                    }
                    
                    continuation.yield(.done(nil))
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    func clearHistory() {
        conversationHistory = []
    }
    
    private func buildTemplateResponse(toolResult: ToolResult, tool: ToolDefinition) -> String {
        switch tool.outputType {
        case .airportList:
            let count = toolResult.airports?.count ?? 0
            return "Found \(count) airport\(count == 1 ? "" : "s")."
        case .airportDetail:
            if let airport = toolResult.airport {
                return "**\(airport.name)** (\(airport.icao))\n" +
                       "Location: \(airport.city), \(airport.country)\n" +
                       "Elevation: \(airport.elevation_ft) ft"
            }
            return "Airport not found."
        case .routeWithAirports:
            let count = toolResult.airports?.count ?? 0
            return "Found \(count) airport\(count == 1 ? "" : "s") along the route."
        default:
            return "Done."
        }
    }
}
```

### 4.7 Tool Executor (Shared)

```swift
/// Executes tools locally using repository
/// Used by OfflineChatbotService
final class ToolExecutor {
    private let repository: AirportRepositoryProtocol
    
    init(repository: AirportRepositoryProtocol) {
        self.repository = repository
    }
    
    func execute(tool: ToolDefinition, arguments: [String: Any]) async throws -> ToolResult {
        switch tool.name {
        case "search_airports":
            let query = arguments["query"] as? String ?? ""
            let limit = arguments["limit"] as? Int ?? 50
            let airports = try await repository.searchAirports(query: query, limit: limit)
            return ToolResult(
                airports: airports,
                visualization: .markers(airports: airports)
            )
            
        case "get_airport_info":
            let icao = arguments["icao"] as? String ?? ""
            let airport = try await repository.airportDetail(icao: icao)
            return ToolResult(
                airport: airport,
                visualization: airport.map { .markerWithDetails(airport: $0) }
            )
            
        case "find_airports_near_route":
            let departure = arguments["departure"] as? String ?? ""
            let destination = arguments["destination"] as? String ?? ""
            let distance = arguments["distance_nm"] as? Int ?? 50
            let result = try await repository.airportsNearRoute(
                from: departure, to: destination, distanceNm: distance, filters: .default
            )
            return ToolResult(
                airports: result.airports,
                visualization: .routeWithMarkers(
                    route: RouteVisualization(
                        coordinates: [],  // Would need to compute
                        departure: departure,
                        destination: destination
                    ),
                    airports: result.airports
                )
            )
            
        default:
            throw ToolError.unknownTool(tool.name)
        }
    }
}

/// Result of tool execution
struct ToolResult {
    let airports: [Airport]?
    let airport: Airport?
    let visualization: VisualizationPayload?
    
    init(airports: [Airport]? = nil, airport: Airport? = nil, visualization: VisualizationPayload? = nil) {
        self.airports = airports
        self.airport = airport
        self.visualization = visualization
    }
}
```

### 4.8 Chatbot Service Factory

```swift
/// Factory for creating appropriate chatbot service
enum ChatbotServiceFactory {
    
    static func create(
        connectivity: ConnectivityMode,
        repository: AirportRepositoryProtocol,
        apiClient: APIClient
    ) -> any ChatbotService {
        switch connectivity {
        case .online, .hybrid:
            return OnlineChatbotService(apiClient: apiClient)
            
        case .offline:
            let backend = selectBestOfflineBackend()
            return OfflineChatbotService(backend: backend, repository: repository)
        }
    }
    
    /// Select best available offline backend
    /// Priority: AppleIntelligence > llama.cpp > MLX > Keyword fallback
    private static func selectBestOfflineBackend() -> any LLMBackend {
        // POST-1.0: Check for AI backends
        // if #available(iOS 18.1, *), AppleIntelligenceBackend.isAvailable {
        //     return AppleIntelligenceBackend()
        // }
        // if LlamaCppBackend.isAvailable {
        //     return LlamaCppBackend()
        // }
        
        // 1.0: Always use keyword fallback
        return KeywordFallbackBackend()
    }
}
```

### 4.9 Chatbot Events

```swift
/// Events streamed from chatbot
enum ChatEvent: Sendable {
    case thinking(String)              // Reasoning/planning
    case toolCall(name: String, args: [String: Any])  // Tool execution
    case content(String)               // Response text chunk
    case visualization(VisualizationPayload)  // Map visualization
    case done(TokenUsage?)             // Completion
}

/// Visualization payload (matches web app)
struct VisualizationPayload: Sendable {
    let kind: VisualizationKind
    let airports: [Airport]?
    let route: RouteVisualization?
    let point: PointVisualization?
    let filterProfile: FilterConfig?
    
    enum VisualizationKind: String, Sendable {
        case markers
        case routeWithMarkers = "route_with_markers"
        case markerWithDetails = "marker_with_details"
        case pointWithMarkers = "point_with_markers"
    }
    
    static func markers(airports: [Airport]) -> VisualizationPayload {
        VisualizationPayload(kind: .markers, airports: airports, route: nil, point: nil, filterProfile: nil)
    }
    
    static func markerWithDetails(airport: Airport) -> VisualizationPayload {
        VisualizationPayload(kind: .markerWithDetails, airports: [airport], route: nil, point: nil, filterProfile: nil)
    }
    
    static func routeWithMarkers(route: RouteVisualization, airports: [Airport]) -> VisualizationPayload {
        VisualizationPayload(kind: .routeWithMarkers, airports: airports, route: route, point: nil, filterProfile: nil)
    }
}
```

### 4.10 Offline AI Roadmap

**1.0 Release:**
- ✅ `OnlineChatbotService` - Full functionality via API
- ✅ `KeywordFallbackBackend` - Pattern matching, no AI
- ✅ `ToolCatalog` - Shared tool definitions
- ✅ `LLMBackend` protocol - Abstraction ready

**Post-1.0 (When Stable):**
- ⏳ `AppleIntelligenceBackend` - When API is mature and widely available
- ⏳ `LlamaCppBackend` - Small models (Llama 3.2 1B, Phi-3 mini)
- ⏳ `MLXBackend` - Apple Silicon optimized inference
- ⏳ Model download manager - For bundled vs downloaded models

**Decision Criteria for Shipping AI Backend:**
1. API is stable (not changing every iOS point release)
2. Works on >50% of target devices
3. Response quality is acceptable (no worse than keyword fallback)
4. Battery/thermal impact is acceptable
5. Model size is reasonable for app download

---

## 5. AppState - Single Source of Truth (Composed)

### 5.1 Why Single Store, But Composed?

**Problems with Multiple ViewModels:**
- State synchronization between Map, Detail, and Chat views
- Chatbot needs to update map state (visualizations)
- Filters affect multiple views
- Complex coordination for deep linking

**Problems with Monolithic AppState:**
- God-class anti-pattern (2,000+ lines handling everything)
- Hard to test individual domains
- Hard to reason about side effects
- Merge conflicts when multiple devs work on state

**Solution:** One `@Observable` store composed of smaller domain objects.

```
┌─────────────────────────────────────────────────────────────────┐
│                        AppState                                  │
│                   (Single Source of Truth)                       │
│                                                                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │AirportDomain │ │  ChatDomain  │ │   NavigationDomain       │ │
│  │              │ │              │ │                          │ │
│  │ - airports   │ │ - messages   │ │ - path                   │ │
│  │ - filters    │ │ - streaming  │ │ - selectedTab            │ │
│  │ - selected   │ │ - thinking   │ │ - sheets                 │ │
│  │ - search     │ │ - input      │ │                          │ │
│  │ - map state  │ │              │ │                          │ │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    SystemDomain                           │   │
│  │                                                          │   │
│  │  - connectivityMode    - isLoading    - error            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  // Cross-domain actions (thin orchestration)                   │
│  func applyVisualization(_ payload: VisualizationPayload)       │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits:**
- Single store guarantee (Redux-style)
- Each domain ~200-400 lines, not 2,000
- Unit test domains in isolation
- Clear ownership of state
- Easy to add new domains (e.g., `SettingsDomain`)

### 5.2 Domain Objects

Each domain is `@Observable`, owns its state, and has its own actions.

#### AirportDomain

```swift
import SwiftUI
import MapKit
import RZFlight

/// Domain: Airport data, filters, map visualization
@Observable
@MainActor
final class AirportDomain {
    
    // MARK: - Dependencies
    private let repository: AirportRepository
    
    // MARK: - Airport Data
    /// Airports already filtered by repository - ready for display
    var airports: [Airport] = []
    var selectedAirport: Airport?
    
    // MARK: - Filters
    /// Current filter config (pure data, no DB logic)
    var filters: FilterConfig = .default
    
    // MARK: - Search
    var searchQuery: String = ""
    var searchResults: [Airport] = []
    var isSearching: Bool = false
    
    // MARK: - Map State
    var mapPosition: MapCameraPosition = .automatic
    var legendMode: LegendMode = .airportType
    var highlights: [String: MapHighlight] = [:]
    var activeRoute: RouteVisualization?
    
    // MARK: - Computed
    
    /// For display - airports are already filtered by repository
    /// Use applyInMemoryFilters only for additional client-side refinement
    var displayAirports: [Airport] {
        airports  // Already filtered when loaded
    }
    
    // MARK: - Init
    
    init(repository: AirportRepository) {
        self.repository = repository
    }
    
    // MARK: - Actions
    
    func load() async throws {
        // Repository handles all filtering (including DB-dependent ones)
        airports = try await repository.airports(matching: filters, limit: 1000)
    }
    
    func search(query: String) async throws {
        guard !query.isEmpty else {
            searchResults = []
            return
        }
        
        isSearching = true
        defer { isSearching = false }
        
        if isRouteQuery(query) {
            try await searchRoute(query)
        } else {
            searchResults = try await repository.searchAirports(query: query, limit: 50)
        }
    }
    
    func select(_ airport: Airport) {
        selectedAirport = airport
        focusMap(on: airport.coord)
    }
    
    func focusMap(on coordinate: CLLocationCoordinate2D, span: Double = 2.0) {
        withAnimation(.snappy) {
            mapPosition = .region(MKCoordinateRegion(
                center: coordinate,
                span: MKCoordinateSpan(latitudeDelta: span, longitudeDelta: span)
            ))
        }
    }
    
    func searchRoute(_ query: String) async throws {
        let icaos = query.uppercased().split(separator: " ").map(String.init)
        guard icaos.count >= 2, let from = icaos.first, let to = icaos.last else { return }
        
        let result = try await repository.getAirportsNearRoute(
            from: from, to: to, distanceNm: 50, filters: filters
        )
        airports = result.airports
        activeRoute = RouteVisualization(coordinates: [], departure: from, destination: to)
        fitMapToRoute()
    }
    
    func clearRoute() {
        activeRoute = nil
        highlights = highlights.filter { !$0.key.hasPrefix("route-") }
    }
    
    func applyFilters() async throws {
        try await load()
    }
    
    func resetFilters() {
        filters = .default
        Task { try? await load() }
    }
    
    /// Apply visualization from chatbot
    func applyVisualization(_ payload: VisualizationPayload) {
        switch payload.kind {
        case .markers:
            if let airports = payload.airports {
                self.airports = airports
                fitMapToAirports()
            }
        case .routeWithMarkers:
            if let route = payload.route { self.activeRoute = route }
            if let airports = payload.airports { self.airports = airports }
            payload.airports?.forEach { airport in
                highlights["chat-\(airport.icao)"] = MapHighlight(
                    id: "chat-\(airport.icao)",
                    coordinate: airport.coord,
                    color: .blue, radius: 15000, popup: airport.name
                )
            }
            fitMapToRoute()
        case .markerWithDetails:
            if let airport = payload.airports?.first { select(airport) }
        case .pointWithMarkers:
            if let airports = payload.airports {
                self.airports = airports
                fitMapToAirports()
            }
        }
        if let filterProfile = payload.filterProfile {
            self.filters = filterProfile
        }
    }
    
    // MARK: - Private
    
    private func isRouteQuery(_ query: String) -> Bool {
        let parts = query.uppercased().split(separator: " ")
        return parts.count >= 2 && parts.allSatisfy { $0.count == 4 && $0.allSatisfy(\.isLetter) }
    }
    
    private func fitMapToAirports() {
        guard !airports.isEmpty else { return }
        // Calculate bounding box
    }
    
    private func fitMapToRoute() {
        guard activeRoute != nil else { return }
        // Calculate bounding box
    }
}
```

#### ChatDomain

```swift
/// Domain: Chat messages, streaming, LLM interaction
@Observable
@MainActor
final class ChatDomain {
    
    // MARK: - Dependencies
    private var chatbotService: ChatbotService
    
    // MARK: - State
    var messages: [ChatMessage] = []
    var input: String = ""
    var isStreaming: Bool = false
    var currentThinking: String?
    
    // MARK: - Callbacks (for cross-domain communication)
    var onVisualization: ((VisualizationPayload) -> Void)?
    
    // MARK: - Init
    
    init(chatbotService: ChatbotService) {
        self.chatbotService = chatbotService
    }
    
    // MARK: - Actions
    
    func send() async {
        guard !input.isEmpty else { return }
        
        let userMessage = ChatMessage(role: .user, content: input)
        messages.append(userMessage)
        input = ""
        isStreaming = true
        
        var assistantContent = ""
        
        do {
            for try await event in chatbotService.sendMessage(userMessage.content) {
                switch event {
                case .thinking(let thought):
                    currentThinking = thought
                case .content(let chunk):
                    assistantContent += chunk
                    updateStreamingMessage(assistantContent)
                case .visualization(let payload):
                    onVisualization?(payload)  // Notify AppState
                case .done:
                    finalizeMessage(assistantContent)
                case .toolCall:
                    break
                }
            }
        } catch {
            messages.append(ChatMessage(
                role: .assistant,
                content: "Sorry, I encountered an error: \(error.localizedDescription)"
            ))
        }
        
        isStreaming = false
        currentThinking = nil
    }
    
    func clear() {
        messages = []
        chatbotService.clearHistory()
    }
    
    func updateService(_ service: ChatbotService) {
        self.chatbotService = service
    }
    
    // MARK: - Private
    
    private func updateStreamingMessage(_ content: String) {
        if let lastIndex = messages.lastIndex(where: { $0.role == .assistant && $0.isStreaming }) {
            messages[lastIndex].content = content
        } else {
            messages.append(ChatMessage(role: .assistant, content: content, isStreaming: true))
        }
    }
    
    private func finalizeMessage(_ content: String) {
        if let lastIndex = messages.lastIndex(where: { $0.role == .assistant && $0.isStreaming }) {
            messages[lastIndex].content = content
            messages[lastIndex].isStreaming = false
        }
    }
}
```

#### NavigationDomain

```swift
/// Domain: Navigation state, tabs, sheets
@Observable
@MainActor
final class NavigationDomain {
    
    // MARK: - State
    var path = NavigationPath()
    var selectedTab: Tab = .map
    var showingChat: Bool = false
    var showingFilters: Bool = false
    var showingSettings: Bool = false
    
    enum Tab: String, CaseIterable, Identifiable {
        case map, search, chat, settings
        var id: String { rawValue }
    }
    
    // MARK: - Actions
    
    func navigate(to destination: any Hashable) {
        path.append(destination)
    }
    
    func pop() {
        guard !path.isEmpty else { return }
        path.removeLast()
    }
    
    func popToRoot() {
        path = NavigationPath()
    }
    
    func showChat() {
        showingChat = true
    }
    
    func showFilters() {
        showingFilters = true
    }
}
```

#### SystemDomain

```swift
/// Domain: Connectivity, loading, errors, app-wide concerns
@Observable
@MainActor
final class SystemDomain {
    
    // MARK: - Dependencies
    private let connectivityMonitor: ConnectivityMonitor
    
    // MARK: - State
    var connectivityMode: ConnectivityMode = .offline
    var isLoading: Bool = false
    var error: AppError?
    
    // MARK: - Init
    
    init(connectivityMonitor: ConnectivityMonitor) {
        self.connectivityMonitor = connectivityMonitor
    }
    
    // MARK: - Actions
    
    func startMonitoring() {
        Task {
            for await mode in connectivityMonitor.modeStream {
                self.connectivityMode = mode
            }
        }
    }
    
    func setLoading(_ loading: Bool) {
        isLoading = loading
    }
    
    func setError(_ error: Error?) {
        self.error = error.map { AppError(from: $0) }
    }
    
    func clearError() {
        error = nil
    }
}
```

### 5.3 AppState (Thin Orchestration Layer)

AppState composes domains and handles cross-domain coordination.

```swift
import SwiftUI
import RZFlight

/// Single source of truth - composes domain objects
/// Handles cross-domain coordination only
@Observable
@MainActor
final class AppState {
    
    // MARK: - Domain Objects
    let airports: AirportDomain
    let chat: ChatDomain
    let navigation: NavigationDomain
    let system: SystemDomain
    
    // MARK: - Init
    
    init(
        repository: AirportRepository,
        chatbotService: ChatbotService,
        connectivityMonitor: ConnectivityMonitor
    ) {
        self.airports = AirportDomain(repository: repository)
        self.chat = ChatDomain(chatbotService: chatbotService)
        self.navigation = NavigationDomain()
        self.system = SystemDomain(connectivityMonitor: connectivityMonitor)
        
        // Wire up cross-domain callbacks
        setupCrossDomainWiring()
    }
    
    // MARK: - Cross-Domain Wiring
    
    private func setupCrossDomainWiring() {
        // Chat visualizations update airport domain
        chat.onVisualization = { [weak self] payload in
            self?.airports.applyVisualization(payload)
        }
    }
    
    // MARK: - Lifecycle
    
    func onAppear() async {
        system.startMonitoring()
        system.setLoading(true)
        defer { system.setLoading(false) }
        
        do {
            try await airports.load()
        } catch {
            system.setError(error)
        }
    }
    
    // MARK: - Cross-Domain Actions (Orchestration)
    
    /// Search that might involve both airports and navigation
    func search(query: String) async {
        do {
            try await airports.search(query: query)
            // If single result, navigate to detail
            if airports.searchResults.count == 1,
               let airport = airports.searchResults.first {
                airports.select(airport)
            }
        } catch {
            system.setError(error)
        }
    }
    
    /// Apply filters and navigate to results
    func applyFiltersAndShow() async {
        system.setLoading(true)
        defer { system.setLoading(false) }
        
        do {
            try await airports.applyFilters()
            navigation.showingFilters = false
        } catch {
            system.setError(error)
        }
    }
    
    /// Select airport from chat and show on map
    func selectAirportFromChat(_ airport: Airport) {
        airports.select(airport)
        navigation.showingChat = false
        navigation.selectedTab = .map
    }
}
```

### 5.4 Environment Injection

```swift
// MARK: - Environment Key

struct AppStateKey: EnvironmentKey {
    static let defaultValue: AppState? = nil
}

extension EnvironmentValues {
    var appState: AppState? {
        get { self[AppStateKey.self] }
        set { self[AppStateKey.self] = newValue }
    }
}

// MARK: - App Entry Point

@main
struct FlyFunEuroAIPApp: App {
    @State private var appState: AppState
    
    init() {
        let repository = AirportRepository()
        let chatbot = ChatbotServiceFactory.create()
        let connectivity = ConnectivityMonitor()
        
        _appState = State(initialValue: AppState(
            repository: repository,
            chatbotService: chatbot,
            connectivityMonitor: connectivity
        ))
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.appState, appState)
        }
    }
}
```

### 5.5 Usage in Views

Views access domains through AppState:

```swift
struct AirportMapView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        // Access airport domain state
        let airports = state?.airports
        
        Map(position: Binding(
            get: { airports?.mapPosition ?? .automatic },
            set: { airports?.mapPosition = $0 }
        )) {
            if let airports {
                ForEach(airports.airports) { airport in
                    Annotation(airport.icao, coordinate: airport.coord) {
                        AirportMarker(airport: airport, legendMode: airports.legendMode)
                            .onTapGesture {
                                airports.select(airport)
                            }
                    }
                }
                
                if let route = airports.activeRoute {
                    MapPolyline(coordinates: route.coordinates)
                        .stroke(.blue, lineWidth: 3)
                }
            }
        }
    }
}

struct ChatView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        // Access chat domain directly
        let chat = state?.chat
        
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack {
                    ForEach(chat?.messages ?? []) { message in
                        ChatBubble(message: message)
                    }
                }
            }
            
            ChatInputBar(
                text: Binding(
                    get: { chat?.input ?? "" },
                    set: { chat?.input = $0 }
                ),
                isStreaming: chat?.isStreaming ?? false,
                onSend: {
                    Task { await chat?.send() }
                }
            )
        }
    }
}
```

### 5.6 Benefits of Composed AppState

| Aspect | Monolithic | Composed |
|--------|------------|----------|
| **Lines per file** | 2,000+ | 200-400 |
| **Testability** | Hard (mock everything) | Easy (test domain in isolation) |
| **Merge conflicts** | Frequent | Rare |
| **Reasoning** | Complex | Clear ownership |
| **Adding features** | Edit God-class | Add new domain |
| **Single source of truth** | ✅ Yes | ✅ Yes |
| **Cross-domain sync** | Implicit | Explicit callbacks |

### 5.7 When to Add a New Domain

Add a new domain when:
- You have 5+ related properties
- Properties have their own actions
- State is independently testable
- Logic is reusable

**Examples:**
- `SettingsDomain` - user preferences, sync settings
- `CacheDomain` - offline tile management, database sync
- `AnalyticsDomain` - usage tracking (if needed)

---

## 5a. No ViewModels - Clarification

**Rule:** The app uses `AppState` with composed domains. There are NO standalone ViewModels.

**What this means:**
- ❌ No `AirportMapViewModel.swift`
- ❌ No `ChatbotViewModel.swift`  
- ❌ No `FilterViewModel.swift`

**If you need view-specific logic:**

Option 1: Put it in the domain
```swift
// ChatDomain handles all chat logic
state.chat.send()
```

Option 2: Use a thin ViewCoordinator (read-only projections)
```swift
/// Read-only projection for complex view logic
/// NEVER holds unique state - just convenience computed properties
struct MapViewCoordinator {
    let airports: AirportDomain
    
    var visibleAirports: [Airport] {
        airports.airports.filter { /* visible in region */ }
    }
    
    var markerCount: Int {
        visibleAirports.count
    }
}
```

**ViewCoordinator rules:**
1. No `@Observable` - it's a struct
2. No stored state - only computed properties
3. Takes domain(s) as input
4. Used for complex view-specific computations only

---

## 5b. Legend Mode

```swift
enum LegendMode: String, CaseIterable, Identifiable {
    case airportType = "Airport Type"
    case procedurePrecision = "Procedure Precision"
    case runwayLength = "Runway Length"
    case country = "Country"
    
    var id: String { rawValue }
}
```

### 5.3 Environment Injection

```swift
// MARK: - Environment Key

struct AppStateKey: EnvironmentKey {
    static let defaultValue: AppState? = nil
}

extension EnvironmentValues {
    var appState: AppState? {
        get { self[AppStateKey.self] }
        set { self[AppStateKey.self] = newValue }
    }
}

// MARK: - App Entry Point

@main
struct FlyFunEuroAIPApp: App {
    @State private var appState: AppState
    
    init() {
        // Initialize dependencies
        let repository = AirportRepository()
        let chatbot = ChatbotServiceFactory.create()
        let connectivity = ConnectivityMonitor()
        
        _appState = State(initialValue: AppState(
            repository: repository,
            chatbotService: chatbot,
            connectivityMonitor: connectivity
        ))
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.appState, appState)
        }
    }
}

// MARK: - Usage in Views

struct AirportMapView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Map(position: Binding(
            get: { state?.mapPosition ?? .automatic },
            set: { state?.mapPosition = $0 }
        )) {
            if let state {
                ForEach(state.airports.airports) { airport in
                    Annotation(airport.icao, coordinate: airport.coord) {
                        AirportMarker(airport: airport, legendMode: state.airports.legendMode)
                            .onTapGesture {
                                state.selectAirport(airport)
                            }
                    }
                }
                
                if let route = state.activeRoute {
                    MapPolyline(coordinates: route.coordinates)
                        .stroke(.blue, lineWidth: 3)
                }
            }
        }
    }
}
```

### 5.8 Benefits of Composed AppState

| Aspect | Benefit |
|--------|---------|
| **Chat → Map Sync** | Chatbot calls `airports.applyVisualization()` via callback |
| **Filter Changes** | One domain owns filters, all views react |
| **Deep Linking** | Set `navigation.path` to navigate anywhere |
| **Testing** | Test each domain in isolation (~200-400 lines) |
| **Debugging** | Clear domain ownership, inspect specific domain |
| **Persistence** | Serialize individual domains or all |
| **Undo/Redo** | Snapshot individual domain state |
| **Maintainability** | No 2,000-line God-class |
| **Onboarding** | New devs can understand one domain at a time |

---

## 6. UI Design

### 6.1 Adaptive Layouts

```
┌─────────────────────────────────────────────────────────────────────┐
│                      iPhone (Compact)                                │
├─────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │                        Map (Full Screen)                        │ │
│ │                                                                 │ │
│ │  ┌──────────────┐  ┌───┐                                       │ │
│ │  │  Search...   │  │ ⚙ │  <- Floating controls                 │ │
│ │  └──────────────┘  └───┘                                       │ │
│ │                                                                 │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │  Results / Filters / Chat (Sheet - swipe up)                    │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    iPad / Mac (Regular)                              │
├─────────────────────────────────────────────────────────────────────┤
│ ┌─────────────┐ ┌───────────────────────────────┐ ┌───────────────┐ │
│ │             │ │                               │ │               │ │
│ │   Search    │ │           Map                 │ │   Filters     │ │
│ │   Results   │ │                               │ │   OR          │ │
│ │             │ │                               │ │   Chat        │ │
│ │   Airport   │ │                               │ │               │ │
│ │   Details   │ │                               │ │               │ │
│ │             │ │                               │ │               │ │
│ └─────────────┘ └───────────────────────────────┘ └───────────────┘ │
│     Sidebar          Main Content                   Inspector        │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 View Hierarchy (Modern SwiftUI)

```swift
// MARK: - Root View

struct ContentView: View {
    @Environment(\.appState) private var state
    @Environment(\.horizontalSizeClass) private var sizeClass
    
    var body: some View {
        Group {
            if sizeClass == .regular {
                RegularLayout()
            } else {
                CompactLayout()
            }
        }
        .task {
            await state?.loadAirports()
        }
    }
}

// MARK: - iPad/Mac Layout (NavigationSplitView + Inspector)

struct RegularLayout: View {
    @Environment(\.appState) private var state
    @State private var columnVisibility: NavigationSplitViewVisibility = .all
    
    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            // Sidebar: Search + Results
            SearchSidebar()
                .navigationTitle("Airports")
        } content: {
            // Main: Map (always visible)
            AirportMapView()
                .navigationTitle("")
                .toolbar(.hidden, for: .navigationBar)
        } detail: {
            // Detail: Airport Detail or empty state
            if let airport = state?.selectedAirport {
                AirportDetailView(airport: airport)
            } else {
                ContentUnavailableView(
                    "Select an Airport",
                    systemImage: "airplane.circle",
                    description: Text("Choose an airport from the map or search to see details")
                )
            }
        }
        .inspector(isPresented: Binding(
            get: { state?.showingFilters ?? false },
            set: { state?.showingFilters = $0 }
        )) {
            FilterPanel()
                .inspectorColumnWidth(min: 280, ideal: 320, max: 400)
        }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    state?.showingFilters.toggle()
                } label: {
                    Label("Filters", systemImage: "line.3.horizontal.decrease.circle")
                }
                
                Button {
                    state?.showingChat.toggle()
                } label: {
                    Label("Chat", systemImage: "bubble.left.and.bubble.right")
                }
            }
        }
        .sheet(isPresented: Binding(
            get: { state?.showingChat ?? false },
            set: { state?.showingChat = $0 }
        )) {
            NavigationStack {
                ChatView()
                    .navigationTitle("Aviation Assistant")
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Done") { state?.showingChat = false }
                        }
                    }
            }
            .presentationDetents([.medium, .large])
        }
    }
}

// MARK: - iPhone Layout (Map + Bottom Sheet)

struct CompactLayout: View {
    @Environment(\.appState) private var state
    @State private var sheetDetent: PresentationDetent = .fraction(0.25)
    
    var body: some View {
        ZStack(alignment: .top) {
            // Full-screen map
            AirportMapView()
                .ignoresSafeArea()
            
            // Floating search bar
            SearchBarCompact()
                .padding(.horizontal)
                .padding(.top, 8)
            
            // Floating chat button
            VStack {
                Spacer()
                HStack {
                    Spacer()
                    FloatingChatButton()
                        .padding(.trailing)
                        .padding(.bottom, 160) // Above sheet
                }
            }
        }
        .sheet(isPresented: .constant(true)) {
            CompactSheetContent()
                .presentationDetents([.fraction(0.25), .medium, .large], selection: $sheetDetent)
                .presentationDragIndicator(.visible)
                .presentationBackgroundInteraction(.enabled(upThrough: .medium))
                .interactiveDismissDisabled()
        }
    }
}

// MARK: - Compact Sheet Content

struct CompactSheetContent: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        NavigationStack(path: Binding(
            get: { state?.navigationPath ?? NavigationPath() },
            set: { state?.navigationPath = $0 }
        )) {
            VStack(spacing: 0) {
                // Segmented control for content switching
                Picker("View", selection: Binding(
                    get: { state?.selectedTab ?? .map },
                    set: { state?.selectedTab = $0 }
                )) {
                    Label("Results", systemImage: "list.bullet").tag(AppState.Tab.search)
                    Label("Filters", systemImage: "slider.horizontal.3").tag(AppState.Tab.map)
                    Label("Chat", systemImage: "bubble.left").tag(AppState.Tab.chat)
                }
                .pickerStyle(.segmented)
                .padding()
                
                // Content based on selection
                Group {
                    switch state?.selectedTab ?? .search {
                    case .search, .map:
                        if state?.selectedAirport != nil {
                            AirportDetailView(airport: state!.selectedAirport!)
                        } else {
                            SearchResultsList()
                        }
                    case .chat:
                        ChatView()
                    case .settings:
                        FilterPanel()
                    }
                }
            }
            .navigationDestination(for: Airport.self) { airport in
                AirportDetailView(airport: airport)
            }
        }
    }
}

// MARK: - Floating Chat Button

struct FloatingChatButton: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Button {
            withAnimation(.spring(response: 0.3)) {
                state?.showingChat.toggle()
            }
        } label: {
            Image(systemName: state?.isStreaming == true ? "ellipsis.bubble.fill" : "bubble.left.and.bubble.right.fill")
                .font(.title2)
                .symbolEffect(.bounce, value: state?.isStreaming)
        }
        .buttonStyle(.borderedProminent)
        .buttonBorderShape(.circle)
        .controlSize(.large)
        .shadow(radius: 4)
    }
}
```

### 6.3 Key Views (Modern SwiftUI with @Environment)

```swift
// MARK: - Map View

struct AirportMapView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Map(position: Binding(
            get: { state?.airports.mapPosition ?? .automatic },
            set: { state?.airports.mapPosition = $0 }
        )) {
            if let state {
                // Airport markers - already filtered by repository
                ForEach(state.airports.airports) { airport in
                    Annotation(airport.icao, coordinate: airport.coord) {
                        AirportMarker(airport: airport, legendMode: state.airports.legendMode)
                            .onTapGesture {
                                state.airports.select(airport)
                            }
                    }
                }
                
                // Route polyline
                if let route = state.airports.activeRoute {
                    MapPolyline(coordinates: route.coordinates)
                        .stroke(.blue, lineWidth: 3)
                }
                
                // Highlights (from chatbot)
                ForEach(Array(state.airports.highlights.values)) { highlight in
                    MapCircle(center: highlight.coordinate, radius: highlight.radius)
                        .foregroundStyle(highlight.color.opacity(0.3))
                        .stroke(highlight.color, lineWidth: 2)
                }
            }
        }
        .mapStyle(.standard(elevation: .realistic))
        .mapControls {
            MapCompass()
            MapScaleView()
            MapUserLocationButton()
        }
        // Legend overlay
        .overlay(alignment: .topTrailing) {
            MapLegend(legendMode: state?.legendMode ?? .airportType)
                .padding()
        }
        // Connectivity indicator
        .overlay(alignment: .top) {
            if state?.connectivityMode == .offline {
                OfflineBanner()
            }
        }
    }
}

// MARK: - Airport Marker

struct AirportMarker: View {
    let airport: Airport
    let legendMode: LegendMode
    
    var body: some View {
        ZStack {
            Circle()
                .fill(markerColor.gradient)
                .frame(width: 32, height: 32)
            
            Text(airport.icao.prefix(3))
                .font(.caption2.bold())
                .foregroundStyle(.white)
        }
        .shadow(radius: 2)
    }
    
    var markerColor: Color {
        switch legendMode {
        case .airportType:
            if airport.procedures.isEmpty { return .gray }
            return airport.isBorderCrossing ? .green : .blue
        case .procedurePrecision:
            guard let best = airport.approaches.min(by: { $0.isMorePreciseThan($1) }) else { return .gray }
            switch best.precisionCategory {
            case .precision: return .green
            case .rnav: return .blue
            case .nonPrecision: return .orange
            }
        case .runwayLength:
            let maxLength = airport.runways.map(\.length_ft).max() ?? 0
            if maxLength >= 6000 { return .green }
            if maxLength >= 3000 { return .blue }
            return .orange
        case .country:
            return countryColor(for: airport.country)
        }
    }
}

// MARK: - Filter Panel

struct FilterPanel: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Form {
            Section("Country") {
                Picker("Country", selection: filterBinding(\.country)) {
                    Text("All Countries").tag(nil as String?)
                    ForEach(availableCountries, id: \.self) { country in
                        Text(countryName(for: country)).tag(country as String?)
                    }
                }
            }
            
            Section("Airport Features") {
                Toggle("Border Crossing / Customs", isOn: boolFilterBinding(\.pointOfEntry))
                Toggle("Has IFR Procedures", isOn: boolFilterBinding(\.hasProcedures))
                Toggle("Has AIP Data", isOn: boolFilterBinding(\.hasAIPData))
                Toggle("Hard Surface Runway", isOn: boolFilterBinding(\.hasHardRunway))
            }
            
            Section("Fuel Availability") {
                Toggle("AVGAS (100LL)", isOn: boolFilterBinding(\.hasAvgas))
                Toggle("Jet-A", isOn: boolFilterBinding(\.hasJetA))
            }
            
            Section("Runway Requirements") {
                LabeledContent("Minimum Length") {
                    Stepper(
                        "\(state?.filters.minRunwayLengthFt ?? 0) ft",
                        value: Binding(
                            get: { state?.filters.minRunwayLengthFt ?? 0 },
                            set: { state?.filters.minRunwayLengthFt = $0 > 0 ? $0 : nil }
                        ),
                        in: 0...10000,
                        step: 500
                    )
                    .monospacedDigit()
                }
            }
            
            Section("Display") {
                Picker("Legend Mode", selection: Binding(
                    get: { state?.legendMode ?? .airportType },
                    set: { state?.legendMode = $0 }
                )) {
                    ForEach(LegendMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
            }
            
            Section {
                Button("Apply Filters", action: applyFilters)
                    .frame(maxWidth: .infinity)
                    .buttonStyle(.borderedProminent)
                
                Button("Reset All", role: .destructive) {
                    state?.resetFilters()
                }
                .frame(maxWidth: .infinity)
            }
        }
        .navigationTitle("Filters")
    }
    
    // Helper bindings for optional bools
    private func boolFilterBinding(_ keyPath: WritableKeyPath<FilterConfig, Bool?>) -> Binding<Bool> {
        Binding(
            get: { state?.filters[keyPath: keyPath] ?? false },
            set: { state?.filters[keyPath: keyPath] = $0 ? true : nil }
        )
    }
    
    private func applyFilters() {
        Task { await state?.applyFilters() }
    }
}

// MARK: - Chat View

struct ChatView: View {
    @Environment(\.appState) private var state
    @FocusState private var isInputFocused: Bool
    
    var body: some View {
        VStack(spacing: 0) {
            // Connection status
            if state?.connectivityMode == .offline {
                OfflineChatBanner()
            }
            
            // Message list
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(state?.chatMessages ?? []) { message in
                            ChatBubble(message: message)
                                .id(message.id)
                        }
                        
                        // Thinking indicator
                        if let thinking = state?.currentThinking {
                            ThinkingBubble(text: thinking)
                        }
                        
                        // Streaming indicator
                        if state?.isStreaming == true {
                            TypingIndicator()
                        }
                    }
                    .padding()
                }
                .onChange(of: state?.chatMessages.count) { _, _ in
                    if let lastId = state?.chatMessages.last?.id {
                        withAnimation {
                            proxy.scrollTo(lastId, anchor: .bottom)
                        }
                    }
                }
            }
            
            Divider()
            
            // Input bar
            HStack(spacing: 12) {
                TextField("Ask about airports...", text: Binding(
                    get: { state?.chatInput ?? "" },
                    set: { state?.chatInput = $0 }
                ), axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...5)
                .focused($isInputFocused)
                .onSubmit {
                    Task { await state?.sendChatMessage() }
                }
                
                Button {
                    Task { await state?.sendChatMessage() }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                }
                .disabled(state?.chatInput.isEmpty ?? true || state?.isStreaming ?? false)
                .symbolEffect(.bounce, value: state?.isStreaming)
            }
            .padding()
            .background(.bar)
        }
    }
}

// MARK: - Chat Bubble

struct ChatBubble: View {
    let message: ChatMessage
    
    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 60) }
            
            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                Text(message.content)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        message.role == .user ? Color.accentColor : Color(.secondarySystemBackground),
                        in: RoundedRectangle(cornerRadius: 16, style: .continuous)
                    )
                    .foregroundStyle(message.role == .user ? .white : .primary)
                
                if message.isStreaming {
                    ProgressView()
                        .scaleEffect(0.7)
                }
            }
            
            if message.role == .assistant { Spacer(minLength: 60) }
        }
    }
}
```

---

## 7. Feature Breakdown

### 7.1 Feature Matrix

| Feature | Offline | Online | Notes |
|---------|---------|--------|-------|
| **Map** |
| Display airports | ✅ | ✅ | Bundled vs latest data |
| Map tiles | ✅ (cached) | ✅ | Cache offline tiles |
| Airport markers | ✅ | ✅ | |
| Legend modes | ✅ | ✅ | |
| Route display | ✅ | ✅ | |
| **Search** |
| ICAO/Name search | ✅ | ✅ | |
| Route search | ✅ (basic) | ✅ | Online: optimized routing |
| Location search | ✅ (coords) | ✅ | Online: geocoding |
| **Filters** |
| Country | ✅ | ✅ | |
| Border crossing | ✅ | ✅ | |
| Has procedures | ✅ | ✅ | |
| Has AIP data | ✅ | ✅ | |
| Hard runway | ✅ | ✅ | |
| AVGAS/Jet-A | ⚠️ (limited) | ✅ | May lack fuel data offline |
| Runway length | ✅ | ✅ | |
| Landing fees | ❌ | ✅ | Requires latest data |
| AIP field search | ⚠️ (cached) | ✅ | |
| **Details** |
| Airport info | ✅ | ✅ | |
| Runways | ✅ | ✅ | |
| Procedures | ✅ | ✅ | |
| AIP entries | ⚠️ (cached) | ✅ | May be outdated offline |
| Country rules | ⚠️ (bundled) | ✅ | |
| **Chatbot** |
| Basic queries | ✅ | ✅ | |
| Airport search | ✅ | ✅ | |
| Route planning | ⚠️ (basic) | ✅ | Limited reasoning offline |
| Complex filters | ⚠️ (limited) | ✅ | |
| Streaming | ✅ | ✅ | |
| Visualizations | ✅ | ✅ | |
| **Sync** |
| Database update | N/A | ✅ | Background download |
| Cache AIP data | N/A | ✅ | |

### 7.2 Offline Limitations

1. **Data Freshness**: Bundled database may be weeks/months old
2. **AIP Data**: Only cached entries available
3. **Fuel Info**: May be incomplete
4. **Chatbot Intelligence**: Smaller model, limited reasoning
5. **Geocoding**: No address/city lookup (coordinates only)
6. **Map Tiles**: Only cached regions available

### 7.3 Online Enhancements

1. **Latest Data**: Real-time airport data
2. **Full AIP Access**: Complete AIP entries
3. **Smart Chatbot**: Full GPT-4 powered assistant
4. **Geocoding**: City/address to coordinates
5. **Live Map Tiles**: Current satellite/map imagery
6. **Sync**: Keep local database updated

---

## 8. Data Sync & Cache Policy

### 8.1 Canonical Data Sources

**Core Principle:** The local SQLite database is the **canonical source of truth** for airport data. The API provides a view over the same data, potentially with enrichments, but never with schema conflicts.

| Data Type | Canonical Source | API Role | Conflict Resolution |
|-----------|-----------------|----------|---------------------|
| **Airports** | Local DB | Read-only view | DB wins; API cannot add/modify airports |
| **Runways** | Local DB | Read-only view | DB wins |
| **Procedures** | Local DB | Read-only view | DB wins |
| **AIP Entries** | Local DB | Enrichment source | API may provide newer entries; merge by timestamp |
| **Country Rules** | Local DB (bundled JSON) | Read-only view | DB wins |
| **GA Friendliness** | Local DB | Computed on server | Re-compute locally from DB or accept API values |
| **User Preferences** | App (UserDefaults/SwiftData) | N/A | Local only |

**Why DB is canonical:**
- `KnownAirports` and RZFlight are built around SQLite
- Offline-first requires local data to be authoritative
- Spatial indexing (KDTree) is built from local DB
- API is just a REST wrapper over the same database

### 8.2 Database Versioning

```
┌─────────────────────────────────────────────────────────────────┐
│                    Database Version Hierarchy                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   BUNDLED DB (v1.0)          App ships with this                │
│        │                     Location: Bundle.main              │
│        │                     Read-only                          │
│        ▼                                                        │
│   ACTIVE DB (v1.2)           Copied to Documents on first run   │
│        │                     Location: Documents/airports.db    │
│        │                     Writable, replaced on sync         │
│        ▼                                                        │
│   SERVER DB (v1.3)           Source for updates                 │
│                              Downloaded as full replacement     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Version Format:** `YYYYMMDD.N` (e.g., `20250115.1`)
- Date component: when DB was generated
- Sequence component: multiple builds per day

**Version Storage:**
```swift
struct DatabaseVersion: Codable, Comparable {
    let date: Date        // 2025-01-15
    let sequence: Int     // 1
    let schemaVersion: Int // 3 (for migrations)
    
    var versionString: String { /* "20250115.1" */ }
    
    static func < (lhs: Self, rhs: Self) -> Bool {
        (lhs.date, lhs.sequence) < (rhs.date, rhs.sequence)
    }
}

// Stored in DB metadata table and UserDefaults
// SELECT value FROM metadata WHERE key = 'db_version'
```

### 8.3 Sync Strategy

**Update Policy:** Full database replacement (no delta/patch)

**Rationale:**
- Database is ~20-50MB compressed - acceptable for periodic download
- Delta patching is complex and error-prone with SQLite
- Full replacement guarantees consistency
- KDTree re-indexes automatically on `KnownAirports` init

**Sync Triggers:**
1. **App launch** (if last sync > 7 days ago)
2. **Background refresh** (weekly, iOS BackgroundTasks)
3. **User-initiated** (pull-to-refresh or settings)
4. **API returns newer version** (opportunistic check)

**Sync Flow:**
```swift
final class SyncService {
    private let bundledVersion: DatabaseVersion
    private var activeVersion: DatabaseVersion
    
    func syncIfNeeded() async throws {
        // 1. Check server version
        let serverVersion = try await api.getDatabaseVersion()
        
        guard serverVersion > activeVersion else {
            return // Already up to date
        }
        
        // 2. Download new DB to temp location
        let tempURL = try await api.downloadDatabase(version: serverVersion)
        
        // 3. Validate downloaded DB
        guard try validateDatabase(at: tempURL) else {
            throw SyncError.validationFailed
        }
        
        // 4. Atomic replacement
        try replaceActiveDatabase(with: tempURL, version: serverVersion)
        
        // 5. Notify app to reload KnownAirports
        NotificationCenter.default.post(name: .databaseUpdated, object: nil)
    }
    
    private func replaceActiveDatabase(with newDB: URL, version: DatabaseVersion) throws {
        let activeURL = documentsURL.appending(path: "airports.db")
        let backupURL = documentsURL.appending(path: "airports.db.backup")
        
        // Backup current (in case rollback needed)
        try? FileManager.default.removeItem(at: backupURL)
        try? FileManager.default.copyItem(at: activeURL, to: backupURL)
        
        // Replace atomically
        _ = try FileManager.default.replaceItemAt(activeURL, withItemAt: newDB)
        
        // Update version
        activeVersion = version
        UserDefaults.standard.set(version.versionString, forKey: "activeDBVersion")
    }
}
```

### 8.4 API Data Handling

**When Online:**
- API responses are converted to RZFlight models (via adapters)
- **Do NOT write API data back to local DB** (avoids conflicts)
- API data is used for display only, not persisted
- Exception: AIP entries may be cached (see below)

**AIP Entry Caching:**
```swift
/// AIP entries from API can be cached for offline access
/// These supplement (not replace) DB entries
final class AIPCache {
    private let store: SwiftData.ModelContainer
    
    /// Cache API-fetched AIP entries
    /// Keyed by airport ICAO + fetch timestamp
    func cache(entries: [AIPEntry], for icao: String) {
        let cached = CachedAIPEntries(
            icao: icao,
            entries: entries,
            fetchedAt: Date(),
            source: .api
        )
        store.insert(cached)
    }
    
    /// Get entries: prefer fresh API cache, fall back to DB
    func entries(for icao: String, maxAge: TimeInterval = 86400) -> [AIPEntry] {
        // Check cache first (if fresh enough)
        if let cached = getCached(icao: icao), 
           cached.fetchedAt.timeIntervalSinceNow > -maxAge {
            return cached.entries
        }
        // Fall back to DB
        return knownAirports.airport(icao: icao)?.aipEntries ?? []
    }
}
```

### 8.5 Schema Migration

**When schema changes:**

1. **Increment `schemaVersion`** in `DatabaseVersion`
2. **Server generates new DB** with updated schema
3. **App checks schema compatibility** before replacing:

```swift
func validateDatabase(at url: URL) throws -> Bool {
    let db = FMDatabase(path: url.path)
    guard db.open() else { return false }
    defer { db.close() }
    
    // Check required tables exist
    let requiredTables = ["airports", "runways", "procedures", "aip"]
    for table in requiredTables {
        guard db.tableExists(table) else { return false }
    }
    
    // Check schema version is compatible
    let serverSchema = db.intForQuery("SELECT value FROM metadata WHERE key = 'schema_version'")
    guard serverSchema >= minSupportedSchema && serverSchema <= maxSupportedSchema else {
        // Incompatible schema - need app update
        throw SyncError.incompatibleSchema(server: serverSchema, app: currentSchemaVersion)
    }
    
    return true
}
```

**Schema Compatibility Matrix:**

| App Version | Min Schema | Max Schema | Notes |
|-------------|------------|------------|-------|
| 1.0.x | 1 | 1 | Initial release |
| 1.1.x | 1 | 2 | Added GA friendliness columns |
| 2.0.x | 2 | 3 | Breaking: new AIP structure |

### 8.6 Failure Handling

| Failure | Behavior |
|---------|----------|
| Download fails | Keep current DB, retry later, show banner |
| Validation fails | Keep current DB, log error, don't retry same version |
| Replacement fails | Restore from backup, log error |
| Incompatible schema | Keep current DB, prompt user to update app |
| No network | Use bundled/active DB, no sync attempt |

### 8.7 Storage Locations

```
App Bundle (read-only):
└── airports.db              # Bundled DB (fallback)

Documents (writable):
├── airports.db              # Active DB (synced)
├── airports.db.backup       # Backup during sync
└── db_version.json          # Version metadata

Caches (purgeable):
├── aip_cache/               # Cached AIP entries from API
├── map_tiles/               # Offline map tiles
└── api_cache/               # HTTP response cache
```

**Cleanup Policy:**
- `Caches/` can be purged by iOS at any time
- App should handle missing cache gracefully
- `Documents/airports.db` is backed up to iCloud (user data)

---

## 9. Implementation Phases

### Phase 1: Foundation (2-3 weeks)
- [ ] Repository pattern with offline/online sources
- [ ] Verify RZFlight integration (no duplicate models)
- [ ] Connectivity monitoring
- [ ] FilterConfig with apply() using RZFlight extensions

### Phase 2: AppState with Composed Domains (2 weeks)
- [ ] `AirportDomain` - airports, filters, map state
- [ ] `ChatDomain` - messages, streaming
- [ ] `NavigationDomain` - tabs, sheets, path
- [ ] `SystemDomain` - connectivity, errors
- [ ] `AppState` - thin orchestration, cross-domain wiring

### Phase 3: UI Implementation (2-3 weeks)
- [ ] Adaptive layouts (iPhone/iPad/Mac)
- [ ] Filter panel connected to AirportDomain
- [ ] Airport detail view
- [ ] Search with route detection
- [ ] Legend modes

### Phase 4: Online Integration (2 weeks)
- [ ] API client implementation
- [ ] Remote data source with RZFlight adapters
- [ ] Sync service
- [ ] Cache management
- [ ] Error handling & fallbacks

### Phase 5: Chatbot - Online (2-3 weeks)
- [ ] SSE streaming client
- [ ] Wire ChatDomain to chatbot service
- [ ] Chat UI (messages, streaming, thinking)
- [ ] Visualization handling via cross-domain callback
- [ ] Filter profile application

### Phase 6: Chatbot - Offline Fallback (1-2 weeks)
- [ ] ToolCatalog (shared with server)
- [ ] KeywordFallbackBackend (pattern matching)
- [ ] ToolExecutor (local tool execution)
- [ ] LLMBackend protocol (abstraction for future)
- [ ] Template-based responses
- [ ] Clear "Limited offline mode" UX

### Phase 7: Polish & Testing (2 weeks)
- [ ] Performance optimization
- [ ] Offline map tile caching
- [ ] Error handling refinement
- [ ] UI polish and animations
- [ ] Testing on all platforms
- [ ] Unit tests for each domain in isolation

---

## 10. Dependencies & Platform Requirements

### Platform Requirements

| Platform | Version | Rationale |
|----------|---------|-----------|
| **iOS** | 18.0+ | `@Observable`, SwiftData, Apple Intelligence |
| **iPadOS** | 18.0+ | Same as iOS |
| **macOS** | 15.0+ | Sequoia, native SwiftUI |
| **Xcode** | 16.0+ | Swift 6, new concurrency |

### Swift Package Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| **RZFlight** | Airport models, KnownAirports, spatial queries | ✅ |
| **RZUtilsSwift** | Logging, utilities | ✅ |
| **FMDB** | SQLite access (via RZFlight) | ✅ |

### Apple Frameworks Used

| Framework | Purpose | iOS Version |
|-----------|---------|-------------|
| **SwiftUI** | UI framework | 18.0+ |
| **Observation** | `@Observable` macro | 17.0+ |
| **SwiftData** | Caching, persistence | 17.0+ |
| **MapKit** | Map visualization | 18.0+ (new APIs) |
| **Foundation** | Networking, async/await | 15.0+ |
| **Apple Intelligence** | Offline chatbot | 18.1+ (device-dependent) |

### No External Dependencies Needed

Using latest Apple frameworks eliminates need for:
- ❌ Combine (replaced by `@Observable`)
- ❌ Alamofire (native `URLSession` async/await)
- ❌ Kingfisher (native `AsyncImage`)
- ❌ Core ML custom models (Apple Intelligence)

### Optional Development Tools

- **SwiftLint** - Code style
- **Swift Testing** - New testing framework (Xcode 16)

---

## 11. Open Questions

### Resolved ✅

| Question | Decision |
|----------|----------|
| Platform version | iOS 18.0+ / macOS 15.0+ (latest only) |
| State management | Single `AppState` composed of domain objects |
| God-class risk | Avoided via composed domains (~200-400 lines each) |
| On-device LLM | **POST-1.0** - abstraction ready, keyword fallback for 1.0 |
| LLM backend | Swappable via `LLMBackend` protocol (Apple Intelligence / llama.cpp / MLX) |
| Tool catalog | Shared between online/offline to avoid grammar drift |
| ViewModels | Eliminated - use domain objects via `@Environment` |
| Cross-domain sync | Explicit callbacks (e.g., `chat.onVisualization`) |
| DB canonical | Local SQLite is source of truth; API is read-only view |

### Remaining Questions

1. **Map tiles offline caching**:
   - Pre-cache Europe on first launch? (large download)
   - Cache as user browses? (gradual)
   - User-selected regions? (manual)
   - **Recommendation:** Cache as user browses + option to pre-download

2. **Database updates**:
   - Full download vs incremental deltas?
   - Update frequency?
   - **Recommendation:** Weekly delta sync, monthly full refresh

3. **Apple Intelligence availability**:
   - Not available on all devices
   - What's the fallback UX?
   - **Recommendation:** Show "Offline mode limited" banner, use keyword matching

4. **visionOS support**:
   - Should we plan for spatial computing?
   - **Recommendation:** Keep architecture compatible, defer implementation

---

## 12. RZFlight Enhancement Proposals

When functionality exists in `euro_aip` (Python) but not in RZFlight (Swift), propose enhancements to RZFlight rather than implementing in the app. Track proposals here:

### 12.1 Proposed Enhancements

| Enhancement | euro_aip Reference | Priority | Status |
|-------------|-------------------|----------|--------|
| **API-friendly initializers** | For API → RZFlight conversion | **Critical** | Proposed |
| **Fuel filtering** | `has_avgas`, `has_jet_a` fields | High | Proposed |
| **Landing fee filtering** | `max_landing_fee` filter | Medium | Proposed |
| **Country list query** | `get_available_countries()` | High | Proposed |
| **Filter config object** | `FilterConfig` class | Medium | Proposed |
| **AIP value search** | `filter_by_aip_field()` | Medium | Proposed |

### 12.2 How to Propose

1. **Check euro_aip**: Review the Python implementation in `src/euro-aip/euro_aip/`
2. **Design Swift API**: Follow existing RZFlight patterns
3. **Update RZFlight**: Submit changes to [roznet/rzflight](https://github.com/roznet/rzflight)
4. **Update app**: Use new functionality once available

### 12.3 Example Enhancement: API-Friendly Initializers (Critical)

Currently RZFlight models are designed for database loading (`FMResultSet`). For API responses, we need memberwise initializers:

```swift
// Proposed addition to RZFlight.Airport
extension Airport {
    /// Initialize from API-style data
    public init(
        icao: String,
        name: String,
        city: String = "",
        country: String = "",
        latitude: Double,
        longitude: Double,
        elevation_ft: Int = 0,
        type: AirportType = .none,
        continent: Continent = .none,
        isoRegion: String? = nil,
        iataCode: String? = nil,
        runways: [Runway] = [],
        procedures: [Procedure] = [],
        aipEntries: [AIPEntry] = []
    ) {
        self.icao = icao
        self.name = name
        self.city = city
        self.country = country
        self.latitude = latitude
        self.longitude = longitude
        self.elevation_ft = elevation_ft
        self.type = type
        self.continent = continent
        self.isoRegion = isoRegion
        self.iataCode = iataCode
        self.runways = runways
        self.procedures = procedures
        self.aipEntries = aipEntries
        // ... set remaining properties to defaults
    }
}

// Proposed addition to RZFlight.Runway
extension Runway {
    public init(
        length_ft: Int,
        width_ft: Int = 0,
        surface: String = "",
        lighted: Bool = false,
        closed: Bool = false,
        le: RunwayEnd,
        he: RunwayEnd
    ) {
        self.length_ft = length_ft
        self.width_ft = width_ft
        self.surface = surface
        self.lighted = lighted
        self.closed = closed
        self.le = le
        self.he = he
    }
}
```

### 12.4 Example Enhancement: Fuel Filtering

```swift
// Proposed addition to KnownAirports
extension KnownAirports {
    /// Get airports with AVGAS fuel available
    func airportsWithAvgas() -> [Airport] {
        // Query airports where AIP entry indicates AVGAS
        // Similar to Python: filter_by_aip_field("fuel_types", "AVGAS")
    }
    
    /// Get airports with Jet-A fuel available
    func airportsWithJetA() -> [Airport] {
        // Query airports where AIP entry indicates Jet-A
    }
}

// Proposed addition to Array<Airport> extension
extension Array where Element == Airport {
    func withAvgas() -> [Airport] {
        return self.filter { airport in
            airport.aipEntries.contains { $0.effectiveFieldName == "fuel_types" && $0.effectiveValue.contains("AVGAS") }
        }
    }
}
```

---

## Appendix A: API Endpoints

```
GET  /api/airports?country=&limit=&...     List airports with filters
GET  /api/airports/{icao}                   Airport detail
GET  /api/airports/{icao}/procedures        Airport procedures
GET  /api/airports/{icao}/runways           Airport runways
GET  /api/airports/{icao}/aip-entries       AIP entries
GET  /api/airports/search/{query}           Search airports
POST /api/airports/route                    Route search
POST /api/airports/locate                   Location search
GET  /api/filters/all                       Filter metadata
GET  /api/rules/{country}                   Country rules
POST /api/aviation-agent/chat/stream        Chatbot (SSE)
GET  /api/sync/version                      Database version
GET  /api/sync/delta?from={version}         Delta update
```

---

## Appendix B: Related Documents

- `designs/UI_FILTER_STATE_DESIGN.md` - Web state management
- `designs/CHATBOT_WEBUI_DESIGN.md` - Chatbot architecture
- `designs/GA_FRIENDLINESS_DESIGN.md` - GA friendliness features


