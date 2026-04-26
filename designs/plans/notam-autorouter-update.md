# NOTAM Autorouter Update — Plan

> Replace FlyFunBrief's PDF-only NOTAM import with a live Autorouter API path, migrate
> Autorouter auth from username/password to OAuth account-linking, and replace the
> ICAO-prefix FIR mapping with VATSpy polygons.

## Goal

The FlyFunBrief iOS app currently imports briefings only via ForeFlight PDF. We want a
live path through the Autorouter NOTAM API, served by the existing flyfun-apps backend,
authenticated per-user via `flyfun-common`'s OAuth account-linking flow. The PDF path
stays as a supplement for users who don't link Autorouter.

## Current state (already in place)

- **`web/server/api/briefing.py`** already exposes `GET /api/briefing/notams` —
  resolves a route to dep/dest/alts/waypoints + corridor airports, calls
  `AutorouterNotamSource`, returns a `BriefingResponse` matching the existing
  Swift `Notam` decode path.
- **`AutorouterNotamSource`** (in `euro_aip/briefing/sources/autorouter_notam.py`) —
  handles pagination (100/page), batches ICAOs (20/request), reassembles
  `code23+code45` → `Q{...}` Q-code, converts FL → feet, maps unix epoch → datetime.
  Deduplicates by NOTAM id.
- **`AutorouterCredentialManager.set_token(access_token, expires_at)`** already exists
  in `euro_aip/utils/autorouter_credentials.py:55` — designed for exactly this
  pre-obtained-token use case. No euro_aip change required to consume an OAuth token.
- **`flyfun_common.autorouter`** provides `create_autorouter_router()` (link / unlink /
  status / callback) and `get_autorouter_token(db, user_id)` returning the encrypted
  bearer token.
- **flyfun-apps web server** already mounts `flyfun_common.auth.create_auth_router()`
  (`web/server/main.py:352`) and uses `current_user_id` for protected endpoints.
- **Cross-subdomain SSO** — Apple Sign In is wired to flyfun-forms (because
  `net.ro-z.FlyFunBrief` is in its `APPLE_APP_IDS`); the resulting JWT works against
  flyfun-apps via the shared cookie/Bearer mechanism.
- **iOS app** — `app/FlyFunBrief/App/Services/BriefingService.swift` and
  `BriefingDomain.swift` exist and handle the PDF path; the Notam JSON decode path is
  already there.

## What needs to change

1. Server uses **OAuth bearer tokens** instead of stored username/password (Autorouter
   has explicitly asked us to stop using password-based auth).
2. Server resolves FIRs via **VATSpy polygons** instead of the ICAO-prefix
   `configs/fir_mapping.json` lookup.
3. iOS app gets a **live-fetch path** that calls `/api/briefing/notams` and surfaces
   "Connect Autorouter" when the user hasn't linked.

`airports_fir` table dropped from scope: with polygons, dep/dest/alts go to Autorouter
as ICAOs directly, en-route FIRs come from polygon intersection of the buffered route,
and the Autorouter response carries per-NOTAM `fir` for free.

## Decisions locked in

1. **Two independent OAuth flows on different hosts:**
   - User identity OAuth (Apple/Google → `flyfun_auth` JWT) **stays on flyfun-forms**
     — that's where `net.ro-z.FlyFunBrief` is in `APPLE_APP_IDS`. Unchanged.
   - Autorouter service-linking OAuth (user grants us permission to call Autorouter on
     their behalf → bearer token in `UserPreferencesRow`) **stays on flyfun-weather**.
     flyfun-weather already mounts `create_autorouter_router()` (for GRAMET) and has
     the redirect URI registered with Autorouter. The shared `flyfun_common` DB means
     flyfun-apps can read the token via `get_autorouter_token` without re-mounting the
     router locally — and any user already linked for GRAMET is automatically linked
     for briefing.

2. **iOS link-flow UX:** `ASWebAuthenticationSession` opens
   `https://weather.flyfun.aero/autorouter/link`. The flow runs server-to-server
   through autorouter.aero and lands on
   `https://weather.flyfun.aero/auth/callback/autorouter`, which returns the small
   success HTML page that `flyfun_common.autorouter` already provides. The 409
   response from `/api/briefing/notams` carries the absolute `link_url`; iOS opens
   it directly. The link host is configurable via `AUTOROUTER_LINK_URL` env var
   (default: `https://weather.flyfun.aero/autorouter/link`) for dev environments.

