#!/usr/bin/env python3
"""
Cost-optimized priority strategy.

Prioritizes airports by:
1. Border crossing + procedures (best for international flights)
2. Procedures only (good for IFR)
3. Others

Within each priority, sorts by landing fee (cheapest first).
"""
from typing import List, Dict, Any, Optional
from euro_aip.models.airport import Airport
from euro_aip.storage.enrichment_storage import EnrichmentStorage
from .base import PriorityStrategy, ScoredAirport


class CostOptimizedStrategy(PriorityStrategy):
    """
    Cost-optimized priority strategy.

    Priority 1: Border crossing + procedures (most useful)
    Priority 2: Procedures only (good for IFR)
    Priority 3: Others

    Within each priority: Sort by landing fee (lowest first)
    """

    name = "cost_optimized"
    description = "Prioritize by usefulness (border crossing + procedures), then sort by landing fees"

    def score(
        self,
        airports: List[Airport],
        enrichment_storage: Optional[EnrichmentStorage] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[ScoredAirport]:
        """Score airports by cost within priority levels."""
        scored: List[ScoredAirport] = []

        for airport in airports:
            # Determine priority level
            has_procedures = bool(airport.procedures and len(airport.procedures) > 0)
            has_border = bool(getattr(airport, 'point_of_entry', False))

            if has_border and has_procedures:
                priority_level = 1  # Best
            elif has_procedures:
                priority_level = 2  # Good
            else:
                priority_level = 3  # OK

            # Get landing fee for sorting (C172 as default)
            landing_fee = 999999.0  # High default for missing data
            if enrichment_storage:
                try:
                    pricing = enrichment_storage.get_pricing_data(airport.ident)
                    if pricing:
                        fee = pricing.get('landing_fee_c172')
                        if fee is not None:
                            try:
                                landing_fee = float(fee)
                            except (TypeError, ValueError):
                                pass
                except Exception:
                    # Pricing data not available (table doesn't exist or other error)
                    # This is expected if pricing hasn't been synced yet
                    pass

            # Get distance if available from context
            distance_nm = None
            if context and 'route_distances' in context:
                distance_nm = context['route_distances'].get(airport.ident)

            # Score = landing fee (lower is better)
            # If landing fee is missing, use distance as secondary sort
            if landing_fee < 999999:
                score = landing_fee
            elif distance_nm is not None:
                score = 900000 + distance_nm  # High base + distance
            else:
                score = 999999.0

            scored.append(ScoredAirport(
                airport=airport,
                priority_level=priority_level,
                score=score,
                metadata={
                    "has_border": has_border,
                    "has_procedures": has_procedures,
                    "landing_fee": landing_fee if landing_fee < 999999 else None,
                    "distance_nm": distance_nm
                }
            ))

        # Sort by priority level first, then by score (ascending)
        scored.sort(key=lambda x: (x.priority_level, x.score))

        return scored
