# GA Friendliness Schema Migration Plan

This document outlines the changes needed to align the implementation with the updated `GA_FRIENDLINESS_DESIGN.md`.

## Overview

The schema has been restructured to:
1. Separate review-derived and AIP-derived feature scores with explicit prefixes
2. Simplify AIP raw data fields
3. Remove persona-specific composite scores (computed at runtime)
4. Encode hospitality info as integers instead of text

**Note:** Notification parsing integration is being worked on independently. This migration focuses on core GA friendliness scores only. Do not use `--parse-notifications` flag during this migration.

## Schema Changes

### Fields to Remove

- `mandatory_handling` (INTEGER)
- `ifr_procedure_available` (INTEGER) - merged into `aip_ifr_available`
- `notification_hassle_score` (REAL) - **Note:** Notification integration handled separately
- `score_ifr_touring` (REAL)
- `score_vfr_budget` (REAL)
- `score_training` (REAL)
- `ga_ops_vfr_score` (REAL) - AIP-derived version removed (review version kept)

### Fields to Rename/Change

- `ifr_score` → `aip_ifr_available` (keep 0-4 enum, just rename)
- `hotel_info` (TEXT) → `aip_hotel_info` (INTEGER: 0=unknown, 1=vicinity, 2=at_airport)
- `restaurant_info` (TEXT) → `aip_restaurant_info` (INTEGER: 0=unknown, 1=vicinity, 2=at_airport)

### Feature Scores to Rename (Add Prefixes)

**Review-derived scores** (add `review_` prefix):
- `ga_cost_score` → `review_cost_score`
- `ga_review_score` → `review_review_score`
- `ga_hassle_score` → `review_hassle_score`
- `ga_ops_ifr_score` → `review_ops_ifr_score`
- `ga_ops_vfr_score` → `review_ops_vfr_score`
- `ga_access_score` → `review_access_score`
- `ga_fun_score` → `review_fun_score`
- `ga_hospitality_score` → `review_hospitality_score`

**AIP-derived scores** (add `aip_` prefix, new fields):
- Add `aip_ops_ifr_score` (computed from `aip_ifr_available`)
- Add `aip_hospitality_score` (computed from `aip_hotel_info`, `aip_restaurant_info`)

## Implementation Changes Required

### 1. `shared/ga_friendliness/database.py`

**Schema creation:**
- Update `create_schema()` to match new schema structure
- Remove persona score columns
- Update field names and types
- Add `aip_` prefix to AIP raw data fields

**Key changes:**
```python
# OLD:
mandatory_handling INTEGER,
ifr_procedure_available INTEGER,
ifr_score INTEGER,
hotel_info TEXT,
restaurant_info TEXT,
ga_cost_score REAL,
...
score_ifr_touring REAL,

# NEW:
aip_ifr_available INTEGER,  -- 0=no IFR, 1=IFR permitted (no procedures), 2=non-precision, 3=RNP, 4=ILS
aip_night_available INTEGER,
aip_hotel_info INTEGER,  -- 0=unknown, 1=vicinity, 2=at_airport
aip_restaurant_info INTEGER,  -- 0=unknown, 1=vicinity, 2=at_airport
review_cost_score REAL,
review_hassle_score REAL,
...
aip_ops_ifr_score REAL,
aip_hospitality_score REAL,
-- (no persona score columns)
```

### 2. `shared/ga_friendliness/models.py`

**`AirportStats` model:**
- Remove: `mandatory_handling`, `ifr_procedure_available`, `notification_hassle_score`
- Rename: `ifr_score` → `aip_ifr_available`
- Change: `hotel_info`, `restaurant_info` from `Optional[str]` to `Optional[int]` with validation (0, 1, 2)
- Rename all `ga_*_score` fields to `review_*_score`
- Add: `aip_ops_ifr_score`, `aip_hospitality_score`
- Remove: persona score fields

