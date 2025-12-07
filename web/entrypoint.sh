#!/bin/bash
set -e

# Build client if source code is mounted
if [ -d "/app/web/client" ] && [ -f "/app/web/client/package.json" ]; then
    echo "Building client application..."
    cd /app/web/client
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo "Installing npm dependencies..."
        npm ci
    fi
    
    echo "Building TypeScript client..."
    npm run build
    echo "Client build complete."
fi

# Run the server
cd /app/web/server
exec python main.py

