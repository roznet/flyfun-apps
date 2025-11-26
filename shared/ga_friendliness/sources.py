"""
Review source implementations for ga_friendliness library.

Provides different sources of review data that can be used by the pipeline.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

from .cache import CachedDataLoader
from .interfaces import ReviewSource
from .models import RawReview

logger = logging.getLogger(__name__)


class CSVReviewSource(ReviewSource):
    """
    Load reviews from a CSV file.
    
    Expected columns:
        - icao: Airport ICAO code (required)
        - review_text: Review text content (required)
        - review_id: Optional unique review ID
        - rating: Optional numeric rating
        - timestamp: Optional ISO format timestamp
        - language: Optional language code
    """

    def __init__(
        self,
        csv_path: Path,
        icao_column: str = "icao",
        text_column: str = "review_text",
        review_id_column: Optional[str] = "review_id",
        rating_column: Optional[str] = "rating",
        timestamp_column: Optional[str] = "timestamp",
        language_column: Optional[str] = "language",
        source_name: str = "csv",
    ):
        """
        Initialize CSV review source.
        
        Args:
            csv_path: Path to CSV file
            icao_column: Name of column containing ICAO codes
            text_column: Name of column containing review text
            review_id_column: Name of column containing review IDs (optional)
            rating_column: Name of column containing ratings (optional)
            timestamp_column: Name of column containing timestamps (optional)
            language_column: Name of column containing language codes (optional)
            source_name: Name to identify this source
        """
        self.csv_path = csv_path
        self.icao_column = icao_column
        self.text_column = text_column
        self.review_id_column = review_id_column
        self.rating_column = rating_column
        self.timestamp_column = timestamp_column
        self.language_column = language_column
        self.source_name = source_name
        
        self._reviews: Optional[List[RawReview]] = None
        self._reviews_by_icao: Optional[Dict[str, List[RawReview]]] = None

    def _load_reviews(self) -> None:
        """Load reviews from CSV if not already loaded."""
        if self._reviews is not None:
            return

        self._reviews = []
        self._reviews_by_icao = {}

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                icao = row.get(self.icao_column, "").strip().upper()
                text = row.get(self.text_column, "").strip()
                
                if not icao or not text:
                    continue

                review = RawReview(
                    icao=icao,
                    review_text=text,
                    review_id=row.get(self.review_id_column) if self.review_id_column else None,
                    rating=float(row.get(self.rating_column)) if self.rating_column and row.get(self.rating_column) else None,
                    timestamp=row.get(self.timestamp_column) if self.timestamp_column else None,
                    language=row.get(self.language_column) if self.language_column else None,
                    source=self.source_name,
                )
                
                self._reviews.append(review)
                
                if icao not in self._reviews_by_icao:
                    self._reviews_by_icao[icao] = []
                self._reviews_by_icao[icao].append(review)

        logger.info(f"Loaded {len(self._reviews)} reviews from {self.csv_path}")

    def get_reviews(self) -> List[RawReview]:
        """Get all reviews from the source."""
        self._load_reviews()
        return self._reviews or []

    def get_reviews_for_icao(self, icao: str) -> List[RawReview]:
        """Get reviews for a specific airport."""
        self._load_reviews()
        return self._reviews_by_icao.get(icao.upper(), [])

    def get_icaos(self) -> Set[str]:
        """Get all ICAO codes in the source."""
        self._load_reviews()
        return set(self._reviews_by_icao.keys()) if self._reviews_by_icao else set()

    def get_source_name(self) -> str:
        """Get the name/identifier of this source."""
        return self.source_name


class AirfieldDirectorySource(ReviewSource, CachedDataLoader):
    """
    Load reviews from airfield.directory export.
    
    Supports:
        - Local JSON export file
        - Cached downloads from S3
        - Individual airport JSON fetches
    """

    # Aircraft type to MTOW mapping for fee band assignment
    AIRCRAFT_MTOW_MAP: Dict[str, int] = {
        # Light singles
        "c172": 1157,      # Cessna 172
        "pa28": 1111,      # Piper PA-28
        "c152": 757,       # Cessna 152
        "c182": 1406,      # Cessna 182
        
        # High performance singles
        "sr22": 1633,      # Cirrus SR22
        "c210": 1814,      # Cessna 210
        "m20": 1315,       # Mooney M20
        "pa32": 1542,      # Piper PA-32
        
        # Light twins
        "pa34": 2155,      # Piper Seneca
        "be76": 1769,      # Beech Duchess
        "da42": 1785,      # Diamond DA42
        
        # Turboprops
        "tbm85": 3354,     # TBM 850
        "tbm9": 3354,      # TBM 900 series
        "pc12": 4740,      # Pilatus PC-12
        
        # Jets
        "c510": 4536,      # Cessna Citation Mustang
        "c525": 5670,      # Citation CJ series
        
        # Default categories
        "default_light": 1000,
        "default_heavy": 4000,
    }

    def __init__(
        self,
        cache_dir: Path,
        export_path: Optional[Path] = None,
        filter_ai_generated: bool = True,
        preferred_language: str = "EN",
        max_cache_age_days: int = 7,
    ):
        """
        Initialize airfield.directory source.
        
        Args:
            cache_dir: Directory for caching downloaded data
            export_path: Path to local export file (if None, downloads from S3)
            filter_ai_generated: Whether to filter out AI-generated reviews
            preferred_language: Preferred language for reviews
            max_cache_age_days: Maximum age of cached data in days
        """
        CachedDataLoader.__init__(self, cache_dir)
        
        self.export_path = export_path
        self.filter_ai_generated = filter_ai_generated
        self.preferred_language = preferred_language
        self.max_cache_age_days = max_cache_age_days
        
        self._data: Optional[Dict] = None
        self._reviews: Optional[List[RawReview]] = None
        self._reviews_by_icao: Optional[Dict[str, List[RawReview]]] = None

    def fetch_data(self, key: str, **kwargs: Any) -> Any:
        """
        Fetch data from remote source.
        
        Keys:
            - "bulk_export": Download bulk export (not implemented - use local file)
            - "airport_{ICAO}": Fetch individual airport JSON (not implemented)
        """
        # For now, we only support local file loading
        # Remote fetching could be added later
        raise NotImplementedError(
            f"Remote fetching not implemented for key: {key}. "
            "Please provide a local export file via export_path."
        )

    def _load_data(self) -> None:
        """Load data from export file."""
        if self._data is not None:
            return

        if self.export_path is None:
            raise ValueError("export_path must be provided")

        if not self.export_path.exists():
            raise FileNotFoundError(f"Export file not found: {self.export_path}")

        logger.info(f"Loading airfield.directory export from {self.export_path}")
        
        with open(self.export_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def _parse_reviews(self) -> None:
        """Parse reviews from loaded data."""
        if self._reviews is not None:
            return

        self._load_data()
        
        self._reviews = []
        self._reviews_by_icao = {}

        # airfield.directory bulk export structure:
        # {
        #   "metadata": {...},
        #   "pireps": {
        #     "LFSB": {
        #       "LFSB#hash": { "content": {"EN": "...", "DE": "..."}, "ai_generated": true, ... }
        #     },
        #     ...
        #   }
        # }
        pireps_by_icao = self._data.get("pireps", {})
        
        for icao, pireps_dict in pireps_by_icao.items():
            icao = icao.upper()
            
            for pirep_id, pirep in pireps_dict.items():
                # Filter AI-generated reviews if configured
                if self.filter_ai_generated and pirep.get("ai_generated", False):
                    continue

                # Get the review text (may be in different languages)
                content = pirep.get("content", {})
                
                # Try preferred language first, then English, then any available
                text = content.get(self.preferred_language) or content.get("EN") or ""
                if not text and content:
                    # Get first available language
                    text = next(iter(content.values()), "")
                
                text = text.strip()
                language = pirep.get("language", self.preferred_language)
                
                if not text:
                    continue

                review = RawReview(
                    icao=icao,
                    review_text=text,
                    review_id=pirep.get("id", pirep_id),
                    rating=pirep.get("rating"),
                    timestamp=pirep.get("created_at") or pirep.get("updated_at"),
                    language=language,
                    ai_generated=pirep.get("ai_generated", False),
                    source="airfield.directory",
                )
                
                self._reviews.append(review)
                
                if icao not in self._reviews_by_icao:
                    self._reviews_by_icao[icao] = []
                self._reviews_by_icao[icao].append(review)

        logger.info(
            f"Parsed {len(self._reviews)} reviews from {len(self._reviews_by_icao)} airports"
        )

    def get_reviews(self) -> List[RawReview]:
        """Get all reviews from the source."""
        self._parse_reviews()
        return self._reviews or []

    def get_reviews_for_icao(self, icao: str) -> List[RawReview]:
        """Get reviews for a specific airport."""
        self._parse_reviews()
        return self._reviews_by_icao.get(icao.upper(), [])

    def get_icaos(self) -> Set[str]:
        """Get all ICAO codes in the source."""
        self._parse_reviews()
        return set(self._reviews_by_icao.keys()) if self._reviews_by_icao else set()

    def get_airport_data(self, icao: str) -> Optional[Dict]:
        """
        Get full airport data including fees.
        
        Returns raw airport dict from export file.
        """
        self._load_data()
        
        airports = self._data.get("airports", [])
        for airport in airports:
            if airport.get("icao", "").upper() == icao.upper():
                return airport
        return None

    def get_source_name(self) -> str:
        """Get the name/identifier of this source."""
        return "airfield.directory"


class AirportJsonDirectorySource(ReviewSource):
    """
    Load airport data from individual JSON files in a directory.
    
    Each JSON file follows the airfield.directory per-airport format:
    {
        "airfield": { "data": { "icao": "EGTF", ... } },
        "aerops": { "data": { "landing_fees": {...}, "currency": "EUR" } },
        "pireps": { "data": [ { "id": "...", "content": {...}, ... } ] }
    }
    
    This source also extracts fee data which can be used for cost scoring.
    """
    
    # Aircraft type to MTOW mapping for fee band assignment
    AIRCRAFT_MTOW_MAP: Dict[str, int] = {
        # Light singles
        "c172": 1157,      # Cessna 172
        "pa28": 1111,      # Piper PA-28
        "c152": 757,       # Cessna 152
        "c182": 1406,      # Cessna 182
        "a210": 1814,      # Cessna 210 (alternative key)
        
        # High performance singles
        "sr22": 1633,      # Cirrus SR22
        "c210": 1814,      # Cessna 210
        "m20": 1315,       # Mooney M20
        "pa32": 1542,      # Piper PA-32
        
        # Light twins
        "pa34": 2155,      # Piper Seneca
        "be76": 1769,      # Beech Duchess
        "da42": 1785,      # Diamond DA42
        
        # Turboprops
        "tbm850": 3354,    # TBM 850
        "tbm85": 3354,     # TBM 850 (alternative)
        "tbm9": 3354,      # TBM 900 series
        "pc12": 4740,      # Pilatus PC-12
        
        # Jets
        "c510": 4536,      # Cessna Citation Mustang
        "c525": 5670,      # Citation CJ series
    }
    
    # Fee bands (MTOW ranges in kg)
    FEE_BANDS = [
        (0, 749, "fee_band_0_749kg"),
        (750, 1199, "fee_band_750_1199kg"),
        (1200, 1499, "fee_band_1200_1499kg"),
        (1500, 1999, "fee_band_1500_1999kg"),
        (2000, 3999, "fee_band_2000_3999kg"),
        (4000, 99999, "fee_band_4000_plus_kg"),
    ]

    def __init__(
        self,
        directory: Path,
        filter_ai_generated: bool = True,
        preferred_language: str = "EN",
        file_pattern: str = "*.json",
    ):
        """
        Initialize directory source.
        
        Args:
            directory: Directory containing per-airport JSON files
            filter_ai_generated: Whether to filter out AI-generated reviews
            preferred_language: Preferred language for reviews
            file_pattern: Glob pattern for JSON files
        """
        self.directory = Path(directory)
        self.filter_ai_generated = filter_ai_generated
        self.preferred_language = preferred_language
        self.file_pattern = file_pattern
        
        self._reviews: Optional[List[RawReview]] = None
        self._reviews_by_icao: Optional[Dict[str, List[RawReview]]] = None
        self._airport_data: Optional[Dict[str, Dict]] = None
        self._fee_data: Optional[Dict[str, Dict]] = None

    def _get_fee_band(self, mtow_kg: int) -> str:
        """Get fee band name for a given MTOW."""
        for min_kg, max_kg, band_name in self.FEE_BANDS:
            if min_kg <= mtow_kg <= max_kg:
                return band_name
        return "fee_band_4000_plus_kg"

    def _parse_airport_file(self, file_path: Path) -> Optional[Dict]:
        """Parse a single airport JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None

    def _load_data(self) -> None:
        """Load all airport data from directory."""
        if self._reviews is not None:
            return

        self._reviews = []
        self._reviews_by_icao = {}
        self._airport_data = {}
        self._fee_data = {}

        if not self.directory.exists():
            raise FileNotFoundError(f"Directory not found: {self.directory}")

        json_files = list(self.directory.glob(self.file_pattern))
        logger.info(f"Found {len(json_files)} JSON files in {self.directory}")

        for file_path in json_files:
            data = self._parse_airport_file(file_path)
            if not data:
                continue

            # Get ICAO from airfield data or filename
            icao = None
            airfield_data = data.get("airfield", {}).get("data", {})
            if airfield_data:
                icao = airfield_data.get("icao", "").upper()
            
            if not icao:
                # Try to get from filename (e.g., EGTF.json)
                icao = file_path.stem.upper()
                if len(icao) != 4:
                    continue

            self._airport_data[icao] = data

            # Parse pireps
            pireps_data = data.get("pireps", {}).get("data", [])
            for pirep in pireps_data:
                # Filter AI-generated reviews if configured
                if self.filter_ai_generated and pirep.get("ai_generated", False):
                    continue

                # Get the review text
                content = pirep.get("content", {})
                if isinstance(content, str):
                    text = content
                else:
                    # Try preferred language first, then English, then any available
                    text = content.get(self.preferred_language) or content.get("EN") or ""
                    if not text and content:
                        text = next(iter(content.values()), "")
                
                text = text.strip()
                if not text:
                    continue

                review = RawReview(
                    icao=icao,
                    review_text=text,
                    review_id=pirep.get("id"),
                    rating=pirep.get("rating"),
                    timestamp=pirep.get("created_at") or pirep.get("updated_at"),
                    language=pirep.get("language", self.preferred_language),
                    ai_generated=pirep.get("ai_generated", False),
                    source="airfield.directory.json",
                )
                
                self._reviews.append(review)
                
                if icao not in self._reviews_by_icao:
                    self._reviews_by_icao[icao] = []
                self._reviews_by_icao[icao].append(review)

            # Parse aerops fee data
            aerops = data.get("aerops") or {}
            aerops_data = aerops.get("data") or {}
            if aerops_data:
                self._parse_fees(icao, aerops_data)

        logger.info(
            f"Parsed {len(self._reviews)} reviews from {len(self._reviews_by_icao)} airports, "
            f"{len(self._fee_data)} airports with fee data"
        )

    def _parse_fees(self, icao: str, aerops_data: Dict) -> None:
        """Parse fee data and aggregate by fee band."""
        landing_fees = aerops_data.get("landing_fees", {})
        if not landing_fees:
            return

        currency = aerops_data.get("currency", "EUR")
        fees_last_changed = aerops_data.get("fees_last_changed")

        # Aggregate fees by band
        fee_bands: Dict[str, List[float]] = {}
        
        for aircraft_type, fees in landing_fees.items():
            aircraft_key = aircraft_type.lower()
            mtow = self.AIRCRAFT_MTOW_MAP.get(aircraft_key)
            
            if mtow is None:
                logger.debug(f"Unknown aircraft type: {aircraft_type}")
                continue

            band = self._get_fee_band(mtow)
            
            # Get the net price from the fee data
            if isinstance(fees, list) and fees:
                fee_entry = fees[0]
                net_price = fee_entry.get("netPrice") or fee_entry.get("netprice")
                if net_price:
                    try:
                        price = float(net_price)
                        if band not in fee_bands:
                            fee_bands[band] = []
                        fee_bands[band].append(price)
                    except (ValueError, TypeError):
                        pass

        # Average fees for each band
        if fee_bands:
            self._fee_data[icao] = {
                "currency": currency,
                "fees_last_changed": fees_last_changed,
                "bands": {
                    band: sum(prices) / len(prices)
                    for band, prices in fee_bands.items()
                }
            }

    def get_reviews(self) -> List[RawReview]:
        """Get all reviews from the source."""
        self._load_data()
        return self._reviews or []

    def get_reviews_for_icao(self, icao: str) -> List[RawReview]:
        """Get reviews for a specific airport."""
        self._load_data()
        return self._reviews_by_icao.get(icao.upper(), [])

    def get_icaos(self) -> Set[str]:
        """Get all ICAO codes in the source."""
        self._load_data()
        return set(self._reviews_by_icao.keys()) if self._reviews_by_icao else set()

    def get_airport_data(self, icao: str) -> Optional[Dict]:
        """Get full airport data including airfield info and aerops."""
        self._load_data()
        return self._airport_data.get(icao.upper())

    def get_fee_data(self, icao: str) -> Optional[Dict]:
        """
        Get parsed fee data for an airport.
        
        Returns dict with:
            - currency: Currency code (e.g., "GBP")
            - fees_last_changed: Date string of last update
            - bands: Dict mapping band names to average prices
        """
        self._load_data()
        return self._fee_data.get(icao.upper())

    def get_all_fee_data(self) -> Dict[str, Dict]:
        """Get fee data for all airports."""
        self._load_data()
        return self._fee_data or {}

    def get_source_name(self) -> str:
        """Get the name/identifier of this source."""
        return "airfield.directory.json"


