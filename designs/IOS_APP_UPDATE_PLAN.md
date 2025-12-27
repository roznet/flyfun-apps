# iOS App Update Plan: Web App Synchronization

## Executive Summary

This document outlines the plan to synchronize the iOS app with the web app, specifically around:
1. **Filter system alignment** - Add missing filter fields and complete ChatFilters mapping
2. **UI payload enhancements** - Support all visualization types, fix filter reload behavior
3. **Notification support** - Display and filter by notification requirements using bundled DB

**Priority Order:** Filters → UI Payload → Notifications

**Key Architecture Decision:** Notifications will use a **NotificationService** that loads from bundled `ga_notifications.db` (offline-first), with optional API refresh when online.

---

## 1. Current State Analysis

### 1.1 FilterConfig Status

FilterConfig already has most fields. Only 3 fields are missing:

| Filter | iOS FilterConfig | iOS applyInMemoryFilters | Gap |
|--------|-----------------|-------------------------|-----|
| `country` | ✅ | ✅ | - |
| `hasProcedures` | ✅ | ✅ | - |
| `hasHardRunway` | ✅ | ✅ | - |
| `hasLightedRunway` | ✅ | ✅ | - |
| `pointOfEntry` | ✅ | ✅ (DB query) | - |
| `minRunwayLengthFt` | ✅ | ✅ | - |
| `maxRunwayLengthFt` | ✅ | ✅ | - |
| `hasILS` | ✅ | ❌ **Add** | Missing filter logic |
| `hasRNAV` | ✅ | ❌ **Add** | Missing filter logic |
| `hasPrecisionApproach` | ✅ | ✅ | - |
| `aipField` | ✅ | ✅ (DB query) | - |
| `hasAvgas` | ❌ **Add** | ❌ **Add** | New field + logic |
| `hasJetA` | ❌ **Add** | ❌ **Add** | New field + logic |
| `maxLandingFee` | ❌ **Add** | ❌ **Add** | New field + logic |

### 1.2 ChatFilters Mapping Status

Current `ChatFilters` only maps 5 fields. Need to add mapping for ALL FilterConfig fields:

| API Field | ChatFilters | toFilterConfig() | Status |
|-----------|-------------|------------------|--------|
| `country` | ✅ | ✅ | OK |
| `has_procedures` | ✅ | ✅ | OK |
| `has_hard_runway` | ✅ | ✅ | OK |
| `point_of_entry` | ✅ | ✅ | OK |
| `min_runway_length_ft` | ✅ | ✅ | OK |
| `has_lighted_runway` | ❌ | ❌ | **Add** |
| `max_runway_length_ft` | ❌ | ❌ | **Add** |
| `has_ils` | ❌ | ❌ | **Add** |
| `has_rnav` | ❌ | ❌ | **Add** |
| `has_precision_approach` | ❌ | ❌ | **Add** |
| `has_avgas` | ❌ | ❌ | **Add** (new) |
| `has_jet_a` | ❌ | ❌ | **Add** (new) |
| `max_landing_fee` | ❌ | ❌ | **Add** (new) |

### 1.3 applyVisualization Bug

**Current behavior** (`AirportDomain.swift:304-306`):
```swift
if let chatFilters = chatPayload.filters {
    filters = chatFilters.toFilterConfig()  // Sets filters but DOESN'T reload!
}
```

**Problem:** Filters are set but `loadAirportsInRegion()` is NOT called, so map doesn't update.

**Web behavior:**
1. If filters present: Apply filters → Reload ALL matching airports → Highlight specific airports
2. If no filters: Just show the specific airports returned

### 1.4 Legend Mode Comparison

| Legend Mode | Web App | iOS App | Notes |
|-------------|---------|---------|-------|
| `airportType` | ✅ | ✅ | - |
| `procedurePrecision` | ✅ | ✅ | - |
| `runwayLength` | ✅ | ✅ | - |
| `country` | ✅ | ✅ | - |
| `relevance` | ✅ | ❌ | GA Friendliness - Phase 4+ |
| `notification` | ✅ | ❌ | **Add** in Phase 3 |

### 1.5 Notification System

**Backend Status:** Fully implemented
- LLM-based extraction from AIP field 302
- Stored in `ga_notifications.db` (409KB, bundled in `/data/`)
- API returns `parsed_notification` and `notification_confidence` in airport details

