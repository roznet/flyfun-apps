#!/usr/bin/env python3

import sys
import os
from pathlib import Path
from typing import Optional

# Add the flyfun-apps package to the path (before importing shared)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load environment variables using shared loader
from shared.env_loader import load_component_env

# Load from component directory (e.g., web/server/dev.env)
component_dir = Path(__file__).parent
load_component_env(component_dir)

# Now continue with imports

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging
from datetime import datetime
import time

from flyfun_common.auth import create_auth_router, get_jwt_secret, is_dev_mode
from flyfun_common.db import init_shared_db, ensure_dev_user, get_engine, SessionLocal
from flyfun_common.db import current_user_id, get_db, UserRow

from euro_aip.models.euro_aip_model import EuroAipModel

# Import security configuration (values only)
from security_config import (
    ALLOWED_ORIGINS, ALLOWED_HOSTS, RATE_LIMIT_WINDOW, RATE_LIMIT_MAX_REQUESTS,
    FORCE_HTTPS, SECURITY_HEADERS, LOG_LEVEL, LOG_FORMAT
)

# Import API routes
from api import airports, procedures, filters, statistics, rules, aviation_agent_chat, ga_friendliness, notifications, briefing

from shared.tool_context import ToolContext

# Configure logging with file output (and optionally stderr for debugger)
# Use /app/logs in Docker, /tmp/flyfun-logs for local development
log_dir = Path(os.getenv("LOG_DIR", "/tmp/flyfun-logs"))
log_dir.mkdir(exist_ok=True, parents=True)
log_file = log_dir / "web_server.log"

# Create formatter
formatter = logging.Formatter(LOG_FORMAT)

# Create file handler
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL))

# Add file handler if not already added
if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file) for h in root_logger.handlers):
    root_logger.addHandler(file_handler)

# Optionally add stderr handler for debugger visibility
# Enable if LOG_TO_STDERR env var is set, or in development mode
log_to_stderr = os.getenv("LOG_TO_STDERR", "").lower() in ("1", "true", "yes")
if log_to_stderr:
    # Check if stderr handler already exists to avoid duplicates
    has_stderr_handler = any(
        isinstance(h, logging.StreamHandler) and h.stream == sys.stderr 
        for h in root_logger.handlers
    )
    if not has_stderr_handler:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(formatter)
        root_logger.addHandler(stderr_handler)

logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {log_file}")
if log_to_stderr:
    logger.info("Also logging to stderr for debugger visibility")

# Global ToolContext (created at startup)
_tool_context: Optional[ToolContext] = None

# Simple rate limiting storage (LRU-capped)
MAX_RATE_LIMIT_ENTRIES = 10000
request_counts = {}


