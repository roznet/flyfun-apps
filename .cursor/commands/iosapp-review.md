# FlyFun EuroAIP iOS App Architecture Review

## Overview
Review code changes in `app/FlyFunEuroAIP/` to ensure compliance with our iOS app architecture as defined in `designs/IOS_APP_DESIGN.md`. Verify RZFlight model reuse, composed AppState pattern, repository abstraction, and platform-specific UI patterns.

## Architecture Rules

1. **RZFlight Model Reuse (CRITICAL)** - Use RZFlight models directly:
   - Use `RZFlight.Airport`, `RZFlight.Runway`, `RZFlight.Procedure`, `RZFlight.AIPEntry`
   - NO duplicate model types in the app
   - Query through `KnownAirports`, not raw SQL
   - Extend RZFlight library, not the app, when functionality is missing

2. **Composed AppState** - Single source of truth:
   - `AppState` composes domain objects (`AirportDomain`, `ChatDomain`, `NavigationDomain`, `SystemDomain`, `SettingsDomain`)
   - Each domain ~200-400 lines, no 2000+ line God-class
   - Cross-domain coordination via explicit callbacks
   - Injected via `@Environment(\.appState)`

3. **No ViewModels** - Domains replace ViewModels:
   - NO standalone `*ViewModel.swift` files
   - View-specific logic goes in domains or thin ViewCoordinators
   - ViewCoordinators are structs with computed properties only (no stored state)

4. **Repository Pattern** - Abstract offline/online sources:
   - `AirportRepositoryProtocol` defines unified API
   - `LocalAirportDataSource` uses `KnownAirports`
   - `RemoteAirportDataSource` converts API → RZFlight via adapters
   - Repository returns `RZFlight.Airport` directly, not app-specific types

5. **FilterConfig is Pure Data** - No DB dependencies:
   - `FilterConfig` is a simple `Codable` struct
   - NO `apply(to:db:)` method in FilterConfig
   - Filtering logic lives in repository/data source
   - FilterConfig only stores filter values

6. **API → RZFlight Adapters** - Single model type:
   - API response models are internal only
   - `APIAirportAdapter.toRZFlight()` converts immediately
   - Never expose `APIAirport` outside adapters
   - Ensures one model type throughout the app

7. **Region-Based Data Loading** - Map performance:
   - `airportsInRegion(boundingBox:filters:limit:)` is primary for map
   - Debounce region changes (300ms)
   - Limit markers (500 max per region)
   - Prefetch with padding factor (1.3x)

8. **File-Based Caching** - No SwiftData:
   - Simple JSON files for AIP cache
   - No complex persistence framework
   - Cache in `Caches/` directory (purgeable)
   - Documents for synced database only

9. **Chatbot Service Abstraction** - Swappable backends:
   - `ChatbotService` protocol for online/offline
   - `LLMBackend` protocol for AI backends
   - `KeywordFallbackBackend` for 1.0 offline
   - Shared `ToolCatalog` between modes

10. **Platform-Specific UI** - Adaptive layouts:
    - iPhone: Bottom sheet + floating controls
    - iPad/Mac: NavigationSplitView + Inspector
    - macOS: Keyboard shortcuts, menu bar, multiple windows
    - Use `@Environment(\.horizontalSizeClass)`

11. **Modern Swift Only** - iOS 18.0+ / macOS 15.0+:
    - `@Observable` macro (no `ObservableObject`)
    - `@Environment` injection (no `@EnvironmentObject`)
    - `async/await` everywhere (no Combine)
    - Modern MapKit with `Map { }` builder

12. **DB is Canonical Source** - Local SQLite is truth:
    - API is read-only view over same data
    - Never write API data back to local DB
    - Full DB replacement for sync (no deltas)
    - AIP entries can be cached (supplement, not replace)

## Review Checklist

