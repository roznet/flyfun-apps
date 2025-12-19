# Offline Mobile SLM for FlyFun Aviation App

This document analyzes the feasibility of building a fine-tuned Small Language Model (SLM) that runs completely offline on iOS and Android devices for the FlyFun aviation application.

## Executive Summary

> [!TIP]
> **Verdict: Feasible and Highly Recommended**
> 
> Running a fine-tuned SLM offline on mobile devices for aviation assistance is not only possible but has become increasingly practical in 2024-2025. The FlyFun database provides excellent training data, and modern quantized SLMs like **Gemma 3n**, **Phi-3-mini**, or **Llama 3.2 1B/3B** can run efficiently on mid-range smartphones.

---

## Part 1: FlyFun Data Analysis

### Available Training Data

Your existing FlyFun codebase provides rich aviation data suitable for fine-tuning:

| Data Source | Records | Description |
|-------------|---------|-------------|
| [airports.db](file:///mnt/nfs-shared/Dev/022_Home/flyfun-apps/data/airports.db) - `airports` | 7,456 | European airports with coordinates, types, ICAO codes |
| [airports.db](file:///mnt/nfs-shared/Dev/022_Home/flyfun-apps/data/airports.db) - `runways` | 3,998 | Runway details (length, surface, lighting) |
| [airports.db](file:///mnt/nfs-shared/Dev/022_Home/flyfun-apps/data/airports.db) - `procedures` | 4,477 | Instrument approach procedures |
| [airports.db](file:///mnt/nfs-shared/Dev/022_Home/flyfun-apps/data/airports.db) - `aip_entries` | 16,240 | AIP information entries |
| [airports.db](file:///mnt/nfs-shared/Dev/022_Home/flyfun-apps/data/airports.db) - `border_crossing_points` | 760 | Border crossing requirements |
| [rules.json](file:///mnt/nfs-shared/Dev/022_Home/flyfun-apps/data/rules.json) | ~267KB | Country-specific aviation Q&A (~100+ questions × 20 countries) |

### Training Data Potential

The `rules.json` file is particularly valuable—it contains structured Q&A pairs organized by category (Tools, Airfields, Flight Rules, VFR, etc.) with answers by country. This is **ideal** for creating a fine-tuning dataset in conversational format.

**Example from rules.json:**
```json
{
  "question": "Are autorouter FPL accepted?",
  "category": "Tools",
  "answers_by_country": {
    "DE": "FPL submitted via Autorouter or Foreflight work well for VFR as well as IFR",
    "FR": "yes",
    "GB": "yes"
  }
}
```

---

## Part 2: Recommended Small Language Models

### Top SLM Candidates for Mobile

| Model | Parameters | Quantized Size | Best For | Mobile Performance |
|-------|------------|----------------|----------|-------------------|
| **Gemma 3n** (Google) | ~2B effective | ~1-2GB | Best overall mobile experience | 50ms response, multimodal |
| **Phi-3-mini** (Microsoft) | 3.8B | ~1.8GB (4-bit) | Reasoning, instruction-following | 12+ tok/s on iPhone 14 |
| **Llama 3.2 1B** (Meta) | 1B | ~0.7GB | Ultra-lightweight, privacy | Best for older devices |
| **Llama 3.2 3B** (Meta) | 3B | ~1.5GB | Better accuracy with reasonable size | Good for flagship phones |
| **TinyLlama 1.1B** | 1.1B | ~1GB | Smallest footprint | 1.2 tok/s on mid-range Android |

### Primary Recommendation: Gemma 3n or Phi-3-mini

> [!IMPORTANT]
> **Recommended: Gemma 3n** for the following reasons:
> - Designed specifically for mobile by Google DeepMind + Qualcomm + Samsung
> - Native support via Google AI Edge SDK / MediaPipe
> - Multimodal (text, image, audio) if you want chart/image understanding later
> - 140+ language support
> - Runs full AI stack (STT + LLM + TTS) offline

**Alternative: Phi-3-mini** if you need:
- Stronger reasoning capabilities
- Better instruction-following for complex aviation queries
- 128K context window for longer documents

---

## Part 3: Mobile Deployment Frameworks

### Framework Comparison

| Framework | iOS | Android | Best For | Notes |
|-----------|-----|---------|----------|-------|
| **llama.cpp** | ✅ | ✅ | GGUF models, CPU-focused | Most portable, excellent ARM64 optimizations |
| **MLC LLM** | ✅ | ✅ | Cross-platform, GPU acceleration | OpenAI-compatible API, SwiftUI/Kotlin SDKs |
| **Google AI Edge** | ✅ (soon) | ✅ | Gemma models, MediaPipe integration | Native Google solution for Gemma 3n |
| **CoreML** | ✅ | ❌ | Apple Neural Engine optimization | Best for iOS-only, 33 tok/s on M1 |
| **TensorFlow Lite** | ✅ | ✅ | General ML deployment | MediaPipe LLM Inference API |

### Recommended Architecture

```mermaid
flowchart TB
    subgraph Mobile App
        UI[User Interface]
        LLM[Local SLM Engine]
        DB[(Local SQLite DB)]
    end
    
    subgraph LLM Engine Options
        LLAMA[llama.cpp]
        MLC[MLC LLM]
        GAIE[Google AI Edge]
    end
    
    UI --> LLM
    LLM --> DB
    LLM --> LLAMA
    LLM --> MLC
    LLM --> GAIE
    
    style GAIE fill:#34a853,color:white
    style UI fill:#4285f4,color:white
```

**For your existing apps:**
- **Android** ([flyfun-apps-android](file:///mnt/nfs-shared/Dev/022_Home/flyfun-apps-android)): Use **MLC LLM** with Kotlin SDK or **Google AI Edge** for Gemma
- **iOS** (SwiftUI app in flyfun-apps): Use **MLC LLM** with Swift SDK or **llama.cpp** via LLM.swift

---

## Part 4: Fine-Tuning Strategy

### Approach: LoRA/QLoRA Fine-Tuning

For your aviation domain, use **Parameter-Efficient Fine-Tuning (PEFT)** with LoRA or QLoRA:

```mermaid
flowchart LR
    A[Base SLM<br/>Gemma/Phi-3] --> B[QLoRA<br/>Fine-tuning]
    B --> C[Aviation<br/>Adapters]
    C --> D[Quantize<br/>4-bit GGUF]
    D --> E[Mobile<br/>Deployment]
    
    F[(FlyFun<br/>Training Data)] --> B
```

### Training Data Preparation

1. **Convert rules.json to chat format:**
```json
{
  "messages": [
    {"role": "user", "content": "Are autorouter flight plans accepted in Germany?"},
    {"role": "assistant", "content": "Yes, FPL submitted via Autorouter or Foreflight work well for VFR as well as IFR flights in Germany."}
  ]
}
```

2. **Create airport/runway Q&A pairs from airports.db:**
```json
{
  "messages": [
    {"role": "user", "content": "What are the runways at LFPG?"},
    {"role": "assistant", "content": "Paris Charles de Gaulle (LFPG) has runways 08L/26R (4215m, asphalt, lighted), 08R/26L (4200m, asphalt, lighted), 09L/27R (2700m, asphalt, lighted), and 09R/27L (2700m, asphalt, lighted)."}
  ]
}
```

3. **Create border crossing Q&A:**
```json
{
  "messages": [
    {"role": "user", "content": "What are the designated border crossing points for France?"},
    {"role": "assistant", "content": "The designated border crossing points for France include LFPG (Paris CDG), LFMN (Nice), LFBO (Toulouse)..."}
  ]
}
```

### Estimated Dataset Size
- ~2,000-5,000 Q&A pairs from rules.json expansion
- ~5,000-10,000 Q&A pairs from airports.db
- **Total: 7,000-15,000 training examples** (sufficient for effective domain adaptation)

---

## Part 5: Implementation Roadmap

### Phase 1: Data Preparation (1-2 weeks)
- [ ] Create training data generation scripts
- [ ] Export rules.json → conversational format
- [ ] Export airports.db → Q&A pairs
- [ ] Create validation dataset (10-20%)

### Phase 2: Fine-Tuning (1-2 weeks)
- [ ] Set up fine-tuning environment on DGX Spark
- [ ] Fine-tune chosen base model with QLoRA
- [ ] Evaluate on aviation-specific benchmarks
- [ ] Quantize to 4-bit GGUF format

### Phase 3: Mobile Integration (2-3 weeks)
- [ ] Integrate llama.cpp / MLC LLM into Android app
- [ ] Integrate into iOS app
- [ ] Implement local context injection from SQLite
- [ ] Add offline caching for model files

### Phase 4: Testing & Optimization (1-2 weeks)
- [ ] Benchmark performance on target devices
- [ ] Optimize memory usage and inference speed
- [ ] User acceptance testing

---

## Part 6: Technical Considerations

### Memory & Storage Requirements

| Scenario | Model | Storage | RAM Usage |
|----------|-------|---------|-----------|
| Minimum | Llama 3.2 1B (Q4) | ~700MB | ~1GB |
| Recommended | Phi-3-mini (Q4) | ~1.8GB | ~2.5GB |
| Best Quality | Llama 3.2 3B (Q4) | ~1.5GB | ~3GB |

### Device Compatibility

| Device Tier | Example Devices | Recommended Model |
|-------------|-----------------|-------------------|
| **Flagship** | iPhone 14+, Pixel 8+, Samsung S24 | Phi-3-mini / Gemma 3n |
| **Mid-range** | iPhone 12-13, Pixel 6-7, Samsung A54 | Llama 3.2 3B |
| **Entry** | Older iPhones, budget Androids | Llama 3.2 1B / TinyLlama |

### Hybrid Architecture (Recommended)

> [!NOTE]
> Consider a **hybrid approach**: The SLM handles common aviation queries offline, while complex or novel queries fall back to cloud API when connectivity is available.

```mermaid
flowchart TD
    Q[User Query] --> C{Can answer<br/>locally?}
    C -->|Yes| L[Local SLM]
    C -->|No| N{Network<br/>available?}
    N -->|Yes| A[Cloud API]
    N -->|No| F[Fallback:<br/>Local + DB lookup]
    L --> R[Response]
    A --> R
    F --> R
```

---

## Part 8: Local Function Calling (Replicating FlyFun Tools Offline)

> [!IMPORTANT]
> **Key Insight**: Your FlyFun chatbot uses a sophisticated tool-calling architecture. The good news: **all tools operate on local SQLite/JSON data** via `ToolContext`, making offline replication entirely feasible.

### Current FlyFun Tool Architecture

Your chatbot uses 11+ tools that query local data:

| Tool | Function | Data Source |
|------|----------|-------------|
| `search_airports` | Search by ICAO/name/city | `airports.db` |
| `find_airports_near_route` | Airports between two locations | `airports.db` + geocoding |
| `find_airports_near_location` | Proximity search | `airports.db` + geocoding |
| `get_airport_details` | Full airport info | `airports.db` |
| `get_border_crossing_airports` | Customs points | `airports.db` |
| `list_rules_for_country` | Country aviation rules | `rules.json` |
| `compare_rules_between_countries` | Compare regulations | `rules.json` |
| `get_notification_for_airport` | Notification requirements | `ga_notifications.db` |

All tools use `ToolContext` with local databases—**no external APIs needed** for core functionality.

### How to Replicate Locally: Structured Output for Tool Calling

Modern SLMs support **structured output** which enables function calling:

```mermaid
flowchart LR
    Q[User Query] --> SLM[Local SLM]
    SLM --> |JSON output| TC{Tool Call?}
    TC -->|Yes| TE[Tool Executor]
    TC -->|No| R[Direct Response]
    TE --> DB[(Local SQLite)]
    TE --> FR[Format Result]
    FR --> R
```

**Three approaches for local function calling:**

#### Option A: Fine-Tune for Tool Selection (Recommended)
Train the SLM to output structured JSON indicating which tool to call:

```json
{
  "tool": "search_airports",
  "arguments": {
    "query": "LFPG",
    "filters": {"has_customs": true}
  }
}
```

Your app parses this and executes the tool locally against SQLite.

#### Option B: Constrained Decoding (llama.cpp Grammar)
Use `llama.cpp` grammar constraints to force valid JSON tool calls:

```
// grammar.gbnf
root ::= "{" ws "\"tool\":" ws tool_name "," ws "\"arguments\":" ws arguments "}"
tool_name ::= "\"search_airports\"" | "\"get_airport_details\"" | "\"list_rules_for_country\""
```

#### Option C: Prompt-Based Tool Selection
For simpler queries, use a two-stage approach:
1. SLM classifies query type → selects tool
2. App executes SQLite query directly
3. SLM formats the result

### Implementation: Local Tool Dispatcher

Port the existing `AviationToolClient` pattern to mobile:

```kotlin
// Android Example (Kotlin)
class LocalToolDispatcher(
    private val airportsDb: SQLiteDatabase,
    private val rulesJson: JsonObject
) {
    fun dispatch(toolCall: ToolCall): ToolResult {
        return when (toolCall.name) {
            "search_airports" -> searchAirports(toolCall.args)
            "get_airport_details" -> getAirportDetails(toolCall.args)
            "list_rules_for_country" -> listRulesForCountry(toolCall.args)
            else -> ToolResult.error("Unknown tool")
        }
    }
    
    private fun searchAirports(args: Map<String, Any>): ToolResult {
        val query = args["query"] as String
        val cursor = airportsDb.rawQuery(
            "SELECT * FROM airports WHERE icao_code LIKE ? OR name LIKE ? LIMIT 10",
            arrayOf("%$query%", "%$query%")
        )
        // ... format results
    }
}
```

### Simplified Flow for Mobile

```mermaid
flowchart TD
    subgraph Mobile App
        U[User: Find airports near Paris with customs]
        SLM[Local SLM]
        TD[Tool Dispatcher]
        DB[(airports.db + rules.json)]
        F[Format Response]
    end
    
    U --> SLM
    SLM -->|"tool: find_airports_near_location<br/>location: Paris<br/>filters: {has_customs: true}"| TD
    TD --> DB
    DB --> TD
    TD -->|Raw results| SLM
    SLM -->|Natural language| F
    F --> R[Response to User]
```

### What You Can Skip for v1

For initial offline version, simplify:

| Feature | Cloud Version | Offline v1 |
|---------|--------------|------------|
| Router (rules vs database) | LangGraph routing | Direct to SLM |
| Multi-tool chaining | Planner orchestration | Single tool per query |
| RAG for rules | ChromaDB vector search | Direct JSON lookup |
| Geocoding | Geoapify API | Pre-indexed cities or skip |

### Fine-Tuning for Tool Use

Include tool-calling examples in training data:

```json
{
  "messages": [
    {"role": "user", "content": "What's the longest runway at Nice airport?"},
    {"role": "assistant", "content": null, "tool_calls": [
      {"name": "get_airport_details", "arguments": {"icao_code": "LFMN"}}
    ]},
    {"role": "tool", "content": "{\"runways\": [{\"le_ident\": \"04L\", \"length_ft\": 9711}, ...]}"},
    {"role": "assistant", "content": "Nice Côte d'Azur (LFMN) has its longest runway as 04L/22R at 9,711 ft (2,960m)."}
  ]
}
```

This teaches the model **when** to call tools and **how** to interpret results.

---

## Conclusion

Building an offline aviation SLM for FlyFun is **highly feasible**. The recommended approach:

1. **Model**: Start with **Gemma 3n** or **Phi-3-mini** (4-bit quantized)
2. **Framework**: **MLC LLM** for cross-platform or **Google AI Edge** for Gemma
3. **Fine-tuning**: QLoRA on your DGX Spark using converted FlyFun data
4. **Data**: Leverage ~15K+ Q&A pairs from `rules.json` and `airports.db`
5. **Tools**: Port `AviationToolClient` pattern with local SQLite dispatcher

This will give pilots a powerful offline aviation assistant that answers country-specific rules, airport information, border crossing requirements, and more—all without internet connectivity.

---

## Next Steps

1. Do you want me to create the data preparation scripts to convert your FlyFun data into training format?
2. Should I set up the fine-tuning configuration for your DGX Spark environment?
3. Would you prefer to start with Android or iOS integration first?

