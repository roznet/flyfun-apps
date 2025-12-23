#!/usr/bin/env python3
"""
Persona-optimized priority strategy.

Uses distance bucketing with persona scores for ranking airports.
- Location search: bucket by distance from point, sort by persona within bucket
- Route search: bucket by position along route (halfway, near_origin, near_destination), sort by persona

Designed to be extensible for future combined scoring approaches.
"""
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from euro_aip.models.airport import Airport
from .base import PriorityStrategy, ScoredAirport

if TYPE_CHECKING:
    from shared.tool_context import ToolContext


class PersonaOptimizedStrategy(PriorityStrategy):
    """
    Persona-optimized priority strategy with distance bucketing.

    For location searches:
        - Buckets airports by distance from search point
        - Within each bucket, sorts by persona score (highest first)
        - Closer airports always rank higher than farther ones

    For route searches:
        - Buckets airports by position along route (based on sort_by parameter)
        - Within each bucket, sorts by persona score (highest first)
        - Default: "halfway" - airports near middle of route rank higher

    Context parameters:
        persona_id: str - Persona for GA scoring (default: "ifr_touring_sr22")

        For location search:
            point_distances: Dict[str, float] - Distance from point to each airport

        For route search:
            enroute_distances: Dict[str, float] - Distance along route from origin
            total_route_distance_nm: float - Total route length
            sort_by: str - "halfway" (default), "near_origin", "near_destination"
    """

    name = "persona_optimized"
    description = "Rank airports by distance buckets with persona score sorting"

    # Distance buckets for location search (nm)
    # Results in buckets: 0-15, 15-30, 30-50, 50-100, 100+
    LOCATION_DISTANCE_BUCKETS = [15, 30, 50, 100]

    # Position buckets for route search (percentage of route from ideal position)
    # Results in buckets: 0-10%, 10-20%, 20-35%, 35%+
    ROUTE_POSITION_BUCKETS = [0.10, 0.20, 0.35]

    def score(
        self,
        airports: List[Airport],
        context: Optional[Dict[str, Any]] = None,
        tool_context: Optional["ToolContext"] = None,
    ) -> List[ScoredAirport]:
        """Score airports based on search type detected from context."""
        context = context or {}

        # Detect search type and delegate
        if "point_distances" in context:
            return self._score_location_search(airports, context, tool_context)
        elif "enroute_distances" in context:
            return self._score_route_search(airports, context, tool_context)
        else:
            # Fallback to basic persona scoring (no distance info)
            return self._score_basic(airports, context, tool_context)

    def _get_ga_score(
        self,
        airport: Airport,
        persona_id: str,
        tool_context: Optional["ToolContext"]
    ) -> Optional[float]:
        """Get GA friendliness score for airport, or None if unavailable."""
        if not tool_context or not tool_context.ga_friendliness_service:
            return None
        try:
            summary_dict = tool_context.ga_friendliness_service.get_summary_dict(
                airport.ident,
                persona_id
            )
            if summary_dict.get("has_data") and summary_dict.get("score") is not None:
                return float(summary_dict["score"])
        except Exception:
            pass
        return None

    def _get_basic_score(self, airport: Airport) -> float:
        """Fallback score when no GA data: based on procedures and border crossing."""
        has_procedures = bool(airport.procedures and len(airport.procedures) > 0)
        has_border = bool(getattr(airport, 'point_of_entry', False))

        if has_border and has_procedures:
            return 80.0  # Treat as decent GA score equivalent
        elif has_procedures:
            return 60.0
        elif has_border:
            return 50.0
        else:
            return 30.0

    def _get_distance_bucket(self, distance_nm: float) -> int:
        """Get bucket index for a distance. Lower bucket = closer = better."""
        for i, threshold in enumerate(self.LOCATION_DISTANCE_BUCKETS):
            if distance_nm <= threshold:
                return i
        return len(self.LOCATION_DISTANCE_BUCKETS)

    def _get_position_bucket(self, position_deviation: float, total_distance: float) -> int:
        """Get bucket index for route position deviation. Lower = closer to target = better."""
        if total_distance <= 0:
            return 0
        deviation_pct = position_deviation / total_distance
        for i, threshold in enumerate(self.ROUTE_POSITION_BUCKETS):
            if deviation_pct <= threshold:
                return i
        return len(self.ROUTE_POSITION_BUCKETS)

    def _score_location_search(
        self,
        airports: List[Airport],
        context: Dict[str, Any],
        tool_context: Optional["ToolContext"]
    ) -> List[ScoredAirport]:
        """
        Score airports for location search.

        Bucket by distance, then sort by persona within each bucket.
        Closer airports always rank higher.
        """
        scored: List[ScoredAirport] = []
        point_distances = context.get("point_distances", {})
        persona_id = context.get("persona_id", "ifr_touring_sr22")

        for airport in airports:
            distance_nm = point_distances.get(airport.ident, 9999.0)
            bucket = self._get_distance_bucket(distance_nm)

            # Get persona score (or fallback)
            ga_score = self._get_ga_score(airport, persona_id, tool_context)
            effective_score = ga_score if ga_score is not None else self._get_basic_score(airport)

            scored.append(ScoredAirport(
                airport=airport,
                priority_level=bucket,  # Lower bucket = closer = higher priority
                score=-effective_score,  # Negative so higher persona = lower score = better
                distance_nm=distance_nm,
                metadata={
                    "ga_score": ga_score,
                    "effective_score": effective_score,
                    "persona_id": persona_id,
                    "has_ga_data": ga_score is not None,
                    "distance_nm": distance_nm,
                    "bucket": bucket,
                }
            ))

        # Sort by: bucket (distance) → persona score → exact distance (tiebreaker)
        scored.sort(key=lambda x: (x.priority_level, x.score, x.distance_nm))
        return scored

    def _score_route_search(
        self,
        airports: List[Airport],
        context: Dict[str, Any],
        tool_context: Optional["ToolContext"]
    ) -> List[ScoredAirport]:
        """
        Score airports for route search.

        Bucket by position along route (based on sort_by parameter),
        then sort by persona within each bucket.
        """
        scored: List[ScoredAirport] = []
        enroute_distances = context.get("enroute_distances", {})
        segment_distances = context.get("segment_distances", {})
        total_distance = context.get("total_route_distance_nm", 0.0)
        sort_by = context.get("sort_by", "halfway")
        persona_id = context.get("persona_id", "ifr_touring_sr22")

        # Calculate target position based on sort_by
        if sort_by == "near_origin":
            target_position = 0.0
        elif sort_by == "near_destination":
            target_position = total_distance
        elif sort_by == "halfway":
            target_position = total_distance / 2.0
        else:
            # Default to halfway
            target_position = total_distance / 2.0

        for airport in airports:
            enroute_nm = enroute_distances.get(airport.ident, 9999.0)
            segment_nm = segment_distances.get(airport.ident, 9999.0)

            # Position deviation from target
            position_deviation = abs(enroute_nm - target_position)
            bucket = self._get_position_bucket(position_deviation, total_distance)

            # Get persona score (or fallback)
            ga_score = self._get_ga_score(airport, persona_id, tool_context)
            effective_score = ga_score if ga_score is not None else self._get_basic_score(airport)

            scored.append(ScoredAirport(
                airport=airport,
                priority_level=bucket,  # Lower bucket = closer to target position
                score=-effective_score,  # Negative so higher persona = lower score = better
                distance_nm=segment_nm,  # Use segment distance for metadata/tiebreaker
                metadata={
                    "ga_score": ga_score,
                    "effective_score": effective_score,
                    "persona_id": persona_id,
                    "has_ga_data": ga_score is not None,
                    "enroute_distance_nm": enroute_nm,
                    "segment_distance_nm": segment_nm,
                    "position_deviation_nm": position_deviation,
                    "target_position_nm": target_position,
                    "bucket": bucket,
                    "sort_by": sort_by,
                }
            ))

        # Sort by: position bucket → persona score → segment distance (tiebreaker)
        scored.sort(key=lambda x: (x.priority_level, x.score, x.distance_nm))
        return scored

    def _score_basic(
        self,
        airports: List[Airport],
        context: Dict[str, Any],
        tool_context: Optional["ToolContext"]
    ) -> List[ScoredAirport]:
        """Fallback scoring when no distance info available. Sort by persona only."""
        scored: List[ScoredAirport] = []
        persona_id = context.get("persona_id", "ifr_touring_sr22")

        for airport in airports:
            ga_score = self._get_ga_score(airport, persona_id, tool_context)
            effective_score = ga_score if ga_score is not None else self._get_basic_score(airport)

            scored.append(ScoredAirport(
                airport=airport,
                priority_level=1 if ga_score is not None else 2,
                score=-effective_score,
                distance_nm=9999.0,
                metadata={
                    "ga_score": ga_score,
                    "effective_score": effective_score,
                    "persona_id": persona_id,
                    "has_ga_data": ga_score is not None,
                }
            ))

        scored.sort(key=lambda x: (x.priority_level, x.score))
        return scored


