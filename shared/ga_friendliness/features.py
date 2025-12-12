"""
Feature engineering for GA friendliness scoring.

Maps label distributions to normalized feature scores [0, 1].
"""

import logging
import re
from typing import Any, Dict, List, Optional

from .exceptions import FeatureMappingError
from .models import (
    AggregationContext,
    AirportFeatureScores,
    FeatureMappingsConfig,
    ReviewFeatureDefinition,
    AIPFeatureDefinition,
    AspectConfig,
    OntologyConfig,
    ReviewExtraction,
)

logger = logging.getLogger(__name__)


# Aircraft type to MTOW mapping (kg)
AIRCRAFT_MTOW_MAP: Dict[str, int] = {
    # Light singles (0-749 kg band)
    "c150": 726,       # Cessna 150
    "c152": 757,       # Cessna 152
    
    # Light singles (750-1199 kg band)
    "pa28": 1111,      # Piper PA-28
    "c172": 1157,      # Cessna 172
    
    # Complex singles (1200-1499 kg band)
    "c182": 1406,      # Cessna 182
    "m20": 1315,       # Mooney M20
    
    # High-performance singles (1500-1999 kg band)
    "pa32": 1542,      # Piper PA-32
    "sr22": 1633,      # Cirrus SR22
    "c210": 1814,      # Cessna 210
    "da42": 1785,      # Diamond DA42
    "be76": 1769,      # Beech Duchess
    
    # Light twins (2000-3999 kg band)
    "pa34": 2155,      # Piper Seneca
    "be58": 2449,      # Beech Baron
    "tbm85": 3354,     # TBM 850
    "tbm9": 3354,      # TBM 900 series
    "pc6": 2800,       # Pilatus PC-6
    
    # Turboprops/Light jets (4000+ kg band)
    "pc12": 4740,      # Pilatus PC-12
    "c510": 4536,      # Cessna Citation Mustang
    "c525": 5670,      # Citation CJ series
}


def get_mtow_for_aircraft(aircraft_type: str) -> Optional[int]:
    """
    Get MTOW for a known aircraft type.
    
    Args:
        aircraft_type: Aircraft type code (e.g., "c172", "sr22")
    
    Returns:
        MTOW in kg, or None if aircraft type unknown
    """
    return AIRCRAFT_MTOW_MAP.get(aircraft_type.lower())


def get_fee_band_for_mtow(mtow_kg: int) -> str:
    """
    Get fee band name for a given MTOW.
    
    Fee bands:
        - 0-749 kg
        - 750-1199 kg
        - 1200-1499 kg
        - 1500-1999 kg
        - 2000-3999 kg
        - 4000+ kg
    
    Args:
        mtow_kg: MTOW in kg
    
    Returns:
        Fee band name (e.g., "fee_band_0_749kg")
    """
    if mtow_kg < 750:
        return "fee_band_0_749kg"
    elif mtow_kg < 1200:
        return "fee_band_750_1199kg"
    elif mtow_kg < 1500:
        return "fee_band_1200_1499kg"
    elif mtow_kg < 2000:
        return "fee_band_1500_1999kg"
    elif mtow_kg < 4000:
        return "fee_band_2000_3999kg"
    else:
        return "fee_band_4000_plus_kg"


def aggregate_fees_by_band(
    fee_data: Dict[str, Any],
) -> Dict[str, Optional[float]]:
    """
    Aggregate fee data from source into fee bands.
    
    Maps aircraft types from source data to fee bands.
    
    Args:
        fee_data: Fee data dict from source (e.g., airfield.directory aerops)
            Expected format: { "aircraft_type": { "landing": price, ... }, ... }
            or { "aircraft_type": price, ... }
    
    Returns:
        Dict mapping fee band names to average fees
    """
    bands: Dict[str, List[float]] = {
        "fee_band_0_749kg": [],
        "fee_band_750_1199kg": [],
        "fee_band_1200_1499kg": [],
        "fee_band_1500_1999kg": [],
        "fee_band_2000_3999kg": [],
        "fee_band_4000_plus_kg": [],
    }
    
    for aircraft_type, data in fee_data.items():
        mtow = get_mtow_for_aircraft(aircraft_type)
        if mtow is None:
            continue
        
        # Extract landing fee
        if isinstance(data, dict):
            fee = data.get("landing") or data.get("total")
        else:
            fee = data
        
        if fee is not None:
            try:
                fee_value = float(fee)
                band = get_fee_band_for_mtow(mtow)
                bands[band].append(fee_value)
            except (ValueError, TypeError):
                pass
    
    # Calculate averages
    result: Dict[str, Optional[float]] = {}
    for band, fees in bands.items():
        if fees:
            result[band] = sum(fees) / len(fees)
        else:
            result[band] = None
    
    return result


