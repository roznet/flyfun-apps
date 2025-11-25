# GA Friendliness Enrichment Design

This document defines the **high-level design and architecture** for a GA friendliness enrichment system for European airports, built as an add-on to the `euro_aip` database.

This is a **conceptual design document**. For detailed implementation architecture, see `GA_FRIENDLINESS_IMPLEMENTATION.md`.

---

## 1. Goals & Philosophy

### 1.1 Goals

- Add **human-centric** information (reviews, PIREPs, fees, perceived hassle, “vibe”) on top of official AIP data.
- Keep this enrichment **physically and logically separate** from the authoritative `euro_aip.sqlite` file.
- Represent **GA friendliness** as a set of structured features and **persona-specific scores**, *not* a single opaque rating.
- Use **LLM / NLP** to mine reviews into structured tags and airport summaries.
- Enable **route-based** queries: “along this route, what are the most GA-friendly alternates / lunch stops?”

### 1.2 Design Principles

1. **Separation of concerns**
   - `euro_aip` is never mutated by this project.
   - All GA friendliness information lives in a separate enrichment database `ga_meta.sqlite`.
   - Tools and services can function with *only* `euro_aip`; GA data is an optional add-on.

2. **Transparency over magic**
   - GA friendliness is not a single “magic” number.
   - Every score must be explainable from underlying features and tags.
   - We keep:
     - raw-ish tags from reviews,
     - aggregated features,
     - persona-specific scores as a thin layer on top.

3. **Personas are first-class citizens**
   - Different pilots care about different things:
     - IFR tourer in SR22T vs cheap VFR burger run vs training/circuit.
   - Scoring is always *relative to a chosen persona*.
   - Personas are defined in data (JSON/YAML), not hard-coded.

4. **Offline complexity, simple runtime**
   - Heavy work (LLM/NLP, aggregation, scoring) runs offline when building `ga_meta.sqlite`.
   - Runtime services (web API, MCP tools, iOS apps) simply:
     - ATTACH `euro_aip.sqlite` and `ga_meta.sqlite`,
     - read precomputed data,
     - optionally recompute persona scores when needed.

5. **Versioned and rebuildable**
   - The whole enrichment DB is treated as a **build artifact**:
     - Input: `euro_aip`, snapshot of airfield.directory data, ontology, persona configurations.
     - Output: `ga_meta.sqlite` with clear version metadata.
   - It should be safe to throw away and regenerate when scoring logic changes.

---

## 2. High-Level Architecture

### 2.1 External Inputs

- **Core airport & procedure data**  
  `euro_aip.sqlite` (existing project)
  - Authoritative AIP data: airports, runways, IFR/VFR procedures, customs, etc.
  - Geometry (lat/lon, R-tree index) for route-based spatial queries.

- **GA-centric reviews & fees**  
  `airfield.directory` (external site)
  - Airport-level PIREPs, ratings.
  - Indicative landing/parking fees by MTOW and aircraft type.
  - Possibly API or regular export (JSON/CSV).

### 2.2 Enrichment Layer (This Design)

- **Database**: `ga_meta.sqlite`
  - Contains:
    - Aggregated per-airport GA stats.
    - Parsed review tags.
    - Airport-level summaries.
    - AIP notification requirements (optional, from euro_aip).
    - (Optionally) precomputed persona-specific scores.

- **Config / Data Files** (JSON format)
  - `ontology.json` - Defines aspects & labels for review parsing (cost, staff, bureaucracy, etc.).
  - `personas.json` - Defines pilot personas and their weights on features.
  - `feature_mappings.json` - Configurable mappings from label distributions to feature scores (optional).

- **Offline Pipelines**
  - Ingestion from review sources (airfield.directory, CSV, etc.).
  - NLP/LLM extraction from free-text reviews → structured tags.
  - Optional: AIP rule parsing from euro_aip (notification requirements, handling rules).
  - Aggregation → normalized feature scores.
  - Persona scoring → scores per airport/persona.
  - Airport-level text summaries & tags.

### 2.3 Runtime Consumers

- Web backend / API:
  - Airport search with GA friendliness.
  - Route-based corridor search with GA friendliness.
