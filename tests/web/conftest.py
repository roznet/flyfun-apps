#!/usr/bin/env python3

"""
Conftest for web tests.
"""

import sys
from pathlib import Path

# Add the web server to path for imports
web_server_path = Path(__file__).parent.parent.parent / "web" / "server"
if str(web_server_path) not in sys.path:
    sys.path.insert(0, str(web_server_path))