**`AirportFeatureScores` model:**
- Split into two models or add source prefixes:
  - Option A: Create `ReviewFeatureScores` and `AIPFeatureScores` models
  - Option B: Keep single model but rename fields with prefixes
- Remove `notification_hassle_score` parameter from hassle score computation
- **Note:** Notification scores are handled separately and not part of this migration

### 3. `shared/ga_friendliness/features.py`

**Hospitality Text Classification:**

Add the following code to classify AIP hospitality text:

```python
import re
from typing import Optional

# Patterns for detecting "at airport" facilities
PAT_AT = re.compile(
    r"""
    ^\s*(?:yes|si|sí|ja|oui)\b
    |
    \b(?:at|on)\s+(?:the\s+)?(ad|aerodrome|airport|airfield|terminal|site)\b
    |
    \bon\s+site\b
    |
    \bin\s+(?:the\s+)?terminals?\b
    |
    \bterminal\s+building\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Patterns for detecting "vicinity" facilities
PAT_VICINITY = re.compile(
    r"""
    \bvicinity\b
    |
    \bnearby\b
    |
    \bnear\s+(?:the\s+)?(ad|aerodrome|airport|airfield)\b
    |
    \bwithin\s+\d+\s*(km|nm|mi|miles)\b
    |
    \b\d+\s*(km|nm|mi|miles)\s*(fm|from)\s+(the\s+)?(ad|aerodrome|airport|airfield)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

def classify_facility(text: Optional[str]) -> str:
    """
    Classify facility location from AIP text.
    
    Returns:
        "at_airport", "vicinity", or "none"
    """
    if not isinstance(text, str):
        return "none"
    s = text.strip()
    if not s or s.lower() in {"-", "nil"}:
        return "none"
    if re.match(r"^\s*no\.?\s*$", s, re.IGNORECASE):
        return "none"
    if PAT_AT.search(s):
        return "at_airport"
    if PAT_VICINITY.search(s):
        return "vicinity"
    return "none"

def parse_hospitality_text_to_int(text: Optional[str]) -> int:
    """
    Parse AIP hospitality text to integer encoding.
    
    Args:
        text: AIP text describing hotel/restaurant availability
        
    Returns:
        0 = unknown/none
        1 = vicinity
        2 = at_airport
    """
    classification = classify_facility(text)
    if classification == "at_airport":
        return 2
    elif classification == "vicinity":
        return 1
    else:
        return 0
```

**New functions needed:**
- `parse_hospitality_text_to_int(text: Optional[str]) -> int`:
  - Parse AIP text to integer encoding (0=unknown/none, 1=vicinity, 2=at_airport)
  - Implementation provided below

**`FeatureMapper` class changes:**
- Split `compute_feature_scores()` into:
  - `compute_review_feature_scores()` - returns review-derived scores
  - `compute_aip_feature_scores()` - returns AIP-derived scores
- Update `map_ops_ifr_score()` to use `aip_ifr_available` (0-4 enum) instead of boolean
- Remove `notification_hassle_score` parameter from `map_hassle_score()` (notification integration handled separately)
- Add `map_aip_ops_ifr_score(aip_ifr_available: int) -> float`
- Add `map_aip_hospitality_score(hotel_info: int, restaurant_info: int) -> float`
- Remove `map_ops_vfr_score()` for AIP (keep review version)

**Formula updates:**
- `aip_ops_ifr_score`: `if aip_ifr_available == 0 then 0.1 else (aip_ifr_available / 4.0 * 0.8 + 0.2)`
- `aip_hospitality_score`: `0.6 * restaurant_score + 0.4 * hotel_score` where:
  - `restaurant_score = 1.0 if aip_restaurant_info == 2 else (0.6 if aip_restaurant_info == 1 else 0.0)`
  - `hotel_score = 1.0 if aip_hotel_info == 2 else (0.6 if aip_hotel_info == 1 else 0.0)`

