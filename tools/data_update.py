#!/usr/bin/env python3
"""
FlyFun Data Update Script

Consolidates all data update commands for different update schedules:
  - initial:    Full build from scratch (run once on new setup)
  - web:        Fetch AIP from web sources (France, UK, Norway) → syncs derived data
  - autorouter: Fetch AIP from autorouter for given countries → syncs derived data
  - aip:        Sync all AIP-derived data (notifications, hospitality fields)
  - reviews:    Update GA friendliness from reviews (run weekly/monthly)

Usage:
    python tools/data_update.py initial           # Full initial build
    python tools/data_update.py web               # Fetch web sources + sync derived
    python tools/data_update.py autorouter ED LO  # Fetch autorouter + sync derived
    python tools/data_update.py aip               # Sync AIP-derived data only
    python tools/data_update.py reviews           # Update reviews/GA friendliness

Environment:
    Set OPENAI_API_KEY for LLM-based review processing
    Set AIRPORTS_DB to override default database path
"""

import argparse
import gzip
import json
import logging
import os
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent

# Database paths
AIRPORTS_DB = Path(os.environ.get("AIRPORTS_DB", PROJECT_ROOT / "data" / "airports.db"))
GA_PERSONA_DB = PROJECT_ROOT / "data" / "ga_persona.db"
GA_NOTIFICATIONS_DB = PROJECT_ROOT / "data" / "ga_notifications.db"
WORLDAIRPORTS_DB = PROJECT_ROOT / "data" / "world_airports.db"

# Airfield.directory export (for reviews) - intermediate files in tmp/
AIRFIELD_EXPORT_URL = "https://airfield-directory-pirep-export.s3.amazonaws.com/airfield-directory-pireps-export-latest.json.gz"
AIRFIELD_EXPORT_RAW = PROJECT_ROOT / "tmp" / "airfield_export_raw.json.gz"
AIRFIELD_EXPORT = PROJECT_ROOT / "tmp" / "airfield_export.json"

# Cache directory
CACHE_DIR = PROJECT_ROOT / "cache"

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def log_section(title: str) -> None:
    """Print a section header."""
    print()
    print("=" * 64)
    print(f" {title}")
    print("=" * 64)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    logger.info(f"Running: {' '.join(args)}")
    return subprocess.run(args, cwd=PROJECT_ROOT, check=check)


