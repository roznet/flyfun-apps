"""
Review source implementations for ga_friendliness library.

Provides different sources of review data that can be used by the pipeline.
"""

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

import requests

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
        fee_data = _parse_aerops_fees(
            aerops_data,
            self.AIRCRAFT_MTOW_MAP,
            self.FEE_BANDS,
        )
        if fee_data:
            self._fee_data[icao] = fee_data

    def get_reviews(self) -> List[RawReview]:
        """Get all reviews from the source."""
        self._load_data()
        return self._reviews or []

    def get_reviews_for_icao(self, icao: str) -> List[RawReview]:
        """Get reviews for a specific airport."""
        self._load_data()
        return self._reviews_by_icao.get(icao.upper(), [])

    def get_icaos(self) -> Set[str]:
        """Get all ICAO codes in the source (including airports with fees but no reviews)."""
        self._load_data()
        # Include airports with reviews OR airports with fee data
        icaos = set()
        if self._reviews_by_icao:
            icaos.update(self._reviews_by_icao.keys())
        if self._fee_data:
            icaos.update(self._fee_data.keys())
        return icaos

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


def _parse_aerops_fees(
    aerops_data: Dict,
    aircraft_mtow_map: Dict[str, int],
    fee_bands: List[tuple],
) -> Optional[Dict[str, Any]]:
    """
    Parse fee data from aerops.data structure and aggregate by fee band.
    
    Shared utility function for parsing landing fees from airfield.directory format.
    
    Args:
        aerops_data: Dict with 'landing_fees', 'currency', 'fees_last_changed'
        aircraft_mtow_map: Mapping of aircraft type (lowercase) to MTOW in kg
        fee_bands: List of (min_kg, max_kg, band_name) tuples
        
    Returns:
        Dict with 'currency', 'fees_last_changed', 'bands' (dict of band_name -> avg_price)
        or None if no fees found
    """
    landing_fees = aerops_data.get("landing_fees", {})
    if not landing_fees:
        return None
    
    currency = aerops_data.get("currency", "EUR")
    fees_last_changed = aerops_data.get("fees_last_changed")
    
    # Helper to get fee band for MTOW
    def get_fee_band(mtow_kg: int) -> str:
        for min_kg, max_kg, band_name in fee_bands:
            if min_kg <= mtow_kg <= max_kg:
                return band_name
        return "fee_band_4000_plus_kg"
    
    # Aggregate fees by band
    fee_bands_dict: Dict[str, List[float]] = {}
    
    for aircraft_type, fees in landing_fees.items():
        aircraft_key = aircraft_type.lower()
        mtow = aircraft_mtow_map.get(aircraft_key)
        
        if mtow is None:
            logger.debug(f"Unknown aircraft type: {aircraft_type}")
            continue
        
        band = get_fee_band(mtow)
        
        # Get the net price from the fee data
        # API format: fees is a list of fee entries
        if isinstance(fees, list) and fees:
            fee_entry = fees[0]
            net_price = fee_entry.get("netPrice") or fee_entry.get("netprice")
            if net_price:
                try:
                    price = float(net_price)
                    if band not in fee_bands_dict:
                        fee_bands_dict[band] = []
                    fee_bands_dict[band].append(price)
                except (ValueError, TypeError):
                    pass
    
    # Average fees for each band
    if fee_bands_dict:
        return {
            "currency": currency,
            "fees_last_changed": fees_last_changed,
            "bands": {
                band: sum(prices) / len(prices)
                for band, prices in fee_bands_dict.items()
            }
        }
    
    return None


