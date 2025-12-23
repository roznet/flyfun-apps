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
   - All GA friendliness information lives in a separate enrichment database `ga_persona.db`.
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
   - Heavy work (LLM/NLP, aggregation, scoring) runs offline when building `ga_persona.db`.
   - Runtime services (web API, MCP tools, iOS apps) simply:
     - ATTACH `euro_aip.sqlite` and `ga_persona.db`,
     - read base feature scores from `ga_airfield_stats`,
     - compute persona scores dynamically from base features.

5. **Versioned and rebuildable**
   - The whole enrichment DB is treated as a **build artifact**:
   - Input: `euro_aip`, snapshot of airfield.directory data, ontology, persona configurations.
   - Output: `ga_persona.db` with clear version metadata.
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

- **Database**: `ga_persona.db`
  - Contains:
    - Aggregated per-airport GA stats (base feature scores).
    - Parsed review tags.
    - Airport-level summaries.
    - Persona scores computed dynamically at runtime from base features.

- **Config / Data Files** (JSON format, optional)
  - `ontology.json` - Defines aspects & labels for review parsing (cost, staff, bureaucracy, etc.).
    - **Built-in defaults available** - library includes default ontology if file not provided
  - `personas.json` - Defines pilot personas and their weights on features.
    - **Built-in defaults available** - library includes default personas if file not provided
  - `feature_mappings.json` - Configurable mappings from label distributions to feature scores (optional).
    - Falls back to hard-coded defaults if not provided

- **Offline Pipelines**
  - Ingestion from multiple review sources:
    - `AirfieldDirectorySource` - airfield.directory export JSON
    - `AirportJsonDirectorySource` - Per-airport JSON files (e.g., EGTF.json)
    - `CSVReviewSource` - CSV files with reviews
    - `CompositeReviewSource` - Combines multiple sources
    - `AirportsDatabaseSource` - IFR metadata, hotel/restaurant info from airports.db
  - NLP/LLM extraction from free-text reviews → structured tags (LangChain-based).
  - Aggregation → normalized feature scores (with optional time decay and Bayesian smoothing).
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

All runtime consumers treat `ga_persona.db` and config files as **read-only** data.

---

## 3. Data Model: `ga_persona.db`

This section defines the schema and relationships for the GA friendliness enrichment database.

### 3.1 Linking to `euro_aip`

Assumptions about `euro_aip`:

- `airport` table (or equivalent) includes:
  - `icao` (TEXT, unique).
  - `name`, `country`, `lat`, `lon`, etc.
- Optionally, an R-tree index on geometry for spatial queries.

**Key rule:**

- `ga_persona.db` never stores `airport.id` (internal numeric ID) from `euro_aip`.
- Link is done via **external keys**:
  - primarily `icao` (TEXT).
  - If needed, extended with `country`, etc. for disambiguation.

**Typical joint usage:**

