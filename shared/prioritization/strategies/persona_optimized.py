#!/usr/bin/env python3
"""
Persona-optimized priority strategy.

Uses GAFriendlinessService persona scores to rank airports.
Falls back to basic ranking (procedures, border crossing) if GA data unavailable.
"""
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from euro_aip.models.airport import Airport
from .base import PriorityStrategy, ScoredAirport

if TYPE_CHECKING:
    from shared.airport_tools import ToolContext

class PersonaOptimizedStrategy(PriorityStrategy):
    """
    Persona-optimized priority strategy.

    Ranks airports by GA friendliness score for the selected persona.
    Airports without GA data are ranked lower by basic criteria.

    Persona is passed via context dict:
        context = {"persona_id": "ifr_touring_sr22"}

    Default persona: "ifr_touring_sr22"
    """

    name = "persona_optimized"
    description = "Rank airports by GA friendliness score for selected persona"

    def score(
        self,
        airports: List[Airport],
        context: Optional[Dict[str, Any]] = None,
        tool_context: Optional["ToolContext"] = None,
    ) -> List[ScoredAirport]:
        """Score airports by persona-based GA friendliness."""
        scored: List[ScoredAirport] = []

        # Get persona from context (default to ifr_touring_sr22)
        persona_id = "ifr_touring_sr22"
        if context and "persona_id" in context:
            persona_id = context["persona_id"]

        for airport in airports:
            # Try to get GA persona score
            ga_score = None
            if tool_context and tool_context.ga_friendliness_service:
                try:
                    summary_dict = tool_context.ga_friendliness_service.get_summary_dict(
                        airport.ident,
                        persona_id
                    )
                    if summary_dict.get("has_data") and summary_dict.get("score") is not None:
                        ga_score = summary_dict["score"]
                except Exception:
                    pass  # GA data not available

            # Determine priority level and score
            if ga_score is not None:
                # Airports with GA data: Priority 1, sorted by score (higher is better)
                priority_level = 1
                score = -ga_score  # Negative because we sort ascending
            else:
                # Airports without GA data: Priority 2, sorted by basic criteria
                priority_level = 2

                # Basic scoring: procedures + border crossing
                has_procedures = bool(airport.procedures and len(airport.procedures) > 0)
                has_border = bool(getattr(airport, 'point_of_entry', False))

                if has_border and has_procedures:
                    score = 0  # Best of fallback group
                elif has_procedures:
                    score = 1  # Good
                else:
                    score = 2  # Basic

            # Get distance if available (for secondary sorting/display)
            segment_distance_nm = None
            if context and "segment_distances" in context:
                segment_distance_nm = context["segment_distances"].get(airport.ident)

            scored.append(ScoredAirport(
                airport=airport,
                priority_level=priority_level,
                score=score,
                metadata={
                    "ga_score": ga_score,
                    "persona_id": persona_id,
                    "has_ga_data": ga_score is not None,
                    "segment_distance_nm": segment_distance_nm,
                }
            ))

        # Sort by priority level first, then by score (ascending)
        # For priority 1: lower score (more negative) = higher GA score = better
        # For priority 2: lower score = better basic criteria
        scored.sort(key=lambda x: (x.priority_level, x.score))

        return scored
