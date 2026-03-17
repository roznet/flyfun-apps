# flyfun-apps

> Aviation planning web app with LLM agent, European AIP data, and GA friendliness scoring. Also includes FlyFunBrief (briefing app) and FlyFunEuroAIP (iOS/macOS app).

## Web App (Frontend)

### Web App Architecture
Core architecture patterns: Zustand store as single source of truth, unidirectional data flow, component communication via store and events. **Read first** before any web UI work.
Key exports: `store`, `AppState`, `VisualizationEngine`, `UIManager`, `ChatbotManager`
→ Full doc: WEB_APP_ARCHITECTURE.md

### Web App State
Zustand store design: state structure, actions, filtering logic, subscriptions, data flow patterns.
Key exports: `store`, `FilterConfig`, `GAState`, `RulesState`, `AuthState`
→ Full doc: WEB_APP_STATE.md

### Web App Map
Map visualization: VisualizationEngine, Leaflet integration, markers, routes, highlights, layers, view management.
Key exports: `VisualizationEngine`, marker styles, route rendering
→ Full doc: WEB_APP_MAP.md

### Web App Legends
Legend system: shared configuration, match-function classification, legend modes (notification, airport-type, runway-length, relevance), LLM legend switching.
Key exports: `LegendConfig`, `LegendEntry`, `NOTIFICATION_LEGEND_CONFIG`, `classifyData`, `getColorFromConfig`
→ Full doc: WEB_APP_LEGENDS.md

### Web App Chat Integration
Chatbot integration: ChatbotManager, SSE streaming, UI payload handling, visualization types (markers, route_with_markers, point_with_markers, marker_with_details).
Key exports: `ChatbotManager`, `LLMIntegration`, visualization handlers
→ Full doc: WEB_APP_CHAT.md

### Web App Filters
Filter system: FilterEngine (backend single source), filter types, AIP filtering, adding new filters, filter profile application.
Key exports: `FilterEngine`, `FilterConfig`, filter implementations
→ Full doc: WEB_APP_FILTERS.md

---

## LLM Agent (Backend)

### Agent Architecture
Core architecture patterns: planner-based tool selection, LangGraph state, graph structure, error handling. **Read first** before any agent work.
Key exports: `AgentState`, `AviationPlan`, `build_agent()`, `build_ui_payload()`
→ Full doc: AGENT_ARCHITECTURE.md

### Agent Planner
Planner node: AviationPlan schema, tool selection logic, filter extraction from natural language.
Key exports: `AviationPlan`, `build_planner_runnable()`, `planner_node()`
→ Full doc: AGENT_PLANNER.md

### Agent Formatter
Formatter chains: strategy-based formatting, UI payload structure, missing_info handling.
Key exports: `formatter_node()`, `build_ui_payload()`, formatter chains
→ Full doc: AGENT_FORMATTER.md

### Agent RAG System
Rules RAG: query router, country extraction, vector retrieval, comparison system.
Key exports: `QueryRouter`, `RulesRAG`, `RulesComparisonService`, `AnswerComparer`
→ Full doc: AGENT_RAG.md

### Agent Tools
Tool catalog: airport tools, rules tools, missing_info pattern, aircraft speed lookup.
Key exports: `get_shared_tool_specs()`, `AIRCRAFT_CRUISE_SPEEDS`, tool implementations
→ Full doc: AGENT_TOOLS.md

### Agent Configuration
JSON-based behavior configuration, multi-provider support (OpenAI/Anthropic/Google), environment variables, prompt management, A/B testing tools.
Key exports: `get_settings()`, `get_behavior_config()`, `AgentBehaviorConfig`, `_PROVIDER_REGISTRY`
→ Full doc: AGENT_CONFIG.md

### Agent Streaming
SSE streaming: FastAPI endpoint, event types, token tracking, session management.
Key exports: `aviation_agent_chat_stream()`, `stream_agent_response()`
→ Full doc: AGENT_STREAMING.md

---

## Data & Scoring

### Data Update Pipeline
Orchestrates AIP data fetching (web + autorouter), AIRAC cycle tracking, change history, and derived database sync. Main tool: `data_update.py`.
Key exports: `data_update.py`, `aipexport.py`, `aipchange.py`, `DatabaseStorage.airac_date`
→ Full doc: DATA_UPDATE_PIPELINE.md