```sql
ATTACH DATABASE 'euro_aip.sqlite' AS aip;
ATTACH DATABASE 'ga_persona.db'   AS ga;

SELECT
  aip.airport.icao,
  aip.airport.name,
  ga.ga_airfield_stats.review_cost_score,
  ga.ga_airfield_stats.aip_ops_ifr_score
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

    -- ============================================
    -- REVIEW AGGREGATE INFO
    -- ============================================
    rating_avg          REAL,          -- Average rating from source (e.g. 1–5)
    rating_count        INTEGER,       -- Number of ratings
    last_review_utc     TEXT,          -- Timestamp of latest review

    -- ============================================
    -- FEE INFO (from review sources)
    -- ============================================
    fee_band_0_749kg    REAL,          -- 0-749 kg MTOW
    fee_band_750_1199kg REAL,          -- 750-1199 kg MTOW
    fee_band_1200_1499kg REAL,         -- 1200-1499 kg MTOW
    fee_band_1500_1999kg REAL,         -- 1500-1999 kg MTOW
    fee_band_2000_3999kg REAL,         -- 2000-3999 kg MTOW
    fee_band_4000_plus_kg REAL,        -- 4000+ kg MTOW
    fee_currency        TEXT,
    fee_last_updated_utc TEXT,

    -- ============================================
    -- AIP RAW DATA (from airports.db/AIP)
    -- ============================================
    -- IFR capabilities
    aip_ifr_available        INTEGER,   -- 0=no IFR, 1=IFR permitted (no procedures), 2=non-precision (VOR/NDB), 3=RNP/RNAV, 4=ILS
    aip_night_available     INTEGER,   -- 0/1
    
    -- Hospitality (encoded from AIP)
    aip_hotel_info          INTEGER,   -- 0=unknown, 1=vicinity, 2=at_airport
    aip_restaurant_info     INTEGER,   -- 0=unknown, 1=vicinity, 2=at_airport

    -- ============================================
    -- REVIEW-DERIVED FEATURE SCORES (0.0–1.0)
    -- From parsing review text and extracting tags
    -- ============================================
    review_cost_score       REAL,      -- From 'cost' aspect labels
    review_hassle_score     REAL,      -- From 'bureaucracy' aspect labels
    review_review_score     REAL,      -- From 'overall_experience' aspect labels
    review_ops_ifr_score    REAL,      -- From review tags about IFR operations
    review_ops_vfr_score   REAL,      -- From review tags about VFR/runway quality
    review_access_score     REAL,      -- From 'transport' aspect labels
    review_fun_score        REAL,      -- From 'food' and 'overall_experience' aspects
    review_hospitality_score REAL,     -- From 'restaurant' and 'accommodation' aspects

    -- ============================================
    -- AIP-DERIVED FEATURE SCORES (0.0–1.0)
    -- Computed from AIP raw data fields
    -- ============================================
    aip_ops_ifr_score       REAL,      -- Computed from aip_ifr_available
    aip_hospitality_score   REAL,      -- Computed from aip_hotel_info, aip_restaurant_info

    -- ============================================
    -- VERSIONING / PROVENANCE
    -- ============================================
    source_version      TEXT,          -- e.g. 'airfield.directory-2025-11-01'
    scoring_version     TEXT           -- e.g. 'ga_scores_v2'
);
```

**Schema Organization:**

1. **Review Aggregate Info** - Raw statistics from review sources (ratings, counts, timestamps)
2. **Fee Info** - Landing/parking fees by MTOW bands (from review sources)
3. **AIP Raw Data** - Structured data extracted from AIP/airports.db:
   - IFR capabilities (IFR available, night ops)
   - Hospitality encoding (hotel, restaurant: 0=unknown, 1=vicinity, 2=at_airport)
4. **Review-Derived Feature Scores** - Normalized [0, 1] scores computed from review tag distributions
5. **AIP-Derived Feature Scores** - Normalized [0, 1] scores computed from AIP raw data

**Note:** Persona-specific composite scores are computed dynamically at runtime from base feature scores, not stored in the database.

**Key Design Principles:**

- **Separation of Sources**: Review-derived and AIP-derived scores are stored separately, allowing personas to prefer one source over another
- **Transparency**: Raw AIP data is preserved alongside computed scores for debugging and transparency
- **Persona Flexibility**: Personas define weight vectors over all feature scores, allowing fine-grained control over which sources matter most
- **Normalized Scores**: All feature scores are normalized [0, 1] to allow weighted combination in persona scoring

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
    timestamp       TEXT,      -- ISO format timestamp from source review (for time decay)
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
  - `ga_meta_info(key)`
- Secondary indexes:
  - `ga_landing_fees(icao)` - for per-airport lookups
  - `ga_review_ner_tags(icao)` - for per-airport tag queries
  - `ga_review_ner_tags(icao, aspect)` - for aggregation performance
  - `ga_review_ner_tags(icao, review_id)` - for incremental update change detection

**Geometry (R-tree)** is *not* in `ga_persona.db`. Geometry lives in `euro_aip`. Route-based queries rely on `euro_aip` for spatial filtering and then join to `ga_meta` via `icao`.

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
- Ensure everything runs **offline**; runtime services only read from `ga_persona.db`.

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
- `restaurant` - Availability and proximity of restaurant/café
- `accommodation` - Availability and proximity of hotels/accommodation
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
  - `on_site`, `walking`, `nearby`, `available`, `none`
- `accommodation`:
  - `on_site`, `walking`, `nearby`, `available`, `none`
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

2. **Map to review-derived feature scores** [0, 1]:
   - `review_cost_score` from `cost` aspect labels
   - `review_hassle_score` from `bureaucracy` aspect labels
   - `review_review_score` from `overall_experience` aspect labels
   - `review_fun_score` from `food`, `overall_experience` aspects
   - `review_ops_ifr_score` from review tags about IFR operations
   - `review_ops_vfr_score` from review tags about VFR/runway quality
   - `review_access_score` from `transport` aspect labels
   - `review_hospitality_score` from `restaurant`, `accommodation` aspects
   - **Optional: Bayesian smoothing** - For airports with few reviews, smooth scores toward global average to handle small sample sizes

