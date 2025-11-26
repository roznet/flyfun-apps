"""
Notification rule parser.

Extracts structured notification rules from AIP customs/immigration text.
Uses regex patterns for common cases, with optional LLM fallback for complex cases.
"""

import re
import logging
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

from .models import (
    NotificationRule,
    RuleType,
    NotificationType,
    ParsedNotificationRules,
)

logger = logging.getLogger(__name__)


class NotificationParser:
    """
    Parse notification requirements from AIP text.
    
    Strategy:
        1. Try regex patterns for common cases (fast, deterministic)
        2. Optionally fall back to LLM for complex/unparseable cases
    """
    
    # Regex patterns for hours notice
    # Matches: "PPR 24 HR", "PN 48 HR", "PPR PN 24HR", "48HR PPR MNM", "4 hours prior notice"
    HOURS_PATTERN = re.compile(
        r'(?:(?:PPR|PN|PPR\s*PN)\s*(?:MNM\s+)?(\d+)\s*(?:HR?S?|HOURS?))|'
        r'(?:(\d+)\s*(?:HR?S?|HOURS?)\s*(?:PPR|PN)\s*(?:MNM)?)|'
        r'(?:(\d+)\s*(?:HR?S?|HOURS?)\s+(?:prior\s+)?(?:notice|advance|PN))',
        re.IGNORECASE
    )
    
    # Pattern for weekday-specific rules
    WEEKDAY_HOURS_PATTERN = re.compile(
        r'(MON(?:DAY)?|TUE(?:SDAY)?|WED(?:NESDAY)?|THU(?:RSDAY)?|FRI(?:DAY)?|SAT(?:URDAY)?|SUN(?:DAY)?|WEEK-?END|WEEK-?DAYS?|HOL(?:IDAYS?)?)'
        r'(?:\s*[-\u2013]\s*(MON(?:DAY)?|TUE(?:SDAY)?|WED(?:NESDAY)?|THU(?:RSDAY)?|FRI(?:DAY)?|SAT(?:URDAY)?|SUN(?:DAY)?|HOL(?:IDAYS?)?))?'
        r'\s*[,:]\s*'
        r'(?:PPR|PN|PPR\s*PN)?\s*(?:MNM\s+)?(\d+)\s*(?:HR?S?|HOURS?)',
        re.IGNORECASE
    )
    
    # Pattern for H24 (24-hour availability)
    H24_PATTERN = re.compile(r'\bH24\b', re.IGNORECASE)
    
    # Pattern for "on request" / "by arrangement"
    ON_REQUEST_PATTERN = re.compile(
        r'\b(?:O/R|on\s+request|by\s+(?:prior\s+)?arrangement|sur\s+demande|subject\s+to\s+(?:notified|notice))\b',
        re.IGNORECASE
    )
    
    # Pattern for "as AD hours"
    AS_AD_HOURS_PATTERN = re.compile(
        r'\b(?:as\s+AD\s+(?:hours?|HR)|AD\s+OPR\s+HR|HR\s+AD|AS\s+AD\s+HR)\b',
        re.IGNORECASE
    )
    
    # Pattern for business day rules
    BUSINESS_DAY_PATTERN = re.compile(
        r'(?:last\s+)?(?:working|business)\s+day\s+(?:before\s+)?(\d{4})?',
        re.IGNORECASE
    )
    
    # Pattern for operating hours
    OPERATING_HOURS_PATTERN = re.compile(r'\b(\d{4})\s*[-\u2013]\s*(\d{4})\b')
    
    # Pattern for Schengen references
    SCHENGEN_PATTERN = re.compile(
        r'\b(?:extra[- ]?schengen|non[- ]?schengen|outside\s+(?:the\s+)?schengen)\b',
        re.IGNORECASE
    )
    
    INTRA_SCHENGEN_PATTERN = re.compile(
        r'\b(?:intra[- ]?schengen|within\s+(?:the\s+)?schengen|schengen\s+(?:flights?|only))\b',
        re.IGNORECASE
    )
    
    # Day name to number mapping
    DAY_MAP = {
        'mon': 0, 'monday': 0,
        'tue': 1, 'tuesday': 1,
        'wed': 2, 'wednesday': 2,
        'thu': 3, 'thursday': 3,
        'fri': 4, 'friday': 4,
        'sat': 5, 'saturday': 5,
        'sun': 6, 'sunday': 6,
        'weekday': (0, 4),
        'weekdays': (0, 4),
        'week-end': (5, 6),
        'weekend': (5, 6),
    }
    
    def __init__(
        self,
        use_llm_fallback: bool = False,
        llm_model: str = "gpt-4o-mini",
        llm_api_key: Optional[str] = None,
    ):
        self.use_llm_fallback = use_llm_fallback
        self.llm_model = llm_model
        self.llm_api_key = llm_api_key
        self._llm_chain = None
    
    def parse(self, icao: str, text: str, std_field_id: int = 302) -> ParsedNotificationRules:
        """Parse notification rules from AIP text."""
        if not text or not text.strip():
            return ParsedNotificationRules(
                icao=icao,
                raw_text=text or "",
                source_std_field_id=std_field_id,
                parse_warnings=["Empty text"],
            )
        
        text = text.strip()
        rules: List[NotificationRule] = []
        warnings: List[str] = []
        
        # Check for H24 first
        if self.H24_PATTERN.search(text):
            rules.append(NotificationRule(
                rule_type=RuleType.CUSTOMS,
                notification_type=NotificationType.H24,
                raw_text=text,
                confidence=0.95,
            ))
        
        # Check for "on request"
        elif self.ON_REQUEST_PATTERN.search(text) and not self.HOURS_PATTERN.search(text):
            rules.append(NotificationRule(
                rule_type=RuleType.CUSTOMS,
                notification_type=NotificationType.ON_REQUEST,
                raw_text=text,
                confidence=0.9,
            ))
        
        # Check for "as AD hours"
        elif self.AS_AD_HOURS_PATTERN.search(text) and not self.HOURS_PATTERN.search(text):
            rules.append(NotificationRule(
                rule_type=RuleType.CUSTOMS,
                notification_type=NotificationType.AS_AD_HOURS,
                raw_text=text,
                confidence=0.9,
            ))
        
        else:
            # Try weekday-specific rules first
            weekday_rules = self._extract_weekday_rules(text)
            if weekday_rules:
                rules.extend(weekday_rules)
            
            # If no weekday rules, try general hours
            if not rules:
                hours_rules = self._extract_hours_rules(text)
                if hours_rules:
                    rules.extend(hours_rules)
            
            # Try business day rules
            business_rules = self._extract_business_day_rules(text)
            if business_rules:
                rules.extend(business_rules)
        
        # Add Schengen context
        is_non_schengen = bool(self.SCHENGEN_PATTERN.search(text))
        is_schengen = bool(self.INTRA_SCHENGEN_PATTERN.search(text))
        
        for rule in rules:
            if is_non_schengen and not is_schengen:
                rule.non_schengen_only = True
            elif is_schengen and not is_non_schengen:
                rule.schengen_only = True
        
        # LLM fallback
        if not rules and self.use_llm_fallback:
            llm_rules = self._parse_with_llm(icao, text)
            if llm_rules:
                rules.extend(llm_rules)
            else:
                warnings.append("Could not parse with regex or LLM")
        elif not rules:
            warnings.append("Could not parse notification rules with regex patterns")
        
        return ParsedNotificationRules(
            icao=icao,
            rules=rules,
            raw_text=text,
            source_std_field_id=std_field_id,
            parse_warnings=warnings,
        )
    
    def _parse_day(self, day_str: str) -> Tuple[Optional[int], Optional[int], bool]:
        """Parse day string into start/end day numbers."""
        day_str = day_str.lower().strip()
        includes_holidays = 'hol' in day_str
        
        day_str = re.sub(r'\s*(?:and\s+)?hol(?:idays?)?', '', day_str, flags=re.IGNORECASE).strip()
        
        if day_str in self.DAY_MAP:
            result = self.DAY_MAP[day_str]
            if isinstance(result, tuple):
                return result[0], result[1], includes_holidays
            return result, None, includes_holidays
        
        return None, None, includes_holidays
    
    def _extract_weekday_rules(self, text: str) -> List[NotificationRule]:
        """Extract rules that are weekday-specific."""
        rules = []
        
        for match in self.WEEKDAY_HOURS_PATTERN.finditer(text):
            day_start_str = match.group(1)
            day_end_str = match.group(2)
            hours = int(match.group(3))
            
            start_day, end_day_from_start, includes_hol = self._parse_day(day_start_str)
            
            if day_end_str:
                end_day, _, hol2 = self._parse_day(day_end_str)
                includes_hol = includes_hol or hol2
            else:
                end_day = end_day_from_start
            
            rule = NotificationRule(
                rule_type=RuleType.PPR,
                notification_type=NotificationType.HOURS,
                hours_notice=hours,
                weekday_start=start_day,
                weekday_end=end_day,
                includes_holidays=includes_hol,
                raw_text=match.group(0),
                confidence=0.85,
            )
            rules.append(rule)
        
        return rules
    
    def _extract_hours_rules(self, text: str) -> List[NotificationRule]:
        """Extract simple hours-based rules."""
        rules = []
        
        for match in self.HOURS_PATTERN.finditer(text):
            # Try each capture group (pattern has 3 alternatives)
            hours = None
            for group_num in [1, 2, 3]:
                if match.group(group_num):
                    hours = int(match.group(group_num))
                    break
            
            if hours is None:
                continue
            
            rule = NotificationRule(
                rule_type=RuleType.PPR,
                notification_type=NotificationType.HOURS,
                hours_notice=hours,
                raw_text=match.group(0),
                confidence=0.8,
            )
            rules.append(rule)
        
        # Deduplicate by hours
        seen_hours = set()
        unique_rules = []
        for rule in rules:
            if rule.hours_notice not in seen_hours:
                seen_hours.add(rule.hours_notice)
                unique_rules.append(rule)
        
        return unique_rules
    
    def _extract_business_day_rules(self, text: str) -> List[NotificationRule]:
        """Extract business day rules."""
        rules = []
        
        for match in self.BUSINESS_DAY_PATTERN.finditer(text):
            time_str = match.group(1)
            
            rule = NotificationRule(
                rule_type=RuleType.PPR,
                notification_type=NotificationType.BUSINESS_DAY,
                business_day_offset=-1,
                specific_time=time_str,
                raw_text=match.group(0),
                confidence=0.75,
            )
            rules.append(rule)
        
        return rules
    
    def _parse_with_llm(self, icao: str, text: str) -> List[NotificationRule]:
        """Use LLM to parse complex notification text."""
        if not self.use_llm_fallback:
            return []
        
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import JsonOutputParser
        except ImportError:
            logger.warning("LangChain not available for LLM fallback")
            return []
        
        # LLM implementation would go here
        return []
    
    def parse_batch(
        self, 
        airports: List[Tuple[str, str]],
        std_field_id: int = 302,
    ) -> List[ParsedNotificationRules]:
        """Parse notification rules for multiple airports."""
        return [
            self.parse(icao, text, std_field_id)
            for icao, text in airports
        ]

