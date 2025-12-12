"""
Unit tests for ga_friendliness storage operations.
"""

from datetime import datetime, timezone

import pytest

from shared.ga_friendliness import (
    GAMetaStorage,
    AirportStats,
    ReviewExtraction,
    AspectLabel,
    RuleSummary,
    NotificationRule,
    StorageError,
    parse_timestamp,
    SCHEMA_VERSION,
)


@pytest.mark.unit
class TestParseTimestamp:
    """Tests for parse_timestamp function."""

    def test_iso_with_milliseconds(self):
        """Test parsing ISO format with milliseconds."""
        result = parse_timestamp("2024-06-15T10:30:00.123Z")
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15

    def test_iso_without_milliseconds(self):
        """Test parsing ISO format without milliseconds."""
        result = parse_timestamp("2024-06-15T10:30:00Z")
        assert result.year == 2024

    def test_date_only(self):
        """Test parsing date only format."""
        result = parse_timestamp("2024-06-15")
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 15

    def test_invalid_format(self):
        """Test invalid format raises error."""
        with pytest.raises(ValueError, match="Unable to parse"):
            parse_timestamp("invalid date")


@pytest.mark.unit
class TestGAMetaStorage:
    """Tests for GAMetaStorage class."""

    def test_create_storage(self, temp_storage):
        """Test creating storage creates database."""
        assert temp_storage.conn is not None

    def test_schema_version(self, temp_storage):
        """Test schema version is set."""
        version = temp_storage.get_meta_info("schema_version")
        assert version == SCHEMA_VERSION


@pytest.mark.unit
class TestStorageAirfieldStats:
    """Tests for airfield stats operations."""

    def test_write_and_read_stats(self, temp_storage, sample_airport_stats):
        """Test writing and reading airport stats."""
        temp_storage.write_airfield_stats(sample_airport_stats)

        result = temp_storage.get_airfield_stats("EGKB")
        assert result is not None
        assert result.icao == "EGKB"
        assert result.rating_avg == 4.25
        assert result.review_cost_score == 0.65

    def test_upsert_stats(self, temp_storage, sample_airport_stats):
        """Test updating existing stats."""
        temp_storage.write_airfield_stats(sample_airport_stats)
        
        # Update rating
        updated = sample_airport_stats.model_copy(update={"rating_avg": 4.5})
        temp_storage.write_airfield_stats(updated)
        
        result = temp_storage.get_airfield_stats("EGKB")
        assert result.rating_avg == 4.5

    def test_get_nonexistent_stats(self, temp_storage):
        """Test getting stats for non-existent airport."""
        result = temp_storage.get_airfield_stats("XXXX")
        assert result is None

    def test_get_all_icaos(self, temp_storage, sample_airport_stats):
        """Test getting all ICAOs."""
        temp_storage.write_airfield_stats(sample_airport_stats)
        
        stats2 = sample_airport_stats.model_copy(update={"icao": "LFAT"})
        temp_storage.write_airfield_stats(stats2)
        
        icaos = temp_storage.get_all_icaos()
        assert "EGKB" in icaos
        assert "LFAT" in icaos


@pytest.mark.unit
class TestStorageReviewTags:
    """Tests for review tags operations."""

    def test_write_and_read_tags(self, temp_storage):
        """Test writing review tags."""
        extractions = [
            ReviewExtraction(
                review_id="r1",
                aspects=[
                    AspectLabel(aspect="cost", label="cheap", confidence=0.9),
                    AspectLabel(aspect="staff", label="positive", confidence=0.85),
                ],
            ),
            ReviewExtraction(
                review_id="r2",
                aspects=[
                    AspectLabel(aspect="cost", label="expensive", confidence=0.8),
                ],
            ),
        ]
        
        temp_storage.write_review_tags("EGKB", extractions)
        
        review_ids = temp_storage.get_processed_review_ids("EGKB")
        assert "r1" in review_ids
        assert "r2" in review_ids

    def test_overwrite_tags(self, temp_storage):
        """Test that write_review_tags overwrites existing tags."""
        # Write initial tags
        temp_storage.write_review_tags("EGKB", [
            ReviewExtraction(
                review_id="r1",
                aspects=[AspectLabel(aspect="cost", label="cheap", confidence=0.9)],
            ),
        ])
        
        # Overwrite with new tags
        temp_storage.write_review_tags("EGKB", [
            ReviewExtraction(
                review_id="r2",
                aspects=[AspectLabel(aspect="cost", label="expensive", confidence=0.8)],
            ),
        ])
        
        review_ids = temp_storage.get_processed_review_ids("EGKB")
        assert "r1" not in review_ids
        assert "r2" in review_ids


@pytest.mark.unit
class TestStorageReviewSummary:
    """Tests for review summary operations."""

    def test_write_summary(self, temp_storage):
        """Test writing review summary."""
        temp_storage.write_review_summary(
            "EGKB",
            "Great airfield with friendly staff.",
            ["GA friendly", "good restaurant"],
        )
        
        # Verify by querying directly
        cursor = temp_storage.conn.execute(
            "SELECT summary_text, tags_json FROM ga_review_summary WHERE icao = ?",
            ("EGKB",)
        )
        row = cursor.fetchone()
        assert row is not None
        assert "friendly staff" in row[0]


