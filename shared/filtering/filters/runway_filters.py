#!/usr/bin/env python3
"""
Runway-related filters (length, surface, etc.)
"""
from typing import Any, Optional
from euro_aip.models.airport import Airport
from euro_aip.storage.enrichment_storage import EnrichmentStorage
from .base import Filter


class MaxRunwayLengthFilter(Filter):
    """Filter airports by maximum runway length."""
    name = "max_runway_length_ft"
    requires_enrichment = False
    description = "Filter by maximum runway length in feet (e.g., 8000)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if value is None:
            return True

        try:
            max_length = float(value)
        except (TypeError, ValueError):
            return True

        longest_runway = getattr(airport, "longest_runway_length_ft", None)
        if longest_runway is None:
            return False  # No runway data, exclude

        return longest_runway <= max_length


class MinRunwayLengthFilter(Filter):
    """Filter airports by minimum runway length."""
    name = "min_runway_length_ft"
    requires_enrichment = False
    description = "Filter by minimum runway length in feet (e.g., 3000)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if value is None:
            return True

        try:
            min_length = float(value)
        except (TypeError, ValueError):
            return True

        longest_runway = getattr(airport, "longest_runway_length_ft", None)
        if longest_runway is None:
            return False  # No runway data, exclude

        return longest_runway >= min_length
