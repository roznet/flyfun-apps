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
- File-based JSON caching (simple, no SwiftData)
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
│  │Connectivity│ │ SyncService │ │  File Cache  │ │Preferences │ │
│  │  Monitor   │ │             │ │  (JSON)      │ │            │ │
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
| File Cache | JSON-based AIP caching |
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
import MapKit

/// Protocol for airport data access - abstracts offline/online sources
/// All methods return RZFlight types directly
/// 
/// IMPORTANT: Filtering is done HERE, not in FilterConfig.
/// This keeps FilterConfig pure (no DB dependencies).
protocol AirportRepositoryProtocol: Sendable {
    // MARK: - Region-Based Queries (for map performance)
    
    /// Get airports within a bounding box - PRIMARY method for map display
    /// This is the key to map performance: only load what's visible
    func airportsInRegion(
        boundingBox: BoundingBox,
        filters: FilterConfig,
        limit: Int
    ) async throws -> [Airport]
    
    // MARK: - General Queries
    
    /// Get airports matching filters (no region constraint)
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [Airport]
    
    /// Search airports by query string
    func searchAirports(query: String, limit: Int) async throws -> [Airport]
    
    /// Get airport with extended data (runways, procedures, AIP entries)
    func airportDetail(icao: String) async throws -> Airport?
    
    // MARK: - Route & Location
    func airportsNearRoute(from: String, to: String, distanceNm: Int, filters: FilterConfig) async throws -> RouteResult
    func airportsNearLocation(center: CLLocationCoordinate2D, radiusNm: Int, filters: FilterConfig) async throws -> [Airport]
    
    // MARK: - In-Memory Filtering (for already-loaded airports)
    /// Apply cheap in-memory filters only (no DB access)
    func applyInMemoryFilters(_ filters: FilterConfig, to airports: [Airport]) -> [Airport]
    
    // MARK: - Metadata
    func availableCountries() async throws -> [String]
    
    /// Get set of ICAOs that are border crossing points
    func borderCrossingICAOs() async throws -> Set<String>
}

// MARK: - Bounding Box for Region Queries

/// Geographic bounding box for region-based queries
struct BoundingBox: Sendable, Equatable {
    /// Southwest corner (minimum latitude and longitude)
    let minCoord: CLLocationCoordinate2D
    /// Northeast corner (maximum latitude and longitude)
    let maxCoord: CLLocationCoordinate2D
    
    // MARK: - Convenience Accessors
    
    var minLatitude: Double { minCoord.latitude }
    var maxLatitude: Double { maxCoord.latitude }
    var minLongitude: Double { minCoord.longitude }
    var maxLongitude: Double { maxCoord.longitude }
    
    // MARK: - Initializers
    
    init(minCoord: CLLocationCoordinate2D, maxCoord: CLLocationCoordinate2D) {
        self.minCoord = minCoord
        self.maxCoord = maxCoord
    }
    
    init(minLatitude: Double, maxLatitude: Double, minLongitude: Double, maxLongitude: Double) {
        self.minCoord = CLLocationCoordinate2D(latitude: minLatitude, longitude: minLongitude)
        self.maxCoord = CLLocationCoordinate2D(latitude: maxLatitude, longitude: maxLongitude)
    }
    
    // MARK: - Queries
    
    /// Check if a coordinate is within this bounding box
    func contains(_ coordinate: CLLocationCoordinate2D) -> Bool {
        coordinate.latitude >= minLatitude &&
        coordinate.latitude <= maxLatitude &&
        coordinate.longitude >= minLongitude &&
        coordinate.longitude <= maxLongitude
    }
    
    /// Check if an airport is within this bounding box
    func contains(_ airport: RZFlight.Airport) -> Bool {
        contains(airport.coord)
    }
}

extension MKCoordinateRegion {
    /// Convert region to bounding box
    var boundingBox: BoundingBox {
        BoundingBox(
            minCoord: CLLocationCoordinate2D(
                latitude: center.latitude - span.latitudeDelta / 2,
                longitude: center.longitude - span.longitudeDelta / 2
            ),
            maxCoord: CLLocationCoordinate2D(
                latitude: center.latitude + span.latitudeDelta / 2,
                longitude: center.longitude + span.longitudeDelta / 2
            )
        )
    }
    
    /// Expand region by a factor (for prefetching beyond visible area)
    func paddedBy(factor: Double) -> MKCoordinateRegion {
        MKCoordinateRegion(
            center: center,
            span: MKCoordinateSpan(
                latitudeDelta: span.latitudeDelta * factor,
                longitudeDelta: span.longitudeDelta * factor
            )
        )
    }
    
    /// Default Europe region
    static let europe = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 50.0, longitude: 10.0),
        span: MKCoordinateSpan(latitudeDelta: 30, longitudeDelta: 40)
    )
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
    
    // MARK: - Region-Based Query (Primary for Map Performance)
    
    func airportsInRegion(
        boundingBox: BoundingBox,
        filters: FilterConfig,
        limit: Int
    ) async throws -> [Airport] {
        // Use KDTree spatial query for efficient bounding box lookup
        // KnownAirports uses KDTree internally for spatial indexing
        let regionAirports = knownAirports.known.values.filter { airport in
            boundingBox.contains(airport.coord)
        }
        
        // Apply DB-dependent filters first (if any)
        var filtered: [Airport]
        if filters.pointOfEntry == true {
            // Intersection: in region AND is border crossing
            let borderCrossings = Set(knownAirports.airportsWithBorderCrossing().map(\.icao))
            filtered = regionAirports.filter { borderCrossings.contains($0.icao) }
        } else {
            filtered = Array(regionAirports)
        }
        
        // Apply in-memory filters
        filtered = applyInMemoryFilters(filters, to: filtered)
        
        return Array(filtered.prefix(limit))
    }
    
    // MARK: - General Queries
    
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
        
        // Apply cheap in-memory filters
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
    
    func airportsNearLocation(center: CLLocationCoordinate2D, radiusNm: Int, filters: FilterConfig) async throws -> [Airport] {
        // Use KnownAirports KDTree-based spatial query
        let nearbyAirports = knownAirports.nearest(coord: center, count: 100)
        
        // Filter by actual distance (KDTree returns approximate nearest, verify with haversine)
        let radiusMeters = Double(radiusNm) * 1852.0
        let filtered = nearbyAirports.filter { airport in
            let distance = center.distance(to: airport.coord)
            return distance <= radiusMeters
        }
        
        // Apply additional filters
        return applyInMemoryFilters(filters, to: filtered)
    }
    
    // MARK: - In-Memory Filtering (No DB Access)
    
    func applyInMemoryFilters(_ filters: FilterConfig, to airports: [Airport]) -> [Airport] {
        var result = airports
        
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
        
        return result
    }
    
    // MARK: - Extended Data
    
    func countryRules(for countryCode: String) async throws -> CountryRules? {
        // Load from bundled rules.json or query DB
        return nil  // TODO: Implement
    }
    
    func availableCountries() async throws -> [String] {
        // Get unique countries from DB
        let countries = Set(knownAirports.known.values.compactMap(\.country))
        return countries.sorted()
    }
    
    func filterMetadata() async throws -> FilterMetadata {
        // Return filter options available in DB
        FilterMetadata()  // TODO: Implement
    }
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
import RZUtilsSwift

// MARK: - Data Source Strategy

/// Strategy for choosing data source based on connectivity
enum DataSourceStrategy: String, Sendable {
    case localOnly      // Always use local (offline mode)
    case remotePreferred  // Try remote first, fallback to local
    case localPreferred   // Try local first, use remote for missing data
}

// MARK: - Unified Repository

/// Main repository that switches between offline/online sources
/// Uses strategy pattern for flexible data source selection
@Observable
@MainActor
final class AirportRepository: AirportRepositoryProtocol {
    // MARK: - State
    private(set) var connectivityMode: ConnectivityMode = .offline
    private(set) var strategy: DataSourceStrategy = .localOnly
    
    // MARK: - Dependencies
    private let localDataSource: LocalAirportDataSource
    private var remoteDataSource: RemoteAirportDataSource?
    private let connectivityMonitor: ConnectivityMonitor
    
    // MARK: - Configuration
    
    /// Base URL for the API (configurable)
    static var apiBaseURL: String = "https://maps.flyfun.aero"
    
    // MARK: - Init
    
    init(localDataSource: LocalAirportDataSource, connectivityMonitor: ConnectivityMonitor) {
        self.localDataSource = localDataSource
        self.connectivityMonitor = connectivityMonitor
    }
    
    // MARK: - Remote Setup
    
    /// Initialize the remote data source (call when online)
    func setupRemoteDataSource() {
        guard remoteDataSource == nil else { return }
        
        do {
            remoteDataSource = try RemoteAirportDataSource(baseURLString: Self.apiBaseURL)
            Logger.app.info("Remote data source initialized")
        } catch {
            Logger.app.error("Failed to initialize remote data source: \(error.localizedDescription)")
        }
    }
    
