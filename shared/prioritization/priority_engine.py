#!/usr/bin/env python3
"""
Priority engine for scoring and sorting airports.
"""
import logging
from typing import List, Dict, Any, Optional
from euro_aip.models.airport import Airport
from euro_aip.storage.enrichment_storage import EnrichmentStorage

from .strategies import PriorityStrategy, CostOptimizedStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry of prioritization strategies."""

    _strategies: Dict[str, PriorityStrategy] = {}

    @classmethod
    def register(cls, strategy: PriorityStrategy):
        """Register a strategy."""
        cls._strategies[strategy.name] = strategy
        logger.debug(f"Registered strategy: {strategy.name}")

    @classmethod
    def get(cls, name: str) -> Optional[PriorityStrategy]:
        """Get a strategy by name."""
        return cls._strategies.get(name)

    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered strategies."""
        return list(cls._strategies.keys())


# Auto-register strategies
StrategyRegistry.register(CostOptimizedStrategy())

logger.info(f"Strategy registry initialized with {len(StrategyRegistry.list_all())} strategies")


class PriorityEngine:
    """
    Engine for prioritizing and sorting airports.

    Usage:
        engine = PriorityEngine(enrichment_storage=storage)
        sorted_airports = engine.apply(airports, strategy="cost_optimized")
    """

    def __init__(self, enrichment_storage: Optional[EnrichmentStorage] = None):
        """Initialize priority engine."""
        self.enrichment_storage = enrichment_storage

    def apply(
        self,
        airports: List[Airport],
        strategy: str = "cost_optimized",
        context: Optional[Dict[str, Any]] = None,
        max_results: int = 20
    ) -> List[Airport]:
        """
        Apply priority strategy and return sorted airports.

        Args:
            airports: List of airports to prioritize
            strategy: Strategy name (default: "cost_optimized")
            context: Optional context (e.g., route distances)
            max_results: Maximum number of results to return

        Returns:
            Sorted list of airports (best first), limited to max_results
        """
        if not airports:
            return []

        # Get strategy
        strategy_obj = StrategyRegistry.get(strategy)
        if not strategy_obj:
            logger.warning(f"Unknown strategy: {strategy}, using cost_optimized")
            strategy_obj = StrategyRegistry.get("cost_optimized")

        # Score airports
        scored = strategy_obj.score(
            airports,
            enrichment_storage=self.enrichment_storage,
            context=context
        )

        # Log priority distribution
        priority_counts = {}
        for item in scored:
            priority_counts[item.priority_level] = priority_counts.get(item.priority_level, 0) + 1

        logger.info(
            f"Strategy '{strategy}' applied | "
            f"Input: {len(airports)} airports → "
            f"Priority distribution: {priority_counts} → "
            f"Returning top {max_results}"
        )

        # Return top N airports
        return [item.airport for item in scored[:max_results]]
