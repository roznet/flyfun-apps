# Euro AIP Airport Explorer (Web)

FastAPI + TypeScript application for browsing the FlyFun Euro AIP dataset. It exposes REST endpoints for airports, procedures, statistics, and an LLM helper API, and ships with a modern TypeScript/Zustand/Leaflet frontend that visualizes the data on an interactive map.

## Architecture

The frontend uses a modern reactive architecture:
- **TypeScript** for type safety
- **Zustand** for state management (single source of truth)
- **Leaflet** for map visualization
- **Vite** for build tooling and development
- **Fetch API** for HTTP requests

See `designs/UI_FILTER_STATE_DESIGN.md` for detailed architecture documentation.

## Features

- Interactive map with procedure/border-crossing overlays and responsive layouts.
- Rich filtering across country, procedure type, approach type, runway characteristics, and standardized AIP fields.
- Detailed airport panels with procedures, runways, AIP entries, and provenance information.
- Statistics dashboard summarizing airport coverage, procedures, and data quality metrics.
- Aviation agent chat endpoint (`/api/aviation-agent/chat/stream`) with LangGraph-based streaming responses.
- Hardened backend configuration: rate limiting, security headers, CORS/trusted hosts, and optional HTTPS enforcement.

## Project Structure

```
web/
├── client/                 # Frontend application
│   ├── ts/                 # TypeScript source code
│   │   ├── store/          # Zustand state management
│   │   ├── adapters/       # API and LLM adapters
│   │   ├── engines/        # Visualization and filter engines
│   │   ├── managers/      # UI manager for DOM updates
│   │   └── main.ts         # Application entry point
│   ├── js/                 # Legacy JavaScript (to be removed)
│   ├── dist/               # Built output (generated)
│   ├── index.html          # Main HTML file
│   ├── package.json        # Node.js dependencies
│   ├── tsconfig.json       # TypeScript configuration
│   └── vite.config.ts      # Vite build configuration
├── server/
│   ├── api/                # FastAPI routers (airports, procedures, filters, statistics, aviation_agent_chat)
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
  - `RULES_JSON`: required rules metadata so the chat endpoint mirrors MCP behavior
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

### Install Backend Dependencies

```bash
cd web
pip install -r requirements.txt
```

### Install Frontend Dependencies

```bash
cd web/client
npm install
```

This installs TypeScript, Zustand, Vite, Leaflet, and other frontend dependencies.

### Start the Backend

In one terminal:

```bash
cd web
./start_server.ksh $(which python3) server/dev.env
```

Or manually:

```bash
cd web
source server/dev.env
uvicorn server.main:app --reload
```

The backend runs on `http://127.0.0.1:8000` by default.

### Start the Frontend (Development)

In a second terminal:

```bash
cd web/client
npm run dev
```

This starts the Vite dev server with hot-reload on `http://localhost:3000` (or next available port). The dev server proxies API requests to the backend.

### Access the UI

- **Development**: Browse to `http://localhost:3000` (Vite dev server)
- **Production**: Build first (`npm run build`), then serve `client/dist/` or browse to `http://127.0.0.1:8000` (FastAPI serves built files)

### Build for Production

```bash
cd web/client
npm run build
```

This creates optimized production bundles in `client/dist/`. Update `index.html` to use the built files instead of the dev server.

### Type Checking

```bash
cd web/client
npm run type-check
```

This runs TypeScript compiler to check for type errors without emitting files.

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

### Aviation Agent (`/api/aviation-agent/chat/stream`)

- Streaming chat endpoint powered by LangGraph-based aviation agent.
- Provides structured planning, tool execution, and formatted responses with map visualizations.
- Returns Server-Sent Events (SSE) for progressive response streaming.
- Enabled via `AVIATION_AGENT_ENABLED=true` environment variable.

All endpoints inherit the rate limiting, security headers, and host/CORS constraints defined in `security_config.py`.

## Frontend Usage

### Basic Features

- **Search**: Type ICAO, IATA, airport name, or city in the search box. Supports:
  - Airport name/ICAO search
  - Route search (e.g., "EGTF LFPG" finds airports near route)
  - Location search (e.g., "Paris" finds airports near location)
- **Filters**: Toggle checkboxes and select dropdowns to filter airports:
  - Country selection
  - Has procedures
  - Has AIP data
  - Has hard runway
  - Border crossing only
  - Max airports limit
- **Map**: Interactive Leaflet map showing airports as markers:
  - Click markers to view airport details
  - Pan and zoom to explore
  - Legend modes change marker colors/styles
- **Legend Modes**: Switch between visualization modes:
  - Airport Type (default): Colors by border crossing/procedures
  - Procedure Precision: Colors by procedure type
  - Runway Length: Colors by runway length
  - Country: Colors by country
- **Airport Details**: Click an airport marker to view:
  - Basic information
  - Runways
  - Procedures
  - AIP entries
  - Country rules

### State Management