3. **Legacy username/password blobs:** ignore in code, do not read. Leave existing
   entries in `UserPreferencesRow.encrypted_creds_json` dormant (other services may
   share the blob). No migration / wipe.

4. **Garmin-format coordinate behaviour in `AutorouterNotamSource`:** unverified —
   API doc says integer semicircles, current impl reads them as if they were decimal
   degrees (`autorouter_notam.py:173-175`). **Verification step is part of Phase 1**
   below: log raw `lat`/`lon` from the first real response, confirm whether
   conversion is missing, fix in `_row_to_notam` if so. Must be resolved before
   Phase 4 ships.

5. **VATSpy refresh cadence:** manual drop-in. Boundaries change rarely; matching the
   AIP cycle drop process is fine. No auto-fetch in `data_update.py`.

## Phase 1 — Migrate Autorouter auth to OAuth (BLOCKING)

> Per agreement with Autorouter, username/password must stop. Phase 1 needs to land
> before any new iOS user is onboarded against the briefing endpoint.

### 1.1 Autorouter OAuth router host (no code change on flyfun-apps)

flyfun-weather already mounts `create_autorouter_router()`
(`weatherbrief/api/app.py:291`) and the redirect URI
`weather.flyfun.aero/auth/callback/autorouter` is registered with Autorouter. Reused
as-is — no additional mount on flyfun-apps. The briefing endpoint reads the token
from the shared DB.

A short comment in `web/server/main.py` (where the mount would otherwise go)
documents this so a future reader doesn't try to add it.

### 1.2 Refactor `_get_notam_source_for_user`

- File: `web/server/api/briefing.py:73-103`.
- Replace the `load_encrypted_creds` + `set_credentials(username, password)` path with:
  ```python
  from flyfun_common.autorouter import get_autorouter_token

  token = get_autorouter_token(db, user_id)
  if token is None:
      raise HTTPException(
          status_code=409,
          detail={
              "error": "autorouter_not_linked",
              "message": "Connect your Autorouter account to fetch NOTAMs.",
              "link_url": "/autorouter/link",
          },
      )

  cache_dir = os.environ.get("CACHE_DIR", "/tmp/flyfun-cache")
  user_cache_dir = os.path.join(cache_dir, "autorouter", user_id)
  cred_mgr = AutorouterCredentialManager(user_cache_dir)
  cred_mgr.set_token(token)  # already exists in euro_aip
  return AutorouterNotamSource(cred_mgr)
  ```
- Remove the references to `load_encrypted_creds`, `username`, `password`, and the
  "WeatherBrief preferences UI" error text.
- Status code change rationale: `409 Conflict` with structured detail lets the iOS
  client distinguish "not linked yet" from "auth failed" (`401`) and "server broken"
  (`5xx`).

### 1.3 Confirm `set_token` semantics

- `AutorouterCredentialManager.set_token` (lines 55-68) sets the cached creds dict
  but doesn't persist via `_save_credentials`. That's fine for our use case (we
  re-create the manager per request from the DB-stored token). Just don't call
  `get_credentials()` first, since that would trigger `_refresh_credentials` →
  `_get_credentials_from_user` → an interactive prompt we don't want.
- Verify `get_token()` returns the set token without triggering refresh when called
  immediately after `set_token`. (It calls `get_credentials()` which checks expiry —
  ours has a 1-year horizon so it should pass.)

### 1.4 Acceptance

- Linked user: `GET /api/briefing/notams?...` returns NOTAMs.
- Unlinked user: returns `409` with `{ "error": "autorouter_not_linked", ... }`.
- Expired/revoked token: Autorouter returns 401 → adjust the exception handler in
  `fetch_route_notams` to map 401 from Autorouter back to the same 409 + structured
  payload, so iOS prompts re-link rather than treating it as a server outage.

### 1.5 Verify Garmin-coord handling on first real response

