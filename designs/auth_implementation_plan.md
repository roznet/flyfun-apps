# Web Authentication with Google & Apple Sign-In

Add OAuth-based authentication to the FlyFun web UI, allowing users to sign in using their Google account or Apple ID. The system will use JWT tokens for stateless session management.

## Login Page Design

The login page features:
- **OAuth-only** - No email/password form, just social login buttons
- **Glassmorphism dark theme** matching aviation aesthetics
- **Google Sign-In** and **Apple Sign-In** buttons (stacked vertically)
- Subtle aviation-themed decorations
- Mobile responsive design

---

## Configuration Required

> [!IMPORTANT]
> **OAuth Credentials Needed**: You'll need to configure:
> - **Google**: Create OAuth 2.0 credentials in [Google Cloud Console](https://console.cloud.google.com/apis/credentials)  
> - **Apple**: Create Service ID and generate private key in [Apple Developer Portal](https://developer.apple.com/account/resources/identifiers/list/serviceId)

**Architecture**: Stateless JWT authentication (no database). User info stored in JWT token only.

---

## Proposed Changes

### Backend Authentication Module

#### [NEW] [auth.py](file:///home/qian/dev/022_Home/flyfun-apps/web/server/api/auth.py)

New FastAPI router for authentication endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/google` | GET | Initiate Google OAuth flow |
| `/api/auth/apple` | GET | Initiate Apple OAuth flow |
| `/api/auth/callback/google` | GET | Google OAuth callback |
| `/api/auth/callback/apple` | POST | Apple OAuth callback (uses form_post) |
| `/api/auth/logout` | POST | Clear session/JWT |
| `/api/auth/me` | GET | Get current user info |

**Key implementation details:**
- **Google**: Use OpenID Connect via `authlib` library
- **Apple**: Generate dynamic JWT client secret using private key
- **Session**: Issue JWT access tokens (15min) + refresh tokens (7 days)
- **CSRF**: Use `state` parameter for OAuth flow protection

---

#### [NEW] [auth_config.py](file:///home/qian/dev/022_Home/flyfun-apps/web/server/auth_config.py)

Configuration for OAuth providers:

```python
# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# Apple OAuth  
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID")  # Service ID
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID")
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID")
APPLE_PRIVATE_KEY_PATH = os.getenv("APPLE_PRIVATE_KEY_PATH")

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
```

---

#### [MODIFY] [main.py](file:///home/qian/dev/022_Home/flyfun-apps/web/server/main.py)

Mount the new auth router:

```diff
+from api import auth
+
+# Authentication routes
+app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
```

---

#### [MODIFY] [requirements.txt](file:///home/qian/dev/022_Home/flyfun-apps/requirements.txt)

Add authentication dependencies:

```diff
+authlib==1.4.1
+python-jose[cryptography]==3.3.0
+httpx==0.27.0
```

---

### Frontend Changes

#### [NEW] [login.html](file:///home/qian/dev/022_Home/flyfun-apps/web/client/login.html)

Standalone login page with:
- Glassmorphism card design
- Google Sign-In button (official branding)
- Apple Sign-In button (official branding)
- Redirect to main app after successful auth

---

#### [NEW] [ts/auth.ts](file:///home/qian/dev/022_Home/flyfun-apps/web/client/ts/auth.ts)

Auth state management with Zustand:

```typescript
interface AuthState {
  user: User | null;
  isLoading: boolean;
  login: (provider: 'google' | 'apple') => void;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}
```

---

#### [MODIFY] [index.html](file:///home/qian/dev/022_Home/flyfun-apps/web/client/index.html)

Add user avatar/login button to header, redirect to login if not authenticated.

---

## Verification Plan

### Unit Tests

#### [NEW] [tests/web/test_auth.py](file:///home/qian/dev/022_Home/flyfun-apps/tests/web/test_auth.py)

Test cases:
- `test_google_oauth_initiate`: Verify redirect URL generation
- `test_apple_client_secret_generation`: Verify JWT client secret format
- `test_jwt_token_creation`: Verify access/refresh token generation
- `test_protected_route_without_auth`: Verify 401 response
- `test_protected_route_with_valid_token`: Verify access granted
- `test_logout_invalidates_session`: Verify token cleared

**Run command:**
```bash
cd /home/qian/dev/022_Home/flyfun-apps
source /root/Projects/flyfun/bin/activate
pytest tests/web/test_auth.py -v
```

### Manual Verification

1. **Start the web server:**
   ```bash
   cd /home/qian/dev/022_Home/flyfun-apps/web/server
   source /root/Projects/flyfun/bin/activate
   python main.py
   ```

2. **Test login flow:**
   - Navigate to `http://localhost:8000`
   - Click "Sign in with Google" button
   - Complete Google OAuth consent
   - Verify redirect back to app with user info displayed

3. **Test protected access:**
   - Clear cookies/logout
   - Try accessing a protected API endpoint
   - Verify 401 response

4. **Test logout:**
   - While logged in, click logout
   - Verify user info cleared
   - Verify protected routes require login again
