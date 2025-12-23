# Docker Deployment Guide

## Overview

This document describes the Docker deployment setup for the Euro AIP application, including the web server, MCP server, and ChromaDB vector database.

**Services:**
- **Web Server**: FastAPI application (port 8000)
- **MCP Server**: Model Context Protocol server for LLM integration
- **ChromaDB**: Vector database for RAG (port 8001)

---

## Initial Setup

### 1. Prerequisites
- Docker and Docker Compose installed
- Git (to clone the repository)

### 2. Clone and Prepare

```bash
# Clone repository
git clone <repository-url>
cd flyfun-apps

# Create required directories
mkdir -p data out logs out/chromadb_data

# Set permissions (development - use proper ownership for production)
chmod 777 out logs out/chromadb_data
```

### 3. Prepare Data Files

**Required:**
- `data/airports.db` - Airport database (must exist, ~7.5MB)
- `data/rules.json` - Aviation rules JSON (generate from Excel if needed)

**Optional:**
- `data/ga_persona.db` - GA friendliness persona database (build if you have export data)

### 4. Configure Environment

```bash
# Copy template
cp env.sample .env

# Edit .env with your settings
nano .env
```

**Required in `.env`:**
```bash
OPENAI_API_KEY=your-openai-api-key-here
ENVIRONMENT=production  # or 'development'
```

**Note:** Paths are automatically set by `docker-compose.yml` - you don't need to configure them in `.env` for Docker.

### 5. Configure Security

```bash
# Copy Docker-specific security config
cp web/server/security_config.docker.py web/server/security_config.py
```

**Edit `web/server/security_config.py`:**

1. **ALLOWED_DIRS** - Use container paths:
   ```python
   ALLOWED_DIRS = ["/app/data", "/app/out", "/app/logs", "/app"]
   ```

2. **ALLOWED_ORIGINS** - Add your production domains:
   ```python
   ALLOWED_ORIGINS = ["https://maps.flyfun.aero", "https://flyfun.aero"]
   ```

3. **ALLOWED_HOSTS** - Add domains + Docker service names:
   ```python
   ALLOWED_HOSTS = ["maps.flyfun.aero", "flyfun.aero", "web-server", "flyfun-web-server"]
   ```

4. **FORCE_HTTPS** - Set to `False` (HTTPS handled by reverse proxy):
   ```python
   FORCE_HTTPS = False
   ```

### 6. Build and Start

```bash
# Build images
docker-compose build

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 7. Build Vector Database

After starting services, build the RAG vector database:

```bash
docker exec -it flyfun-web-server python /app/tools/xls_to_rules.py \
    --out /app/data/rules.json \
    --build-rag
```

This builds the ChromaDB vector database from `rules.json`. **Data persists in `out/chromadb_data/`** on the host and will survive container restarts and rebuilds.

### 8. Verify Setup

```bash
# Check health
curl http://localhost:8000/health
curl http://localhost:8001/api/v2/heartbeat  # ChromaDB

# Test API
curl http://localhost:8000/api/airports/EGLL

# Check logs
docker-compose logs web-server | grep "Loaded model"
```

---

## Updates

### Code Changes

**When you change application code** (Python files, TypeScript, `requirements.txt`, etc.):

```bash
# Pull latest code
git pull

# Rebuild image (compiles TypeScript, installs dependencies)
docker-compose build web-server

# Restart with new image
docker-compose up -d web-server

