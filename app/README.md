# FlyFun EuroAIP App

An iOS aviation planning assistant for European general aviation pilots.

## Features

- **Airport Search & Discovery**: Find airports by ICAO code, name, city, or location
- **Route Planning**: Find airports along flight routes
- **Rules & Regulations**: Access country-specific aviation rules
- **Border Crossing**: Find airports with customs/immigration facilities
- **AI Chat Assistant**: Natural language queries about airports and procedures

## Offline Mode

The app supports full offline functionality using on-device AI inference.

### Framework

**MediaPipe LLM Inference SDK** (via CocoaPods)
- `MediaPipeTasksGenAI` - Core GenAI inference
- `MediaPipeTasksGenAIC` - C bindings for LLM inference

### Model

**[Gemma 3n E2B](https://www.kaggle.com/models/google/gemma-3n/transformers/gemma-3n-e2b-it)** (gemma-3n-e2b.task)
- Optimized for mobile devices
- ~600MB model file
- Supports tool calling for structured queries
- Downloaded separately and placed in app container

### Offline Tools

The offline mode supports these tools via `LocalToolDispatcher`:

| Tool | Description |
|------|-------------|
| `search_airports` | Search by ICAO, name, or city |
| `get_airport_details` | Get detailed airport information |
| `find_airports_near_route` | Find airports along a flight route |
| `find_airports_near_location` | Find airports near a location with optional notification filter |
| `find_airports_by_notification` | Find airports by notification requirements |
| `get_border_crossing_airports` | Get customs/border crossing airports |
| `list_rules_for_country` | Get aviation rules for a country |
| `compare_rules_between_countries` | Compare rules between two countries |

### Offline Databases

- **airports.db** - Airport data (via RZFlight library)
- **ga_notifications.db** - GA notification requirements (hours notice, operating hours)
- **rules.json** - Country-specific aviation rules

### Tool Replication from Web Version

The offline tools replicate the server-side API functionality:

**Web API** → **LocalToolDispatcher**

| Web Endpoint | Offline Tool | Data Source |
|--------------|--------------|-------------|
| `/api/airports/search` | `search_airports` | RZFlight KnownAirports |
| `/api/airports/{icao}` | `get_airport_details` | RZFlight airportWithExtendedData |
| `/api/airports/near-route` | `find_airports_near_route` | RZFlight airportsNearRoute |
| `/api/airports/near-location` | `find_airports_near_location` | RZFlight nearest + SQLite notifications |
| `/api/airports/by-notification` | `find_airports_by_notification` | SQLite ga_notifications.db |
| `/api/airports/border-crossing` | `get_border_crossing_airports` | RZFlight airportsWithBorderCrossing |
| `/api/rules/{country}` | `list_rules_for_country` | rules.json |
| `/api/rules/compare` | `compare_rules_between_countries` | rules.json |

**Key Differences:**
- Web uses PostgreSQL; offline uses SQLite + RZFlight KDTree
- Notification data is bundled from `ga_notifications.db` (synced from Android assets)
- Tool dispatch uses JSON-based tool calling with LLM instead of function calling API

## Architecture

```
App/
├── Services/Offline/
│   ├── OfflineChatbotService.swift  # Main offline chat orchestration
│   ├── InferenceEngine.swift        # MediaPipe LLM wrapper
│   ├── LocalToolDispatcher.swift    # Tool execution
│   └── ModelManager.swift           # Model file management
├── Data/DataSources/
│   └── LocalAirportDataSource.swift # SQLite airport queries
└── State/Domains/
    └── ChatDomain.swift             # Chat state management
```

## Setup

### Prerequisites
- Xcode 15+
- iOS 17+
- CocoaPods

### Installation

```bash
cd app
pod install
open FlyFunEuroAIP.xcworkspace
```

### Model Setup

1. Download `gemma-3n-e2b.task` model file
2. Copy to app container Documents/models/ directory
3. Or use `xcrun simctl` for simulator:
   ```bash
   xcrun simctl get_app_container booted net.ro-z.FlyFunEuroAIP data
   # Copy model to that path/Documents/models/
   ```

## Configuration

Create `secrets.json` from the sample:
```bash
cp FlyFunEuroAIP/secrets.json.sample FlyFunEuroAIP/secrets.json
```

## License

Copyright © Ro-Z.net