**iOS Status:** No implementation, but DB is already bundled

**Database Schema:**
```sql
CREATE TABLE notifications (
    icao TEXT PRIMARY KEY,
    rule_type TEXT,           -- 'customs' | 'immigration'
    notification_type TEXT,   -- 'hours' | 'h24' | 'on_request' | 'business_day'
    hours_notice INTEGER,
    operating_hours_start TEXT,
    operating_hours_end TEXT,
    weekday_rules TEXT,       -- JSON
    schengen_rules TEXT,      -- JSON
    contact_info TEXT,        -- JSON
    summary TEXT,
    raw_text TEXT,
    confidence REAL,
    llm_response TEXT
);
```

---

## 2. Notification Architecture Decision

### Decision: NotificationService with Local DB

Given the app's **offline-first principle**, notifications will use a service that:
1. Loads from bundled `ga_notifications.db` at startup (offline support)
2. Provides fast local lookups (important for legend mode)
3. Optionally refreshes from API when online (fresh data)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NotificationService                           │
├─────────────────────────────────────────────────────────────────────┤
│  Primary: Bundled ga_notifications.db (offline, fast)               │
│  Optional: API refresh when viewing details (online, fresh)         │
├─────────────────────────────────────────────────────────────────────┤
│  Methods:                                                           │
│  - getNotification(icao:) -> NotificationInfo?        // Single     │
│  - getNotifications(icaos:) -> [String: NotificationInfo]  // Batch │
│  - refreshFromAPI(icao:) async -> NotificationInfo?   // Online     │
│  - preloadAll() async                                 // Startup    │
└─────────────────────────────────────────────────────────────────────┘
```

**Why this approach:**
| Concern | Solution |
|---------|----------|
| Offline support | Bundled DB works without network |
| Performance | Local lookups for legend mode (100+ airports) |
| Fresh data | Optional API refresh for details view |
| Consistency | Follows KnownAirports pattern |

**Data flow:**
```
App Launch
    ↓
NotificationService.init(dbPath: "ga_notifications.db")
    ↓
preloadAll() → Cache in memory
    ↓
AirportDomain requests notification
    ↓
getNotification(icao:) → Return from cache
    ↓
(Optional) Airport Detail View
    ↓
refreshFromAPI(icao:) → Update cache with fresh data
```

---

## 3. Implementation Phases

### Phase 1: Filter System Alignment (Low Risk)

**Goal:** Complete FilterConfig, fix ChatFilters mapping, add missing filter logic.

**Duration:** 1-2 days

#### 1.1 Add Missing Fields to FilterConfig

**File:** `app/FlyFunEuroAIP/App/Models/FilterConfig.swift`

```swift
// Add to FilterConfig struct:

// MARK: - Fuel Filters (NEW)
var hasAvgas: Bool?
var hasJetA: Bool?

// MARK: - Fee Filters (NEW)
var maxLandingFee: Double?
```

**Update computed properties:**
- `hasActiveFilters` - Add checks for new fields
- `activeFilterCount` - Add counts for new fields
- `description` - Add descriptions for new fields

#### 1.2 Complete ChatFilters Mapping

**File:** `app/FlyFunEuroAIP/App/Models/Chat/VisualizationPayload.swift`

```swift
struct ChatFilters: Sendable {
    // Existing (already parsed)
    let country: String?
    let hasProcedures: Bool?
    let hasHardRunway: Bool?
    let pointOfEntry: Bool?
    let minRunwayLengthFt: Int?

    // Add parsing for existing FilterConfig fields
    let hasLightedRunway: Bool?
    let maxRunwayLengthFt: Int?
    let hasILS: Bool?
    let hasRNAV: Bool?
    let hasPrecisionApproach: Bool?

    // Add parsing for new FilterConfig fields
    let hasAvgas: Bool?
    let hasJetA: Bool?
    let maxLandingFee: Double?

