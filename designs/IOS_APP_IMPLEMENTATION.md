# FlyFun EuroAIP iOS App - Implementation Plan

## Overview

This document provides a detailed implementation roadmap for the FlyFun EuroAIP iOS/macOS app. It breaks down the design into actionable phases with specific tasks, dependencies, and deliverables.

**Reference:** `designs/IOS_APP_DESIGN.md` for architecture and design decisions.

---

## Platform Requirements

| Platform | Version | Rationale |
|----------|---------|-----------|
| **iOS** | 18.0+ | `@Observable`, modern MapKit, Apple Intelligence |
| **macOS** | 15.0+ | Native SwiftUI experience |
| **Xcode** | 16.0+ | Swift 6 support |

**Why Latest Only:** No backward compatibility complexity. Use all modern Apple frameworks.

---

## ⚠️ Critical Rules

### 1. RZFlight Model Reuse

**DO NOT create duplicate models.** Use [RZFlight](https://github.com/roznet/rzflight) types directly:

```swift
// ✅ CORRECT
import RZFlight
let airports: [Airport]  // RZFlight.Airport

// ❌ WRONG
struct AppAirport { ... }  // NO!
```

### 2. Single AppState with Composed Domains (No Multiple ViewModels)

**DO NOT create separate ViewModels.** Use single `AppState` composed of domain objects:

```swift
// ✅ CORRECT - Single store with composed domains
@Observable final class AppState {
    let airports: AirportDomain   // Owns airport/filter/map state
    let chat: ChatDomain          // Owns chat/streaming state
    let navigation: NavigationDomain  // Owns nav/tabs/sheets
    let system: SystemDomain      // Owns connectivity/errors
}

@Observable final class AirportDomain {
    var airports: [Airport] = []
    var filters: FilterConfig = .default
    var mapPosition: MapCameraPosition = .automatic
}

@Observable final class ChatDomain {
    var messages: [ChatMessage] = []
    var isStreaming: Bool = false
}

// ❌ WRONG - Standalone ViewModels
class AirportMapViewModel: ObservableObject { ... }  // NO!
class ChatbotViewModel: ObservableObject { ... }  // NO!
```

**Why composed?** Prevents God-class anti-pattern. Each domain is 200-400 lines, testable in isolation.

### 3. Modern SwiftUI Patterns

```swift
// ✅ CORRECT - Use @Observable (iOS 17+)
@Observable final class AirportDomain { }

// ❌ WRONG - Legacy ObservableObject
class AirportDomain: ObservableObject { @Published var x = 0 }

// ✅ CORRECT - Environment injection
@Environment(\.appState) private var state

// ❌ WRONG - EnvironmentObject
@EnvironmentObject var state: AppState
```

### 4. Logging & Crash Reporting

**Use RZUtilsSwift for logging:**
```swift
import RZUtilsSwift

final class AirportRepository {
    private let log = RZSLog(AirportRepository.self)
    
    func load() async throws {
        log.info("Loading airports...")
        // ...
    }
}
```

**Use Apple native crash reporting (MetricKit):**
- No third-party SDKs
- Configure `MXMetricManager` in `AppDelegate`
- Crashes automatically uploaded to App Store Connect

---

## Current State Assessment

### What Exists (Proof of Concept)

| Component | Status | Notes |
|-----------|--------|-------|
| Project setup | ✅ | Xcode project, targets, dependencies |
| RZFlight integration | ✅ | Package linked, KnownAirports working |
| AppModel | ✅ | Async initialization, database loading |
| AirportMapViewModel | ⚠️ | Basic, filters not functional |
| ContentView | ✅ | Adaptive layout detection |
| RegularLayout | ✅ | iPad/Mac side panel |
| CompactLayout | ✅ | iPhone overlay layout |
| SearchBar | ✅ | Basic search UI |
| FilterPanel | ⚠️ | UI only, not connected |
| SearchResultsList | ✅ | Basic results display |
| UI Airport struct | ⚠️ | Duplicate! Should use RZFlight.Airport |

### What Needs to Be Built

1. **Remove duplicate Airport model** - Use RZFlight.Airport directly
2. **Data Layer**: Repository pattern wrapping KnownAirports, remote data source
3. **FilterConfig**: App-specific filter state (pure data, filtering done by repository)
4. **Filters**: Connect FilterPanel to FilterConfig → KnownAirports filtering
5. **Details View**: Airport detail using airport.runways, procedures, aipEntries
6. **Route Search**: Use KnownAirports.airportsNearRoute()
7. **Chatbot**: Online (SSE) and offline (on-device LLM)
8. **Sync**: Database updates, cache management
9. **UI Polish**: Animations, legends, better markers

### Immediate Cleanup Required

The current PoC has a duplicate `Airport` struct in `AirportMapViewModel.swift`:

```swift
// ❌ CURRENT (wrong) - duplicates RZFlight.Airport
struct Airport: Identifiable {
    let name: String
    let icao: String
    let coordinate: CLLocationCoordinate2D
}

// ✅ SHOULD BE - use RZFlight directly
import RZFlight
// RZFlight.Airport already has all these + much more
```

---

## Phase 1: Foundation - Data Layer & RZFlight Integration

**Duration:** 2-3 weeks  
**Goal:** Solid data foundation using RZFlight models with offline/online abstraction

### 1.1 RZFlight Integration (NO NEW MODELS)

**Rule:** Use `RZFlight.Airport`, `RZFlight.Runway`, `RZFlight.Procedure`, `RZFlight.AIPEntry` directly.

**Tasks:**
- [ ] Verify RZFlight package is properly linked
- [ ] Ensure `KnownAirports` initializes correctly with bundled database
- [ ] Test all existing `KnownAirports` methods work as expected
- [ ] Document any missing functionality (for RZFlight enhancement)

**RZFlight provides (DO NOT DUPLICATE):**
- `Airport` with runways[], procedures[], aipEntries[]
- `Runway` with length_ft, surface, isHardSurface
- `Procedure` with procedureType, approachType, precisionCategory
- `AIPEntry` with section, field, value, standardField
- `KnownAirports` for all queries

### 1.2 App-Specific Types (Only What's Missing)

**File:** `App/Models/AppTypes.swift`

- [ ] **FilterConfig.swift** - Pure UI filter configuration (no DB dependencies)
  ```swift
  struct FilterConfig: Codable, Equatable, Sendable {
      var country: String?
      var hasProcedures: Bool?
      var hasHardRunway: Bool?
      var pointOfEntry: Bool?
      var minRunwayLengthFt: Int?
      // ...
      
      var hasActiveFilters: Bool { /* computed */ }
      
      // NOTE: No apply() method! 
      // Filtering is done by the repository.
  }
  ```

- [ ] **RouteResult.swift** - Route search result wrapper
- [ ] **MapHighlight.swift** - UI visualization
- [ ] **ConnectivityMode.swift** - Network state

**Deliverables:**
- Minimal app-specific types only
- FilterConfig as pure data struct (filtering done by repository)
- Unit tests for filter application

### 1.2 Repository Protocol

**File:** `App/Data/Repositories/AirportRepository.swift`

- [ ] Define `AirportRepositoryProtocol`
- [ ] Define all required methods
- [ ] Create async/throws signatures

### 1.3 Local Data Source (Using KnownAirports)

**File:** `App/Data/DataSources/LocalAirportDataSource.swift`

- [ ] Implement `AirportRepositoryProtocol`
- [ ] Wrap `KnownAirports` - DO NOT duplicate its logic
- [ ] Implement `applyInMemoryFilters()` using RZFlight Array extensions
- [ ] Return `RZFlight.Airport` directly (no mapping needed)

**Tasks:**
- [ ] Initialize `KnownAirports` from bundled database
- [ ] Implement `getAirports()` using KnownAirports + filter extensions
- [ ] Implement `searchAirports()` using `knownAirports.matching()`
- [ ] Implement `getAirportDetail()` using `knownAirports.airportWithExtendedData()`
- [ ] Implement `getAirportsNearRoute()` using `knownAirports.airportsNearRoute()`
- [ ] Implement `getAirportsNearLocation()` using `knownAirports.nearest(coord:count:)`

**Key Pattern:**
```swift
func airports(matching filters: FilterConfig, limit: Int) async throws -> [Airport] {
    var airports: [Airport]
    
    // Use KnownAirports for DB-dependent filters
    if filters.pointOfEntry == true {
        airports = knownAirports.airportsWithBorderCrossing()
    } else {
        airports = Array(knownAirports.known.values)
    }
    
    // Apply cheap in-memory filters (no DB access)
    airports = applyInMemoryFilters(filters, to: airports)
    
    return Array(airports.prefix(limit))
}

// Filtering lives in repository, NOT in FilterConfig
func applyInMemoryFilters(_ filters: FilterConfig, to airports: [Airport]) -> [Airport] {
    var result = airports
    if let country = filters.country { result = result.inCountry(country) }
    if filters.hasHardRunway == true { result = result.withHardRunways() }
    // ... other in-memory filters
    return result
}
```

### 1.4 Connectivity Monitor

**File:** `App/Services/ConnectivityMonitor.swift`

- [ ] Create `ConnectivityMonitor` using NWPathMonitor
- [ ] Publish connection state
- [ ] Distinguish WiFi vs cellular

```swift
import Network

@Observable
final class ConnectivityMonitor {
    var isConnected: Bool = false
    var connectionType: ConnectionType = .none
    
    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "connectivity")
    
    enum ConnectionType: Sendable {
        case none, wifi, cellular
    }
    
    func startMonitoring() {
        monitor.pathUpdateHandler = { [weak self] path in
            Task { @MainActor in
                self?.isConnected = path.status == .satisfied
                self?.connectionType = self?.mapConnectionType(path) ?? .none
            }
        }
        monitor.start(queue: queue)
    }
    
    private func mapConnectionType(_ path: NWPath) -> ConnectionType {
        if path.usesInterfaceType(.wifi) { return .wifi }
        if path.usesInterfaceType(.cellular) { return .cellular }
        return .none
    }
}
```

### 1.5 Filter Engine

**File:** `App/Data/Filtering/FilterEngine.swift`

- [ ] Port filter logic from web app
- [ ] Client-side filtering for local data
- [ ] Filter validation

---

## Phase 2: AppState with Composed Domains

**Duration:** 2 weeks  
**Goal:** Complete AppState with composed domains and functional filters

### 2.1 Domain Objects

**Note:** AppState composes smaller domain objects. NO monolithic God-class.

#### AirportDomain

**File:** `App/State/Domains/AirportDomain.swift`

- [ ] Create `AirportDomain` with `@Observable` macro
- [ ] Airport data state (airports, selected, search results)
- [ ] Filter state (pure data, no DB logic)
- [ ] Map state (position, legend, highlights, route)
- [ ] Actions: `load()`, `search()`, `select()`, `applyFilters()`

```swift
@Observable
@MainActor
final class AirportDomain {
    // Dependencies
    private let repository: AirportRepository
    
    // Airport Data (already filtered by repository)
    var airports: [Airport] = []
    var selectedAirport: Airport?
    var searchResults: [Airport] = []
    var isSearching: Bool = false
    
    // Filters (pure data, no DB logic)
    var filters: FilterConfig = .default
    
    // Map State
    var mapPosition: MapCameraPosition = .automatic
    var legendMode: LegendMode = .airportType
    var highlights: [String: MapHighlight] = [:]
    var activeRoute: RouteVisualization?
    
    // Actions
    func load() async throws {
        // Repository handles filtering (including DB-dependent ones)
        airports = try await repository.airports(matching: filters, limit: 1000)
    }
    func search(query: String) async throws { }
    func select(_ airport: Airport) { }
    func applyVisualization(_ payload: VisualizationPayload) { }
}
```

#### ChatDomain

**File:** `App/State/Domains/ChatDomain.swift`

- [ ] Create `ChatDomain` with `@Observable` macro
- [ ] Message state (messages, input, streaming)
- [ ] Cross-domain callback (`onVisualization`)
- [ ] Actions: `send()`, `clear()`

```swift
@Observable
@MainActor
final class ChatDomain {
    // Dependencies
    private var chatbotService: ChatbotService
    
    // State
    var messages: [ChatMessage] = []
    var input: String = ""
    var isStreaming: Bool = false
    var currentThinking: String?
    
    // Cross-domain callback
    var onVisualization: ((VisualizationPayload) -> Void)?
    
    // Actions
    func send() async { }
    func clear() { }
}
```

#### NavigationDomain

**File:** `App/State/Domains/NavigationDomain.swift`

- [ ] Create `NavigationDomain` with `@Observable` macro
- [ ] Navigation state (path, tabs, sheets)
- [ ] Actions: `navigate()`, `pop()`, `showChat()`, `showFilters()`

```swift
@Observable
@MainActor
final class NavigationDomain {
    var path = NavigationPath()
    var selectedTab: Tab = .map
    var showingChat: Bool = false
    var showingFilters: Bool = false
    
    enum Tab: String, CaseIterable { case map, search, chat, settings }
}
```

#### SystemDomain

**File:** `App/State/Domains/SystemDomain.swift`

- [ ] Create `SystemDomain` with `@Observable` macro
- [ ] System state (connectivity, loading, errors)
- [ ] Actions: `startMonitoring()`, `setLoading()`, `setError()`

```swift
@Observable
@MainActor
final class SystemDomain {
    var connectivityMode: ConnectivityMode = .offline
    var isLoading: Bool = false
    var error: AppError?
}
```

#### SettingsDomain

**File:** `App/State/Domains/SettingsDomain.swift`

- [ ] Create `SettingsDomain` with `@Observable` macro
- [ ] Use `@AppStorage` for all persisted preferences
- [ ] Unit preferences (distance, altitude, runway)
- [ ] Default filters and legend mode
- [ ] Session state (last map position, selected airport, tab)
- [ ] Behavior preferences (restore session, auto-sync)

```swift
@Observable
@MainActor
final class SettingsDomain {
    // Units
    @AppStorage("units.distance") var distanceUnit: DistanceUnit = .nauticalMiles
    @AppStorage("units.altitude") var altitudeUnit: AltitudeUnit = .feet
    
    // Defaults
    @AppStorage("defaults.legendMode") var defaultLegendMode: LegendMode = .airportType
    @AppStorage("defaults.filterOnlyProcedures") var defaultOnlyProcedures: Bool = false
    
    // Session
    @AppStorage("session.lastMapLatitude") var lastMapLatitude: Double = 50.0
    @AppStorage("session.lastSelectedAirport") var lastSelectedAirport: String = ""
    
    // Behavior
    @AppStorage("behavior.restoreSession") var restoreSessionOnLaunch: Bool = true
}
```

**Note:** Integrates with existing `Settings.swift` in the app.

### 2.2 AppState (Thin Orchestration)

**File:** `App/State/AppState.swift`

- [ ] Compose all domain objects
- [ ] Wire cross-domain callbacks
- [ ] Lifecycle methods (`onAppear`)
- [ ] Cross-domain orchestration actions

```swift
@Observable
@MainActor
final class AppState {
    // Composed domains
    let airports: AirportDomain
    let chat: ChatDomain
    let navigation: NavigationDomain
    let system: SystemDomain
    
    init(repository: AirportRepository, chatbotService: ChatbotService, connectivityMonitor: ConnectivityMonitor) {
        self.airports = AirportDomain(repository: repository)
        self.chat = ChatDomain(chatbotService: chatbotService)
        self.navigation = NavigationDomain()
        self.system = SystemDomain(connectivityMonitor: connectivityMonitor)
        
        // Wire cross-domain callbacks
        chat.onVisualization = { [weak self] payload in
            self?.airports.applyVisualization(payload)
        }
    }
    
    // Cross-domain actions
    func search(query: String) async { }
    func applyFiltersAndShow() async { }
}
```

### 2.3 Environment Setup

**File:** `App/State/AppStateEnvironment.swift`

- [ ] Create `AppStateKey` environment key
- [ ] Add `appState` to `EnvironmentValues`
- [ ] Inject in app entry point

```swift
struct AppStateKey: EnvironmentKey {
    static let defaultValue: AppState? = nil
}

extension EnvironmentValues {
    var appState: AppState? {
        get { self[AppStateKey.self] }
        set { self[AppStateKey.self] = newValue }
    }
}
```

### 2.4 Filter Binding Helpers

**File:** `App/Helpers/FilterBindings.swift`

- [ ] Create binding helpers for optional booleans
- [ ] Create binding helpers for optional integers

---

## Phase 3: UI Implementation

**Duration:** 2-3 weeks  
**Goal:** Complete, polished UI for all platforms

### 3.1 Map Enhancements

**File:** `UserInterface/Views/Map/`

- [ ] **AirportMapView.swift** - Enhanced map view
  - [ ] Region-based data loading (via `onMapCameraChange`)
  - [ ] Debounced region updates (300ms)
  - [ ] Legend mode-based marker colors
  - [ ] Route polyline rendering
  - [ ] Highlight circles
  - [ ] **MKClusterAnnotation** for dense areas (via UIViewRepresentable if needed)

- [ ] **ClusteredMapView.swift** - UIViewRepresentable for full clustering support
  - [ ] `AirportAnnotation` with `clusteringIdentifier`
  - [ ] `AirportAnnotationView` (MKMarkerAnnotationView subclass)
  - [ ] `ClusterAnnotationView` with count badge
  - [ ] Zoom to expand cluster on tap

**Map Performance Strategy:**
```swift
.onMapCameraChange(frequency: .onEnd) { context in
    state?.airports.onRegionChange(context.region)  // Triggers region-based load
}
```

**Repository must support:**
```swift
func airportsInRegion(boundingBox:filters:limit:) async throws -> [Airport]
```

- [ ] **AirportMarker.swift** - Custom marker view
  ```swift
  struct AirportMarker: View {
      let airport: Airport
      let legendMode: LegendMode
      
      var body: some View {
          ZStack {
              Circle()
                  .fill(markerColor)
                  .frame(width: 32, height: 32)
              Text(airport.icao)
                  .font(.caption2.bold())
                  .foregroundStyle(.white)
          }
      }
      
      var markerColor: Color {
          switch legendMode {
          case .airportType: return airportTypeColor
          case .procedurePrecision: return procedureColor
          case .runwayLength: return runwayLengthColor
          case .country: return countryColor
          }
      }
  }
  ```

- [ ] **MapLegend.swift** - Legend overlay

### 3.2 Filter Panel

**File:** `UserInterface/Views/Filters/`

- [ ] **FilterPanel.swift** - Complete filter UI
  - [ ] Country picker
  - [ ] Boolean toggles (border crossing, procedures, etc.)
  - [ ] Fuel toggles
  - [ ] Runway length stepper/slider
  - [ ] Reset button
  - [ ] Apply button (for API mode)

- [ ] **FilterChips.swift** - Active filter chips display

### 3.3 Airport Detail View

**File:** `UserInterface/Views/Detail/`

- [ ] **AirportDetailView.swift** - Main detail view
  - [ ] Header with name, ICAO, location
  - [ ] Tab view (Info, Runways, Procedures, AIP)

- [ ] **AirportInfoTab.swift** - Basic info tab
- [ ] **RunwaysTab.swift** - Runways list
- [ ] **ProceduresTab.swift** - Procedures grouped by type
- [ ] **AIPEntriesTab.swift** - AIP entries by section

### 3.4 Search Enhancement

**File:** `UserInterface/Views/Search/`

- [ ] **SearchBar.swift** - Update with route detection
- [ ] **SearchResultsView.swift** - Enhanced results
  - [ ] Group by type (exact match, route, location)
  - [ ] Show distance for route results

### 3.5 Layout Refinement

- [ ] **RegularLayout.swift** - Refine iPad/Mac layout
  - [ ] Proper NavigationSplitView
  - [ ] Sidebar with search + results
  - [ ] Inspector with filters/details

- [ ] **CompactLayout.swift** - Refine iPhone layout
  - [ ] Bottom sheet with detents
  - [ ] Floating search bar
  - [ ] Tab bar for switching content

### 3.6 Components

**File:** `UserInterface/Views/Components/`

- [ ] **ConnectivityBanner.swift** - Offline indicator
- [ ] **LoadingOverlay.swift** - Loading state
- [ ] **ErrorBanner.swift** - Error display
- [ ] **EmptyStateView.swift** - No results state

### 3.7 macOS-Specific Features

**Goal:** Make Mac version feel native, not "iPad on bigger screen"

**File:** `App/macOS/` (macOS-only)

- [ ] **Keyboard Shortcuts**
  - [ ] ⌘F - Focus search
  - [ ] ⌘L - Toggle filters
  - [ ] ⌘K - Toggle chat
  - [ ] ⌘, - Settings
  - [ ] ⌘1-4 - Tab switching

- [ ] **Menu Bar Items**
  - [ ] View menu (filters, chat, legend mode, zoom)
  - [ ] Map menu (clear route, center, reset)
  - [ ] Remove inapplicable items (New, etc.)

- [ ] **Multiple Windows**
  - [ ] Settings window (standard macOS pattern)
  - [ ] Route planning window (⇧⌘N)
  - [ ] Airport detail in new window

- [ ] **Mac-Specific Polish**
  - [ ] Window toolbar styling
  - [ ] Sidebar width customization
  - [ ] Context menus (right-click)
  - [ ] Drag & drop support

**Implementation Pattern:**
```swift
#if os(macOS)
// Mac-specific code
.commands { /* Menu bar */ }
Window("Route", id: "route") { /* New window type */ }
#endif
```

---

## Phase 4: Online Integration

**Duration:** 2 weeks  
**Goal:** Full API integration with fallback, converting all responses to RZFlight models

### 4.1 API Client

**File:** `App/Networking/`

- [ ] **APIClient.swift** - Base networking
  ```swift
  final class APIClient {
      let baseURL: URL
      let session: URLSession
      
      func request<T: Decodable>(_ endpoint: Endpoint) async throws -> T
      func streamSSE(_ endpoint: Endpoint) -> AsyncThrowingStream<SSEEvent, Error>
  }
  ```

- [ ] **Endpoint.swift** - Endpoint definitions
- [ ] **APIError.swift** - Error types

### 4.2 API Response Models (Internal)

**File:** `App/Networking/APIModels/`

These are **internal** models matching API JSON structure. Never exposed outside the adapter.

- [ ] **APIAirport.swift** - API airport response
- [ ] **APIRunway.swift** - API runway response
- [ ] **APIProcedure.swift** - API procedure response
- [ ] **APIAIPEntry.swift** - API AIP entry response
- [ ] **APIResponses.swift** - List/detail response wrappers

### 4.3 API → RZFlight Adapters

**File:** `App/Data/Adapters/`

**Critical:** All API responses MUST be converted to RZFlight models.

- [ ] **APIAirportAdapter.swift** - Convert APIAirport → RZFlight.Airport
  ```swift
  enum APIAirportAdapter {
      static func toRZFlight(_ api: APIAirport) -> Airport
      static func toRZFlightWithExtendedData(_ response: APIAirportDetailResponse) -> Airport
  }
  ```

- [ ] **APIRunwayAdapter.swift** - Convert APIRunway → RZFlight.Runway
- [ ] **APIProcedureAdapter.swift** - Convert APIProcedure → RZFlight.Procedure
- [ ] **APIAIPEntryAdapter.swift** - Convert APIAIPEntry → RZFlight.AIPEntry

**Pattern:**
```swift
// ✅ CORRECT: API response → Adapter → RZFlight model
func getAirports() async throws -> [Airport] {  // Returns RZFlight.Airport
    let response: APIAirportListResponse = try await apiClient.request(endpoint)
    return response.airports.map { APIAirportAdapter.toRZFlight($0) }
}

// ❌ WRONG: Exposing API models directly
func getAirports() async throws -> [APIAirport] {  // NO!
    return try await apiClient.request(endpoint)
}
```

### 4.4 RZFlight Initializer Proposals

If RZFlight models don't have convenient initializers for API data:

- [ ] Propose `Airport.init(icao:name:city:country:latitude:longitude:...)` to RZFlight
- [ ] Propose `Runway.init(length_ft:width_ft:surface:lighted:closed:le:he:)` to RZFlight
- [ ] Temporary workaround: Use internal extension until PR merged

**Temporary Extension (if needed):**
```swift
// App/Extensions/RZFlight+APIInit.swift
extension Airport {
    /// Temporary: API-friendly initializer (propose to RZFlight)
    static func fromAPI(
        icao: String,
        name: String,
        // ... other params
    ) -> Airport {
        // Build using available initializers
    }
}
```

### 4.5 Remote Data Source

**File:** `App/Data/DataSources/RemoteAirportDataSource.swift`

- [ ] Implement `AirportRepositoryProtocol`
- [ ] Use adapters to convert ALL responses to RZFlight models
- [ ] Return `RZFlight.Airport` (same as LocalDataSource)
- [ ] Handle pagination
- [ ] Error mapping

### 4.3 Unified Repository

**File:** `App/Data/Repositories/AirportRepository.swift`

- [ ] Implement strategy pattern for offline/online
- [ ] Add fallback logic
- [ ] Add caching layer
- [ ] Publish connectivity mode

### 4.4 Sync Service

**File:** `App/Services/SyncService.swift`

- [ ] Check for database updates
- [ ] Download new database
- [ ] Apply updates
- [ ] Track sync status

---

## Phase 5: Online Chatbot

**Duration:** 2-3 weeks  
**Goal:** Streaming chatbot with visualizations

### 5.1 Chat Models

**File:** `App/Models/Chat/`

- [ ] **ChatMessage.swift** - Message model
- [ ] **ChatEvent.swift** - Streaming events
- [ ] **VisualizationPayload.swift** - Visualization data

### 5.2 SSE Streaming

**File:** `App/Networking/SSEClient.swift`

- [ ] Implement SSE parsing
- [ ] Handle reconnection
- [ ] Parse event types (plan, thinking, message, ui_payload, done)

### 5.3 Online Chatbot Service

**File:** `App/Services/Chatbot/OnlineChatbotService.swift`

- [ ] Implement `ChatbotService` protocol
- [ ] Send messages via API
- [ ] Stream responses
- [ ] Handle visualizations

### 5.4 ChatDomain Integration

**File:** `App/State/Domains/ChatDomain.swift` (already created in Phase 2)

- [ ] Wire up `onVisualization` callback to `AirportDomain`
- [ ] Handle streaming state updates
- [ ] Manage conversation history
- [ ] Track thinking state for UI

**Note:** Chat logic lives in `ChatDomain`, NOT a separate ViewModel.

### 5.5 Chat UI

**File:** `UserInterface/Views/Chat/`

- [ ] **ChatView.swift** - Main chat view
- [ ] **ChatBubble.swift** - Message bubble
- [ ] **ChatInputBar.swift** - Input with send button
- [ ] **ThinkingIndicator.swift** - Typing/thinking state
- [ ] **VisualizationCard.swift** - Embedded visualization preview

---

## Phase 6: Offline Chatbot - Keyword Fallback (1.0)

**Duration:** 1-2 weeks  
**Goal:** Functional offline chatbot with keyword pattern matching (AI deferred to post-1.0)

### 6.1 Shared Tool Catalog

**File:** `App/Services/Chatbot/ToolCatalog.swift`

**Critical:** Same tool definitions as server to avoid grammar drift.

- [ ] Define `ToolCatalog` with all tool definitions
- [ ] Mirror server's `shared/aviation_agent/tools.py` schema
- [ ] Mark which tools are `availableOffline`
- [ ] Define parameter schemas for argument extraction

```swift
enum ToolCatalog {
    static let allTools: [ToolDefinition] = [
        searchAirports,
        getAirportInfo,
        findAirportsNearRoute,
        // ... mirrors server
    ]
    
    static var offlineTools: [ToolDefinition] {
        allTools.filter { $0.availableOffline }
    }
}
```

### 6.2 LLM Backend Protocol (Abstraction for Future)

**File:** `App/Services/Chatbot/LLMBackend.swift`

- [ ] Define `LLMBackend` protocol (swappable AI implementations)
- [ ] Implement `KeywordFallbackBackend` (pattern matching, no AI)
- [ ] Stub `AppleIntelligenceBackend` (POST-1.0)
- [ ] Stub `LlamaCppBackend` (POST-1.0, for small local models)

```swift
protocol LLMBackend: Sendable {
    static var isAvailable: Bool { get }
    func classifyIntent(message: String, availableTools: [ToolDefinition]) async throws -> IntentClassification
    func extractArguments(message: String, tool: ToolDefinition) async throws -> [String: Any]
}

// 1.0: This is the only implementation
final class KeywordFallbackBackend: LLMBackend {
    static var isAvailable: Bool { true }
    // Pattern matching for ICAO codes, route queries, etc.
}
```

### 6.3 Tool Executor

**File:** `App/Services/Chatbot/ToolExecutor.swift`

- [ ] Execute tools using repository
- [ ] Build `ToolResult` with visualization
- [ ] Handle all `ToolCatalog.offlineTools`

### 6.4 Offline Chatbot Service

**File:** `App/Services/Chatbot/OfflineChatbotService.swift`

- [ ] Implement `ChatbotService` protocol
- [ ] Use `LLMBackend` for intent classification
- [ ] Execute tools via `ToolExecutor`
- [ ] Generate template-based responses (1.0)
- [ ] Emit visualizations

### 6.5 Chatbot Service Factory

**File:** `App/Services/Chatbot/ChatbotServiceFactory.swift`

```swift
enum ChatbotServiceFactory {
    static func create(
        connectivity: ConnectivityMode,
        repository: AirportRepository,
        apiClient: APIClient
    ) -> any ChatbotService {
        switch connectivity {
        case .online, .hybrid:
            return OnlineChatbotService(apiClient: apiClient)
        case .offline:
            let backend = selectBestOfflineBackend()  // 1.0: Always KeywordFallbackBackend
            return OfflineChatbotService(backend: backend, repository: repository)
        }
    }
    
    private static func selectBestOfflineBackend() -> any LLMBackend {
        // POST-1.0: Check AppleIntelligence, llama.cpp, etc.
        return KeywordFallbackBackend()  // 1.0: Always this
    }
}
```

### 6.6 "Limited Offline Mode" UX

- [ ] Banner showing "Offline - Limited AI"
- [ ] Help text explaining what queries work
- [ ] Example prompts for pattern-matched queries
- [ ] Graceful handling of unrecognized queries

### 6.7 POST-1.0: AI Backend Implementation

**Not in 1.0 scope** - abstraction ready, implementation deferred:

| Backend | When to Add | Notes |
|---------|-------------|-------|
| `AppleIntelligenceBackend` | When API is stable + widely available | Device-gated |
| `LlamaCppBackend` | If we want consistent cross-device AI | Requires model download |
| `MLXBackend` | For Apple Silicon optimization | macOS focused |

**Decision criteria for shipping AI backend:**
1. API is stable (not changing every iOS release)
2. Works on >50% of target devices
3. Quality >= keyword fallback
4. Acceptable battery/thermal impact

---

## Phase 7: Polish & Testing

**Duration:** 2 weeks  
**Goal:** Production-ready quality

### 7.1 Performance

- [ ] Profile and optimize filter queries
- [ ] Lazy loading for large lists
- [ ] Tune MKClusterAnnotation thresholds
- [ ] Memory management
- [ ] Region-based loading performance tuning

### 7.2 Offline Experience

- [ ] Pre-cache map tiles for Europe
- [ ] Download manager UI
- [ ] Storage management
- [ ] Clear cache option

### 7.3 Error Handling

- [ ] Comprehensive error types
- [ ] User-friendly error messages
- [ ] Retry mechanisms
- [ ] Offline fallback UI

### 7.4 Accessibility

- [ ] VoiceOver labels
- [ ] Dynamic type support
- [ ] Reduce motion support
- [ ] Color contrast

### 7.5 App Store Preparation

- [ ] App icons (all sizes)
- [ ] Screenshots for all devices
- [ ] Privacy policy
- [ ] App Store description

---

## Testing Strategy

### Test Infrastructure

**Test Database:**
```
FlyFunEuroAIPTests/
├── Fixtures/
│   ├── test_airports.db        # Small DB with ~100 known airports
│   ├── test_airports.json      # Same data as JSON for unit tests
│   └── test_visualization.json # Sample visualization payloads
├── Helpers/
│   ├── TestFixtures.swift      # Airport/filter test data factory
│   ├── MockRepository.swift    # In-memory repository for unit tests
│   └── PreviewFactory.swift    # AppState factory for previews
└── ...
```

### 1. Filter Tests

**Goal:** Ensure FilterConfig produces same results as Python `euro_aip` filters.

**File:** `Tests/FilterTests.swift`

```swift
import XCTest
@testable import FlyFunEuroAIP
import RZFlight

final class FilterTests: XCTestCase {
    
    var testAirports: [Airport]!
    
    override func setUp() {
        // Load fixture airports with known properties
        testAirports = TestFixtures.airports
    }
    
    // MARK: - Country Filter
    
    func testFilterByCountry() {
        let filters = FilterConfig(country: "FR")
        let result = MockRepository.applyInMemoryFilters(filters, to: testAirports)
        
        XCTAssertTrue(result.allSatisfy { $0.country == "FR" })
        XCTAssertEqual(result.count, TestFixtures.frenchAirportCount)
    }
    
    // MARK: - Procedure Filters
    
    func testFilterHasProcedures() {
        let filters = FilterConfig(hasProcedures: true)
        let result = MockRepository.applyInMemoryFilters(filters, to: testAirports)
        
        XCTAssertTrue(result.allSatisfy { !$0.procedures.isEmpty })
        XCTAssertEqual(result.count, TestFixtures.airportsWithProceduresCount)
    }
    
    func testFilterPrecisionApproach() {
        // Airports with ILS/LPV approaches
        let airports = testAirports.withPrecisionApproaches()
        
        XCTAssertTrue(airports.allSatisfy { airport in
            airport.approaches.contains { $0.precisionCategory == .precision }
        })
    }
    
    // MARK: - Runway Filters
    
    func testFilterMinRunwayLength() {
        let filters = FilterConfig(minRunwayLengthFt: 3000)
        let result = MockRepository.applyInMemoryFilters(filters, to: testAirports)
        
        XCTAssertTrue(result.allSatisfy { airport in
            airport.runways.contains { $0.length_ft >= 3000 }
        })
    }
    
    func testFilterHardRunway() {
        let filters = FilterConfig(hasHardRunway: true)
        let result = MockRepository.applyInMemoryFilters(filters, to: testAirports)
        
        XCTAssertTrue(result.allSatisfy { airport in
            airport.runways.contains { $0.isHardSurface }
        })
    }
    
    // MARK: - Combined Filters
    
    func testCombinedFilters() {
        // French airports with IFR procedures and 2000ft+ runway
        let filters = FilterConfig(
            country: "FR",
            hasProcedures: true,
            minRunwayLengthFt: 2000
        )
        let result = MockRepository.applyInMemoryFilters(filters, to: testAirports)
        
        XCTAssertTrue(result.allSatisfy { airport in
            airport.country == "FR" &&
            !airport.procedures.isEmpty &&
            airport.runways.contains { $0.length_ft >= 2000 }
        })
    }
    
    // MARK: - Parity with Python euro_aip
    
    func testFilterParityWithPython() {
        // Test cases exported from Python euro_aip tests
        // Ensures Swift filters produce identical results
        
        let testCases: [(FilterConfig, Set<String>)] = [
            // (filters, expected ICAOs)
            (FilterConfig(country: "GB", hasProcedures: true), 
             Set(["EGLL", "EGKK", "EGGW", "EGCC"])),
            (FilterConfig(pointOfEntry: true, country: "FR"),
             Set(["LFPG", "LFPO", "LFML", "LFMN"])),
            // ... more test cases from Python
        ]
        
        for (filters, expectedICAOs) in testCases {
            let result = MockRepository.applyInMemoryFilters(filters, to: testAirports)
            let resultICAOs = Set(result.map(\.icao))
            
            XCTAssertEqual(resultICAOs, expectedICAOs, 
                "Filter mismatch: \(filters)")
        }
    }
}
```

### 2. Repository Integration Tests

**Goal:** Test LocalAirportDataSource with real SQLite queries.

**File:** `Tests/RepositoryTests.swift`

```swift
import XCTest
@testable import FlyFunEuroAIP
import RZFlight

final class RepositoryTests: XCTestCase {
    
    var repository: LocalAirportDataSource!
    
    override func setUp() async throws {
        // Use test database with known data
        let testDBPath = Bundle(for: Self.self).path(forResource: "test_airports", ofType: "db")!
        repository = try LocalAirportDataSource(databasePath: testDBPath)
    }
    
    // MARK: - Region Queries
    
    func testAirportsInRegion() async throws {
        // Bounding box around London
        let bbox = BoundingBox(
            minLatitude: 51.0, maxLatitude: 52.0,
            minLongitude: -1.0, maxLongitude: 1.0
        )
        
        let airports = try await repository.airportsInRegion(
            boundingBox: bbox, filters: .default, limit: 100
        )
        
        // Should include EGLL, EGKK, EGLC, etc.
        XCTAssertTrue(airports.contains { $0.icao == "EGLL" })
        XCTAssertTrue(airports.allSatisfy { bbox.contains($0.coord) })
    }
    
    // MARK: - Route Queries
    
    func testAirportsNearRoute() async throws {
        // EGTF (Fairoaks) to LFMD (Cannes)
        let result = try await repository.airportsNearRoute(
            from: "EGTF", to: "LFMD", distanceNm: 30, filters: .default
        )
        
        XCTAssertEqual(result.departure, "EGTF")
        XCTAssertEqual(result.destination, "LFMD")
        XCTAssertFalse(result.airports.isEmpty)
        
        // Should include airports along the route
        // (Paris area, Lyon area, etc.)
        let icaos = Set(result.airports.map(\.icao))
        XCTAssertTrue(icaos.contains("LFPG") || icaos.contains("LFPO"),
            "Should include Paris airports")
    }
    
    func testRouteWithFilters() async throws {
        // Only border crossings along route
        let result = try await repository.airportsNearRoute(
            from: "EGTF", to: "LFMD", distanceNm: 30,
            filters: FilterConfig(pointOfEntry: true)
        )
        
        // All results should be border crossings
        // (This requires DB access to verify)
        XCTAssertFalse(result.airports.isEmpty)
    }
    
    // MARK: - Search
    
    func testSearchByICAO() async throws {
        let results = try await repository.searchAirports(query: "EGLL", limit: 10)
        
        XCTAssertEqual(results.first?.icao, "EGLL")
    }
    
    func testSearchByName() async throws {
        let results = try await repository.searchAirports(query: "Heathrow", limit: 10)
        
        XCTAssertTrue(results.contains { $0.icao == "EGLL" })
    }
    
    func testSearchByCity() async throws {
        let results = try await repository.searchAirports(query: "London", limit: 50)
        
        // Should include multiple London airports
        let icaos = Set(results.map(\.icao))
        XCTAssertTrue(icaos.contains("EGLL"))  // Heathrow
        XCTAssertTrue(icaos.contains("EGLC"))  // City
    }
    
    // MARK: - Detail
    
    func testAirportDetail() async throws {
        let airport = try await repository.airportDetail(icao: "EGLL")
        
        XCTAssertNotNil(airport)
        XCTAssertEqual(airport?.icao, "EGLL")
        XCTAssertFalse(airport?.runways.isEmpty ?? true)
        XCTAssertFalse(airport?.procedures.isEmpty ?? true)
    }
}
```

### 3. Chat Visualization Tests

**Goal:** Ensure `applyVisualization` correctly updates AppState.

**File:** `Tests/VisualizationTests.swift`

```swift
import XCTest
@testable import FlyFunEuroAIP
import RZFlight

@MainActor
final class VisualizationTests: XCTestCase {
    
    var appState: AppState!
    
    override func setUp() async throws {
        appState = await PreviewFactory.makeAppState()
    }
    
    // MARK: - Markers Visualization
    
    func testMarkersVisualization() {
        let airports = TestFixtures.airports.prefix(10).map { $0 }
        let payload = VisualizationPayload(
            kind: .markers,
            airports: airports,
            route: nil,
            point: nil,
            filterProfile: nil
        )
        
        appState.airports.applyVisualization(payload)
        
        XCTAssertEqual(appState.airports.airports.count, 10)
        XCTAssertEqual(
            Set(appState.airports.airports.map(\.icao)),
            Set(airports.map(\.icao))
        )
    }
    
    // MARK: - Route Visualization
    
    func testRouteWithMarkersVisualization() {
        let airports = TestFixtures.airports.prefix(5).map { $0 }
        let route = RouteVisualization(
            coordinates: [
                CLLocationCoordinate2D(latitude: 51.5, longitude: -0.5),
                CLLocationCoordinate2D(latitude: 43.5, longitude: 7.0)
            ],
            departure: "EGTF",
            destination: "LFMD"
        )
        let payload = VisualizationPayload(
            kind: .routeWithMarkers,
            airports: airports,
            route: route,
            point: nil,
            filterProfile: nil
        )
        
        appState.airports.applyVisualization(payload)
        
        // Check route is set
        XCTAssertNotNil(appState.airports.activeRoute)
        XCTAssertEqual(appState.airports.activeRoute?.departure, "EGTF")
        XCTAssertEqual(appState.airports.activeRoute?.destination, "LFMD")
        
        // Check airports are set
        XCTAssertEqual(appState.airports.airports.count, 5)
        
        // Check highlights are created
        XCTAssertFalse(appState.airports.highlights.isEmpty)
        for airport in airports {
            XCTAssertNotNil(appState.airports.highlights["chat-\(airport.icao)"])
        }
    }
    
    // MARK: - Detail Visualization
    
    func testMarkerWithDetailsVisualization() {
        let airport = TestFixtures.airports.first!
        let payload = VisualizationPayload(
            kind: .markerWithDetails,
            airports: [airport],
            route: nil,
            point: nil,
            filterProfile: nil
        )
        
        appState.airports.applyVisualization(payload)
        
        XCTAssertEqual(appState.airports.selectedAirport?.icao, airport.icao)
    }
    
    // MARK: - Filter Profile Application
    
    func testFilterProfileApplication() {
        let filterConfig = FilterConfig(
            country: "FR",
            hasProcedures: true,
            minRunwayLengthFt: 2000
        )
        let payload = VisualizationPayload(
            kind: .markers,
            airports: [],
            route: nil,
            point: nil,
            filterProfile: filterConfig
        )
        
        appState.airports.applyVisualization(payload)
        
        XCTAssertEqual(appState.airports.filters.country, "FR")
        XCTAssertEqual(appState.airports.filters.hasProcedures, true)
        XCTAssertEqual(appState.airports.filters.minRunwayLengthFt, 2000)
    }
    
    // MARK: - Clearing State
    
    func testClearRoute() {
        // Setup: add a route
        appState.airports.activeRoute = RouteVisualization(
            coordinates: [], departure: "EGTF", destination: "LFMD"
        )
        appState.airports.highlights["route-1"] = MapHighlight(
            id: "route-1", coordinate: .init(latitude: 0, longitude: 0),
            color: .blue, radius: 1000, popup: nil
        )
        appState.airports.highlights["chat-EGLL"] = MapHighlight(
            id: "chat-EGLL", coordinate: .init(latitude: 0, longitude: 0),
            color: .blue, radius: 1000, popup: nil
        )
        
        appState.airports.clearRoute()
        
        XCTAssertNil(appState.airports.activeRoute)
        XCTAssertNil(appState.airports.highlights["route-1"])
        XCTAssertNotNil(appState.airports.highlights["chat-EGLL"])  // Chat highlights preserved
    }
}
```

### 4. Preview Infrastructure

**Goal:** Robust SwiftUI previews with realistic mock data.

**File:** `App/Preview/PreviewFactory.swift`

```swift
import SwiftUI
import RZFlight
import MapKit

/// Factory for creating preview-ready AppState and components
@MainActor
enum PreviewFactory {
    
    // MARK: - AppState
    
    /// Create AppState with mock data for previews
    static func makeAppState() -> AppState {
        let repository = MockRepository()
        let chatbot = MockChatbotService()
        let connectivity = MockConnectivityMonitor()
        
        let state = AppState(
            repository: repository,
            chatbotService: chatbot,
            connectivityMonitor: connectivity
        )
        
        // Pre-populate with sample data
        state.airports.airports = TestFixtures.airports
        state.airports.selectedAirport = TestFixtures.airports.first
        state.airports.mapPosition = .region(.europe)
        
        return state
    }
    
    /// Create AppState with chat messages
    static func makeAppStateWithChat() -> AppState {
        let state = makeAppState()
        
        state.chat.messages = [
            ChatMessage(role: .user, content: "Find airports near EGTF with ILS"),
            ChatMessage(role: .assistant, content: "I found 5 airports near Fairoaks with ILS approaches:\n\n1. **EGLL** - London Heathrow\n2. **EGKK** - London Gatwick\n..."),
        ]
        
        return state
    }
    
    /// Create AppState with active route
    static func makeAppStateWithRoute() -> AppState {
        let state = makeAppState()
        
        state.airports.activeRoute = RouteVisualization(
            coordinates: [
                CLLocationCoordinate2D(latitude: 51.3, longitude: -0.5),  // EGTF
                CLLocationCoordinate2D(latitude: 43.5, longitude: 7.0)   // LFMD
            ],
            departure: "EGTF",
            destination: "LFMD"
        )
        
        // Highlights along route
        state.airports.highlights = [
            "route-LFPG": MapHighlight(id: "route-LFPG", coordinate: .init(latitude: 49.0, longitude: 2.5), color: .blue, radius: 20000, popup: "Paris CDG"),
            "route-LFLY": MapHighlight(id: "route-LFLY", coordinate: .init(latitude: 45.7, longitude: 5.0), color: .blue, radius: 20000, popup: "Lyon")
        ]
        
        return state
    }
    
    // MARK: - Individual Components
    
    static var sampleAirport: Airport {
        TestFixtures.airports.first!
    }
    
    static var sampleAirportWithProcedures: Airport {
        TestFixtures.airports.first { !$0.procedures.isEmpty }!
    }
    
    static var sampleChatMessages: [ChatMessage] {
        [
            ChatMessage(role: .user, content: "What's EGLL?"),
            ChatMessage(role: .assistant, content: "**London Heathrow (EGLL)** is the busiest airport in the UK..."),
            ChatMessage(role: .user, content: "Show me airports between EGTF and LFMD"),
            ChatMessage(role: .assistant, content: "Here are airports along your route:", isStreaming: true)
        ]
    }
}

// MARK: - Mock Repository

final class MockRepository: AirportRepositoryProtocol {
    func airportsInRegion(boundingBox: BoundingBox, filters: FilterConfig, limit: Int) async throws -> [Airport] {
        TestFixtures.airports.filter { boundingBox.contains($0.coord) }.prefix(limit).map { $0 }
    }
    
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [Airport] {
        Array(TestFixtures.airports.prefix(limit))
    }
    
    func searchAirports(query: String, limit: Int) async throws -> [Airport] {
        TestFixtures.airports.filter { 
            $0.icao.contains(query.uppercased()) || 
            $0.name.localizedCaseInsensitiveContains(query)
        }.prefix(limit).map { $0 }
    }
    
    func airportDetail(icao: String) async throws -> Airport? {
        TestFixtures.airports.first { $0.icao == icao }
    }
    
    func airportsNearRoute(from: String, to: String, distanceNm: Int, filters: FilterConfig) async throws -> RouteResult {
        RouteResult(airports: Array(TestFixtures.airports.prefix(10)), departure: from, destination: to)
    }
    
    func airportsNearLocation(center: CLLocationCoordinate2D, radiusNm: Int, filters: FilterConfig) async throws -> [Airport] {
        Array(TestFixtures.airports.prefix(10))
    }
    
    func applyInMemoryFilters(_ filters: FilterConfig, to airports: [Airport]) -> [Airport] {
        // Simplified for preview
        airports
    }
    
    func countryRules(for countryCode: String) async throws -> CountryRules? { nil }
    func availableCountries() async throws -> [String] { ["GB", "FR", "DE", "IT", "ES"] }
    func filterMetadata() async throws -> FilterMetadata { FilterMetadata() }
}

// MARK: - Mock Chatbot

final class MockChatbotService: ChatbotService {
    var isOnline: Bool { false }
    var capabilities: ChatbotCapabilities { .fallback }
    
    func sendMessage(_ message: String) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.yield(.content("This is a mock response for: \(message)"))
            continuation.yield(.done(nil))
            continuation.finish()
        }
    }
    
    func clearHistory() {}
}

// MARK: - Mock Connectivity

final class MockConnectivityMonitor: ConnectivityMonitor {
    var modeStream: AsyncStream<ConnectivityMode> {
        AsyncStream { continuation in
            continuation.yield(.offline)
        }
    }
}
```

**File:** `App/Preview/TestFixtures.swift`

```swift
import RZFlight
import CoreLocation

/// Test data fixtures for unit tests and previews
enum TestFixtures {
    
    /// Sample airports with known properties for testing
    static let airports: [Airport] = [
        makeAirport(icao: "EGLL", name: "London Heathrow", city: "London", country: "GB",
                   lat: 51.4700, lon: -0.4543, elevation: 83,
                   hasProcedures: true, hasPrecision: true, runwayLength: 12800),
        makeAirport(icao: "EGKK", name: "London Gatwick", city: "London", country: "GB",
                   lat: 51.1481, lon: -0.1903, elevation: 202,
                   hasProcedures: true, hasPrecision: true, runwayLength: 10879),
        makeAirport(icao: "EGTF", name: "Fairoaks", city: "Chobham", country: "GB",
                   lat: 51.3481, lon: -0.5589, elevation: 80,
                   hasProcedures: false, hasPrecision: false, runwayLength: 2362),
        makeAirport(icao: "LFPG", name: "Charles de Gaulle", city: "Paris", country: "FR",
                   lat: 49.0097, lon: 2.5478, elevation: 392,
                   hasProcedures: true, hasPrecision: true, runwayLength: 13829),
        makeAirport(icao: "LFMD", name: "Cannes Mandelieu", city: "Cannes", country: "FR",
                   lat: 43.5420, lon: 6.9533, elevation: 13,
                   hasProcedures: true, hasPrecision: false, runwayLength: 5577),
        // ... more airports
    ]
    
    static let frenchAirportCount = airports.filter { $0.country == "FR" }.count
    static let airportsWithProceduresCount = airports.filter { !$0.procedures.isEmpty }.count
    
    private static func makeAirport(
        icao: String, name: String, city: String, country: String,
        lat: Double, lon: Double, elevation: Int,
        hasProcedures: Bool, hasPrecision: Bool, runwayLength: Int
    ) -> Airport {
        // Build using RZFlight Airport
        // Note: May need API-friendly initializer (proposed RZFlight enhancement)
        var airport = Airport(
            location: CLLocationCoordinate2D(latitude: lat, longitude: lon),
            icao: icao
        )
        // Set properties...
        return airport
    }
}
```

### 5. SwiftUI Preview Usage

```swift
// MARK: - Preview Examples

#Preview("Map View") {
    AirportMapView()
        .environment(\.appState, PreviewFactory.makeAppState())
}

#Preview("Map with Route") {
    AirportMapView()
        .environment(\.appState, PreviewFactory.makeAppStateWithRoute())
}

#Preview("Chat View") {
    ChatView()
        .environment(\.appState, PreviewFactory.makeAppStateWithChat())
}

#Preview("Airport Detail") {
    AirportDetailView(airport: PreviewFactory.sampleAirportWithProcedures)
        .environment(\.appState, PreviewFactory.makeAppState())
}

#Preview("Filter Panel") {
    FilterPanel()
        .environment(\.appState, PreviewFactory.makeAppState())
}

#Preview("Settings") {
    SettingsView()
        .environment(\.appState, PreviewFactory.makeAppState())
}
```

### Test Coverage Priorities

| Component | Priority | Test Type | Notes |
|-----------|----------|-----------|-------|
| FilterConfig + Repository filtering | **Critical** | Unit + Integration | Must match Python euro_aip |
| Visualization payload handling | **Critical** | Unit | Chat→Map integration |
| Route search | High | Integration | Complex spatial logic |
| Region-based loading | High | Integration | Map performance |
| Session restore | Medium | Unit | Settings persistence |
| Chat streaming | Medium | Integration | SSE parsing |
| Unit conversions | Low | Unit | Simple math |

### CI/CD Test Configuration

```yaml
# .github/workflows/tests.yml
- name: Run Tests
  run: |
    xcodebuild test \
      -scheme FlyFunEuroAIP \
      -destination 'platform=iOS Simulator,name=iPhone 15' \
      -testPlan UnitTests
      
- name: Run Integration Tests
  run: |
    xcodebuild test \
      -scheme FlyFunEuroAIP \
      -destination 'platform=iOS Simulator,name=iPhone 15' \
      -testPlan IntegrationTests
```

---

## File Structure (Target)

**Key Changes:**
- Core models from RZFlight (no duplicates)
- Single `AppState` composed of domain objects (no ViewModels folder)
- Modern SwiftUI patterns

```
app/FlyFunEuroAIP/
├── App/
│   ├── FlyFunEuroAIPApp.swift           # App entry point
│   ├── AppDelegate.swift                # MetricKit crash reporting
│   ├── Log.swift                        # Logging setup
│   │
│   ├── State/                           # Single source of truth
│   │   ├── AppState.swift               # Composes domains, orchestration
│   │   ├── AppStateEnvironment.swift    # Environment key
│   │   │
│   │   └── Domains/                     # Domain objects (~200-400 lines each)
│   │       ├── AirportDomain.swift      # Airports, filters, map state
│   │       ├── ChatDomain.swift         # Messages, streaming, LLM
│   │       ├── NavigationDomain.swift   # Tabs, sheets, path
│   │       ├── SystemDomain.swift       # Connectivity, loading, errors
│   │       └── SettingsDomain.swift     # User preferences, persisted state
│   │
│   ├── Models/                          # App-specific types ONLY
│   │   ├── FilterConfig.swift           # Filter state
│   │   ├── RouteResult.swift            # Route wrapper
│   │   ├── MapHighlight.swift           # Map viz
│   │   ├── LegendMode.swift             # Map legend
│   │   ├── ConnectivityMode.swift       # Network state
│   │   ├── AppError.swift               # Error types
│   │   └── Chat/
│   │       ├── ChatMessage.swift
│   │       ├── ChatEvent.swift
│   │       └── VisualizationPayload.swift
│   │   # NOTE: Airport, Runway, Procedure, AIPEntry from RZFlight
│   │
│   ├── Data/
│   │   ├── Repositories/
│   │   │   ├── AirportRepository.swift      # Protocol + unified impl
│   │   │   └── AirportRepositoryProtocol.swift
│   │   ├── DataSources/
│   │   │   ├── LocalAirportDataSource.swift   # Uses KnownAirports
│   │   │   └── RemoteAirportDataSource.swift  # API client
│   │   ├── Adapters/
│   │   │   └── APIAirportAdapter.swift        # API → RZFlight
│   │   └── Cache/
│   │       └── AIPCache.swift                 # File-based JSON cache
│   │
│   ├── Networking/
│   │   ├── APIClient.swift
│   │   ├── Endpoint.swift
│   │   ├── SSEClient.swift
│   │   └── APIModels/                    # Internal only
│   │       ├── APIAirport.swift
│   │       └── APIResponses.swift
│   │
│   ├── Services/
│   │   ├── ConnectivityMonitor.swift
│   │   ├── SyncService.swift
│   │   └── Chatbot/
│   │       ├── ChatbotService.swift          # Protocol
│   │       ├── OnlineChatbotService.swift    # SSE streaming
│   │       ├── OfflineChatbotService.swift   # Uses LLMBackend
│   │       ├── ToolCatalog.swift             # Shared tool definitions
│   │       ├── ToolExecutor.swift            # Local tool execution
│   │       ├── ChatbotServiceFactory.swift   # Factory
│   │       └── LLMBackends/
│   │           ├── LLMBackend.swift          # Protocol (swappable)
│   │           ├── KeywordFallbackBackend.swift  # 1.0: Pattern matching
│   │           ├── AppleIntelligenceBackend.swift # POST-1.0: Stub
│   │           └── LlamaCppBackend.swift     # POST-1.0: Stub
│   │
│   └── Helpers/
│       ├── FilterBindings.swift              # Binding helpers
│       └── CountryHelpers.swift              # Country names
│
├── UserInterface/
│   ├── ContentView.swift                     # Root view
│   │
│   ├── Layouts/                              # Adaptive layouts
│   │   ├── RegularLayout.swift               # iPad/Mac
│   │   └── CompactLayout.swift               # iPhone
│   │
│   ├── Map/
│   │   ├── AirportMapView.swift
│   │   ├── AirportMarker.swift
│   │   └── MapLegend.swift
│   │
│   ├── Search/
│   │   ├── SearchSidebar.swift
│   │   ├── SearchBarCompact.swift
│   │   └── SearchResultsList.swift
│   │
│   ├── Filters/
│   │   ├── FilterPanel.swift
│   │   └── FilterChips.swift
│   │
│   ├── Detail/
│   │   ├── AirportDetailView.swift
│   │   ├── AirportInfoSection.swift
│   │   ├── RunwaysSection.swift
│   │   ├── ProceduresSection.swift
│   │   └── AIPEntriesSection.swift
│   │
│   ├── Chat/
│   │   ├── ChatView.swift
│   │   ├── ChatBubble.swift
│   │   ├── ThinkingBubble.swift
│   │   └── FloatingChatButton.swift
│   │
│   ├── Settings/
│   │   └── SettingsView.swift           # User preferences UI
│   │
│   ├── Components/
│   │   ├── OfflineBanner.swift
│   │   ├── LoadingView.swift
│   │   └── ErrorView.swift
│   │
│   ├── ViewCoordinators/                # Optional: read-only projections
│   │   └── MapViewCoordinator.swift     # Complex view-specific computations
│   │
│   └── Preview/
│       ├── PreviewFactory.swift         # AppState factory for previews
│       └── TestFixtures.swift           # Sample data for tests/previews
│
├── Assets.xcassets/
├── Data/
│   └── airports.db                           # Bundled database
└── Development Assets/
    └── airports_small.db                     # Preview database

FlyFunEuroAIPTests/
├── Fixtures/
│   ├── test_airports.db                 # Small test DB (~100 airports)
│   ├── test_airports.json               # Same data as JSON
│   └── test_visualizations.json         # Sample payloads
├── Helpers/
│   ├── MockRepository.swift             # In-memory repository
│   └── MockChatbotService.swift         # Mock chatbot
├── FilterTests.swift                    # FilterConfig tests
├── RepositoryTests.swift                # LocalAirportDataSource tests
├── VisualizationTests.swift             # applyVisualization tests
├── SettingsTests.swift                  # SettingsDomain tests
└── ChatDomainTests.swift                # Chat streaming tests
```

**Architecture Choices:**
- ✅ `State/Domains/` - Composed domain objects (200-400 lines each)
- ✅ `AppState.swift` - Thin orchestration layer
- ✅ `ViewCoordinators/` - Optional read-only projections for complex view logic

**Removed:**
- ❌ `ViewModels/` folder - NO standalone ViewModels
- ❌ `AppModel.swift` - replaced by AppState
- ❌ Duplicate model files - use RZFlight

---

## Dependencies

### Current (Keep)
- **RZFlight** - Airport data, KnownAirports, spatial queries
  - Provides: `Airport`, `Runway`, `Procedure`, `AIPEntry`, `KnownAirports`
  - Source: [github.com/roznet/rzflight](https://github.com/roznet/rzflight)
- **RZUtilsSwift** - Logging, utilities
- **FMDB** - SQLite access (used by RZFlight)

### Add
- **None required** - Using native Apple frameworks

### Optional (Consider)
- **SwiftLint** - Code style enforcement
- **Quick/Nimble** - BDD testing (if preferred)

---

## RZFlight Enhancement Tracking

When implementing features, if functionality exists in `euro_aip` (Python) but not in RZFlight:

1. **Don't implement in the app** - propose RZFlight enhancement
2. **Track here** until implemented
3. **Workaround if needed** - use local extension temporarily

### Proposed Enhancements

| Feature | Python Reference | Priority | Workaround |
|---------|-----------------|----------|------------|
| **API-friendly initializers** | For API → RZFlight | **Critical** | Extension in app |
| **Bounding box query** | For map performance | **High** | Filter `known.values` (O(n)) |
| Fuel filtering (AVGAS/Jet-A) | `has_avgas`, `has_jet_a` | High | AIP entry search |
| Landing fee filtering | `max_landing_fee` | Medium | AIP entry search |
| Country list | `get_countries()` | High | SQL query |
| Airport count by country | `count_by_country()` | Low | Compute locally |

### Bounding Box Query (High Priority for Map Performance)

RZFlight has a KDTree for spatial indexing. Expose it for efficient region queries:

```swift
// Proposed addition to KnownAirports
extension KnownAirports {
    /// Get airports within a geographic bounding box
    /// Uses KDTree for O(log n) spatial query instead of O(n) scan
    func airports(in boundingBox: BoundingBox) -> [Airport] {
        // Use existing KDTree to find airports in region
    }
}
```

**Current workaround:** Filter `known.values` - O(n) for each region change
**With enhancement:** O(log n + k) where k = results

### API-Friendly Initializers (Critical for Phase 4)

RZFlight models currently use `FMResultSet` initializers. For API responses, we need:

```swift
// Needed in RZFlight
Airport.init(icao:name:city:country:latitude:longitude:elevation_ft:type:...)
Runway.init(length_ft:width_ft:surface:lighted:closed:le:he:)
Procedure.init(name:procedureType:approachType:runwayIdent:...)
AIPEntry.init(ident:section:field:value:...)
```

**Workaround until merged:** Define extensions in `App/Extensions/RZFlight+APIInit.swift`

### How to Propose Enhancement

```bash
# 1. Clone RZFlight
git clone https://github.com/roznet/rzflight

# 2. Add feature following existing patterns
# 3. Add tests
# 4. Submit PR
```

---

## Milestones & Timeline

| Phase | Duration | Milestone | Key Deliverable |
|-------|----------|-----------|-----------------|
| Phase 1 | Week 1-2 | Data layer + RZFlight integration | `AirportRepository` working |
| Phase 2 | Week 3-4 | `AppState` with composed domains | Domain objects + orchestration |
| Phase 3 | Week 5-7 | UI complete (all platforms) | Adaptive layouts working |
| Phase 4 | Week 8-9 | Online API integration | Live data + sync |
| Phase 5 | Week 10-11 | Online chatbot | `ChatDomain` + SSE + viz |
| Phase 6 | Week 12 | Offline chatbot (keyword fallback) | Pattern matching + tool execution |
| Phase 7 | Week 13-14 | Polish + Testing | App Store ready |

**Total: ~14 weeks (3.5 months)**

### POST-1.0 Roadmap

| Feature | When | Dependency |
|---------|------|------------|
| Apple Intelligence backend | iOS 18.x stable | API maturity |
| llama.cpp / local LLM | User demand | Model download UX |
| Advanced offline AI | Both above | User testing |

### Reduced Timeline Rationale

| Simplification | Time Saved |
|----------------|------------|
| Composed domains vs monolith | Better testability (not time saved, but quality) |
| Latest iOS only (no compat) | 1 week |
| Apple Intelligence vs custom LLM | 2 weeks |
| Modern SwiftUI patterns | 1 week |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| On-device LLM performance | Medium | High | Test early, have fallback to simple Q&A |
| API changes | Low | Medium | Version API, handle gracefully |
| Large database size | Medium | Medium | Incremental sync, compression |
| Memory constraints (iPhone) | Medium | High | Lazy loading, proper cleanup |
| Apple Intelligence availability | High | Medium | Support alternative (Core ML) |

---

## Next Steps

### Decisions Made ✅

| Decision | Choice |
|----------|--------|
| iOS Version | 18.0+ (latest only) |
| State Management | Single `AppState` composed of domain objects |
| ViewModels | Eliminated (use domain objects) |
| Architecture | Redux-style single store, but composed to avoid God-class |
| Offline Chatbot | Apple Intelligence |

### Immediate Actions

1. **Update Xcode project**
   - Set deployment target to iOS 18.0 / macOS 15.0
   - Enable Swift 6 mode
   - Remove any legacy code

2. **Remove duplicate Airport model**
   - Delete local `Airport` struct from `AirportMapViewModel.swift`
   - Use `RZFlight.Airport` directly

3. **Create domain objects**
   - New folder: `App/State/Domains/`
   - `AirportDomain.swift` - airports, filters, map state
   - `ChatDomain.swift` - messages, streaming
   - `NavigationDomain.swift` - tabs, sheets
   - `SystemDomain.swift` - connectivity, errors

4. **Create AppState (orchestration)**
   - New file: `App/State/AppState.swift`
   - Compose domain objects
   - Wire cross-domain callbacks

5. **Setup Environment injection**
   - Create `AppStateKey`
   - Inject in app entry point

6. **Start Phase 1**
   - Repository protocol
   - Local data source wrapping KnownAirports

---

## Related Documents

- `designs/IOS_APP_DESIGN.md` - Architecture and design
- `designs/UI_FILTER_STATE_DESIGN.md` - Web state patterns (reference)
- `designs/CHATBOT_WEBUI_DESIGN.md` - Chatbot patterns (reference)