3. **Incorporate numeric ratings:**
   - `rating_avg`, `rating_count` from source

4. **Compute AIP-derived feature scores** (separate from review scores):
   - `aip_ops_ifr_score` computed from `aip_ifr_available`
   - `aip_hospitality_score` computed from `aip_hotel_info`, `aip_restaurant_info`
   - AIP raw data stored separately: `aip_ifr_available`, `aip_hotel_info`, `aip_restaurant_info`, etc.

**Note:** Review-derived and AIP-derived scores are computed and stored separately. Personas combine them at scoring time using a simple weighted sum over all available feature scores.

**AIP-Derived Score Computation:**

AIP-derived scores are computed from raw AIP data fields:

- **`aip_ops_ifr_score`**:
  - Computed from `aip_ifr_available` (0-4 scale)
  - Formula: `if aip_ifr_available == 0 then 0.1 else (aip_ifr_available / 4.0 * 0.8 + 0.2)`
  - Maps: 0→0.1, 1→0.4, 2→0.6, 3→0.8, 4→1.0
  - **Note:** VFR-only airports (aip_ifr_available=0) receive a score of 0.1 rather than 0.0 because they still provide utility as diversion options in VMC for VFR operations. A score of 0.0 would imply "completely unusable" which is too harsh for VFR-capable fields.

- **`aip_hospitality_score`**:
  - Computed from `aip_hotel_info` and `aip_restaurant_info` integer fields
  - Maps encoded values to scores:
    - `2` (at_airport) → 1.0
    - `1` (vicinity) → 0.6
    - `0` (unknown) → 0.0
  - Combined: 60% restaurant, 40% accommodation
  - Formula: `0.6 * restaurant_score + 0.4 * hotel_score`

**Mapping Configuration:**
- Mappings defined in `feature_mappings.json` (optional)
- Falls back to hard-coded defaults if config not provided
- Validated against ontology on load

**Optional Extensions:**
- **Time decay:** Recent reviews weighted more heavily (disabled by default)
- **Bayesian smoothing:** Small sample sizes pulled toward global prior (disabled by default)
- Both extensions are optional and can be enabled via configuration

Scores are written to `ga_airfield_stats`.

### 4.5.1 Feature Mapping Configuration (Config-Driven Feature Computation)

**Design Goal:** Make feature computation fully configurable without code changes. This allows easily:
- Changing which aspects contribute to which features
- Updating label-to-score mappings
- Adding aspects to existing features
- Tuning feature calculation formulas

All without modifying Python code or rebuilding the application.

**Configuration File:** `feature_mappings.json`

```json
{
  "version": "2.0",
  "description": "Feature mapping configuration for GA friendliness scoring",

  "review_feature_definitions": {
    "review_cost_score": {
      "description": "Cost/fee friendliness from pilot reviews",
      "aspects": [
        {
          "name": "cost",
          "weight": 1.0
        }
      ],
      "aggregation": "weighted_label_mapping",
      "label_scores": {
        "cheap": 0.9,
        "reasonable": 0.6,
        "expensive": 0.3,
        "very_expensive": 0.1,
        "unclear": null
      }
    },

    "review_hassle_score": {
      "description": "Bureaucracy/paperwork burden from reviews",
      "aspects": [
        {
          "name": "bureaucracy",
          "weight": 0.7
        },
        {
          "name": "staff",
          "weight": 0.3
        }
      ],
      "aggregation": "weighted_label_mapping",
      "label_scores": {
        "bureaucracy": {
          "simple": 0.9,
          "moderate": 0.6,
          "complex": 0.3,
          "very_complex": 0.1
        },
        "staff": {
          "very_positive": 0.9,
          "positive": 0.7,
          "neutral": 0.5,
          "negative": 0.3,
          "very_negative": 0.1
        }
      }
    },

    "review_fun_score": {
      "description": "Fun factor from food/vibe reviews",
      "aspects": [
        {
          "name": "food",
          "weight": 0.6
        },
        {
          "name": "overall_experience",
          "weight": 0.4
        }
      ],
      "aggregation": "weighted_label_mapping"
    },

    "review_hospitality_score": {
      "description": "Restaurant/hotel availability from reviews",
      "aspects": [
        {
          "name": "restaurant",
          "weight": 0.6
        },
        {
          "name": "accommodation",
          "weight": 0.4
        }
      ],
      "aggregation": "weighted_label_mapping",
      "label_scores": {
        "restaurant": {
          "on_site": 1.0,
          "walking": 0.9,
          "nearby": 0.7,
          "available": 0.5,
          "none": 0.0
        },
        "accommodation": {
          "on_site": 1.0,
          "walking": 0.9,
          "nearby": 0.7,
          "available": 0.5,
          "none": 0.0
        }
      }
    }
  },

  "aip_feature_definitions": {
    "aip_ops_ifr_score": {
      "description": "IFR capability from official AIP data",
      "raw_fields": ["aip_ifr_available"],
      "computation": "lookup_table",
      "value_mapping": {
        "0": 0.1,
        "1": 0.4,
        "2": 0.6,
        "3": 0.8,
        "4": 1.0
      },
      "notes": "0.1 for VFR-only preserves utility as diversion option"
    },

    "aip_hospitality_score": {
      "description": "Hotel/restaurant from official AIP data",
      "raw_fields": ["aip_hotel_info", "aip_restaurant_info"],
      "computation": "weighted_component_sum",
      "component_mappings": {
        "aip_hotel_info": {
          "0": 0.0,
          "1": 0.6,
          "2": 1.0
        },
        "aip_restaurant_info": {
          "0": 0.0,
          "1": 0.6,
          "2": 1.0
        }
      },
      "component_weights": {
        "aip_hotel_info": 0.4,
        "aip_restaurant_info": 0.6
      }
    }
  }
}
```

