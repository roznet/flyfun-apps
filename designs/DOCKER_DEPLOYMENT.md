# Docker Deployment Guide

## Overview

This document describes the Docker deployment setup for the Euro AIP application, including the web server and MCP server.

## Architecture

The deployment consists of:
- **Web Server**: FastAPI application serving the web UI and API
  - Runs as non-root user (UID 2000, user `flyfun`)
  - Dockerfile: `web/Dockerfile`
- **MCP Server**: Model Context Protocol server for LLM integration
  - Runs as non-root user (UID 2001, user `flyfun-mcp`)
  - Dockerfile: `mcp_server/Dockerfile`
- **Shared Data**: Mounted volumes for data files, output, cache, and logs

## Directory Structure

```
.
├── web/
│   └── Dockerfile          # Web server container
├── mcp_server/
│   └── Dockerfile          # MCP server container
├── docker-compose.yml      # Orchestration
├── .env                    # Environment configuration (create from env.sample)
├── env.sample              # Template for .env
├── .dockerignore           # Files to exclude from builds
├── data/                   # Data files (airports.db, rules.json) - mounted as volume
├── out/                    # Output files (ga_meta.sqlite) - mounted as volume
├── cache/                  # Cache files (vector DB) - mounted as volume
└── logs/                   # Log files - mounted as volume
```

## Quick Start

### 1. Prepare Environment

```bash
# Copy environment template
cp env.sample .env

# Edit .env with your configuration
# - Set OPENAI_API_KEY
# - Adjust paths if needed
# - Configure security settings
```

### 2. Prepare Data Files and Directories

Ensure you have the required data files:
- `data/airports.db` - Airport database
- `data/rules.json` - Rules JSON file

```bash
# Create directories if they don't exist
mkdir -p data out cache logs

# Ensure data files are in place
ls -la data/airports.db data/rules.json

# Set permissions for writable directories (containers run as UID 2000/2001)
# Option 1: Make directories world-writable (less secure, but simple)
chmod 777 out cache logs

# Option 2: Create directories with specific ownership (more secure)
# This requires matching the UID/GID on your host system
# sudo chown -R 2000:2000 out cache logs
# chmod 755 out cache logs
```

**Note on Permissions**: The containers run as non-root users:
- Web server: UID 2000 (user `flyfun`)
- MCP server: UID 2001 (user `flyfun-mcp`)

For writable volumes (`out`, `cache`, `logs`), ensure they're writable by these UIDs or use world-writable permissions (777) for development.

### 3. Build and Run

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Configuration

### Environment Variables

All configuration is done through the `.env` file at the project root. Key variables:

#### Common
- `ENVIRONMENT`: `development` or `production`
- `AIRPORTS_DB`: Path to airports database (inside container: `/app/data/airports.db`)
- `RULES_JSON`: Path to rules JSON (inside container: `/app/data/rules.json`)
- `LOG_LEVEL`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

#### Web Server
- `WEB_PORT`: Port to expose (default: `8000`)
- `GA_META_DB`: Path to GA meta database (default: `/app/out/ga_meta.sqlite`)
- `GA_META_READONLY`: Whether GA database is read-only (default: `true`)
- `AVIATION_AGENT_ENABLED`: Enable aviation agent (default: `true`)
- `VECTOR_DB_PATH`: Path to vector database (default: `/app/cache/rules_vector_db`)

#### MCP Server
- `AIRPORTS_DB`: Path to airports database (inside container: `/app/data/airports.db`)
- `RULES_JSON`: Path to rules JSON (inside container: `/app/data/rules.json`)
- `LOG_LEVEL`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

#### Security
- `OPENAI_API_KEY`: OpenAI API key (required)

### Volume Mappings

The `docker-compose.yml` maps host directories to container paths:

| Host Directory | Container Path | Purpose | Access |
|---------------|---------------|---------|--------|
| `./data` | `/app/data` | Data files (airports.db, rules.json) | Read-only |
| `./out` | `/app/out` | Output files (ga_meta.sqlite) | Read-write |
| `./cache` | `/app/cache` | Cache files (vector DB) | Read-write |
| `./logs` | `/app/logs` | Log files | Read-write |

You can customize these in `.env`:
```bash
DATA_DIR=./data
OUTPUT_DIR=./out
CACHE_DIR=./cache
LOGS_DIR=./logs
```

## Data Files

### Required Files

1. **airports.db**: Airport database (SQLite)
   - Location: `data/airports.db`
   - Size: ~7.5MB (stored in Git LFS)
   - Read-only in containers

2. **rules.json**: Aviation rules metadata
   - Location: `data/rules.json`
   - Read-only in containers

### Output Files

1. **ga_meta.sqlite**: GA friendliness database
   - Location: `out/ga_meta.sqlite` (created by build tools)
   - Read-write in containers (if `GA_META_READONLY=false`)
   - Read-only in production web server (default)