# Future extension point for combined scoring
class CombinedScoreStrategy(PersonaOptimizedStrategy):
    """
    Alternative strategy using combined distance + persona scoring.

    Not yet implemented - placeholder for future use.

    Would compute: combined = distance_weight * norm_distance + persona_weight * (1 - norm_persona)
    """

    name = "combined_score"
    description = "Rank airports by combined distance and persona score"

    # Weights for combined scoring (sum to 1.0)
    DISTANCE_WEIGHT = 0.6
    PERSONA_WEIGHT = 0.4

    def _compute_combined_score(
        self,
        distance_nm: float,
        max_distance_nm: float,
        persona_score: float
    ) -> float:
        """
        Compute combined score (lower = better).

        Args:
            distance_nm: Distance to airport
            max_distance_nm: Maximum distance for normalization
            persona_score: GA persona score (0-100, higher = better)

        Returns:
            Combined score (0-1, lower = better)
        """
        # Normalize distance (0-1, lower = better)
        norm_distance = min(distance_nm / max_distance_nm, 1.0) if max_distance_nm > 0 else 0.0

        # Normalize persona (0-1, higher = better, so invert)
        norm_persona = persona_score / 100.0 if persona_score else 0.0

        # Combined score (lower = better)
        return self.DISTANCE_WEIGHT * norm_distance + self.PERSONA_WEIGHT * (1.0 - norm_persona)
