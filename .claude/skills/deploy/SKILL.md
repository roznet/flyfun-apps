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
5. If `requirements.txt` or `Dockerfile.base` changed, check every pin resolves
   on a clean copy of the base image's `FROM` (no Docker cache involved):
   ```
   docker run --rm -v "$PWD/requirements.txt:/r.txt:ro" python:3.13-slim \
     pip install --no-cache-dir --dry-run -r /r.txt
   ```
   It must end with `Would install …`. An error like `No matching
   distribution found` means the base build will fail on the server — fix the
   pin first. (CI runs the same check on PRs: `.github/workflows/requirements.yml`.)
6. Ask the user to confirm before proceeding

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
| `Dockerfile.base`, `requirements.txt`, or rzflight/euro_aip changes | **Base image rebuild** (steps 4–6: build base, `./verify-base-image.sh`, then build services, then recreate) |
| `web/`, `shared/`, `mcp_server/`, `configs/` | **Service rebuild** (`docker compose build web-server` and/or `mcp-server`) |
| `tools/`, `.env`, `security_config.py` | **Restart only** (`docker compose restart web-server`) |
| `data/rules.json` or rules Excel files | **RAG rebuild** needed after deploy |
| Only docs, tests, `.claude/`, or non-deployed files | **No rebuild needed** — just pull |

Tell the user what will be rebuilt and why.

## Deploy steps

Every remote command below runs under `set -euo pipefail` and each phase is its
own `ssh` call: **stop at the first failure** and go to [Rollback](#rollback).
Never pipe build output through `tail`/`head` without `pipefail` — the pipeline
then reports the exit status of `tail`, and a failed build looks like success.
Never chain the base build into the service builds with `&&` in one shot: a
failed base build leaves the old `flyfun-base:latest` in place, the services
build fine on it, and then crash-loop on the flyfun-common startup guard.

1. Push to remote: `git push origin main`

2. Record the commit currently deployed (needed for rollback) and tag the
   running images as `:prev`. Do this **before** pulling or building:
   ```
   ssh <user>@<server> 'set -euo pipefail; cd flyfun-apps
     git rev-parse HEAD
     for img in flyfun-base flyfun-web-server flyfun-mcp-server; do
       if docker image inspect "$img:latest" >/dev/null 2>&1; then
         docker tag "$img:latest" "$img:prev"
       else
         echo "MISSING $img:latest"
       fi
     done
     docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep -E "^flyfun-(base|web-server|mcp-server):(latest|prev) "'
   ```
   Note the printed commit as `<prev_commit>`. If `flyfun-base:latest` is
   reported `MISSING` (it may have been pruned), say so: there is no base to roll back to,
   and the base **must** be built in step 4.

3. Pull. The checkout may be on a detached HEAD after a rollback, so check out
   `main` first:
   ```
   ssh <user>@<server> 'set -euo pipefail; cd flyfun-apps && git checkout main && git pull --ff-only && git rev-parse HEAD'
   ```

4. **Base image** (only if the scope needs a base rebuild, or the base is
   missing). Build it as its own step and stop if it fails:
   ```
   ssh <user>@<server> 'set -euo pipefail; cd flyfun-apps && docker compose build --no-cache base'
   ```
   Then verify the new base **before** building any service:
   ```
   ssh <user>@<server> 'set -euo pipefail; cd flyfun-apps && ./verify-base-image.sh'
   ```
   `verify-base-image.sh` checks that `flyfun-base:latest` carries this
   checkout's `requirements.txt` (so it really is the new build) and that every
   requirement — including `flyfun-common>=…` that the startup guard enforces —
   is satisfied in it, printing the installed flyfun-common version. If either
   step fails, **stop**: nothing has been recreated yet, so prod is untouched.
   A failed build leaves the old `flyfun-base:latest` in place; if the build
   succeeded but verification failed, retag `flyfun-base:prev` to `:latest`.
   Then run `git checkout <prev_commit>` so the checkout matches what is
   running, and report back with the build/verify output.

5. **Build the services** (skip for restart-only scope). Build both when the
   base was rebuilt; otherwise only those whose code changed:
   ```
   ssh <user>@<server> 'set -euo pipefail; cd flyfun-apps && docker compose build web-server mcp-server'
   ```

6. **Only then recreate**, without letting compose build anything implicitly:
   ```
   ssh <user>@<server> 'set -euo pipefail; cd flyfun-apps && docker compose up -d --no-build web-server mcp-server'
   ```
   If only a restart is needed: `docker compose restart web-server`.

7. If RAG rebuild is needed (rules.json changed):
   ```
   ssh <user>@<server> "docker exec -it flyfun-web-server python /app/tools/xls_to_rules.py --out /app/data/rules.json --build-rag"
   ```

8. Wait ~40 s (the healthcheck `start_period`), then verify. Both containers
   must be `running` and not restarting, and the web server healthy:
   ```
   ssh <user>@<server> "docker inspect --format='{{.Name}} {{.State.Status}} restarts={{.RestartCount}} health={{if .State.Health}}{{.State.Health.Status}}{{end}}' flyfun-web-server flyfun-mcp-server"
   curl -s -o /dev/null -w '%{http_code}' https://maps.flyfun.aero/health
   ```
   Anything other than `running`, `restarts=0`, web `healthy` and HTTP `200`
   → check the logs (below) and, unless the fix is immediate, roll back.

## Rollback

Restores the images tagged `:prev` in step 2 and the previous checkout. No
build is involved, so it works even when the base cannot be built:
```
ssh <user>@<server> 'set -euo pipefail; cd flyfun-apps
  for img in flyfun-base flyfun-web-server flyfun-mcp-server; do
    docker tag "$img:prev" "$img:latest"
  done
  git checkout <prev_commit>
  docker compose up -d --no-build --force-recreate web-server mcp-server'
```
Then re-run the checks in step 8. The checkout is left on a detached HEAD at
`<prev_commit>`; the next deploy must `git checkout main` before `git pull`.

## If something goes wrong

- Check logs: `ssh <user>@<server> "docker logs --tail 50 flyfun-web-server"`
- Check ChromaDB: `ssh <user>@<server> "docker logs --tail 20 flyfun-chromadb"`
- The web container runs on port 8000 internally, exposed via `WEB_PORT` (default 8000)
- ChromaDB runs on port 8000 internally, exposed on host port 8001
- `docker compose` (v2 syntax, NOT `docker-compose`)
- Containers: `flyfun-web-server`, `flyfun-mcp-server`, `flyfun-chromadb`
