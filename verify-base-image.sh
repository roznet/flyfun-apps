#!/bin/bash
# Verify that flyfun-base:latest was built from THIS checkout's requirements.txt
# and that every requirement is satisfied inside it.
#
# Run after `docker compose build --no-cache base` and before building the
# services. A failed base build leaves the previous flyfun-base:latest in
# place, and services built on it crash-loop on the flyfun-common startup
# guard (web/server/main.py) — this catches that before anything is recreated.
#
# Usage: ./verify-base-image.sh [image]   (default: flyfun-base:latest)

set -euo pipefail

IMAGE="${1:-flyfun-base:latest}"
cd "$(dirname "$0")"

# 1. The image must carry this checkout's requirements.txt. If the build
#    failed, :latest is still the old image and this diff is non-empty.
if ! docker run --rm "$IMAGE" cat /app/requirements.txt | diff -u - requirements.txt; then
    echo "FAIL: $IMAGE was not built from this checkout's requirements.txt" >&2
    echo "      rebuild it: docker compose build --no-cache base" >&2
    exit 1
fi

# 2. Every requirement in it must be satisfied by what is installed.
docker run --rm -i "$IMAGE" python - <<'EOF'
import sys
from importlib.metadata import version, PackageNotFoundError
try:
    from packaging.requirements import Requirement
except ImportError:
    from pip._vendor.packaging.requirements import Requirement

bad = []
for line in open('/app/requirements.txt'):
    line = line.split('#', 1)[0].strip()
    if not line:
        continue
    req = Requirement(line)
    try:
        installed = version(req.name)
    except PackageNotFoundError:
        bad.append(f'{req.name}: not installed')
        continue
    if not req.specifier.contains(installed, prereleases=True):
        bad.append(f'{req.name}: {installed} does not satisfy {req.specifier}')

print(f"flyfun-common {version('flyfun-common')}, euro-aip {version('euro-aip')}")
if bad:
    print('FAIL: unsatisfied requirements:\n  ' + '\n  '.join(bad), file=sys.stderr)
    sys.exit(1)
print('OK: all requirements satisfied')
EOF