    init(from dict: [String: Any]) {
        // Existing
        self.country = dict["country"] as? String ?? dict["iso_country"] as? String
        self.hasProcedures = dict["has_procedures"] as? Bool
        self.hasHardRunway = dict["has_hard_runway"] as? Bool
        self.pointOfEntry = dict["point_of_entry"] as? Bool
        self.minRunwayLengthFt = dict["min_runway_length_ft"] as? Int

        // Add these
        self.hasLightedRunway = dict["has_lighted_runway"] as? Bool
        self.maxRunwayLengthFt = dict["max_runway_length_ft"] as? Int
        self.hasILS = dict["has_ils"] as? Bool
        self.hasRNAV = dict["has_rnav"] as? Bool
        self.hasPrecisionApproach = dict["has_precision_approach"] as? Bool
        self.hasAvgas = dict["has_avgas"] as? Bool
        self.hasJetA = dict["has_jet_a"] as? Bool
        self.maxLandingFee = dict["max_landing_fee"] as? Double
    }

    func toFilterConfig() -> FilterConfig {
        var config = FilterConfig()
        config.country = country
        config.hasProcedures = hasProcedures
        config.hasHardRunway = hasHardRunway
        config.pointOfEntry = pointOfEntry
        config.minRunwayLengthFt = minRunwayLengthFt
        // Add all the new mappings
        config.hasLightedRunway = hasLightedRunway
        config.maxRunwayLengthFt = maxRunwayLengthFt
        config.hasILS = hasILS
        config.hasRNAV = hasRNAV
        config.hasPrecisionApproach = hasPrecisionApproach
        config.hasAvgas = hasAvgas
        config.hasJetA = hasJetA
        config.maxLandingFee = maxLandingFee
        return config
    }
}
```

#### 1.3 Add Missing Filter Logic in Repository

**File:** `app/FlyFunEuroAIP/App/Data/DataSources/LocalAirportDataSource.swift`

Current `applyInMemoryFilters` is missing: `hasILS`, `hasRNAV`, `hasAvgas`, `hasJetA`, `maxLandingFee`

```swift
func applyInMemoryFilters(_ filters: FilterConfig, to airports: [RZFlight.Airport]) -> [RZFlight.Airport] {
    var result = airports

    // ... existing filters ...

    // Add ILS/RNAV filtering (use RZFlight if available, else filter by procedures)
    if filters.hasILS == true {
        result = result.filter { airport in
            airport.procedures.contains { $0.approachType == .ils }
        }
    }
    if filters.hasRNAV == true {
        result = result.filter { airport in
            airport.procedures.contains { $0.approachType == .rnav }
        }
    }

    // Fuel filtering - requires AIP field lookup or RZFlight enhancement
    // Phase 1: Skip (document as limitation)
    // Phase 4+: Add to RZFlight or parse AIP entries

    // Landing fee filtering - requires AIP field parsing
    // Phase 1: Skip (document as limitation)

    return result
}
```

**Note:** Fuel and landing fee filtering require either:
- RZFlight enhancement (preferred, Phase 4+)
- AIP entry parsing in app (fallback)

For Phase 1, document as limitation and implement in later phase.

#### 1.4 Update Filter UI

**File:** `app/FlyFunEuroAIP/App/Views/Filters/FilterPanelContent.swift`

Add UI controls for new filters (show only when data available):

```swift
// Fuel section (future - when filtering is implemented)
Section("Fuel") {
    Toggle("AVGAS Available", isOn: boolFilterBinding(\.hasAvgas))
    Toggle("Jet-A Available", isOn: boolFilterBinding(\.hasJetA))
}
```

#### Testing Phase 1

- [ ] Unit tests for FilterConfig new fields
- [ ] Unit tests for ChatFilters parsing ALL fields
- [ ] Unit tests for ChatFilters.toFilterConfig() mapping
- [ ] Test ILS/RNAV filtering in applyInMemoryFilters
- [ ] Integration test: chatbot sends filters → iOS applies them

---

### Phase 2: UI Payload Enhancements (Medium Complexity)

**Goal:** Fix applyVisualization reload bug, add suggested queries support.

**Duration:** 2-3 days

#### 2.1 Fix applyVisualization Filter Reload Bug

**File:** `app/FlyFunEuroAIP/App/State/Domains/AirportDomain.swift`

**Current (broken):**
```swift
if let chatFilters = chatPayload.filters {
    filters = chatFilters.toFilterConfig()  // Sets but doesn't reload!
}
```

**Fixed:**
```swift
func applyVisualization(_ chatPayload: ChatVisualizationPayload) {
    Logger.app.info("Applying chat visualization: \(chatPayload.kind.rawValue)")

    // Clear previous chat highlights
    clearChatHighlights()

    // Check if we have meaningful filters
    if let chatFilters = chatPayload.filters {
        let newFilters = chatFilters.toFilterConfig()
        if newFilters.hasActiveFilters {
            // MODE 1: Filters present - apply and reload ALL matching airports
            self.filters = newFilters
            Task {
                // Reload airports with new filters
                if let region = visibleRegion {
                    try? await loadAirportsInRegion(region)
                } else {
                    try? await load()
                }

                // Then add highlights for specific airports from chat
                if let markers = chatPayload.visualization?.markers {
                    for marker in markers {
                        let id = "chat-\(marker.icao)"
                        highlights[id] = MapHighlight(
                            id: id,
                            coordinate: marker.coordinate.clLocationCoordinate,
                            color: colorForMarkerStyle(marker.style),
                            radius: 15000,
                            popup: marker.name ?? marker.icao
                        )
                    }
                }
            }
            return
        }
    }

    // MODE 2: No meaningful filters - just show specific airports
    // ... existing implementation for visualization handling ...
}
```

#### 2.2 Add Suggested Queries Support

**File:** `app/FlyFunEuroAIP/App/Models/Chat/VisualizationPayload.swift`

```swift
/// Follow-up query suggestion from chatbot
struct SuggestedQuery: Sendable, Identifiable, Equatable {
    let id: String
    let text: String
    let tool: String?
    let category: String?
    let priority: Int?

