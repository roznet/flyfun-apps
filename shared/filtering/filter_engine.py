#!/usr/bin/env python3
"""
Filter engine for applying multiple filters to airports.
"""
import logging
from typing import Dict, Any, List, Iterable, Optional, TYPE_CHECKING
from euro_aip.models.airport import Airport

from .filters import (
    Filter,
    CountryFilter,
    HasProceduresFilter,
    HasAipDataFilter,
    HasHardRunwayFilter,
    PointOfEntryFilter,
    ExcludeLargeAirportsFilter,
    MaxRunwayLengthFilter,
    MinRunwayLengthFilter,
    HasAvgasFilter,
    HasJetAFilter,
    MaxLandingFeeFilter,
    TripDistanceFilter,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from shared.tool_context import ToolContext


class FilterRegistry:
    """Registry of all available filters."""

    _filters: Dict[str, Filter] = {}

    @classmethod
    def register(cls, filter_instance: Filter):
        """Register a filter by its name."""
        cls._filters[filter_instance.name] = filter_instance
        logger.debug(f"Registered filter: {filter_instance.name}")

    @classmethod
    def get(cls, name: str) -> Optional[Filter]:
        """Get a filter by name."""
        return cls._filters.get(name)

    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered filter names."""
        return list(cls._filters.keys())

    @classmethod
    def get_all(cls) -> Dict[str, Filter]:
        """Get all registered filters."""
        return cls._filters.copy()


# Auto-register all filters
#
# IMPORTANT: If you add or rename a filter that should be exposed to the LLM planner,
# you MUST also update the filter list in:
#   configs/aviation_agent/prompts/planner_v1.md
#
# Filters NOT exposed to LLM (internal use only):
#   - has_aip_data, exclude_large_airports, trip_distance
#
FilterRegistry.register(CountryFilter())
FilterRegistry.register(HasProceduresFilter())
FilterRegistry.register(HasAipDataFilter())
FilterRegistry.register(HasHardRunwayFilter())
FilterRegistry.register(PointOfEntryFilter())
FilterRegistry.register(ExcludeLargeAirportsFilter())
FilterRegistry.register(MaxRunwayLengthFilter())
FilterRegistry.register(MinRunwayLengthFilter())
FilterRegistry.register(HasAvgasFilter())
FilterRegistry.register(HasJetAFilter())
FilterRegistry.register(MaxLandingFeeFilter())
FilterRegistry.register(TripDistanceFilter())

logger.info(f"Filter registry initialized with {len(FilterRegistry.list_all())} filters")


class FilterEngine:
    """
    Engine for applying filters to airports.

    Usage:
        engine = FilterEngine(context=ctx)
        filtered = engine.apply(airports, {"country": "FR", "has_avgas": True})
    """

    def __init__(
        self,
        context: Optional["ToolContext"] = None,
    ):
        """
        Initialize filter engine.

        Args:
            context: ToolContext with services for filters that need them
        """
        self.context = context

    def apply(
        self,
        airports: Iterable[Airport],
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Airport]:
        """
        Apply multiple filters to a list of airports.

        Args:
            airports: Iterable of Airport objects
            filters: Dict of filter_name -> filter_value

        Returns:
            Filtered list of airports

        Example:
            filters = {
                "country": "FR",
                "has_hard_runway": True,
                "max_runway_length_ft": 8000,
                "has_avgas": True,
                "max_landing_fee": 50
            }
        """
        if not filters:
            return list(airports)

        filtered: List[Airport] = []
        filters_applied = []

        for airport in airports:
            passes_all_filters = True

            for filter_name, filter_value in filters.items():
                # Get the filter from registry
                filter_obj = FilterRegistry.get(filter_name)

                if not filter_obj:
                    logger.warning(f"Unknown filter: {filter_name}, skipping")
                    continue

                # Track which filters are being applied (for logging)
                if filter_name not in filters_applied:
                    filters_applied.append(filter_name)

                # Apply the filter
                try:
                    if not filter_obj.apply(
                        airport,
                        filter_value,
                        self.context,
                    ):
                        passes_all_filters = False
                        break  # Airport failed this filter, no need to check others
                except Exception as e:
                    logger.error(f"Error applying filter {filter_name} to {airport.ident}: {e}")
                    passes_all_filters = False
                    break

            if passes_all_filters:
                filtered.append(airport)

        logger.info(f"Filters applied: {filters_applied} | Input: {len(list(airports))} airports → Output: {len(filtered)} airports")

        return filtered

    def get_available_filters(self) -> Dict[str, str]:
        """Get all available filters with descriptions."""
        return {
            name: filter_obj.description
            for name, filter_obj in FilterRegistry.get_all().items()
        }
