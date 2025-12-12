"""
UI configuration for GA friendliness display.

This module is the source of truth for:
- Feature display names and descriptions
- Relevance bucket colors (thresholds computed dynamically from quartiles)

These values are served via API to ensure frontend consistency.
"""

from typing import Dict, List

from .personas import FEATURE_NAMES


# --- Feature Display Names ---
# Map internal feature names to user-friendly display names

FEATURE_DISPLAY_NAMES: Dict[str, str] = {
    # Review-derived features
    "review_cost_score": "Cost",
    "review_hassle_score": "Low Hassle",
    "review_review_score": "Reviews",
    "review_ops_ifr_score": "IFR Ops (Reviews)",
    "review_ops_vfr_score": "VFR Ops",
    "review_access_score": "Access",
    "review_fun_score": "Fun Factor",
    "review_hospitality_score": "Hospitality (Reviews)",

    # AIP-derived features
    "aip_ops_ifr_score": "IFR Ops (Official)",
    "aip_hospitality_score": "Hospitality (Official)",
}


# --- Feature Descriptions ---
# Explain what each feature measures (higher = better for all)

FEATURE_DESCRIPTIONS: Dict[str, str] = {
    # Review-derived features
    "review_cost_score": "Lower landing/handling fees based on pilot reviews = higher score",
    "review_hassle_score": "Less bureaucracy and simpler procedures based on pilot reviews = higher score",
    "review_review_score": "Better pilot reviews and ratings = higher score",
    "review_ops_ifr_score": "Better IFR operations based on pilot experience = higher score",
    "review_ops_vfr_score": "Better VFR operations environment based on pilot reviews = higher score",
    "review_access_score": "Better transport links and accessibility based on pilot reviews = higher score",
    "review_fun_score": "More interesting destination and scenery based on pilot reviews = higher score",
    "review_hospitality_score": "Better restaurant/accommodation based on pilot reviews = higher score",

    # AIP-derived features
    "aip_ops_ifr_score": "Official IFR capability (approaches, procedures, night ops) = higher score",
    "aip_hospitality_score": "Official hotel/restaurant information from AIP = higher score",
}


# --- Relevance Bucket Configuration ---
# Colors only - thresholds computed dynamically from quartiles on the frontend

RELEVANCE_BUCKETS: List[Dict[str, str]] = [
    {"id": "top-quartile", "label": "Most Relevant", "color": "#27ae60"},      # Green - top 25%
    {"id": "second-quartile", "label": "Relevant", "color": "#3498db"},        # Blue - 50-75%
    {"id": "third-quartile", "label": "Less Relevant", "color": "#e67e22"},    # Orange - 25-50%
    {"id": "bottom-quartile", "label": "Least Relevant", "color": "#e74c3c"},  # Red - bottom 25%
    {"id": "unknown", "label": "Unknown", "color": "#95a5a6"},                  # Gray - no data
]


# --- API Config Response Builder ---

def get_ui_config() -> Dict:
    """
    Build complete UI configuration for API response.
    
    Returns:
        Dict with all UI configuration needed by frontend
    """
    return {
        "feature_names": FEATURE_NAMES,
        "feature_display_names": FEATURE_DISPLAY_NAMES,
        "feature_descriptions": FEATURE_DESCRIPTIONS,
        "relevance_buckets": RELEVANCE_BUCKETS,
    }


# --- Validation ---

def validate_config_consistency() -> List[str]:
    """
    Validate that all feature names have display names and descriptions.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    for feature in FEATURE_NAMES:
        if feature not in FEATURE_DISPLAY_NAMES:
            errors.append(f"Missing display name for feature: {feature}")
        if feature not in FEATURE_DESCRIPTIONS:
            errors.append(f"Missing description for feature: {feature}")
    
    # Check for extra keys in display names/descriptions
    for key in FEATURE_DISPLAY_NAMES:
        if key not in FEATURE_NAMES:
            errors.append(f"Extra display name for unknown feature: {key}")
    
    for key in FEATURE_DESCRIPTIONS:
        if key not in FEATURE_NAMES:
            errors.append(f"Extra description for unknown feature: {key}")
    
    # Validate bucket structure
    bucket_ids = [b["id"] for b in RELEVANCE_BUCKETS]
    if "unknown" not in bucket_ids:
        errors.append("Missing 'unknown' bucket for unscored airports")
    
    for bucket in RELEVANCE_BUCKETS:
        if "id" not in bucket or "label" not in bucket or "color" not in bucket:
            errors.append(f"Bucket missing required fields: {bucket}")
        elif not bucket["color"].startswith("#"):
            errors.append(f"Bucket color should be hex: {bucket}")
    
    return errors

