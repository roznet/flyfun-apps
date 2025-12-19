#!/usr/bin/env python3

"""
Unit tests for OAuth authentication routes.

Tests JWT token creation/verification, state management, and route responses.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# Add the web server to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "web" / "server"))


class TestJWTTokens:
    """Test JWT token creation and verification."""
    
    def test_create_access_token(self):
        """Test that access tokens are created correctly."""
        from api.auth import create_access_token, decode_access_token
        
        token_data = {
            "sub": "user123",
            "email": "test@example.com",
            "name": "Test User",
            "provider": "google"
        }
        
        token = create_access_token(token_data)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        
    def test_decode_access_token(self):
        """Test that access tokens decode correctly."""
        from api.auth import create_access_token, decode_access_token
        
        token_data = {
            "sub": "user123",
            "email": "test@example.com",
            "name": "Test User",
            "provider": "google"
        }
        
        token = create_access_token(token_data)
        decoded = decode_access_token(token)
        
        assert decoded is not None
        assert decoded["sub"] == "user123"
        assert decoded["email"] == "test@example.com"
        assert decoded["name"] == "Test User"
        assert decoded["provider"] == "google"
        assert "exp" in decoded
        assert "iat" in decoded
        
    def test_decode_invalid_token(self):
        """Test that invalid tokens return None."""
        from api.auth import decode_access_token
        
        result = decode_access_token("invalid.token.here")
        assert result is None
        
    def test_decode_expired_token(self):
        """Test that expired tokens return None."""
        from api.auth import create_access_token, decode_access_token
        
        # Create a token with negative expiry (already expired)
        token_data = {"sub": "user123", "email": "test@example.com"}
        token = create_access_token(token_data, expires_delta=timedelta(seconds=-10))
        
        result = decode_access_token(token)
        assert result is None


class TestStateManagement:
    """Test OAuth state token management for CSRF protection."""
    
    def test_generate_state(self):
        """Test state token generation."""
        from api.auth import _generate_state
        
        state = _generate_state()
        
        assert state is not None
        assert isinstance(state, str)
        assert len(state) > 20  # Should be reasonably long
        
    def test_verify_valid_state(self):
        """Test that valid state tokens verify correctly."""
        from api.auth import _generate_state, _verify_state
        
        state = _generate_state()
        result = _verify_state(state)
        
        assert result is True
        
    def test_verify_invalid_state(self):
        """Test that invalid state tokens fail verification."""
        from api.auth import _verify_state
        
        result = _verify_state("invalid-state-token")
        
        assert result is False
        
    def test_state_consumed_after_verification(self):
        """Test that state tokens are consumed (one-time use)."""
        from api.auth import _generate_state, _verify_state
        
        state = _generate_state()
        
        # First verification should succeed
        first_result = _verify_state(state)
        assert first_result is True
        
        # Second verification should fail (token consumed)
        second_result = _verify_state(state)
        assert second_result is False


class TestAuthConfig:
    """Test authentication configuration."""
    
    def test_is_auth_configured_without_env(self):
        """Test auth configuration check with no env vars."""
        with patch.dict(os.environ, {}, clear=True):
            # Need to reload the module to pick up env changes
            from auth_config import is_auth_configured
            # When no env vars are set, auth should not be configured
            # (This depends on default values in the config)
            
    def test_apple_private_key_missing(self):
        """Test getting Apple private key when file doesn't exist."""
        from auth_config import get_apple_private_key
        
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY_PATH": "/nonexistent/path.p8"}):
            # Reload to pick up new env
            import importlib
            import auth_config
            importlib.reload(auth_config)
            
            result = auth_config.get_apple_private_key()
            assert result == ""


class TestAuthStatusEndpoint:
    """Test the /api/auth/status endpoint."""
    
    def test_status_unauthenticated(self):
        """Test status endpoint when not authenticated."""
        # Import here to avoid circular import issues
        from api.auth import router
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router)
        
        client = TestClient(app)
        response = client.get("/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user"] is None
        assert "providers" in data


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
