# Multi-stage build for Euro AIP Web Server
# Stage 1: Build client with Node.js
FROM node:20-slim AS client-builder

WORKDIR /build

# Copy client source and dependencies
COPY web/client/package*.json ./
RUN npm ci

# Copy client source code
COPY web/client/ ./

# Build the client
RUN npm run build

# Stage 2: Final image with web server (uses base image from Dockerfile.base)
FROM flyfun-base:latest AS final

# Create non-root user with UID 2000
RUN groupadd -r -g 2000 flyfun && \
    useradd -r -u 2000 -g flyfun -d /app -s /bin/bash flyfun

# Copy application-specific code
COPY web/server/ /app/web/server/

# Copy shared application code
COPY shared/ /app/shared/

# Copy agent behavior configs (prompts, tools, examples)
COPY configs/ /app/configs/

# Copy built client dist from builder stage
COPY --from=client-builder /build/dist /app/web/client/dist
# Also copy other client files needed at runtime (CSS, HTML)
COPY web/client/css/ /app/web/client/css/
COPY web/client/index.html /app/web/client/index.html

# Copy ga_persona.db into container (optional - will be in writable location)
# This allows SQLite to work properly even if /app/data is mounted read-only
# Create directory first, then copy if file exists
RUN mkdir -p /app/data_builtin
COPY data/ga_persona.db /app/data_builtin/ga_persona.db

# Set correct ownership
RUN chown -R flyfun:flyfun /app

# Switch to non-root user
USER flyfun

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the server
WORKDIR /app/web/server
CMD ["python", "main.py"]