2. **Vector DB**: Rules vector database for RAG
   - Location: `cache/rules_vector_db/`
   - Created automatically on first use
   - Read-write in containers

## Building Images

### Web Server

```bash
docker build -f web/Dockerfile -t flyfun-web-server .
```

### MCP Server

```bash
docker build -f mcp_server/Dockerfile -t flyfun-mcp-server .
```

### Both (via docker-compose)

```bash
docker-compose build
```

## Running Services

### Start All Services

```bash
docker-compose up -d
```

### Start Individual Services

```bash
# Web server only
docker-compose up -d web-server

# MCP server only
docker-compose up -d mcp-server
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web-server
docker-compose logs -f mcp-server
```

### Stop Services

```bash
docker-compose down
```

### Restart Services

```bash
docker-compose restart
```

## Health Checks

The web server includes a health check endpoint:
- URL: `http://localhost:8000/health`
- Returns: `{"status": "healthy", "timestamp": "..."}`

Docker Compose automatically monitors health:
```bash
# Check health status
docker-compose ps
```

## Development

### Local Development with Docker

1. **Mount source code as volume** (for live reload):
   ```yaml
   # Add to docker-compose.yml under web-server volumes:
   - ./web/server:/app/web/server:ro
   - ./shared:/app/shared:ro
   ```

2. **Use development environment**:
   ```bash
   ENVIRONMENT=development docker-compose up
   ```

### Debugging

```bash
# Execute command in running container
docker-compose exec web-server bash
docker-compose exec mcp-server bash

# View environment variables
docker-compose exec web-server env

# Check file permissions
docker-compose exec web-server ls -la /app/data
```

## Production Deployment

### Security Considerations

1. **API Keys**: Never commit `.env` file with real API keys
2. **File Permissions**: Ensure data files have correct permissions
3. **Network**: Use Docker networks to isolate services
4. **HTTPS**: Use reverse proxy (nginx/traefik) for HTTPS
5. **Secrets**: Consider using Docker secrets or external secret management

### Reverse Proxy Setup

Example nginx configuration:

```nginx
server {
    listen 80;
    server_name maps.flyfun.aero;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Environment-Specific Configuration

Create separate `.env` files for different environments:

```bash
# Development
cp env.sample .env.dev
# Edit .env.dev

# Production
cp env.sample .env.prod
# Edit .env.prod

# Use specific env file
docker-compose --env-file .env.prod up -d
```

## Troubleshooting

### Container Won't Start

1. **Check logs**:
   ```bash
   docker-compose logs web-server
   ```

2. **Check data files exist**:
   ```bash
   ls -la data/airports.db data/rules.json
   ```

3. **Check file permissions**:
   ```bash
   docker-compose exec web-server ls -la /app/data
   ```

### Database Errors

1. **Read-only database error**:
   - Check `GA_META_READONLY` setting
   - Ensure output directory is writable by UID 2000 (web server)
   - Check file permissions: `ls -la out/`
   - Fix permissions: `chmod 777 out` or `chown -R 2000:2000 out`

2. **Database not found**:
   - Verify `AIRPORTS_DB` path in `.env`
   - Check volume mount in `docker-compose.yml`
   - Ensure file exists in `data/` directory

3. **Permission denied errors**:
   - Containers run as non-root (UID 2000/2001)
   - Ensure writable volumes (`out`, `cache`, `logs`) have correct permissions
   - Check container user: `docker-compose exec web-server id`
   - Fix: `chmod 777 out cache logs` or match UID/GID on host

### Port Conflicts

If port 8000 is already in use:
```bash
# Change in .env
WEB_PORT=8001

# Or in docker-compose.yml
ports:
  - "8001:8000"
```

### Build Failures

1. **euro_aip installation fails**:
   - Check internet connection
   - Verify git repository URL in Dockerfile
   - Consider using local copy or submodule

2. **Dependencies fail**:
   ```bash
   # Rebuild without cache
   docker-compose build --no-cache
   ```

## Migration from Non-Docker Setup

### Step 1: Update Environment Loading

The code now uses `shared/env_loader.py` which:
- Supports both `.env` and `{env}.env` files
- Works with Docker (loads from root `.env`)
- Works with local development (loads from component directories)

### Step 2: Consolidate Configuration

Move from multiple `dev.env` files to single root `.env`:
- Old: `web/server/dev.env`, `mcp_server/dev.env`
- New: `.env` at root (used by both services)

### Step 3: Update Paths

Paths in `.env` are container paths:
- Old: `/Users/you/flyfun/data/airports.db`
- New: `/app/data/airports.db` (mapped from host `./data/airports.db`)

### Step 4: Test

```bash
# Build and test
docker-compose build
docker-compose up -d

# Verify services are running
docker-compose ps
curl http://localhost:8000/health
```

## Next Steps

- [ ] Set up CI/CD for automated builds
- [ ] Configure monitoring and alerting
- [ ] Set up backup strategy for data files
- [ ] Document production deployment process
- [ ] Add support for multiple environments (staging, production)