    /// Update strategy based on connectivity and user preference
    func updateStrategy(preferRemote: Bool = false) {
        switch connectivityMode {
        case .offline:
            strategy = .localOnly
        case .online, .hybrid:
            strategy = preferRemote ? .remotePreferred : .localPreferred
            // Lazily initialize remote data source when we go online
            if strategy != .localOnly {
                setupRemoteDataSource()
            }
        }
        Logger.app.info("Repository strategy: \(strategy.rawValue)")
    }
    
    // MARK: - Connectivity Observation
    
    func startObservingConnectivity() {
        Task {
            for await mode in connectivityMonitor.modeStream {
                self.connectivityMode = mode
                self.updateStrategy()
                Logger.sync.info("Repository connectivity: \(mode.rawValue)")
            }
        }
    }
    
    // MARK: - Active Data Source
    
    /// Get the active data source based on current strategy
    private var activeDataSource: AirportRepositoryProtocol {
        switch strategy {
        case .localOnly, .localPreferred:
            return localDataSource
        case .remotePreferred:
            return remoteDataSource ?? localDataSource
        }
    }
    
    // MARK: - AirportRepositoryProtocol Implementation
    
    // Note: Current implementation uses localDataSource for most queries
    // Remote data source integration is in progress
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
    // MARK: - Geographic Filters
    var country: String?
    
    // MARK: - Feature Filters
    var hasProcedures: Bool?
    var hasHardRunway: Bool?
    var hasLightedRunway: Bool?
    var pointOfEntry: Bool?
    
    // MARK: - Runway Filters
    var minRunwayLengthFt: Int?
    var maxRunwayLengthFt: Int?
    
    // MARK: - Approach Filters
    var hasILS: Bool?
    var hasRNAV: Bool?
    var hasPrecisionApproach: Bool?
    
    // MARK: - AIP Filters
    var aipField: String?
    
    // MARK: - Default
    static let `default` = FilterConfig()
    
    // MARK: - Computed Properties
    
    /// Returns true if any filter is active
    var hasActiveFilters: Bool {
        country != nil ||
        hasProcedures == true ||
        hasHardRunway == true ||
        hasLightedRunway == true ||
        pointOfEntry == true ||
        minRunwayLengthFt != nil ||
        maxRunwayLengthFt != nil ||
        hasILS == true ||
        hasRNAV == true ||
        hasPrecisionApproach == true ||
        aipField != nil
    }
    
    /// Count of active filters
    var activeFilterCount: Int {
        var count = 0
        if country != nil { count += 1 }
        if hasProcedures == true { count += 1 }
        if hasHardRunway == true { count += 1 }
        if hasLightedRunway == true { count += 1 }
        if pointOfEntry == true { count += 1 }
        if minRunwayLengthFt != nil { count += 1 }
        if maxRunwayLengthFt != nil { count += 1 }
        if hasILS == true { count += 1 }
        if hasRNAV == true { count += 1 }
        if hasPrecisionApproach == true { count += 1 }
        if aipField != nil { count += 1 }
        return count
    }
    
    /// Human-readable description of active filters
    var description: String {
        var parts: [String] = []
        if let country = country { parts.append("Country: \(country)") }
        if hasProcedures == true { parts.append("Has procedures") }
        if hasHardRunway == true { parts.append("Hard runway") }
        if hasLightedRunway == true { parts.append("Lighted runway") }
        if pointOfEntry == true { parts.append("Border crossing") }
        if let min = minRunwayLengthFt { parts.append("Runway ≥ \(min)ft") }
        if let max = maxRunwayLengthFt { parts.append("Runway ≤ \(max)ft") }
        if hasILS == true { parts.append("Has ILS") }
        if hasRNAV == true { parts.append("Has RNAV") }
        if hasPrecisionApproach == true { parts.append("Precision approach") }
        if let field = aipField { parts.append("AIP field: \(field)") }
        return parts.isEmpty ? "No filters" : parts.joined(separator: ", ")
    }
    
    // MARK: - Mutating Helpers
    
    /// Reset all filters to defaults
    mutating func reset() {
        self = .default
    }
    
    // NOTE: No apply(to:db:) method!
    // Filtering is done by the repository, not by FilterConfig.
    // This keeps FilterConfig pure and free of storage dependencies.
}

/// App-specific: Map visualization highlight
struct MapHighlight: Identifiable, Sendable, Equatable {
    let id: String
    let coordinate: CLLocationCoordinate2D
    let color: HighlightColor
    let radius: Double  // meters
    let popup: String?
    
    enum HighlightColor: String, Sendable, Equatable {
        case blue, red, green, orange, purple
    }
    
    static func == (lhs: MapHighlight, rhs: MapHighlight) -> Bool {
        lhs.id == rhs.id
    }
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
/// Protocol for chatbot services (online/offline)
protocol ChatbotService: Sendable {
    /// Send a message and stream the response
    func sendMessage(
        _ message: String,
        history: [ChatMessage]
    ) -> AsyncThrowingStream<ChatEvent, Error>
    
    /// Check if the service is available
    func isAvailable() async -> Bool
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
/// SSE events from the aviation agent streaming API
enum ChatEvent: Sendable {
    /// Planner selected a tool
    case plan(PlanData)
    
    /// Planning reasoning/thinking
    case thinking(content: String)
    
    /// Tool execution starting
    case toolCallStart(name: String, arguments: [String: Any])
    
    /// Tool execution completed
    case toolCallEnd(name: String, result: ToolResult)
    
    /// Streaming message content (character by character)
    case message(content: String)
    
    /// Thinking phase complete
    case thinkingDone
    
    /// Visualization data for the map
    case uiPayload(ChatVisualizationPayload)
    
    /// Final answer with complete state
    case finalAnswer(state: [String: Any])
    
    /// Stream complete
    case done(sessionId: String?, tokens: TokenUsage?)
    
    /// Error occurred
    case error(message: String)
    
    /// Unknown event type
    case unknown(event: String, data: String)
}

/// Visualization payload from chatbot API - instructs map what to display
/// Note: This is different from the internal VisualizationPayload in AirportDomain
struct ChatVisualizationPayload: Sendable {
    /// Kind of visualization (airport, route, list, etc.)
    let kind: Kind
    
    /// Visualization data (markers, routes, highlights)
    let visualization: VisualizationData?
    
    /// Filter configuration suggested by the chatbot
    let filters: ChatFilters?
    
    /// List of airport ICAOs to highlight
    let airports: [String]?
    
    /// Raw data from API
    let raw: [String: Any]
    
    enum Kind: String, Sendable {
        case airport
        case route
        case list
        case search
        case unknown
    }
    
    init(from dict: [String: Any]) {
        // Parses from API response dictionary
        // See implementation for full parsing logic
    }
}

/// Internal visualization payload (for programmatic use in AirportDomain)
struct VisualizationPayload: Sendable {
    enum Kind: Sendable {
        case markers
        case routeWithMarkers
        case markerWithDetails
        case regionFocus
    }
    
    let kind: Kind
    let airports: [RZFlight.Airport]
    let route: RouteVisualization?
    let point: CLLocationCoordinate2D?
    let filterProfile: FilterConfig?
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
    /// Exposed for views that need to call repository methods directly (e.g., CountryPicker)
    let repository: AirportRepositoryProtocol
    
    // MARK: - Airport Data (already filtered by repository)
    var airports: [RZFlight.Airport] = []
    var selectedAirport: RZFlight.Airport?
    var searchResults: [RZFlight.Airport] = []
    var isSearching: Bool = false
    
    // MARK: - Filters (pure data, no DB logic)
    var filters: FilterConfig = .default
    
    // MARK: - Map State
    var mapPosition: MapCameraPosition = .region(.europe)
    var visibleRegion: MKCoordinateRegion?
    var legendMode: LegendMode = .airportType
    var highlights: [String: MapHighlight] = [:]
    var activeRoute: RouteVisualization?
    
    // MARK: - Procedure Lines
    /// Procedure lines for visualization (keyed by airport ICAO)
    var procedureLines: [String: [RZFlight.Airport.ProcedureLine]] = [:]
    private var procedureLinesLoadingTask: Task<Void, Never>?
    
    // MARK: - Cached Lookups (for legend coloring)
    /// Set of ICAOs that are border crossing points - loaded once at startup
    var borderCrossingICAOs: Set<String> = []
    
    // MARK: - Region Loading
    private var regionUpdateTask: Task<Void, Never>?
    
    // MARK: - Search State
    /// Track when search results are active to prevent region-based loading from overwriting them
    var isSearchActive: Bool = false
    
    // MARK: - Init
    
    init(repository: AirportRepositoryProtocol) {
        self.repository = repository
    }
    
    // MARK: - Region-Based Loading
    
    /// Called when map region changes - loads airports for visible area
    /// Uses debouncing to avoid excessive queries during pan/zoom
    /// Respects search state: won't overwrite search results unless search is cleared
    func onRegionChange(_ region: MKCoordinateRegion) {
        // Don't load if search is active - preserve search results
        guard !isSearchActive else {
            return
        }
        
        regionUpdateTask?.cancel()
        regionUpdateTask = Task {
            // Debounce: wait 300ms after last region change
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            
            visibleRegion = region
            try? await loadAirportsInRegion(region)
        }
    }
    
