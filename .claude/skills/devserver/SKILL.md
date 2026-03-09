---
name: devserver
description: Start or restart the local dev server (backend + frontend) in a tmux session
disable-model-invocation: true
---

# Local dev server management

Manage the `flyfun-apps` tmux session that runs the FastAPI backend and Vite frontend dev server.

**Ports**: Backend 8010, Frontend 3010 (offset from flyfun-weather which uses 8000/3000).

## Step 1 — Determine the project root

Figure out the correct project root (`PROJECT_ROOT`):
- Use the current working directory
- If we are in a git worktree (`.git` is a file not a directory), the working directory IS the project root for that worktree

## Step 2 — Resolve the venv

- If `$PROJECT_ROOT/venv/` exists, use it
- Otherwise check `$PROJECT_ROOT/../main/venv/` (worktree case sharing main's venv)
- If neither exists, tell the user and stop

Store the resolved path as `VENV_PATH`.

## Step 3 — Check for .env file

- If `$PROJECT_ROOT/.env` exists, good — nothing to do
- If it does NOT exist, check if `$PROJECT_ROOT/../main/.env` exists (worktree case)
  - If found, copy it: `cp ../main/.env $PROJECT_ROOT/.env`
  - Tell the user it was copied
- If neither exists, warn the user that the `.env` file is missing and the server will likely fail to start

## Step 4 — Check for existing tmux session

Run: `tmux has-session -t flyfun-apps 2>/dev/null`

If a session exists:
1. Check what directory it's running in: `tmux display-message -t flyfun-apps -p '#{pane_current_path}'`
2. Compare that path to `$PROJECT_ROOT`
3. **If the directory matches** and the session looks healthy, tell the user:
   > Dev server already running at http://localhost:3010 — attach with `tmux attach -t flyfun-apps`

   Then stop (no restart needed).
4. **If the directory does NOT match** (e.g., switched worktrees), kill the session:
   ```
   tmux kill-session -t flyfun-apps
   ```
   Then continue to Step 5 to create a fresh one.

## Step 5 — Start the tmux session

Create a new tmux session with two panes:

```bash
# Create detached session — pane 0 runs the backend
tmux new-session -d -s flyfun-apps -c "$PROJECT_ROOT"

# Pane 0: backend (FastAPI with reload on port 8010)
tmux send-keys -t flyfun-apps "source $VENV_PATH/bin/activate && cd web/server && PORT=8010 python main.py" Enter

# Create pane 1 (vertical split) for the frontend watcher
tmux split-window -h -t flyfun-apps -c "$PROJECT_ROOT/web/client"
tmux send-keys -t flyfun-apps "BACKEND_PORT=8010 npm run dev -- --port 3010" Enter
```

## Step 6 — Report to user

Tell the user:
- Frontend running at **http://localhost:3010** (with API proxy to backend)
- Backend running at **http://localhost:8010**
- Attach to tmux with: `tmux attach -t flyfun-apps`
- Pane 0 = backend (uvicorn with --reload), Pane 1 = frontend (Vite dev server)

## Notes

- The `.env` file is loaded automatically by the app (shared.env_loader), no need to source it manually
- `uvicorn --reload` watches for Python file changes automatically
- Vite dev server provides HMR for TypeScript changes
- The Vite proxy target is configured via `BACKEND_PORT` env var (defaults to 8010 in vite.config.ts)
- Production uses port 8000 (docker), dev uses port 8010
- flyfun-weather uses ports 8000/3000, so these are offset to avoid clashes
