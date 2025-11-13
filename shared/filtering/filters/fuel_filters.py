#!/usr/bin/env python3
"""
Fuel availability filters (AVGAS, Jet-A, etc.)
"""
from typing import Any, Optional
from euro_aip.models.airport import Airport
from euro_aip.storage.enrichment_storage import EnrichmentStorage
from .base import Filter


class HasAvgasFilter(Filter):
    """Filter airports by AVGAS availability."""
    name = "has_avgas"
    requires_enrichment = True
    description = "Filter by AVGAS fuel availability (boolean)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if value is None or not value:
            return True  # Not filtering for AVGAS

        if not enrichment_storage:
            return False  # Can't check without enrichment data

        try:
            fuels = enrichment_storage.get_fuel_availability(airport.ident)
            if not fuels:
                return False  # No fuel data

            has_avgas = any(
                'avgas' in fuel.get('fuel_type', '').lower() and fuel.get('available', False)
                for fuel in fuels
            )

            return has_avgas
        except Exception:
            # Fuel data table doesn't exist or other error
            return False


class HasJetAFilter(Filter):
    """Filter airports by Jet-A fuel availability."""
    name = "has_jet_a"
    requires_enrichment = True
    description = "Filter by Jet-A fuel availability (boolean)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if value is None or not value:
            return True  # Not filtering for Jet-A

        if not enrichment_storage:
            return False  # Can't check without enrichment data

        try:
            fuels = enrichment_storage.get_fuel_availability(airport.ident)
            if not fuels:
                return False  # No fuel data

            has_jet_a = any(
                ('jeta1' in fuel.get('fuel_type', '').lower() or
                 'jet a1' in fuel.get('fuel_type', '').lower() or
                 'jet a' in fuel.get('fuel_type', '').lower())
                and fuel.get('available', False)
                for fuel in fuels
            )

            return has_jet_a
        except Exception:
            # Fuel data table doesn't exist or other error
            return False
