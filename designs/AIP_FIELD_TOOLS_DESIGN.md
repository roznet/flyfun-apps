# AIP Field Query Tools Design

> Tools for querying raw AIP field values and change history across airports.

**Issue:** #33 — Extra tools for AIP field  
**Status:** Implementation

---

## Overview

Two new tools for the MCP server and aviation chatbot to let users query **raw AIP standard field values** across airports:

1. **`list_aip_fields`** — Discover available AIP standard fields (names, IDs, descriptions)
2. **`query_aip_fields`** — Retrieve field values for airports matching criteria, with optional change history

### Example Queries

| User Query | Tool Flow |
|------------|-----------|
| "Show me all custom fields for point of entry in France" | `query_aip_fields(field="Customs and immigration", country="FR")` |
| "Show me maintenance fields along the route" | `find_airports_near_route(...)` → `query_aip_fields(field="Maintenance", icao_codes=[...])` |
| "What restaurant fields changed in France recently?" | `query_aip_fields(field="Restaurants", country="FR", changed_since="2026-01-01")` |
| "ATS hours for airports near Lyon" | `find_airports_near_location(...)` → `query_aip_fields(field="ATS", icao_codes=[...])` |
| "What AIP fields are available?" | `list_aip_fields()` |

---

## Design Decisions

### D1: Two tools (not 1 or 3+)
- `list_aip_fields` for discovery + `query_aip_fields` for values & changes
- Matches existing pattern: `browse_rules` (discovery) / `answer_rules_question` (query)
- Change history via optional `changed_since` parameter (not a separate tool)

### D2: Hybrid field documentation
- Common fields listed in tool description (6 most-used)
- Full list via `list_aip_fields` tool for discovery
- Avoids prompt bloat while supporting the 80% case

### D3: Airport scoping via country + ICAOs
- `country` filter for "all airports in France" queries (most common)
- Optional `icao_codes` for explicit airport lists (from prior search/route tools)
- Geographic queries chain: existing tool → `query_aip_fields(icao_codes=[...])`
- No duplication of location/route search logic

### D4: Staleness metadata included
- Per-country AIRAC date (from `DatabaseStorage.get_country_coverage()`)
- Per-field change timestamps when `changed_since` is used (from `aip_entries_changes` table)

---

## euro_aip Library Usage

### What we use from the library

| API | Purpose |
|-----|---------|
| `model.airports.by_country(code)` | Filter airports by country |
| `model.airports[icao]` / `.get(icao)` | Lookup by ICAO |
| `airport.aip_entries` | Access all AIP entries for an airport |
| `airport.get_standardized_entries()` | Get only standardized (mapped) entries |
| `entry.std_field` / `entry.std_field_id` | Field name and numeric ID |
| `entry.value` / `entry.section` / `entry.source` | Field data |
| `storage.get_country_coverage()` | AIRAC dates for staleness |

### What the library does NOT provide (requires local helpers)

| Need | Current Workaround | Future Library Enhancement |
|------|-------------------|---------------------------|
| List distinct standard fields across dataset | Iterate all airports and collect `std_field`/`std_field_id` | `model.airports.distinct_std_fields()` |
| Query `aip_entries_changes` table | Raw SQL via `storage.database_path` | `storage.get_field_changes(field_id, since, country)` |
| Batch query: "get field X for all airports matching Y" | Iterate + filter | `model.airports.by_country("FR").aip_field(501)` |

**Important:** Local helpers are structured in a dedicated `_aip_field_helpers` section of `airport_tools.py` for easy extraction to the library later. See `future-euroaip-update.md` for the recommended upstream API.

---

## Tool Specifications

### `list_aip_fields`

**Parameters:** None

**Response:**
```python
{
    "fields": [
        {
            "std_field_id": 101,
            "std_field": "Name of aerodrome",
            "section": "admin",
            "airport_count": 2345,  # How many airports have this field
        },
        # ... all standard fields
    ],
    "total_fields": 25,
    "total_airports_with_aip_data": 3200,
}
```

**Implementation:** Iterates `model.airports.with_aip_data()`, collects distinct `(std_field, std_field_id, section)` tuples, counts airports per field.

### `query_aip_fields`

**Parameters:**
```python
{
    "field": str,              # Required — std_field name or std_field_id (e.g., "Customs and immigration" or "302")
    "country": str | None,     # Optional — ISO-2 country code filter
    "icao_codes": list[str] | None,  # Optional — explicit ICAO list
    "changed_since": str | None,     # Optional — ISO date, only return airports where field changed
    "max_results": int,        # Default 20 — limit response size
}
```

**Response (normal query):**
```python
{
    "field": {"std_field": "Customs and immigration", "std_field_id": 302},
    "airports": [
        {
            "icao": "LFAT",
            "name": "Le Touquet",
            "country": "FR",
            "value": "Customs available H24...",
            "source": "sia",
        },
        # ...
    ],
    "total_matches": 145,
    "returned": 20,
    "staleness": {
        "country_airac_dates": {"FR": "2026-03-20", "DE": "2026-03-20"},
    },
}
```

