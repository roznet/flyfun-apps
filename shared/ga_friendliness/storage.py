"""
Storage operations for ga_meta.sqlite with transaction support.

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
    Handles all database operations for ga_meta.sqlite.
    
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
        self.conn = get_connection(db_path, readonly=readonly)
        self._lock = threading.Lock()
        self._in_transaction = False
    
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
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
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
            try:
                self.conn.execute("""
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
                    self.conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write airfield stats: {e}")

    def get_airfield_stats(self, icao: str) -> Optional[AirportStats]:
        """Read stats for a single airport."""
        try:
            cursor = self.conn.execute(
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
            cursor = self.conn.execute(
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
                self.conn.execute(
                    "DELETE FROM ga_review_ner_tags WHERE icao = ?", (icao,)
                )

                # Insert new tags
                for extraction in tags:
                    for aspect_label in extraction.aspects:
                        self.conn.execute("""
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
                    self.conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write review tags: {e}")

    def write_review_tags_batch(
        self, tags_by_icao: Dict[str, List[ReviewExtraction]]
    ) -> None:
        """Write tags for multiple airports in a single transaction."""
        self._check_readonly()
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()

                for icao, extractions in tags_by_icao.items():
                    # Delete existing tags for this icao
                    self.conn.execute(
                        "DELETE FROM ga_review_ner_tags WHERE icao = ?", (icao,)
                    )

                    # Insert new tags
                    for extraction in extractions:
                        for aspect_label in extraction.aspects:
                            self.conn.execute("""
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
                    self.conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write review tags batch: {e}")

    def get_processed_review_ids(self, icao: str) -> Set[str]:
        """Get set of review_ids already processed for this airport."""
        try:
            cursor = self.conn.execute(
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
                self.conn.execute("""
                    INSERT OR REPLACE INTO ga_review_summary 
                    (icao, summary_text, tags_json, last_updated_utc)
                    VALUES (?, ?, ?, ?)
                """, (icao, summary_text, json.dumps(tags_json), now))

                if not self._in_transaction:
                    self.conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write review summary: {e}")

    # --- Meta Info Operations ---

    def write_meta_info(self, key: str, value: str) -> None:
        """Write to ga_meta_info table."""
        self._check_readonly()
        with self._lock:
            try:
                self.conn.execute("""
                    INSERT OR REPLACE INTO ga_meta_info (key, value)
                    VALUES (?, ?)
                """, (key, value))

                if not self._in_transaction:
                    self.conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write meta info: {e}")

    def get_meta_info(self, key: str) -> Optional[str]:
        """Read from ga_meta_info table."""
        try:
            cursor = self.conn.execute(
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
                self.conn.execute(
                    "DELETE FROM ga_notification_requirements WHERE icao = ?", (icao,)
                )

                # Insert new rules
                for rule in rules:
                    self.conn.execute("""
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
                    self.conn.commit()
            except sqlite3.Error as e:
                raise StorageError(f"Failed to write notification requirements: {e}")

    def write_aip_rule_summary(self, icao: str, summary: RuleSummary) -> None:
        """Insert or update ga_aip_rule_summary."""
        self._check_readonly()
        with self._lock:
            try:
                now = datetime.now(timezone.utc).isoformat()
                self.conn.execute("""
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
                    self.conn.commit()
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
            cursor = self.conn.execute("""
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

