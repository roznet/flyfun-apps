"""
Abstract interfaces for ga_friendliness library.

These interfaces define the contracts that must be implemented by concrete classes.
They enable dependency injection and testing with mocks.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

from .models import (
    AirportStats,
    NotificationRule,
    ParsedAIPRules,
    RawReview,
    ReviewExtraction,
    RuleSummary,
)


class ReviewSource(ABC):
    """
    Abstract base class for review data sources.
    
    Implementations:
        - AirfieldDirectorySource: Load from airfield.directory export/API
        - CSVReviewSource: Load from CSV file
        - CompositeReviewSource: Combine multiple sources
    """

    @abstractmethod
    def get_reviews(self) -> List[RawReview]:
        """
        Get all reviews from the source.
        
        Returns:
            List of RawReview objects
        """
        pass

    @abstractmethod
    def get_reviews_for_icao(self, icao: str) -> List[RawReview]:
        """
        Get reviews for a specific airport.
        
        Args:
            icao: Airport ICAO code
            
        Returns:
            List of RawReview objects for that airport
        """
        pass

    @abstractmethod
    def get_icaos(self) -> Set[str]:
        """
        Get all ICAO codes in the source.
        
        Returns:
            Set of ICAO codes
        """
        pass

    def iter_reviews_by_icao(self) -> Iterator[tuple[str, List[RawReview]]]:
        """
        Iterate over reviews grouped by ICAO.
        
        Yields:
            Tuples of (icao, reviews_list)
        """
        for icao in self.get_icaos():
            reviews = self.get_reviews_for_icao(icao)
            if reviews:
                yield icao, reviews

    def get_source_name(self) -> str:
        """Get the name/identifier of this source."""
        return self.__class__.__name__


class AIPDataSource(ABC):
    """
    Abstract base class for AIP data sources.
    
    Provides access to AIP text data from euro_aip.sqlite for rule parsing.
    """

    @abstractmethod
    def get_airport_aip_text(self, icao: str) -> Optional[Dict[str, Dict[str, str]]]:
        """
        Get AIP text fields for an airport.
        
        Returns:
            Dict mapping section -> field -> text value
            Example:
                {
                    'customs': {
                        'notification': 'PPR 24 HR weekdays, 48 HR weekends',
                        'availability': 'H24'
                    },
                    'handling': {
                        'ppr_required': 'PPR 2 HR',
                        'services': 'Available on PPR'
                    }
                }
            Returns None if airport not found.
        """
        pass

    @abstractmethod
    def get_all_airports(self) -> List[str]:
        """Get list of all ICAOs in the AIP source."""
        pass

    @abstractmethod
    def get_last_aip_change_timestamp(self, icao: str) -> Optional[datetime]:
        """
        Get when AIP data was last changed for this airport.
        
        Returns:
            Timestamp of last change, or None if not found.
        """
        pass


class StorageInterface(ABC):
    """
    Abstract interface for GA friendliness storage operations.
    
    Defines all database operations needed by the library.
    Concrete implementation: GAMetaStorage (in storage.py)
    """

    @abstractmethod
    def __enter__(self) -> "StorageInterface":
        """Context manager entry: begin transaction."""
        pass

    @abstractmethod
    def __exit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> None:
        """Context manager exit: commit or rollback."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close database connection and cleanup resources."""
        pass

    # --- Airport Stats Operations ---

    @abstractmethod
    def write_airfield_stats(self, stats: AirportStats) -> None:
        """Insert or update a row in ga_airfield_stats."""
        pass

    @abstractmethod
    def get_airfield_stats(self, icao: str) -> Optional[AirportStats]:
        """Read stats for a single airport."""
        pass

    @abstractmethod
    def get_all_icaos(self) -> List[str]:
        """Get list of all ICAOs in ga_airfield_stats."""
        pass

    # --- Review Tags Operations ---

    @abstractmethod
    def write_review_tags(self, icao: str, tags: List[ReviewExtraction]) -> None:
        """
        Write review tags to ga_review_ner_tags.
        
        Clears existing tags for this icao first (idempotent rebuild).
        """
        pass

    @abstractmethod
    def write_review_tags_batch(
        self, tags_by_icao: Dict[str, List[ReviewExtraction]]
    ) -> None:
        """Write tags for multiple airports in a single transaction."""
        pass

    @abstractmethod
    def get_processed_review_ids(self, icao: str) -> Set[str]:
        """Get set of review_ids already processed for this airport."""
        pass

    # --- Review Summary Operations ---

    @abstractmethod
    def write_review_summary(
        self, icao: str, summary_text: str, tags_json: List[str]
    ) -> None:
        """Insert or update ga_review_summary for an airport."""
        pass

    # --- Meta Info Operations ---

    @abstractmethod
    def write_meta_info(self, key: str, value: str) -> None:
        """Write to ga_meta_info table."""
        pass

    @abstractmethod
    def get_meta_info(self, key: str) -> Optional[str]:
        """Read from ga_meta_info table."""
        pass

    @abstractmethod
    def get_last_processed_timestamp(self, icao: str) -> Optional[datetime]:
        """Get when airport was last processed."""
        pass

    @abstractmethod
    def update_last_processed_timestamp(
        self, icao: str, timestamp: datetime
    ) -> None:
        """Update last processed timestamp for an airport."""
        pass

    # --- Change Detection ---

    @abstractmethod
    def has_changes(
        self, icao: str, reviews: List[RawReview], since: Optional[datetime] = None
    ) -> bool:
        """Check if airport has new/changed reviews."""
        pass

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
        # Default implementation: always return False (no fee change detection)
        # Subclasses should override this for fee change detection
        return False

    def update_fees_only(
        self, icao: str, fee_data: Dict[str, Any]
    ) -> None:
        """
        Update only fee data for an airport without processing reviews.
        
        Args:
            icao: Airport ICAO code
            fee_data: Fee data dict with 'currency', 'fees_last_changed', and 'bands'
        """
        # Default implementation: raise NotImplementedError
        # Subclasses should override this for fee-only updates
        raise NotImplementedError("Fee-only updates not supported by this storage implementation")

    # --- Resume Support ---

    @abstractmethod
    def get_last_successful_icao(self) -> Optional[str]:
        """Get last successfully processed ICAO code (for resume)."""
        pass

    @abstractmethod
    def set_last_successful_icao(self, icao: str) -> None:
        """Set last successfully processed ICAO code."""
        pass

    # --- AIP Rules Operations (for Phase 5) ---

    @abstractmethod
    def write_notification_requirements(
        self, icao: str, rules: List[NotificationRule]
    ) -> None:
        """Write notification requirements to ga_notification_requirements."""
        pass

    @abstractmethod
    def write_aip_rule_summary(self, icao: str, summary: RuleSummary) -> None:
        """Insert or update ga_aip_rule_summary."""
        pass

    @abstractmethod
    def get_last_aip_processed_timestamp(self, icao: str) -> Optional[datetime]:
        """Get when AIP rules were last processed for this airport."""
        pass

    @abstractmethod
    def update_last_aip_processed_timestamp(
        self, icao: str, timestamp: datetime
    ) -> None:
        """Update last processed timestamp for AIP rules."""
        pass

    # --- Global Priors (for Bayesian smoothing) ---

    @abstractmethod
    def compute_global_priors(self) -> Dict[str, float]:
        """Compute global average scores across all airports."""
        pass

    @abstractmethod
    def store_global_priors(self, priors: Dict[str, float]) -> None:
        """Store computed global priors in ga_meta_info."""
        pass

    @abstractmethod
    def get_global_priors(self) -> Optional[Dict[str, float]]:
        """Get stored global priors from ga_meta_info."""
        pass