@pytest.mark.unit
class TestStorageMetaInfo:
    """Tests for meta info operations."""

    def test_write_and_read_meta(self, temp_storage):
        """Test writing and reading meta info."""
        temp_storage.write_meta_info("test_key", "test_value")
        
        result = temp_storage.get_meta_info("test_key")
        assert result == "test_value"

    def test_get_nonexistent_meta(self, temp_storage):
        """Test getting non-existent meta info."""
        result = temp_storage.get_meta_info("nonexistent")
        assert result is None

    def test_upsert_meta(self, temp_storage):
        """Test updating meta info."""
        temp_storage.write_meta_info("key", "value1")
        temp_storage.write_meta_info("key", "value2")
        
        result = temp_storage.get_meta_info("key")
        assert result == "value2"


@pytest.mark.unit
class TestStorageTimestamps:
    """Tests for timestamp tracking operations."""

    def test_last_processed_timestamp(self, temp_storage):
        """Test last processed timestamp tracking."""
        now = datetime.now(timezone.utc)
        temp_storage.update_last_processed_timestamp("EGKB", now)
        
        result = temp_storage.get_last_processed_timestamp("EGKB")
        assert result is not None
        # Compare within 1 second tolerance (for serialization roundtrip)
        # parse_timestamp returns naive UTC, so convert now to naive for comparison
        now_naive = now.replace(tzinfo=None)
        assert abs((result - now_naive).total_seconds()) < 1

    def test_last_aip_processed_timestamp(self, temp_storage):
        """Test last AIP processed timestamp tracking."""
        now = datetime.now(timezone.utc)
        temp_storage.update_last_aip_processed_timestamp("EGKB", now)
        
        result = temp_storage.get_last_aip_processed_timestamp("EGKB")
        assert result is not None


@pytest.mark.unit
class TestStorageResumeSupport:
    """Tests for resume support operations."""

    def test_last_successful_icao(self, temp_storage):
        """Test last successful ICAO tracking."""
        temp_storage.set_last_successful_icao("EGKB")
        
        result = temp_storage.get_last_successful_icao()
        assert result == "EGKB"

    def test_last_successful_icao_none(self, temp_storage):
        """Test getting last successful ICAO when not set."""
        result = temp_storage.get_last_successful_icao()
        assert result is None


@pytest.mark.unit
class TestStorageAIPRules:
    """Tests for AIP rules operations."""

    def test_write_notification_requirements(self, temp_storage):
        """Test writing notification requirements."""
        rules = [
            NotificationRule(
                rule_type="ppr",
                notification_hours=24,
                notification_type="hours",
                weekday_start=0,
                weekday_end=4,
                confidence=0.9,
            ),
            NotificationRule(
                rule_type="ppr",
                notification_hours=48,
                notification_type="hours",
                weekday_start=5,
                weekday_end=6,
                confidence=0.85,
            ),
        ]
        
        temp_storage.write_notification_requirements("EGKB", rules)
        
        # Verify by querying directly
        cursor = temp_storage.conn.execute(
            "SELECT COUNT(*) FROM ga_notification_requirements WHERE icao = ?",
            ("EGKB",)
        )
        count = cursor.fetchone()[0]
        assert count == 2

    def test_write_aip_rule_summary(self, temp_storage):
        """Test writing AIP rule summary."""
        summary = RuleSummary(
            notification_summary="24h weekdays, 48h weekends",
            hassle_level="moderate",
            notification_score=0.6,
        )
        
        temp_storage.write_aip_rule_summary("EGKB", summary)
        
        # Verify by querying directly
        cursor = temp_storage.conn.execute(
            "SELECT notification_summary, hassle_level FROM ga_aip_rule_summary WHERE icao = ?",
            ("EGKB",)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "24h weekdays, 48h weekends"


@pytest.mark.unit
class TestStorageGlobalPriors:
    """Tests for global priors operations."""

    def test_store_and_get_priors(self, temp_storage):
        """Test storing and retrieving global priors."""
        priors = {
            "ga_cost_score": 0.55,
            "ga_hassle_score": 0.60,
            "ga_review_score": 0.65,
        }
        
        temp_storage.store_global_priors(priors)
        
        result = temp_storage.get_global_priors()
        assert result is not None
        assert result["ga_cost_score"] == 0.55

    def test_get_priors_not_set(self, temp_storage):
        """Test getting priors when not set."""
        result = temp_storage.get_global_priors()
        assert result is None


@pytest.mark.unit
class TestStorageTransactions:
    """Tests for transaction management."""

    def test_context_manager_commit(self, temp_storage, sample_airport_stats):
        """Test context manager commits on success."""
        with temp_storage:
            temp_storage.write_airfield_stats(sample_airport_stats)
        
        result = temp_storage.get_airfield_stats("EGKB")
        assert result is not None

    def test_context_manager_rollback(self, temp_db_path, sample_airport_stats):
        """Test context manager rolls back on exception."""
        storage = GAMetaStorage(temp_db_path)
        
        try:
            with storage:
                storage.write_airfield_stats(sample_airport_stats)
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        result = storage.get_airfield_stats("EGKB")
        # Should be None because transaction was rolled back
        assert result is None
        
        storage.close()