**New method:**
```python
def map_aip_hospitality_score(
    self,
    hotel_info: int,
    restaurant_info: int,
) -> float:
    """
    Map hotel and restaurant integer encodings to hospitality score.
    
    Args:
        hotel_info: 0=unknown, 1=vicinity, 2=at_airport
        restaurant_info: 0=unknown, 1=vicinity, 2=at_airport
        
    Returns:
        Normalized score [0, 1]
    """
    hotel_score = 1.0 if hotel_info == 2 else (0.6 if hotel_info == 1 else 0.0)
    restaurant_score = 1.0 if restaurant_info == 2 else (0.6 if restaurant_info == 1 else 0.0)
    return 0.6 * restaurant_score + 0.4 * hotel_score
```

### 4. `shared/ga_friendliness/storage.py`

**`write_airfield_stats()` method:**
- Update SQL INSERT statement with new field names
- Update parameter tuple to match new model fields
- Remove persona score fields

**`get_airfield_stats()` method:**
- Update field mapping to read new column names
- Handle integer hospitality fields instead of text
- Map new field names to model attributes

### 5. `shared/ga_friendliness/builder.py`

**`_process_airport()` method:**
- Update AIP metadata extraction:
  - Use `aip_ifr_available` instead of separate `ifr_score` and `ifr_procedure_available`
  - Parse `hotel_info` and `restaurant_info` text to integers
- Split feature score computation:
  - Compute review-derived scores separately
  - Compute AIP-derived scores separately
- Update `AirportStats` construction with new field names
- Remove persona score computation (runtime only now)

**Key changes:**
```python
# OLD:
ifr_score = metadata.get("ifr_score", 0)
ifr_available = metadata.get("ifr_permitted", False)
hotel_info = metadata.get("hotel_info")  # TEXT
restaurant_info = metadata.get("restaurant_info")  # TEXT

feature_scores = self.feature_mapper.compute_feature_scores(...)
persona_scores = self.persona_manager.compute_scores_for_all_personas(feature_scores)

# NEW:
from shared.ga_friendliness.features import parse_hospitality_text_to_int

aip_ifr_available = metadata.get("ifr_score", 0)  # 0-4 enum
hotel_text = metadata.get("hotel_info")
aip_hotel_info = parse_hospitality_text_to_int(hotel_text)  # 0, 1, or 2
restaurant_text = metadata.get("restaurant_info")
aip_restaurant_info = parse_hospitality_text_to_int(restaurant_text)  # 0, 1, or 2

review_scores = self.feature_mapper.compute_review_feature_scores(
    icao=icao,
    distributions=distributions,
)
aip_scores = self.feature_mapper.compute_aip_feature_scores(
    icao=icao,
    aip_ifr_available=aip_ifr_available,
    aip_hotel_info=aip_hotel_info,
    aip_restaurant_info=aip_restaurant_info,
)
# No persona score computation here (runtime only)
```

### 6. `shared/ga_friendliness/sources.py`

**`AirportsDatabaseSource` class:**
- Add `parse_hospitality_text_to_int()` method or import from features
- Update `get_airport_metadata()` to return integer hospitality values
- Or keep text extraction and do parsing in builder

### 7. `shared/ga_friendliness/personas.py`

**`PersonaManager` class:**
- Update to handle source preferences (prefer_review, prefer_aip, prefer_combined, etc.)
- Update `compute_score()` to:
  - Read both `review_*_score` and `aip_*_score` fields
  - Apply source preference strategy per feature
  - Combine scores based on persona configuration
- Update field name references from `ga_*_score` to logical names with source resolution

**New logic needed:**
```python
def _resolve_feature_score(
    self,
    feature_name: str,  # e.g., "ops_ifr_score"
    review_score: Optional[float],
    aip_score: Optional[float],
    source_preference: str
) -> Optional[float]:
    """Resolve feature score based on source preference."""
    if source_preference == "prefer_review":
        return review_score if review_score is not None else aip_score
    elif source_preference == "prefer_aip":
        return aip_score if aip_score is not None else review_score
    elif source_preference == "prefer_combined":
        if review_score is not None and aip_score is not None:
            return 0.7 * review_score + 0.3 * aip_score
        return review_score or aip_score
    # ... etc
```