**Configuration Structure:**

**Review Feature Definitions:**
- `aspects`: List of ontology aspects that contribute to this feature
  - Each aspect has a `name` (must exist in ontology) and `weight`
  - Multiple aspects are combined via weighted average
- `aggregation`: Method for combining aspect data
  - `"weighted_label_mapping"`: Map aspect labels to scores, then weighted average
- `label_scores`: Mapping of aspect labels to numeric scores [0, 1]
  - Can be flat (single aspect) or nested by aspect name (multiple aspects)
  - `null` values are treated as missing data

**AIP Feature Definitions:**
- `raw_fields`: List of raw AIP database fields used in computation
- `computation`: Method for computing score
  - `"lookup_table"`: Direct mapping from field value to score
  - `"weighted_component_sum"`: Weighted combination of multiple fields
- `value_mapping`: For lookup_table, maps raw values to scores
- `component_mappings` + `component_weights`: For weighted_component_sum, maps each field and combines

**Implementation in `features.py`:**

```python
class FeatureMapper:
    def __init__(self, config: FeatureMappingConfig):
        """Load feature definitions from config file."""
        self.config = config
        self.review_feature_defs = config.review_feature_definitions
        self.aip_feature_defs = config.aip_feature_definitions

    def compute_review_feature_scores(
        self,
        icao: str,
        distributions: Dict[str, Dict[str, float]]
    ) -> Dict[str, float]:
        """
        Compute ALL review-derived features from config definitions.
        No hard-coded logic - everything driven by config.
        """
        scores = {}
        for feature_name, definition in self.review_feature_defs.items():
            scores[feature_name] = self._compute_review_feature(
                definition, distributions
            )
        return scores

    def _compute_review_feature(
        self,
        definition: ReviewFeatureDefinition,
        distributions: Dict[str, Dict[str, float]]
    ) -> Optional[float]:
        """
        Compute a single review feature from its definition.

        Generic computation based on config - supports multiple aspects
        with different weights combined via weighted average.
        """
        if definition.aggregation == "weighted_label_mapping":
            total_score = 0.0
            total_weight = 0.0

            for aspect_config in definition.aspects:
                aspect_name = aspect_config["name"]
                aspect_weight = aspect_config["weight"]

                # Get label distribution for this aspect
                label_dist = distributions.get(aspect_name, {})
                if not label_dist:
                    continue

                # Get label scores for this aspect
                if isinstance(definition.label_scores, dict):
                    # Check if nested by aspect or flat
                    if aspect_name in definition.label_scores:
                        label_scores = definition.label_scores[aspect_name]
                    else:
                        label_scores = definition.label_scores
                else:
                    continue

                # Map labels to score using config
                aspect_score = self._map_labels_to_score(
                    label_dist,
                    label_scores
                )

                if aspect_score is not None:
                    total_score += aspect_weight * aspect_score
                    total_weight += aspect_weight

            return total_score / total_weight if total_weight > 0 else None

        return None

    def compute_aip_feature_scores(
        self,
        icao: str,
        aip_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Compute ALL AIP-derived features from config definitions.
        No hard-coded logic - everything driven by config.
        """
        scores = {}
        for feature_name, definition in self.aip_feature_defs.items():
            scores[feature_name] = self._compute_aip_feature(
                definition, aip_data
            )
        return scores

    def _compute_aip_feature(
        self,
        definition: AIPFeatureDefinition,
        aip_data: Dict[str, Any]
    ) -> Optional[float]:
        """
        Compute a single AIP feature from its definition.

        Supports multiple computation methods based on config.
        """
        if definition.computation == "lookup_table":
            # Simple value lookup
            field_name = definition.raw_fields[0]
            value = aip_data.get(field_name)
            if value is None:
                return None

            return definition.value_mapping.get(str(value))

        elif definition.computation == "weighted_component_sum":
            # Weighted combination of multiple fields
            total_score = 0.0
            total_weight = 0.0

            for field_name in definition.raw_fields:
                value = aip_data.get(field_name)
                if value is None:
                    continue

                # Map value to score
                component_score = definition.component_mappings[field_name].get(str(value))
                if component_score is None:
                    continue

                # Get weight
                weight = definition.component_weights[field_name]

                total_score += weight * component_score
                total_weight += weight

            return total_score / total_weight if total_weight > 0 else None

        return None
```

