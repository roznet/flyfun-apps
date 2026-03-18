# Auth & Usage Tracking

> Google OAuth SSO via flyfun-common, chatbot gating, per-user rate limiting, and cost tracking.

## Intent

All map/airport/filter/rules features are **public**. Only the chatbot (LLM agent) requires authentication. This gates the expensive LLM calls behind login, enables per-user rate limiting, and feeds usage data into the shared flyfun cost ledger for cross-service visibility.

## Quick Reference

| File | Purpose |
|------|---------|
| `web/server/main.py` | Auth router mount, `/auth/me` override, shared DB init |
| `web/server/api/aviation_agent_chat.py` | `current_user_id` dependency on chat endpoints |
| `web/server/api/chat_usage.py` | Rate limiting, usage logging, cost recording |
| `web/server/db/models.py` | `ChatUsageRow` (app-specific table) |
| `ts/store/types.ts` | `AuthState`, `AuthUser`, `ChatUsageInfo` |
| `ts/store/store.ts` | `auth` state slice, `setAuth()` action |
| `ts/main.ts` | `checkAuth()`, `renderAuthButton()` |
| `ts/managers/chatbot-manager.ts` | Auth overlay, 401/429 handling |

**External dependency:** `flyfun-common` library (auth, db, costs modules).

---

## Architecture

```
flyfun-common (shared)                 flyfun-apps (this project)
─────────────────────                  ──────────────────────────
UserRow, ApiTokenRow, CostLedgerRow    ChatUsageRow
create_auth_router()                   /auth/me override (adds chat_usage)
current_user_id dependency             chat endpoints: Depends(current_user_id)
record_cost()                          log_chat_usage() → record_cost()
init_shared_db(), ensure_dev_user()    Called in lifespan
```

### SSO Mechanism

Three things make cross-subdomain SSO work:
1. **Same cookie** (`flyfun_auth`) across all services
2. **Same JWT secret** — all apps decode each other's tokens
3. **Cookie domain** `.flyfun.aero` — browser sends cookie to all subdomains

A user logged in at `weather.flyfun.aero` is automatically authenticated at `maps.flyfun.aero`.

### Auth Priority (from flyfun-common)

1. Dev mode → `dev-user-001` (no validation)
2. `flyfun_auth` cookie → decode JWT
3. `Authorization: Bearer <token>` → JWT or API token (`ff_` prefix)
4. None → 401

---

## Backend

### Protected vs Public Endpoints

| Endpoint | Auth Required | Why |
|----------|--------------|-----|
| `/api/airports/*` | No | Public data |
| `/api/procedures/*` | No | Public data |
| `/api/filters/*` | No | Public data |
| `/api/rules/*` | No | Public data |
| `/api/ga/*` | No | Public data |
| `/api/notifications/*` | No | Public data |
| `/api/aviation-agent/chat` | **Yes** | LLM cost |
| `/api/aviation-agent/chat/stream` | **Yes** | LLM cost |
| `/api/aviation-agent/feedback` | **Yes** | User attribution |
| `/api/aviation-agent/quick-actions` | No | Static data |

### Rate Limiting

Per-user daily limit (20 messages/day, free tier):

```python
# chat_usage.py
DAILY_CHAT_LIMIT = 20

def check_chat_rate_limit(db, user_id):
    count = get_today_chat_count(db, user_id)
    if count >= DAILY_CHAT_LIMIT:
        raise HTTPException(429, "Daily chat limit reached")
```

Rate limit is checked **before** the streaming generator starts (avoids wasting LLM tokens on a request that will be rejected).

### Usage Logging

After each chat stream completes:
1. Token counts captured from the SSE `done` event
2. `ChatUsageRow` written (user_id, model, tokens, thread_id, persona_id)
3. `record_cost()` called on shared `CostLedgerRow` (service=`flyfun-maps`, action=`chat`)

### Security Headers

`security_config.py` controls CORS and CSP:
- CORS `allow_headers` restricted to `["Content-Type", "Authorization", "Accept"]` (not `["*"]`)
- CSP policy set via `Content-Security-Policy` header
- `/auth/logout` requires POST (matches flyfun-common router)

### Custom `/auth/me`

Registered **before** the common auth router to take priority. Returns app-specific `chat_usage`:

```json
{
  "id": "user-uuid",
  "email": "user@example.com",
  "name": "User Name",
  "approved": true,
  "chat_usage": { "used": 5, "limit": 20 }
}
```

---

## Frontend

### Auth State in Store

```typescript
interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;       // true until /auth/me resolves
  user: AuthUser | null;
  chatUsage: ChatUsageInfo | null;  // { used, limit }
}
```

### Auth Check Flow

```
App init → fetch /auth/me (credentials: include)
    ↓ 200                    ↓ 401/error
setAuth(user, chatUsage)     setAuth(null)
    ↓                            ↓
renderAuthButton()           renderAuthButton()
chatbot: show UI             chatbot: show sign-in overlay
```

### Chatbot Auth Gating

`ChatbotManager` subscribes to auth state:
- **Not authenticated**: Shows lock icon + "Sign in to use the Aviation Assistant" + Google button. Input/send disabled.
- **Authenticated**: Normal chat UI (event listeners, quick actions, welcome message attached once).
- **401 from stream**: Resets auth state, shows sign-in overlay.
- **429 from stream**: Shows rate limit error message.

### Header Auth Button

`#auth-button-container` in the header renders:
- **Signed out**: "Sign in with Google" link
- **Signed in**: User name + logout button

---

## Database

### Shared Tables (from flyfun-common)

- `users` — one row per person across all flyfun apps
- `api_tokens` — programmatic access tokens
- `cost_ledger` — cross-service cost tracking

### App-Specific Table

```sql
chat_usage (
    id           INTEGER PRIMARY KEY,
    user_id      VARCHAR(64) FK → users.id,
    timestamp    DATETIME,
    model        VARCHAR(100),
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd     FLOAT,
    thread_id    VARCHAR(64),
    persona_id   VARCHAR(64)
)
```

Created automatically by `init_shared_db()` in dev mode (because `ChatUsageRow` is registered on flyfun-common's `Base.metadata`). In production, requires migration.

---

## Deployment

### Required Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `JWT_SECRET` | Production | Must match across all flyfun services |
| `GOOGLE_CLIENT_ID` | Production | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Production | Google OAuth |
| `DATABASE_URL` | Production | Shared MySQL (same DB as flyfun-weather) |
| `ENVIRONMENT` | No | `development` (default) or `production` |

### Dev Mode

- Auth auto-bypassed: `current_user_id` returns `dev-user-001`
- SQLite at `data/flyfun.db` (auto-created)
- No Google credentials needed

---

## Key Choices

- **SessionMiddleware required**: OAuth state must survive the Google redirect roundtrip.
- **`ChatUsageRow` on shared `Base`**: Uses `ForeignKey("users.id")` and is created by the same `create_all()`. Follows flyfun-weather pattern.
- **Rate limit before streaming**: The `check_chat_rate_limit()` runs in a separate DB session before the generator starts, so 429 is returned immediately.
- **Usage logged in `finally` block**: Ensures logging even if streaming is interrupted.
- **`authInitialized` flag in ChatbotManager**: Prevents duplicate event listener attachment when auth state changes multiple times.

## References

- flyfun-common auth design: `~/Developer/public/flyfun-common` → `get_design_doc("flyfun-common", "auth")`
- flyfun-common DB design: `get_design_doc("flyfun-common", "db")`
- flyfun-weather reference: `~/Developer/public/flyfun-weather/main/src/weatherbrief/api/app.py`
