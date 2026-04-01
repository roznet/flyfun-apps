# Future euro_aip Library Enhancements

> Recommendations for upstream API additions to `euro_aip` (roznet/rzflight)
> to replace local workarounds in flyfun-apps.

**Context:** Issue #33 added AIP field query tools to flyfun-apps. Several helpers
were implemented locally because the euro_aip library doesn't yet expose the
needed APIs. This document describes what should be added to the library and
how flyfun-apps code should be updated afterwards.

---

## 1. Distinct Standard Fields Discovery

### Current Workaround (flyfun-apps)
```python
# shared/airport_tools.py :: _aip_collect_std_fields()
# Iterates ALL airports, collects distinct (std_field, std_field_id, section)
for airport in model.airports.with_aip_data():
    for entry in airport.aip_entries:
        # collect std_field_id → {name, section, count}
```

**Problem:** O(airports × entries) scan every call. No caching.

### Recommended euro_aip API

**Option A: Collection method (preferred)**
```python
# On AirportCollection
fields = model.airports.distinct_std_fields()
# Returns: list[dict] with keys: std_field_id, std_field, section, airport_count
```

**Option B: DatabaseStorage method**
```python
fields = storage.get_distinct_std_fields()
# SQL: SELECT DISTINCT std_field, std_field_id, section, COUNT(DISTINCT airport_icao)
#      FROM aip_entries WHERE std_field IS NOT NULL GROUP BY std_field_id
```

Option B is more efficient (single SQL query) but requires the storage object.
Option A fits the fluent collection API better and can delegate to B internally.

### flyfun-apps Cleanup
Replace `_aip_collect_std_fields(ctx.model)` with:
```python
fields = ctx.model.airports.distinct_std_fields()
# or
fields = ctx.storage.get_distinct_std_fields()
```

---

## 2. Batch AIP Field Query

### Current Workaround (flyfun-apps)
```python
# shared/airport_tools.py :: _aip_get_field_values()
# Iterates airports, scans aip_entries for matching std_field_id
for airport in airports:
    for entry in airport.aip_entries:
        if entry.std_field_id == target_id:
            results.append(...)
```

**Problem:** Loads all entries for each airport just to find one field.

### Recommended euro_aip API

**Option A: Collection method with field accessor**
```python
# Chainable field extraction
results = (model.airports
    .by_country("FR")
    .with_aip_data()
    .aip_field(302))  # Returns list[dict] with icao, name, value, source
```

**Option B: DatabaseStorage direct query**
```python
results = storage.get_aip_field_values(
    std_field_id=302,
    country="FR",      # optional
    icao_codes=None,    # optional
    limit=20,
)
# SQL: SELECT a.ident, a.name, e.value, e.source
#      FROM airports a JOIN aip_entries e ON a.ident = e.airport_icao
#      WHERE e.std_field_id = ? AND a.iso_country = ?
```

Option B is significantly more efficient — single SQL join instead of loading
all Airport objects and scanning their entries.

### flyfun-apps Cleanup
Replace `_aip_get_field_values(ctx.model, ...)` with:
```python
results = ctx.storage.get_aip_field_values(std_field_id=302, country="FR")
```

---

## 3. Change History Query

### Current Workaround (flyfun-apps)
```python
# shared/airport_tools.py :: _aip_get_field_changes()
# Raw SQL directly on aip_entries_changes via storage.database_path
conn = sqlite3.connect(storage.database_path)
conn.execute("""
    SELECT airport_icao, old_value, new_value, changed_at, source
    FROM aip_entries_changes
    WHERE std_field_id = ? AND changed_at >= ?
""", ...)
```

**Problem:** Bypasses the library entirely, couples to internal schema.

### Recommended euro_aip API

```python
changes = storage.get_field_changes(
    std_field_id=302,
    since="2026-01-01",     # ISO date string
    country="FR",           # optional
    icao_codes=None,        # optional
    limit=20,
)
# Returns: list[dict] with keys:
#   airport_icao, old_value, new_value, changed_at, source
```

This encapsulates the change tracking schema and allows the library to
evolve its internal schema without breaking consumers.

### flyfun-apps Cleanup
Replace `_aip_get_field_changes(ctx.storage, ...)` with:
```python
changes = ctx.storage.get_field_changes(
    std_field_id=302,
    since="2026-01-01",
    country="FR",
)
```

---

## 4. Staleness / AIRAC Metadata

### Current State
`storage.get_country_coverage()` already exists and is used directly.
No changes needed.

---

## Migration Checklist

When the euro_aip library is updated with these APIs:

1. **Bump euro_aip version** in `requirements.txt` to the version with new APIs
2. **Replace helpers** in `shared/airport_tools.py`:
   - Delete `_aip_collect_std_fields()` → use `storage.get_distinct_std_fields()`
   - Delete `_aip_get_field_values()` → use `storage.get_aip_field_values()`
   - Delete `_aip_get_field_changes()` → use `storage.get_field_changes()`
3. **Remove raw SQL imports** (`_sqlite3`) from the AIP field section
4. **Update tests** to use the library methods
5. **Delete this file** once migration is complete

---

## Implementation Priority

| Enhancement | Impact | Effort | Priority |
|------------|--------|--------|----------|
| `get_field_changes()` | High (eliminates raw SQL) | Medium | P1 |
| `get_aip_field_values()` | High (performance) | Low | P1 |
| `get_distinct_std_fields()` | Medium (convenience) | Low | P2 |
| Collection `aip_field()` method | Nice-to-have (fluent API) | Medium | P3 |