### GA Friendliness System
Persona-based airport scoring using reviews, fees, and AIP data. Separate enrichment database (`ga_persona.db`), LLM-extracted features, configurable personas.
Key exports: `GAFriendlinessService`, `PersonaManager`, `AirportFeatureScores`
→ Full doc: GA_FRIENDLINESS_DESIGN.md

### AIP Field Search
Structured search on preprocessed AIP data. Integer encoding for hospitality fields (-1=unknown, 0=none, 1=vicinity, 2=at_airport), filter semantics where "vicinity" includes "at_airport".
Key exports: `HotelFilter`, `RestaurantFilter`, `get_icaos_by_hospitality`
→ Full doc: AIP_FIELD_SEARCH_DESIGN.md

### GA Notification Agent
Waterfall parser for PPR/customs notification requirements. Regex patterns handle simple cases (H24, O/R, hours notice), LLM fallback for complex rules. Outputs factual rules to `ga_notifications.db` and hassle scores to `ga_persona.db`.
Key exports: `NotificationParser`, `NotificationScorer`, `NotificationBatchProcessor`, `get_notification_config`
→ Full doc: NOTIFICATION_PARSING_DESIGN.md

---

## FlyFunBrief (Briefing App)

### Briefing App Architecture
Core architecture patterns: RZFlight model reuse, composed AppState with domains, enriched model pattern, identity-based NOTAM tracking. **Read first** before any FlyFunBrief work.
Key exports: `AppState`, `BriefingDomain`, `NotamDomain`, `FlightDomain`, `EnrichedNotam`
→ Full doc: BRIEFING_APP_ARCHITECTURE.md

### Briefing App Data Layer
Core Data stack with CloudKit sync, repository pattern, identity key-based status transfer, global NOTAM ignore list with auto-expiration, airport-level ignore list.
Key exports: `FlightRepository`, `IgnoreListManager`, `AirportIgnoreListManager`, `PersistenceController`, `CDFlight`, `CDBriefing`, `CDNotamStatus`, `CDIgnoredAirport`
→ Full doc: BRIEFING_APP_DATA.md

### Briefing App NOTAM System
NOTAM domain, filtering pipeline, enriched model pattern, identity matching across briefings, NOTAM and airport ignore lists, profile-driven priority evaluation (IFR/VFR) with cumulative filtering.
Key exports: `NotamDomain`, `EnrichedNotam`, `NotamIdentity`, `NotamStatus`, `NotamPriority`, `PriorityProfile`, `PriorityFilter`, filter types
→ Full doc: BRIEFING_APP_NOTAMS.md

---

## FlyFunEuroAIP (Mobile iOS/macOS)

### iOS App Architecture
Core architecture patterns: RZFlight model reuse, composed AppState, domain structure, environment injection. **Read first** before any FlyFunEuroAIP work.
→ Full doc: IOS_APP_ARCHITECTURE.md

### iOS App UI Layout
Layout philosophy: iPhone (map-centric overlays) vs iPad (NavigationSplitView), view folder structure, shared components (FilterBindings, FloatingActionButton), naming conventions.
→ Full doc: IOS_APP_UI.md

### iOS App Data Layer
Repository pattern, LocalAirportDataSource (KnownAirports), FilterConfig, region-based loading for map performance.
→ Full doc: IOS_APP_DATA.md

### iOS App Map
Map views (online SwiftUI Map, offline MKMapView), legend modes, AirportMarkerView, visualization from chat.
→ Full doc: IOS_APP_MAP.md

### iOS App Chat System
ChatDomain, OnlineChatbotService (SSE), OfflineChatbotService (MediaPipe), LocalToolDispatcher, suggested queries.
→ Full doc: IOS_APP_CHAT.md

### iOS App Offline Mode
Tile caching (CachedTileOverlay, OfflineTileManager), bundled data (airports.db, rules.json), on-device AI (Gemma 2B via MediaPipe).
→ Full doc: IOS_APP_OFFLINE.md

---

## Auth & Deployment

### Auth & Usage Tracking
Google OAuth SSO via flyfun-common, chatbot gating behind login, per-user daily rate limiting, cost tracking via shared ledger. Public endpoints stay open, only LLM chat requires auth.
Key exports: `ChatUsageRow`, `check_chat_rate_limit`, `log_chat_usage`, `AuthState`
→ Full doc: AUTH_USAGE.md

### Docker Deployment
Container deployment setup for web server and services.
→ Full doc: DOCKER_DEPLOYMENT.md