The frontend uses Zustand for reactive state management:
- All state lives in a centralized store
- UI and map automatically update when state changes
- State persists in URL parameters (shareable links)
- Chatbot visualizations automatically sync with state

See `designs/UI_FILTER_STATE_DESIGN.md` for architecture details.

## Customization & Extension

### Frontend Development

The frontend is built with TypeScript and follows a reactive architecture:

- **Add Filters**: See `designs/UI_FILTER_STATE_DESIGN.md` for step-by-step guide
- **Add LLM Visualizations**: Add new visualization types in `ts/adapters/llm-integration.ts`
- **Add Map Features**: Extend `ts/engines/visualization-engine.ts`
- **Add UI Components**: Update `ts/managers/ui-manager.ts`

### Backend Development

- **Security**: Harden `security_config.py` for production (API keys, HTTPS enforcement, origin restrictions, stricter limits).
- **Data**: Swap databases or rules by changing `AIRPORTS_DB` / `RULES_JSON`; the FastAPI startup reloads resources automatically.
- **New endpoints**: Add routers under `server/api/`, register them in `main.py`, and add corresponding methods to `ts/adapters/api-adapter.ts`.

### Architecture Documentation

For detailed information on:
- How the state management works
- How to add new filters
- How to add new LLM visualizations
- How to add new features
- How to extend the system

See `designs/UI_FILTER_STATE_DESIGN.md`.

## Testing

### Frontend Testing

1. **Type Check**: `cd web/client && npm run type-check`
2. **Build**: `cd web/client && npm run build`
3. **Dev Server**: `cd web/client && npm run dev`
4. **Browser Testing**:
   - Open browser console and check for errors
   - Test all filters
   - Test search functionality
   - Test map interactions
   - Test chatbot integration (if enabled)

### Backend Testing

- Test API endpoints directly: `curl http://localhost:8000/api/airports?country=FR`
- Check FastAPI docs: `http://localhost:8000/docs`

## Troubleshooting

### Frontend Issues

- **TypeScript errors**: Run `npm run type-check` to see all errors
- **Build fails**: Check `package.json` dependencies are installed
- **Map not showing**: Check browser console for Leaflet errors, verify Leaflet CDN is loading
- **State not updating**: Check browser console for Zustand errors, verify store subscriptions
- **Infinite loops**: Check for circular state updates (see `designs/UI_FILTER_STATE_DESIGN.md`)

### Backend Issues

- **Server fails to start**: confirm `dev.env` points to real `airports.db` / `rules.json` files (`sqlite3 your.db '.tables'`), security config imports without errors, and dependencies are installed.
- **CORS/host errors**: broaden `ALLOWED_ORIGINS`/`ALLOWED_HOSTS` while developing, then lock them down for production.
- **Blank map or empty tables**: inspect browser console, ensure the API requests return 200, and verify rate limiting is not blocking requests.
- **429 responses**: increase `RATE_LIMIT_MAX_REQUESTS` during testing or run behind a reverse proxy with IP forwarding configured.

### Common Issues

- **"Leaflet not loaded"**: Ensure Leaflet CDN script is included in `index.html` before the app script
- **"Map container not found"**: Ensure HTML has `<div id="map"></div>`
- **API errors**: Check backend is running and accessible at configured port
- **Hot reload not working**: Restart Vite dev server

## Development Workflow

### Typical Development Session

1. **Start Backend**:
   ```bash
   cd web
   source server/dev.env
   uvicorn server.main:app --reload
   ```

2. **Start Frontend** (in separate terminal):
   ```bash
   cd web/client
   npm run dev
   ```

3. **Make Changes**:
   - Edit TypeScript files in `web/client/ts/`
   - Vite automatically rebuilds and hot-reloads
   - Changes appear in browser immediately

4. **Type Check** (before committing):
   ```bash
   cd web/client
   npm run type-check
   ```

5. **Build for Production**:
   ```bash
   cd web/client
   npm run build
   ```

## Deployment Notes

### Frontend Deployment

1. **Build production bundle**:
   ```bash
   cd web/client
   npm run build
   ```

2. **Update HTML** (if using built files):
   - Ensure `index.html` references `dist/main.iife.js`
   - Or configure FastAPI to serve `client/dist/` directory

3. **Serve static files**:
   - FastAPI can serve `client/dist/` directly
   - Or use nginx/other web server for static files

### Backend Deployment

- Run behind a reverse proxy (nginx, Traefik) that terminates TLS and forwards headers; enable `FORCE_HTTPS` in production.
- Persist `dev.env`/`security_config.py` as environment-specific copies (do **not** commit real secrets or production paths).
- Monitor logs (`LOG_LEVEL`, `LOG_FORMAT`) and consider externalizing settings via environment variables instead of editing the config file directly.

## License & Support

This web application is part of the FlyFun Euro AIP tooling released under the repository’s MIT license. For questions, open an issue in the main project or contact flyfun.aero.

Happy exploring! 🛩️