**Benefits of This Approach:**

1. **Change aspect contributions without code:**
   - Want hassle to include staff feedback more heavily? Edit JSON, change weight from 0.3 to 0.5
   - Want to add "fuel" aspect to hassle score? Add to aspects array

2. **Update label mappings without code:**
   - Think "expensive" should be 0.2 instead of 0.3? Edit JSON
   - Add new labels from ontology? Add to label_scores

3. **Tune AIP formulas without code:**
   - Want different IFR score mapping? Edit value_mapping
   - Change hospitality weights (60/40 vs 50/50)? Edit component_weights

4. **Easy to experiment:**
   - Test different scoring approaches by swapping config files
   - A/B test different feature definitions
   - Roll back by reverting config file

5. **Single source of truth:**
   - All feature logic documented in JSON
   - Easy to see what contributes to each feature
   - No need to read Python code to understand scoring

**What Still Requires Code Changes:**

- Adding completely new feature scores (new schema column needed)
- New aggregation methods beyond weighted_label_mapping and weighted_component_sum
- Complex custom formulas that don't fit declarative patterns

**Fallback Behavior:**

If `feature_mappings.json` is not provided, the system falls back to hard-coded defaults in `features.py` that match the config structure above. This ensures backward compatibility and provides working defaults out of the box.

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

### 4.7 AIP Notification Score Integration (Future Work)

**Status:** The notification parsing system is being developed separately and is **not part of this migration**.

**What's included in this migration:**
- ✅ Ensure persona scoring can handle missing notification data
- ✅ Don't break if notification features are added later

**What's NOT included:**
- ❌ Creating `ga_aip_rule_summary` table (will be added in future migration)
- ❌ Populating notification data
- ❌ Using `--parse-notifications` flag
- ❌ Integrating notification scores into hassle scoring

**Future integration (after this migration):**
- A separate notification parsing system will create its own table structure
- Notification scores may be added as a new feature (e.g., `aip_notification_score`)
- Personas can then weight notification scores independently
- For now, personas should only weight `review_hassle_score` for bureaucracy assessment

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

### 5.1 Feature Score Sources

Scores stored in `ga_airfield_stats` are organized by source:

**Review-Derived Scores** (from review tag parsing):
- `review_cost_score`       (0–1) - From 'cost' aspect labels
- `review_hassle_score`      (0–1) - From 'bureaucracy' aspect labels
- `review_review_score`      (0–1) - From 'overall_experience' aspect labels
- `review_ops_ifr_score`    (0–1) - From review tags about IFR operations
- `review_ops_vfr_score`    (0–1) - From review tags about VFR/runway quality
- `review_access_score`     (0–1) - From 'transport' aspect labels
- `review_fun_score`         (0–1) - From 'food' and 'overall_experience' aspects
- `review_hospitality_score` (0–1) - From 'restaurant' and 'accommodation' aspects

**AIP-Derived Scores** (computed from AIP raw data):
- `aip_ops_ifr_score`        (0–1) - Computed from `aip_ifr_available`
- `aip_hospitality_score`    (0–1) - Computed from `aip_hotel_info`, `aip_restaurant_info`

