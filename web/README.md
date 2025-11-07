# Euro AIP Airport Explorer (Web)

FastAPI + vanilla JavaScript application for browsing the FlyFun Euro AIP dataset. It exposes REST endpoints for airports, procedures, statistics, and an LLM helper API, and ships with a Leaflet/Bootstrap frontend that visualizes the data on an interactive map.

## Features

- Interactive map with procedure/border-crossing overlays and responsive layouts.
- Rich filtering across country, procedure type, approach type, runway characteristics, and standardized AIP fields.
- Detailed airport panels with procedures, runways, AIP entries, and provenance information.
- Statistics dashboard summarizing airport coverage, procedures, and data quality metrics.
- Optional chat endpoint (`/chat/ask`) that powers the MCP integration.
- Hardened backend configuration: rate limiting, security headers, CORS/trusted hosts, and optional HTTPS enforcement.

## Project Structure

```
web/
├── client/                 # Static assets (index.html, JS modules, inline styles)
├── server/
│   ├── api/                # FastAPI routers (airports, procedures, filters, statistics)
│   ├── chat/ask.py         # Chat-style helper endpoint backed by the Euro AIP model
│   ├── security_config.py  # Runtime security policy (copy from .sample)
│   ├── dev.env             # Environment variables (copy from .sample)
│   └── main.py             # FastAPI entry point
├── start_server.ksh        # Convenience launcher (loads env, runs FastAPI)
└── README.md               # This file
```

## Environment Configuration

1. Copy the provided samples:

```bash
cd web/server
cp dev.env.sample dev.env
cp security_config.py.sample security_config.py
```

2. Edit both files and provide absolute paths/secrets appropriate for your machine or deployment:

- `dev.env`
  - `AIRPORTS_DB`: absolute path to the SQLite database (e.g., `/Users/you/flyfun/data/airports.db`)
  - `RULES_JSON`: optional rules metadata consumed by `/chat/ask`
  - `ENVIRONMENT`, `LOG_LEVEL`: runtime tuning
- `security_config.py`
  - Update `ALLOWED_ORIGINS`/`ALLOWED_HOSTS` for your dev/prod domains
  - Adjust `ALLOWED_DIR` if you restrict file access
  - Review rate limits, distance bounds, API key requirement, and session configuration before production

3. Load the environment in any shell session before starting the server:

```bash
source web/server/dev.env
```

> Keep per-environment files (e.g., `prod.env`) alongside the samples and ensure they stay out of version control.

## Running Locally

### Install Dependencies

```bash
cd web
pip install -r requirements.txt
```

### Start the Backend

```bash
cd web
./start_server.ksh $(which python3) server/dev.env
```

`start_server.ksh` sources your env file and runs `server/main.py` with the interpreter you provide. You can also run `uvicorn server.main:app --reload` if preferred.

### Access the UI

Browse to `http://127.0.0.1:8000/` and the static frontend will load from the same FastAPI app. The root serves `client/index.html`, using the REST endpoints described below.

## API Overview

### Airports (`/api/airports`)

- `GET /` — list airports with query parameters for country, runway surface, procedures, border crossings, standardized fields, pagination, etc.
- `GET /{icao}` — airport detail including core metadata, runways, and procedures.
- `GET /{icao}/aip-entries` — raw and standardized AIP entries for the airport.
- `GET /{icao}/procedures`, `/runways`, `/search/{query}` — specialized lookups and search.

### Procedures (`/api/procedures`)

- Filterable list endpoints (`/`, `/approaches`, `/departures`, `/arrivals`).
- Runway-specific views (`/by-runway/{icao}`) and precision ranking (`/most-precise/{icao}`).

### Filters (`/api/filters`)

- Discover available countries, procedure types, approach types, AIP sections/fields, and fetch them all in one payload (`/all`).

### Statistics (`/api/statistics`)

- Overview counts, per-country breakdowns, procedure distribution, runway stats, and data-quality metrics.

### Chat (`/chat/ask`)

- Lightweight question/answer endpoint that leverages the shared `EuroAipModel` to assist LLM integrations (mirrors the MCP tool behavior).

All endpoints inherit the rate limiting, security headers, and host/CORS constraints defined in `security_config.py`.

## Frontend Usage

- **Search**: Type ICAO, IATA, airport name, or city; the result list collapses on selection.
- **Filters**: Toggle booleans (procedures, point of entry, etc.), select countries, procedure types, or approach types; the map and statistics update instantly.
- **Map**: Circle markers highlight airports; colors distinguish procedure coverage and border crossings. Clicking a marker syncs the details panel.
- **Charts**: Live charts update with the current filter set, powered by the statistics endpoints.
- **Keyboard shortcuts**: `Cmd/Ctrl + F` focuses search; `Esc` resets.

## Customization & Extension

- **Security**: Harden `security_config.py` for production (API keys, HTTPS enforcement, origin restrictions, stricter limits).
- **Data**: Swap databases by changing `AIRPORTS_DB` without modifying code; the FastAPI startup reloads the `EuroAipModel` automatically.
- **Frontend**: Extend `client/js/` modules or inject additional bundles; static files are served by `StaticFiles` from `client/`.
- **New endpoints**: Add routers under `server/api/`, register them in `main.py`, and surface the data in the frontend as needed.

## Troubleshooting

- **Server fails to start**: confirm `dev.env` points to a real database (`sqlite3 your.db '.tables'`), security config imports without errors, and dependencies are installed.
- **CORS/host errors**: broaden `ALLOWED_ORIGINS`/`ALLOWED_HOSTS` while developing, then lock them down for production.
- **Blank map or empty tables**: inspect browser console, ensure the API requests return 200, and verify rate limiting is not blocking requests.
- **429 responses**: increase `RATE_LIMIT_MAX_REQUESTS` during testing or run behind a reverse proxy with IP forwarding configured.

## Deployment Notes

- Run behind a reverse proxy (nginx, Traefik) that terminates TLS and forwards headers; enable `FORCE_HTTPS` in production.
- Persist `dev.env`/`security_config.py` as environment-specific copies (do **not** commit real secrets or production paths).
- Monitor logs (`LOG_LEVEL`, `LOG_FORMAT`) and consider externalizing settings via environment variables instead of editing the config file directly.

## License & Support

This web application is part of the FlyFun Euro AIP tooling released under the repository’s MIT license. For questions, open an issue in the main project or contact flyfun.aero.

Happy exploring! 🛩️