    init?(from dict: [String: Any]) {
        guard let text = dict["text"] as? String else { return nil }
        self.id = UUID().uuidString
        self.text = text
        self.tool = dict["tool"] as? String
        self.category = dict["category"] as? String
        self.priority = dict["priority"] as? Int
    }
}

// Add to ChatVisualizationPayload:
struct ChatVisualizationPayload: Sendable {
    // ... existing fields ...

    /// Follow-up query suggestions
    let suggestedQueries: [SuggestedQuery]?

    init(from dict: [String: Any]) {
        // ... existing parsing ...

        // Parse suggested queries (top-level field, not in visualization)
        if let queries = dict["suggested_queries"] as? [[String: Any]] {
            self.suggestedQueries = queries.compactMap { SuggestedQuery(from: $0) }
        } else {
            self.suggestedQueries = nil
        }
    }
}
```

#### 2.3 Add Suggested Queries to ChatDomain

**File:** `app/FlyFunEuroAIP/App/State/Domains/ChatDomain.swift`

```swift
@Observable
@MainActor
final class ChatDomain {
    // ... existing properties ...

    /// Follow-up query suggestions from last response
    var suggestedQueries: [SuggestedQuery] = []

    func handleEvent(_ event: ChatEvent) {
        switch event {
        // ... existing cases ...

        case .uiPayload(let payload):
            // Capture suggested queries
            if let queries = payload.suggestedQueries {
                self.suggestedQueries = queries
            } else {
                self.suggestedQueries = []
            }
            onVisualization?(payload)

        // ... rest of cases ...
        }
    }

    /// Clear suggestions when starting new message
    func clearSuggestions() {
        suggestedQueries = []
    }
}
```

#### 2.4 Display Suggested Queries in Chat UI

**File:** `app/FlyFunEuroAIP/UserInterface/Views/Chat/SuggestedQueriesView.swift` (NEW)

```swift
import SwiftUI

struct SuggestedQueriesView: View {
    let queries: [SuggestedQuery]
    let onSelect: (SuggestedQuery) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(queries) { query in
                    Button {
                        onSelect(query)
                    } label: {
                        Text(query.text)
                            .font(.caption)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.accentColor.opacity(0.1))
                            .foregroundColor(.accentColor)
                            .cornerRadius(16)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)
        }
    }
}
```

**Integrate into ChatView:**
```swift
// After message list, before input bar:
if !chat.suggestedQueries.isEmpty && !chat.isStreaming {
    SuggestedQueriesView(queries: chat.suggestedQueries) { query in
        chat.input = query.text
        chat.clearSuggestions()
        Task { await chat.send() }
    }
}
```

#### Testing Phase 2

- [ ] Test applyVisualization reloads airports when filters present
- [ ] Test applyVisualization preserves highlights after reload
- [ ] Unit tests for SuggestedQuery parsing
- [ ] UI tests for suggested queries display
- [ ] Integration test: user taps suggestion → chat sends query

---

### Phase 3: Notification Support (Higher Complexity)

**Goal:** Add NotificationService, display notifications, add legend mode.

**Duration:** 3-5 days

#### 3.1 Create NotificationInfo Model

**File:** `app/FlyFunEuroAIP/App/Models/NotificationInfo.swift` (NEW)

```swift
import Foundation

