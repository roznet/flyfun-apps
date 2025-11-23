# GA Friendliness Enrichment Design

This document defines the **design, plan, and structure** for a GA friendliness enrichment system for European airports, built as an add-on to the `euro_aip` database.

The system is explicitly **design-only**. Implementation (Python, Swift, etc.) is intentionally left for later (Cursor / Codex / other tools).

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
    - (Optionally) precomputed persona-specific scores.

- **Config / Data Files**
  - `ontology.json` (or `.yml`)
    - Defines aspects & labels for review parsing (cost, staff, bureaucracy, etc.).
  - `personas.json` (or `.yml`)
    - Defines pilot personas and their weights on features.
  - Optional additional config files for feature engineering or thresholds.

- **Offline Pipelines (Conceptual)**
  - Ingestion from airfield.directory exports.
  - NLP/LLM extraction from free-text reviews → structured tags.
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

    -- Fee info (aggregated GA bands, typically for common MTOW ranges)
    fee_band_lt_1500kg  REAL,
    fee_band_1500_2000  REAL,
    fee_currency        TEXT,
    fee_last_updated_utc TEXT,

    -- Binary/boolean-style flags (derived from source + PIREPs + AIP if needed)
    mandatory_handling  INTEGER,       -- 0/1
    ifr_available       INTEGER,       -- 0/1
    night_available     INTEGER,       -- 0/1

    -- Normalized feature scores (0.0–1.0)
    ga_cost_score       REAL,
    ga_review_score     REAL,
    ga_hassle_score     REAL,
    ga_ops_ifr_score    REAL,
    ga_ops_vfr_score    REAL,
    ga_access_score     REAL,
    ga_fun_score        REAL,

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

#### 3.2.5 `ga_meta_info`

General metadata and build info.

```sql
CREATE TABLE ga_meta_info (
    key     TEXT PRIMARY KEY,
    value   TEXT
);
```

Example keys:

- `build_timestamp`
- `source_airfield_directory_snapshot`
- `ontology_version`
- `personas_version`
- `scoring_version`

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
- `overall_experience`:
  - `very_positive`, `positive`, `neutral`, `negative`, `very_negative`

Other aspects have similarly defined label sets.

The ontology file should be referenced in `ga_meta_info` via `ontology_version`.

### 4.4 Extraction Step (Per Review)

Conceptual pipeline:

1. **LLM call:**
   - Input:
     - Ontology (aspects + allowed labels).
     - Raw `review_text`.
   - Output:
     - Strict JSON, e.g.:

       ```json
       {
         "aspects": [
           {
             "aspect": "cost",
             "labels": ["expensive"],
             "confidence": 0.87
           },
           {
             "aspect": "staff",
             "labels": ["very_positive"],
             "confidence": 0.92
           }
         ]
       }
       ```

2. **Validation:**
   - Ensure `aspect` is known (found in `ontology.json`).
   - Ensure all `labels` are allowed labels for that aspect.
   - Ensure `confidence` is in [0.0, 1.0]; apply a threshold if needed (e.g. drop < 0.5).

3. **Insertion into `ga_review_ner_tags`:**
   - For each aspect-label pair, insert a row with:
     - `icao`, `review_id`, `aspect`, `label`, `confidence`, `created_utc`.

Note: Raw review text does **not** need to be stored in `ga_meta.sqlite` if licensing/privacy constraints exist; only derived tags are stored.

### 4.5 Aggregation Step (Per Airport)

For each `icao`:

- Use `ga_review_ner_tags` to compute:
  - Label distributions per aspect:
    - e.g. for `cost`, counts or weighted counts of `cheap` vs `expensive`.
  - Mapped normalized scores:
    - e.g. `ga_cost_score` from distribution of `cheap`/`reasonable` vs `expensive`.
    - `ga_hassle_score` from `bureaucracy` labels (simple vs complex).
    - `ga_fun_score` from `food`, `overall_experience`, etc.
- Incorporate numeric ratings:
  - `rating_avg`, `rating_count`.

These aggregated scores and stats are written into `ga_airfield_stats`.

The precise mapping from label distributions to numeric scores is defined in the feature engineering / persona section (see below).

### 4.6 Summary Generation Step (Per Airport)

For each airport (`icao`):

1. Aggregate:
   - All tags from `ga_review_ner_tags` for that airport.
   - Rating stats from source.
   - (Optionally) some AIP info (e.g. IFR available, runway types) for context.