Open question 4 from the decisions list. With a freshly linked test user:
- Issue one real `/api/briefing/notams` request that returns NOTAMs with non-null
  `lat`/`lon`.
- Log raw values before `_row_to_notam` conversion.
- Compare to the known location: if values look like `~480000000` for ~40°N, the API
  is returning Garmin semicircles and `autorouter_notam.py:173-175` needs
  `lat * 180 / 2**31` (and same for lon). If values look like `48.7` directly, the
  doc is wrong and the impl is right — no change.
- Land the fix (or a comment confirming it's correct) in the same PR as Phase 1, so
  Phase 4 can trust `coordinates` for distance/route filtering on iOS.

## Phase 2 — VATSpy FIR ingest

### 2.1 Add `firs` table to nav.db

Schema (in `euro_aip/storage/database_storage.py` migrations):
```sql
CREATE TABLE firs (
    icao TEXT NOT NULL PRIMARY KEY,
    name TEXT,
    polygon_geojson TEXT NOT NULL,   -- raw GeoJSON Polygon/MultiPolygon coordinates
    bbox_min_lat REAL NOT NULL,
    bbox_max_lat REAL NOT NULL,
    bbox_min_lon REAL NOT NULL,
    bbox_max_lon REAL NOT NULL,
    is_oceanic INTEGER DEFAULT 0,
    source TEXT,                     -- "vatspy"
    updated_at TEXT
);
CREATE INDEX idx_firs_bbox ON firs(bbox_min_lat, bbox_max_lat, bbox_min_lon, bbox_max_lon);
```

Bbox columns let us prefilter candidate FIRs cheaply before running point-in-polygon.

### 2.2 Add `euro_aip/sources/vatspy_fir.py`

- Pattern: same as other euro_aip sources (cached, accepts local path or URL).
- Source URL: VATSpy Data Project release `Boundaries.geojson` on GitHub. License:
  attribution. Include a short LICENSE/source note in the source module docstring.
- Parse with stdlib `json` only — **no shapely or geopandas dep added.**
- Filter to FIRs only (skip TMA / sub-sectors that VATSpy bundles).
- Write to `firs` table via `DatabaseStorage`.

### 2.3 Add `euro_aip/models/fir.py` + `fir_collection.py`

- `FIR` dataclass: `icao`, `name`, `polygon_rings` (list of list of (lon, lat)),
  `bbox`, `is_oceanic`.
- `FIRCollection` extending `QueryableCollection` for fluent queries (`by_icao`,
  bbox prefilter, etc.).
- Hand-rolled point-in-polygon helper (ray casting, ~30 lines, in
  `euro_aip/utils/geometry.py` next to existing spatial utils). Handles MultiPolygon
  by OR-ing the rings.

### 2.4 Add `EuroAipModel.firs_along_route(route_navpoints, corridor_nm)`

Returns `set[str]` of FIR ICAOs the buffered route crosses. Implementation:
- Sample the route polyline at ~5 nm intervals (similar precision to existing
  `find_airports_near_route`).
- For each sample, prefilter candidate FIRs by bbox padded by `corridor_nm` (degrees
  conversion uses the existing latitude-aware helper).
- Run point-in-polygon on each candidate.
- Union of all hits.

### 2.5 Hook into the data update pipeline

- Add a step in `data_update.py` (or whatever orchestrates `nav.db` rebuild) to call
  `VatspyFirSource(...).update_model(model)` after airports/waypoints. Idempotent.

## Phase 3 — Switch the API endpoint to polygon-based FIR resolution

- File: `web/server/api/briefing.py`, function `_resolve_route_icaos:106-159`.
- Replace the `_get_fir_mapping()` + ICAO-prefix lookup with:
  ```python
  firs = model.firs_along_route(route_navpoints, corridor_nm=corridor_nm)
  ```
  where `route_navpoints` is the resolved list of NavPoints (dep, waypoints, dest)
  already built earlier in the same function.
- Keep the airport corridor logic (`find_airports_near_route`) unchanged.
- Remove the `_get_fir_mapping`, `_fir_mapping`, and the import of `Path` for that
  config.
- Delete `configs/fir_mapping.json` once the new path is verified end-to-end.

### Verification before deleting fir_mapping.json

For ~5 representative routes (e.g., EGTF→LSGS, LFPG→EDDF, EGLL→LFPG via airways,
LGAV→LMML over sea, KJFK→KLAX for non-EU sanity check), compare the FIR list produced
by both methods. The polygon path should be a strict superset where the prefix lookup
was incomplete (e.g., split FIRs) and identical otherwise.

## Phase 4 — iOS app wiring

> Phase 4 work is in `app/FlyFunBrief/`. RZFlight Notam model already decodes the
> server response; the work is in `BriefingService` and the user-facing flow.

### 4.1 BriefingService — add `fetchAutorouterBriefing`

- File: `app/FlyFunBrief/App/Services/BriefingService.swift`
- New `actor` method:
  ```swift
  func fetchAutorouterBriefing(
      departure: String,
      destination: String,
      waypoints: [String],
      departureTime: Date?,
      arrivalTime: Date?,
      corridorNm: Double = 25.0
  ) async throws -> Briefing
  ```
- GETs `https://apps.flyfun.aero/api/briefing/notams?...` with `Authorization: Bearer <jwt>`.
- Decodes the existing `BriefingResponse` JSON shape into `RZFlight.Briefing`.
- Maps `409 { error: "autorouter_not_linked" }` to a typed
  `BriefingServiceError.autorouterNotLinked(linkURL:)`.

### 4.2 BriefingDomain — second import path

- File: `app/FlyFunBrief/App/State/Domains/BriefingDomain.swift`
- Add `importBriefingFromAutorouter(flight: CDFlight)` alongside the existing
  PDF-import path. Reuses `onBriefingParsed` callback, same downstream identity-key
  status-transfer logic.
- The two paths produce the same `Briefing` model — no NotamDomain changes needed.

### 4.3 UI: connect-autorouter affordance

- New section in Settings (`UserInterface/Views/Settings/`): "Autorouter Account"
  with status (`linked` / `not linked`) and Connect / Disconnect buttons.
- Connect: open `apps.flyfun.aero/autorouter/link` in `ASWebAuthenticationSession`
  with callback URL scheme `flyfun://autorouter/callback` (or a query-param flag
  on the redirect target). Server callback page just needs to return a "you can
  close this window" page that the session detects.
- Disconnect: `POST /autorouter/unlink`.
- Status check: `GET /autorouter/status` on app launch / settings open.
- In flight-detail / NOTAM list: when the user taps "Fetch live NOTAMs" and the
  service throws `.autorouterNotLinked`, show a sheet that links to the Settings
  flow.

### 4.4 PDF path stays

- Keep ForeFlight PDF import for users who don't link Autorouter.
- Both paths feed the same domain; the only UI difference is the entry point.

## Phase ordering

Phase 1 must land first (Autorouter agreement). Phase 2 and 3 can land together
(polygon ingest + endpoint switch); they're independent of phase 1 but cleaner to do
after so the only divergence on the endpoint is one concern at a time. Phase 4 lands
last and depends on phases 1–3 being deployed.

## Risks

- **Garmin-coord bug** (open question 5) — could affect any NOTAMs that arrived from
  Autorouter into existing Notam-shaped storage. Verify with a real response before
  trusting `coordinates` for distance/route filtering on the iOS side.
- **VATSpy boundary changes vs Autorouter ICAO list** — VATSpy is community-maintained;
  occasional drift between its FIR ICAOs and Autorouter's accepted `itemas` values.
  Mitigation: log on Autorouter 4xx-per-ICAO when it occurs, surface via warning,
  don't fail the whole request.
- **OAuth token expiry mid-session** — 401 from Autorouter mid-fetch should bubble
  back as `409 autorouter_not_linked` (not 502), so iOS prompts re-link. Need a
  small adjustment in the exception-handling block of `fetch_route_notams`.
- **Cross-subdomain Bearer token** — verify the iOS app actually has the
  `flyfun_auth` JWT after Apple Sign In through forms.flyfun.aero, and that it sends
  it on requests to apps.flyfun.aero. (It should — same JWT secret, same `ff_`/JWT
  semantics — but worth confirming once with a manual curl.)
