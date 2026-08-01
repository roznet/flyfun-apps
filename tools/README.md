# FlyFun Tools

Python utilities that ingest Eurocontrol AIP material, merge multiple sources, and export aviation data products. All scripts rely on the shared `euro_aip` models from the `rzflight` project and a configured `airports.db` path.

## Environment Setup

- Copy `dev.env.sample` to `dev.env`, update the absolute paths, then source it before running any tool:

```bash
cp dev.env.sample dev.env
${EDITOR:-vi} dev.env    # set AIRPORTS_DB, RULES_JSON, etc.
source dev.env
```

- Required variables:
  - `AIRPORTS_DB`: path to the SQLite database you want to read/write
  - `RULES_JSON`: path to the standardized rules file (used by some exports)
  - `LOG_LEVEL`: optional logging level override

> Keep separate copies such as `prod.env` for other environments.

## Tool Matrix

| Script | High-Level Purpose |
| --- | --- |
| `aipexport.py` | Aggregate multiple AIP sources into a consolidated `EuroAipModel`, then persist to SQLite and/or JSON. |
| `aip.py` | Low-level commands for fetching AIP data from specific sources (Autorouter, France AIP, UK AIP, etc.), parsing PDFs/HTML, and analyzing stored data. |
| `aipchange.py` | Compare two AIP sources (e.g., sequential AIRAC cycles) and report field-level deltas. |
| `bordercrossingexport.py` | Build a model enriched with customs/border crossing data and export it to database/JSON for downstream use. |
| `foreflight.py` | Create ForeFlight content packs (KML/CSV + manifest) from the Euro AIP database or custom Excel definitions. |
| `starlink.py` | Build a ForeFlight map layer showing where Starlink coastal coverage ends (the 12 NM offshore limit). |
| `ffpack.py` | Shared helper, not a CLI: content pack directory + `manifest.json` handling, used by `foreflight.py` and `starlink.py`. |

## `aipexport.py`

- **Use when** you want a unified `airports.db` populated from web downloads, local eAIP distributions, Autorouter, or custom CSV feeds.
- **Key options**
  - Source toggles: `--worldairports`, `--france-eaip`, `--uk-eaip`, `--france-web`, `--uk-web`, `--autorouter`, `--pointdepassage`
  - Outputs: `--database-storage` (writes a new SQLite database with change tracking), `--json` (full model dump)
  - Cache control: `--cache-dir`, `--force-refresh`, `--never-refresh`
  - Airport filter: supply ICAO codes as positional arguments
- **Example**

```bash
source dev.env
python aipexport.py --france-web --uk-web --autorouter --database-storage ../data/airports.db
```

- **Notes**
  - Web sources require an AIRAC date; if omitted the script uses the current effective cycle.
  - Autorouter credentials can be passed with `--autorouter-username`/`--autorouter-password` or stored securely in the environment.

## `aip.py`

- **Use when** you need to interact with a single source, download raw material, or run interpreters against an existing database.
- **Commands**
  - `autorouter`: fetch procedures/AIP PDFs via the Autorouter API (`-u/--username`, `-p/--password`)
  - `france_eaip` / `uk_eaip`: parse local eAIP directories (`-r/--root-dir`)
  - `worldairports`: download OurAirports data into a lightweight SQLite (`-d/--database`)
  - `pointdepassage`: parse official customs PDF into the database (`-j/--journal-path`)
  - `querydb`: run ad-hoc SQL filters against `airports.db` (`--where`)
  - `analyze`: execute interpreter analyses and export results (`--interpreters`, `--format`, `--output`)
- **Example**

```bash
source dev.env
python aip.py france_eaip -r /Volumes/AIP/FRANCE -c cache/france --force-refresh
```

- **Tips**
  - Combine with `--verbose` for detailed parsing logs.
  - The `analyze` command requires interpreters from `euro_aip.interp`; pass comma-separated names like `custom,maintenance`.

## `aipchange.py`

- **Use when** you need to diff two AIRAC cycles or compare different sources for the same airport set.
- **Workflow**
  1. Specify both sources via `--source1` / `--source2` and provide their required arguments (`--root-dirX`, `--usernameX`, etc.).
  2. Optionally filter fields with `-f/--fields` or target specific ICAO codes.
  3. Inspect console output or save structured reports.
- **Example**

```bash
source dev.env
python aipchange.py --source1 france_eaip --root-dir1 /data/eaip_2025-04 --source2 france_eaip --root-dir2 /data/eaip_2025-06 --csv-output france_changes.csv
```

- **Outputs**
  - Console summary of changed fields per airport
  - JSON report (`-o`) and/or flattened CSV (`--csv-output`)