- MCP tools:
  - “Find GA-friendly alternates along this route (persona X)”.
- iOS / SwiftUI apps:
  - Display GA friendliness scores and summaries.
  - Show top GA-friendly options along planned flight.

All runtime consumers treat `ga_meta.sqlite` and config files as **read-only** data.

---

## 3. Data Model: `ga_meta.sqlite`

This section defines the schema and relationships for the GA friendliness enrichment database.

### 3.1 Linking to `euro_aip`

Assumptions about `euro_aip`:

- `airport` table (or equivalent) includes:
  - `icao` (TEXT, unique).
  - `name`, `country`, `lat`, `lon`, etc.
- Optionally, an R-tree index on geometry for spatial queries.

**Key rule:**

- `ga_meta.sqlite` never stores `airport.id` (internal numeric ID) from `euro_aip`.
- Link is done via **external keys**:
  - primarily `icao` (TEXT).
  - If needed, extended with `country`, etc. for disambiguation.

**Typical joint usage:**

```sql
ATTACH DATABASE 'euro_aip.sqlite' AS aip;
ATTACH DATABASE 'ga_meta.sqlite'  AS ga;

SELECT
  aip.airport.icao,
  aip.airport.name,
  ga.ga_airfield_stats.score_ifr_touring
FROM aip.airport
LEFT JOIN ga.ga_airfield_stats
  ON ga.ga_airfield_stats.icao = aip.airport.icao;
```

### 3.2 Core Tables

#### 3.2.1 `ga_airfield_stats`

One row per airport (per ICAO). Main query table for GA friendliness.

```sql
CREATE TABLE ga_airfield_stats (
    icao                TEXT PRIMARY KEY,

    -- Aggregate review info
    rating_avg          REAL,          -- average rating from source (e.g. 1–5)
    rating_count        INTEGER,       -- number of ratings
    last_review_utc     TEXT,          -- timestamp of latest review

    -- Fee info (aggregated GA bands by MTOW ranges)
    fee_band_0_749kg    REAL,          -- 0-749 kg MTOW
    fee_band_750_1199kg REAL,          -- 750-1199 kg MTOW
    fee_band_1200_1499kg REAL,         -- 1200-1499 kg MTOW
    fee_band_1500_1999kg REAL,         -- 1500-1999 kg MTOW
    fee_band_2000_3999kg REAL,         -- 2000-3999 kg MTOW
    fee_band_4000_plus_kg REAL,        -- 4000+ kg MTOW
    fee_currency        TEXT,
    fee_last_updated_utc TEXT,

    -- Binary/boolean-style flags (derived from source + PIREPs + AIP if needed)
    mandatory_handling  INTEGER,       -- 0/1
    ifr_procedure_available INTEGER,   -- 0/1: True if instrument approach procedures exist (ILS, RNAV, VOR, etc.)
    night_available     INTEGER,       -- 0/1

    -- Normalized feature scores (0.0–1.0)
    ga_cost_score       REAL,
    ga_review_score     REAL,
    ga_hassle_score     REAL,
    ga_ops_ifr_score    REAL,
    ga_ops_vfr_score    REAL,
    ga_access_score     REAL,
    ga_fun_score        REAL,
    ga_hospitality_score REAL,       -- Restaurant, hotel, accommodation quality
    notification_hassle_score REAL,  -- From AIP notification rules (optional)

    -- Persona-specific composite scores (denormalized cache; optional)
    score_ifr_touring   REAL,
    score_vfr_budget    REAL,
    score_training      REAL,

    -- Versioning / provenance
    source_version      TEXT,          -- e.g. 'airfield.directory-2025-11-01'
    scoring_version     TEXT           -- e.g. 'ga_scores_v1'
);
```

Notes:

- Persona-specific score columns are **optional** and can be:
  - Precomputed offline.
  - Or omitted, with scores computed at runtime from base features.
- `ga_*_score` fields are normalized [0, 1] to allow simple weighted sum scoring.

#### 3.2.2 `ga_landing_fees`

Optional detailed fee grid, if we want to expose nuanced fee info.

