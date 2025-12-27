# Caddy Configuration for Shared Infrastructure

This directory contains Caddy configuration files for the FlyFun services. These files are designed to be used with a shared Caddy server running on infrastructure separate from the application containers.

## Structure

```
etc/caddy/
├── Caddyfile                    # Main file that imports all services
├── sites-enabled/
│   ├── mcp.flyfun.aero.caddy    # MCP server configuration
│   └── maps.flyfun.aero.caddy   # Web server configuration
├── README.md                     # This file
└── SECURITY.md                  # Security considerations
```

## Integration with Shared Caddy Server

To use these configurations on your shared infrastructure Caddy server:

### Option 1: Import into Main Caddyfile

Add to your shared server's main Caddyfile:

```caddyfile
# Import FlyFun service configurations
import /path/to/flyfun-apps/rules/etc/caddy/sites-enabled/*.caddy
```

### Option 2: Symlink or Copy

1. **Symlink approach** (recommended for development):
   ```bash
   ln -s /path/to/flyfun-apps/rules/etc/caddy/sites-enabled/*.caddy /etc/caddy/sites-enabled/
   ```

2. **Copy approach** (for production):
   ```bash
   cp /path/to/flyfun-apps/rules/etc/caddy/sites-enabled/*.caddy /etc/caddy/sites-enabled/
   ```

### Option 3: Mount Individual Files in Docker (Recommended for Modular Setup)

If your shared Caddy server runs in Docker, you can mount individual Caddyfiles. This allows you to:
- Pick and choose which services to include
- Combine Caddyfiles from multiple repositories
- Update individual services independently

**Example docker-compose.yml for shared Caddy server:**

```yaml
services:
  caddy:
    image: caddy:latest
    volumes:
      # Main Caddyfile that imports all service configs
      - /path/to/shared-infra/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      # Individual FlyFun service Caddyfiles
      - /path/to/flyfun-apps/rules/etc/caddy/sites-enabled/mcp.flyfun.aero.caddy:/etc/caddy/sites-enabled/mcp.flyfun.aero.caddy:ro
      - /path/to/flyfun-apps/rules/etc/caddy/sites-enabled/maps.flyfun.aero.caddy:/etc/caddy/sites-enabled/maps.flyfun.aero.caddy:ro
      # Other repositories can add their Caddyfiles here too
      # - /path/to/other-repo/etc/caddy/sites-enabled/service.caddy:/etc/caddy/sites-enabled/service.caddy:ro
      # Caddy data (certificates)
      - caddy_data:/data
      - caddy_config:/config
    ports:
      - "80:80"
      - "443:443"
```

**Main Caddyfile on shared server (`/path/to/shared-infra/caddy/Caddyfile`):**

```caddyfile
# Import all service configurations from sites-enabled
import /etc/caddy/sites-enabled/*.caddy
```

This approach allows multiple repositories to contribute their Caddyfiles without conflicts.

### Option 4: Mount Directory (Alternative)

If you prefer mounting the entire directory:

```yaml
volumes:
  - /path/to/flyfun-apps/rules/etc/caddy/sites-enabled:/etc/caddy/sites-enabled:ro
```

**Note:** With directory mounting, ensure file names don't conflict across repositories. Using individual file mounts (Option 3) gives better control.

## Service Endpoints

The Caddyfiles currently reference Docker service names:
- **MCP Server**: `mcp-server:8001`
- **Web Server**: `web-server:8000`

### Network Considerations

Since Caddy runs on a shared infrastructure server (not in the Docker network), you have two options:

#### Option 1: Update Caddyfiles to use Docker host (Recommended)

If your shared Caddy server can reach the Docker host, update the reverse_proxy targets:

**In `sites-enabled/mcp.flyfun.aero.caddy`:**
```caddyfile
reverse_proxy <docker-host-ip-or-hostname>:8001
```

**In `sites-enabled/maps.flyfun.aero.caddy`:**
```caddyfile
reverse_proxy <docker-host-ip-or-hostname>:8000
```

Replace `<docker-host-ip-or-hostname>` with:
- The IP address of the Docker host
- A hostname that resolves to the Docker host
- `localhost` if Caddy runs on the same machine as Docker

#### Option 2: Use Docker service names (if Caddy is in Docker network)

If your shared Caddy server is also running in Docker and can join the `flyfun-network`, you can keep the service names as-is. This requires:
- Caddy container to be on the same Docker network
- Network configuration to allow inter-container communication

### Port Mappings

The docker-compose.yml exposes:
- **MCP Server**: Port `8001` (configurable via `MCP_PORT` env var)
- **Web Server**: Port `8000` (configurable via `WEB_PORT` env var)

Ensure these ports are accessible from your shared infrastructure server (firewall rules, etc.).

## Domains Configured

- `mcp.flyfun.aero` - MCP server endpoint
- `maps.flyfun.aero` - Web application

## DNS Requirements

Ensure DNS records point to your shared infrastructure server:
- `mcp.flyfun.aero` → Shared server IP
- `maps.flyfun.aero` → Shared server IP

Caddy will automatically obtain Let's Encrypt certificates for these domains.

## Updating Configurations

When you update these Caddyfiles:

1. Commit changes to the repository
2. On the shared infrastructure server:
   - If using symlinks: `caddy reload` (picks up changes automatically)
   - If using copies: Copy new files and `caddy reload`
   - If using imports: `caddy reload` (if Caddy watches the directory)

## Testing

To test the configuration locally before deploying:

```bash
# Validate syntax
caddy validate --config /path/to/etc/caddy/Caddyfile

# Test configuration
caddy run --config /path/to/etc/caddy/Caddyfile
```

