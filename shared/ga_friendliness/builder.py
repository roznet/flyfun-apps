"""
Main pipeline orchestrator for building GA friendliness database.

Coordinates all components to build ga_meta.sqlite from review sources.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .config import GAFriendlinessSettings, get_default_ontology, get_default_personas
from .exceptions import BuildError, StorageError
from .features import FeatureMapper, aggregate_fees_by_band
from .interfaces import ReviewSource, StorageInterface
from .models import (
    AirportStats,
    BuildMetrics,
    BuildResult,
    FailureMode,
    OntologyConfig,
    PersonasConfig,
    RawReview,
)
from .ontology import OntologyManager
from .personas import PersonaManager
from .sources import AirfieldDirectorySource, AirportJsonDirectorySource, AirportsDatabaseSource
from .storage import GAMetaStorage

# Optional imports for NLP components
try:
    from shared.ga_review_agent import ReviewExtractor, TagAggregator, SummaryGenerator
    HAS_REVIEW_AGENT = True
except ImportError:
    HAS_REVIEW_AGENT = False

logger = logging.getLogger(__name__)


class GAFriendlinessBuilder:
    """
    Main pipeline orchestrator for building GA friendliness data.
    
    Coordinates:
        - Loading reviews from sources
        - Extracting tags using LLM
        - Aggregating tags into feature scores
        - Generating summaries
        - Writing to database
    
    Features:
        - Incremental updates (only process changed airports)
        - Resume capability (continue from last successful airport)
        - Configurable failure handling
        - LLM usage tracking
    """

    def __init__(
        self,
        settings: Optional[GAFriendlinessSettings] = None,
        ontology: Optional[OntologyConfig] = None,
        personas: Optional[PersonasConfig] = None,
        storage: Optional[StorageInterface] = None,
        extractor: Optional[Any] = None,  # ReviewExtractor
        aggregator: Optional[Any] = None,  # TagAggregator
        summarizer: Optional[Any] = None,  # SummaryGenerator
    ):
        """
        Initialize builder with optional dependency injection.
        
        Args:
            settings: Configuration settings
            ontology: Ontology config (uses default if not provided)
            personas: Personas config (uses default if not provided)
            storage: Storage instance (creates from settings if not provided)
            extractor: Review extractor (creates from settings if not provided)
            aggregator: Tag aggregator (creates from settings if not provided)
            summarizer: Summary generator (creates from settings if not provided)
        """
        self.settings = settings or GAFriendlinessSettings()
        
        # Load ontology and personas
        self.ontology = ontology or get_default_ontology()
        self.personas_config = personas or get_default_personas()
        
        # Initialize managers
        self.ontology_manager = OntologyManager(self.ontology)
        self.persona_manager = PersonaManager(self.personas_config)
        
        # Initialize storage
        self._storage = storage
        
        # Initialize NLP components
        self._extractor = extractor
        self._aggregator = aggregator or (
            TagAggregator(
                enable_time_decay=self.settings.enable_time_decay,
                time_decay_half_life_days=self.settings.time_decay_half_life_days,
            ) if HAS_REVIEW_AGENT else None
        )
        self._summarizer = summarizer
        
        # Feature mapper
        self.feature_mapper = FeatureMapper(ontology=self.ontology)
        
        # Metrics
        self._metrics = BuildMetrics()

    @property
    def storage(self) -> StorageInterface:
        """Get or create storage instance."""
        if self._storage is None:
            self._storage = GAMetaStorage(self.settings.ga_meta_db_path)
        return self._storage

    @property
    def extractor(self) -> Any:
        """Get or create extractor instance."""
        if self._extractor is None and HAS_REVIEW_AGENT:
            self._extractor = ReviewExtractor(
                ontology=self.ontology,
                llm_model=self.settings.llm_model,
                llm_temperature=self.settings.llm_temperature,
                api_key=self.settings.llm_api_key,
                max_retries=self.settings.llm_max_retries,
                mock_llm=self.settings.use_mock_llm,
            )
        return self._extractor

    @property
    def summarizer(self) -> Any:
        """Get or create summarizer instance."""
        if self._summarizer is None and HAS_REVIEW_AGENT:
            self._summarizer = SummaryGenerator(
                llm_model=self.settings.llm_model,
                llm_temperature=self.settings.llm_temperature + 0.3,  # Slightly higher
                api_key=self.settings.llm_api_key,
                mock_llm=self.settings.use_mock_llm,
            )
        return self._summarizer

    def build(
        self,
        review_source: ReviewSource,
        incremental: bool = False,
        since: Optional[datetime] = None,
        icaos: Optional[List[str]] = None,
        resume: bool = False,
        airports_db: Optional[AirportsDatabaseSource] = None,
    ) -> BuildResult:
        """
        Build GA friendliness database from reviews.
        
        Args:
            review_source: Source of reviews to process
            incremental: Only process changed airports
            since: Only process reviews after this date
            icaos: Optional list of specific ICAOs to process
            resume: Resume from last successful ICAO
            airports_db: Optional AirportsDatabaseSource for IFR/hotel/restaurant data
        
        Returns:
            BuildResult with metrics and status
        """
        self._metrics = BuildMetrics(start_time=datetime.now(timezone.utc))
        
        try:
            # Get airports to process
            if icaos:
                airports_to_process = set(icaos)
            else:
                airports_to_process = review_source.get_icaos()
            
            # Sort for deterministic order (enables resume)
            airports_sorted = sorted(airports_to_process)
            
            # Handle resume
            start_index = 0
            if resume:
                last_icao = self.storage.get_last_successful_icao()
                if last_icao and last_icao in airports_sorted:
                    start_index = airports_sorted.index(last_icao) + 1
                    logger.info(
                        f"Resuming from {last_icao}, index {start_index}/{len(airports_sorted)}"
                    )
            
            airports_to_process_list = airports_sorted[start_index:]
            self._metrics.total_airports = len(airports_to_process_list)
            
            logger.info(
                f"Build started: {self._metrics.total_airports} airports, "
                f"incremental={incremental}, source={review_source.get_source_name()}"
            )
            
            # Process each airport
            failure_mode = FailureMode(self.settings.failure_mode)
            
            with self.storage:
                for icao in airports_to_process_list:
                    try:
                        # Get reviews for this airport
                        reviews = review_source.get_reviews_for_icao(icao)
                        
                        if not reviews:
                            self._metrics.skipped_airports += 1
                            continue
                        
                        # Check for changes if incremental
                        if incremental:
                            if not self.storage.has_changes(icao, reviews, since):
                                self._metrics.skipped_airports += 1
                                continue
                        
                        # Process airport
                        self._process_airport(icao, reviews, review_source, airports_db)
                        
                        self._metrics.successful_airports += 1
                        self._metrics.total_reviews += len(reviews)
                        
                        # Track progress for resume
                        self.storage.set_last_successful_icao(icao)
                        
                    except Exception as e:
                        self._metrics.failed_airports += 1
                        self._metrics.errors.append(f"{icao}: {str(e)}")
                        
                        logger.error(f"Airport {icao} processing failed: {e}")
                        
                        if failure_mode == FailureMode.FAIL_FAST:
                            raise BuildError(f"Failed processing {icao}: {e}")
                        elif failure_mode == FailureMode.SKIP:
                            continue
                        # CONTINUE: log and continue
                
                # Store build metadata
                self._store_build_metadata()
            
            self._metrics.end_time = datetime.now(timezone.utc)
            self._metrics.duration_seconds = (
                self._metrics.end_time - self._metrics.start_time
            ).total_seconds()
            
            logger.info(
                f"Build completed: {self._metrics.successful_airports} successful, "
                f"{self._metrics.failed_airports} failed, {self._metrics.skipped_airports} skipped, "
                f"{self._metrics.duration_seconds:.1f}s"
            )
            
            return BuildResult(
                success=self._metrics.failed_airports == 0,
                metrics=self._metrics,
                output_db_path=str(self.settings.ga_meta_db_path),
                last_successful_icao=self.storage.get_last_successful_icao(),
            )
            
        except Exception as e:
            self._metrics.end_time = datetime.now(timezone.utc)
            self._metrics.duration_seconds = (
                self._metrics.end_time - self._metrics.start_time
            ).total_seconds() if self._metrics.start_time else None
            self._metrics.errors.append(f"Build failed: {str(e)}")
            
            logger.error(f"Build failed: {e}")
            
            return BuildResult(
                success=False,
                metrics=self._metrics,
                output_db_path=str(self.settings.ga_meta_db_path),
            )

    def _process_airport(
        self,
        icao: str,
        reviews: List[RawReview],
        source: ReviewSource,
        airports_db: Optional[AirportsDatabaseSource] = None,
    ) -> None:
        """
        Process a single airport's reviews.
        
        Pipeline:
            1. Extract tags from reviews
            2. Aggregate tags into distributions
            3. Map distributions to feature scores
            4. Get airport metadata from airports.db (if available)
            5. Generate summary
            6. Write to database
        """
        logger.debug(f"Processing airport {icao} with {len(reviews)} reviews")
        
        # Extract tags
        extractions = []
        if self.extractor:
            review_data = [
                (r.review_text, r.review_id, r.timestamp)
                for r in reviews
            ]
            extractions = self.extractor.extract_batch(review_data)
            
            # Filter by ontology
            extractions = [
                self.ontology_manager.filter_extraction(
                    e, confidence_threshold=self.settings.confidence_threshold
                )
                for e in extractions
            ]
            
            self._metrics.total_extractions += len(extractions)
        
        # Aggregate tags
        distributions = {}
        if self._aggregator and extractions:
            distributions, context = self._aggregator.aggregate_tags(extractions)
        
        # Get airport metadata from airports.db (IFR score, hotel, restaurant)
        ifr_score = 0  # Default: IFR not available
        ifr_available = False
        hotel_info = None
        restaurant_info = None
        
        if airports_db:
            try:
                metadata = airports_db.get_airport_metadata(icao)
                ifr_score = metadata.get("ifr_score", 0)
                ifr_available = metadata.get("ifr_permitted", False)
                hotel_info = metadata.get("hotel_info")
                restaurant_info = metadata.get("restaurant_info")
            except Exception as e:
                logger.warning(f"Failed to get airports.db metadata for {icao}: {e}")
        
        # Compute feature scores
        feature_scores = self.feature_mapper.compute_feature_scores(
            icao=icao,
            distributions=distributions,
            ifr_procedure_available=ifr_available,
        )
        
        # Compute persona scores
        persona_scores = self.persona_manager.compute_scores_for_all_personas(feature_scores)
        
        # Get fee data if source supports it
        fee_bands: Dict[str, Optional[float]] = {}
        fee_currency = "EUR"  # Default
        
        if isinstance(source, AirportJsonDirectorySource):
            # AirportJsonDirectorySource has pre-aggregated fee data
            fee_data = source.get_fee_data(icao)
            if fee_data:
                fee_bands = fee_data.get("bands", {})
                fee_currency = fee_data.get("currency", "EUR")
        elif isinstance(source, AirfieldDirectorySource):
            airport_data = source.get_airport_data(icao)
            if airport_data and "aerops" in airport_data:
                fee_bands = aggregate_fees_by_band(airport_data["aerops"])
        
        # Compute rating stats
        ratings = [r.rating for r in reviews if r.rating is not None]
        rating_avg = sum(ratings) / len(ratings) if ratings else None
        rating_count = len(ratings)
        
        # Get last review timestamp
        timestamps = [r.timestamp for r in reviews if r.timestamp]
        last_review = max(timestamps) if timestamps else None
        
        # Build airport stats
        stats = AirportStats(
            icao=icao,
            rating_avg=rating_avg,
            rating_count=rating_count,
            last_review_utc=last_review,
            fee_band_0_749kg=fee_bands.get("fee_band_0_749kg"),
            fee_band_750_1199kg=fee_bands.get("fee_band_750_1199kg"),
            fee_band_1200_1499kg=fee_bands.get("fee_band_1200_1499kg"),
            fee_band_1500_1999kg=fee_bands.get("fee_band_1500_1999kg"),
            fee_band_2000_3999kg=fee_bands.get("fee_band_2000_3999kg"),
            fee_band_4000_plus_kg=fee_bands.get("fee_band_4000_plus_kg"),
            fee_currency=fee_currency,
            mandatory_handling=False,
            ifr_procedure_available=ifr_available,
            ifr_score=ifr_score,
            night_available=False,
            hotel_info=hotel_info,
            restaurant_info=restaurant_info,
            ga_cost_score=feature_scores.ga_cost_score,
            ga_review_score=feature_scores.ga_review_score,
            ga_hassle_score=feature_scores.ga_hassle_score,
            ga_ops_ifr_score=feature_scores.ga_ops_ifr_score,
            ga_ops_vfr_score=feature_scores.ga_ops_vfr_score,
            ga_access_score=feature_scores.ga_access_score,
            ga_fun_score=feature_scores.ga_fun_score,
            ga_hospitality_score=feature_scores.ga_hospitality_score,
            source_version=self.settings.source_version,
            scoring_version=self.settings.scoring_version,
        )
        
        # Write to database
        self.storage.write_airfield_stats(stats)
        
        # Write review tags
        if extractions:
            self.storage.write_review_tags(icao, extractions)
        
        # Generate and store summary
        if self.summarizer and extractions:
            summary_text, tags = self.summarizer.generate_summary(
                icao, extractions, stats
            )
            self.storage.write_review_summary(icao, summary_text, tags)
        
        # Update last processed timestamp
        self.storage.update_last_processed_timestamp(
            icao, datetime.now(timezone.utc)
        )

    def _store_build_metadata(self) -> None:
        """Store build metadata in ga_meta_info."""
        now = datetime.now(timezone.utc).isoformat()
        
        self.storage.write_meta_info("build_timestamp", now)
        self.storage.write_meta_info("source_version", self.settings.source_version)
        self.storage.write_meta_info("scoring_version", self.settings.scoring_version)
        self.storage.write_meta_info("ontology_version", self.ontology.version)
        self.storage.write_meta_info("personas_version", self.personas_config.version)

    def get_metrics(self) -> BuildMetrics:
        """Get current build metrics."""
        return self._metrics

    def close(self) -> None:
        """Clean up resources."""
        if self._storage:
            self._storage.close()

