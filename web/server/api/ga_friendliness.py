#!/usr/bin/env python3

"""
GA Friendliness API endpoints.

Provides access to GA friendliness scores, personas, and configuration.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import logging

from .models import GAFriendlySummary

# Import service from shared location
from shared.ga_friendliness.service import GAFriendlinessService as BaseGAFriendlinessService

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Response Models ---

class PersonaResponse(BaseModel):
    """Persona information."""
    id: str
    label: str
    description: str
    weights: Dict[str, float]


class GAConfigResponse(BaseModel):
    """Complete GA configuration for UI."""
    feature_names: List[str]
    feature_display_names: Dict[str, str]
    feature_descriptions: Dict[str, str]
    relevance_buckets: List[Dict[str, str]]
    personas: List[PersonaResponse]
    default_persona: str
    version: str


class AirportGAScoreResponse(BaseModel):
    """Score response for a single airport."""
    icao: str
    has_data: bool = False
    score: Optional[float] = None
    features: Optional[Dict[str, Optional[float]]] = None
    review_count: int = 0


class AirportGASummaryResponse(BaseModel):
    """Full summary response for a single airport."""
    icao: str
    has_data: bool = False
    score: Optional[float] = None
    features: Optional[Dict[str, Optional[float]]] = None
    review_count: int = 0
    last_review_utc: Optional[str] = None
    tags: Optional[List[str]] = None
    summary_text: Optional[str] = None
    notification_summary: Optional[str] = None
    hassle_level: Optional[str] = None
    hotel_info: Optional[str] = None
    restaurant_info: Optional[str] = None


# --- Service Wrapper Class ---

class GAFriendlinessService(BaseGAFriendlinessService):
    """
    Web API wrapper for GA Friendliness Service.
    
    Extends the base service with methods that return API response models
    for backward compatibility with existing web API code.
    """
    
    def get_config(self) -> GAConfigResponse:
        """Get complete UI configuration as API response model."""
        config_dict = self.get_config_dict()
        return GAConfigResponse(**config_dict)
    
    def get_personas(self) -> List[PersonaResponse]:
        """Get list of available personas as API response models."""
        personas_dict = self.get_personas_dict()
        return [PersonaResponse(**p) for p in personas_dict]
    
    def get_summaries_batch(
        self,
        icaos: List[str]
    ) -> Dict[str, GAFriendlySummary]:
        """
        Get GA summaries for multiple airports with ALL persona scores pre-computed.
        
        This is the primary method for the airports API integration.
        Returns data that enables instant persona switching in the UI.
        
        Args:
            icaos: List of ICAO codes
            
        Returns:
            Dict mapping ICAO -> GAFriendlySummary (only for airports with data)
        """
        summaries_dict = self.get_summaries_batch_dict(icaos)
        return {
            icao: GAFriendlySummary(**summary_dict)
            for icao, summary_dict in summaries_dict.items()
        }
    
    def get_summary(
        self,
        icao: str,
        persona_id: str = "ifr_touring_sr22"
    ) -> AirportGASummaryResponse:
        """
        Get detailed GA summary for a single airport as API response model.
        
        Args:
            icao: Airport ICAO code
            persona_id: Persona to compute score for
            
        Returns:
            Full summary response
        """
        summary_dict = self.get_summary_dict(icao, persona_id)
        return AirportGASummaryResponse(**summary_dict)


# --- Global Service Instance ---

_service: Optional[GAFriendlinessService] = None


def set_service(service: Optional[GAFriendlinessService]):
    """Set the shared GAFriendlinessService instance."""
    global _service
    _service = service


def get_service() -> Optional[GAFriendlinessService]:
    """Get the shared GAFriendlinessService instance."""
    return _service


# --- API Endpoints ---

@router.get("/config", response_model=GAConfigResponse)
async def get_ga_config():
    """Get GA friendliness configuration for the UI."""
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="GA Friendliness service not available")
    
    return service.get_config()


@router.get("/personas", response_model=List[PersonaResponse])
async def get_ga_personas():
    """Get list of available personas."""
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="GA Friendliness service not available")
    
    return service.get_personas()


@router.get("/summary/{icao}", response_model=AirportGASummaryResponse)
async def get_ga_summary(
    icao: str,
    persona: str = Query("ifr_touring_sr22", description="Persona ID for score calculation")
):
    """Get detailed GA summary for a single airport."""
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="GA Friendliness service not available")
    
    return service.get_summary(icao, persona)
