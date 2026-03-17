# Data Update Pipeline

> Orchestrates AIP data fetching, change tracking, and derived database updates across AIRAC cycles.

## Intent

Aviation AIP data changes every 28 days (AIRAC cycle). This pipeline fetches data from multiple sources, tracks what changed, syncs derived databases, and stamps everything with the AIRAC cycle date for traceability.

## Architecture

```
┌─────────────────────┐
│  data_update.py     │  ← Main orchestrator
│  (modes: web,       │
│   autorouter, aip,  │
│   reviews, initial) │
└────────┬────────────┘
         │
    ┌────┴────────────────────────────────┐
    │                                      │
    ▼                                      ▼
┌──────────────┐                   ┌───────────────┐
│ aipexport.py │                   │ data_update.py │
│ (fetch AIP)  │                   │ sync_aip_derived()
│              │                   │                │
│ Sources:     │                   │ Calls:         │
│ - france_web │                   │ - build_ga_notifications.py
│ - uk_web     │                   │ - build_ga_friendliness.py --aip-only
│ - norway_web │                   │ - _stamp_airac_metadata()
│ - autorouter │                   └───────────────┘
└──────┬───────┘
       │
       ▼
┌──────────────────┐     ┌────────────────────┐     ┌──────────────────┐
│  airports.db     │────▶│ ga_notifications.db │     │  ga_persona.db   │
│                  │     │ (factual rules)     │     │ (scores/reviews) │
│ Tables:          │     └────────────────────┘     └──────────────────┘
│ - aip_entries    │
│ - *_changes (4)  │
│ - airac_updates  │
└──────────────────┘
```

## Key Components

### data_update.py — Orchestrator
Entry point for all data operations. Modes:

| Mode | What it does |
|------|-------------|
| `initial` | Full build from scratch (web → sync → reviews) |
| `web` | Fetch France/UK/Norway web sources → sync derived |
| `autorouter ED EB LO` | Fetch via autorouter for given prefixes → sync derived |
| `aip` | Sync derived data only (notifications + AIP fields) |
| `aip LF EG` | Sync for specific country prefixes |
| `reviews` | Update GA friendliness from airfield.directory reviews |
| `notifications` | Update notification rules only |

### aipexport.py — AIP Fetcher
Fetches AIP data from web or autorouter sources into `airports.db` via `euro_aip.DatabaseStorage`.

Key flags:
- `--airac-date YYYY-MM-DD` — target a specific AIRAC cycle (auto-detected if omitted)
- `--database` — existing DB to use as base
- `--database-storage` — output DB path
- `--france-web`, `--uk-web`, `--norway-web` — enable web sources
- `--autorouter` — enable autorouter source

Sets `storage.airac_date` before `save_model()` so all changes get tagged.

### aipchange.py — Change Viewer
Queries `*_changes` tables in `airports.db`.

Key flags:
- `--since today|yesterday|Nd|latest|YYYY-MM-DD` — date filter
- `--airac YYYY-MM-DD` — filter by AIRAC cycle date
- `--airac list` — show all recorded AIRAC updates
- `--field "Customs and immigration"` — filter by AIP field
- `--summary` — counts by type/airport/field

## AIRAC Tracking

### Change-level tracking (Option A)
All `*_changes` tables have an `airac_date TEXT` column:
- `aip_entries_changes` — AIP field changes
- `airports_changes` — airport metadata changes
- `runways_changes` — runway changes
- `procedures_changes` — procedure changes

Set via `DatabaseStorage.airac_date` property before saving. NULL for pre-tracking historical data.

### Cycle metadata (Option C)
`airac_updates` table in `airports.db`:

```sql
CREATE TABLE airac_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    airac_date TEXT NOT NULL,      -- e.g., "2026-02-19"
    source TEXT NOT NULL,           -- e.g., "france_eaip_html", "autorouter"
    fetched_at TEXT NOT NULL,       -- when the fetch ran
    airports_updated INTEGER,       -- airports processed
    changes_count INTEGER,          -- total field changes
    status TEXT DEFAULT 'success',  -- success/partial/failed
    UNIQUE(airac_date, source)
);
```

Populated automatically by `DatabaseStorage.save_model()` when `airac_date` is set.

### Derived database stamping
After `sync_aip_derived()`, `data_update.py` writes `last_airac_date` to:
- `ga_persona.db` → `ga_meta_info` table (key-value)
- `ga_notifications.db` → `metadata` table (created if missing)

These are informational — derived data is always recomputed from `airports.db`, not incrementally patched.

## Patterns

### Adding a new AIP source
1. Implement source in `euro_aip` library
2. Add CLI flag in `aipexport.py`
3. Add fetch function in `data_update.py`
4. The AIRAC tracking comes free via `DatabaseStorage.airac_date`

### Catching up multiple AIRAC cycles
Use `--airac-date` with `aipexport.py` directly (not via `data_update.py`):
```bash
python tools/aipexport.py --france-web --uk-web --norway-web \
  --database data/airports.db --database-storage data/airports.db \
  -c cache --airac-date 2026-01-22
python tools/data_update.py aip  # sync derived
# Then repeat for next cycle
```

### Querying changes by AIRAC cycle
```bash
python tools/aipchange.py --airac 2026-02-19 --summary
python tools/aipchange.py --airac 2026-02-19 --field "Customs and immigration"
```

## Gotchas

- `data_update.py web` auto-detects the current AIRAC date; autorouter always fetches latest available
- `--changed` mode in `build_ga_notifications.py` compares AIP text hashes — much faster than full rebuild
- `--aip-only` in `build_ga_friendliness.py` skips review processing (seconds vs minutes)
- Existing historical `_changes` rows have `airac_date = NULL` (pre-tracking)
- The `airac_updates` table uses `INSERT OR REPLACE` keyed on `(airac_date, source)` — re-running overwrites

## References

- [GA Friendliness Design](./GA_FRIENDLINESS_DESIGN.md) — scoring system that consumes AIP data
- [Notification Parsing Design](./NOTIFICATION_PARSING_DESIGN.md) — notification extraction from AIP text
- [Docker Deployment](./DOCKER_DEPLOYMENT.md) — how data files are deployed
- euro_aip library: `~/Developer/public/rzflight/euro_aip/euro_aip/storage/database_storage.py`
