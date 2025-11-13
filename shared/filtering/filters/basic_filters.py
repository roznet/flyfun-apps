#!/usr/bin/env python3
"""
Basic airport filters (country, procedures, border crossing, etc.)
"""
from typing import Any, Optional
from euro_aip.models.airport import Airport
from euro_aip.storage.enrichment_storage import EnrichmentStorage
from .base import Filter


class CountryFilter(Filter):
    """Filter airports by ISO country code."""
    name = "country"
    requires_enrichment = False
    description = "Filter by country (ISO-2 code, e.g., 'FR', 'GB')"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if not value:
            return True
        country_code = str(value).upper()
        airport_country = (airport.iso_country or "").upper()
        return airport_country == country_code


class HasProceduresFilter(Filter):
    """Filter airports by procedure availability."""
    name = "has_procedures"
    requires_enrichment = False
    description = "Filter by instrument procedures availability (boolean)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if value is None:
            return True
        has_procedures = bool(airport.has_procedures)
        return has_procedures == bool(value)


class HasAipDataFilter(Filter):
    """Filter airports by AIP data availability."""
    name = "has_aip_data"
    requires_enrichment = False
    description = "Filter by AIP data availability (boolean)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if value is None:
            return True
        has_aip = bool(len(airport.aip_entries) > 0)
        return has_aip == bool(value)


class HasHardRunwayFilter(Filter):
    """Filter airports by hard surface runway availability."""
    name = "has_hard_runway"
    requires_enrichment = False
    description = "Filter by hard surface runway (boolean)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if value is None:
            return True
        has_hard = bool(getattr(airport, "has_hard_runway", False))
        return has_hard == bool(value)


class PointOfEntryFilter(Filter):
    """Filter airports by border crossing (customs) capability."""
    name = "point_of_entry"
    requires_enrichment = False
    description = "Filter by border crossing/customs capability (boolean)"

    def apply(
        self,
        airport: Airport,
        value: Any,
        enrichment_storage: Optional[EnrichmentStorage] = None
    ) -> bool:
        if value is None:
            return True
        is_poe = bool(getattr(airport, "point_of_entry", False))
        return is_poe == bool(value)