    /// Load airports within the visible map region
    private func loadAirportsInRegion(_ region: MKCoordinateRegion) async throws {
        // Calculate bounding box with some padding for smooth panning
        let paddedRegion = region.paddedBy(factor: 1.3)
        
        airports = try await repository.airportsInRegion(
            boundingBox: paddedRegion.boundingBox,
            filters: filters,
            limit: 500  // Cap markers for performance
        )
        Logger.app.info("Loaded \(self.airports.count) airports in region")
        
        // Load procedure lines if in procedure legend mode
        if legendMode == .procedures {
            await loadProcedureLines()
        }
    }
    
    /// Initial load - loads airports for default Europe view
    func load() async throws {
        // Load border crossing ICAOs for legend coloring
        borderCrossingICAOs = try await repository.borderCrossingICAOs()
        Logger.app.info("Loaded \(self.borderCrossingICAOs.count) border crossing ICAOs")
        
        let defaultRegion = MKCoordinateRegion.europe
        visibleRegion = defaultRegion
        try await loadAirportsInRegion(defaultRegion)
    }
    
    /// Check if an airport is a border crossing (uses cached set)
    func isBorderCrossing(_ airport: RZFlight.Airport) -> Bool {
        borderCrossingICAOs.contains(airport.icao)
    }
    
    func search(query: String) async throws {
        guard !query.isEmpty else {
            searchResults = []
            isSearchActive = false
            // Clear search state - allow region loading to resume
            if visibleRegion != nil {
                try? await loadAirportsInRegion(visibleRegion!)
            }
            return
        }
        
        isSearching = true
        defer { isSearching = false }
        
        // Check if it's a route query (e.g., "EGTF LFMD")
        if isRouteQuery(query) {
            try await searchRoute(query)
        } else {
            // Regular search - clear route state and set search active to preserve results
            activeRoute = nil
            highlights = highlights.filter { !$0.key.hasPrefix("route-") }
            isSearchActive = true
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
    
    /// Apply visualization from chatbot (ChatVisualizationPayload from API)
    func applyVisualization(_ chatPayload: ChatVisualizationPayload) {
        Logger.app.info("Applying chat visualization: \(chatPayload.kind.rawValue)")
        
        // Clear previous chat highlights
        clearChatHighlights()
        
        // Apply filters if provided
        if let chatFilters = chatPayload.filters {
            filters = chatFilters.toFilterConfig()
        }
        
        // Apply visualization data
        if let viz = chatPayload.visualization {
            // Handle markers, routes, center point, etc.
            // (See implementation for full details)
        }
        
        // Handle airports list (for highlighting)
        if let airportICAOs = chatPayload.airports {
            for icao in airportICAOs {
                // Add highlights for each airport
            }
        }
    }
    
    /// Apply internal visualization payload (for programmatic use)
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
/// Domain: Chat messages and streaming state
/// This is a composed part of AppState, not a standalone ViewModel.
@Observable
@MainActor
final class ChatDomain {
    // MARK: - State
    var messages: [ChatMessage] = []
    var input: String = ""
    var isStreaming: Bool = false
    var currentThinking: String?
    var currentToolCall: String?
    var error: String?
    
    /// Tools used during current streaming session
    private var toolsUsed: [String] = []
    
    // MARK: - Cross-Domain Callback
    /// Called when chat produces a visualization payload
    /// AppState wires this to AirportDomain.applyVisualization
    /// Note: Uses ChatVisualizationPayload (from API), not internal VisualizationPayload
    var onVisualization: ((ChatVisualizationPayload) -> Void)?
    
    // MARK: - Dependencies
    private var chatbotService: ChatbotService?
    
    // MARK: - Init
    
    init() {}
    
    /// Initialize with a chatbot service
    func configure(service: ChatbotService) {
        self.chatbotService = service
    }
    
    // MARK: - Actions
    
    /// Send a message to the chatbot
    func send() async {
        let userMessage = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !userMessage.isEmpty else { return }
        
        // Check if service is available
        guard let service = chatbotService else {
            Logger.app.warning("Chatbot service not configured")
            addOfflineResponse(for: userMessage)
            return
        }
        
        // Add user message
        messages.append(ChatMessage(role: .user, content: userMessage))
        input = ""
        error = nil
        
        isStreaming = true
        currentThinking = nil
        currentToolCall = nil
        toolsUsed = []  // Reset tools for new message
        
        do {
            // Stream response from service
            var accumulatedContent = ""
            
            for try await event in service.sendMessage(userMessage, history: messages.dropLast()) {
                await handleEvent(event, accumulatedContent: &accumulatedContent)
            }
            
            // Ensure we have a final message
            if !accumulatedContent.isEmpty {
                finishStreaming()
            }
            
        } catch {
            Logger.app.error("Chat error: \(error.localizedDescription)")
            self.error = error.localizedDescription
            messages.append(ChatMessage(
                role: .assistant,
                content: "Sorry, I encountered an error: \(error.localizedDescription)"
            ))
        }
        
        isStreaming = false
        currentThinking = nil
        currentToolCall = nil
    }
    
    /// Handle a streaming event
    private func handleEvent(_ event: ChatEvent, accumulatedContent: inout String) async {
        switch event {
        case .thinking(let content):
            currentThinking = content
        case .thinkingDone:
            currentThinking = nil
        case .toolCallStart(let name, _):
            currentToolCall = name
            if !toolsUsed.contains(name) {
                toolsUsed.append(name)
            }
        case .toolCallEnd(let name, _):
            if currentToolCall == name {
                currentToolCall = nil
            }
        case .message(let content):
            accumulatedContent += content
            updateLastAssistantMessage(accumulatedContent)
        case .uiPayload(let payload):
            onVisualization?(payload)  // Notify AppState
        case .done:
            break
        case .error(let message):
            error = message
        case .unknown:
            break
        }
    }
    
    /// Clear chat history
    func clear() {
        messages = []
        currentThinking = nil
        currentToolCall = nil
        error = nil
    }
    
    /// Update the last assistant message (for streaming)
    func updateLastAssistantMessage(_ content: String) {
        guard let lastIndex = messages.lastIndex(where: { $0.role == .assistant }) else {
            messages.append(ChatMessage(role: .assistant, content: content, isStreaming: true))
            return
        }
        messages[lastIndex] = ChatMessage(
            role: .assistant,
            content: content,
            isStreaming: true
        )
    }
    
    /// Finish streaming for the last message
    func finishStreaming() {
        guard let lastIndex = messages.lastIndex(where: { $0.role == .assistant }) else { return }
        let message = messages[lastIndex]
        messages[lastIndex] = ChatMessage(
            role: message.role,
            content: message.content,
            isStreaming: false,
            toolsUsed: toolsUsed
        )
        isStreaming = false
    }
}
```

**Note on Visualization Payloads:**
- `ChatVisualizationPayload`: From API responses (SSE `ui_payload` events), parsed from JSON
- `VisualizationPayload`: Internal type in `AirportDomain` for programmatic map updates
- `ChatDomain` uses `ChatVisualizationPayload` and passes it to `AirportDomain.applyVisualization(_:)` which converts it appropriately

#### NavigationDomain

```swift
/// Domain: Navigation state, tabs, sheets, overlays
@Observable
@MainActor
final class NavigationDomain {
    // MARK: - Tab State
    var selectedTab: Tab = .map
    
    // MARK: - Left Overlay Mode
    /// Controls what's shown in the left overlay (search/filter or chat)
    var leftOverlayMode: LeftOverlayMode = .search
    /// Whether the left overlay panel is visible (for iPad/Mac - slides in from left)
    var showingLeftOverlay: Bool = false
    
    // MARK: - Bottom Tab State
    /// Selected bottom tab (Airport Info, AIP, Rules)
    var selectedBottomTab: BottomTab = .airportInfo
    /// Whether the bottom tab bar is visible (can be hidden even when airport is selected)
    var showingBottomTabBar: Bool = false
    
    // MARK: - Sheet State
    var showingChat: Bool = false
    var showingSearchSheet: Bool = false
    var showingFilters: Bool = false
    var showingSettings: Bool = false
    var showingAirportDetail: Bool = false
    
    // MARK: - Navigation Path (for programmatic navigation)
    var path = NavigationPath()
    
    // MARK: - Types
    
    enum Tab: String, CaseIterable, Identifiable, Sendable {
        case map = "Map"
        case search = "Search"
        case chat = "Chat"
        case settings = "Settings"
        
        var id: String { rawValue }
        
        var systemImage: String {
            switch self {
            case .map: return "map"
            case .search: return "magnifyingglass"
            case .chat: return "bubble.left.and.bubble.right"
            case .settings: return "gear"
            }
        }
    }
    
    enum LeftOverlayMode: String, Sendable {
        case search
        case chat
        case filters
    }
    
    enum BottomTab: String, CaseIterable, Identifiable, Sendable {
        case airportInfo = "Airport"
        case aip = "AIP"
        case rules = "Rules"
        
        var id: String { rawValue }
        
        var systemImage: String {
            switch self {
            case .airportInfo: return "airplane"
            case .aip: return "doc.text"
            case .rules: return "book"
            }
        }
        
        var displayName: String {
            rawValue
        }
    }
    
    // MARK: - Actions
    
    func navigate(to tab: Tab) {
        selectedTab = tab
    }
    
    func showChat() {
        showingChat = true
    }
    
    func hideChat() {
        showingChat = false
    }
    
    func toggleChat() {
        showingChat.toggle()
    }
    
    // Left overlay actions
    func showSearchInLeftOverlay() {
        leftOverlayMode = .search
        showingLeftOverlay = true
    }
    
    func showChatInLeftOverlay() {
        leftOverlayMode = .chat
        showingLeftOverlay = true
    }
    
    func showFiltersInLeftOverlay() {
        leftOverlayMode = .filters
        showingLeftOverlay = true
    }
    
    func hideLeftOverlay() {
        showingLeftOverlay = false
    }
    
    // Bottom tab actions
    func selectBottomTab(_ tab: BottomTab) {
        selectedBottomTab = tab
    }
    
    func showBottomTabBar() {
        showingBottomTabBar = true
    }
    
    func hideBottomTabBar() {
        showingBottomTabBar = false
    }
}
```

#### AppError

```swift
import Foundation

/// Unified error type for the app
/// Provides user-friendly messages and logging context
enum AppError: LocalizedError, Equatable {
    // Data errors
    case databaseOpenFailed(path: String)
    case databaseCorrupted
    case airportNotFound(icao: String)
    case syncFailed(reason: String)
    case incompatibleSchema(server: Int, app: Int)
    
    // Network errors
    case networkUnavailable
    case serverError(statusCode: Int)
    case apiDecodingFailed(endpoint: String)
    case timeout
    
    // Chat errors
    case chatStreamFailed
    case toolExecutionFailed(tool: String)
    
    // General
    case unknown(message: String)
    
    var errorDescription: String? {
        switch self {
        case .databaseOpenFailed: return "Could not open airport database"
        case .databaseCorrupted: return "Airport database is corrupted"
        case .airportNotFound(let icao): return "Airport \(icao) not found"
        case .syncFailed(let reason): return "Database sync failed: \(reason)"
        case .incompatibleSchema: return "Please update the app to use latest database"
        case .networkUnavailable: return "No internet connection"
        case .serverError(let code): return "Server error (\(code))"
        case .apiDecodingFailed: return "Failed to parse server response"
        case .timeout: return "Request timed out"
        case .chatStreamFailed: return "Chat connection interrupted"
        case .toolExecutionFailed(let tool): return "Could not execute \(tool)"
        case .unknown(let msg): return msg
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .networkUnavailable: return "Check your internet connection and try again"
        case .serverError, .timeout: return "Try again later"
        case .syncFailed: return "You can continue using cached data"
        case .incompatibleSchema: return "Visit the App Store to update"
        default: return nil
        }
    }
    
    /// Create from any Error
    init(from error: Error) {
        if let appError = error as? AppError {
            self = appError
        } else if let urlError = error as? URLError {
            switch urlError.code {
            case .notConnectedToInternet: self = .networkUnavailable
            case .timedOut: self = .timeout
            default: self = .unknown(message: urlError.localizedDescription)
            }
        } else {
            self = .unknown(message: error.localizedDescription)
        }
    }
}
```

#### SystemDomain

```swift
import RZUtilsSwift

/// Domain: Connectivity, loading, errors, app-wide concerns
@Observable
@MainActor
final class SystemDomain {
    
    // MARK: - Dependencies
    private let connectivityMonitor: ConnectivityMonitor
    private let log = RZSLog(SystemDomain.self)
    
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
                log.info("Connectivity changed: \(mode)")
            }
        }
    }
    