**Response (with `changed_since`):**
```python
{
    "field": {"std_field": "Restaurants", "std_field_id": 502},
    "airports": [
        {
            "icao": "LFAT",
            "name": "Le Touquet",
            "country": "FR",
            "value": "Restaurant at airport",
            "previous_value": "Restaurant in vicinity",
            "changed_at": "2026-02-15T10:30:00",
        },
    ],
    "total_matches": 12,
    "returned": 12,
    "staleness": {
        "country_airac_dates": {"FR": "2026-03-20"},
        "changes_queried_since": "2026-01-01",
    },
}
```

---

## Implementation Details

### Field Resolution

The `field` parameter accepts either a field name or numeric ID:
```python
def _resolve_field(field: str, known_fields: dict) -> tuple[str, int] | None:
    """Resolve field name or ID to (std_field, std_field_id)."""
    # Try numeric ID first
    if field.isdigit():
        field_id = int(field)
        match = known_fields.get(field_id)
        if match:
            return (match["std_field"], field_id)
    # Try name match (case-insensitive, partial)
    field_lower = field.lower()
    for fid, info in known_fields.items():
        if field_lower in info["std_field"].lower():
            return (info["std_field"], fid)
    return None
```

### Airport Selection

```python
def _select_airports(model, country=None, icao_codes=None):
    """Select airports using euro_aip collection API."""
    airports = model.airports.with_aip_data()
    if country:
        airports = airports.by_country(country.upper())
    if icao_codes:
        icao_set = {c.upper() for c in icao_codes}
        airports = airports.filter(lambda a: a.ident in icao_set)
    return airports
```

### Change History Query

Requires raw SQL on `aip_entries_changes` table (not yet exposed by euro_aip):
```python
def _query_field_changes(db_path, std_field_id, since_date, country=None):
    """Query aip_entries_changes for field modifications.
    
    NOTE: This is a local helper that should be moved to 
    euro_aip DatabaseStorage. See future-euroaip-update.md.
    """
    conn = sqlite3.connect(db_path)
    # ... SQL query on aip_entries_changes ...
```

### Staleness Info

Uses existing `storage.get_country_coverage()` to add per-country AIRAC dates, filtered to countries present in the result set.

---

## Planner Prompt Additions

```
**AIP Field Tools - Which to Use:**
- list_aip_fields: To discover what AIP data fields are available
- query_aip_fields: To get raw AIP field values for airports
  - Use 'country' for country-wide queries ("customs fields in France")
  - Use 'icao_codes' after a search/route tool for geographic queries
  - Use 'changed_since' for change history ("what changed recently")
  - Common fields: Customs and immigration, Hotels, Restaurants, ATS, Maintenance, Type of Traffic permitted

Examples:
- "customs info for French airports" → query_aip_fields(field="Customs and immigration", country="FR")
- "what AIP fields exist?" → list_aip_fields()
- "restaurant changes in France this year" → query_aip_fields(field="Restaurants", country="FR", changed_since="2026-01-01")
- "ATS hours near Lyon" → [first find_airports_near_location, then] query_aip_fields(field="ATS", icao_codes=[...])
```

---

## Files Changed

| File | Changes |
|------|---------|
| `shared/airport_tools.py` | Add `list_aip_fields()`, `query_aip_fields()`, helper functions, tool specs |
| `mcp_server/main.py` | Add MCP wrappers for both tools |
| `configs/aviation_agent/prompts/planner_v1.md` | Add AIP field tool guidance |
| `designs/AIP_FIELD_TOOLS_DESIGN.md` | This document |
| `future-euroaip-update.md` | Recommendations for upstream library enhancements |

---

## Testing

```python
# test_list_aip_fields.py
def test_returns_fields():
    result = list_aip_fields(ctx)
    assert result["total_fields"] > 0
    assert all("std_field_id" in f for f in result["fields"])

# test_query_aip_fields.py
def test_query_by_country():
    result = query_aip_fields(ctx, field="Restaurants", country="FR")
    assert all(a["country"] == "FR" for a in result["airports"])

def test_query_by_icao_codes():
    result = query_aip_fields(ctx, field="302", icao_codes=["LFAT", "LFPG"])
    assert len(result["airports"]) <= 2

def test_query_with_changes():
    result = query_aip_fields(ctx, field="Restaurants", country="FR", changed_since="2025-01-01")
    assert all("changed_at" in a for a in result["airports"])

def test_field_resolution_by_name():
    result = query_aip_fields(ctx, field="customs")  # partial match
    assert result["field"]["std_field_id"] == 302

def test_staleness_info():
    result = query_aip_fields(ctx, field="Hotels", country="FR")
    assert "staleness" in result
    assert "FR" in result["staleness"]["country_airac_dates"]
```
