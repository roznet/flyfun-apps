# FlyFun EuroAIP iOS App - Implementation Plan

## Overview

This document provides a detailed implementation roadmap for the FlyFun EuroAIP iOS/macOS app. It breaks down the design into actionable phases with specific tasks, dependencies, and deliverables.

**Reference:** `designs/IOS_APP_DESIGN.md` for architecture and design decisions.

---

## Platform Requirements

| Platform | Version | Rationale |
|----------|---------|-----------|
| **iOS** | 18.0+ | `@Observable`, SwiftData, Apple Intelligence |
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
3. **FilterConfig**: App-specific filter state with apply() using RZFlight extensions
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
- FilterConfig with apply() using RZFlight extensions
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
- [ ] Use `FilterConfig.apply()` with RZFlight Array extensions
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
final class ConnectivityMonitor: ObservableObject {
    @Published var isConnected: Bool = false
    @Published var connectionType: ConnectionType = .none
    
    enum ConnectionType {
        case none, wifi, cellular
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
  - [ ] Legend mode-based marker colors
  - [ ] Route polyline rendering
  - [ ] Highlight circles
  - [ ] Annotation clustering (for large datasets)

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

## Phase 6: Offline Chatbot (Apple Intelligence)

**Duration:** 2-3 weeks  
**Goal:** On-device chatbot using Apple Intelligence

### 6.1 Apple Intelligence Integration

**Approach:** Use Apple Intelligence APIs (iOS 18.1+) for:
- Intent understanding
- Response generation
- Token streaming

**Fallback:** Keyword-based matching when Apple Intelligence unavailable

### 6.2 Offline Tool Registry

**File:** `App/Services/Chatbot/OfflineToolRegistry.swift`

- [ ] Define available offline tools
- [ ] `search_airports` - Local search
- [ ] `get_airport_info` - Airport details
- [ ] `find_airports_near_route` - Route search
- [ ] `find_airports_in_country` - Country filter
- [ ] Map tool results to visualizations

```swift
final class OfflineToolRegistry {
    private let repository: LocalAirportDataSource
    
    enum Tool: String, CaseIterable {
        case searchAirports = "search_airports"
        case getAirportInfo = "get_airport_info"
        case findAirportsNearRoute = "find_airports_near_route"
        case findAirportsInCountry = "find_airports_in_country"
    }
    
    func execute(_ tool: Tool, arguments: [String: Any]) async throws -> ToolResult
}
```

### 6.3 Offline Chatbot Service

**File:** `App/Services/Chatbot/OfflineChatbotService.swift`

- [ ] Implement `ChatbotService` protocol
- [ ] Use Apple Intelligence for intent classification
- [ ] Execute local tools
- [ ] Generate responses with context
- [ ] Stream tokens to UI

### 6.4 Intent Understanding

- [ ] Route queries: "airports between EGTF and LFMD"
- [ ] Airport info: "tell me about EGKB"
- [ ] Filter queries: "airports with ILS in France"
- [ ] General questions: answered from cached knowledge

### 6.5 Fallback Mode (No Apple Intelligence)

**File:** `App/Services/Chatbot/KeywordChatbotService.swift`

- [ ] Pattern matching for common queries
- [ ] Direct tool execution
- [ ] Template-based responses
- [ ] Clear "Limited offline mode" UX

### 6.6 Chatbot Service Factory

**File:** `App/Services/Chatbot/ChatbotServiceFactory.swift`

```swift
enum ChatbotServiceFactory {
    static func create(
        connectivity: ConnectivityMode,
        repository: AirportRepository
    ) -> ChatbotService {
        switch connectivity {
        case .online, .hybrid:
            return OnlineChatbotService(...)
        case .offline:
            if AppleIntelligence.isAvailable {
                return OfflineChatbotService(...)
            } else {
                return KeywordChatbotService(...)
            }
        }
    }
}
```

---

## Phase 7: Polish & Testing

**Duration:** 2 weeks  
**Goal:** Production-ready quality

### 7.1 Performance

- [ ] Profile and optimize filter queries
- [ ] Lazy loading for large lists
- [ ] Map marker clustering
- [ ] Memory management for LLM

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

### 7.5 Testing

- [ ] Unit tests for models
- [ ] Unit tests for view models
- [ ] Unit tests for repository
- [ ] UI tests for critical flows
- [ ] Performance tests

### 7.6 App Store Preparation

- [ ] App icons (all sizes)
- [ ] Screenshots for all devices
- [ ] Privacy policy
- [ ] App Store description

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
│   │       └── SystemDomain.swift       # Connectivity, loading, errors
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
│   │       └── AirportCache.swift             # SwiftData cache
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
│   │       ├── OfflineChatbotService.swift   # Apple Intelligence
│   │       ├── OfflineToolRegistry.swift     # Local tools
│   │       └── ChatbotServiceFactory.swift   # Factory
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
│   ├── Components/
│   │   ├── OfflineBanner.swift
│   │   ├── LoadingView.swift
│   │   └── ErrorView.swift
│   │
│   ├── ViewCoordinators/                # Optional: read-only projections
│   │   └── MapViewCoordinator.swift     # Complex view-specific computations
│   │
│   └── Preview/
│       └── PreviewHelpers.swift              # Preview providers
│
├── Assets.xcassets/
├── Data/
│   └── airports.db                           # Bundled database
└── Development Assets/
    └── airports_small.db                     # Preview database
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
| Fuel filtering (AVGAS/Jet-A) | `has_avgas`, `has_jet_a` | High | AIP entry search |
| Landing fee filtering | `max_landing_fee` | Medium | AIP entry search |
| Country list | `get_countries()` | High | SQL query |
| Airport count by country | `count_by_country()` | Low | Compute locally |

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
| Phase 6 | Week 12-13 | Offline chatbot | Apple Intelligence |
| Phase 7 | Week 14-15 | Polish + Testing | App Store ready |

**Total: ~15 weeks (4 months)**

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