## `bordercrossingexport.py`

- **Use when** you want a dataset focused on customs/border crossing requirements.
- **Inputs**
  - Either start from an existing database (`--database`) or build from World Airports (`--worldairports` + optional `--worldairports-db`)
  - Add supplemental HTML/PDF sources as positional arguments or let the tool use defaults.
- **Outputs**
  - `--database-storage`: new SQLite with border crossing annotations
  - `--json`: serialized model for downstream services (e.g., MCP rules)
- **Example**

```bash
source dev.env
python bordercrossingexport.py --database ../data/airports.db --json border_crossing.json
```

- **Notes**
  - Use `--save-all-fields` if you need every raw AIP field preserved in the output database.
  - Combine with `--force-refresh` to bypass cached downloads.

## `foreflight.py`

- **Use when** you want ForeFlight content packs, KML overlays, or custom waypoint bundles.
- **Commands**
  - `airports` (default): generate “Point of Entry” + “Approaches” KML files from `airports.db`
  - `approach`: build a pack from an Excel workbook containing `navdata` and `byop` sheets (`--xlsx`)
- **Example (database-driven)**

```bash
source dev.env
python foreflight.py PointOfEntry -c airports -d $AIRPORTS_DB -n --procedure-distance 12
```

- **Example (custom approach)**

```bash
source dev.env
python foreflight.py CustomApproach -c approach -x ./approach_definition.xlsx -n --describe "LFPO,RWY09"
```

- **Dependencies**
  - `pandas` and `openpyxl` for Excel processing
  - `simplekml` for KML generation (already listed in `requirements.txt`)
- **Outputs**
  - Content pack directory containing `manifest.json`, `navdata/*.kml`, and optional updated Excel (`*_updated.xlsx`)

## `starlink.py`

- **Use when** you want to see in the cockpit where Starlink stops working. Starlink's land/Roam
  service reaches territorial waters only out to 12 NM from the coast; this draws that limit as a
  ForeFlight map layer.
- **Example (the default covers UK + France + Spain + Balearics)**

```bash
source dev.env
python starlink.py Starlink12NM -r western-europe -n
```

- **Key options**
  - `-r/--region`: `western-europe` (default), `uk-ireland`, `mediterranean`, `atlantic-islands`,
    `scandinavia`, `europe`. Or `--bbox=W,S,E,N` for anything else — use the `=`, since a
    bbox starting with a negative longitude is otherwise parsed as an option name.
  - `--distance-nm`: the rule itself, default 12. Change it and the layer follows.
  - `--source`: coastline dataset, default `gshhg-h` (~200 m). Also `gshhg-i`, `ne10m`, `osm`.
  - `--no-fill`: emit only the limit line, skipping the shaded beyond-limit layer.
  - `--kmz FILE`: also write a single-file KMZ with both layers as folders, for checking the
    result in Google Earth before loading it on the iPad. The content pack `.zip` is *not* a KMZ
    (a KMZ needs `doc.kml` at the archive root), so use this rather than renaming the pack.
  - `--out-dir DIR`: build the pack somewhere other than the current directory, e.g. `out/`.
- **Outputs**
  - `layers/<Name>Limit.kml` — the offshore limit, as one placemark holding a MultiGeometry of
    LineStrings. Islands and enclosed water (mid Irish Sea) come out as their own closed rings.
  - `layers/<Name>Beyond.kml` — translucent wash over the water past the limit. Separate file so
    ForeFlight lists it as an independent toggle.
- **Notes**
  - Every run measures its own output: it resamples the emitted limit and reports the geodesic
    distance back to land. Expect a median near 12.0 NM and ~100% of samples within 0.5 NM. This
    checks the buffer maths, *not* the fidelity of the source coastline.
  - The limit is buffered from the *physical* shoreline, so it is conservative. Legal territorial
    seas use straight baselines that close bays, which sit further out in places like Norway and
    the French Biscay coast.
  - **Resolution is a memory decision, not a quality preference.** Detail below a few hundred
    metres cannot survive a 22 km buffer, and peak memory in GEOS scales with the number of
    polygon parts fed to one buffer call. Full-resolution OSM coastline is 5.3M vertices for the
    British Isles alone; buffering an archipelago in one call has been measured at 30 GB. Hence
    the defaults simplify on read and buffer in small batches, and `--max-vertices` /
    `--memory-limit-mb` exist to abort rather than let the machine swap.
- **Dependencies**
  - `shapely`, `pyproj`, `pyshp`, `simplekml`

---

All tools honor the `LOG_LEVEL` environment variable and write cache artifacts under `cache/` by default. Review each script’s `--help` output for full argument listings. 