def ensure_directories() -> None:
    """Ensure required directories exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    AIRPORTS_DB.parent.mkdir(parents=True, exist_ok=True)
    AIRFIELD_EXPORT.parent.mkdir(parents=True, exist_ok=True)


def download_reviews() -> bool:
    """Download latest airfield.directory PIREPs and filter for human-only reviews."""
    log_section("Downloading Airfield.directory Reviews")

    # Download latest export
    logger.info(f"Downloading from: {AIRFIELD_EXPORT_URL}")
    try:
        urllib.request.urlretrieve(AIRFIELD_EXPORT_URL, AIRFIELD_EXPORT_RAW)
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False

    if not AIRFIELD_EXPORT_RAW.exists():
        logger.error("Download failed - file not created")
        return False

    size_mb = AIRFIELD_EXPORT_RAW.stat().st_size / (1024 * 1024)
    logger.info(f"Downloaded: {size_mb:.1f} MB")

    # Filter out AI-generated PIREPs, keep only human reviews
    logger.info("Filtering for human-only reviews (ai_generated != true)...")

    try:
        with gzip.open(AIRFIELD_EXPORT_RAW, "rt", encoding="utf-8") as f:
            data = json.load(f)

        # Filter: keep only reviews where ai_generated is not true
        filtered_pireps = {}
        for airport_id, reviews in data.get("pireps", {}).items():
            human_reviews = {
                review_id: review
                for review_id, review in reviews.items()
                if not review.get("ai_generated", False)
            }
            if human_reviews:
                filtered_pireps[airport_id] = human_reviews

        filtered_data = {"pireps": filtered_pireps}

        with open(AIRFIELD_EXPORT, "w", encoding="utf-8") as f:
            json.dump(filtered_data, f)

    except Exception as e:
        logger.error(f"Filtering failed: {e}")
        return False

    if not AIRFIELD_EXPORT.exists() or AIRFIELD_EXPORT.stat().st_size == 0:
        logger.error("Filtering failed or produced empty output")
        return False

    # Count airports and reviews
    airport_count = len(filtered_pireps)
    review_count = sum(len(reviews) for reviews in filtered_pireps.values())

    logger.info(f"Filtered export: {airport_count} airports, {review_count} human reviews")
    logger.info(f"Saved to: {AIRFIELD_EXPORT}")

    return True


# =============================================================================
# UPDATE FUNCTIONS
# =============================================================================


def fetch_web_sources() -> None:
    """Fetch AIP data from web sources (France, UK, Norway)."""
    log_section("Fetching AIP from Web Sources")

    args = ["python", "tools/aipexport.py"]

    # If database exists, use it as base
    if AIRPORTS_DB.exists():
        logger.info(f"Using existing database as base: {AIRPORTS_DB}")
        args.extend(["--database", str(AIRPORTS_DB)])

    # Enable web sources (France, UK, Norway)
    args.extend(["--france-web", "--uk-web", "--norway-web"])

    # WorldAirports for metadata enrichment
    if WORLDAIRPORTS_DB.exists():
        args.extend([
            "--worldairports",
            "--worldairports-db", str(WORLDAIRPORTS_DB),
            "--worldairports-filter", "required",
        ])

    # Output to database
    args.extend(["--database-storage", str(AIRPORTS_DB)])

    # Cache directory
    args.extend(["-c", str(CACHE_DIR)])

    run_command(args)
    logger.info("Web sources fetch complete")

    # Show recent changes
    log_section("Recent AIP Changes")
    try:
        run_command(
            ["python", "tools/aipchange.py", "--since", "today", "--summary"],
            check=False,
        )
    except Exception:
        logger.info("No changes to display")


def update_reviews() -> None:
    """Update GA friendliness from reviews."""
    log_section("Updating GA Friendliness / Reviews")

    # Step 1: Download latest reviews
    if not download_reviews():
        raise RuntimeError("Failed to download reviews")

    args = ["python", "tools/build_ga_friendliness.py"]

    # Output database
    args.extend(["--output", str(GA_PERSONA_DB)])

    # Use airports.db for AIP-derived fields
    if AIRPORTS_DB.exists():
        args.extend(["--airports-db", str(AIRPORTS_DB)])

    # Source: the filtered human-only export
    if AIRFIELD_EXPORT.exists():
        logger.info(f"Using filtered export file: {AIRFIELD_EXPORT}")
        args.extend(["--export", str(AIRFIELD_EXPORT)])
    else:
        raise RuntimeError("Download/filtering failed - no export file available")

    # Incremental mode: skip already-processed airports
    args.append("--incremental")

    # Cache directory
    args.extend(["--cache-dir", str(CACHE_DIR / "ga_friendliness")])

    run_command(args)
    logger.info("Reviews update complete")


def update_aip_fields_only() -> None:
    """Fast update: only AIP-derived fields in ga_persona.db."""
    log_section("Updating AIP Fields in GA Persona DB")

    if not AIRPORTS_DB.exists():
        raise RuntimeError(f"airports.db not found: {AIRPORTS_DB}")

    args = [
        "python", "tools/build_ga_friendliness.py",
        "--aip-only",
        "--airports-db", str(AIRPORTS_DB),
        "--output", str(GA_PERSONA_DB),
    ]

    run_command(args)
    logger.info("AIP fields update complete")


def sync_aip_derived(prefixes: list[str] = None, full: bool = False) -> None:
    """Sync all AIP-derived data: notifications and hospitality fields.

    This should be called after any AIP data update (web or autorouter).

    Args:
        prefixes: Optional list of ICAO prefixes to limit sync scope.
        full: If True, do full rebuild (for initial setup). Default uses --changed mode.
    """
    log_section("Syncing AIP-Derived Data")

    if not AIRPORTS_DB.exists():
        raise RuntimeError(f"airports.db not found: {AIRPORTS_DB}")

    # 1. Update notification requirements
    update_notifications(prefixes=prefixes, full=full)

    # 2. Update AIP-derived fields in ga_persona.db (hospitality, etc.)
    if GA_PERSONA_DB.exists():
        update_aip_fields_only()

    logger.info("AIP-derived data sync complete")


def run_autorouter(prefixes: list[str]) -> None:
    """Run autorouter on all airports with AIP entries matching given prefixes."""
    if not prefixes:
        print("Usage: autorouter <icao_prefix> [prefix2] [prefix3] ...")
        print("Example: autorouter ED           (for Germany)")
        print("Example: autorouter ED LO EB LE  (multiple countries)")
        print()
        print("Common prefixes:")
        print("  ED - Germany    EG - UK        EH - Netherlands")
        print("  EI - Ireland    EL - Luxembourg EB - Belgium")
        print("  LF - France     LI - Italy     LS - Switzerland")
        print("  LO - Austria    LZ - Slovakia  LE - Spain")
        sys.exit(1)

    log_section(f"Running Autorouter for: {' '.join(prefixes)}")

    if not AIRPORTS_DB.exists():
        raise RuntimeError(f"airports.db not found: {AIRPORTS_DB}")

    # Build SQL query for all prefixes using parameterized queries
    placeholders = " OR ".join("airport_icao LIKE ?" for _ in prefixes)
    params = [f"{p}%" for p in prefixes]
    query = f"SELECT DISTINCT airport_icao FROM aip_entries WHERE {placeholders} ORDER BY airport_icao"

    # Query airports
    with sqlite3.connect(AIRPORTS_DB) as conn:
        cursor = conn.execute(query, params)
        airports = [row[0] for row in cursor.fetchall()]

    if not airports:
        raise RuntimeError(f"No airports found with AIP entries matching: {' '.join(prefixes)}")

    logger.info(f"Found {len(airports)} airports with AIP entries")

    # Build args for aipexport.py with autorouter
    args = [
        "python", "tools/aipexport.py",
        "--autorouter",
        "--database", str(AIRPORTS_DB),
        "--database-storage", str(AIRPORTS_DB),
        "-c", str(CACHE_DIR),
    ]

    # Add all airport ICAOs
    args.extend(airports)

    run_command(args)

    log_section("Autorouter Complete")
    logger.info(f"Processed: {len(airports)} airports")


def update_notifications(prefixes: list[str] = None, full: bool = False) -> None:
    """Update notification requirements from AIP data.

    Extracts structured notification rules (PPR, customs, immigration) from
    AIP text and stores in ga_notifications.db.

    Args:
        prefixes: Optional list of ICAO prefixes to process (e.g., ["LF", "EG"]).
                  If None, processes all airports with AIP data.
        full: If True, do full rebuild. If False (default), use --changed mode
              to only process airports where AIP text changed.
    """
    log_section("Updating GA Notification Requirements")

    if not AIRPORTS_DB.exists():
        raise RuntimeError(f"airports.db not found: {AIRPORTS_DB}")

    args = [
        "python", "tools/build_ga_notifications.py",
        "--airports-db", str(AIRPORTS_DB),
        "--output", str(GA_NOTIFICATIONS_DB),
    ]

    # Use --changed mode by default (smarter than --incremental)
    # Only use full mode when explicitly requested
    if not full:
        args.append("--changed")

    # Add prefix filter if specified
    if prefixes:
        args.extend(["--prefixes", ",".join(prefixes)])

    run_command(args)
    logger.info("Notification requirements update complete")


def initial_build() -> None:
    """Full initial build from scratch."""
    log_section("INITIAL BUILD - Full Setup")

    logger.info("This will build all data from scratch")
    logger.info("  - AIP data from France, UK, Norway web sources")
    logger.info("  - GA notification requirements")
    logger.info("  - GA friendliness database")

    # Step 1: Fetch AIP data from web sources
    fetch_web_sources()

    # Step 2: Sync all AIP-derived data (notifications, hospitality fields)
    sync_aip_derived(full=True)

    # Step 3: Build GA friendliness (subjective scoring from reviews)
    update_reviews()

    log_section("INITIAL BUILD COMPLETE")
    logger.info(f"Databases created:")
    logger.info(f"  - {AIRPORTS_DB}")
    logger.info(f"  - {GA_NOTIFICATIONS_DB}")
    logger.info(f"  - {GA_PERSONA_DB}")


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FlyFun Data Update Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  initial       Full build from scratch (first time setup)
  web           Fetch AIP from web sources (FR, UK, NO) → syncs derived data
  autorouter    Fetch AIP from autorouter for countries → syncs derived data
  aip           Sync all AIP-derived data (notifications, hospitality fields)
  reviews       Update GA friendliness/reviews (run weekly/monthly)
  notifications Update notification requirements only (subset of 'aip')

Examples:
  python tools/data_update.py initial
  python tools/data_update.py web                  # Fetch web + sync derived
  python tools/data_update.py autorouter ED LO     # Fetch autorouter + sync derived
  python tools/data_update.py aip                  # Sync all AIP-derived data
  python tools/data_update.py aip LF EG            # Sync for specific countries
  python tools/data_update.py reviews
  python tools/data_update.py notifications LF EG  # Notifications only
        """,
    )

    parser.add_argument(
        "mode",
        choices=["initial", "web", "autorouter", "aip", "reviews", "notifications"],
        help="Update mode to run",
    )
    parser.add_argument(
        "args",
        nargs="*",
        help="Additional arguments (e.g., ICAO prefixes for autorouter/aip/notifications)",
    )

    args = parser.parse_args()

    ensure_directories()

    if args.mode == "initial":
        initial_build()
    elif args.mode == "web":
        fetch_web_sources()
        sync_aip_derived()
    elif args.mode == "autorouter":
        run_autorouter(args.args)
        # Sync derived data for the same prefixes
        if args.args:
            sync_aip_derived(prefixes=args.args)
    elif args.mode == "aip":
        # Sync all AIP-derived data (optional prefix filter)
        sync_aip_derived(prefixes=args.args if args.args else None)
    elif args.mode == "reviews":
        update_reviews()
    elif args.mode == "notifications":
        # Optional prefixes for filtering (e.g., "LF" for France)
        update_notifications(args.args if args.args else None)


if __name__ == "__main__":
    main()