    func setLoading(_ loading: Bool) {
        isLoading = loading
    }
    
    func setError(_ error: Error?) {
        if let error = error {
            let appError = AppError(from: error)
            self.error = appError
            log.error("App error: \(appError.localizedDescription)")
        } else {
            self.error = nil
        }
    }
    
    func clearError() {
        error = nil
    }
}
```

#### SettingsDomain

```swift
import SwiftUI

/// Domain: User preferences and persisted state
/// Uses @AppStorage for automatic persistence
@Observable
@MainActor
final class SettingsDomain {
    
    // MARK: - Unit Preferences
    
    @ObservationIgnored
    @AppStorage("units.distance") private var _distanceUnit: String = DistanceUnit.nauticalMiles.rawValue
    
    @ObservationIgnored
    @AppStorage("units.altitude") private var _altitudeUnit: String = AltitudeUnit.feet.rawValue
    
    @ObservationIgnored
    @AppStorage("units.runway") private var _runwayUnit: String = RunwayUnit.feet.rawValue
    
    var distanceUnit: DistanceUnit {
        get { DistanceUnit(rawValue: _distanceUnit) ?? .nauticalMiles }
        set { _distanceUnit = newValue.rawValue }
    }
    
    var altitudeUnit: AltitudeUnit {
        get { AltitudeUnit(rawValue: _altitudeUnit) ?? .feet }
        set { _altitudeUnit = newValue.rawValue }
    }
    
    var runwayUnit: RunwayUnit {
        get { RunwayUnit(rawValue: _runwayUnit) ?? .feet }
        set { _runwayUnit = newValue.rawValue }
    }
    
    // MARK: - Default Filters
    
    @ObservationIgnored
    @AppStorage("defaults.legendMode") private var _defaultLegendMode: String = LegendMode.airportType.rawValue
    
    @ObservationIgnored
    @AppStorage("defaults.filterOnlyProcedures") private var _defaultOnlyProcedures: Bool = false
    
    @ObservationIgnored
    @AppStorage("defaults.filterOnlyBorderCrossing") private var _defaultOnlyBorderCrossing: Bool = false
    
    @ObservationIgnored
    @AppStorage("defaults.filterCountry") private var _defaultCountry: String = ""
    
    var defaultLegendMode: LegendMode {
        get { LegendMode(rawValue: _defaultLegendMode) ?? .airportType }
        set { _defaultLegendMode = newValue.rawValue }
    }
    
    var defaultFilters: FilterConfig {
        var config = FilterConfig.default
        if _defaultOnlyProcedures { config.hasProcedures = true }
        if _defaultOnlyBorderCrossing { config.pointOfEntry = true }
        if !_defaultCountry.isEmpty { config.country = _defaultCountry }
        return config
    }
    
    func setDefaultFilter(onlyProcedures: Bool) {
        _defaultOnlyProcedures = onlyProcedures
    }
    
    func setDefaultFilter(onlyBorderCrossing: Bool) {
        _defaultOnlyBorderCrossing = onlyBorderCrossing
    }
    
    func setDefaultFilter(country: String?) {
        _defaultCountry = country ?? ""
    }
    
    // MARK: - Last Session State (Restore on Launch)
    
    @ObservationIgnored
    @AppStorage("session.lastMapLatitude") private var _lastMapLatitude: Double = 50.0
    
    @ObservationIgnored
    @AppStorage("session.lastMapLongitude") private var _lastMapLongitude: Double = 10.0
    
    @ObservationIgnored
    @AppStorage("session.lastMapSpan") private var _lastMapSpan: Double = 30.0
    
    @ObservationIgnored
    @AppStorage("session.lastSelectedAirport") private var _lastSelectedAirport: String = ""
    
    @ObservationIgnored
    @AppStorage("session.lastTab") private var _lastTab: String = "map"
    
    var lastMapRegion: MKCoordinateRegion {
        get {
            MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: _lastMapLatitude, longitude: _lastMapLongitude),
                span: MKCoordinateSpan(latitudeDelta: _lastMapSpan, longitudeDelta: _lastMapSpan)
            )
        }
        set {
            _lastMapLatitude = newValue.center.latitude
            _lastMapLongitude = newValue.center.longitude
            _lastMapSpan = newValue.span.latitudeDelta
        }
    }
    
    var lastSelectedAirportICAO: String? {
        get { _lastSelectedAirport.isEmpty ? nil : _lastSelectedAirport }
        set { _lastSelectedAirport = newValue ?? "" }
    }
    
    var lastTab: NavigationDomain.Tab {
        get { NavigationDomain.Tab(rawValue: _lastTab) ?? .map }
        set { _lastTab = newValue.rawValue }
    }
    
    // MARK: - Behavior Preferences
    
    @ObservationIgnored
    @AppStorage("behavior.restoreSession") var restoreSessionOnLaunch: Bool = true
    
    @ObservationIgnored
    @AppStorage("behavior.autoSync") var autoSyncDatabase: Bool = true
    