```sql
CREATE TABLE ga_landing_fees (
    id              INTEGER PRIMARY KEY,
    icao            TEXT NOT NULL,
    mtow_min_kg     REAL,
    mtow_max_kg     REAL,
    operation_type  TEXT,      -- 'landing','touchgo','parking'
    amount          REAL,
    currency        TEXT,
    source          TEXT,      -- e.g. 'airfield.directory','manual'
    valid_from_date TEXT,
    valid_to_date   TEXT
);
```

Intended usage:

- Offline:
  - derive per-persona or per-MTOW-band medians/quantiles.
- UI:
  - “Indicative landing fee for MTOW X kg: Y EUR”.

#### 3.2.3 `ga_review_ner_tags`

Structured representation of information extracted from reviews.

```sql
CREATE TABLE ga_review_ner_tags (
    id              INTEGER PRIMARY KEY,
    icao            TEXT NOT NULL,
    review_id       TEXT,      -- optional: source-side review ID
    aspect          TEXT,      -- e.g. 'cost','staff','bureaucracy','fuel','food'
    label           TEXT,      -- e.g. 'expensive','very_positive','complex'
    confidence      REAL,      -- 0.0–1.0
    created_utc     TEXT
);
```

Intended usage:

- Aggregation:
  - Build distributions per `(icao, aspect, label)`.
  - Convert distributions into normalized feature scores (e.g. `ga_cost_score`).
- Debugging & transparency:
  - Explain *why* a field is “expensive” or “friendly”.

#### 3.2.4 `ga_review_summary`

LLM-generated text summary and tags per airport.

```sql
CREATE TABLE ga_review_summary (
    icao            TEXT PRIMARY KEY,
    summary_text    TEXT,      -- 2–4 sentence summary of recurring themes
    tags_json       TEXT,      -- JSON array: ["GA friendly","cheap","good restaurant"]
    last_updated_utc TEXT
);
```

Intended usage:

- UI: quick, digestible summary (no need to show full review list).
- Tag-based filtering (optional future extension):
  - e.g. filter airports that have tags like “good restaurant” or “no handling”.

#### 3.2.5 `ga_notification_requirements` (Optional)

Detailed structured notification requirements parsed from AIP data.

```sql
CREATE TABLE ga_notification_requirements (
    id                  INTEGER PRIMARY KEY,
    icao                TEXT NOT NULL,
    rule_type           TEXT NOT NULL,  -- 'ppr', 'pn', 'customs_notification'
    weekday_start       INTEGER,         -- 0=Monday, 6=Sunday, NULL=all days
    weekday_end         INTEGER,         -- NULL=single day, or end of range
    notification_hours  INTEGER,         -- Hours before flight (24, 48, etc.)
    notification_type   TEXT NOT NULL,  -- 'hours', 'business_day', 'specific_time', 'h24', 'on_request'
    specific_time        TEXT,           -- e.g., "1300" for "before 1300"
    business_day_offset  INTEGER,        -- e.g., -1 for "last business day before"
    is_obligatory        INTEGER,        -- 0/1
    raw_text             TEXT,           -- Original AIP text
    source_section       TEXT,           -- Which AIP section (customs, handling, etc.)
    created_utc          TEXT,
    updated_utc          TEXT
);
```

**Purpose:**
- Store detailed breakdown of notification rules for operational use.
- Examples: "PPR 24 HR weekdays, 48 HR weekends" → two rows with weekday ranges.
- Supports complex rules: business day requirements, specific times, conditional rules.

#### 3.2.6 `ga_aip_rule_summary` (Optional)

High-level summary of AIP notification requirements for scoring.

```sql
CREATE TABLE ga_aip_rule_summary (
    icao                TEXT PRIMARY KEY,
    notification_summary TEXT,     -- Human-readable: "24h weekdays, 48h weekends"
    hassle_level        TEXT,      -- 'low', 'moderate', 'high', 'very_high'
    notification_score  REAL,      -- Normalized score [0, 1] for scoring
    last_updated_utc    TEXT
);
```

**Purpose:**
- High-level summary for UI display.
- Normalized score feeds into `ga_hassle_score` feature.

#### 3.2.7 `ga_meta_info`

General metadata and build info.