def compute_aip_ifr_score(
    procedures: List[Any],  # List of Procedure objects
    ifr_permitted_field: Optional[str] = None,
) -> int:
    """
    Compute IFR capability score from airport procedures and AIP data.

    This function determines the IFR capability level based on:
    1. Whether IFR operations are permitted (from AIP field 207)
    2. The types of approach procedures available at the airport

    Args:
        procedures: List of Procedure objects from Airport.procedures
        ifr_permitted_field: Value from AIP field 207 ("IFR", "VFR/IFR", "VFR", or None)

    Returns:
        0 = No IFR (VFR only or no IFR permission)
        1 = IFR permitted but no published approach procedures
        2 = Non-precision approaches (VOR/NDB/LOC/LDA/SDF)
        3 = RNP/RNAV approaches
        4 = ILS approaches (highest precision)
    """
    # Check if IFR is permitted
    ifr_permitted = False
    if ifr_permitted_field:
        field_upper = ifr_permitted_field.strip().upper()
        ifr_permitted = 'IFR' in field_upper

    if not ifr_permitted:
        return 0  # VFR only

    # IFR is permitted, now check for approach procedures
    # Filter for approach procedures only
    approaches = [
        p for p in procedures
        if hasattr(p, 'procedure_type') and p.procedure_type.lower() == 'approach'
    ]

    if not approaches:
        return 1  # IFR permitted but no published procedures

    # Check for ILS (highest precision)
    has_ils = any(
        hasattr(p, 'approach_type') and p.approach_type and p.approach_type.upper() == 'ILS'
        for p in approaches
    )
    if has_ils:
        return 4

    # Check for RNP/RNAV
    has_rnp_rnav = any(
        hasattr(p, 'approach_type') and p.approach_type and p.approach_type.upper() in ['RNP', 'RNAV']
        for p in approaches
    )
    if has_rnp_rnav:
        return 3

    # Check for non-precision approaches (VOR, NDB, LOC, LDA, SDF)
    non_precision_types = {'VOR', 'NDB', 'LOC', 'LDA', 'SDF'}
    has_non_precision = any(
        hasattr(p, 'approach_type') and p.approach_type and p.approach_type.upper() in non_precision_types
        for p in approaches
    )
    if has_non_precision:
        return 2

    # Has approaches but unknown/unrecognized type - treat as non-precision
    return 2


def compute_aip_night_available() -> int:
    """
    Compute night operations availability from AIP data.

    NOTE: This is a stub for future implementation.
    Currently always returns 0 (unknown/unavailable).

    Future implementation should check:
    - Runway lighting availability
    - AIP remarks about night operations
    - Operating hours restrictions

    Returns:
        0 = Unknown/not available (current stub behavior)
        1 = Night operations available (future implementation)
    """
    # TODO: Implement night operations detection
    # Possible sources:
    # - AIP field for operating hours
    # - Runway lighting (has_lighted_runway from runway data)
    # - AIP remarks/restrictions
    return 0


# Patterns for hospitality text classification

