#!/bin/bash
# Build script for production deployment
# This script builds the frontend and updates index.html for production

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIENT_DIR="$SCRIPT_DIR/client"

echo "Building frontend for production..."

cd "$CLIENT_DIR"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing npm dependencies..."
    npm install
fi

# Build the frontend
echo "Building TypeScript frontend..."
npm run build

# Check if build was successful
if [ ! -f "dist/main.iife.js" ]; then
    echo "Error: Build failed - dist/main.iife.js not found"
    exit 1
fi

echo "Build successful!"
echo "Frontend built files are in: $CLIENT_DIR/dist/"
echo ""
echo "Next steps:"
echo "1. Ensure index.html references /dist/main.iife.js (or use conditional loading)"
echo "2. Restart the FastAPI service: sudo systemctl restart euro-aip.service"
echo "3. Test the application in your browser"

