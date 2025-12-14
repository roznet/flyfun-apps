#!/usr/bin/env python3

"""
Pydantic models for API responses that extend the euro_aip domain models.
"""

from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

# Import the domain models
from euro_aip.models.airport import Airport
from euro_aip.models.procedure import Procedure
from euro_aip.models.aip_entry import AIPEntry
from euro_aip.models.runway import Runway

# Import notification service accessor
from .notifications import get_notification_service


class GAFriendlySummary(BaseModel):
    """
    GA Friendliness data - isolated from airport structure.
    
    Contains all raw feature scores and pre-computed persona scores,
    enabling instant persona switching in the UI without additional API calls.
    """
    model_config = ConfigDict(from_attributes=True)
    
    # Raw feature scores (0-1 normalized) - for UI breakdown display
    features: Dict[str, Optional[float]]
    # e.g., {"ga_cost_score": 0.7, "ga_review_score": 0.85, ...}
    
    # Pre-computed scores for ALL personas - enables instant UI toggle
    persona_scores: Dict[str, Optional[float]]
    # e.g., {"ifr_touring_sr22": 0.72, "vfr_budget_flyer": 0.65, ...}
    
    # Review metadata
    review_count: int = 0
    last_review_utc: Optional[str] = None
    
    # Optional enrichment (for detail view)
    tags: Optional[List[str]] = None
    summary_text: Optional[str] = None
    notification_hassle: Optional[str] = None


class AirportSummary(BaseModel):
    """Pydantic model for airport summary responses."""
    model_config = ConfigDict(from_attributes=True)
    
    ident: str
    name: Optional[str]
    latitude_deg: Optional[float]
    longitude_deg: Optional[float]
    iso_country: Optional[str]
    municipality: Optional[str]
    point_of_entry: Optional[bool]
    has_procedures: bool
    has_runways: bool
    has_aip_data: bool
    has_hard_runway: Optional[bool]
    has_lighted_runway: Optional[bool]
    has_soft_runway: Optional[bool]
    has_water_runway: Optional[bool]
    has_snow_runway: Optional[bool]
    longest_runway_length_ft: Optional[int]
    procedure_count: int
    runway_count: int
    aip_entry_count: int
    
    # GA Friendliness data - optional, populated when include_ga=True
    ga: Optional[GAFriendlySummary] = None
    
    @classmethod
    def from_airport(cls, airport: Airport, ga_summary: Optional[GAFriendlySummary] = None):
        """Create AirportSummary from Airport domain model."""
        return cls(
            ident=airport.ident,
            name=airport.name,
            latitude_deg=airport.latitude_deg,
            longitude_deg=airport.longitude_deg,
            iso_country=airport.iso_country,
            municipality=airport.municipality,
            point_of_entry=airport.point_of_entry,
            has_procedures=bool(airport.procedures),
            has_runways=bool(airport.runways),
            has_aip_data=bool(airport.aip_entries),
            has_hard_runway=airport.has_hard_runway,
            has_lighted_runway=airport.has_lighted_runway,
            has_soft_runway=airport.has_soft_runway,
            has_water_runway=airport.has_water_runway,
            has_snow_runway=airport.has_snow_runway,
            longest_runway_length_ft=airport.longest_runway_length_ft,
            procedure_count=len(airport.procedures),
            runway_count=len(airport.runways),
            aip_entry_count=len(airport.aip_entries),
            ga=ga_summary
        )