class ReviewExtractorInterface(ABC):
    """
    Abstract interface for review tag extraction.
    
    Defines the contract for NLP-based extraction from reviews.
    """

    @abstractmethod
    def extract(
        self,
        review_text: str,
        review_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> ReviewExtraction:
        """
        Extract tags from a single review.
        
        Args:
            review_text: Review text to extract tags from
            review_id: Optional review ID from source
            timestamp: Optional timestamp from source review
            
        Returns:
            ReviewExtraction with aspect-label pairs
        """
        pass

    @abstractmethod
    def extract_batch(
        self,
        reviews: List[tuple[str, Optional[str], Optional[str]]],
    ) -> List[ReviewExtraction]:
        """
        Extract tags from multiple reviews.
        
        Args:
            reviews: List of (text, review_id, timestamp) tuples
            
        Returns:
            List of ReviewExtraction objects
        """
        pass

    @abstractmethod
    def get_token_usage(self) -> Dict[str, int]:
        """Get cumulative token usage stats."""
        pass


class RuleParserInterface(ABC):
    """
    Abstract interface for AIP rule parsing.
    """

    @abstractmethod
    def parse_rules(
        self, icao: str, aip_text: Dict[str, Dict[str, str]]
    ) -> ParsedAIPRules:
        """Parse rules from AIP text."""
        pass


class RuleSummarizerInterface(ABC):
    """
    Abstract interface for rule summarization.
    """

    @abstractmethod
    def summarize_rules(self, icao: str, rules: ParsedAIPRules) -> RuleSummary:
        """Generate high-level summary from detailed rules."""
        pass

    @abstractmethod
    def calculate_hassle_score(self, rules: List[NotificationRule]) -> float:
        """Calculate normalized hassle score from rules."""
        pass


class SummaryGeneratorInterface(ABC):
    """
    Abstract interface for airport summary generation.
    """

    @abstractmethod
    def generate_summary(
        self,
        icao: str,
        extractions: List[ReviewExtraction],
        stats: Optional[AirportStats] = None,
    ) -> tuple[str, List[str]]:
        """
        Generate airport summary and tags.
        
        Args:
            icao: Airport ICAO code
            extractions: Extracted review tags
            stats: Optional airport stats for context
            
        Returns:
            Tuple of (summary_text, tags_list)
        """
        pass