def get_client_ip(request: Request) -> str:
    """Extract real client IP, accounting for reverse proxy headers."""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # First IP in the chain is the original client
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(client_ip: str) -> bool:
    """Simple rate limiting implementation."""
    global request_counts
    current_time = time.time()

    # Clean old entries
    request_counts = {ip: (count, timestamp) for ip, (count, timestamp) in request_counts.items()
                     if current_time - timestamp < RATE_LIMIT_WINDOW}

    # Evict oldest entries if too many tracked IPs
    if len(request_counts) >= MAX_RATE_LIMIT_ENTRIES:
        oldest = sorted(request_counts.items(), key=lambda x: x[1][1])[:len(request_counts) // 2]
        for ip, _ in oldest:
            del request_counts[ip]

    if client_ip not in request_counts:
        request_counts[client_ip] = (1, current_time)
        return True

    count, timestamp = request_counts[client_ip]

    if current_time - timestamp > RATE_LIMIT_WINDOW:
        request_counts[client_ip] = (1, current_time)
        return True

    if count >= RATE_LIMIT_MAX_REQUESTS:
        return False

    request_counts[client_ip] = (count + 1, timestamp)
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    global _tool_context
    
    # Startup
    logger.info("Starting up Euro AIP Airport Explorer...")

    # Initialize shared auth DB (users, api_tokens, chat_usage tables)
    import db.models  # noqa: F401 – register ChatUsageRow on Base.metadata
    engine = get_engine()
    env = os.getenv("ENVIRONMENT", "development")
    if env == "development":
        init_shared_db(engine)
        logger.info("Dev mode: shared DB tables created")
    if is_dev_mode():
        with SessionLocal() as session:
            ensure_dev_user(session)
        logger.info("Dev user ensured")

    try:
        # Create ToolContext with all services using centralized configuration
        logger.info("Initializing ToolContext with all services...")
        _tool_context = ToolContext.create(
            load_airports=True,
            load_rules=True,
            load_notifications=True,
            load_ga_friendliness=True
        )
        
        # Apply custom logic to model
        _tool_context.model.remove_airports_by_country("RU")
        logger.info(f"Loaded model with {_tool_context.model.airports.count()} airports")
        
        # All derived fields are now updated automatically in load_model()
        logger.info("Model loaded with all derived fields updated")
        
        # Make model available to API routes (extract from ToolContext)
        airports.set_model(_tool_context.model)
        procedures.set_model(_tool_context.model)
        filters.set_model(_tool_context.model)
        statistics.set_model(_tool_context.model)
        briefing.set_model(_tool_context.model)

        # Extract and distribute rules manager from ToolContext
        if _tool_context.rules_manager:
            # ToolContext.create() already calls load_rules(), but check anyway
            if not _tool_context.rules_manager.loaded:
                if not _tool_context.rules_manager.load_rules():
                    logger.warning("No rules loaded")
            rules.set_rules_manager(_tool_context.rules_manager)
            logger.info("Rules manager initialized")
        else:
            logger.warning("Rules manager not available")

        # Extract and distribute GA friendliness service
        # Wrap the base service in the web API wrapper class for API response models
        if _tool_context.ga_friendliness_service:
            from api.ga_friendliness import GAFriendlinessService as WebGAFriendlinessService
            # The web API wrapper extends the base service and adds methods that return API models
            web_ga_service = WebGAFriendlinessService(
                db_path=_tool_context.ga_friendliness_service.db_path,
                readonly=_tool_context.ga_friendliness_service.readonly
            )
            ga_friendliness.set_service(web_ga_service)
            if web_ga_service.enabled:
                logger.info("GA Friendliness service enabled (readonly)")
            else:
                logger.info("GA Friendliness service disabled")
        else:
            logger.info("GA Friendliness service not configured")
            ga_friendliness.set_service(None)

        # Extract and distribute notification service
        if _tool_context.notification_service:
            notifications.set_notification_service(_tool_context.notification_service)
            logger.info("Notification service initialized")
        else:
            logger.info("Notification service not available")
            # Set None explicitly so API knows it's not available (instead of lazy creation)

        logger.info("Application startup complete")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Euro AIP Airport Explorer...")
    # ToolContext and its services will be cleaned up automatically

# Create FastAPI app with lifespan context manager
app = FastAPI(
    title="Euro AIP Airport Explorer",
    description="Interactive web application for exploring European airport data",
    version="1.0.0",
    lifespan=lifespan
)

# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Add security headers
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    
    return response

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    client_ip = get_client_ip(request)
    logger.info(
        f"{request.method} {request.url.path} - "
        f"{response.status_code} - {process_time:.3f}s - {client_ip}"
    )
    return response

# Add rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = get_client_ip(request)

    if not check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."}
        )
    
    response = await call_next(request)
    return response

# Add security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=ALLOWED_HOSTS
)

# Force HTTPS in production
# Note: In Docker deployments, HTTPS termination happens at reverse proxy level
# Container should accept HTTP, so FORCE_HTTPS is typically False in Docker
if FORCE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware)

# Add CORS middleware with restricted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# SessionMiddleware is required for OAuth state to survive the Google redirect roundtrip
app.add_middleware(SessionMiddleware, secret_key=get_jwt_secret())