**Persona Scoring Approach:**

Personas compute scores using a **simple weighted sum** of all available feature scores. Each persona defines a weight vector over all feature scores (both review-derived and AIP-derived). If a persona doesn't care about a particular source or feature, they simply set its weight to 0.

**Available Feature Scores:**
- All review-derived scores: `review_cost_score`, `review_hassle_score`, `review_review_score`, `review_ops_ifr_score`, `review_ops_vfr_score`, `review_access_score`, `review_fun_score`, `review_hospitality_score`
- All AIP-derived scores: `aip_ops_ifr_score`, `aip_hospitality_score`

**Note:** Some features are only available from one source:
- `review_cost_score` - Only from reviews (fees are separate)
- `review_review_score` - Only from reviews (overall experience)
- `review_fun_score` - Only from reviews (subjective "fun" factor)
- `review_access_score` - Only from reviews (transport/accessibility)
- `aip_ops_ifr_score` - Only from AIP data (IFR capability)
- `aip_hospitality_score` - Only from AIP data (hotel/restaurant info)

### 5.1.1 Complete List of Weightable Features

Personas can assign weights to any of the following feature scores. This is the **canonical list** of all available features:

**Review-derived (8 features):**
1. `review_cost_score` - Cost/fee friendliness from pilot reviews
2. `review_hassle_score` - Bureaucracy/paperwork burden from reviews
3. `review_review_score` - Overall experience from reviews
4. `review_ops_ifr_score` - IFR operations quality from reviews
5. `review_ops_vfr_score` - VFR/runway quality from reviews
6. `review_access_score` - Transportation/accessibility from reviews
7. `review_fun_score` - "Fun factor" from food/vibe reviews
8. `review_hospitality_score` - Restaurant/hotel from reviews

**AIP-derived (2 features):**
9. `aip_ops_ifr_score` - IFR capability from official AIP data (0-4 scale)
10. `aip_hospitality_score` - Hotel/restaurant from official AIP data

**Total: 10 weightable features** (8 review + 2 AIP)

Personas omit features they don't care about (implicit weight = 0.0).

### 5.2 Persona Definitions

Personas are defined in `personas.json` (JSON format). Each persona is a **weight vector** over all available feature scores.

```json
{
  "version": "2.0",
  "personas": {
    "ifr_touring_sr22": {
      "label": "IFR touring (SR22)",
      "description": "Typical SR22T IFR touring mission: prefers solid IFR capability, reasonable fees, low bureaucracy. Some weight on hospitality for overnight stops.",
      "weights": {
        "aip_ops_ifr_score": 0.25,
        "review_hassle_score": 0.20,
        "review_cost_score": 0.20,
        "review_review_score": 0.15,
        "review_access_score": 0.10,
        "review_hospitality_score": 0.05,
        "aip_hospitality_score": 0.05
      },
      "missing_behaviors": {
        "aip_ops_ifr_score": "negative",
        "review_hospitality_score": "exclude",
        "aip_hospitality_score": "exclude"
      }
    },
    "vfr_budget": {
      "label": "VFR fun / budget",
      "description": "VFR sightseeing / burger runs: emphasis on cost, fun/vibe, hospitality (good lunch spot), and general GA friendliness.",
      "weights": {
        "review_cost_score": 0.30,
        "review_fun_score": 0.20,
        "review_hospitality_score": 0.20,
        "review_review_score": 0.15,
        "review_access_score": 0.10,
        "review_ops_vfr_score": 0.05
      },
      "missing_behaviors": {
        "review_hospitality_score": "neutral"
      }
    },
    "training": {
      "label": "Training field",
      "description": "Regular training/circuit work: solid runway, availability, low hassle, reasonable cost.",
      "weights": {
        "review_ops_vfr_score": 0.30,
        "review_hassle_score": 0.25,
        "review_cost_score": 0.20,
        "review_review_score": 0.15,
        "review_fun_score": 0.10
      },
      "missing_behaviors": {
        "review_hospitality_score": "exclude",
        "aip_hospitality_score": "exclude",
        "aip_ops_ifr_score": "exclude"
      }
    },
    "lunch_stop": {
      "label": "Lunch stop / day trip",
      "description": "Day trip destination: emphasis on great restaurant/café, good vibe, easy access, reasonable cost.",
      "weights": {
        "review_hospitality_score": 0.25,
        "aip_hospitality_score": 0.10,
        "review_fun_score": 0.25,
        "review_cost_score": 0.15,
        "review_hassle_score": 0.15,
        "review_access_score": 0.10
      },
      "missing_behaviors": {
        "review_hospitality_score": "negative",
        "aip_ops_ifr_score": "exclude"
      }
    }
  }
}
```