# Verify
docker-compose logs web-server --tail=20
curl http://localhost:8000/health
```

**Quick update (no rebuild needed):**
- Changes to `.env`, `security_config.py`, or files in `tools/` only require restart:
  ```bash
  docker-compose restart web-server
  ```

**What requires rebuild vs restart:**
- **Rebuild needed:** `web/server/*.py`, `web/client/`, `shared/`, `requirements.txt`
- **Restart only:** `.env`, `security_config.py`, `tools/`, data files in `data/`

### Update airports.db

**Replace the database file:**

```bash
# Stop services (optional, but safer)
docker-compose stop web-server mcp-server

# Replace the file on host
cp /path/to/new/airports.db data/airports.db

# Restart services
docker-compose start web-server mcp-server

# Verify
docker exec flyfun-web-server ls -la /app/data/airports.db
curl http://localhost:8000/api/airports/EGLL
```

**Note:** The `data/` directory is mounted as a volume, so file changes are immediately available in containers.

### Update GA persona database

**Option 1: Build from export data (recommended)**

```bash
# If you have airfield.directory export JSON
docker exec -it flyfun-web-server python /app/tools/build_ga_friendliness.py \
    --export /path/to/export.json \
    --output /app/data/ga_persona.db
```

**Option 2: Replace existing file**

```bash
# Stop web-server (if GA_META_READONLY=false, otherwise optional)
docker-compose stop web-server

# Replace file on host
cp /path/to/new/ga_persona.db data/ga_persona.db

# Restart
docker-compose start web-server
```

**Note:** The file is in `data/ga_persona.db` on the host, mounted into containers.

### Rebuild RAG (Vector Database)

**When `rules.json` is updated:**

```bash
# Rebuild vector database from rules.json
docker exec -it flyfun-web-server python /app/tools/xls_to_rules.py \
    --out /app/data/rules.json \
    --vector-db-url http://chromadb:8000 \
    --build-rag
```

**When Excel files are updated:**

1. Place Excel files in `data/` directory:
   ```bash
   cp /path/to/definitions.xlsx data/
   cp /path/to/GB-rules.xlsx data/
   cp /path/to/FR-rules.xlsx data/
   ```

2. Rebuild rules.json and vector database:
   ```bash
   docker exec -it flyfun-web-server python /app/tools/xls_to_rules.py \
       --out /app/data/rules.json \
       --defs /app/data/definitions.xlsx \
       --add GB "/app/data/GB-rules.xlsx" \
       --add FR "/app/data/FR-rules.xlsx" \
       --build-rag
   ```

**Note:** ChromaDB data persists in `out/chromadb_data/`. Rebuilding replaces the existing vector database.

### Update rules.json Only

If you only need to update `rules.json` without rebuilding the vector database:

```bash
# Replace file on host
cp /path/to/new/rules.json data/rules.json

# Restart web-server to pick up changes
docker-compose restart web-server
```

To update the vector database after updating `rules.json`, see "Rebuild RAG" above.

### Full Service Update

To update all services (web, MCP, ChromaDB):

```bash
# Pull latest code
git pull

# Stop containers (data persists in volumes)
docker-compose down

# Rebuild all images
docker-compose build

# Start all services (ChromaDB data will be restored from volume)
docker-compose up -d

# Verify
docker-compose ps
docker-compose logs --tail=50
```

**Important:** ChromaDB data persists in `out/chromadb_data/` on the host. After `docker-compose down` and rebuild, the data will automatically be restored when the container starts. You should **not** need to rebuild the vector database unless you've updated `rules.json`.

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs web-server

# Check data files exist
ls -la data/airports.db data/rules.json

# Check file permissions
docker exec flyfun-web-server ls -la /app/data
```

### Database Errors

**Read-only database error:**
```bash
# Check permissions
ls -la out/

# Fix permissions
chmod 777 out logs
# Or use proper ownership: chown -R 2000:2000 out logs
```

**ChromaDB connection errors:**
```bash
# Verify ChromaDB is running
docker-compose ps chromadb

# Check ChromaDB logs
docker-compose logs chromadb

# Test connectivity from web-server
docker exec flyfun-web-server curl http://chromadb:8000/api/v1/heartbeat
```

**Vector database not found:**
```bash
# Rebuild vector database
docker exec -it flyfun-web-server python /app/tools/xls_to_rules.py \
    --out /app/data/rules.json \
    --build-rag

# Verify rules.json exists
ls -la data/rules.json

# Check ChromaDB data
ls -la out/chromadb_data/
```

**ChromaDB data lost after rebuild:**

If ChromaDB appears empty after `docker-compose down` and rebuild:

1. **Verify the data directory exists:**
   ```bash
   ls -la out/chromadb_data/
   ```

2. **Check ChromaDB logs for errors:**
   ```bash
   docker-compose logs chromadb | grep -i persist
   ```

3. **Verify volume mount:**
   ```bash
   docker inspect flyfun-chromadb | grep -A 10 Mounts
   ```

4. **Check directory permissions:**
   ```bash
   # Ensure directory is writable
   chmod -R 777 out/chromadb_data
   # Or use proper ownership
   chown -R 2000:2000 out/chromadb_data
   ```

5. **Verify environment variables:**
   ```bash
   docker exec flyfun-chromadb env | grep -i persist
   # Should show: IS_PERSISTENT=TRUE and PERSIST_DIRECTORY=/chroma/chroma
   ```

6. **If data is truly lost, rebuild:**
   ```bash
   docker exec -it flyfun-web-server python /app/tools/xls_to_rules.py \
       --out /app/data/rules.json \
       --build-rag
   ```

**Note:** ChromaDB data should persist automatically. If it doesn't, check that:
- The `out/chromadb_data/` directory exists on the host
- The directory has proper permissions (writable by the container)
- You're not using `docker-compose down -v` (which removes volumes)

### Airport Data Not Showing

**If API works but UI doesn't update:**
1. Open browser DevTools (F12)
2. Check Console tab for JavaScript errors
3. Check Network tab - verify API calls return 200 status
4. Verify model loaded: `docker-compose logs web-server | grep "Loaded model"`
5. Test API directly: `curl http://localhost:8000/api/airports/EGLL`

**If API doesn't work:**
- Check if database exists: `docker exec flyfun-web-server ls -la /app/data/airports.db`
- Check logs: `docker-compose logs web-server --tail=50`
- Verify CORS settings in `security_config.py`

### Port Conflicts

**Web server port (8000) in use:**
```bash
# Change in .env
WEB_PORT=8001
# Then restart: docker-compose up -d
```

**ChromaDB port (8001) in use:**
```bash
# Change in .env
CHROMADB_PORT=8002
# Then restart: docker-compose up -d
```

### Build Failures

```bash
# Rebuild without cache
docker-compose build --no-cache

# Check specific service logs
docker-compose build web-server 2>&1 | tee build.log
```

### Permission Errors

Containers run as non-root (UID 2000/2001):

```bash
# Check container user
docker exec flyfun-web-server id

# Fix permissions on writable directories
chmod 777 out logs
# Or: chown -R 2000:2000 out logs
```

### Services Not Communicating

```bash
# Check network
docker network inspect flyfun-network

# Verify service names resolve
docker exec flyfun-web-server ping chromadb

# Check internal URLs (use service names, not localhost)
docker exec flyfun-web-server curl http://chromadb:8000/api/v1/heartbeat
```

---

## Quick Reference

### Common Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart service
docker-compose restart web-server

# View logs
docker-compose logs -f web-server

# Execute command in container
docker exec -it flyfun-web-server bash

# Check status
docker-compose ps

# Health check
curl http://localhost:8000/health
```

### Directory Structure

```
.
├── data/              # Read-only: airports.db, rules.json, ga_persona.db
├── out/               # Writable: chromadb_data/
├── logs/              # Writable: application logs
├── .env               # Environment configuration
└── docker-compose.yml # Service orchestration
```

### Volume Mappings

| Host | Container | Purpose |
|------|-----------|---------|
| `./data` | `/app/data` | Data files (read-only) |
| `./out` | `/app/out` | Output files (read-write) |
| `./logs` | `/app/logs` | Log files (read-write) |
| `./tools` | `/app/tools` | Utility scripts (read-only) |
| `./out/chromadb_data` | `/chroma/chroma` | ChromaDB storage |

---

## Additional Resources

- Reverse proxy setup: See "Production Deployment" section for nginx configuration
- Development workflow: Mount source code as volumes for live reload (development only)
- Health checks: `http://localhost:8000/health` for web server status
