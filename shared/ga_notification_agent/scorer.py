"""
Notification hassle scorer.

Computes hassle scores from parsed notification rules.
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
import sqlite3

from .models import (
    NotificationRule,
    NotificationType,
    ParsedNotificationRules,
    HassleScore,
    HassleLevel,
)
from .parser import NotificationParser

logger = logging.getLogger(__name__)


class NotificationScorer:
    """
    Score notification hassle from parsed rules.
    
    Also handles loading data from airports.db and writing to ga_meta.sqlite.
    """
    
    # Standard field IDs
    STD_FIELD_CUSTOMS = 302  # Customs and immigration
    
    def __init__(
        self,
        parser: Optional[NotificationParser] = None,
        use_llm_fallback: bool = False,
        llm_model: str = "gpt-4o-mini",
        llm_api_key: Optional[str] = None,
    ):
        """
        Initialize scorer.
        
        Args:
            parser: NotificationParser instance (creates default if not provided)
            use_llm_fallback: Whether to use LLM for complex cases
            llm_model: OpenAI model to use for LLM extraction
            llm_api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.parser = parser or NotificationParser(
            use_llm_fallback=use_llm_fallback,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
        )
    
    def score_from_text(self, icao: str, text: str) -> HassleScore:
        """
        Parse and score notification text.
        
        Args:
            icao: Airport ICAO code
            text: Raw AIP customs/immigration text
            
        Returns:
            HassleScore with computed score
        """
        parsed = self.parser.parse(icao, text)
        return HassleScore.from_parsed_rules(parsed)
    
    def score_from_parsed(self, parsed: ParsedNotificationRules) -> HassleScore:
        """
        Score from already-parsed rules.
        
        Args:
            parsed: ParsedNotificationRules
            
        Returns:
            HassleScore
        """
        return HassleScore.from_parsed_rules(parsed)
    
    def load_and_score_from_airports_db(
        self,
        airports_db_path: Path,
        icaos: Optional[List[str]] = None,
        return_parsed: bool = False,
    ) -> Dict[str, HassleScore]:
        """
        Load notification text from airports.db and score all airports.
        
        Args:
            airports_db_path: Path to airports.db
            icaos: Optional list of ICAOs to process (all if None)
            return_parsed: If True, returns (scores, parsed_rules) tuple
            
        Returns:
            Dict mapping ICAO -> HassleScore
            If return_parsed=True: Tuple of (scores_dict, parsed_rules_dict)
        """
        if not airports_db_path.exists():
            raise FileNotFoundError(f"Airports database not found: {airports_db_path}")
        
        conn = sqlite3.connect(airports_db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            query = """
                SELECT airport_icao, value 
                FROM aip_entries 
                WHERE std_field_id = ? AND value IS NOT NULL AND LENGTH(value) >= 3
            """
            params = [self.STD_FIELD_CUSTOMS]
            
            if icaos:
                placeholders = ",".join("?" * len(icaos))
                query += f" AND airport_icao IN ({placeholders})"
                params.extend([i.upper() for i in icaos])
            
            cursor = conn.execute(query, params)
            
            scores = {}
            parsed_rules = {}
            for row in cursor:
                icao = row["airport_icao"]
                text = row["value"]
                
                try:
                    parsed = self.parser.parse(icao, text)
                    score = HassleScore.from_parsed_rules(parsed)
                    scores[icao] = score
                    parsed_rules[icao] = parsed
                except Exception as e:
                    logger.warning(f"Failed to score {icao}: {e}")
            
            logger.info(f"Scored {len(scores)} airports from airports.db")
            
            if return_parsed:
                return scores, parsed_rules
            return scores
            
        finally:
            conn.close()
    
    def write_to_ga_meta(
        self,
        ga_meta_db_path: Path,
        scores: Dict[str, HassleScore],
        parsed_rules: Optional[Dict[str, ParsedNotificationRules]] = None,
    ) -> int:
        """
        Write scores and rules to ga_meta.sqlite.
        
        Args:
            ga_meta_db_path: Path to ga_meta.sqlite
            scores: Dict mapping ICAO -> HassleScore
            parsed_rules: Optional dict of parsed rules to also store
            
        Returns:
            Number of airports updated
        """
        conn = sqlite3.connect(ga_meta_db_path)
        
        try:
            # Note: notification_hassle_score column doesn't exist in current schema
            # Data is stored in ga_aip_rule_summary table instead
            # This update is a no-op but kept for future schema compatibility
            updated = 0
            
            # Write to ga_aip_rule_summary
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            
            for icao, score in scores.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ga_aip_rule_summary
                    (icao, notification_summary, hassle_level, notification_score, last_updated_utc)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (icao, score.summary, score.level.value, score.score, now)
                )
            
            # Write detailed rules if provided
            if parsed_rules:
                for icao, parsed in parsed_rules.items():
                    self._write_notification_rules(conn, icao, parsed, now)
            
            conn.commit()
            logger.info(f"Updated {updated} airports in ga_meta.sqlite")
            return updated
            
        finally:
            conn.close()
    
    def _write_notification_rules(
        self,
        conn: sqlite3.Connection,
        icao: str,
        parsed: ParsedNotificationRules,
        timestamp: str,
    ) -> None:
        """Write parsed rules to ga_notification_requirements table."""
        import json
        
        # Delete existing rules for this airport
        conn.execute(
            "DELETE FROM ga_notification_requirements WHERE icao = ?",
            (icao,)
        )
        
        # Insert new rules
        for rule in parsed.rules:
            conn.execute(
                """
                INSERT INTO ga_notification_requirements (
                    icao, rule_type, weekday_start, weekday_end,
                    notification_hours, notification_type,
                    specific_time, business_day_offset, is_obligatory,
                    includes_holidays, schengen_only, non_schengen_only,
                    conditions_json, raw_text, source_std_field_id,
                    confidence, created_utc, updated_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    icao,
                    rule.rule_type.value,
                    rule.weekday_start,
                    rule.weekday_end,
                    rule.hours_notice,
                    rule.notification_type.value,
                    rule.specific_time,
                    rule.business_day_offset,
                    1 if rule.is_obligatory else 0,
                    1 if rule.includes_holidays else 0,
                    1 if rule.schengen_only else 0,
                    1 if rule.non_schengen_only else 0,
                    json.dumps(rule.conditions) if rule.conditions else None,
                    rule.raw_text,
                    parsed.source_std_field_id,
                    rule.confidence,
                    timestamp,
                    timestamp,
                )
            )