# Patterns for detecting "at airport" facilities
PAT_AT = re.compile(
    r"""
    ^\s*(?:yes|si|sí|ja|oui)\b
    |
    \b(?:at|on)\s+(?:the\s+)?(ad|aerodrome|airport|airfield|terminal|site)\b
    |
    \bon\s+site\b
    |
    \bin\s+(?:the\s+)?terminals?\b
    |
    \bterminal\s+building\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Patterns for detecting "vicinity" facilities
PAT_VICINITY = re.compile(
    r"""
    \bvicinity\b
    |
    \bnearby\b
    |
    \bnear\s+(?:the\s+)?(ad|aerodrome|airport|airfield)\b
    |
    \bwithin\s+\d+\s*(km|nm|mi|miles)\b
    |
    \b\d+\s*(km|nm|mi|miles)\s*(fm|from)\s+(?:the\s+)?(ad|aerodrome|airport|airfield)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def classify_facility(text: Optional[str]) -> str:
    """
    Classify facility location from AIP text.

    Analyzes text descriptions from AIP to determine whether a facility
    (hotel, restaurant, etc.) is located at the airport, in the vicinity,
    or not available.

    Args:
        text: AIP text describing facility availability

    Returns:
        "at_airport" - Facility is on-site at the airport
        "vicinity" - Facility is nearby/in vicinity
        "none" - No facility or unknown
    """
    if not isinstance(text, str):
        return "none"

    s = text.strip()

    # Empty or explicit "no" indicators
    if not s or s.lower() in {"-", "nil"}:
        return "none"
    if re.match(r"^\s*no\.?\s*$", s, re.IGNORECASE):
        return "none"

    # Check for "at airport" patterns
    if PAT_AT.search(s):
        return "at_airport"

    # Check for "vicinity" patterns
    if PAT_VICINITY.search(s):
        return "vicinity"

    return "none"


def parse_hospitality_text_to_int(text: Optional[str]) -> int:
    """
    Parse AIP hospitality text to integer encoding.

    Converts textual descriptions of hotel/restaurant availability
    into a standardized integer encoding for storage in the database.

    Args:
        text: AIP text describing hotel/restaurant availability

    Returns:
        0 = unknown/none
        1 = vicinity (nearby but not on-site)
        2 = at_airport (on-site facility)
    """
    classification = classify_facility(text)
    if classification == "at_airport":
        return 2
    elif classification == "vicinity":
        return 1
    else:
        return 0


# Default label score mappings
DEFAULT_LABEL_SCORES: Dict[str, Dict[str, float]] = {
    "cost": {
        "cheap": 1.0,
        "reasonable": 0.7,
        "expensive": 0.2,
        "unclear": 0.5,
    },
    "staff": {
        "very_positive": 1.0,
        "positive": 0.8,
        "neutral": 0.5,
        "negative": 0.2,
        "very_negative": 0.0,
    },
    "bureaucracy": {
        "simple": 1.0,
        "moderate": 0.6,
        "complex": 0.2,
    },
    "fuel": {
        "excellent": 1.0,
        "ok": 0.7,
        "poor": 0.3,
        "unavailable": 0.0,
    },
    "transport": {
        "excellent": 1.0,
        "good": 0.8,
        "ok": 0.5,
        "poor": 0.2,
        "none": 0.0,
    },
    "food": {
        "excellent": 1.0,
        "good": 0.8,
        "ok": 0.5,
        "poor": 0.2,
        "none": 0.0,
    },
    "restaurant": {
        "on_site": 1.0,
        "walking": 0.8,
        "nearby": 0.6,
        "available": 0.4,
        "none": 0.0,
    },
    "accommodation": {
        "on_site": 1.0,
        "walking": 0.8,
        "nearby": 0.6,
        "available": 0.4,
        "none": 0.0,
    },
    "overall_experience": {
        "very_positive": 1.0,
        "positive": 0.8,
        "neutral": 0.5,
        "negative": 0.2,
        "very_negative": 0.0,
    },
    "runway": {
        "excellent": 1.0,
        "ok": 0.6,
        "poor": 0.2,
    },
    "noise_neighbours": {
        "not_an_issue": 1.0,
        "minor_concern": 0.6,
        "significant_issue": 0.2,
    },
    "training_traffic": {
        "busy": 0.3,
        "moderate": 0.6,
        "quiet": 0.9,
        "none": 1.0,
    },
    # IFR/VFR operations
    "ifr": {
        "excellent": 1.0,
        "good": 0.8,
        "ok": 0.5,
        "poor": 0.2,
        "unavailable": 0.0,
    },
    "procedure": {
        "well_documented": 1.0,
        "standard": 0.7,
        "complex": 0.4,
        "unclear": 0.2,
    },
    "approach": {
        "excellent": 1.0,
        "good": 0.8,
        "ok": 0.5,
        "poor": 0.2,
    },
    "vfr": {
        "excellent": 1.0,
        "good": 0.8,
        "ok": 0.5,
        "poor": 0.2,
        "restricted": 0.3,
    },
}


class FeatureMapper:
    """
    Maps label distributions to normalized feature scores.

    Uses config-driven approach to convert aspect/label distributions
    into [0, 1] feature scores. All computation is driven by configuration,
    with hard-coded defaults as fallback.
    """

    def __init__(
        self,
        ontology: Optional[OntologyConfig] = None,
        mappings: Optional[FeatureMappingsConfig] = None,
    ):
        """
        Initialize feature mapper.

        Args:
            ontology: Ontology config for validation
            mappings: Custom feature mappings (uses defaults if not provided)
        """
        self.ontology = ontology

        # Use provided config or fall back to defaults
        if mappings is None:
            mappings = self._get_default_config()

        self.config = mappings
        self.review_feature_defs = mappings.review_feature_definitions
        self.aip_feature_defs = mappings.aip_feature_definitions

    def _map_labels_to_score(
        self,
        label_dist: Dict[str, float],
        label_scores: Dict[str, float],
        default: float = 0.5,
    ) -> Optional[float]:
        """
        Map label distribution to weighted score using label score mapping.

        Args:
            label_dist: Distribution of labels (label -> count/weight)
            label_scores: Mapping of labels to scores
            default: Default score for unknown labels

        Returns:
            Weighted score [0, 1] or None if no valid data
        """
        if not label_dist:
            return None

        total_weight = 0.0
        weighted_score = 0.0

        for label, weight in label_dist.items():
            # Get score for this label, use default if not in mapping
            score = label_scores.get(label, default)
            weighted_score += score * weight
            total_weight += weight

        if total_weight == 0:
            return None

        return weighted_score / total_weight

    def _compute_review_feature(
        self,
        definition: "ReviewFeatureDefinition",
        distributions: Dict[str, Dict[str, float]],
    ) -> Optional[float]:
        """
        Compute a single review feature from its definition.

        Generic computation based on config - supports multiple aspects
        with different weights combined via weighted average.

        Args:
            definition: Review feature definition from config
            distributions: Dict mapping aspect -> label -> count

        Returns:
            Feature score [0, 1] or None if no valid data
        """
        if definition.aggregation == "weighted_label_mapping":
            total_score = 0.0
            total_weight = 0.0

            for aspect_config in definition.aspects:
                aspect_name = aspect_config.name
                aspect_weight = aspect_config.weight

                # Get label distribution for this aspect
                label_dist = distributions.get(aspect_name, {})
                if not label_dist:
                    continue

                # Get label scores for this aspect
                # Handle both flat dict and nested-by-aspect dict
                label_scores = definition.label_scores
                if isinstance(label_scores, dict):
                    # Check if nested by aspect name
                    if aspect_name in label_scores and isinstance(
                        label_scores[aspect_name], dict
                    ):
                        label_scores = label_scores[aspect_name]

                # Map labels to score using config
                aspect_score = self._map_labels_to_score(label_dist, label_scores)

                if aspect_score is not None:
                    total_score += aspect_weight * aspect_score
                    total_weight += aspect_weight

            return total_score / total_weight if total_weight > 0 else None

        return None

    def _compute_aip_feature(
        self,
        definition: "AIPFeatureDefinition",
        aip_data: Dict[str, Any],
    ) -> Optional[float]:
        """
        Compute a single AIP feature from its definition.

        Supports multiple computation methods based on config.

        Args:
            definition: AIP feature definition from config
            aip_data: Dict with raw AIP field values

        Returns:
            Feature score [0, 1] or None if data not available
        """
        if definition.computation == "lookup_table":
            # Simple value lookup
            field_name = definition.raw_fields[0]
            value = aip_data.get(field_name)
            if value is None:
                return None

            return definition.value_mapping.get(str(value))

        elif definition.computation == "weighted_component_sum":
            # Weighted combination of multiple fields
            total_score = 0.0
            total_weight = 0.0

            for field_name in definition.raw_fields:
                value = aip_data.get(field_name)
                if value is None:
                    continue

                # Map value to score
                component_score = definition.component_mappings[field_name].get(
                    str(value)
                )
                if component_score is None:
                    continue

                # Get weight
                weight = definition.component_weights[field_name]

                total_score += weight * component_score
                total_weight += weight

            return total_score / total_weight if total_weight > 0 else None

        return None

    def compute_review_feature_scores(
        self,
        icao: str,
        distributions: Dict[str, Dict[str, float]],
    ) -> Dict[str, Optional[float]]:
        """
        Compute ALL review-derived features from config definitions.

        No hard-coded logic - everything driven by config.

        Args:
            icao: Airport ICAO code
            distributions: Dict mapping aspect -> label -> count

        Returns:
            Dict mapping feature_name -> score (0-1) or None
        """
        scores = {}
        for feature_name, definition in self.review_feature_defs.items():
            scores[feature_name] = self._compute_review_feature(
                definition, distributions
            )
        return scores

    def compute_aip_feature_scores(
        self,
        icao: str,
        aip_data: Dict[str, Any],
    ) -> Dict[str, Optional[float]]:
        """
        Compute ALL AIP-derived features from config definitions.

        No hard-coded logic - everything driven by config.

        Args:
            icao: Airport ICAO code
            aip_data: Dict with keys like 'aip_ifr_available', 'aip_hotel_info', etc.

        Returns:
            Dict mapping feature_name -> score (0-1) or None
        """
        scores = {}
        for feature_name, definition in self.aip_feature_defs.items():
            scores[feature_name] = self._compute_aip_feature(definition, aip_data)
        return scores

    def _get_default_config(self) -> FeatureMappingsConfig:
        """
        Get hard-coded default feature mapping configuration.

        This serves as a fallback when no external config file is provided.
        Matches the structure described in the design document.

        Returns:
            Default FeatureMappingsConfig
        """
        # Review feature definitions
        review_features = {
            "review_cost_score": ReviewFeatureDefinition(
                description="Cost/fee friendliness from pilot reviews",
                aspects=[AspectConfig(name="cost", weight=1.0)],
                aggregation="weighted_label_mapping",
                label_scores=DEFAULT_LABEL_SCORES["cost"],
            ),
            "review_hassle_score": ReviewFeatureDefinition(
                description="Bureaucracy/paperwork burden from reviews",
                aspects=[
                    AspectConfig(name="bureaucracy", weight=0.7),
                    AspectConfig(name="staff", weight=0.3),
                ],
                aggregation="weighted_label_mapping",
                label_scores={
                    "bureaucracy": DEFAULT_LABEL_SCORES["bureaucracy"],
                    "staff": DEFAULT_LABEL_SCORES["staff"],
                },
            ),
            "review_review_score": ReviewFeatureDefinition(
                description="Overall experience from reviews",
                aspects=[AspectConfig(name="overall_experience", weight=1.0)],
                aggregation="weighted_label_mapping",
                label_scores=DEFAULT_LABEL_SCORES["overall_experience"],
            ),
            "review_ops_ifr_score": ReviewFeatureDefinition(
                description="IFR operations quality from reviews",
                aspects=[
                    AspectConfig(name="ifr", weight=0.6),
                    AspectConfig(name="procedure", weight=0.2),
                    AspectConfig(name="approach", weight=0.2),
                ],
                aggregation="weighted_label_mapping",
                label_scores={
                    "ifr": DEFAULT_LABEL_SCORES["ifr"],
                    "procedure": DEFAULT_LABEL_SCORES["procedure"],
                    "approach": DEFAULT_LABEL_SCORES["approach"],
                },
            ),
            "review_ops_vfr_score": ReviewFeatureDefinition(
                description="VFR/runway quality from reviews",
                aspects=[
                    AspectConfig(name="runway", weight=0.6),
                    AspectConfig(name="vfr", weight=0.4),
                ],
                aggregation="weighted_label_mapping",
                label_scores={
                    "runway": DEFAULT_LABEL_SCORES["runway"],
                    "vfr": DEFAULT_LABEL_SCORES["vfr"],
                },
            ),
            "review_access_score": ReviewFeatureDefinition(
                description="Transportation/accessibility from reviews",
                aspects=[AspectConfig(name="transport", weight=1.0)],
                aggregation="weighted_label_mapping",
                label_scores=DEFAULT_LABEL_SCORES["transport"],
            ),
            "review_fun_score": ReviewFeatureDefinition(
                description="Fun factor from food/vibe reviews",
                aspects=[
                    AspectConfig(name="food", weight=0.6),
                    AspectConfig(name="overall_experience", weight=0.4),
                ],
                aggregation="weighted_label_mapping",
                label_scores={
                    "food": DEFAULT_LABEL_SCORES["food"],
                    "overall_experience": DEFAULT_LABEL_SCORES["overall_experience"],
                },
            ),
            "review_hospitality_score": ReviewFeatureDefinition(
                description="Restaurant/hotel availability from reviews",
                aspects=[
                    AspectConfig(name="restaurant", weight=0.6),
                    AspectConfig(name="accommodation", weight=0.4),
                ],
                aggregation="weighted_label_mapping",
                label_scores={
                    "restaurant": DEFAULT_LABEL_SCORES["restaurant"],
                    "accommodation": DEFAULT_LABEL_SCORES["accommodation"],
                },
            ),
        }

        # AIP feature definitions
        aip_features = {
            "aip_ops_ifr_score": AIPFeatureDefinition(
                description="IFR capability from official AIP data",
                raw_fields=["aip_ifr_available"],
                computation="lookup_table",
                value_mapping={
                    "0": 0.1,  # VFR-only, still useful as diversion
                    "1": 0.4,  # IFR permitted, no procedures
                    "2": 0.6,  # Non-precision
                    "3": 0.8,  # RNP/RNAV
                    "4": 1.0,  # ILS
                },
                notes="0.1 for VFR-only preserves utility as diversion option",
            ),
            "aip_hospitality_score": AIPFeatureDefinition(
                description="Hotel/restaurant from official AIP data",
                raw_fields=["aip_hotel_info", "aip_restaurant_info"],
                computation="weighted_component_sum",
                component_mappings={
                    "aip_hotel_info": {"0": 0.0, "1": 0.6, "2": 1.0},
                    "aip_restaurant_info": {"0": 0.0, "1": 0.6, "2": 1.0},
                },
                component_weights={
                    "aip_hotel_info": 0.4,
                    "aip_restaurant_info": 0.6,
                },
            ),
        }

        return FeatureMappingsConfig(
            version="2.0",
            description="Default feature mappings (hard-coded fallback)",
            review_feature_definitions=review_features,
            aip_feature_definitions=aip_features,
        )


def apply_bayesian_smoothing(
    score: float,
    sample_count: int,
    prior: float = 0.5,
    strength: float = 10.0,
) -> float:
    """
    Apply Bayesian smoothing to a score.
    
    For airports with few reviews, pulls score toward the prior (global average).
    
    Formula: smoothed = (k * prior + n * score) / (k + n)
    where k = strength, n = sample_count
    
    Args:
        score: Raw score
        sample_count: Number of samples contributing to score
        prior: Prior (global average) to smooth toward
        strength: Smoothing strength (higher = more smoothing)
    
    Returns:
        Smoothed score
    """
    if sample_count == 0:
        return prior
    
    return (strength * prior + sample_count * score) / (strength + sample_count)

