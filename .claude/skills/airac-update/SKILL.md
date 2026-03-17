---
name: airac-update
description: Update AIP data for a new AIRAC cycle (web sources + autorouter), verify changes, and optionally commit/push
---

# AIRAC Data Update

Run this after each AIRAC cycle to update all AIP data, verify the results, and commit.

## Pre-flight checks

1. Activate the venv: `source venv/bin/activate`
2. Ensure working tree is clean for data files (`git status data/`)
3. Show which AIRAC cycles have been applied:
   ```
   python tools/aipchange.py --airac list
   ```
   If no airac_updates table exists yet, fall back to checking update dates:
   ```
   python -c "import sqlite3; conn=sqlite3.connect('data/airports.db'); print(conn.execute('SELECT DISTINCT date(updated_at) as d FROM aip_entries ORDER BY d DESC LIMIT 5').fetchall())"
   ```
4. Tell the user the latest AIRAC cycle in the database, compute the current effective AIRAC cycle, and confirm before proceeding. If multiple cycles need catching up, offer to run them sequentially.

## Step 1: Fetch web sources (France, UK, Norway)

```
python tools/data_update.py web
```

This fetches AIP from web sources and syncs derived data (notifications + AIP fields in ga_persona.db).

To fetch a specific AIRAC cycle (e.g., when catching up on multiple cycles), pass `--airac-date` to the underlying aipexport.py. The data_update.py wrapper doesn't support this directly, so run aipexport.py manually:
```
python tools/aipexport.py --database data/airports.db --france-web --uk-web --norway-web --database-storage data/airports.db -c cache --airac-date YYYY-MM-DD
```
Then sync derived data with: `python tools/data_update.py aip`

## Step 2: Fetch autorouter (Germany, Belgium, Austria)

```
python tools/data_update.py autorouter ED EB LO
```

This fetches AIP via autorouter for airports with existing AIP entries in those prefixes, then syncs derived data.
Note: autorouter doesn't support AIRAC date selection — it always fetches the latest available data.

## Step 3: Verify and summarize changes

Run these checks and present results to the user:

### 3a. Change summary
```
python tools/aipchange.py --since today --summary
```

### 3b. Detailed changes for high-impact fields

Show customs/immigration changes:
```
python tools/aipchange.py --since today --field "Customs and immigration"
```

Show ATS changes:
```
python tools/aipchange.py --since today --field "ATS"
```

Show Fuelling changes:
```
python tools/aipchange.py --since today --field "Fuelling"
```

### 3c. Notification processing check

Verify ga_notifications.db was updated — check for any airports with confidence 0.0 (failed extraction):
```
sqlite3 data/ga_notifications.db "SELECT icao, rule_type, confidence, summary FROM ga_notification_requirements WHERE confidence < 0.3 ORDER BY confidence ASC LIMIT 10;"
```

### 3d. Database sanity check

Check total airport counts are reasonable:
```
sqlite3 data/airports.db "SELECT substr(airport_icao, 1, 2) as prefix, count(*) as cnt FROM aip_entries GROUP BY prefix ORDER BY cnt DESC;"
```

## Step 4: Present summary to user

Format a clear summary with:
- AIRAC cycle date
- Total number of changes (by type and by country prefix)
- Top changed airports
- Top changed fields
- Any warnings (low confidence notifications, missing data, Norway web issues)
- Customs/immigration changes (always show these as they're operationally important)

Then ask: **"Are you happy with these changes? Should I commit and push?"**

## Step 5: Commit and push (only after user confirms)

Stage only the data files:
```
git add data/airports.db data/ga_notifications.db data/ga_persona.db
```

Commit with AIRAC cycle reference:
```
git commit -m "data: update AIP data for AIRAC cycle YYYY-MM-DD

- Web sources: France, UK, Norway
- Autorouter: ED (Germany), EB (Belgium), LO (Austria)
- N airports changed, N notification rules updated

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Then push:
```
git push origin main
```
