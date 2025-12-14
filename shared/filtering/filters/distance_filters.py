#!/usr/bin/env python3
"""
Distance-based filters (e.g., trip distance ranges).
"""
from typing import Any, Optional, TYPE_CHECKING
from euro_aip.models.airport import Airport
from .base import Filter

if TYPE_CHECKING:
    from shared.airport_tools import ToolContext


class TripDistanceFilter(Filter):
    """Filter airports by trip distance (in nautical miles)."""
    name = "trip_distance"
    description = "Filter by trip distance range (dict with 'from' (ICAO code), and optional 'min'/'max' keys in NM)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        context: Optional["ToolContext"] = None,
    ) -> bool:
        if value is None or not isinstance(value, dict):
            return True

        from_icao = value.get("from")
        if from_icao is None:
            return True  # from airport not specified, leave filtering to caller
        from_airport = context.model.airports.where(ident=from_icao.upper()).first()
        if from_airport is None:
            return True  # from airport not found, leave filtering to caller
        _, distance_nm = from_airport.navpoint.haversine_distance(airport.navpoint)


        max_distance = value.get("max")
        min_distance = value.get("min")

        if max_distance is not None and min_distance is not None:
            return min_distance <= distance_nm <= max_distance
        if max_distance is not None:
            return distance_nm <= max_distance
        if min_distance is not None:
            return distance_nm >= min_distance
        return True

