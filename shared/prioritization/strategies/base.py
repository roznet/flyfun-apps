#!/usr/bin/env python3
"""
Base class for prioritization strategies.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from euro_aip.models.airport import Airport
from euro_aip.storage.enrichment_storage import EnrichmentStorage


@dataclass
class ScoredAirport:
    """An airport with priority score and sort keys."""
    airport: Airport
    priority_level: int  # 1 = highest priority, 3 = lowest
    score: float  # Within priority level, lower score = better (e.g., lower cost, shorter distance)
    metadata: Dict[str, Any]  # Additional info (landing_fee, distance, etc.)


class PriorityStrategy(ABC):
    """
    Base class for airport prioritization strategies.

    Each strategy defines how to score and sort airports based on different criteria.
    """

    name: str = "base_strategy"
    description: str = "Base priority strategy"

    @abstractmethod
    def score(
        self,
        airports: List[Airport],
        enrichment_storage: Optional[EnrichmentStorage] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[ScoredAirport]:
        """
        Score airports and assign priority levels.

        Args:
            airports: List of airports to score
            enrichment_storage: Optional enrichment data
            context: Optional context (e.g., {"route_distances": {...}})

        Returns:
            List of ScoredAirport objects, sorted by priority then score
        """
        raise NotImplementedError

    def __repr__(self):
        return f"<PriorityStrategy: {self.name}>"