class AirportDetail(BaseModel):
    """Pydantic model for detailed airport responses."""
    model_config = ConfigDict(from_attributes=True)
    
    ident: str
    name: Optional[str]
    type: Optional[str]
    latitude_deg: Optional[float]
    longitude_deg: Optional[float]
    elevation_ft: Optional[float]
    continent: Optional[str]
    iso_country: Optional[str]
    iso_region: Optional[str]
    municipality: Optional[str]
    scheduled_service: Optional[str]
    gps_code: Optional[str]
    iata_code: Optional[str]
    local_code: Optional[str]
    home_link: Optional[str]
    wikipedia_link: Optional[str]
    keywords: Optional[str]
    point_of_entry: Optional[bool]
    avgas: Optional[bool]
    jet_a: Optional[bool]
    has_hard_runway: Optional[bool]
    has_lighted_runway: Optional[bool]
    has_soft_runway: Optional[bool]
    has_water_runway: Optional[bool]
    has_snow_runway: Optional[bool]
    longest_runway_length_ft: Optional[int]
    sources: List[str]
    runways: List[Dict[str, Any]]
    procedures: List[Dict[str, Any]]
    aip_entries: List[Dict[str, Any]]
    created_at: str
    updated_at: str
    
    @classmethod
    def from_airport(cls, airport: Airport):
        """Create AirportDetail from Airport domain model."""
        return cls(
            ident=airport.ident,
            name=airport.name,
            type=airport.type,
            latitude_deg=airport.latitude_deg,
            longitude_deg=airport.longitude_deg,
            elevation_ft=airport.elevation_ft,
            continent=airport.continent,
            iso_country=airport.iso_country,
            iso_region=airport.iso_region,
            municipality=airport.municipality,
            scheduled_service=airport.scheduled_service,
            gps_code=airport.gps_code,
            iata_code=airport.iata_code,
            local_code=airport.local_code,
            home_link=airport.home_link,
            wikipedia_link=airport.wikipedia_link,
            keywords=airport.keywords,
            point_of_entry=airport.point_of_entry,
            avgas=airport.avgas,
            jet_a=airport.jet_a,
            has_hard_runway=airport.has_hard_runway,
            has_lighted_runway=airport.has_lighted_runway,
            has_soft_runway=airport.has_soft_runway,
            has_water_runway=airport.has_water_runway,
            has_snow_runway=airport.has_snow_runway,
            longest_runway_length_ft=airport.longest_runway_length_ft,
            sources=list(airport.sources),
            runways=[r.to_dict() for r in airport.runways],
            procedures=[p.to_dict() for p in airport.procedures],
            aip_entries=cls._get_aip_entries_with_parsed_notifications(airport),
            created_at=airport.created_at.isoformat(),
            updated_at=airport.updated_at.isoformat()
        )
    
    @classmethod
    def _get_aip_entries_with_parsed_notifications(cls, airport: Airport) -> List[Dict[str, Any]]:
        """
        Get aip_entries with parsed notification summaries injected.
        
        For std_field_id=302 (Customs and immigration), replace the value
        with the parsed summary from ga_notifications.db if available.
        """
        notification_service = get_notification_service()
        parsed_notification = notification_service.get_notification_summary(airport.ident)
        
        entries = []
        for e in airport.aip_entries:
            entry_dict = e.to_dict()
            
            # If this is the customs/immigration field and we have a parsed summary
            if e.std_field_id == 302 and parsed_notification and parsed_notification.get("summary"):
                # Replace value with parsed summary
                entry_dict["value"] = parsed_notification["summary"]
                entry_dict["parsed_notification"] = True
                entry_dict["notification_confidence"] = parsed_notification.get("confidence")
            
            entries.append(entry_dict)
        
        return entries


class AIPEntryResponse(BaseModel):
    """Pydantic model for AIP entry responses."""
    model_config = ConfigDict(from_attributes=True)
    
    ident: str
    section: str
    field: str
    value: str
    std_field: Optional[str]
    std_field_id: Optional[int]
    mapping_score: Optional[float]
    alt_field: Optional[str]
    alt_value: Optional[str]
    source: Optional[str]
    created_at: str
    
    @classmethod
    def from_aip_entry(cls, entry: AIPEntry):
        """Create AIPEntryResponse from AIPEntry domain model."""
        return cls(
            ident=entry.ident,
            section=entry.section,
            field=entry.field,
            value=entry.value,
            std_field=entry.std_field,
            std_field_id=entry.std_field_id,
            mapping_score=entry.mapping_score,
            alt_field=entry.alt_field,
            alt_value=entry.alt_value,
            source=entry.source,
            created_at=entry.created_at.isoformat()
        )


