"""Every route commits its session before the response is sent.

flyfun-common's ``current_user_id`` resolves ``Depends(get_db, scope="function")``.
A bare ``Depends(get_db)`` here would commit only after the response had gone
out, and give the request a second session (which locks on SQLite against the
token's ``last_used_at`` write). See flyfun-common ``designs/db.md``.
"""

import sys
from pathlib import Path

# Ensure web/server is importable
_server_dir = Path(__file__).resolve().parents[2] / "web" / "server"
if str(_server_dir) not in sys.path:
    sys.path.insert(0, str(_server_dir))


def test_no_route_resolves_get_db_at_request_scope():
    from flyfun_common.db import find_request_scoped_db
    from flyfun_common.db.deps import _iter_route_dependants
    from main import app

    assert len(list(_iter_route_dependants(app.routes))) > 40
    assert find_request_scoped_db(app) == []
