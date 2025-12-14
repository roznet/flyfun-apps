#!/usr/bin/env python3

"""
GA Friendliness Service - Main entry point for GA friendliness data access.

This service provides access to all GA friendliness data including scores,
personas, and configuration. It owns the database connection and provides
all query functionality.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
import sqlite3
import re

from .storage import GAMetaStorage
from .models import AirportFeatureScores
from .personas import PersonaManager, FEATURE_NAMES
from .config import get_default_personas
from .ui_config import get_ui_config
from .features import get_fee_band_for_mtow

logger = logging.getLogger(__name__)


def _get_notification_summary(icao: str) -> Optional[str]:
    """
    Fetch customs/immigration notification summary from ga_notifications.db.
    
    Returns the parsed and formatted summary from the ga_notification_requirements table.
    """
    # Get notification database path using consistent pattern
    from shared.aviation_agent.config import get_ga_notifications_db_path
    
    db_path = Path(get_ga_notifications_db_path())
    
    if not db_path.exists():
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
        
        # Clean up the summary - remove empty values
        summary = row["summary"].strip()
        cleaned_lines = []
        for line in summary.split("\n"):
            line = line.strip()
            if not line:
                continue
            
            # Remove patterns like "| Hours:" at end of line
            line = re.sub(r'\|\s*Hours:\s*$', '', line)
            # Remove "Hours:" alone at start
            line = re.sub(r'^Hours:\s*$', '', line)
            # Remove lines that are just "| Hours:"
            line = re.sub(r'^\|\s*Hours:\s*$', '', line)
            # Remove trailing " |"
            line = re.sub(r'\s*\|\s*$', '', line)
            line = line.strip()
            
            # Skip if line became empty
            if not line:
                continue
            # Skip lines that are only emoji placeholders with no value
            if line in ("📞", "📧"):
                continue
            # Skip lines like "📞 " or "📧 " with only whitespace after
            if re.match(r'^[📞📧]\s*$', line):
                continue
                
            cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines) if cleaned_lines else None
        
    except Exception as e:
        logger.warning(f"Error fetching notification for {icao}: {e}")
        return None


class GAFriendlinessService:
    """
    Service for GA friendliness data access.
    
    Provides access to GA friendliness scores, personas, configuration,
    and landing fees. Wraps the ga_friendliness library with a clean
    service interface.
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
    
    def get_config_dict(self) -> Dict[str, Any]:
        """
        Get complete UI configuration as a dictionary.
        
        Returns:
            Dict with feature_names, feature_display_names, feature_descriptions,
            relevance_buckets, personas (as dicts), default_persona, and version.
        """
        ui_config = get_ui_config()
        
        # Build personas list
        personas = []
        if self.persona_manager:
            for persona in self.persona_manager.list_personas():
                personas.append({
                    "id": persona.id,
                    "label": persona.label,
                    "description": persona.description,
                    "weights": persona.weights.model_dump()
                })
        
        return {
            "feature_names": ui_config["feature_names"],
            "feature_display_names": ui_config["feature_display_names"],
            "feature_descriptions": ui_config["feature_descriptions"],
            "relevance_buckets": ui_config["relevance_buckets"],
            "personas": personas,
            "default_persona": "ifr_touring_sr22",
            "version": "1.0"
        }
    
    def get_personas_dict(self) -> List[Dict[str, Any]]:
        """
        Get list of available personas as dictionaries.
        
        Returns:
            List of persona dicts with id, label, description, and weights.
        """
        if not self.persona_manager:
            return []
        
        return [
            {
                "id": p.id,
                "label": p.label,
                "description": p.description,
                "weights": p.weights.model_dump()
            }
            for p in self.persona_manager.list_personas()
        ]
    
    def get_summaries_batch_dict(
        self,
        icaos: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get GA summaries for multiple airports with ALL persona scores pre-computed.
        
        This is the primary method for the airports API integration.
        Returns data that enables instant persona switching in the UI.
        
        Args:
            icaos: List of ICAO codes
            
        Returns:
            Dict mapping ICAO -> summary dict (only for airports with data).
            Summary dict contains: features, persona_scores, review_count, last_review_utc,
            tags, summary_text, notification_hassle.
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
                    review_cost_score=stats.review_cost_score,
                    review_hassle_score=stats.review_hassle_score,
                    review_review_score=stats.review_review_score,
                    review_ops_ifr_score=stats.review_ops_ifr_score,
                    review_ops_vfr_score=stats.review_ops_vfr_score,
                    review_access_score=stats.review_access_score,
                    review_fun_score=stats.review_fun_score,
                    review_hospitality_score=stats.review_hospitality_score,
                    aip_ops_ifr_score=stats.aip_ops_ifr_score,
                    aip_hospitality_score=stats.aip_hospitality_score,
                )
                
                # Pre-compute scores for ALL personas
                persona_scores: Dict[str, Optional[float]] = {}
                for persona_id in persona_ids:
                    score = self.persona_manager.compute_score(persona_id, features)
                    persona_scores[persona_id] = score
                
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
                
                results[icao.upper()] = {
                    "features": features_dict,
                    "persona_scores": persona_scores,
                    "review_count": stats.rating_count or 0,
                    "last_review_utc": stats.last_review_utc,
                    "tags": tags if tags else None,
                    "summary_text": summary_text,
                    "notification_hassle": None
                }
                
            except Exception as e:
                logger.warning(f"Error getting GA summary for {icao}: {e}")
                # Skip this airport
        
        return results
    
    def get_summary_dict(
        self,
        icao: str,
        persona_id: str = "ifr_touring_sr22"
    ) -> Dict[str, Any]:
        """
        Get detailed GA summary for a single airport as a dictionary.
        
        Args:
            icao: Airport ICAO code
            persona_id: Persona to compute score for
            
        Returns:
            Dict with: icao, has_data, score, features, review_count, last_review_utc,
            tags, summary_text, notification_summary, hassle_level, hotel_info, restaurant_info.
        """
        if not self._enabled or not self.storage or not self.persona_manager:
            # Still try to get notification data even when GA service is disabled
            notification_summary = _get_notification_summary(icao)
            return {
                "icao": icao.upper(),
                "has_data": notification_summary is not None,
                "score": None,
                "features": None,
                "review_count": 0,
                "last_review_utc": None,
                "tags": None,
                "summary_text": None,
                "notification_summary": notification_summary,
                "hassle_level": None,
                "hotel_info": None,
                "restaurant_info": None
            }
        
        try:
            stats = self.storage.get_airfield_stats(icao.upper())
            if not stats:
                return {
                    "icao": icao.upper(),
                    "has_data": False,
                    "score": None,
                    "features": None,
                    "review_count": 0,
                    "last_review_utc": None,
                    "tags": None,
                    "summary_text": None,
                    "notification_summary": None,
                    "hassle_level": None,
                    "hotel_info": None,
                    "restaurant_info": None
                }
            
            # Build feature scores
            features = AirportFeatureScores(
                icao=stats.icao,
                review_cost_score=stats.review_cost_score,
                review_hassle_score=stats.review_hassle_score,
                review_review_score=stats.review_review_score,
                review_ops_ifr_score=stats.review_ops_ifr_score,
                review_ops_vfr_score=stats.review_ops_vfr_score,
                review_access_score=stats.review_access_score,
                review_fun_score=stats.review_fun_score,
                review_hospitality_score=stats.review_hospitality_score,
                aip_ops_ifr_score=stats.aip_ops_ifr_score,
                aip_hospitality_score=stats.aip_hospitality_score,
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
            
            return {
                "icao": stats.icao,
                "has_data": True,
                "score": score,
                "features": {
                    name: getattr(stats, name)
                    for name in FEATURE_NAMES
                },
                "review_count": stats.rating_count or 0,
                "last_review_utc": stats.last_review_utc,
                "tags": tags if tags else None,
                "summary_text": summary_text,
                "notification_summary": notification_summary,
                "hassle_level": hassle_level,
                "hotel_info": stats.hotel_info,
                "restaurant_info": stats.restaurant_info,
            }
            
        except Exception as e:
            logger.error(f"Error getting GA summary for {icao}: {e}")
            return {
                "icao": icao.upper(),
                "has_data": False,
                "score": None,
                "features": None,
                "review_count": 0,
                "last_review_utc": None,
                "tags": None,
                "summary_text": None,
                "notification_summary": None,
                "hassle_level": None,
                "hotel_info": None,
                "restaurant_info": None
            }

    def get_landing_fee_by_weight(
        self,
        icao: str,
        mtow_kg: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get landing fee for a given MTOW (Maximum Take-Off Weight).

        Args:
            icao: Airport ICAO code
            mtow_kg: Maximum Take-Off Weight in kilograms

        Returns:
            Dict with:
            - fee: Landing fee amount
            - currency: Currency code
            - fee_band: Fee band name (e.g., "fee_band_750_1199kg")
            - fee_last_updated_utc: Last update timestamp
            Or None if not available
        """
        if not self._enabled or not self.storage:
            return None

        try:
            stats = self.storage.get_airfield_stats(icao.upper())
            if not stats:
                return None

            # Map MTOW to fee band
            fee_band = get_fee_band_for_mtow(mtow_kg)
            fee_value = getattr(stats, fee_band, None)

            if fee_value is None:
                return None

            return {
                "fee": fee_value,
                "currency": stats.fee_currency,
                "fee_band": fee_band,
                "fee_last_updated_utc": stats.fee_last_updated_utc,
            }
        except Exception as e:
            logger.error(f"Error getting landing fee for {icao}: {e}")
            return None