```sql
CREATE TABLE ga_meta_info (
    key     TEXT PRIMARY KEY,
    value   TEXT
);
```

Example keys:

- `build_timestamp`
- `source_version` - Source snapshot identifier
- `ontology_version`
- `personas_version`
- `scoring_version`
- `last_processed_{icao}` - Per-airport processing timestamps (for incremental updates)
- `last_aip_processed_{icao}` - Per-airport AIP processing timestamps

### 3.3 Indexing Strategy

- Primary keys:
  - `ga_airfield_stats(icao)`
  - `ga_review_summary(icao)`
- Secondary indexes:
  - `ga_landing_fees(icao)` (for per-airport lookups).
  - `ga_review_ner_tags(icao)`.
  - Optional: `ga_review_ner_tags(icao, aspect)` for aggregation performance.

**Geometry (R-tree)** is *not* in `ga_meta.sqlite`. Geometry lives in `euro_aip`. Route-based queries rely on `euro_aip` for spatial filtering and then join to `ga_meta` via `icao`.

### 3.4 Non-ICAO Fields (Open Topic)

Open question:

- How to handle “non-ICAO” strips:
  - Option A: create pseudo-ICAO codes and document the mapping.
  - Option B: separate table for non-ICAO fields with different linkage rules.
- This can be added later without changing the main design.

---

## 4. NLP / LLM Pipeline for PIREP Parsing

This section describes how free-text PIREPs / reviews from airfield.directory are turned into structured GA friendliness data.

### 4.1 Goals

- Convert **unstructured reviews** into:
  - Stable structured tags (`ga_review_ner_tags`).
  - Short airport-level summaries & tags (`ga_review_summary`).
- Use a **fixed ontology** to avoid inconsistent or “vibe-only” interpretations.
- Ensure everything runs **offline**; runtime services only read from `ga_meta.sqlite`.

### 4.2 Inputs

From `airfield.directory` (conceptual):

Per review:

- `airport_icao` (TEXT)
- `review_id` (TEXT, optional)
- `review_text` (TEXT)
- `rating` (numeric, e.g. 1–5)
- `timestamp` (TEXT)

Implementation details of how this is exported/API are outside this design.

### 4.3 Ontology

Defined in `ontology.json` (versioned).

#### 4.3.1 Aspects

Examples:

- `cost`
- `staff`
- `bureaucracy`
- `fuel`
- `runway`
- `transport`
- `food`
- `restaurant` - Quality of on-airport or nearby restaurant/café
- `accommodation` - Quality of nearby hotels/accommodation
- `noise_neighbours`
- `training_traffic`
- `overall_experience`

#### 4.3.2 Labels

Per aspect, allowed labels. Example:

- `cost`:
  - `cheap`, `reasonable`, `expensive`, `unclear`
- `staff`:
  - `very_positive`, `positive`, `neutral`, `negative`, `very_negative`
- `bureaucracy`:
  - `simple`, `moderate`, `complex`
- `fuel`:
  - `excellent`, `ok`, `poor`, `unavailable`
- `restaurant`:
  - `excellent`, `good`, `ok`, `poor`, `none`
- `accommodation`:
  - `excellent`, `good`, `limited`, `poor`, `none`
- `overall_experience`:
  - `very_positive`, `positive`, `neutral`, `negative`, `very_negative`

Other aspects have similarly defined label sets.

The ontology file should be referenced in `ga_meta_info` via `ontology_version`.

### 4.4 Extraction Step (Per Review)

**Pipeline:**

1. **LLM call** (using LangChain 1.0):
   - Input: Ontology + raw `review_text`
   - Output: Structured JSON with aspect-label pairs and confidence scores
   - Uses Pydantic models for validation

2. **Validation:**
   - Ensure `aspect` exists in ontology
   - Ensure `labels` are allowed for that aspect
   - Apply confidence threshold (configurable, default 0.5)

3. **Storage:**
   - Insert validated tags into `ga_review_ner_tags`
   - Track `review_id` for incremental updates

**Note:** Raw review text is not stored; only derived structured tags are persisted.

### 4.5 Aggregation Step (Per Airport)

For each `icao`:

1. **Compute label distributions** from `ga_review_ner_tags`:
   - Count occurrences per `(aspect, label)` pair
   - Weight by confidence if configured
   - **Optional: Time decay** - Weight recent reviews more heavily (exponential decay based on review age)

2. **Map to normalized feature scores** [0, 1]:
   - `ga_cost_score` from `cost` aspect labels
   - `ga_hassle_score` from `bureaucracy` labels (combined with AIP notification rules if available)
   - `ga_review_score` from `overall_experience` labels
   - `ga_fun_score` from `food`, `overall_experience`, etc.
   - `ga_ops_ifr_score` from review tags + AIP data (if available)
   - `ga_ops_vfr_score` from review tags + AIP data (if available)
   - `ga_access_score` from `transport` aspect labels
   - `ga_hospitality_score` from `restaurant`, `accommodation` aspect labels
   - **Optional: Bayesian smoothing** - For airports with few reviews, smooth scores toward global average to handle small sample sizes

3. **Incorporate numeric ratings:**
   - `rating_avg`, `rating_count` from source

4. **Combine with AIP data** (if available):
   - `notification_hassle_score` from AIP rules feeds into `ga_hassle_score`
   - AIP operational data (IFR procedures, runway length) feeds into ops scores

**Mapping Configuration:**
- Mappings defined in `feature_mappings.json` (optional)
- Falls back to hard-coded defaults if config not provided
- Validated against ontology on load

**Optional Extensions:**
- **Time decay:** Recent reviews weighted more heavily (disabled by default)
- **Bayesian smoothing:** Small sample sizes pulled toward global prior (disabled by default)
- Both extensions are optional and can be enabled via configuration

Scores are written to `ga_airfield_stats`.

### 4.6 Summary Generation Step (Per Airport)

For each airport (`icao`):

1. **Aggregate context:**
   - Tags from `ga_review_ner_tags`
   - Rating stats from source
   - Feature scores (for context)
   - Optional: AIP info (IFR available, runway types)

2. **LLM generation:**
   - Generate `summary_text`: 2–4 sentence summary of recurring themes
   - Generate `tags_json`: Human-readable tags array
     - Example: `["GA friendly","expensive","good restaurant"]`

3. **Store** in `ga_review_summary`.

### 4.7 AIP Rule Parsing (Optional)

**Goal:** Parse structured notification requirements and handling rules from euro_aip database.

**Two-stage processing:**

1. **Detailed extraction:**
   - Parse AIP text (customs, handling sections) using LLM
   - Extract structured rules: weekday ranges, time requirements, business day rules
   - Store in `ga_notification_requirements` table
   - Handles complex patterns: "PPR 24 HR weekdays, 48 HR weekends", "Last business day before 1300"

2. **High-level summarization:**
   - Generate human-readable summary: "24h weekdays, 48h weekends"
   - Calculate normalized `notification_score` [0, 1]
   - Store in `ga_aip_rule_summary`
   - Feeds into `ga_hassle_score` feature

**Integration:**
- Optional feature (works with or without euro_aip)
- Separate NLP pipeline (rule extraction vs. sentiment extraction)
- Supports incremental updates (tracks AIP change timestamps)

### 4.8 Incremental Updates

**Change Detection:**
- Track processed `review_id`s in `ga_review_ner_tags`
- Track `last_processed_timestamp` per airport in `ga_meta_info`
- Compare incoming reviews against stored data
- Only process airports with new/changed reviews

**Benefits:**
- Efficient updates when only some airports change
- Faster rebuilds for regular updates
- Full rebuild still supported for schema changes

### 4.9 Idempotency & Versioning

- Full pipeline is **repeatable**:
  - Same input + same config → same `ga_meta.sqlite`
- Version tracking:
  - `source_version` - Source snapshot identifier
  - `ontology_version` - Ontology config version
  - `scoring_version` - Feature mapping version
  - `personas_version` - Persona config version

Stored in `ga_meta_info` and `ga_airfield_stats`.

---

## 5. Personas & GA Friendliness Scoring

This section defines how **personas** are represented and how GA friendliness scores are computed from base features.

### 5.1 Base Feature Scores

Scores stored in `ga_airfield_stats` as inputs to persona scoring:

- `ga_cost_score`       (0–1)
- `ga_review_score`     (0–1)
- `ga_hassle_score`     (0–1)
- `ga_ops_ifr_score`    (0–1)
- `ga_ops_vfr_score`    (0–1)
- `ga_access_score`     (0–1)
- `ga_fun_score`        (0–1)
- `ga_hospitality_score` (0–1) - Restaurant, hotel, accommodation quality

General idea:

- Each is a normalized score synthesizing:
  - PIREP tags,
  - AIP info, and
  - Possibly basic derived metrics (e.g. runway length, IFR capability).
- The exact feature engineering logic (e.g. mapping label distributions → numeric values) can be documented in a separate internal design file if needed. For this high-level design:
  - treat them as interpretable [0, 1] values.

### 5.2 Persona Definitions

Personas are defined in `personas.json` (JSON format):

```json
{
  "version": "1.0",
  "personas": {
  "ifr_touring_sr22": {
    "label": "IFR touring (SR22)",
    "description": "Typical SR22T IFR touring mission: prefers solid IFR capability, reasonable fees, low bureaucracy. Some weight on hospitality for overnight stops.",
    "weights": {
      "ga_ops_ifr_score": 0.25,
      "ga_hassle_score": 0.20,
      "ga_cost_score": 0.20,
      "ga_review_score": 0.15,
      "ga_access_score": 0.10,
      "ga_hospitality_score": 0.10
    }
  },
  "vfr_budget": {
    "label": "VFR fun / budget",
    "description": "VFR sightseeing / burger runs: emphasis on cost, fun/vibe, hospitality (good lunch spot), and general GA friendliness.",
    "weights": {
      "ga_cost_score": 0.30,
      "ga_fun_score": 0.20,
      "ga_hospitality_score": 0.20,
      "ga_review_score": 0.15,
      "ga_access_score": 0.10,
      "ga_ops_vfr_score": 0.05
    }
  },
  "training": {
    "label": "Training field",
    "description": "Regular training/circuit work: solid runway, availability, low hassle, reasonable cost.",
    "weights": {
      "ga_ops_vfr_score": 0.30,
      "ga_hassle_score": 0.25,
      "ga_cost_score": 0.20,
      "ga_review_score": 0.15,
      "ga_fun_score": 0.10
      }
    },
  "lunch_stop": {
    "label": "Lunch stop / day trip",
    "description": "Day trip destination: emphasis on great restaurant/café, good vibe, easy access, reasonable cost.",
    "weights": {
      "ga_hospitality_score": 0.35,
      "ga_fun_score": 0.25,
      "ga_cost_score": 0.15,
      "ga_hassle_score": 0.15,
      "ga_access_score": 0.10
      }
    }
  }
}
```

**Rules:**
- Weights should ideally sum to 1.0 (not strictly required)
- Features not mentioned have weight 0.0
- Versioned via `personas_version` in `ga_meta_info`

### 5.3 Scoring Function (Conceptual)

For airport `icao`, persona `P`:

```text
score_P(icao) = Σ_f ( weight_P[f] * feature_f[icao] )
```

Where:

- `feature_f[icao]` is one of:
  - `ga_cost_score`, `ga_review_score`, etc.
- `weight_P[f]` is read from persona config.

### 5.4 Where Scores Are Stored

**Hybrid approach:**

1. **Primary persona(s) denormalized:**
   - One or more common personas stored as columns in `ga_airfield_stats`
   - Example: `score_ifr_touring`, `score_vfr_budget`
   - Enables fast SQL sorting/filtering

2. **Other personas computed at runtime:**
   - Base features stored in `ga_airfield_stats`
   - Runtime layer computes scores using `personas.json` weights
   - No schema changes needed for new personas

**Benefits:**
- Fast queries for common personas
- Flexibility for adding new personas
- Clear separation: base features vs. persona scores

### 5.5 API / UI Interaction

- Search / route APIs should accept a `persona` parameter:
  - e.g. `persona=ifr_touring_sr22`.
- If `persona` is missing:
  - Use a default:
    - e.g. `ifr_touring_sr22` for your own use case, or
    - a neutral persona with equal weights.