### 1. RZFlight Model Reuse
- [ ] Uses `RZFlight.Airport`, not app-defined `Airport`?
- [ ] Uses `RZFlight.Runway`, `RZFlight.Procedure`, `RZFlight.AIPEntry`?
- [ ] Queries through `KnownAirports`, not raw SQL?
- [ ] No duplicate model types in `App/Models/`?
- [ ] Extensions proposed to RZFlight for missing features?

### 2. Composed AppState
- [ ] `AppState` composes domain objects?
- [ ] Each domain is ~200-400 lines max?
- [ ] Cross-domain coordination via callbacks (`chat.onVisualization`)?
- [ ] `@Observable` on all domains?
- [ ] `@MainActor` on domains that touch UI?

### 3. No ViewModels
- [ ] No `*ViewModel.swift` files in project?
- [ ] Views access domains via `@Environment(\.appState)`?
- [ ] View-specific logic in domains or ViewCoordinators?
- [ ] ViewCoordinators are structs with computed properties only?

### 4. Repository Pattern
- [ ] `AirportRepositoryProtocol` defines unified API?
- [ ] Local data source uses `KnownAirports`?
- [ ] Remote data source uses adapters?
- [ ] Repository returns RZFlight types directly?
- [ ] No mixing of data sources in views?

### 5. FilterConfig Purity
- [ ] `FilterConfig` is pure `Codable` struct?
- [ ] No `apply(to:)` method with DB parameter?
- [ ] Filtering logic in repository/data source?
- [ ] `hasActiveFilters` computed property exists?

### 6. API Adapters
- [ ] API response models marked internal?
- [ ] `APIAirportAdapter` converts to RZFlight?
- [ ] No `APIAirport` exposed outside adapters?
- [ ] Adapters handle missing/optional fields gracefully?

### 7. Map Performance
- [ ] Uses `airportsInRegion()` for map display?
- [ ] Region changes debounced?
- [ ] Marker limit enforced?
- [ ] Prefetch padding applied?

### 8. Caching Strategy
- [ ] Uses simple JSON files for caching?
- [ ] No SwiftData or Core Data?
- [ ] Cache in `Caches/` directory?
- [ ] Handles cache purge gracefully?

### 9. Chatbot Architecture
- [ ] `ChatbotService` protocol exists?
- [ ] `LLMBackend` protocol for AI swapping?
- [ ] Shared `ToolCatalog` used?
- [ ] Online/offline implementations separate?

### 10. Platform Adaptations
- [ ] `CompactLayout` for iPhone?
- [ ] `RegularLayout` for iPad/Mac?
- [ ] Uses `horizontalSizeClass` for detection?
- [ ] macOS keyboard shortcuts defined?

### 11. Modern Swift Patterns
- [ ] Uses `@Observable` (no `ObservableObject`)?
- [ ] Uses `@Environment` (no `@EnvironmentObject`)?
- [ ] Uses `async/await` (no Combine)?
- [ ] Uses modern MapKit `Map { }` builder?

### 12. Data Integrity
- [ ] Local DB is source of truth?
- [ ] API data not written to local DB?
- [ ] Sync uses full replacement?
- [ ] Schema version checked before replacement?

## Red Flags to Flag

Flag these violations immediately:

- 🔴 **Duplicate models**: Creating `Airport`, `Runway`, etc. in app instead of using RZFlight
- 🔴 **ViewModel files**: Any `*ViewModel.swift` file in the project
- 🔴 **God-class AppState**: Single file >500 lines without domain composition
- 🔴 **Direct SQL queries**: Using `FMDatabase` directly instead of `KnownAirports`
- 🔴 **FilterConfig with DB logic**: `apply(to:db:)` method in FilterConfig
- 🔴 **Exposed API models**: `APIAirport` used outside adapter files
- 🔴 **SwiftData usage**: Any `@Model` or SwiftData imports
- 🔴 **ObservableObject**: Using `ObservableObject` instead of `@Observable`
- 🔴 **Combine imports**: Using Combine for state management
- 🔴 **All airports loaded**: Loading all 10K+ airports at once for map
- 🔴 **Direct state mutation**: `state.airports = ...` instead of method call
- 🔴 **Missing cross-domain wiring**: Chatbot visualization not updating map