class CompositeReviewSource(ReviewSource):
    """
    Combine multiple review sources.
    
    Aggregates reviews from multiple sources with optional deduplication.
    """

    def __init__(
        self,
        sources: List[ReviewSource],
        deduplicate_by_id: bool = True,
    ):
        """
        Initialize composite source.
        
        Args:
            sources: List of ReviewSource instances to combine
            deduplicate_by_id: Whether to deduplicate reviews by review_id
        """
        self.sources = sources
        self.deduplicate_by_id = deduplicate_by_id
        
        self._reviews: Optional[List[RawReview]] = None
        self._reviews_by_icao: Optional[Dict[str, List[RawReview]]] = None

    def _load_reviews(self) -> None:
        """Load and combine reviews from all sources."""
        if self._reviews is not None:
            return

        self._reviews = []
        self._reviews_by_icao = {}
        seen_ids: Set[str] = set()

        for source in self.sources:
            for review in source.get_reviews():
                # Deduplicate by review_id if configured
                if self.deduplicate_by_id and review.review_id:
                    if review.review_id in seen_ids:
                        continue
                    seen_ids.add(review.review_id)

                self._reviews.append(review)
                
                if review.icao not in self._reviews_by_icao:
                    self._reviews_by_icao[review.icao] = []
                self._reviews_by_icao[review.icao].append(review)

        logger.info(
            f"Combined {len(self._reviews)} reviews from {len(self.sources)} sources"
        )

    def get_reviews(self) -> List[RawReview]:
        """Get all reviews from all sources."""
        self._load_reviews()
        return self._reviews or []

    def get_reviews_for_icao(self, icao: str) -> List[RawReview]:
        """Get reviews for a specific airport from all sources."""
        self._load_reviews()
        return self._reviews_by_icao.get(icao.upper(), [])

    def get_icaos(self) -> Set[str]:
        """Get all ICAO codes from all sources."""
        self._load_reviews()
        return set(self._reviews_by_icao.keys()) if self._reviews_by_icao else set()

    def get_source_name(self) -> str:
        """Get the name/identifier of this source."""
        source_names = [s.get_source_name() for s in self.sources]
        return f"composite({', '.join(source_names)})"