/// Notification requirements for an airport
/// Data comes from bundled ga_notifications.db
struct NotificationInfo: Codable, Sendable, Equatable {
    /// Type of rule
    enum RuleType: String, Codable, Sendable {
        case customs
        case immigration
    }

    /// Type of notification requirement
    enum NotificationType: String, Codable, Sendable, CaseIterable {
        case hours       // Requires X hours notice
        case h24         // 24/7 available, no notice needed
        case onRequest   // Available on request
        case businessDay // Business day notice required
        case unavailable // Not available

        var displayName: String {
            switch self {
            case .h24: return "24/7"
            case .hours: return "Notice Required"
            case .onRequest: return "On Request"
            case .businessDay: return "Business Day"
            case .unavailable: return "Unavailable"
            }
        }
    }

    let icao: String
    let ruleType: RuleType
    let notificationType: NotificationType
    let hoursNotice: Int?
    let operatingHoursStart: String?
    let operatingHoursEnd: String?
    let summary: String
    let confidence: Double
    let contactPhone: String?
    let contactEmail: String?

    /// Color for legend mode
    var legendColor: LegendColor {
        switch notificationType {
        case .h24: return .green
        case .hours:
            guard let hours = hoursNotice else { return .orange }
            if hours <= 24 { return .blue }
            if hours <= 48 { return .orange }
            return .red
        case .onRequest: return .orange
        case .businessDay: return .orange
        case .unavailable: return .red
        }
    }

    enum LegendColor {
        case green, blue, orange, red, gray
    }

    /// Formatted display string
    var displaySummary: String {
        var parts: [String] = []

        switch notificationType {
        case .h24:
            parts.append("24/7 - No notice required")
        case .hours:
            if let hours = hoursNotice {
                parts.append("\(hours)h notice required")
            }
        case .onRequest:
            parts.append("Available on request")
        case .businessDay:
            parts.append("Business day notice required")
        case .unavailable:
            parts.append("Not available")
        }

        if let start = operatingHoursStart, let end = operatingHoursEnd,
           !start.isEmpty, !end.isEmpty {
            parts.append("Hours: \(formatTime(start))-\(formatTime(end))")
        }

        if let phone = contactPhone, !phone.isEmpty {
            parts.append("Tel: \(phone)")
        }

        return parts.joined(separator: "\n")
    }

    private func formatTime(_ hhmm: String) -> String {
        guard hhmm.count >= 4 else { return hhmm }
        let h = hhmm.prefix(2)
        let m = hhmm.dropFirst(2).prefix(2)
        return "\(h):\(m)"
    }
}
```

#### 3.2 Create NotificationService

**File:** `app/FlyFunEuroAIP/App/Services/NotificationService.swift` (NEW)

```swift
import Foundation
import FMDB
import OSLog

/// Service for accessing airport notification requirements
/// Uses bundled ga_notifications.db (offline-first) with optional API refresh
final class NotificationService: @unchecked Sendable {
    private let db: FMDatabase
    private var cache: [String: NotificationInfo] = [:]
    private let cacheQueue = DispatchQueue(label: "notification.cache")

    init(databasePath: String) throws {
        let db = FMDatabase(path: databasePath)
        guard db.open() else {
            throw AppError.databaseOpenFailed(path: databasePath)
        }
        self.db = db
        Logger.app.info("NotificationService initialized")
    }

    /// Preload all notifications into cache (call at startup)
    func preloadAll() async {
        let query = """
            SELECT icao, rule_type, notification_type, hours_notice,
                   operating_hours_start, operating_hours_end,
                   summary, confidence, contact_info
            FROM notifications
            WHERE confidence > 0.5
        """

        guard let results = db.executeQuery(query, withArgumentsIn: []) else {
            Logger.app.error("Failed to query notifications")
            return
        }

        var loaded = 0
        while results.next() {
            if let notification = parseRow(results) {
                cacheQueue.sync {
                    cache[notification.icao] = notification
                }
                loaded += 1
            }
        }
        results.close()
        Logger.app.info("Preloaded \(loaded) notifications")
    }

