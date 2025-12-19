#!/usr/bin/env python3

"""
Authentication configuration for OAuth providers.

This file contains configuration values for Google and Apple OAuth.
All sensitive values should be set via environment variables.
"""

import os
from pathlib import Path

# ============================================================================
# GOOGLE OAUTH CONFIGURATION
# ============================================================================

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# ============================================================================
# APPLE OAUTH CONFIGURATION
# ============================================================================

APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")  # Service ID (e.g., com.example.flyfun)
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY_PATH = os.getenv("APPLE_PRIVATE_KEY_PATH", "")

# Apple OAuth endpoints
APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"

# ============================================================================
# JWT CONFIGURATION
# ============================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-production-to-a-random-secret")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours for better UX
REFRESH_TOKEN_EXPIRE_DAYS = 30

# ============================================================================
# OAUTH REDIRECT CONFIGURATION
# ============================================================================

# Base URL for OAuth callbacks (set this to your deployed domain in production)
BASE_URL = os.getenv("AUTH_BASE_URL", "http://localhost:8000")

# Callback URLs
GOOGLE_REDIRECT_URI = f"{BASE_URL}/api/auth/callback/google"
APPLE_REDIRECT_URI = f"{BASE_URL}/api/auth/callback/apple"

# Where to redirect after successful login
LOGIN_SUCCESS_REDIRECT = "/"
LOGIN_FAILURE_REDIRECT = "/login.html?error=auth_failed"

# ============================================================================
# COOKIE CONFIGURATION
# ============================================================================

COOKIE_NAME = "flyfun_auth"
COOKIE_SECURE = os.getenv("ENVIRONMENT", "development") == "production"
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = "lax"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def is_auth_configured() -> bool:
    """Check if at least one OAuth provider is configured."""
    google_configured = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    apple_configured = bool(APPLE_CLIENT_ID and APPLE_TEAM_ID and APPLE_KEY_ID and APPLE_PRIVATE_KEY_PATH)
    return google_configured or apple_configured


def get_apple_private_key() -> str:
    """Load Apple private key from file."""
    if not APPLE_PRIVATE_KEY_PATH:
        return ""
    key_path = Path(APPLE_PRIVATE_KEY_PATH)
    if not key_path.exists():
        return ""
    return key_path.read_text()