    @ObservationIgnored
    @AppStorage("behavior.showOfflineBanner") var showOfflineBanner: Bool = true
    
    // MARK: - Chatbot Preferences
    
    @ObservationIgnored
    @AppStorage("chatbot.saveHistory") var saveChatHistory: Bool = false
    
    @ObservationIgnored
    @AppStorage("chatbot.showThinking") var showChatbotThinking: Bool = true
    
    // MARK: - Actions
    
    /// Save current session state for restoration
    func saveSessionState(
        mapRegion: MKCoordinateRegion,
        selectedAirport: Airport?,
        tab: NavigationDomain.Tab
    ) {
        lastMapRegion = mapRegion
        lastSelectedAirportICAO = selectedAirport?.icao
        lastTab = tab
    }
    
    /// Reset all settings to defaults
    func resetToDefaults() {
        distanceUnit = .nauticalMiles
        altitudeUnit = .feet
        runwayUnit = .feet
        defaultLegendMode = .airportType
        _defaultOnlyProcedures = false
        _defaultOnlyBorderCrossing = false
        _defaultCountry = ""
        restoreSessionOnLaunch = true
        autoSyncDatabase = true
        showOfflineBanner = true
    }
}

// MARK: - Unit Types

enum DistanceUnit: String, CaseIterable, Identifiable, Sendable {
    case nauticalMiles = "nm"
    case kilometers = "km"
    case miles = "mi"
    
    var id: String { rawValue }
    
    var displayName: String {
        switch self {
        case .nauticalMiles: return "Nautical Miles"
        case .kilometers: return "Kilometers"
        case .miles: return "Miles"
        }
    }
    
    var abbreviation: String {
        switch self {
        case .nauticalMiles: return "NM"
        case .kilometers: return "km"
        case .miles: return "mi"
        }
    }
    
    func convert(fromNauticalMiles nm: Double) -> Double {
        switch self {
        case .nauticalMiles: return nm
        case .kilometers: return nm * 1.852
        case .miles: return nm * 1.15078
        }
    }
}

enum AltitudeUnit: String, CaseIterable, Identifiable {
    case feet = "ft"
    case meters = "m"
    
    var id: String { rawValue }
    
    var displayName: String {
        switch self {
        case .feet: return "Feet"
        case .meters: return "Meters"
        }
    }
    
    func convert(fromFeet ft: Int) -> Int {
        switch self {
        case .feet: return ft
        case .meters: return Int(Double(ft) * 0.3048)
        }
    }
}

enum RunwayUnit: String, CaseIterable, Identifiable {
    case feet = "ft"
    case meters = "m"
    
    var id: String { rawValue }
    
    var displayName: String {
        switch self {
        case .feet: return "Feet"
        case .meters: return "Meters"
        }
    }
    
    func convert(fromFeet ft: Int) -> Int {
        switch self {
        case .feet: return ft
        case .meters: return Int(Double(ft) * 0.3048)
        }
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
    let settings: SettingsDomain
    
    // MARK: - Init
    
    init(
        repository: AirportRepository,
        chatbotService: ChatbotService,
        connectivityMonitor: ConnectivityMonitor
    ) {
        self.settings = SettingsDomain()
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
        
        // Restore session state if enabled
        if settings.restoreSessionOnLaunch {
            restoreLastSession()
        }
        
        // Apply default filters from settings
        airports.filters = settings.defaultFilters
        airports.legendMode = settings.defaultLegendMode
        
        do {
            try await airports.load()
        } catch {
            system.setError(error)
        }
    }
    
    // MARK: - Session Persistence
    
    /// Restore last session state
    private func restoreLastSession() {
        // Restore map position
        airports.mapPosition = .region(settings.lastMapRegion)
        airports.visibleRegion = settings.lastMapRegion
        
        // Restore tab
        navigation.selectedTab = settings.lastTab
        
        // Note: selectedAirport restored after load completes
        // (need to look up from repository)
    }
    
    /// Save session state (call on app background/terminate)
    func saveSession() {
        settings.saveSessionState(
            mapRegion: airports.visibleRegion ?? .europe,
            selectedAirport: airports.selectedAirport,
            tab: navigation.selectedTab
        )
    }
    
    /// Restore selected airport after data loads
    func restoreSelectedAirportIfNeeded() async {
        guard settings.restoreSessionOnLaunch,
              let icao = settings.lastSelectedAirportICAO else { return }
        
        if let airport = try? await airports.repository.airportDetail(icao: icao) {
            airports.selectedAirport = airport
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
enum LegendMode: String, CaseIterable, Identifiable, Sendable, Codable {
    case airportType = "Airport Type"
    case runwayLength = "Runway Length"
    case procedures = "IFR Procedures"
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

// MARK: - Regular Layout (iPad/Mac)

struct RegularLayout: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        ZStack {
            // Full screen map
            AirportMapView()
                .ignoresSafeArea()
            
            // Semi-transparent backdrop when overlay is visible (tap to dismiss)
            if state?.navigation.showingLeftOverlay == true {
                Color.black.opacity(0.3)
                    .ignoresSafeArea()
                    .onTapGesture {
                        state?.navigation.hideLeftOverlay()
                    }
                    .transition(.opacity)
            }
            
            // Left Overlay (slides in from left when visible)
            HStack(spacing: 0) {
                if state?.navigation.showingLeftOverlay == true {
                    LeftOverlayContainer()
                        .padding(.leading, 8)
                        .padding(.vertical, 8)
                        .transition(.move(edge: .leading).combined(with: .opacity))
                        .zIndex(1) // Ensure overlay is above backdrop
                }
                Spacer()
            }
            
            // Bottom Tab Bar (overlay)
            VStack {
                Spacer()
                BottomTabBar()
            }
            
            // Floating Action Buttons (top-right corner)
            VStack {
                HStack {
                    Spacer()
                    RegularFloatingActionButtons()
                        .padding(.trailing, 16)
                        .padding(.top, 8)
                }
                .padding(.top, 8) // Safe area padding
                Spacer()
            }
        }
        .animation(.spring(response: 0.3, dampingFraction: 0.8), value: state?.navigation.showingLeftOverlay)
    }
}

/// Left overlay container that shows either Search/Filter or Chat based on navigation state
struct LeftOverlayContainer: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        VStack(spacing: 0) {
            // Toolbar with close button
            overlayToolbar
            
            // Content area - shows Search, Chat, or Filters
            Group {
                switch state?.navigation.leftOverlayMode ?? .search {
                case .search:
                    SearchView()
                case .chat:
                    ChatView()
                case .filters:
                    FilterPanelContent()
                }
            }
        }
        .frame(width: overlayWidth)
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .shadow(color: .black.opacity(0.15), radius: 20, x: 4, y: 0)
    }
}

// MARK: - Compact Layout (iPhone)

struct CompactLayout: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        ZStack {
            // Map as background
            AirportMapView()
                .ignoresSafeArea()
            
            // Bottom Tab Bar (overlay)
            VStack {
                Spacer()
                BottomTabBar()
            }
            
            // Floating Action Buttons (top-right corner)
            VStack {
                HStack {
                    Spacer()
                    FloatingActionButtons()
                        .padding(.trailing, 16)
                        .padding(.top, 8)
                }
                .padding(.top, 8) // Safe area padding
                Spacer()
            }
        }
    }
}

