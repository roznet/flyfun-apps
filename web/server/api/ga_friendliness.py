#!/usr/bin/env python3

"""
GA Friendliness API endpoints.

Provides access to GA friendliness scores, personas, and configuration.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from pathlib import Path
import logging
import sqlite3
import os

from .models import GAFriendlySummary

# Import from ga_friendliness library
from shared.ga_friendliness.storage import GAMetaStorage
from shared.ga_friendliness.models import AirportFeatureScores
from shared.ga_friendliness.personas import PersonaManager, FEATURE_NAMES
from shared.ga_friendliness.config import get_default_personas
from shared.ga_friendliness.ui_config import get_ui_config

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_notification_summary(icao: str) -> Optional[str]:
    """
    Fetch customs/immigration notification summary from ga_notifications.db.
    
    Returns the parsed and formatted summary from the ga_notification_requirements table.
    """
    # Find notification database path
    possible_paths = [
        Path(os.environ.get("GA_NOTIFICATIONS_DB", "")),
        Path(__file__).parent.parent.parent.parent / "data" / "ga_notifications.db",
        Path("/home/qian/dev/022_Home/flyfun-apps/data/ga_notifications.db"),
    ]
    
    db_path = None
    for p in possible_paths:
        if p.exists() and p.stat().st_size > 0:
            db_path = p
            break
    
    if not db_path:
        return None
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        # Query parsed notification data
        cursor = conn.execute(
            """SELECT summary FROM ga_notification_requirements 
               WHERE icao = ?""",
            (icao.upper(),)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row["summary"]:
            return None
        
        return row["summary"].strip()
        
    except Exception as e:
        logger.warning(f"Error fetching notification for {icao}: {e}")
        return None


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


# --- Service Class ---

class GAFriendlinessService:
    """
    Service for GA friendliness data access.
    
    Wraps the ga_friendliness library with web API patterns.
    """
    
    def __init__(self, db_path: Optional[str] = None, readonly: bool = True):
        """
        Initialize the service.
        
        Args:
            db_path: Path to ga_meta.sqlite. If None, service is disabled.
            readonly: If True, open database in read-only mode (default for web API).
        """
        self.db_path = db_path
        self.readonly = readonly
        self.storage: Optional[GAMetaStorage] = None
        self.persona_manager: Optional[PersonaManager] = None
        self._enabled = False
        
        if db_path and Path(db_path).exists():
            try:
                # Open in readonly mode by default for web API (no writes)
                self.storage = GAMetaStorage(Path(db_path), readonly=readonly)
                self.persona_manager = PersonaManager(get_default_personas())
                self._enabled = True
                logger.info(f"GA Friendliness service initialized (readonly={readonly}): {db_path}")
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
                features_dict: Dict[str, Optional[float]] = {
                    name: getattr(stats, name, None)
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
                persona_scores: Dict[str, Optional[float]] = {}
                for persona_id in persona_ids:
                    score = self.persona_manager.compute_score(persona_id, features)
                    persona_scores[persona_id] = score
                
                results[icao.upper()] = GAFriendlySummary(
                    features=features_dict,
                    persona_scores=persona_scores,
                    review_count=stats.rating_count or 0,
                    last_review_utc=stats.last_review_utc,
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
        Get detailed GA summary for a single airport.
        
        Args:
            icao: Airport ICAO code
            persona_id: Persona to compute score for
            
        Returns:
            Full summary response
        """
        if not self._enabled or not self.storage or not self.persona_manager:
            # Still try to get notification data even when GA service is disabled
            notification_summary = _get_notification_summary(icao)
            return AirportGASummaryResponse(
                icao=icao.upper(), 
                has_data=notification_summary is not None,
                notification_summary=notification_summary
            )
        
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
            if self.storage.conn:
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
            
            # Get notification/customs summary from ga_notifications.db
            notification_summary = _get_notification_summary(icao)
            hassle_level = None  # TODO: compute from notification data if needed
            
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
