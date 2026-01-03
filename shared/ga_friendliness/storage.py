"""
Storage operations for GA persona database with transaction support.

Provides all CRUD operations for the GA friendliness database.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .database import get_connection
from .exceptions import StorageError
from .interfaces import StorageInterface
from .models import (
    AirportStats,
    NotificationRule,
    RawReview,
    ReviewExtraction,
    RuleSummary,
)


def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO format timestamp string to datetime.
    
    Handles both timezone-aware and naive timestamps.
    Returns timezone-naive datetime in UTC for comparison purposes.
    """
    # Try Python's built-in fromisoformat first (handles most ISO formats)
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        # Convert to naive UTC for consistent comparison
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        pass

    # Fall back to manual parsing for edge cases
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse timestamp: {timestamp_str}")


class GAMetaStorage(StorageInterface):
    """
    Handles all database operations for GA persona database.
    
    Supports:
        - Transaction management (context manager)
        - Thread-safe operations
        - Batch writes for efficiency
        - Resource cleanup
        - Read-only mode for production use
    """

    def __init__(self, db_path: Path, readonly: bool = False):
        """
        Initialize storage.
        
        Creates database and schema if needed (unless readonly=True).
        Ensures schema is at current version.
        
        Args:
            db_path: Path to database file
            readonly: If True, open in read-only mode (no writes allowed)
        """
        self.db_path = db_path
        self.readonly = readonly
        # get_connection() uses check_same_thread=False for read-only mode,
        # so a single shared connection is safe across threads for reads
        self.conn = get_connection(db_path, readonly=readonly)
        self._lock = threading.Lock()
        self._in_transaction = False
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection (same connection for all operations)."""
        if self.conn is None:
            raise StorageError("Database connection has been closed")
        return self.conn
    
    def _check_readonly(self) -> None:
        """Raise error if attempting write operation in readonly mode."""
        if self.readonly:
            raise StorageError("Cannot perform write operation in readonly mode")

    def __enter__(self) -> "GAMetaStorage":
        """Context manager entry: begin transaction."""
        self._in_transaction = True
        return self

    def __exit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> None:
        """Context manager exit: commit or rollback."""
        conn = self._get_connection()
        if exc_type is None:
            conn.commit()
        else:
            conn.rollback()
        self._in_transaction = False

    def close(self) -> None:
        """Close database connection and cleanup resources."""
        if self.conn:
            self.conn.close()
            self.conn = None

    # --- Airport Stats Operations ---

    def write_airfield_stats(self, stats: AirportStats) -> None:
        """Insert or update a row in ga_airfield_stats."""
        self._check_readonly()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO ga_airfield_stats (
                        icao, rating_avg, rating_count, last_review_utc,
                        fee_band_0_749kg, fee_band_750_1199kg, fee_band_1200_1499kg,
                        fee_band_1500_1999kg, fee_band_2000_3999kg, fee_band_4000_plus_kg,
                        fee_currency, fee_last_updated_utc,
                        aip_ifr_available, aip_night_available,
                        aip_hotel_info, aip_restaurant_info,
                        review_cost_score, review_hassle_score, review_review_score,
                        review_ops_ifr_score, review_ops_vfr_score, review_access_score,
                        review_fun_score, review_hospitality_score,
                        aip_ops_ifr_score, aip_hospitality_score,
                        source_version, scoring_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    stats.icao,
                    stats.rating_avg,
                    stats.rating_count,
                    stats.last_review_utc,
                    stats.fee_band_0_749kg,
                    stats.fee_band_750_1199kg,
                    stats.fee_band_1200_1499kg,
                    stats.fee_band_1500_1999kg,
                    stats.fee_band_2000_3999kg,
                    stats.fee_band_4000_plus_kg,
                    stats.fee_currency,
                    stats.fee_last_updated_utc,
                    stats.aip_ifr_available,
                    stats.aip_night_available,
                    stats.aip_hotel_info,
                    stats.aip_restaurant_info,
                    stats.review_cost_score,
                    stats.review_hassle_score,
                    stats.review_review_score,
                    stats.review_ops_ifr_score,
                    stats.review_ops_vfr_score,
                    stats.review_access_score,
                    stats.review_fun_score,
                    stats.review_hospitality_score,
                    stats.aip_ops_ifr_score,
                    stats.aip_hospitality_score,
                    stats.source_version,
                    stats.scoring_version,
                ))
                if not self._in_transaction:
                    conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write airfield stats: {e}")

    def get_airfield_stats(self, icao: str) -> Optional[AirportStats]:
        """Read stats for a single airport."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM ga_airfield_stats WHERE icao = ?", (icao,)
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return AirportStats(
                icao=row["icao"],
                rating_avg=row["rating_avg"],
                rating_count=row["rating_count"] or 0,
                last_review_utc=row["last_review_utc"],
                fee_band_0_749kg=row["fee_band_0_749kg"],
                fee_band_750_1199kg=row["fee_band_750_1199kg"],
                fee_band_1200_1499kg=row["fee_band_1200_1499kg"],
                fee_band_1500_1999kg=row["fee_band_1500_1999kg"],
                fee_band_2000_3999kg=row["fee_band_2000_3999kg"],
                fee_band_4000_plus_kg=row["fee_band_4000_plus_kg"],
                fee_currency=row["fee_currency"],
                fee_last_updated_utc=row["fee_last_updated_utc"],
                aip_ifr_available=row["aip_ifr_available"] or 0,
                aip_night_available=row["aip_night_available"] or 0,
                aip_hotel_info=row["aip_hotel_info"],
                aip_restaurant_info=row["aip_restaurant_info"],
                review_cost_score=row["review_cost_score"],
                review_hassle_score=row["review_hassle_score"],
                review_review_score=row["review_review_score"],
                review_ops_ifr_score=row["review_ops_ifr_score"],
                review_ops_vfr_score=row["review_ops_vfr_score"],
                review_access_score=row["review_access_score"],
                review_fun_score=row["review_fun_score"],
                review_hospitality_score=row["review_hospitality_score"],
                aip_ops_ifr_score=row["aip_ops_ifr_score"],
                aip_hospitality_score=row["aip_hospitality_score"],
                source_version=row["source_version"] or "unknown",
                scoring_version=row["scoring_version"] or "unknown",
            )
        except sqlite3.Error as e:
            raise StorageError(f"Failed to read airfield stats: {e}")

    def get_all_icaos(self) -> List[str]:
        """Get list of all ICAOs in ga_airfield_stats."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT icao FROM ga_airfield_stats ORDER BY icao"
            )
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to get ICAOs: {e}")

    # --- Review Tags Operations ---

    def write_review_tags(self, icao: str, tags: List[ReviewExtraction]) -> None:
        """Write review tags to ga_review_ner_tags."""
        self._check_readonly()
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()

                # Delete existing tags for this icao
                conn = self._get_connection()
                conn.execute(
                    "DELETE FROM ga_review_ner_tags WHERE icao = ?", (icao,)
                )

                # Insert new tags
                for extraction in tags:
                    for aspect_label in extraction.aspects:
                        conn.execute("""
                            INSERT INTO ga_review_ner_tags
                            (icao, review_id, aspect, label, confidence, timestamp, created_utc)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            icao,
                            extraction.review_id,
                            aspect_label.aspect,
                            aspect_label.label,
                            aspect_label.confidence,
                            extraction.timestamp,
                            now,
                        ))

                if not self._in_transaction:
                    conn = self._get_connection()
                conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write review tags: {e}")

    def write_review_tags_batch(
        self, tags_by_icao: Dict[str, List[ReviewExtraction]]
    ) -> None:
        """Write tags for multiple airports in a single transaction."""
        self._check_readonly()
        with self._lock:
            conn = self._get_connection()
            try:
                now = datetime.now(timezone.utc).isoformat()

                for icao, extractions in tags_by_icao.items():
                    # Delete existing tags for this icao
                    conn.execute(
                        "DELETE FROM ga_review_ner_tags WHERE icao = ?", (icao,)
                    )

                    # Insert new tags
                    for extraction in extractions:
                        for aspect_label in extraction.aspects:
                            conn.execute("""
                                INSERT INTO ga_review_ner_tags 
                                (icao, review_id, aspect, label, confidence, timestamp, created_utc)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                icao,
                                extraction.review_id,
                                aspect_label.aspect,
                                aspect_label.label,
                                aspect_label.confidence,
                                extraction.timestamp,
                                now,
                            ))

                if not self._in_transaction:
                    conn = self._get_connection()
                conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write review tags batch: {e}")

    def get_processed_review_ids(self, icao: str) -> Set[str]:
        """Get set of review_ids already processed for this airport."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT DISTINCT review_id FROM ga_review_ner_tags WHERE icao = ? AND review_id IS NOT NULL",
                (icao,)
            )
            return {row[0] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            raise StorageError(f"Failed to get processed review IDs: {e}")

    # --- Review Summary Operations ---

    def write_review_summary(
        self, icao: str, summary_text: str, tags_json: List[str]
    ) -> None:
        """Insert or update ga_review_summary for an airport."""
        self._check_readonly()
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()
                conn = self._get_connection()
                conn.execute("""
                    INSERT OR REPLACE INTO ga_review_summary 
                    (icao, summary_text, tags_json, last_updated_utc)
                    VALUES (?, ?, ?, ?)
                """, (icao, summary_text, json.dumps(tags_json), now))

                if not self._in_transaction:
                    conn = self._get_connection()
                conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write review summary: {e}")

    # --- Meta Info Operations ---

    def write_meta_info(self, key: str, value: str) -> None:
        """Write to ga_meta_info table."""
        self._check_readonly()
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute("""
                    INSERT OR REPLACE INTO ga_meta_info (key, value)
                    VALUES (?, ?)
                """, (key, value))

                if not self._in_transaction:
                    conn = self._get_connection()
                conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write meta info: {e}")

    def get_meta_info(self, key: str) -> Optional[str]:
        """Read from ga_meta_info table."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT value FROM ga_meta_info WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            raise StorageError(f"Failed to read meta info: {e}")

    def get_last_processed_timestamp(self, icao: str) -> Optional[datetime]:
        """Get when airport was last processed."""
        key = f"last_processed_{icao}"
        value = self.get_meta_info(key)
        if value:
            try:
                return parse_timestamp(value)
            except ValueError:
                return None
        return None

    def update_last_processed_timestamp(
        self, icao: str, timestamp: datetime
    ) -> None:
        """Update last processed timestamp for an airport."""
        self._check_readonly()
        key = f"last_processed_{icao}"
        self.write_meta_info(key, timestamp.isoformat())

    # --- Change Detection ---

    def has_changes(
        self, icao: str, reviews: List[RawReview], since: Optional[datetime] = None
    ) -> bool:
        """Check if airport has new/changed reviews."""
        # Get last processed timestamp
        last_processed = self.get_last_processed_timestamp(icao)
        if last_processed is None:
            return True  # Never processed

        # Get already processed review_ids
        processed_ids = self.get_processed_review_ids(icao)

        # Filter reviews by since date if provided
        if since:
            filtered_reviews = []
            for r in reviews:
                if r.timestamp:
                    try:
                        review_time = parse_timestamp(r.timestamp)
                        if review_time > since:
                            filtered_reviews.append(r)
                    except ValueError:
                        # Invalid timestamp, include review
                        filtered_reviews.append(r)
                else:
                    # No timestamp, include if ID is new
                    if r.review_id and r.review_id not in processed_ids:
                        filtered_reviews.append(r)
            reviews = filtered_reviews

        # Check for new reviews (review_id not in processed_ids)
        for review in reviews:
            if review.review_id and review.review_id not in processed_ids:
                return True  # New review found

        # Check for updated reviews (same ID but newer timestamp)
        for review in reviews:
            if review.review_id in processed_ids and review.timestamp:
                try:
                    review_time = parse_timestamp(review.timestamp)
                    if review_time > last_processed:
                        return True  # Review was updated
                except ValueError:
                    return True  # Invalid timestamp, treat as potentially updated

        # Check for deleted reviews
        if processed_ids:
            source_review_ids = {r.review_id for r in reviews if r.review_id}
            deleted_ids = processed_ids - source_review_ids
            if deleted_ids:
                return True  # Reviews were deleted

        return False  # No changes detected

    def has_fee_changes(
        self, icao: str, fee_data: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Check if airport fees have changed.
        
        Args:
            icao: Airport ICAO code
            fee_data: Fee data dict with 'fees_last_changed' and 'bands', or None
            
        Returns:
            True if fees have changed or if airport has no fee data but new data is available
        """
        # Get current fee data from database
        current_stats = self.get_airfield_stats(icao)
        if current_stats is None:
            # Airport not in database, treat as change
            return fee_data is not None
        
        # If no new fee data, no change
        if fee_data is None:
            return False
        
        # Compare fees_last_changed timestamps
        new_fees_changed = fee_data.get("fees_last_changed")
        current_fees_changed = current_stats.fee_last_updated_utc
        
        # If new data has timestamp but current doesn't, it's a change
        if new_fees_changed and not current_fees_changed:
            return True
        
        # If both have timestamps, compare them
        if new_fees_changed and current_fees_changed:
            try:
                new_time = parse_timestamp(new_fees_changed)
                current_time = parse_timestamp(current_fees_changed)
                if new_time > current_time:
                    return True
            except ValueError:
                # Invalid timestamp, compare fee values directly
                pass
        
        # Compare fee band values (in case timestamps are missing or equal)
        new_bands = fee_data.get("bands", {})
        if not new_bands:
            return False  # No new fee data
        
        # Check if any fee band values differ
        current_bands = {
            "fee_band_0_749kg": current_stats.fee_band_0_749kg,
            "fee_band_750_1199kg": current_stats.fee_band_750_1199kg,
            "fee_band_1200_1499kg": current_stats.fee_band_1200_1499kg,
            "fee_band_1500_1999kg": current_stats.fee_band_1500_1999kg,
            "fee_band_2000_3999kg": current_stats.fee_band_2000_3999kg,
            "fee_band_4000_plus_kg": current_stats.fee_band_4000_plus_kg,
        }
        
        for band_name, new_value in new_bands.items():
            current_value = current_bands.get(band_name)
            # Compare with small epsilon for floating point comparison
            if abs((new_value or 0.0) - (current_value or 0.0)) > 0.01:
                return True
        
        # Check currency change
        new_currency = fee_data.get("currency", "EUR")
        current_currency = current_stats.fee_currency or "EUR"
        if new_currency != current_currency:
            return True
        
        return False  # No fee changes detected

    def update_fees_only(
        self, icao: str, fee_data: Dict[str, Any]
    ) -> None:
        """
        Update only fee data for an airport without processing reviews.
        
        Args:
            icao: Airport ICAO code
            fee_data: Fee data dict with 'currency', 'fees_last_changed', and 'bands'
        """
        self._check_readonly()
        
        # Get current stats to preserve other fields
        current_stats = self.get_airfield_stats(icao)
        if current_stats is None:
            raise StorageError(f"Cannot update fees for {icao}: airport not in database")
        
        # Update only fee-related fields
        fee_bands = fee_data.get("bands", {})
        fee_currency = fee_data.get("currency", "EUR")
        fee_last_updated = fee_data.get("fees_last_changed")
        
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute("""
                    UPDATE ga_airfield_stats SET
                        fee_band_0_749kg = ?,
                        fee_band_750_1199kg = ?,
                        fee_band_1200_1499kg = ?,
                        fee_band_1500_1999kg = ?,
                        fee_band_2000_3999kg = ?,
                        fee_band_4000_plus_kg = ?,
                        fee_currency = ?,
                        fee_last_updated_utc = ?
                    WHERE icao = ?
                """, (
                    fee_bands.get("fee_band_0_749kg"),
                    fee_bands.get("fee_band_750_1199kg"),
                    fee_bands.get("fee_band_1200_1499kg"),
                    fee_bands.get("fee_band_1500_1999kg"),
                    fee_bands.get("fee_band_2000_3999kg"),
                    fee_bands.get("fee_band_4000_plus_kg"),
                    fee_currency,
                    fee_last_updated,
                    icao,
                ))
                
                if not self._in_transaction:
                    conn = self._get_connection()
                conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to update fees for {icao}: {e}")

    def upsert_aip_only(
        self,
        icao: str,
        aip_ifr_available: int,
        aip_night_available: int,
        aip_hotel_info: Optional[int],
        aip_restaurant_info: Optional[int],
        aip_ops_ifr_score: Optional[float],
        aip_hospitality_score: Optional[float],
    ) -> bool:
        """
        Update or insert only AIP-derived fields for an airport.

        Works for airports not yet in ga_airfield_stats (creates minimal entry).
        Does not touch review-derived fields.

        Args:
            icao: Airport ICAO code
            aip_ifr_available: IFR availability (0-2)
            aip_night_available: Night ops availability (0-2)
            aip_hotel_info: Hotel info (-1=unknown, 0=none, 1=vicinity, 2=at_airport)
            aip_restaurant_info: Restaurant info (-1=unknown, 0=none, 1=vicinity, 2=at_airport)
            aip_ops_ifr_score: Computed IFR score (0-1)
            aip_hospitality_score: Computed hospitality score (0-1)

        Returns:
            True if inserted (new airport), False if updated (existing)
        """
        self._check_readonly()

        with self._lock:
            try:
                conn = self._get_connection()

                # Check if airport exists
                cursor = conn.execute(
                    "SELECT 1 FROM ga_airfield_stats WHERE icao = ?", (icao,)
                )
                exists = cursor.fetchone() is not None

                if exists:
                    # Update only AIP fields
                    conn.execute("""
                        UPDATE ga_airfield_stats SET
                            aip_ifr_available = ?,
                            aip_night_available = ?,
                            aip_hotel_info = ?,
                            aip_restaurant_info = ?,
                            aip_ops_ifr_score = ?,
                            aip_hospitality_score = ?
                        WHERE icao = ?
                    """, (
                        aip_ifr_available,
                        aip_night_available,
                        aip_hotel_info,
                        aip_restaurant_info,
                        aip_ops_ifr_score,
                        aip_hospitality_score,
                        icao,
                    ))
                else:
                    # Insert minimal entry with only AIP fields
                    conn.execute("""
                        INSERT INTO ga_airfield_stats (
                            icao,
                            aip_ifr_available,
                            aip_night_available,
                            aip_hotel_info,
                            aip_restaurant_info,
                            aip_ops_ifr_score,
                            aip_hospitality_score
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        icao,
                        aip_ifr_available,
                        aip_night_available,
                        aip_hotel_info,
                        aip_restaurant_info,
                        aip_ops_ifr_score,
                        aip_hospitality_score,
                    ))

                if not self._in_transaction:
                    conn.commit()

                return not exists

            except sqlite3.Error as e:
                raise StorageError(f"Failed to upsert AIP data for {icao}: {e}")

    # --- Resume Support ---

    def get_last_successful_icao(self) -> Optional[str]:
        """Get last successfully processed ICAO code (for resume)."""
        return self.get_meta_info("last_successful_icao")

    def set_last_successful_icao(self, icao: str) -> None:
        """Set last successfully processed ICAO code."""
        self._check_readonly()
        self.write_meta_info("last_successful_icao", icao)

    # --- AIP Rules Operations ---

    def write_notification_requirements(
        self, icao: str, rules: List[NotificationRule]
    ) -> None:
        """Write notification requirements to ga_notification_requirements."""
        self._check_readonly()
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()

                # Delete existing rules for this icao
                conn = self._get_connection()
                conn.execute(
                    "DELETE FROM ga_notification_requirements WHERE icao = ?", (icao,)
                )

                # Insert new rules
                for rule in rules:
                    conn.execute("""
                        INSERT INTO ga_notification_requirements (
                            icao, rule_type, weekday_start, weekday_end,
                            notification_hours, notification_type, specific_time,
                            business_day_offset, is_obligatory, includes_holidays,
                            schengen_only, non_schengen_only, conditions_json,
                            source_field, source_section, source_std_field_id,
                            aip_entry_id, confidence, created_utc, updated_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        icao,
                        rule.rule_type,
                        rule.weekday_start,
                        rule.weekday_end,
                        rule.notification_hours,
                        rule.notification_type,
                        rule.specific_time,
                        rule.business_day_offset,
                        1 if rule.is_obligatory else 0,
                        1 if rule.includes_holidays else 0,
                        1 if rule.schengen_only else 0,
                        1 if rule.non_schengen_only else 0,
                        json.dumps(rule.conditions) if rule.conditions else None,
                        rule.source_field,
                        rule.source_section,
                        rule.source_std_field_id,
                        rule.aip_entry_id,
                        rule.confidence,
                        now,
                        now,
                    ))

                if not self._in_transaction:
                    conn = self._get_connection()
                conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write notification requirements: {e}")

    def write_aip_rule_summary(self, icao: str, summary: RuleSummary) -> None:
        """Insert or update ga_aip_rule_summary."""
        self._check_readonly()
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()
                conn = self._get_connection()
                conn.execute("""
                    INSERT OR REPLACE INTO ga_aip_rule_summary 
                    (icao, notification_summary, hassle_level, notification_score, last_updated_utc)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    icao,
                    summary.notification_summary,
                    summary.hassle_level,
                    summary.notification_score,
                    now,
                ))

                if not self._in_transaction:
                    conn = self._get_connection()
                conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write AIP rule summary: {e}")


    def get_last_aip_processed_timestamp(self, icao: str) -> Optional[datetime]:
        """Get when AIP rules were last processed for this airport."""
        key = f"last_aip_processed_{icao}"
        value = self.get_meta_info(key)
        if value:
            try:
                return parse_timestamp(value)
            except ValueError:
                return None
        return None

    def update_last_aip_processed_timestamp(
        self, icao: str, timestamp: datetime
    ) -> None:
        """Update last processed timestamp for AIP rules."""
        self._check_readonly()
        key = f"last_aip_processed_{icao}"
        self.write_meta_info(key, timestamp.isoformat())

    # --- Global Priors ---

    def compute_global_priors(self) -> Dict[str, float]:
        """Compute global average scores across all airports."""
        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT
                    AVG(review_cost_score) as review_cost_score,
                    AVG(review_hassle_score) as review_hassle_score,
                    AVG(review_review_score) as review_review_score,
                    AVG(review_ops_ifr_score) as review_ops_ifr_score,
                    AVG(review_ops_vfr_score) as review_ops_vfr_score,
                    AVG(review_access_score) as review_access_score,
                    AVG(review_fun_score) as review_fun_score,
                    AVG(review_hospitality_score) as review_hospitality_score,
                    AVG(aip_ops_ifr_score) as aip_ops_ifr_score,
                    AVG(aip_hospitality_score) as aip_hospitality_score
                FROM ga_airfield_stats
                WHERE review_cost_score IS NOT NULL
            """)
            row = cursor.fetchone()

            # Default to 0.5 for any NULL values
            return {
                "review_cost_score": row["review_cost_score"] or 0.5,
                "review_hassle_score": row["review_hassle_score"] or 0.5,
                "review_review_score": row["review_review_score"] or 0.5,
                "review_ops_ifr_score": row["review_ops_ifr_score"] or 0.5,
                "review_ops_vfr_score": row["review_ops_vfr_score"] or 0.5,
                "review_access_score": row["review_access_score"] or 0.5,
                "review_fun_score": row["review_fun_score"] or 0.5,
                "review_hospitality_score": row["review_hospitality_score"] or 0.5,
                "aip_ops_ifr_score": row["aip_ops_ifr_score"] or 0.5,
                "aip_hospitality_score": row["aip_hospitality_score"] or 0.5,
            }
        except sqlite3.Error as e:
            raise StorageError(f"Failed to compute global priors: {e}")

    def store_global_priors(self, priors: Dict[str, float]) -> None:
        """Store computed global priors in ga_meta_info."""
        self._check_readonly()
        self.write_meta_info("global_priors", json.dumps(priors))

    def get_global_priors(self) -> Optional[Dict[str, float]]:
        """Get stored global priors from ga_meta_info."""
        value = self.get_meta_info("global_priors")
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    def get_icaos_by_hospitality(
        self,
        hotel: Optional[str] = None,
        restaurant: Optional[str] = None,
    ) -> Set[str]:
        """
        Get set of ICAOs matching hospitality filter criteria.

        Filter semantics:
            - "at_airport": Most restrictive, only value 2
            - "vicinity": Less restrictive, includes both vicinity (1) AND at_airport (2)
            - "any": Same as "vicinity" (backwards compatibility)

        Args:
            hotel: "at_airport", "vicinity", "any", or None (no filter)
            restaurant: "at_airport", "vicinity", "any", or None (no filter)

        Returns:
            Set of matching ICAO codes. Returns empty set if no filters specified.
        """
        if hotel is None and restaurant is None:
            return set()  # No filter

        conditions = []

        # Database: -1=unknown, 0=none, 1=vicinity, 2=at_airport
        # "vicinity" includes at_airport (>= 1), "at_airport" is exact (= 2)

        if hotel is not None:
            if hotel == "at_airport":
                conditions.append("aip_hotel_info = 2")
            elif hotel in ("vicinity", "any"):
                # vicinity includes at_airport (value >= 1)
                conditions.append("aip_hotel_info >= 1")

        if restaurant is not None:
            if restaurant == "at_airport":
                conditions.append("aip_restaurant_info = 2")
            elif restaurant in ("vicinity", "any"):
                # vicinity includes at_airport (value >= 1)
                conditions.append("aip_restaurant_info >= 1")

        if not conditions:
            return set()

        query = f"""
            SELECT icao FROM ga_airfield_stats
            WHERE {' AND '.join(conditions)}
        """

        try:
            conn = self._get_connection()
            cursor = conn.execute(query, ())
            return {row["icao"] for row in cursor}
        except sqlite3.Error as e:
            raise StorageError(f"Failed to query hospitality filters: {e}")

