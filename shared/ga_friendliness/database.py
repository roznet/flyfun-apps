"""
SQLite schema and connection management for ga_meta.sqlite.

Handles schema creation, versioning, and migrations.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from .exceptions import StorageError

# Current schema version
SCHEMA_VERSION = "1.0"


def get_schema_version(conn: sqlite3.Connection) -> Optional[str]:
    """
    Get current schema version from database.
    
    Returns:
        Schema version string (e.g., "1.0") or None if not set.
    """
    try:
        cursor = conn.execute(
            "SELECT value FROM ga_meta_info WHERE key = 'schema_version'"
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        # Table doesn't exist
        return None


def create_schema(conn: sqlite3.Connection) -> None:
    """
    Create all tables in ga_meta.sqlite and set schema version.
    
    Tables:
        - ga_airfield_stats (main query table)
        - ga_landing_fees (optional detailed fees)
        - ga_review_ner_tags (structured review tags)
        - ga_review_summary (LLM-generated summaries)
        - ga_meta_info (versioning metadata)
        - ga_notification_requirements (AIP notification rules, optional)
        - ga_aip_rule_summary (AIP rule summaries, optional)
    """
    cursor = conn.cursor()

    # ga_meta_info - General metadata and build info
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ga_meta_info (
            key     TEXT PRIMARY KEY,
            value   TEXT
        )
    """)

    # ga_airfield_stats - Main query table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ga_airfield_stats (
            icao                TEXT PRIMARY KEY,
            
            -- Aggregate review info
            rating_avg          REAL,
            rating_count        INTEGER,
            last_review_utc     TEXT,
            
            -- Fee info (aggregated GA bands by MTOW ranges)
            fee_band_0_749kg    REAL,
            fee_band_750_1199kg REAL,
            fee_band_1200_1499kg REAL,
            fee_band_1500_1999kg REAL,
            fee_band_2000_3999kg REAL,
            fee_band_4000_plus_kg REAL,
            fee_currency        TEXT,
            fee_last_updated_utc TEXT,
            
            -- Binary/boolean-style flags and IFR capabilities
            mandatory_handling  INTEGER,
            ifr_procedure_available INTEGER,
            ifr_score           INTEGER,  -- 0=no IFR, 1=IFR permitted, 2=VOR/NDB, 3=RNP, 4=ILS
            night_available     INTEGER,
            
            -- AIP metadata (from airports.db)
            hotel_info          TEXT,
            restaurant_info     TEXT,
            
            -- Normalized feature scores (0.0-1.0)
            ga_cost_score       REAL,
            ga_review_score     REAL,
            ga_hassle_score     REAL,
            ga_ops_ifr_score    REAL,
            ga_ops_vfr_score    REAL,
            ga_access_score     REAL,
            ga_fun_score        REAL,
            ga_hospitality_score REAL,
            notification_hassle_score REAL,
            
            -- Persona-specific composite scores (denormalized cache; optional)
            score_ifr_touring   REAL,
            score_vfr_budget    REAL,
            score_training      REAL,
            
            -- Versioning / provenance
            source_version      TEXT,
            scoring_version     TEXT
        )
    """)

    # ga_landing_fees - Optional detailed fee grid
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ga_landing_fees (
            id              INTEGER PRIMARY KEY,
            icao            TEXT NOT NULL,
            mtow_min_kg     REAL,
            mtow_max_kg     REAL,
            operation_type  TEXT,
            amount          REAL,
            currency        TEXT,
            source          TEXT,
            valid_from_date TEXT,
            valid_to_date   TEXT
        )
    """)

    # ga_review_ner_tags - Structured review tags
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ga_review_ner_tags (
            id              INTEGER PRIMARY KEY,
            icao            TEXT NOT NULL,
            review_id       TEXT,
            aspect          TEXT,
            label           TEXT,
            confidence      REAL,
            timestamp       TEXT,
            created_utc     TEXT
        )
    """)

    # ga_review_summary - LLM-generated summaries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ga_review_summary (
            icao            TEXT PRIMARY KEY,
            summary_text    TEXT,
            tags_json       TEXT,
            last_updated_utc TEXT
        )
    """)

    # ga_notification_requirements - AIP notification rules (optional)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ga_notification_requirements (
            id                  INTEGER PRIMARY KEY,
            icao                TEXT NOT NULL,
            rule_type           TEXT NOT NULL,
            weekday_start       INTEGER,
            weekday_end         INTEGER,
            notification_hours  INTEGER,
            notification_type   TEXT NOT NULL,
            specific_time       TEXT,
            business_day_offset INTEGER,
            is_obligatory       INTEGER,
            includes_holidays   INTEGER,
            schengen_only       INTEGER,
            non_schengen_only   INTEGER,
            conditions_json     TEXT,
            raw_text            TEXT,
            source_field        TEXT,
            source_section      TEXT,
            source_std_field_id INTEGER,
            aip_entry_id        TEXT,
            confidence          REAL,
            created_utc         TEXT,
            updated_utc         TEXT
        )
    """)

    # ga_aip_rule_summary - AIP rule summaries (optional)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ga_aip_rule_summary (
            icao                TEXT PRIMARY KEY,
            notification_summary TEXT,
            hassle_level        TEXT,
            notification_score  REAL,
            last_updated_utc    TEXT
        )
    """)

    # Create indexes for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_landing_fees_icao 
        ON ga_landing_fees(icao)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_review_tags_icao 
        ON ga_review_ner_tags(icao)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_review_tags_icao_aspect 
        ON ga_review_ner_tags(icao, aspect)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_review_tags_icao_review_id 
        ON ga_review_ner_tags(icao, review_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notification_icao 
        ON ga_notification_requirements(icao)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notification_type 
        ON ga_notification_requirements(icao, rule_type)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notification_weekday 
        ON ga_notification_requirements(icao, weekday_start, weekday_end)
    """)

    # Set schema version
    cursor.execute("""
        INSERT OR REPLACE INTO ga_meta_info (key, value)
        VALUES ('schema_version', ?)
    """, (SCHEMA_VERSION,))

    conn.commit()


def migrate_schema(
    conn: sqlite3.Connection,
    from_version: str,
    to_version: str
) -> None:
    """
    Migrate schema from one version to another.
    
    Handles:
        - Adding new columns (ALTER TABLE ADD COLUMN)
        - Modifying existing columns (via table recreation if needed)
        - Data transformations if required
    
    Raises:
        StorageError: If migration fails.
    """
    # Define migration paths
    migrations = {
        # ("1.0", "1.1"): _migrate_1_0_to_1_1,
    }

    # Build migration path
    current = from_version
    while current != to_version:
        found = False
        for (start, end), migrate_fn in migrations.items():
            if start == current:
                try:
                    migrate_fn(conn)
                    current = end
                    found = True
                    break
                except Exception as e:
                    raise StorageError(
                        f"Migration from {start} to {end} failed: {e}"
                    )
        
        if not found:
            raise StorageError(
                f"No migration path from {current} to {to_version}"
            )

    # Update schema version
    conn.execute("""
        INSERT OR REPLACE INTO ga_meta_info (key, value)
        VALUES ('schema_version', ?)
    """, (to_version,))
    conn.commit()


def ensure_schema_version(conn: sqlite3.Connection) -> None:
    """
    Ensure database schema is at current version.
    
    If schema doesn't exist, creates it.
    If schema exists but is older version, migrates it.
    If schema is newer version, raises error.
    """
    current_version = get_schema_version(conn)

    if current_version is None:
        # No schema, create it
        create_schema(conn)
    elif current_version == SCHEMA_VERSION:
        # Schema is current, nothing to do
        pass
    elif current_version < SCHEMA_VERSION:
        # Schema is older, migrate
        migrate_schema(conn, current_version, SCHEMA_VERSION)
    else:
        # Schema is newer (shouldn't happen), raise error
        raise StorageError(
            f"Database schema version {current_version} is newer than "
            f"library version {SCHEMA_VERSION}. Please upgrade library."
        )


def get_connection(db_path: Path, readonly: bool = False) -> sqlite3.Connection:
    """
    Get a connection to ga_meta.sqlite.
    
    Creates the database and schema if it doesn't exist (unless readonly=True).
    Ensures schema is at current version.
    
    Args:
        db_path: Path to the database file
        readonly: If True, open in read-only mode (no schema checks/writes)
        
    Returns:
        Connection with schema at current version.
    """
    if readonly:
        # Read-only mode: database must exist
        if not db_path.exists():
            raise StorageError(f"Database not found (readonly mode): {db_path}")
        
        # Open with URI for read-only mode
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        
        # Set read-only pragma for safety
        conn.execute("PRAGMA query_only = ON")
        
        # No WAL mode or schema checks in read-only mode
        return conn
    
    # Write mode: create database and enable WAL for concurrent access
    # Create parent dirs if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create connection
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Set pragmas for better performance
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 30000")  # 30 seconds

    # Ensure schema is current
    ensure_schema_version(conn)

    return conn


def attach_euro_aip(
    conn: sqlite3.Connection, euro_aip_path: Path, alias: str = "aip"
) -> None:
    """
    ATTACH euro_aip.sqlite for joint queries.
    
    Usage:
        conn = get_connection(ga_meta_path)
        attach_euro_aip(conn, euro_aip_path)
        # Now can query: SELECT * FROM aip.airport JOIN ga_airfield_stats ...
    
    Args:
        conn: SQLite connection to ga_meta.sqlite
        euro_aip_path: Path to euro_aip.sqlite
        alias: Alias for attached database (default: 'aip')
    """
    if not euro_aip_path.exists():
        raise StorageError(f"euro_aip database not found: {euro_aip_path}")

    try:
        conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(euro_aip_path),))
    except sqlite3.Error as e:
        raise StorageError(f"Failed to attach euro_aip database: {e}")