    /// Get notification for single airport (fast, from cache)
    func getNotification(icao: String) -> NotificationInfo? {
        cacheQueue.sync {
            cache[icao]
        }
    }

    /// Batch get notifications (for legend mode)
    func getNotifications(icaos: [String]) -> [String: NotificationInfo] {
        cacheQueue.sync {
            var result: [String: NotificationInfo] = [:]
            for icao in icaos {
                if let notification = cache[icao] {
                    result[icao] = notification
                }
            }
            return result
        }
    }

    /// Check if notification data exists for airport
    func hasNotification(icao: String) -> Bool {
        cacheQueue.sync {
            cache[icao] != nil
        }
    }

    private func parseRow(_ rs: FMResultSet) -> NotificationInfo? {
        guard let icao = rs.string(forColumn: "icao"),
              let ruleTypeStr = rs.string(forColumn: "rule_type"),
              let notifTypeStr = rs.string(forColumn: "notification_type"),
              let summary = rs.string(forColumn: "summary") else {
            return nil
        }

        guard let ruleType = NotificationInfo.RuleType(rawValue: ruleTypeStr),
              let notifType = NotificationInfo.NotificationType(rawValue: notifTypeStr) else {
            return nil
        }

        // Parse contact info JSON
        var phone: String?
        var email: String?
        if let contactJson = rs.string(forColumn: "contact_info"),
           let data = contactJson.data(using: .utf8),
           let contact = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            phone = contact["phone"] as? String
            email = contact["email"] as? String
        }

        return NotificationInfo(
            icao: icao,
            ruleType: ruleType,
            notificationType: notifType,
            hoursNotice: rs.columnIsNull("hours_notice") ? nil : Int(rs.int(forColumn: "hours_notice")),
            operatingHoursStart: rs.string(forColumn: "operating_hours_start"),
            operatingHoursEnd: rs.string(forColumn: "operating_hours_end"),
            summary: summary,
            confidence: rs.double(forColumn: "confidence"),
            contactPhone: phone,
            contactEmail: email
        )
    }
}
```

#### 3.3 Integrate NotificationService into App

**File:** `app/FlyFunEuroAIP/App/State/AppState.swift`

```swift
@Observable
@MainActor
final class AppState {
    // ... existing domains ...

    /// Notification service (loaded from bundled DB)
    let notificationService: NotificationService?

    init() {
        // ... existing init ...

        // Initialize notification service
        if let notifPath = Bundle.main.path(forResource: "ga_notifications", ofType: "db") {
            do {
                notificationService = try NotificationService(databasePath: notifPath)
                Task {
                    await notificationService?.preloadAll()
                }
            } catch {
                Logger.app.error("Failed to initialize NotificationService: \(error)")
                notificationService = nil
            }
        } else {
            Logger.app.warning("ga_notifications.db not found in bundle")
            notificationService = nil
        }
    }
}
```

#### 3.4 Add Notification Legend Mode

**File:** `app/FlyFunEuroAIP/App/Models/MapTypes.swift`

```swift
enum LegendMode: String, CaseIterable, Identifiable, Sendable, Codable {
    case airportType = "Airport Type"
    case runwayLength = "Runway Length"
    case procedures = "IFR Procedures"
    case country = "Country"
    case notification = "Notification"  // NEW

    var id: String { rawValue }
}
```

**File:** `app/FlyFunEuroAIP/App/Views/Map/AirportAnnotationView.swift`

```swift
// In color selection logic:
case .notification:
    if let service = appState.notificationService,
       let notification = service.getNotification(icao: airport.icao) {
        switch notification.legendColor {
        case .green: return .green
        case .blue: return .blue
        case .orange: return .orange
        case .red: return .red
        case .gray: return .gray
        }
    }
    return .gray  // No data
```

#### 3.5 Display Notification in Airport Detail

**File:** `app/FlyFunEuroAIP/UserInterface/Views/AirportDetail/NotificationSummaryView.swift` (NEW)

```swift
import SwiftUI