class AirfieldDirectoryAPISource(ReviewSource, CachedDataLoader):
    """
    Download and load reviews from airfield.directory API.
    
    Downloads per-airport JSON files from the API for specified ICAO codes.
    Supports caching to avoid repeated downloads.
    
    The API format matches the per-airport JSON format:
    {
        "airfield": { "data": { "icao": "EDAZ", ... } },
        "aerops": { "data": { "landing_fees": {...}, "currency": "EUR" } },
        "pireps": { "data": [ { "id": "...", "content": {...}, ... } ] }
    }
    """
    
    # Aircraft type to MTOW mapping for fee band assignment
    # (same as AirportJsonDirectorySource)
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
        cache_dir: Path,
        icaos: List[str],
        filter_ai_generated: bool = True,
        preferred_language: str = "EN",
        max_cache_age_days: int = 7,
        base_url: str = "https://airfield.directory/airfield",
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize API source.
        
        Args:
            cache_dir: Directory for caching downloaded JSON files
            icaos: List of ICAO codes to download
            filter_ai_generated: Whether to filter out AI-generated reviews
            preferred_language: Preferred language for reviews
            max_cache_age_days: Maximum age of cached data in days
            base_url: Base URL for API (default: https://airfield.directory/airfield)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for failed downloads
        """
        CachedDataLoader.__init__(self, cache_dir)
        
        self.icaos = [icao.upper().strip() for icao in icaos]
        self.filter_ai_generated = filter_ai_generated
        self.preferred_language = preferred_language
        self.max_cache_age_days = max_cache_age_days
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        
        self._reviews: Optional[List[RawReview]] = None
        self._reviews_by_icao: Optional[Dict[str, List[RawReview]]] = None
        self._airport_data: Optional[Dict[str, Dict]] = None
        self._fee_data: Optional[Dict[str, Dict]] = None
    
    def fetch_data(self, key: str, **kwargs: Any) -> Any:
        """
        Fetch airport JSON from API.
        
        Keys:
            - "airport_{ICAO}": Fetch individual airport JSON
            
        Args:
            key: Cache key (e.g., "airport_EDAZ")
            **kwargs: Additional arguments (unused)
            
        Returns:
            Parsed JSON dict
            
        Raises:
            requests.RequestException: On network errors
            ValueError: On invalid response
        """
        if not key.startswith("airport_"):
            raise ValueError(f"Invalid key format: {key}")
        
        icao = key.replace("airport_", "").upper()
        url = f"{self.base_url}/{icao}.json"
        
        # Retry logic with exponential backoff
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Fetching {url} (attempt {attempt + 1}/{self.max_retries})")
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()
                
                # Parse JSON
                data = response.json()
                
                # Validate structure
                if not isinstance(data, dict):
                    raise ValueError(f"Invalid response format: expected dict, got {type(data)}")
                
                # Verify ICAO matches
                airfield_data = data.get("airfield", {}).get("data", {})
                if airfield_data.get("icao", "").upper() != icao:
                    logger.warning(
                        f"ICAO mismatch: requested {icao}, got {airfield_data.get('icao')}"
                    )
                
                return data
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # Airport not found - don't retry
                    logger.warning(f"Airport not found: {icao} (404)")
                    raise
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.debug(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
            except (requests.exceptions.RequestException, ValueError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.debug(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
        
        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise ValueError(f"Failed to fetch {url} after {self.max_retries} attempts")
    
    def _load_data(self) -> None:
        """Download and parse all airports."""
        if self._reviews is not None:
            return
        
        self._reviews = []
        self._reviews_by_icao = {}
        self._airport_data = {}
        self._fee_data = {}
        
        logger.info(f"Downloading {len(self.icaos)} airports from {self.base_url}")
        
        successful = 0
        failed = 0
        
        for icao in self.icaos:
            try:
                # Use cached data loader to get airport JSON
                cache_key = f"airport_{icao}"
                data = self.get_cached(
                    cache_key,
                    max_age_days=self.max_cache_age_days,
                )
                
                if not data:
                    logger.warning(f"No data returned for {icao}")
                    failed += 1
                    continue
                
                self._airport_data[icao] = data
                
                # Parse pireps (reviews)
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
                        source="airfield.directory.api",
                    )
                    
                    self._reviews.append(review)
                    
                    if icao not in self._reviews_by_icao:
                        self._reviews_by_icao[icao] = []
                    self._reviews_by_icao[icao].append(review)
                
                # Parse aerops fee data
                aerops = data.get("aerops") or {}
                aerops_data = aerops.get("data") or {}
                if aerops_data:
                    fee_data = _parse_aerops_fees(
                        aerops_data,
                        self.AIRCRAFT_MTOW_MAP,
                        self.FEE_BANDS,
                    )
                    if fee_data:
                        self._fee_data[icao] = fee_data
                
                successful += 1
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    logger.warning(f"Airport not found: {icao} (404)")
                else:
                    logger.error(f"HTTP error for {icao}: {e}")
                failed += 1
            except Exception as e:
                logger.error(f"Failed to process {icao}: {e}")
                failed += 1
        
        logger.info(
            f"Downloaded {successful} airports, {failed} failed. "
            f"Parsed {len(self._reviews)} reviews from {len(self._reviews_by_icao)} airports, "
            f"{len(self._fee_data)} airports with fee data"
        )
    
    def get_reviews(self) -> List[RawReview]:
        """Get all reviews from the source."""
        self._load_data()
        return self._reviews or []
    
    def get_reviews_for_icao(self, icao: str) -> List[RawReview]:
        """Get reviews for a specific airport."""
        self._load_data()
        return self._reviews_by_icao.get(icao.upper(), [])
    
    def get_icaos(self) -> Set[str]:
        """Get all ICAO codes in the source (including airports with fees but no reviews)."""
        self._load_data()
        # Include airports with reviews OR airports with fee data
        icaos = set()
        if self._reviews_by_icao:
            icaos.update(self._reviews_by_icao.keys())
        if self._fee_data:
            icaos.update(self._fee_data.keys())
        return icaos
    
    def get_airport_data(self, icao: str) -> Optional[Dict]:
        """Get full airport data including airfield info and aerops."""
        self._load_data()
        return self._airport_data.get(icao.upper())
    
    def get_fee_data(self, icao: str) -> Optional[Dict]:
        """
        Get parsed fee data for an airport.
        
        Returns dict with:
            - currency: Currency code (e.g., "EUR")
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
        return "airfield.directory.api"


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


class AirportsDatabaseSource:
    """
    Extract airport metadata from euro_aip airports.db.
    
    Provides:
        - IFR score (0-4) based on traffic type and available procedures
        - Hotel availability info
        - Restaurant availability info
    
    This is NOT a ReviewSource - it provides supplementary airport metadata.
    """
    
    # Standard field IDs from aip_entries
    STD_FIELD_IFR_VFR = 207      # Type of Traffic permitted (IFR/VFR)
    STD_FIELD_HOTEL = 501        # Hotels
    STD_FIELD_RESTAURANT = 502   # Restaurants
    
    # IFR score values
    IFR_SCORE_NOT_PERMITTED = 0  # IFR not in traffic type
    IFR_SCORE_PERMITTED = 1      # IFR permitted but no procedures
    IFR_SCORE_BASIC = 2          # Has VOR/NDB/LOC procedures
    IFR_SCORE_RNP = 3            # Has RNP/RNAV procedures
    IFR_SCORE_ILS = 4            # Has ILS procedures
    
    def __init__(self, db_path: Path):
        """
        Initialize airports database source.

        Args:
            db_path: Path to airports.db SQLite database
        """
        self.db_path = Path(db_path)
        self._conn = None
        self._cache: Dict[str, Dict] = {}
        self._euro_aip_model = None  # Lazy-loaded EuroAipModel
    
    def _get_connection(self):
        """Get or create database connection."""
        if self._conn is None:
            import sqlite3
            if not self.db_path.exists():
                raise FileNotFoundError(f"Airports database not found: {self.db_path}")
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def _get_aip_field(self, icao: str, std_field_id: int) -> Optional[str]:
        """Get a specific AIP field value for an airport."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT value FROM aip_entries 
            WHERE airport_icao = ? AND std_field_id = ?
            ORDER BY source_priority DESC
            LIMIT 1
            """,
            (icao.upper(), std_field_id)
        )
        row = cursor.fetchone()
        return row["value"] if row else None
    
    def _is_ifr_permitted(self, icao: str) -> bool:
        """Check if IFR traffic is permitted at the airport."""
        value = self._get_aip_field(icao, self.STD_FIELD_IFR_VFR)
        if not value:
            return False
        # Check if "IFR" appears in the traffic type
        return "IFR" in value.upper()
    
    def _get_best_approach_type(self, icao: str) -> Optional[str]:
        """
        Get the best approach type available at the airport.
        
        Returns: 'ILS', 'RNP', 'RNAV', 'VOR', 'NDB', 'LOC', or None
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT DISTINCT approach_type FROM procedures 
            WHERE airport_icao = ? AND approach_type IS NOT NULL AND approach_type != ''
            """,
            (icao.upper(),)
        )
        approach_types = {row["approach_type"].upper() for row in cursor}
        
        if not approach_types:
            return None
        
        # Return best available (ILS > RNP/RNAV > others)
        if "ILS" in approach_types:
            return "ILS"
        if "RNP" in approach_types or "RNAV" in approach_types:
            return "RNP"
        # Return first available
        return next(iter(approach_types))
    
    def get_ifr_score(self, icao: str) -> int:
        """
        Calculate IFR score for an airport (0-4).
        
        Scoring:
            0 = IFR not permitted (field 207 doesn't contain "IFR")
            1 = IFR permitted but no published procedures
            2 = Has basic procedures (VOR, NDB, LOC)
            3 = Has RNP/RNAV procedures
            4 = Has ILS procedures
        
        Args:
            icao: Airport ICAO code
            
        Returns:
            IFR score from 0 to 4
        """
        if not self._is_ifr_permitted(icao):
            return self.IFR_SCORE_NOT_PERMITTED
        
        best_approach = self._get_best_approach_type(icao)
        
        if best_approach is None:
            return self.IFR_SCORE_PERMITTED
        elif best_approach == "ILS":
            return self.IFR_SCORE_ILS
        elif best_approach in ("RNP", "RNAV"):
            return self.IFR_SCORE_RNP
        else:
            return self.IFR_SCORE_BASIC
    
    def get_hotel_info(self, icao: str) -> Optional[str]:
        """Get hotel availability info for an airport."""
        return self._get_aip_field(icao, self.STD_FIELD_HOTEL)
    
    def get_restaurant_info(self, icao: str) -> Optional[str]:
        """Get restaurant availability info for an airport."""
        return self._get_aip_field(icao, self.STD_FIELD_RESTAURANT)
    
    def _load_euro_aip_model(self):
        """Lazy-load the EuroAipModel (loads entire database)."""
        if self._euro_aip_model is None:
            try:
                from euro_aip.storage import DatabaseStorage

                storage = DatabaseStorage(str(self.db_path))
                self._euro_aip_model = storage.load_model()
            except ImportError:
                # euro_aip not available
                import logging
                logging.warning("euro_aip module not available, AIP data will be limited")
                self._euro_aip_model = False  # Mark as unavailable
            except Exception as e:
                import logging
                logging.error(f"Failed to load euro_aip model: {e}")
                self._euro_aip_model = False  # Mark as unavailable

    def get_airport(self, icao: str) -> Optional[Any]:
        """
        Get euro_aip Airport object for an airport.

        Returns Airport object with procedures, aip_entries, etc.
        Uses cached EuroAipModel for efficient access.

        Args:
            icao: Airport ICAO code

        Returns:
            Airport object from euro_aip, or None if not found/unavailable
        """
        # Load model if not already loaded
        self._load_euro_aip_model()

        # Check if model is available
        if self._euro_aip_model is False:
            return None

        # Get airport from model
        try:
            airport = self._euro_aip_model.airports.where(ident=icao.upper()).first()
            return airport
        except Exception as e:
            import logging
            logging.debug(f"Airport {icao} not found in euro_aip model: {e}")
            return None

    def get_airport_metadata(self, icao: str) -> Dict[str, Any]:
        """
        Get all relevant metadata for an airport.

        Returns dict with:
            - ifr_score: int (0-4)
            - ifr_permitted: bool
            - best_approach_type: str or None
            - hotel_info: str or None
            - restaurant_info: str or None
        """
        icao = icao.upper()

        # Check cache
        if icao in self._cache:
            return self._cache[icao]

        ifr_permitted = self._is_ifr_permitted(icao)
        best_approach = self._get_best_approach_type(icao) if ifr_permitted else None

        metadata = {
            "ifr_score": self.get_ifr_score(icao),
            "ifr_permitted": ifr_permitted,
            "best_approach_type": best_approach,
            "hotel_info": self.get_hotel_info(icao),
            "restaurant_info": self.get_restaurant_info(icao),
        }

        self._cache[icao] = metadata
        return metadata
    
    def get_all_icaos(self) -> Set[str]:
        """Get all ICAO codes in the database."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT DISTINCT icao_code FROM airports WHERE icao_code IS NOT NULL")
        return {row["icao_code"] for row in cursor}