/// Bottom tab bar that shows airport detail information in tabs
struct BottomTabBar: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Group {
            // Only show if an airport is selected AND tab bar is visible
            if state?.airports.selectedAirport != nil && (state?.navigation.showingBottomTabBar ?? false) {
                VStack(spacing: 0) {
                    // Tab content with close button
                    ZStack(alignment: .topTrailing) {
                        tabContent
                            .frame(height: tabContentHeight)
                        
                        // Close button
                        Button {
                            state?.navigation.hideBottomTabBar()
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.title2)
                                .foregroundStyle(.secondary)
                                .background(.ultraThinMaterial, in: Circle())
                        }
                        .padding(8)
                    }
                    
                    // Tab bar
                    tabBar
                }
                .background(.ultraThinMaterial)
                .transition(.move(edge: .bottom))
            }
        }
        .onChange(of: state?.airports.selectedAirport) { oldValue, newValue in
            if newValue != nil {
                state?.navigation.showBottomTabBar()
            }
        }
    }
    
    private var tabContent: some View {
        Group {
            if let airport = state?.airports.selectedAirport {
                switch state?.navigation.selectedBottomTab ?? .airportInfo {
                case .airportInfo:
                    AirportInfoTab(airport: airport)
                case .aip:
                    AIPTab(airport: airport)
                case .rules:
                    RulesTab(airport: airport)
                }
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

### 6.4 Settings UI

```swift
struct SettingsView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Form {
            // MARK: - Units
            Section("Units") {
                Picker("Distance", selection: Binding(
                    get: { state?.settings.distanceUnit ?? .nauticalMiles },
                    set: { state?.settings.distanceUnit = $0 }
                )) {
                    ForEach(DistanceUnit.allCases) { unit in
                        Text(unit.displayName).tag(unit)
                    }
                }
                
                Picker("Altitude", selection: Binding(
                    get: { state?.settings.altitudeUnit ?? .feet },
                    set: { state?.settings.altitudeUnit = $0 }
                )) {
                    ForEach(AltitudeUnit.allCases) { unit in
                        Text(unit.displayName).tag(unit)
                    }
                }
                
                Picker("Runway Length", selection: Binding(
                    get: { state?.settings.runwayUnit ?? .feet },
                    set: { state?.settings.runwayUnit = $0 }
                )) {
                    ForEach(RunwayUnit.allCases) { unit in
                        Text(unit.displayName).tag(unit)
                    }
                }
            }
            
            // MARK: - Default View
            Section("Default View") {
                Picker("Legend Mode", selection: Binding(
                    get: { state?.settings.defaultLegendMode ?? .airportType },
                    set: { state?.settings.defaultLegendMode = $0 }
                )) {
                    ForEach(LegendMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                
                Toggle("Only IFR Airports", isOn: Binding(
                    get: { state?.settings._defaultOnlyProcedures ?? false },
                    set: { state?.settings.setDefaultFilter(onlyProcedures: $0) }
                ))
                
                Toggle("Only Border Crossings", isOn: Binding(
                    get: { state?.settings._defaultOnlyBorderCrossing ?? false },
                    set: { state?.settings.setDefaultFilter(onlyBorderCrossing: $0) }
                ))
            }
            
            // MARK: - Behavior
            Section("Behavior") {
                Toggle("Restore Session on Launch", isOn: Binding(
                    get: { state?.settings.restoreSessionOnLaunch ?? true },
                    set: { state?.settings.restoreSessionOnLaunch = $0 }
                ))
                .help("Remember last map position and selected airport")
                
                Toggle("Auto-Sync Database", isOn: Binding(
                    get: { state?.settings.autoSyncDatabase ?? true },
                    set: { state?.settings.autoSyncDatabase = $0 }
                ))
                .help("Automatically download database updates when online")
                
                Toggle("Show Offline Banner", isOn: Binding(
                    get: { state?.settings.showOfflineBanner ?? true },
                    set: { state?.settings.showOfflineBanner = $0 }
                ))
            }
            
            // MARK: - Chatbot
            Section("Chatbot") {
                Toggle("Show Thinking Process", isOn: Binding(
                    get: { state?.settings.showChatbotThinking ?? true },
                    set: { state?.settings.showChatbotThinking = $0 }
                ))
                .help("Show AI reasoning while generating responses")
            }
            
            // MARK: - Data
            Section("Data") {
                LabeledContent("Database Version") {
                    Text(state?.system.databaseVersion ?? "Unknown")
                        .foregroundStyle(.secondary)
                }
                
                LabeledContent("Last Sync") {
                    Text(state?.system.lastSyncDate?.formatted() ?? "Never")
                        .foregroundStyle(.secondary)
                }
                
                Button("Sync Now") {
                    Task { await state?.syncDatabase() }
                }
                .disabled(state?.system.connectivityMode == .offline)
                
                Button("Clear Cache", role: .destructive) {
                    state?.clearCache()
                }
            }
            
            // MARK: - Reset
            Section {
                Button("Reset All Settings", role: .destructive) {
                    state?.settings.resetToDefaults()
                }
            }
            
            // MARK: - About
            Section("About") {
                LabeledContent("Version") {
                    Text(Bundle.main.appVersion)
                        .foregroundStyle(.secondary)
                }
                Link("Privacy Policy", destination: URL(string: "https://flyfun.aero/privacy")!)
                Link("Terms of Service", destination: URL(string: "https://flyfun.aero/terms")!)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Settings")
    }
}

extension Bundle {
    var appVersion: String {
        let version = infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(version) (\(build))"
    }
}
```

**Settings Persistence:**
- Uses `@AppStorage` for automatic UserDefaults persistence
- Settings survive app restarts
- Syncs across devices via iCloud (if enabled)

**Unit Conversion Helper:**
```swift
extension View {
    /// Format distance using user's preferred unit
    func formattedDistance(_ nm: Double, settings: SettingsDomain) -> String {
        let value = settings.distanceUnit.convert(fromNauticalMiles: nm)
        return String(format: "%.1f %@", value, settings.distanceUnit.abbreviation)
    }
    
    /// Format altitude using user's preferred unit
    func formattedAltitude(_ ft: Int, settings: SettingsDomain) -> String {
        let value = settings.altitudeUnit.convert(fromFeet: ft)
        return "\(value) \(settings.altitudeUnit.rawValue)"
    }
}
```

### 6.5 Map Performance Strategy

**Problem:** Europe has ~10,000+ airports. Rendering all markers kills performance.

**Solution:** Region-based data loading + clustering

```swift
struct AirportMapView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Map(position: $mapPosition) {
            // Only render airports in visible region (loaded by AirportDomain)
            ForEach(state?.airports.airports ?? []) { airport in
                Annotation(airport.icao, coordinate: airport.coord) {
                    AirportMarker(airport: airport, legendMode: state?.airports.legendMode ?? .airportType)
                }
            }
        }
        // React to region changes
        .onMapCameraChange(frequency: .onEnd) { context in
            state?.airports.onRegionChange(context.region)
        }
        // Use MapKit clustering for dense areas
        .mapStyle(.standard(elevation: .realistic))
    }
}
```

**Key Design Decisions:**

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Data Loading** | By visible region | Don't load all 10K airports |
| **Debouncing** | 300ms after pan/zoom | Avoid excessive queries |
| **Prefetch Padding** | 1.3x visible region | Smooth panning |
| **Marker Limit** | 500 per region | Performance ceiling |
| **Clustering** | MapKit native | Automatic zoom-based grouping |

**Repository Method:**
```swift
func airportsInRegion(boundingBox:filters:limit:) async throws -> [Airport]
```

**RZFlight Enhancement Opportunity:**
- Add `KnownAirports.airports(in: BoundingBox)` for efficient spatial query
- Current approach filters `known.values` - O(n) scan
- KDTree already exists in RZFlight - could expose bounding box query

### 6.5 macOS-Specific Affordances

**Goal:** Make the Mac version feel native, not "iPad on a bigger screen."

#### Keyboard Shortcuts

```swift
struct ContentView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        RegularLayout()
            .focusedSceneValue(\.appState, state)
            // Keyboard shortcuts
            .keyboardShortcut("f", modifiers: .command) { focusSearch() }
            .keyboardShortcut("l", modifiers: .command) { toggleFilters() }
            .keyboardShortcut("k", modifiers: .command) { toggleChat() }
            .keyboardShortcut(",", modifiers: .command) { showSettings() }
    }
}
```

| Shortcut | Action | Notes |
|----------|--------|-------|
| ⌘F | Focus search field | Standard find |
| ⌘L | Toggle filter panel | L for "List filters" |
| ⌘K | Toggle chat | K for "Konversation" (common pattern) |
| ⌘, | Open settings | Standard preferences |
| ⌘1-4 | Switch tabs | Standard tab switching |
| ⌘R | Refresh/reload | Reload airport data |
| ⌘⌫ | Clear route | Clear active route |
| ⌘+ / ⌘- | Zoom map | Standard zoom |

#### Menu Bar Items

```swift
@main
struct FlyFunEuroAIPApp: App {
    @State private var appState: AppState
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.appState, appState)
        }
        .commands {
            // Replace default menus
            CommandGroup(replacing: .newItem) { }  // Remove "New" - not applicable
            
            // View menu
            CommandMenu("View") {
                Button("Toggle Filters") { appState.navigation.showingFilters.toggle() }
                    .keyboardShortcut("l")
                Button("Toggle Chat") { appState.navigation.showingChat.toggle() }
                    .keyboardShortcut("k")
                Divider()
                Picker("Legend Mode", selection: $appState.airports.legendMode) {
                    ForEach(LegendMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                Divider()
                Button("Zoom In") { zoomIn() }
                    .keyboardShortcut("+")
                Button("Zoom Out") { zoomOut() }
                    .keyboardShortcut("-")
            }
            
            // Map menu
            CommandMenu("Map") {
                Button("Clear Route") { appState.airports.clearRoute() }
                    .keyboardShortcut(.delete)
                    .disabled(appState.airports.activeRoute == nil)
                Button("Center on Selection") { centerOnSelection() }
                    .keyboardShortcut("e")
                    .disabled(appState.airports.selectedAirport == nil)
                Divider()
                Button("Show All Airports") { resetMapView() }
            }
        }
        
        #if os(macOS)
        // Settings window (macOS only)
        Settings {
            SettingsView()
                .environment(\.appState, appState)
        }
        
        // Multiple window support
        Window("Route Planning", id: "route") {
            RoutePlanningWindow()
                .environment(\.appState, appState)
        }
        .keyboardShortcut("n", modifiers: [.command, .shift])
        #endif
    }
}
```

#### Multiple Windows (macOS)

```swift
#if os(macOS)
/// Separate window for focused route planning
struct RoutePlanningWindow: View {
    @Environment(\.appState) private var state
    @Environment(\.openWindow) private var openWindow
    
    var body: some View {
        HSplitView {
            // Route list
            List(selection: $selectedRoute) {
                ForEach(savedRoutes) { route in
                    RouteRow(route: route)
                }
            }
            .frame(minWidth: 200)
            
            // Route detail / map
            if let route = selectedRoute {
                RouteDetailView(route: route)
            } else {
                ContentUnavailableView("Select a Route", systemImage: "point.topLeft.down.to.point.bottomright.curvepath")
            }
        }
        .frame(minWidth: 800, minHeight: 500)
    }
}

/// Airport detail as separate window
struct AirportDetailWindow: View {
    let airport: Airport
    
    var body: some View {
        AirportDetailView(airport: airport)
            .frame(minWidth: 400, minHeight: 600)
    }
}
#endif
```

#### Mac-Specific UI Polish

```swift
struct RegularLayout: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        NavigationSplitView {
            SearchSidebar()
                #if os(macOS)
                .navigationSplitViewColumnWidth(min: 250, ideal: 300, max: 400)
                #endif
        } content: {
            AirportMapView()
        } detail: {
            if let airport = state?.airports.selectedAirport {
                AirportDetailView(airport: airport)
                    #if os(macOS)
                    // Mac: toolbar button to open in new window
                    .toolbar {
                        ToolbarItem {
                            Button {
                                openAirportWindow(airport)
                            } label: {
                                Label("Open in New Window", systemImage: "macwindow.badge.plus")
                            }
                        }
                    }
                    #endif
            }
        }
        #if os(macOS)
        // Mac-specific toolbar style
        .toolbar {
            ToolbarItem(placement: .navigation) {
                Text("FlyFun EuroAIP")
                    .font(.headline)
            }
        }
        .toolbarBackground(.visible, for: .windowToolbar)
        #endif
    }
}
```

#### Platform Checks Summary

| Feature | iOS/iPadOS | macOS |
|---------|------------|-------|
| Navigation | Bottom sheet / tabs | NavigationSplitView |
| Keyboard shortcuts | N/A | Full support |
| Menu bar | N/A | Custom menus |
| Multiple windows | N/A | Supported |
| Settings | In-app sheet | Separate Settings window |
| Toolbar | iOS style | Mac window toolbar |
| Sidebar width | Automatic | Customizable |
| Right-click | N/A | Context menus |
| Drag & drop | Limited | Full support |

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
| **User Preferences** | App (UserDefaults/@AppStorage) | N/A | Local only |

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

**AIP Entry Caching (File-Based):**

Uses simple JSON file caching instead of SwiftData for simplicity:

```swift
import RZUtilsSwift

/// AIP entries from API can be cached for offline access
/// These supplement (not replace) DB entries
/// Uses file-based JSON caching (no SwiftData)
final class AIPCache {
    private let cacheDirectory: URL
    private let knownAirports: KnownAirports
    private let log = RZSLog(AIPCache.self)
    
    init(knownAirports: KnownAirports) {
        self.knownAirports = knownAirports
        self.cacheDirectory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appending(path: "aip_cache")
        try? FileManager.default.createDirectory(at: cacheDirectory, withIntermediateDirectories: true)
    }
    
    private func cacheURL(for icao: String) -> URL {
        cacheDirectory.appending(path: "\(icao.uppercased()).json")
    }
    
    /// Cache API-fetched AIP entries as JSON file
    func cache(entries: [AIPEntry], for icao: String) {
        let cached = CachedAIPEntries(
            icao: icao,
            entries: entries,
            fetchedAt: Date()
        )
        do {
            let data = try JSONEncoder().encode(cached)
            try data.write(to: cacheURL(for: icao))
            log.info("Cached \(entries.count) AIP entries for \(icao)")
        } catch {
            log.error("Failed to cache AIP entries for \(icao): \(error)")
        }
    }
    
    /// Get entries: prefer fresh API cache, fall back to DB
    func entries(for icao: String, maxAge: TimeInterval = 86400) -> [AIPEntry] {
        // Check file cache first (if fresh enough)
        if let cached = loadCached(icao: icao),
           cached.fetchedAt.timeIntervalSinceNow > -maxAge {
            return cached.entries
        }
        // Fall back to DB
        return knownAirports.airport(icao: icao)?.aipEntries ?? []
    }
    
    private func loadCached(icao: String) -> CachedAIPEntries? {
        let url = cacheURL(for: icao)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(CachedAIPEntries.self, from: data)
    }
    
    /// Clear all cached entries (for storage management)
    func clearCache() {
        try? FileManager.default.removeItem(at: cacheDirectory)
        try? FileManager.default.createDirectory(at: cacheDirectory, withIntermediateDirectories: true)
        log.info("AIP cache cleared")
    }
}

/// Cached AIP entries wrapper
struct CachedAIPEntries: Codable {
    let icao: String
    let entries: [AIPEntry]
    let fetchedAt: Date
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
| **iOS** | 18.0+ | `@Observable`, modern MapKit, Apple Intelligence |
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
| **OSLog** | Structured logging (via RZUtilsSwift) | 15.0+ |
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

## 11. Logging & Crash Reporting

### Logging Strategy

Uses **RZUtilsSwift** logging (built on Apple's OSLog):

```swift
import RZUtilsSwift

final class AirportRepository {
    private let log = RZSLog(AirportRepository.self)
    
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [Airport] {
        log.info("Fetching airports: filters=\(filters), limit=\(limit)")
        // ...
        log.debug("Found \(results.count) airports")
        return results
    }
}
```

**Log Levels:**

| Level | Usage | Example |
|-------|-------|---------|
| `error` | Failures that affect functionality | DB open failed, API error |
| `warning` | Recoverable issues | Cache miss, fallback used |
| `info` | Significant events | App launch, sync complete, connectivity change |
| `debug` | Development diagnostics | Query results, state changes |
| `trace` | Verbose tracing | Method entry/exit (disabled in release) |

**Log Categories:**

```swift
// Each component has its own category via RZSLog
RZSLog(AirportRepository.self)   // "FlyFunEuroAIP.AirportRepository"
RZSLog(ChatDomain.self)          // "FlyFunEuroAIP.ChatDomain"
RZSLog(SyncService.self)         // "FlyFunEuroAIP.SyncService"
```

**Filtering in Console.app:**
- Subsystem: `FlyFunEuroAIP`
- Category: Component name

### Crash Reporting

Uses **Apple's native crash reporting** (no third-party SDK):

1. **MetricKit** - Automatic crash and diagnostic collection
2. **App Store Connect** - Crash reports via Xcode Organizer
3. **TestFlight** - Crash feedback from beta testers

```swift
import MetricKit

@main
struct FlyFunEuroAIPApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    var body: some Scene { /* ... */ }
}

class AppDelegate: NSObject, UIApplicationDelegate, MXMetricManagerSubscriber {
    
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Subscribe to MetricKit
        MXMetricManager.shared.add(self)
        return true
    }
    
    func didReceive(_ payloads: [MXMetricPayload]) {
        // Payloads include crash diagnostics
        // These are automatically sent to App Store Connect
        for payload in payloads {
            // Optional: Log locally or send to custom analytics
            RZSLog(AppDelegate.self).info("Received metrics payload: \(payload.timeStampBegin) - \(payload.timeStampEnd)")
        }
    }
    
    func didReceive(_ payloads: [MXDiagnosticPayload]) {
        // Detailed crash diagnostics
        for payload in payloads {
            if let crashDiagnostics = payload.crashDiagnostics {
                for crash in crashDiagnostics {
                    RZSLog(AppDelegate.self).error("Crash: \(crash.terminationReason ?? "unknown")")
                }
            }
        }
    }
}
```

**Why Native Only:**
- No SDK to maintain/update
- Privacy-compliant (no third-party data sharing)
- Automatic symbolication in Xcode
- Integrated with App Store Connect
- MetricKit provides battery, memory, and performance metrics too

---

## 12. Map Clustering

### MKClusterAnnotation Strategy

Uses Apple's native `MKClusterAnnotation` for performance with many markers:

```swift
import MapKit

// MARK: - Annotation Types

/// Custom annotation for airports
final class AirportAnnotation: NSObject, MKAnnotation, Identifiable {
    let id: String
    let airport: Airport
    
    var coordinate: CLLocationCoordinate2D { airport.coord }
    var title: String? { airport.icao }
    var subtitle: String? { airport.name }
    
    // Clustering identifier - same ID means they cluster together
    var clusteringIdentifier: String { "airport" }
    
    init(airport: Airport) {
        self.id = airport.icao
        self.airport = airport
        super.init()
    }
}

// MARK: - Map View with Clustering

struct AirportMapView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Map(position: $state.airports.mapPosition) {
            // ForEach over annotations
            ForEach(airportAnnotations) { annotation in
                Annotation(annotation.title ?? "", coordinate: annotation.coordinate) {
                    AirportMarkerView(airport: annotation.airport)
                }
                .annotationTitles(.hidden)
            }
        }
        .onMapCameraChange { context in
            state?.airports.onRegionChange(context.region)
        }
    }
    
    private var airportAnnotations: [AirportAnnotation] {
        state?.airports.airports.map { AirportAnnotation(airport: $0) } ?? []
    }
}