**Rules:**
- Weights should ideally sum to 1.0 (not strictly required, but recommended for interpretability)
- Feature names in weights are **actual database field names** with source prefix (e.g., `review_cost_score`, `aip_ops_ifr_score`)
- Features not mentioned have weight 0.0 (implicitly excluded)
- If a persona doesn't care about reviews, set all `review_*_score` weights to 0
- If a persona doesn't care about AIP data, set all `aip_*_score` weights to 0
- Versioned via `personas_version` in `ga_meta_info`

**Weight Validation:**
- **Normalization:** The scoring function normalizes by the sum of active weights: `score = Σ(w×v) / Σ(w)`
- Therefore, weights don't strictly need to sum to 1.0 (weights {0.3, 0.2, 0.5} produce the same result as {3, 2, 5})
- **Best Practice:** Weights should sum to 1.0 for readability and interpretability
- **Validation:** Persona loading should WARN (not error) if weights don't sum to 1.0 ± 0.01

Example validation:
```python
def validate_persona_weights(weights: Dict[str, float]) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        logger.warning(f"Persona weights sum to {total:.2f}, expected ~1.0")
```

**Feature Validation:**
- All weighted features must exist in `ga_airfield_stats` schema
- Unknown features raise a validation error at persona load time
- This prevents typos and ensures personas stay in sync with schema changes
- Available features are defined in: `shared/ga_friendliness/models.py::AirportFeatureScores`

**Missing Behaviors:**
- `neutral` (default): Treat missing value as 0.5 (average)
- `negative`: Treat missing as 0.0 (feature is required, missing = worst case)
- `positive`: Treat missing as 1.0 (rare, assume best case)
- `exclude`: Skip this feature entirely, re-normalize remaining weights

When a feature has weight 0.0, missing_behavior is irrelevant. Only specify missing_behaviors for features where the default (neutral) isn't appropriate.

### 5.3 Scoring Function

For airport `icao`, persona `P`:

```text
// Step 1: Apply missing value behavior for each feature
for each feature f in all_features:
    weight = weight_P[f]  // from persona config (0.0 if not specified)
    if weight == 0.0:
        continue  // Feature not used by this persona
    
    value = feature_value[f]  // read from ga_airfield_stats
    behavior = missing_behavior_P[f] or "neutral"
    effective_value[f] = resolve_missing(value, behavior)
    
    if behavior == "exclude" and value is NULL:
        continue  // Skip this feature entirely
    
    total_score += weight * effective_value[f]
    total_weight += weight

// Step 2: Normalize by total active weight
score_P(icao) = total_score / total_weight  (if total_weight > 0, else 0.5)
```

Where:

- `all_features` = all feature scores in `ga_airfield_stats`:
  - `review_cost_score`, `review_hassle_score`, `review_review_score`, `review_ops_ifr_score`, `review_ops_vfr_score`, `review_access_score`, `review_fun_score`, `review_hospitality_score`
  - `aip_ops_ifr_score`, `aip_hospitality_score`
- `weight_P[f]` is read from persona config (actual field names with source prefix)
- `feature_value[f]` is the raw value from `ga_airfield_stats` (may be NULL)
- `missing_behavior_P[f]` determines how to handle NULL feature values:
  - `neutral` (default): use 0.5 (average)
  - `negative`: use 0.0 (required feature, missing = worst case)
  - `positive`: use 1.0 (rare, assume best case)
  - `exclude`: skip feature entirely, don't include in `total_weight`
- `total_weight` = sum of weights for features that weren't excluded
- If `total_weight == 0` (all features excluded or missing), return default score of 0.5

**Example:**
- Persona has weights: `{"review_cost_score": 0.3, "aip_ops_ifr_score": 0.2, "review_hassle_score": 0.5}`
- Airport has: `review_cost_score = 0.8`, `aip_ops_ifr_score = NULL`, `review_hassle_score = 0.6`
- Missing behavior for `aip_ops_ifr_score` is `"negative"` → use 0.0
- Score = `(0.3 * 0.8 + 0.2 * 0.0 + 0.5 * 0.6) / (0.3 + 0.2 + 0.5)` = `0.54 / 1.0` = `0.54`

### 5.4 Where Scores Are Stored

**Runtime Computation:**

