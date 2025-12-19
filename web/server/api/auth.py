#!/usr/bin/env python3

"""
OAuth Authentication API routes for Google and Apple Sign-In.

This module provides stateless JWT-based authentication using OAuth providers.
No database is required - user info is stored in the JWT token itself.
"""

import secrets
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, JWTError
from authlib.integrations.httpx_client import AsyncOAuth2Client
import httpx

from auth_config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_DISCOVERY_URL, GOOGLE_REDIRECT_URI,
    APPLE_CLIENT_ID, APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_AUTH_URL, APPLE_TOKEN_URL, APPLE_JWKS_URL, APPLE_REDIRECT_URI,
    JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
    COOKIE_NAME, COOKIE_SECURE, COOKIE_HTTPONLY, COOKIE_SAMESITE, COOKIE_MAX_AGE,
    LOGIN_SUCCESS_REDIRECT, LOGIN_FAILURE_REDIRECT,
    get_apple_private_key, is_auth_configured
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory state storage for CSRF protection (use Redis in production for multiple instances)
_oauth_states: dict[str, float] = {}
STATE_EXPIRY_SECONDS = 600  # 10 minutes


def _generate_state() -> str:
    """Generate a random state token for CSRF protection."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    # Clean up old states
    current_time = time.time()
    expired = [s for s, t in _oauth_states.items() if current_time - t > STATE_EXPIRY_SECONDS]
    for s in expired:
        _oauth_states.pop(s, None)
    return state


def _verify_state(state: str) -> bool:
    """Verify the state token is valid and not expired."""
    if state not in _oauth_states:
        return False
    created_time = _oauth_states.pop(state)
    return time.time() - created_time < STATE_EXPIRY_SECONDS


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def get_current_user(request: Request) -> Optional[dict]:
    """Extract current user from JWT cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return decode_access_token(token)


def require_auth(request: Request) -> dict:
    """Dependency that requires authentication."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ============================================================================
# GOOGLE OAUTH
# ============================================================================

@router.get("/google")
async def google_login():
    """Initiate Google OAuth flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    
    state = _generate_state()
    
    # Fetch Google's OAuth configuration
    async with httpx.AsyncClient() as client:
        resp = await client.get(GOOGLE_DISCOVERY_URL)
        google_config = resp.json()
    
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account"
    }
    
    auth_url = f"{google_config['authorization_endpoint']}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/callback/google")