// MARK: - UIKit Map for Clustering (if SwiftUI Map doesn't support it)

/// Use UIViewRepresentable for full MKClusterAnnotation support
struct ClusteredMapView: UIViewRepresentable {
    @Binding var region: MKCoordinateRegion
    let airports: [Airport]
    let onSelect: (Airport) -> Void
    
    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        
        // Register annotation views
        mapView.register(
            AirportAnnotationView.self,
            forAnnotationViewWithReuseIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier
        )
        mapView.register(
            ClusterAnnotationView.self,
            forAnnotationViewWithReuseIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier
        )
        
        return mapView
    }
    
    func updateUIView(_ mapView: MKMapView, context: Context) {
        // Update region
        mapView.setRegion(region, animated: false)
        
        // Update annotations efficiently
        let currentICAOs = Set(mapView.annotations.compactMap { ($0 as? AirportAnnotation)?.id })
        let newICAOs = Set(airports.map(\.icao))
        
        // Remove old
        let toRemove = mapView.annotations.filter { 
            guard let a = $0 as? AirportAnnotation else { return false }
            return !newICAOs.contains(a.id)
        }
        mapView.removeAnnotations(toRemove)
        
        // Add new
        let toAdd = airports.filter { !currentICAOs.contains($0.icao) }
            .map { AirportAnnotation(airport: $0) }
        mapView.addAnnotations(toAdd)
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator(onSelect: onSelect)
    }
    
    class Coordinator: NSObject, MKMapViewDelegate {
        let onSelect: (Airport) -> Void
        
        init(onSelect: @escaping (Airport) -> Void) {
            self.onSelect = onSelect
        }
        
        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            // Let system handle clusters
            if annotation is MKClusterAnnotation {
                return nil  // System will use registered ClusterAnnotationView
            }
            return nil  // System will use registered AirportAnnotationView
        }
        
        func mapView(_ mapView: MKMapView, didSelect annotation: MKAnnotation) {
            if let cluster = annotation as? MKClusterAnnotation {
                // Zoom to cluster
                let rect = cluster.memberAnnotations.reduce(MKMapRect.null) { rect, ann in
                    let point = MKMapPoint(ann.coordinate)
                    let pointRect = MKMapRect(x: point.x, y: point.y, width: 0.1, height: 0.1)
                    return rect.union(pointRect)
                }
                mapView.setVisibleMapRect(rect, edgePadding: .init(top: 50, left: 50, bottom: 50, right: 50), animated: true)
            } else if let airport = (annotation as? AirportAnnotation)?.airport {
                onSelect(airport)
            }
        }
    }
}

