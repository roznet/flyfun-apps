#!/usr/bin/env python3
"""
Pytest configuration for flyfun-apps.
Ensures the repository root is importable when running tests in isolation.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