## Review Process

1. **Analyze changed files** in `app/FlyFunEuroAIP/`
2. **Check imports** - should see `import RZFlight`, no `import Combine`
3. **Verify model usage** - search for `RZFlight.Airport` vs local `Airport`
4. **Check state management** - domains composed in AppState?
5. **Verify repository pattern** - data access through repository?
6. **Check UI patterns** - adaptive layouts, environment injection?
7. **Identify violations** with specific file paths and line numbers
8. **Suggest fixes** with code examples showing corrected approach

## Output Format

For each finding:

**✅ APPROVED:**
- `file:line` - Brief explanation of why it's correct
- Example: `AirportDomain.swift:45` - Uses `RZFlight.Airport` correctly, queries via `KnownAirports`

**❌ VIOLATION:**
- `file:line` - Description of violation
- **Problem:** Why it violates architecture
- **Fix:** Suggested corrected implementation
- **Impact:** What breaks (performance, maintainability, etc.)

Example violation:
```
❌ VIOLATION:
Models/Airport.swift:1
- Issue: Created duplicate Airport model instead of using RZFlight.Airport
- Problem: Violates "RZFlight Model Reuse" rule, will cause type conflicts
- Fix: Delete this file, use `import RZFlight` and `RZFlight.Airport` directly
- Impact: Type duplication, maintenance burden, conversion overhead
```

## Approved Patterns Reference

**RZFlight Model Usage:**
```swift
// ✅ GOOD: Use RZFlight types directly
import RZFlight

let airport: Airport  // This is RZFlight.Airport
let runways: [Runway]  // This is [RZFlight.Runway]

// ❌ BAD: Create app-level duplicates
struct AppAirport {  // Don't create this!
    let icao: String
    let name: String
}
```

**Composed AppState:**
```swift
// ✅ GOOD: Compose domain objects
@Observable
@MainActor
final class AppState {
    let airports: AirportDomain
    let chat: ChatDomain
    let navigation: NavigationDomain
    let system: SystemDomain
    let settings: SettingsDomain
    
    // Thin orchestration only
    func onAppear() async { ... }
}

// ❌ BAD: Monolithic state
@Observable
final class AppState {
    var airports: [Airport] = []
    var selectedAirport: Airport?
    var filters: FilterConfig = .default
    var mapPosition: MapCameraPosition = .automatic
    var chatMessages: [ChatMessage] = []
    var isStreaming: Bool = false
    // ... 50 more properties
    // ... 2000 lines of methods
}
```

**Domain Pattern:**
```swift
// ✅ GOOD: Domain with focused responsibility
@Observable
@MainActor
final class AirportDomain {
    private let repository: AirportRepository
    
    var airports: [Airport] = []
    var selectedAirport: Airport?
    var filters: FilterConfig = .default
    
    func select(_ airport: Airport) {
        selectedAirport = airport
        focusMap(on: airport.coord)
    }
}

// ❌ BAD: Standalone ViewModel
class AirportMapViewModel: ObservableObject {  // Don't do this!
    @Published var airports: [Airport] = []
}
```

**Repository Pattern:**
```swift
// ✅ GOOD: Repository returns RZFlight types
protocol AirportRepositoryProtocol {
    func airports(matching filters: FilterConfig, limit: Int) async throws -> [Airport]
}

// ❌ BAD: Repository returns app-specific types
protocol AirportRepositoryProtocol {
    func airports() async throws -> [AppAirport]  // Wrong type!
}
```

