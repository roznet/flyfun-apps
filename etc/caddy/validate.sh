#!/bin/bash
# Validate Caddy configuration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Validating Caddy configuration..."
echo "Caddyfile location: $SCRIPT_DIR/Caddyfile"
echo ""

if command -v caddy &> /dev/null; then
    caddy validate --config "$SCRIPT_DIR/Caddyfile"
else
    echo "Caddy CLI not found. Using Docker instead..."
    docker run --rm \
        -v "$SCRIPT_DIR:/etc/caddy:ro" \
        caddy:latest \
        caddy validate --config /etc/caddy/Caddyfile
fi

echo ""
echo "✓ Configuration is valid!"
