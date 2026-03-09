---
name: deploy
description: Deploy the flyfun-apps web app to production on maps.flyfun.aero
disable-model-invocation: true
---

# Deploy flyfun-apps to production

Use the SSH user and server IP for flyfun.aero deployment from user config.
The project directory on the server is `flyfun-apps`.

## Pre-flight checks

1. Ensure the working tree is clean (`git status`)
2. Ensure we are on the `main` branch
3. Show the commits that will be deployed: `git log --oneline origin/main..HEAD`
4. **Check what changed** to determine rebuild scope (see below)
5. Ask the user to confirm before proceeding

## Determine rebuild scope

Get the commit currently deployed on the server:
```
ssh <user>@<server> "cd flyfun-apps && git rev-parse HEAD"
```

Then check what files changed between that commit and local HEAD:
```
git diff --name-only <server_commit>..HEAD
```

Classify the changes:

| Changed files | Action needed |
|---|---|
| `Dockerfile.base`, `requirements.txt`, or rzflight/euro_aip changes | **Base image rebuild** (`docker compose build --no-cache base` then rebuild services) |
| `web/`, `shared/`, `mcp_server/`, `configs/` | **Service rebuild** (`docker compose build web-server` and/or `mcp-server`) |
| `tools/`, `.env`, `security_config.py` | **Restart only** (`docker compose restart web-server`) |
| `data/rules.json` or rules Excel files | **RAG rebuild** needed after deploy |
| Only docs, tests, `.claude/`, or non-deployed files | **No rebuild needed** — just pull |

Tell the user what will be rebuilt and why.

## Deploy steps

1. Push to remote: `git push origin main`
2. SSH to the server and pull:
   ```
   ssh <user>@<server> "cd flyfun-apps && git pull"
   ```
3. **Before rebuilding**, check if `flyfun-base` image exists (it may have been pruned):
   ```
   ssh <user>@<server> "docker images --format '{{.Repository}}:{{.Tag}}' | grep flyfun-base || echo 'MISSING'"
   ```
   If missing, build it first: `ssh <user>@<server> "cd flyfun-apps && docker compose build base"`

4. Rebuild based on scope determined above. The most common case (code changes):
   ```
   ssh <user>@<server> "cd flyfun-apps && docker compose build web-server && docker compose up -d web-server"
   ```

   If base image rebuild is needed (requirements.txt, euro_aip changes):
   ```
   ssh <user>@<server> "cd flyfun-apps && docker compose build --no-cache base && docker compose build web-server mcp-server && docker compose up -d"
   ```

   If only restart needed:
   ```
   ssh <user>@<server> "cd flyfun-apps && docker compose restart web-server"
   ```

5. If RAG rebuild is needed (rules.json changed):
   ```
   ssh <user>@<server> "docker exec -it flyfun-web-server python /app/tools/xls_to_rules.py --out /app/data/rules.json --build-rag"
   ```

6. Wait a few seconds, then verify the health check:
   ```
   ssh <user>@<server> "docker inspect --format='{{.State.Health.Status}}' flyfun-web-server"
   ```

7. Also check the endpoint is responding:
   ```
   curl -s -o /dev/null -w '%{http_code}' https://maps.flyfun.aero/health
   ```

## If something goes wrong

- Check logs: `ssh <user>@<server> "docker logs --tail 50 flyfun-web-server"`
- Check ChromaDB: `ssh <user>@<server> "docker logs --tail 20 flyfun-chromadb"`
- The web container runs on port 8000 internally, exposed via `WEB_PORT` (default 8000)
- ChromaDB runs on port 8000 internally, exposed on host port 8001
- `docker compose` (v2 syntax, NOT `docker-compose`)
- Containers: `flyfun-web-server`, `flyfun-mcp-server`, `flyfun-chromadb`