- Base feature scores (review-derived and AIP-derived) are stored in `ga_airfield_stats`
- Persona-specific composite scores are computed dynamically at runtime
- Runtime layer reads base features and computes persona scores using `personas.json` weight vectors (simple weighted sum)
- No schema changes needed for new personas or persona weight adjustments

**Benefits:**
- Flexibility for adding new personas without database changes
- Easy experimentation with different persona weights
- Clear separation: base features (stored) vs. persona scores (computed)

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
        -- Persona score computed at runtime from base features
        -- (computation logic not shown - handled by application layer)
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
            ORDER BY computed_persona_score DESC  -- Computed at runtime
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
- Configurable via JSON files (ontology, personas, feature mappings) or built-in defaults
- Environment variable support via `GA_FRIENDLINESS_` prefix

**Key modules:**
- `database.py` - Schema creation, versioning, migrations
- `builder.py` - Main pipeline orchestrator
- `models.py` - Pydantic models for all data structures
- `config.py` - Settings and configuration loading (with built-in defaults)
- `sources.py` - Review source implementations (CSV, JSON, airfield.directory, airports.db)
- `features.py` - Feature engineering and score mapping
- `personas.py` - Persona management and score computation
- `storage.py` - Database storage interface
- `ontology.py` - Ontology validation and filtering

**Reusable agents at `shared/` level:**

- `shared/ga_review_agent/` - LLM-based review processing
  - `extractor.py` - LangChain-based tag extraction with retry logic
  - `aggregator.py` - Tag aggregation with optional time decay
  - `summarizer.py` - LLM-generated airport summaries
- Both agents follow the same pattern as `shared/aviation_agent/` (same level, reusable in other contexts)

**Note:** AIP notification rule parsing is handled by a separate system (see separate notification requirements design document). The GA friendliness system only consumes the normalized notification scores from `ga_aip_rule_summary`.

### 7.2 Key Components

- **Review Sources:** Abstract interface (`ReviewSource`) with multiple implementations:
  - `AirfieldDirectorySource` - airfield.directory export JSON with caching
  - `AirportJsonDirectorySource` - Per-airport JSON files (filters AI-generated reviews)
  - `CSVReviewSource` - CSV files with configurable column mapping
  - `CompositeReviewSource` - Combines multiple sources
  - `AirportsDatabaseSource` - IFR metadata, hotel/restaurant info from airports.db
- **GA Review Agent:** `shared/ga_review_agent/` - LLM-based extraction (LangChain 1.0), aggregation, summarization
  - Batch processing for efficiency
  - Token usage tracking
  - Retry logic for transient failures
- **AIP Notification Integration:** Reads normalized notification scores from `ga_aip_rule_summary` table
  - Notification parsing handled by separate system (see notification requirements design document)
  - Scores integrated into `ga_hassle_score` feature
- **Feature Engineering:** Configurable mappings from label distributions to scores
  - Default mappings built-in
  - Optional custom mappings via JSON
- **Persona Scoring:** Weighted combination of base features with missing value handling
  - Configurable missing behaviors per persona/feature
  - Runtime computation from base feature scores
- **Incremental Updates:** Change detection and selective reprocessing
  - Resume capability (continue from last successful ICAO)
  - Timestamp-based change detection
- **CLI Tool:** `tools/build_ga_friendliness.py` for rebuilding database
  - Multiple source options (--export, --csv, --json-dir, --airports-db)
  - Incremental and resume modes
  - Comprehensive metrics output

### 7.3 Design Decisions

- **JSON config** (not YAML) - simpler, no extra dependencies
- **Built-in defaults** - Ontology and personas have default implementations, no external files required
- **Environment variable support** - All settings configurable via `GA_FRIENDLINESS_` prefixed env vars
- **LangChain 1.0** - modern API, good Pydantic integration
- **Optional AIP notification integration** - works with or without notification scores
- **Multiple source types** - Flexible ingestion from various formats
- **Incremental updates** - efficient for regular updates with resume capability
- **Schema versioning** - safe schema evolution with migration support
- **Comprehensive metrics** - track build progress, LLM usage, token costs, errors
- **Configurable failure modes** - continue, fail_fast, or skip on errors
- **Optional statistical extensions** - Time decay and Bayesian smoothing available but disabled by default for backward compatibility
- **IFR score granularity** - Integer score (0-4) for detailed IFR capability tracking
- **AIP metadata integration** - Hotel and restaurant info from airports.db stored directly in stats table

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