class ProcedureSummary(BaseModel):
    """Pydantic model for procedure summary responses."""
    model_config = ConfigDict(from_attributes=True)
    
    name: str
    procedure_type: str
    approach_type: Optional[str]
    runway_ident: Optional[str]
    authority: Optional[str]
    source: Optional[str]
    airport_ident: str
    airport_name: Optional[str]
    
    @classmethod
    def from_procedure(cls, procedure: Procedure, airport: Airport):
        """Create ProcedureSummary from Procedure domain model."""
        return cls(
            name=procedure.name,
            procedure_type=procedure.procedure_type,
            approach_type=procedure.approach_type,
            runway_ident=procedure.runway_ident,
            authority=procedure.authority,
            source=procedure.source,
            airport_ident=airport.ident,
            airport_name=airport.name
        )


class ProcedureDetail(BaseModel):
    """Pydantic model for detailed procedure responses."""
    model_config = ConfigDict(from_attributes=True)
    
    name: str
    procedure_type: str
    approach_type: Optional[str]
    runway_number: Optional[str]
    runway_letter: Optional[str]
    runway_ident: Optional[str]
    source: Optional[str]
    authority: Optional[str]
    raw_name: Optional[str]
    data: Optional[Dict[str, Any]]
    created_at: str
    updated_at: str
    
    @classmethod
    def from_procedure(cls, procedure: Procedure):
        """Create ProcedureDetail from Procedure domain model."""
        return cls(
            name=procedure.name,
            procedure_type=procedure.procedure_type,
            approach_type=procedure.approach_type,
            runway_number=procedure.runway_number,
            runway_letter=procedure.runway_letter,
            runway_ident=procedure.runway_ident,
            source=procedure.source,
            authority=procedure.authority,
            raw_name=procedure.raw_name,
            data=procedure.data,
            created_at=procedure.created_at.isoformat(),
            updated_at=procedure.updated_at.isoformat()
        )


class RunwayResponse(BaseModel):
    """Pydantic model for runway responses."""
    model_config = ConfigDict(from_attributes=True)
    
    le_ident: str
    he_ident: str
    length_ft: Optional[int]
    width_ft: Optional[int]
    surface: Optional[str]
    lighted: Optional[bool]
    closed: Optional[bool]
    le_latitude_deg: Optional[float]
    le_longitude_deg: Optional[float]
    le_elevation_ft: Optional[int]
    le_heading_degT: Optional[float]
    le_displaced_threshold_ft: Optional[int]
    he_latitude_deg: Optional[float]
    he_longitude_deg: Optional[float]
    he_elevation_ft: Optional[int]
    he_heading_degT: Optional[float]
    he_displaced_threshold_ft: Optional[int]
    
    @classmethod
    def from_runway(cls, runway: Runway):
        """Create RunwayResponse from Runway domain model."""
        return cls(
            le_ident=runway.le_ident,
            he_ident=runway.he_ident,
            length_ft=runway.length_ft,
            width_ft=runway.width_ft,
            surface=runway.surface,
            lighted=runway.lighted,
            closed=runway.closed,
            le_latitude_deg=runway.le_latitude_deg,
            le_longitude_deg=runway.le_longitude_deg,
            le_elevation_ft=runway.le_elevation_ft,
            le_heading_degT=runway.le_heading_degT,
            le_displaced_threshold_ft=runway.le_displaced_threshold_ft,
            he_latitude_deg=runway.he_latitude_deg,
            he_longitude_deg=runway.he_longitude_deg,
            he_elevation_ft=runway.he_elevation_ft,
            he_heading_degT=runway.he_heading_degT,
            he_displaced_threshold_ft=runway.he_displaced_threshold_ft
        ) 


class RuleEntryResponse(BaseModel):
    """Pydantic model for an individual rule entry."""

    question_id: str
    question_text: Optional[str]
    category: Optional[str]
    tags: List[str] = []
    answer_html: Optional[str]
    links: List[str] = []
    last_reviewed: Optional[str]
    confidence: Optional[str]


class RuleCategoryResponse(BaseModel):
    """Pydantic model for a category grouping of rules."""

    name: str
    count: int
    rules: List[RuleEntryResponse]


class CountryRulesResponse(BaseModel):
    """Pydantic model for rules grouped by category for a country."""

    country: str
    total_rules: int
    categories: List[RuleCategoryResponse]