### 8. `tools/build_ga_friendliness.py`

**Changes needed:**
- **No direct changes required** - This file uses abstractions (builder, sources) that handle schema details
- **Verification needed:**
  - Ensure `AirportsDatabaseSource` integration still works (provides IFR/hotel/restaurant metadata)
  - CLI arguments and options remain unchanged
  - The tool will automatically use new schema once underlying modules are updated

**What to verify after migration:**
- `--airports-db` flag still provides AIP metadata correctly
- Build summary output still shows correct metrics
- No errors when building with new schema

**Note on Notification Parsing:**
- Notification parsing (`--parse-notifications` flag) is being worked on independently
- For now, **do not use `--parse-notifications`** during migration
- The notification agent will be updated separately to work with the new schema
- Focus migration efforts on core friendliness scores only

### 9. Persona Configuration Updates

**`personas.json` structure:**
- Update field names in weights to logical names (without prefix):
  - `ga_cost_score` → `cost_score`
  - `ga_ops_ifr_score` → `ops_ifr_score`
  - etc.
- Add `source_preferences` section to persona configs
- Update default personas in `config.py` if they exist

## Migration Strategy

### Option 1: Clean Slate (Recommended)
Since backward compatibility is not required:
1. Drop and recreate `ga_meta.sqlite` database
2. Update all code to new schema
3. Rebuild from scratch

### Option 2: Migration Script
If existing data needs to be preserved:
1. Create migration script to:
   - Rename columns
   - Convert hospitality text to integers
   - Split combined scores into review/AIP scores
   - Remove persona score columns
2. Update schema version
3. Run migration

## Testing Checklist

- [ ] Schema creation matches design
- [ ] Hotel/restaurant text parsing to integers works correctly
- [ ] Review-derived scores computed and stored with `review_` prefix
- [ ] AIP-derived scores computed and stored with `aip_` prefix
- [ ] Persona scoring works with source preferences
- [ ] Runtime persona score computation works
- [ ] Storage read/write operations work with new field names
- [ ] Builder pipeline produces correct output
- [ ] All tests updated and passing

## Files to Modify

1. `shared/ga_friendliness/database.py` - Schema definition
2. `shared/ga_friendliness/models.py` - Pydantic models
3. `shared/ga_friendliness/features.py` - Feature computation logic
4. `shared/ga_friendliness/storage.py` - Database operations
5. `shared/ga_friendliness/builder.py` - Pipeline orchestration
6. `shared/ga_friendliness/personas.py` - Persona scoring with source preferences
7. `shared/ga_friendliness/sources.py` - Hospitality parsing (optional)
8. `shared/ga_friendliness/config.py` - Default persona configs (if any)
9. All test files in `tests/ga_friendliness/`

## Estimated Effort

- Schema changes: ~2 hours
- Model updates: ~2 hours
- Feature computation refactoring: ~4 hours
- Storage layer updates: ~2 hours
- Builder updates: ~3 hours
- Persona scoring with source preferences: ~4 hours
- Testing and validation: ~4 hours

**Total: ~21 hours**

**Note:** Notification agent updates are handled separately and not included in this estimate.

## Additional Notes

### Notification Integration (Out of Scope)

The notification parsing system (`shared/ga_notification_agent`) is being updated independently. For this migration:

- **Do not use `--parse-notifications` flag** during migration
- Notification-related schema changes (`ga_aip_rule_summary` table) are preserved but not actively used
- Once notification agent is updated, it will integrate with the new schema
- Notification scores will be consumed at runtime from `ga_aip_rule_summary` when computing persona scores (future integration)

### Backward Compatibility

Since backward compatibility is not required:
- Old databases can be dropped and recreated
- No migration scripts needed
- Clean implementation of new schema

