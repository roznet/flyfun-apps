# Caddy Configuration

Caddy reverse proxy configuration for FlyFun services. Designed for a shared Caddy server running on the host (not in Docker).

## Structure

```
etc/caddy/
├── Caddyfile                         # Main file (imports sites-enabled)
├── sites-enabled/
│   ├── maps.flyfun.aero.caddy        # Web app → localhost:8000
│   └── mcp.flyfun.aero.caddy         # MCP API → localhost:8002
└── validate.sh                       # Validation script
```

## Validation

```bash
./etc/caddy/validate.sh
```

Uses Docker if Caddy CLI isn't installed locally.

## Deployment

Copy or symlink to your Caddy server's config directory:

```bash
# Symlink (picks up changes automatically)
ln -s /path/to/etc/caddy/sites-enabled/*.caddy /etc/caddy/sites-enabled/

# Or import in your main Caddyfile
import /path/to/etc/caddy/sites-enabled/*.caddy
```

Then reload: `caddy reload`

## DNS

Point these domains to your server:
- `maps.flyfun.aero`
- `mcp.flyfun.aero`

Caddy handles HTTPS certificates automatically via Let's Encrypt.
