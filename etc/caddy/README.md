# Caddy Configuration

Caddy reverse proxy configuration for FlyFun services. Designed for a shared Caddy server outside this compose project. In production that's its own Docker container with host networking, so the `localhost` upstreams reach the ports published on the host.

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

Production doesn't deploy from here. The live site files are in the private `digitalocean` repo, `flyfun.aero/etc/caddy/sites-enabled/`, so copy any change there, commit and push, then on the droplet:

```bash
cd ~/digitalocean && git pull && shared-infra/caddy/reload.sh
```

## DNS

Point these domains to your server:
- `maps.flyfun.aero`
- `mcp.flyfun.aero`

Caddy handles HTTPS certificates automatically via Let's Encrypt.