# Add exception handler for validation errors to log details
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors for debugging."""
    logger.warning(f"Validation error on {request.url.path}: {len(exc.errors())} error(s)")
    # Return validation errors without echoing back the request body
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# --- Auth routes ---
# Custom /auth/me registered BEFORE common router so it takes priority,
# returning app-specific fields (chat usage).
@app.get("/auth/me", tags=["auth"])
def auth_me(user_id: str = Depends(current_user_id), db=Depends(get_db)):
    """Return current user info with chat usage."""
    user = db.get(UserRow, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    from api.chat_usage import get_today_chat_count, DAILY_CHAT_LIMIT
    chat_count = get_today_chat_count(db, user_id)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.display_name,
        "approved": user.approved,
        "chat_usage": {"used": chat_count, "limit": DAILY_CHAT_LIMIT},
    }

@app.get("/auth/trial-status", tags=["auth"])
def trial_status(request: Request):
    """Return anonymous trial usage for unauthenticated users."""
    from api.chat_usage import ANON_COOKIE_NAME, ANON_DAILY_LIMIT, get_today_anon_count
    anon_id = request.cookies.get(ANON_COOKIE_NAME)
    if not anon_id:
        return {"used": 0, "limit": ANON_DAILY_LIMIT}
    db = SessionLocal()
    try:
        count = get_today_anon_count(db, anon_id)
        return {"used": count, "limit": ANON_DAILY_LIMIT}
    finally:
        db.close()

# Mount common auth router (login/google, callback/google, logout, providers)
app.include_router(create_auth_router())

# Include API routes
app.include_router(airports.router, prefix="/api/airports", tags=["airports"])
app.include_router(procedures.router, prefix="/api/procedures", tags=["procedures"])
app.include_router(filters.router, prefix="/api/filters", tags=["filters"])
app.include_router(statistics.router, prefix="/api/statistics", tags=["statistics"])
app.include_router(rules.router, prefix="/api/rules", tags=["rules"])
app.include_router(notifications.router)  # Has its own prefix /api/notifications

if aviation_agent_chat.feature_enabled():
    logger.info("Aviation agent router enabled at /api/aviation-agent")
    app.include_router(
        aviation_agent_chat.router,
        prefix="/api/aviation-agent",
        tags=["aviation-agent"],
    )
else:
    logger.info("Aviation agent router disabled (AVIATION_AGENT_ENABLED is false)")

# GA Friendliness API - always mount, graceful degradation if no DB
app.include_router(ga_friendliness.router, prefix="/api/ga", tags=["ga-friendliness"])

# Briefing API - parse ForeFlight PDFs and other briefing sources
app.include_router(briefing.router, prefix="/api/briefing", tags=["briefing"])

# Serve static files for client assets
client_dir = Path(__file__).parent.parent / "client"

# Debug logging to verify paths
logger.info(f"Client directory: {client_dir}")

# Add cache control middleware for development
@app.middleware("http")
async def add_cache_control_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Add cache control headers for JavaScript/TypeScript files in development
    if request.url.path.endswith(('.js', '.ts')):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    
    return response

# Mount static files
css_dir = os.path.join(client_dir, "css")
app.mount("/css", StaticFiles(directory=css_dir, html=True), name="css")

# Mount assets (logos, images)
assets_dir = client_dir / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    logger.info(f"Assets directory mounted: {assets_dir}")

# Mount TypeScript build output (for production)
ts_dist_dir = client_dir / "dist"
if ts_dist_dir.exists():
    app.mount("/dist", StaticFiles(directory=str(ts_dist_dir), html=True), name="dist")
    logger.info(f"TypeScript dist directory mounted: {ts_dist_dir}")

# Mount TypeScript source (for development - Vite handles this, but fallback)
ts_dir = client_dir / "ts"
if ts_dir.exists():
    app.mount("/ts", StaticFiles(directory=str(ts_dir), html=True), name="ts")
    logger.info(f"TypeScript source directory mounted: {ts_dir}")

@app.get("/")
async def read_root():
    """Serve the main HTML page."""
    html_file = client_dir / "index.html"
    return FileResponse(str(html_file))

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    # show environment variables
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
        log_level="info"
    ) 