### 5.6 Extensibility

- Adding a persona:
  - Add entry to `personas.json`.
  - Optionally recompute DB for new denormalized columns.
- Changing weights:
  - Update `personas.json`.
  - Bump `scoring_version`.

### 5.7 Open Questions

- Do we want user-adjustable sliders to override persona weights in UI?
- Do we want to experiment with **learned weights** (simple ML) and store them as a separate persona?

---

## 6. Route-Based Search & GA Friendliness

This section describes how GA friendliness data is used with `euro_aip` to support route-based airport search.

### 6.1 Goals

Given:

- A route (polyline, sequence of lat/lon points),
- A corridor width (e.g. ±20 NM),
- A persona,

We want to:

1. Find candidate airports within the corridor.
2. Compute along-track (`along_nm`) and cross-track (`xtrack_nm`) distances for each candidate.
3. For each candidate, compute or read a persona-specific GA friendliness score.
4. Cluster airports by route distance segments (e.g. 0–100 NM, 100–200 NM).
5. Return a structured result suitable for:
   - map pins + side panel,
   - “top GA-friendly options per segment”.

### 6.2 Dependencies

- `euro_aip.sqlite`:
  - `airport` table with `icao`, `lat`, `lon`, etc.
  - R-tree or equivalent index for spatial queries (airports near route).
- `ga_meta.sqlite`:
  - `ga_airfield_stats` for base feature scores and/or persona scores.
  - `ga_review_summary` for brief summary & tags.
- Persona configuration (`personas.json`).

### 6.3 Conceptual Flow

1. **Input**
   - Route polyline (series of lat/lon points).
   - Corridor width (NM).
   - Persona id (string).

2. **Candidate Selection**
   - Use geometry from `euro_aip`:
     - For each leg of the route, compute a bounding box extended by corridor width.
     - Use R-tree to get airports in each bounding box.
     - For each candidate airport:
       - Compute:
         - `xtrack_nm` (cross-track distance from route).
         - `along_nm` (distance along the route from origin to closest point on route).
   - Filter out airports with `xtrack_nm` > corridor width.

3. **Join with GA Data**
   - For each candidate `icao`, join to `ga.ga_airfield_stats` on `icao`.
   - Compute persona-specific score:
     - From `score_<persona>` column if available, or
     - From base features + persona weights at runtime.

4. **Segmenting & Ranking**
   - Define segment size (e.g. every 100 NM).
   - Compute `segment_index = floor(along_nm / segment_size)`.
   - For each segment:
     - Sort candidate airports by persona score (descending).
     - Optionally limit to top N (e.g. top 3 per segment).

5. **Output**
   - Structured output with segments, airports, distances, and GA metrics.

### 6.4 Example Output Shape (JSON)

Example conceptual response:

```json
{
  "persona": "ifr_touring_sr22",
  "corridor_width_nm": 20,
  "segment_length_nm": 100,
  "segments": [
    {
      "segment_index": 0,
      "start_nm": 0,
      "end_nm": 100,
      "airports": [
        {
          "icao": "LFQQ",
          "name": "Lille",
          "country": "FR",
          "along_nm": 75.2,
          "xtrack_nm": 10.3,
          "score": 0.82,
          "ga_cost_score": 0.40,
          "ga_hassle_score": 0.75,
          "ga_ops_ifr_score": 0.90,
          "summary_tags": ["IFR", "handling", "good food"],
          "has_review_summary": true
        }
      ]
    },
    {
      "segment_index": 1,
      "start_nm": 100,
      "end_nm": 200,
      "airports": []
    }
  ]
}
```

Notes:

- Including base feature scores (`ga_cost_score`, `ga_hassle_score`, etc.) in response makes it easier for the UI to:
  - explain why a field is high/low in GA friendliness.
  - color-code or show tooltips.
- `summary_tags` come from `ga_review_summary.tags_json`.

### 6.5 SQL-ish Pseudocode for Ranking

Assuming:

- Both DBs attached as `aip` and `ga`.
- A temporary or ephemeral table `route_candidates(icao, along_nm, xtrack_nm)`.

Example conceptual SQL:

```sql
WITH candidates AS (
    SELECT
        c.icao,
        c.along_nm,
        c.xtrack_nm,
        g.score_ifr_touring AS persona_score,
        CAST(c.along_nm / 100 AS INTEGER) AS segment
    FROM route_candidates c
    LEFT JOIN ga.ga_airfield_stats g
      ON g.icao = c.icao
    WHERE c.xtrack_nm <= 20
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY segment
            ORDER BY persona_score DESC
        ) AS seg_rank
    FROM candidates
)
SELECT *
FROM ranked
WHERE seg_rank <= 3
ORDER BY segment, seg_rank;
```

Parameters to make configurable:

- Corridor width (NM).
- Segment length (NM).
- Persona (which score column or which weight set to use).

### 6.6 Behavior for Missing Data

For airports without enrichment data (`ga_airfield_stats` missing or some scores = NULL):

- Options:
  - **Option A:** assign a neutral score:
    - e.g. 0.5 with a “no enrichment data” flag; or
  - **Option B:** treat score as `NULL`:
    - push such airports to bottom of ranking.
- Decision can be persona-dependent or global; should be documented once chosen.

### 6.7 API Surface (Conceptual)

High-level endpoint:

- Request:
  - Route geometry (polyline, or start/end with an implied route from planner).
  - Corridor width (NM).
  - Segment length (NM).
  - Persona id.
- Response:
  - As per example above: persona, corridor info, segments, airports, GA metrics.

Exact protocol (HTTP/MCP/etc.) is outside this design; this only defines **what data is necessary**.

---

## 7. Implementation Architecture

### 7.1 Library Structure

**Core library:** `shared/ga_friendliness/`

- Independent library (no hard dependency on euro_aip)
- Uses ICAO codes as linking keys
- Supports ATTACH DATABASE pattern for joint queries
- Configurable via JSON files (ontology, personas, feature mappings)

**Reusable agents at `shared/` level:**

- `shared/ga_review_agent/` - LLM-based review processing (extraction, aggregation, summarization)
- `shared/ga_notification_requirement_agent/` - AIP notification rule parsing
- Both agents follow the same pattern as `shared/aviation_agent/` (same level, reusable in other contexts)

### 7.2 Key Components

- **Review Sources:** Abstract interface for multiple data sources (airfield.directory, CSV, etc.)
- **GA Review Agent:** `shared/ga_review_agent/` - LLM-based extraction (LangChain 1.0), aggregation, summarization
- **GA Notification Requirement Agent:** `shared/ga_notification_requirement_agent/` - Parse notification requirements from euro_aip
- **Feature Engineering:** Configurable mappings from label distributions to scores
- **Persona Scoring:** Weighted combination of base features
- **Incremental Updates:** Change detection and selective reprocessing
- **CLI Tool:** `tools/build_ga_friendliness.py` for rebuilding database

### 7.3 Design Decisions

- **JSON config** (not YAML) - simpler, no extra dependencies
- **LangChain 1.0** - modern API, good Pydantic integration
- **Optional AIP parsing** - works with or without euro_aip
- **Incremental updates** - efficient for regular updates
- **Schema versioning** - safe schema evolution
- **Comprehensive metrics** - track build progress, LLM usage, errors
- **Configurable failure modes** - continue, fail_fast, or skip on errors
- **Optional statistical extensions** - Time decay and Bayesian smoothing available but disabled by default for backward compatibility

### 7.4 Integration Points

- **Runtime consumers:** ATTACH both databases, LEFT JOIN for GA data
- **Web API:** Optional endpoints for GA friendliness queries
- **Route-based search:** Extend existing tools to include GA scores
- **Backward compatible:** Existing tools work without ga_meta.sqlite

---

## 8. Open Questions

- **Non-ICAO fields:** Represent with pseudo-ICAO codes or separate table?
- **Neutral vs missing data:** How to treat airports with no reviews in rankings?
- **Persona explosion:** How many personas to support in UI? How to communicate differences?
- **Learned scoring:** Eventually learn persona weights from user feedback?

---

*For detailed implementation architecture, see `GA_FRIENDLINESS_IMPLEMENTATION.md`.*

---

*End of design document.*
