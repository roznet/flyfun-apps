#!/bin/zsh

# Simple launcher for the Euro AIP web server.
# Usage: start_server.ksh /path/to/python /path/to/dev.env
# The script changes directory to "server" located alongside start_server.ksh.

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 /path/to/python /path/to/dev.env" >&2
    exit 1
fi

PYTHON_PATH=$1
ENV_FILE=$2

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

# Load environment variables
echo "Loading environment variables from '$ENV_FILE'"
set -a
. "$ENV_FILE"
set +a
echo "AIRPORTS_DB: $AIRPORTS_DB"
echo "RULES_JSON: $RULES_JSON"

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SERVER_DIR="$SCRIPT_DIR/server"

if [ ! -d "$SERVER_DIR" ]; then
    echo "Error: Expected server directory at '$SERVER_DIR'" >&2
    exit 1
fi

cd "$SERVER_DIR" || exit 1


exec "$PYTHON_PATH" "main.py"