struct NotificationSummaryView: View {
    let notification: NotificationInfo

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: iconName)
                    .foregroundColor(iconColor)
                Text(notification.notificationType.displayName)
                    .font(.headline)
            }

            Text(notification.displaySummary)
                .font(.body)
                .foregroundColor(.secondary)

            if notification.confidence < 0.9 {
                Text("Confidence: \(Int(notification.confidence * 100))%")
                    .font(.caption)
                    .foregroundColor(.orange)
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(8)
    }

    private var iconName: String {
        switch notification.notificationType {
        case .h24: return "checkmark.circle.fill"
        case .hours: return "clock.fill"
        case .onRequest: return "phone.fill"
        case .businessDay: return "calendar"
        case .unavailable: return "xmark.circle.fill"
        }
    }

    private var iconColor: Color {
        switch notification.legendColor {
        case .green: return .green
        case .blue: return .blue
        case .orange: return .orange
        case .red: return .red
        case .gray: return .gray
        }
    }
}
```

**Integrate into AIPTab:**
```swift
// In AIPTab, when showing field 302:
if entry.standardField == 302,
   let notification = appState.notificationService?.getNotification(icao: airport.icao) {
    NotificationSummaryView(notification: notification)
} else {
    Text(entry.value)
}
```

#### Testing Phase 3

- [ ] Unit tests for NotificationInfo model
- [ ] Unit tests for NotificationService DB queries
- [ ] Test NotificationService preloadAll performance
- [ ] Test notification legend mode coloring
- [ ] Test NotificationSummaryView display
- [ ] Integration test: AIPTab shows notification summary
- [ ] Test offline behavior (bundled DB works without network)

---

## 4. File Change Summary

### Phase 1: Filters
| File | Action | Changes |
|------|--------|---------|
| `Models/FilterConfig.swift` | Modify | Add `hasAvgas`, `hasJetA`, `maxLandingFee` |
| `Models/Chat/VisualizationPayload.swift` | Modify | Complete ChatFilters with ALL fields |
| `Data/DataSources/LocalAirportDataSource.swift` | Modify | Add ILS/RNAV filtering logic |
| `Views/Filters/FilterPanelContent.swift` | Modify | Add UI for new filters (optional) |
| `Tests/FilterConfigTests.swift` | Modify | Add tests for new fields |

### Phase 2: UI Payload
| File | Action | Changes |
|------|--------|---------|
| `Models/Chat/VisualizationPayload.swift` | Modify | Add SuggestedQuery |
| `State/Domains/ChatDomain.swift` | Modify | Track suggested queries |
| `State/Domains/AirportDomain.swift` | Modify | **Fix applyVisualization reload bug** |
| `UserInterface/Views/Chat/SuggestedQueriesView.swift` | Create | New view component |
| `UserInterface/Views/Chat/ChatView.swift` | Modify | Display suggested queries |

### Phase 3: Notifications
| File | Action | Changes |
|------|--------|---------|
| `Models/NotificationInfo.swift` | Create | New model |
| `Services/NotificationService.swift` | Create | New service (local DB) |
| `State/AppState.swift` | Modify | Add notificationService |
| `Models/MapTypes.swift` | Modify | Add notification legend mode |
| `Views/Map/AirportAnnotationView.swift` | Modify | Notification coloring |
| `UserInterface/Views/AirportDetail/NotificationSummaryView.swift` | Create | New view |
| `UserInterface/Views/AirportDetail/AIPTab.swift` | Modify | Show notification summary |

---

## 5. Error Handling

### Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| ChatFilters parsing fails | Log warning, use empty FilterConfig |
| SuggestedQuery parsing fails | Skip invalid queries, show valid ones |
| NotificationService init fails | Log error, continue without notifications |
| Notification not found for airport | Show "Unknown" in legend, raw AIP text in detail |
| applyVisualization reload fails | Log error, keep existing airports |

### Offline Behavior

| Feature | Offline Status |
|---------|---------------|
| Filters | ✅ Works (local filtering) |
| Suggested queries | ❌ Requires online chat |
| Notification legend | ✅ Works (bundled DB) |
| Notification detail | ✅ Works (bundled DB) |

---

## 6. Performance Considerations

### NotificationService

- **Preload at startup**: ~600 notifications, < 100ms
- **Cache in memory**: Fast O(1) lookups
- **Legend mode**: Batch lookup for visible airports

### Filter Reload

- **Debounce**: Existing region loading debounce (300ms) applies
- **Limit**: Cap at 500 airports for map performance

---

## 7. Progress Tracking

### Phase 1: Filter System Alignment ✅ COMPLETE (2025-12-26)
- [x] Add fuel/fee filters to FilterConfig (`hasAvgas`, `hasJetA`, `maxLandingFee`)
- [x] Complete ChatFilters parsing (all 13 fields)
- [x] Complete ChatFilters.toFilterConfig() mapping (all fields mapped)
- [x] Add ILS/RNAV filtering in applyInMemoryFilters (using `Procedure.ApproachType`)
- [ ] Update filter UI (optional - deferred)
- [x] Write unit tests (FilterConfigTests + ChatFiltersTests)
- [ ] Manual testing

**Implementation Notes:**
- ILS filtering: Matches `.ils` approach type
- RNAV filtering: Matches `.rnav` or `.rnp` approach types
- Fuel/fee filters added but not yet applied in `applyInMemoryFilters` (requires RZFlight enhancement)
- Static helper functions `hasILSApproach`/`hasRNAVApproach` added to `LocalAirportDataSource`

### Phase 2: UI Payload Enhancements ✅ COMPLETE (2025-12-26)
- [x] **Fix applyVisualization filter reload bug** - Now calls `applyFilters()` when filters provided
- [x] Add SuggestedQuery model (in VisualizationPayload.swift)
- [x] Parse suggested_queries in ChatVisualizationPayload
- [x] Add suggestedQueries to ChatDomain
- [x] Create SuggestedQueriesView (horizontal scrolling chips)
- [x] Integrate into ChatView (shows above input bar when queries available)
- [x] Write unit tests (SuggestedQueryTests, ChatDomainTests)
- [ ] Manual testing

**Implementation Notes:**
- `applyVisualization` refactored to call `applyFilters()` then `applyVisualizationHighlights()`
- SuggestedQuery: id, text, tool?, category?, priority?
- ChatDomain.useSuggestion() auto-sends query
- SuggestedQueriesView hidden during streaming

### Phase 3: Notification Support ✅ COMPLETE (2025-12-26)
- [x] Create NotificationInfo model
- [x] Create NotificationService (with bundled DB)
- [x] Integrate NotificationService into AppState
- [x] Add notification legend mode
- [x] Implement notification marker coloring
- [x] Create NotificationSummaryView
- [x] Update AIPTab to show notification summary
- [x] Write unit tests (37+ tests in NotificationTests.swift)
- [ ] Manual testing

**Implementation Notes:**
- NotificationInfo: NotificationType enum (h24, hours, onRequest, businessDay, notAvailable, unknown)
- EasinessScore (0-100): h24=100, short notice=90, moderate=60-80, long notice=10-40
- NotificationService: Preloads from bundled ga_notifications.db, thread-safe cache
- NotificationSummaryView: Full summary with icon, type, hours, contact, EasinessBadge
- Legend colors: green (easy), blue (moderate), orange (some hassle), red (high hassle), gray (no data)

---

## 8. Future Considerations (Phase 4+)

### RZFlight Enhancements

Consider proposing these additions to RZFlight:
- `hasAvgas` / `hasJetA` filtering methods
- Notification model integration
- Landing fee parsing

### GA Friendliness

The web app has a `relevance` legend mode based on GA Friendliness scoring. Could be added using same service pattern as notifications.

### API Notification Refresh

NotificationService could optionally refresh from API when online:
```swift
func refreshFromAPI(icao: String) async -> NotificationInfo? {
    // Fetch from /api/airports/{icao} with notification data
    // Update cache
}
```

---

## Appendix: Reference Documents

- `designs/IOS_APP_DESIGN.md` - Main iOS architecture document
- `designs/UI_FILTER_STATE_DESIGN.md` - Web app state management
- `designs/CHATBOT_WEBUI_DESIGN.md` - Web app chatbot architecture
- `designs/NOTIFICATION_PARSING_DESIGN.md` - Notification system backend
- `designs/IOS_APP_UPDATE_PLAN_REVIEW.md` - Review feedback incorporated