// MARK: - Custom Annotation Views

final class AirportAnnotationView: MKMarkerAnnotationView {
    override var annotation: MKAnnotation? {
        didSet { configure() }
    }
    
    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        clusteringIdentifier = "airport"
        configure()
    }
    
    required init?(coder aDecoder: NSCoder) { fatalError() }
    
    private func configure() {
        guard let airportAnnotation = annotation as? AirportAnnotation else { return }
        let airport = airportAnnotation.airport
        
        // Color by airport type
        markerTintColor = airport.type.markerColor
        glyphImage = UIImage(systemName: airport.hasInstrumentProcedures ? "airplane.circle.fill" : "airplane.circle")
        displayPriority = airport.hasInstrumentProcedures ? .required : .defaultHigh
    }
}

final class ClusterAnnotationView: MKAnnotationView {
    override var annotation: MKAnnotation? {
        didSet { configure() }
    }
    
    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        collisionMode = .circle
        configure()
    }
    
    required init?(coder aDecoder: NSCoder) { fatalError() }
    
    private func configure() {
        guard let cluster = annotation as? MKClusterAnnotation else { return }
        
        let count = cluster.memberAnnotations.count
        image = drawClusterImage(count: count)
        displayPriority = .required
    }
    
    private func drawClusterImage(count: Int) -> UIImage {
        let size = CGSize(width: 40, height: 40)
        return UIGraphicsImageRenderer(size: size).image { context in
            // Draw circle
            UIColor.systemBlue.setFill()
            UIBezierPath(ovalIn: CGRect(origin: .zero, size: size)).fill()
            
            // Draw count
            let text = count > 99 ? "99+" : "\(count)"
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.boldSystemFont(ofSize: 14),
                .foregroundColor: UIColor.white
            ]
            let textSize = text.size(withAttributes: attrs)
            let textRect = CGRect(
                x: (size.width - textSize.width) / 2,
                y: (size.height - textSize.height) / 2,
                width: textSize.width,
                height: textSize.height
            )
            text.draw(in: textRect, withAttributes: attrs)
        }
    }
}
```

### Clustering Behavior

| Zoom Level | Behavior |
|------------|----------|
| Wide (Europe) | Heavy clustering, show counts |
| Regional (country) | Moderate clustering |
| Local (city) | Individual markers |
| Detail | Full markers with labels |

### Performance Considerations

- **Limit initial load**: 500 airports max via `airportsInRegion()`
- **Progressive loading**: Load more as user zooms
- **Clustering threshold**: ~20+ annotations start clustering
- **Animation**: Disable animations during rapid pan/zoom

---

## 13. Open Questions

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

## 14. RZFlight Enhancement Proposals

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

---

## Appendix C: Implementation Status (as of Review)

### ✅ Implemented

| Component | Status | Notes |
|-----------|--------|-------|
| **Architecture** |
| AppState with composed domains | ✅ Complete | All 5 domains implemented (Airport, Chat, Navigation, System, Settings) |
| Repository pattern | ✅ Complete | Local and Remote data sources, strategy pattern |
| Connectivity monitoring | ✅ Complete | AsyncStream-based, ConnectionType tracking |
| **Data Layer** |
| LocalAirportDataSource | ✅ Complete | Uses KnownAirports, bulk loads extended data |
| RemoteAirportDataSource | ⚠️ Partial | Structure exists, full integration in progress |
| AirportRepository | ✅ Complete | Strategy-based switching, connectivity observation |
| **State Management** |
| AirportDomain | ✅ Complete | Region-based loading, procedure lines, border crossing cache |
| ChatDomain | ✅ Complete | SSE streaming, visualization callbacks |
| NavigationDomain | ✅ Complete | Left overlay, bottom tabs, sheets |
| SystemDomain | ✅ Complete | Connectivity, errors, loading |
| SettingsDomain | ✅ Complete | Unit preferences, session persistence |
| **UI Components** |
| Map view | ✅ Complete | Region-based loading, procedure lines, highlights |
| Left overlay | ✅ Complete | Search/Chat/Filters switching |
| Bottom tab bar | ✅ Complete | Airport Info/AIP/Rules tabs |
| Chat view | ✅ Complete | Streaming, thinking indicators, tool calls |
| Filter panel | ✅ Complete | Integrated with FilterConfig |
| **Chatbot** |
| OnlineChatbotService | ✅ Complete | SSE parsing, event handling |
| ChatEvent parsing | ✅ Complete | All event types supported |
| Visualization handling | ✅ Complete | ChatVisualizationPayload → AirportDomain |
| Offline chatbot | ❌ Not started | POST-1.0 feature |

### ⚠️ Differences from Design

1. **UI Layout**: Uses ZStack with overlays instead of NavigationSplitView
   - Left overlay slides in from left (iPad/Mac)
   - Bottom tab bar overlays map
   - More flexible for cross-platform consistency

2. **FilterConfig**: Simplified from design
   - Removed: `hasAIPData`, `hasAvgas`, `hasJetA`, `maxLandingFee`, `aipValue`, `aipOperator`
   - Added: `hasLightedRunway`, `hasILS`, `hasRNAV`, `hasPrecisionApproach`
   - Focus on core filtering needs

3. **BoundingBox**: Uses `minCoord`/`maxCoord` instead of separate lat/lon
   - More type-safe with CLLocationCoordinate2D
   - Convenience accessors for lat/lon

4. **ChatEvent**: More detailed than design
   - Includes `plan`, `toolCallStart`, `toolCallEnd`, `thinkingDone`, `finalAnswer`
   - Better alignment with actual API events

5. **Visualization Payloads**: Two types
   - `ChatVisualizationPayload`: From API (parsed from JSON)
   - `VisualizationPayload`: Internal (for programmatic use)
   - Clear separation of concerns

6. **DistanceUnit**: Uses `miles` instead of `statuteMiles`
   - Simpler naming convention

### 🔄 In Progress

- Remote data source full integration
- Database sync service
- AIP entry caching

### 📋 Planned (POST-1.0)

- Offline chatbot with LLM backend abstraction
- Apple Intelligence integration
- Database delta updates
- Map tile offline caching


