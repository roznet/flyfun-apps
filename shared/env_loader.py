"""
Shared environment variable loader for consistent configuration across components.

Supports loading from:
1. explicit_path (if provided)
2. ENV_FILE environment variable (explicit path override)
3. .env file in component directory
4. .env file in project root (final fallback)
5. Environment variables already set (highest priority)

Uses python-dotenv for robust parsing (handles quotes, multiline, etc.)
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_component_env(
    component_dir: Path,
    env_name: Optional[str] = None,
    explicit_path: Optional[Path] = None
) -> None:
    """
    Load environment file for a component.
    
    Priority order:
    1. explicit_path (if provided)
    2. ENV_FILE environment variable
    3. .env in component directory (fallback)
    4. .env in project root (final fallback)
    
    Args:
        component_dir: Directory containing the component (e.g., web/server, mcp_server)
        env_name: Deprecated parameter, kept for backwards compatibility but not used
        explicit_path: Explicit path to env file (overrides all other logic)
    """
    # Priority 1: Explicit path
    if explicit_path:
        if explicit_path.exists():
            load_dotenv(explicit_path, override=True)
            return
        else:
            # Don't fail silently - warn if explicit path doesn't exist
            import warnings
            warnings.warn(f"Explicit env file path does not exist: {explicit_path}")
    
    # Priority 2: ENV_FILE environment variable
    env_file_var = os.getenv("ENV_FILE")
    if env_file_var:
        env_file = Path(env_file_var)
        if env_file.exists():
            load_dotenv(env_file, override=True)
            return
    
    # Priority 3: .env in component directory (fallback)
    env_file = component_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
        return
    
    # Priority 4: .env in project root (final fallback)
    # Find project root (assumes this file is in shared/)
    project_root = Path(__file__).parent.parent
    root_env_file = project_root / ".env"
    if root_env_file.exists():
        load_dotenv(root_env_file, override=True)
        return


