#!/usr/bin/env python3
"""
GA Friendliness API endpoints.

Provides endpoints for:
- /api/ga/config - UI configuration (feature names, display names, bucket colors)
- /api/ga/personas - List available personas with weights
- /api/ga/scores - Batch fetch scores for multiple airports
- /api/ga/summary/{icao} - Full summary for single airport
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .models import GAFriendlySummary

# Import GA friendliness library
from shared.ga_friendliness import (
    GAMetaStorage,
    PersonaManager,
    AirportFeatureScores,
    AirportStats,
    get_default_personas,
    FEATURE_NAMES,
    get_ui_config,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Pydantic Response Models ---

class PersonaResponse(BaseModel):
    """Persona information for API response."""
    id: str
    label: str
    description: str
    weights: Dict[str, float]


class GAConfigResponse(BaseModel):
    """Complete UI configuration response."""
    feature_names: List[str]
    feature_display_names: Dict[str, str]
    feature_descriptions: Dict[str, str]
    relevance_buckets: List[Dict[str, str]]
    personas: List[PersonaResponse]
    default_persona: str
    version: str


class AirportGAScoreResponse(BaseModel):
    """GA score for a single airport."""
    icao: str
    has_data: bool
    score: Optional[float] = None
    features: Optional[Dict[str, Optional[float]]] = None
    review_count: int = 0


class AirportGASummaryResponse(BaseModel):
    """Full GA summary for an airport."""
    icao: str
    has_data: bool
    score: Optional[float] = None
    features: Optional[Dict[str, Optional[float]]] = None
    review_count: int = 0
    last_review_utc: Optional[str] = None
    
    # Additional details
    tags: List[str] = Field(default_factory=list)
    summary_text: Optional[str] = None
    notification_summary: Optional[str] = None
    hassle_level: Optional[str] = None
    
    # Hospitality info
    hotel_info: Optional[str] = None
    restaurant_info: Optional[str] = None


# --- Service Class ---

class GAFriendlinessService:
    """
    Service for GA friendliness data access.
    
    Wraps the ga_friendliness library with web API patterns.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the service.
        
        Args:
            db_path: Path to ga_meta.sqlite. If None, service is disabled.
        """
        self.db_path = db_path
        self.storage: Optional[GAMetaStorage] = None
        self.persona_manager: Optional[PersonaManager] = None
        self._enabled = False
        
        if db_path and Path(db_path).exists():
            try:
                self.storage = GAMetaStorage(Path(db_path))
                self.persona_manager = PersonaManager(get_default_personas())
                self._enabled = True
                logger.info(f"GA Friendliness service initialized with DB: {db_path}")
            except Exception as e:
                logger.error(f"Failed to initialize GA Friendliness service: {e}")
                self._enabled = False
        else:
            logger.info("GA Friendliness service disabled (no database configured)")
    
    @property
    def enabled(self) -> bool:
        """Check if service is enabled and functional."""
        return self._enabled
    
    def get_config(self) -> GAConfigResponse:
        """Get complete UI configuration."""
        ui_config = get_ui_config()
        
        # Build personas list
        personas = []
        if self.persona_manager:
            for persona in self.persona_manager.list_personas():
                personas.append(PersonaResponse(
                    id=persona.id,
                    label=persona.label,
                    description=persona.description,
                    weights=persona.weights.model_dump()
                ))
        
        return GAConfigResponse(
            feature_names=ui_config["feature_names"],
            feature_display_names=ui_config["feature_display_names"],
            feature_descriptions=ui_config["feature_descriptions"],
            relevance_buckets=ui_config["relevance_buckets"],
            personas=personas,
            default_persona="ifr_touring_sr22",
            version="1.0"
        )
    
    def get_personas(self) -> List[PersonaResponse]:
        """Get list of available personas."""
        if not self.persona_manager:
            return []
        
        return [
            PersonaResponse(
                id=p.id,
                label=p.label,
                description=p.description,
                weights=p.weights.model_dump()
            )
            for p in self.persona_manager.list_personas()
        ]
    
    def get_scores(
        self,
        icaos: List[str],
        persona_id: str = "ifr_touring_sr22"
    ) -> Dict[str, AirportGAScoreResponse]:
        """
        Get GA scores for multiple airports.
        
        Args:
            icaos: List of ICAO codes
            persona_id: Persona to compute score for
            
        Returns:
            Dict mapping ICAO -> score response
        """
        if not self._enabled or not self.storage or not self.persona_manager:
            # Return empty responses for all requested airports
            return {
                icao: AirportGAScoreResponse(icao=icao, has_data=False)
                for icao in icaos
            }
        
        results = {}
        for icao in icaos:
            try:
                stats = self.storage.get_airfield_stats(icao.upper())
                if stats:
                    # Build feature scores
                    features = AirportFeatureScores(
                        icao=stats.icao,
                        ga_cost_score=stats.ga_cost_score,
                        ga_review_score=stats.ga_review_score,
                        ga_hassle_score=stats.ga_hassle_score,
                        ga_ops_ifr_score=stats.ga_ops_ifr_score,
                        ga_ops_vfr_score=stats.ga_ops_vfr_score,
                        ga_access_score=stats.ga_access_score,
                        ga_fun_score=stats.ga_fun_score,
                        ga_hospitality_score=stats.ga_hospitality_score,
                    )
                    
                    # Compute persona score
                    score = self.persona_manager.compute_score(persona_id, features)
                    
                    results[icao.upper()] = AirportGAScoreResponse(
                        icao=stats.icao,
                        has_data=True,
                        score=score,
                        features={
                            name: getattr(stats, name)
                            for name in FEATURE_NAMES
                        },
                        review_count=stats.rating_count or 0
                    )
                else:
                    results[icao.upper()] = AirportGAScoreResponse(
                        icao=icao.upper(),
                        has_data=False
                    )
            except Exception as e:
                logger.warning(f"Error getting GA score for {icao}: {e}")
                results[icao.upper()] = AirportGAScoreResponse(
                    icao=icao.upper(),
                    has_data=False
                )
        
        return results
    
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
        if not self._enabled or not self.storage or not self.persona_manager:
            return {}
        
        # Get all persona IDs for pre-computing scores
        persona_ids = self.persona_manager.list_persona_ids()
        
        results = {}
        for icao in icaos:
            try:
                stats = self.storage.get_airfield_stats(icao.upper())
                if not stats:
                    continue  # Skip airports without GA data
                
                # Build feature scores dict
                features_dict = {
                    name: getattr(stats, name)
                    for name in FEATURE_NAMES
                }
                
                # Build AirportFeatureScores for persona scoring
                features = AirportFeatureScores(
                    icao=stats.icao,
                    ga_cost_score=stats.ga_cost_score,
                    ga_review_score=stats.ga_review_score,
                    ga_hassle_score=stats.ga_hassle_score,
                    ga_ops_ifr_score=stats.ga_ops_ifr_score,
                    ga_ops_vfr_score=stats.ga_ops_vfr_score,
                    ga_access_score=stats.ga_access_score,
                    ga_fun_score=stats.ga_fun_score,
                    ga_hospitality_score=stats.ga_hospitality_score,
                )
                
                # Pre-compute scores for ALL personas
                persona_scores = {}
                for persona_id in persona_ids:
                    score = self.persona_manager.compute_score(persona_id, features)
                    persona_scores[persona_id] = score
                
                results[icao.upper()] = GAFriendlySummary(
                    features=features_dict,
                    persona_scores=persona_scores,
                    review_count=stats.rating_count or 0,
                    last_review_utc=stats.last_review_utc,
                    # Optional enrichment - available in detail view via get_summary
                    tags=None,
                    summary_text=None,
                    notification_hassle=None
                )
                
            except Exception as e:
                logger.warning(f"Error getting GA summary for {icao}: {e}")
                # Skip this airport
        
        return results
    
    def get_summary(
        self,
        icao: str,
        persona_id: str = "ifr_touring_sr22"
    ) -> AirportGASummaryResponse:
        """
        Get full GA summary for a single airport.
        
        Args:
            icao: Airport ICAO code
            persona_id: Persona to compute score for
            
        Returns:
            Full summary response
        """
        if not self._enabled or not self.storage or not self.persona_manager:
            return AirportGASummaryResponse(icao=icao.upper(), has_data=False)
        
        try:
            stats = self.storage.get_airfield_stats(icao.upper())
            if not stats:
                return AirportGASummaryResponse(icao=icao.upper(), has_data=False)
            
            # Build feature scores
            features = AirportFeatureScores(
                icao=stats.icao,
                ga_cost_score=stats.ga_cost_score,
                ga_review_score=stats.ga_review_score,
                ga_hassle_score=stats.ga_hassle_score,
                ga_ops_ifr_score=stats.ga_ops_ifr_score,
                ga_ops_vfr_score=stats.ga_ops_vfr_score,
                ga_access_score=stats.ga_access_score,
                ga_fun_score=stats.ga_fun_score,
                ga_hospitality_score=stats.ga_hospitality_score,
            )
            
            # Compute persona score
            score = self.persona_manager.compute_score(persona_id, features)
            
            # Get review summary if available
            summary_text = None
            tags: List[str] = []
            try:
                cursor = self.storage.conn.execute(
                    "SELECT summary_text, tags_json FROM ga_review_summary WHERE icao = ?",
                    (icao.upper(),)
                )
                row = cursor.fetchone()
                if row:
                    summary_text = row["summary_text"]
                    import json
                    tags = json.loads(row["tags_json"]) if row["tags_json"] else []
            except Exception:
                pass  # Summary table may not exist
            
            # Get AIP rule summary if available
            notification_summary = None
            hassle_level = None
            try:
                cursor = self.storage.conn.execute(
                    "SELECT notification_summary, hassle_level FROM ga_aip_rule_summary WHERE icao = ?",
                    (icao.upper(),)
                )
                row = cursor.fetchone()
                if row:
                    notification_summary = row["notification_summary"]
                    hassle_level = row["hassle_level"]
            except Exception:
                pass  # Summary table may not exist
            
            return AirportGASummaryResponse(
                icao=stats.icao,
                has_data=True,
                score=score,
                features={
                    name: getattr(stats, name)
                    for name in FEATURE_NAMES
                },
                review_count=stats.rating_count or 0,
                last_review_utc=stats.last_review_utc,
                tags=tags,
                summary_text=summary_text,
                notification_summary=notification_summary,
                hassle_level=hassle_level,
                hotel_info=stats.hotel_info,
                restaurant_info=stats.restaurant_info,
            )
            
        except Exception as e:
            logger.error(f"Error getting GA summary for {icao}: {e}")
            return AirportGASummaryResponse(icao=icao.upper(), has_data=False)


# --- Global Service Instance ---

_service: Optional[GAFriendlinessService] = None


def init_service(db_path: Optional[str]) -> None:
    """Initialize the GA friendliness service."""
    global _service
    _service = GAFriendlinessService(db_path)


def get_service() -> GAFriendlinessService:
    """Get the GA friendliness service instance."""
    if _service is None:
        raise RuntimeError("GA Friendliness service not initialized")
    return _service


def feature_enabled() -> bool:
    """Check if GA friendliness feature is enabled."""
    return _service is not None and _service.enabled


# --- API Endpoints ---

@router.get("/config", response_model=GAConfigResponse)
async def get_config():
    """
    Get GA friendliness UI configuration.
    
    Returns all configuration needed by the frontend:
    - Feature names and display names
    - Feature descriptions
    - Relevance bucket colors
    - Available personas with weights
    """
    service = get_service()
    return service.get_config()


@router.get("/personas", response_model=List[PersonaResponse])
async def get_personas():
    """
    Get list of available personas.
    
    Each persona has an ID, label, description, and feature weights.
    """
    service = get_service()
    return service.get_personas()


@router.get("/scores", response_model=Dict[str, AirportGAScoreResponse])
async def get_scores(
    icaos: str = Query(..., description="Comma-separated list of ICAO codes (max 200)"),
    persona: str = Query("ifr_touring_sr22", description="Persona ID for score computation")
):
    """
    Get GA scores for multiple airports.
    
    Returns scores computed for the specified persona, along with
    individual feature scores and review count.
    """
    service = get_service()
    
    # Parse and validate ICAO list
    icao_list = [i.strip().upper() for i in icaos.split(",") if i.strip()]
    
    if len(icao_list) > 200:
        raise HTTPException(
            status_code=400,
            detail="Maximum 200 ICAOs per request"
        )
    
    if not icao_list:
        raise HTTPException(
            status_code=400,
            detail="At least one ICAO code required"
        )
    
    return service.get_scores(icao_list, persona)


@router.get("/summary/{icao}", response_model=AirportGASummaryResponse)
async def get_summary(
    icao: str,
    persona: str = Query("ifr_touring_sr22", description="Persona ID for score computation")
):
    """
    Get full GA summary for an airport.
    
    Returns complete GA data including:
    - Computed score for persona
    - All feature scores
    - Review summary and tags
    - Notification requirements summary
    - Hospitality info
    """
    service = get_service()
    
    if len(icao) != 4:
        raise HTTPException(
            status_code=400,
            detail="ICAO code must be 4 characters"
        )
    
    return service.get_summary(icao.upper(), persona)


@router.get("/health")
async def health_check():
    """Check GA friendliness service health."""
    service = get_service()
    return {
        "enabled": service.enabled,
        "db_path": service.db_path,
    }

