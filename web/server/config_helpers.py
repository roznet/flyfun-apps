#!/usr/bin/env python3

"""
Configuration helper functions for the Euro AIP Airport Explorer.

This file wraps the centralized config functions from shared/aviation_agent/config.py
with production safety validation.

This separation allows:
- config_helpers.py to be tracked by git and auto-update
- security_config.py to be customized per environment without conflicts
- Production safety validation while using centralized path resolution
"""

import os
from security_config import ENVIRONMENT, ALLOWED_DIRS


def _is_path_allowed(path: str) -> bool:
    """Check if a path starts with any of the allowed directories.
    
    Args:
        path: Path to check
        
    Returns:
        True if path is in an allowed directory
    """
    # In development, allow any path
    if ENVIRONMENT != "production":
        return True
    
    # In production, check against allowed directories
    for allowed_dir in ALLOWED_DIRS:
        if path.startswith(allowed_dir):
            return True

    return False


def _validate_and_fix_path(path: str, default_name: str, fallback_dir: str = "./") -> str:
    """Validate and fix a path to ensure it's in an allowed directory.
    
    Args:
        path: Path to validate
        default_name: Default filename to use if path needs to be fixed
        fallback_dir: Fallback directory prefix (default: "./")
        
    Returns:
        Validated safe path
    """
    # In production, ensure path is in an allowed location
    if ENVIRONMENT == "production":
        if not _is_path_allowed(path):
            # Use first allowed directory as fallback
            fallback = ALLOWED_DIRS[0] if ALLOWED_DIRS else fallback_dir
            path = os.path.join(fallback, default_name)
    
    return path


def _get_default_safe_path(env_var: str, default_name: str, fallback_dir: str = "./") -> str:
    """Get a safe path with validation, using first allowed directory as fallback.
    
    Args:
        env_var: Environment variable name to read
        default_name: Default filename if env var not set
        fallback_dir: Fallback directory prefix (default: "./")
        
    Returns:
        Validated safe path
    """
    path = os.getenv(env_var, default_name)
    return _validate_and_fix_path(path, default_name, fallback_dir)


def get_safe_db_path() -> str:
    """Get a safe database path with validation.
    
    Uses centralized config function and adds production safety validation.
    
    Returns:
        Path to airports database
    """
    from shared.aviation_agent.config import _default_airports_db
    path = str(_default_airports_db())
    return _validate_and_fix_path(path, "airports.db")


def get_safe_rules_path() -> str:
    """Get a safe rules path with validation.
    
    Uses centralized config function and adds production safety validation.
    
    Returns:
        Path to rules.json file
    """
    from shared.aviation_agent.config import _default_rules_json
    path = str(_default_rules_json())
    return _validate_and_fix_path(path, "rules.json")


def get_safe_ga_meta_db_path() -> str | None:
    """Get a safe GA meta database path with validation.
    
    Uses centralized config function and adds production safety validation.
    
    Returns:
        Path to GA persona database or None if not configured/available
    """
    from shared.aviation_agent.config import get_ga_meta_db_path
    
    db_path = get_ga_meta_db_path()
    
    if db_path is None:
        return None
    
    # Validate and fix path using shared logic
    db_path = _validate_and_fix_path(db_path, "ga_persona.db")
    
    # Verify file exists
    if not os.path.exists(db_path):
        return None
    
    return db_path