2. LLM step:
   - Generate `summary_text`:
     - 2–4 sentences summarizing the recurring themes.
   - Generate `tags_json`:
     - A small set of human-readable tags:
       - e.g. `["GA friendly","expensive","good restaurant","busy weekends"]`.

3. Store / update in `ga_review_summary`.

### 4.7 Idempotency & Versioning

- Full pipeline should be **repeatable**:
  - Same input snapshot + same ontology + same scoring configuration → same `ga_meta.sqlite`.
- Important version info:
  - Source snapshot ID (`source_airfield_directory_snapshot`).
  - `ontology_version`.
  - `scoring_version`.
  - `personas_version`.

Stored in `ga_meta_info` and `ga_airfield_stats.source_version` / `scoring_version`.

### 4.8 Open Questions

- Keep a minimal subset of **raw review text** (e.g. short excerpts) for transparency or avoid entirely?
- How strict should confidence thresholds be for tag inclusion?
- Do we support multiple languages or assume normalization into a single language?

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

General idea:

- Each is a normalized score synthesizing:
  - PIREP tags,
  - AIP info, and
  - Possibly basic derived metrics (e.g. runway length, IFR capability).
- The exact feature engineering logic (e.g. mapping label distributions → numeric values) can be documented in a separate internal design file if needed. For this high-level design:
  - treat them as interpretable [0, 1] values.

### 5.2 Persona Definitions

Personas are defined in a small config file, e.g. `personas.json`:

```json
{
  "ifr_touring_sr22": {
    "label": "IFR touring (SR22)",
    "description": "Typical SR22T IFR touring mission: prefers solid IFR capability, reasonable fees, low bureaucracy.",
    "weights": {
      "ga_ops_ifr_score": 0.30,
      "ga_hassle_score": 0.20,
      "ga_cost_score": 0.20,
      "ga_review_score": 0.20,
      "ga_access_score": 0.10
    }
  },
  "vfr_budget": {
    "label": "VFR fun / budget",
    "description": "VFR sightseeing / burger runs: emphasis on cost, fun/vibe, and general GA friendliness.",
    "weights": {
      "ga_cost_score": 0.35,
      "ga_fun_score": 0.25,
      "ga_review_score": 0.20,
      "ga_access_score": 0.10,
      "ga_ops_vfr_score": 0.10
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
  }
}
```

Rules:

- Per persona, weights should ideally sum to 1.0 (but not strictly required).
- Any base feature not mentioned in `weights` implicitly has weight 0.0.
- Personae are versioned via `personas_version` in `ga_meta_info`.

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

Two complementary approaches:

1. **Denormalized persona columns in `ga_airfield_stats`**  
   e.g. `score_ifr_touring`, `score_vfr_budget`, `score_training`.

   - Pros:
     - Very simple SQL sorting/filtering.
     - Good for most common persona(s).
   - Cons:
     - Schema changes if you want many personas (or accept sparse columns).

2. **Runtime scoring only**
   - Store only base features.
   - Persona scoring done in API / app layer using `personas.json`.
   - Pros:
     - More flexible; no DB schema changes when adding personas.
   - Cons:
     - Slightly more logic in runtime layer.

**Design choice for now:**

- At least one **primary persona** (e.g. `ifr_touring_sr22`) may be denormalized into a score column for convenience.
- Additional personas can initially be computed in runtime without schema changes.

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

## 7. Open Questions & Next Steps

### 7.1 Open Questions

- **Non-ICAO fields:**
  - Represent with pseudo-ICAO codes or separate table?
- **Neutral vs missing data:**
  - How to treat airports with no reviews or no GA data in rankings?
- **Persona explosion:**
  - How many personas do we actually want to support in UI?
  - How do we communicate differences clearly to users?
- **Learned scoring:**
  - Do we want to eventually learn persona weights from labeled examples (your own ratings, other users’ feedback) instead of hand-tuning?

### 7.2 Next Steps (for Implementation, Not in This Design)

- Define `ontology.json` schema and initial values in detail.
- Define mapping from label distributions → each `ga_*_score`.
- Decide which persona(s) should be denormalized into DB columns.
- Write a separate **implementation design**:
  - offline builder CLI,
  - integration into web backend / MCP tools,
  - testing strategy (e.g. golden airports with known GA friendliness).

---

*End of design document.*
