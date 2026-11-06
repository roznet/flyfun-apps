#!/bin/bash
# Build script for Docker images
# Ensures base image is built and verified before dependent images

set -euo pipefail
cd "$(dirname "$0")"

echo "Building base image..."
docker compose build base

echo "Verifying base image..."
./verify-base-image.sh

echo "Building web-server and mcp-server..."
docker compose build web-server mcp-server

echo "All images built successfully!"
