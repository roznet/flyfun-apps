#!/bin/zsh

# Simple launcher for the Euro AIP MCP server.
# Usage: start_mcp.ksh /path/to/python /path/to/dev.env
# The script changes directory to "mcp_server" (this script's directory).

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 /path/to/python /path/to/dev.env [main.py args...]" >&2
    exit 1
fi

PYTHON_PATH=$1
ENV_FILE=$2
shift 2

if [ ! -x "$PYTHON_PATH" ]; then
    if command -v "$PYTHON_PATH" >/dev/null 2>&1; then
        PYTHON_PATH=$(command -v "$PYTHON_PATH")
    else
        echo "Error: Python interpreter '$PYTHON_PATH' not found or not executable." >&2
        exit 1
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: Environment file '$ENV_FILE' does not exist." >&2
    exit 1
fi

# Load environment variables (auto-export)
echo "Loading environment variables from '$ENV_FILE'"
set -a
. "$ENV_FILE"
set +a

echo "AIRPORTS_DB: $AIRPORTS_DB"
echo "RULES_JSON: $RULES_JSON"

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

cd "$SCRIPT_DIR" || exit 1

exec "$PYTHON_PATH" "main.py" "$@"