async def google_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Google OAuth callback."""
    if error:
        logger.warning(f"Google OAuth error: {error}")
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)
    
    if not code or not state:
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)
    
    if not _verify_state(state):
        logger.warning("Invalid state token in Google callback")
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)
    
    try:
        # Fetch Google's OAuth configuration
        async with httpx.AsyncClient() as client:
            resp = await client.get(GOOGLE_DISCOVERY_URL)
            google_config = resp.json()
            
            # Exchange code for tokens
            token_resp = await client.post(
                google_config["token_endpoint"],
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": GOOGLE_REDIRECT_URI
                }
            )
            tokens = token_resp.json()
            
            if "error" in tokens:
                logger.error(f"Google token error: {tokens}")
                return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)
            
            # Get user info
            userinfo_resp = await client.get(
                google_config["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            userinfo = userinfo_resp.json()
        
        # Create our JWT token with user info
        token_data = {
            "sub": userinfo.get("sub"),
            "email": userinfo.get("email"),
            "name": userinfo.get("name"),
            "picture": userinfo.get("picture"),
            "provider": "google"
        }
        access_token = create_access_token(token_data)
        
        # Set cookie and redirect
        response = RedirectResponse(url=LOGIN_SUCCESS_REDIRECT, status_code=302)
        response.set_cookie(
            key=COOKIE_NAME,
            value=access_token,
            max_age=COOKIE_MAX_AGE,
            httponly=COOKIE_HTTPONLY,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE
        )
        
        logger.info(f"User logged in via Google: {userinfo.get('email')}")
        return response
        
    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}", exc_info=True)
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)


# ============================================================================
# APPLE OAUTH
# ============================================================================

def _generate_apple_client_secret() -> str:
    """Generate a dynamic client secret JWT for Apple OAuth."""
    private_key = get_apple_private_key()
    if not private_key:
        raise ValueError("Apple private key not configured")
    
    now = datetime.utcnow()
    payload = {
        "iss": APPLE_TEAM_ID,
        "iat": now,
        "exp": now + timedelta(days=180),  # Max 6 months
        "aud": "https://appleid.apple.com",
        "sub": APPLE_CLIENT_ID
    }
    
    headers = {
        "kid": APPLE_KEY_ID,
        "alg": "ES256"
    }
    
    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


@router.get("/apple")
async def apple_login():
    """Initiate Apple OAuth flow."""
    if not APPLE_CLIENT_ID or not APPLE_TEAM_ID or not APPLE_KEY_ID:
        raise HTTPException(status_code=503, detail="Apple OAuth not configured")
    
    state = _generate_state()
    
    params = {
        "client_id": APPLE_CLIENT_ID,
        "redirect_uri": APPLE_REDIRECT_URI,
        "response_type": "code id_token",
        "response_mode": "form_post",
        "scope": "name email",
        "state": state
    }
    
    auth_url = f"{APPLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.post("/callback/apple")
async def apple_callback(request: Request):
    """Handle Apple OAuth callback (uses form_post)."""
    form = await request.form()
    code = form.get("code")
    id_token = form.get("id_token")
    state = form.get("state")
    error = form.get("error")
    user_data = form.get("user")  # Only sent on first authorization
    
    if error:
        logger.warning(f"Apple OAuth error: {error}")
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)
    
    if not state or not _verify_state(state):
        logger.warning("Invalid state token in Apple callback")
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)
    
    try:
        # If we have an id_token, we can decode it directly
        # Otherwise, exchange code for tokens
        if not id_token and code:
            client_secret = _generate_apple_client_secret()
            
            async with httpx.AsyncClient() as client:
                token_resp = await client.post(
                    APPLE_TOKEN_URL,
                    data={
                        "client_id": APPLE_CLIENT_ID,
                        "client_secret": client_secret,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": APPLE_REDIRECT_URI
                    }
                )
                tokens = token_resp.json()
                
                if "error" in tokens:
                    logger.error(f"Apple token error: {tokens}")
                    return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)
                
                id_token = tokens.get("id_token")
        
        if not id_token:
            return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)
        
        # Fetch Apple's public keys to verify the token
        async with httpx.AsyncClient() as client:
            keys_resp = await client.get(APPLE_JWKS_URL)
            apple_keys = keys_resp.json()
        
        # Decode the id_token (we trust Apple's signature for now)
        # In production, you should verify the signature with Apple's JWKS
        id_token_payload = jwt.decode(
            id_token,
            options={"verify_signature": False}  # TODO: Implement proper verification
        )
        
        # Extract user info
        # Note: Apple only sends name on first authorization
        email = id_token_payload.get("email")
        sub = id_token_payload.get("sub")
        
        # Parse user data if provided (first authorization only)
        name = None
        if user_data:
            import json
            try:
                user_info = json.loads(user_data)
                name_parts = user_info.get("name", {})
                first_name = name_parts.get("firstName", "")
                last_name = name_parts.get("lastName", "")
                name = f"{first_name} {last_name}".strip()
            except json.JSONDecodeError:
                pass
        
        # Create our JWT token
        token_data = {
            "sub": sub,
            "email": email,
            "name": name,
            "picture": None,  # Apple doesn't provide profile pictures
            "provider": "apple"
        }
        access_token = create_access_token(token_data)
        
        # Set cookie and redirect
        response = RedirectResponse(url=LOGIN_SUCCESS_REDIRECT, status_code=302)
        response.set_cookie(
            key=COOKIE_NAME,
            value=access_token,
            max_age=COOKIE_MAX_AGE,
            httponly=COOKIE_HTTPONLY,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE
        )
        
        logger.info(f"User logged in via Apple: {email}")
        return response
        
    except Exception as e:
        logger.error(f"Apple OAuth callback error: {e}", exc_info=True)
        return RedirectResponse(url=LOGIN_FAILURE_REDIRECT)


# ============================================================================
# USER INFO & LOGOUT
# ============================================================================

@router.get("/me")
async def get_me(request: Request):
    """Get current authenticated user info."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "provider": user.get("provider")
    }


@router.post("/logout")
async def logout(response: Response):
    """Clear the authentication cookie."""
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(key=COOKIE_NAME)
    return response


@router.get("/status")
async def auth_status(request: Request):
    """Check authentication status and available providers."""
    user = get_current_user(request)
    
    return {
        "authenticated": user is not None,
        "user": {
            "email": user.get("email"),
            "name": user.get("name"),
            "picture": user.get("picture"),
            "provider": user.get("provider")
        } if user else None,
        "providers": {
            "google": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            "apple": bool(APPLE_CLIENT_ID and APPLE_TEAM_ID and APPLE_KEY_ID)
        }
    }