**FilterConfig Purity:**
```swift
// ✅ GOOD: Pure data struct
struct FilterConfig: Codable, Equatable, Sendable {
    var country: String?
    var hasProcedures: Bool?
    var minRunwayLengthFt: Int?
    
    var hasActiveFilters: Bool {
        country != nil || hasProcedures != nil || minRunwayLengthFt != nil
    }
}

// ❌ BAD: FilterConfig with DB logic
struct FilterConfig {
    func apply(to airports: [Airport], db: FMDatabase) -> [Airport] {  // Don't do this!
        // DB-dependent logic should be in repository
    }
}
```

**Region-Based Loading:**
```swift
// ✅ GOOD: Load only visible region
func onRegionChange(_ region: MKCoordinateRegion) {
    regionUpdateTask?.cancel()
    regionUpdateTask = Task {
        try? await Task.sleep(for: .milliseconds(300))  // Debounce
        guard !Task.isCancelled else { return }
        airports = try await repository.airportsInRegion(
            boundingBox: region.paddedBy(factor: 1.3).boundingBox,
            filters: filters,
            limit: 500
        )
    }
}

// ❌ BAD: Load all airports
func load() async throws {
    airports = try await repository.allAirports()  // 10K+ airports!
}
```

**Environment Injection:**
```swift
// ✅ GOOD: Use @Environment
struct AirportMapView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Map { ... }
            .onTapGesture {
                state?.airports.select(airport)
            }
    }
}

// ❌ BAD: Use @StateObject or @EnvironmentObject
struct AirportMapView: View {
    @StateObject private var viewModel = AirportMapViewModel()  // Don't do this!
    @EnvironmentObject var appState: AppState  // Don't do this!
}
```

**API Adapters:**
```swift
// ✅ GOOD: Convert immediately, internal only
internal struct APIAirport: Decodable { ... }  // Internal

enum APIAirportAdapter {
    static func toRZFlight(_ api: APIAirport) -> Airport {
        Airport(location: CLLocationCoordinate2D(...), icao: api.ident)
    }
}

// Usage in data source
let airports = response.airports.map { APIAirportAdapter.toRZFlight($0) }

// ❌ BAD: Expose API types
public struct APIAirport: Decodable { ... }  // Don't expose!

func getAirports() async throws -> [APIAirport] {  // Wrong return type!
    ...
}
```

## Key Files to Review

### Core Architecture
- `App/State/AppState.swift` - Composed domains?
- `App/State/Domains/*.swift` - Each domain ~200-400 lines?
- `App/Data/AirportRepository.swift` - Returns RZFlight types?
- `App/Data/DataSources/*.swift` - Proper abstraction?

### Model Usage
- `App/Models/*.swift` - Should be minimal (app-specific only)
- Any imports of `RZFlight` - Should be present
- Any `struct Airport` - Should NOT exist (use RZFlight.Airport)

### UI Layer
- `App/Views/*.swift` - Uses `@Environment(\.appState)`?
- `App/Views/Map/*.swift` - Region-based loading?
- No `*ViewModel.swift` files

### Caching
- `App/Data/Cache/*.swift` - File-based JSON only?
- No SwiftData imports

## Things to Ensure

✅ **DO:**
- Import and use RZFlight models directly
- Compose AppState from domain objects
- Use repository pattern for data access
- Keep FilterConfig as pure data
- Convert API responses to RZFlight immediately
- Use region-based loading for maps
- Use @Observable and @Environment
- Implement platform-specific UI

## Things to Avoid

❌ **DON'T:**
- Create duplicate model types
- Create ViewModel files
- Put DB logic in FilterConfig
- Expose API response types
- Load all airports for map
- Use ObservableObject or Combine
- Use SwiftData
- Mix data sources in views
- Create monolithic AppState

## Notes

- Focus on architecture compliance, not code style
- Flag even minor violations to prevent pattern drift
- Reference `designs/IOS_APP_DESIGN.md` for full design details
- Check RZFlight source for available models and methods
- Verify against `src/euro-aip/Sources/RZFlight/` for RZFlight API
- Be constructive - suggest fixes, don't just point out problems

