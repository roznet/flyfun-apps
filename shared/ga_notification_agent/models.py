"""
Models for notification requirement parsing.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class RuleType(str, Enum):
    """Type of notification rule."""
    PPR = "ppr"                    # Prior Permission Required
    PN = "pn"                      # Prior Notice
    CUSTOMS = "customs"            # Customs notification
    IMMIGRATION = "immigration"    # Immigration notification
    HANDLING = "handling"          # Handling notification


class NotificationType(str, Enum):
    """How the notification timing is specified."""
    HOURS = "hours"                # X hours before (24, 48, etc.)
    BUSINESS_DAY = "business_day"  # Business day before with optional time
    SPECIFIC_TIME = "specific_time"  # Before specific time (e.g., before 1300)
    ON_REQUEST = "on_request"      # O/R, by arrangement
    H24 = "h24"                    # Available 24 hours
    AS_AD_HOURS = "as_ad_hours"    # As aerodrome hours
    NOT_AVAILABLE = "not_available"  # Service not available
    UNKNOWN = "unknown"            # Could not parse


class NotificationRule(BaseModel):
    """
    Structured representation of a notification requirement.
    
    Examples:
        - "PPR 24 HR" -> hours=24, notification_type=HOURS
        - "PN on last working day before 1500" -> notification_type=BUSINESS_DAY, specific_time="1500"
        - "O/R" -> notification_type=ON_REQUEST
        - "H24" -> notification_type=H24
    """
    rule_type: RuleType = Field(..., description="Type of notification (PPR, PN, customs, etc.)")
    notification_type: NotificationType = Field(..., description="How timing is specified")
    
    # Time-based fields
    hours_notice: Optional[int] = Field(None, description="Hours notice required (24, 48, etc.)")
    
    # Day-specific fields
    weekday_start: Optional[int] = Field(None, ge=0, le=6, description="Start weekday (0=Monday, 6=Sunday)")
    weekday_end: Optional[int] = Field(None, ge=0, le=6, description="End weekday (inclusive)")
    includes_holidays: bool = Field(False, description="Whether this rule applies to holidays")
    
    # Business day fields  
    business_day_offset: Optional[int] = Field(None, description="Days before (-1 = last business day)")
    specific_time: Optional[str] = Field(None, description="Specific time cutoff (e.g., '1500')")
    
    # Operating hours
    hours_start: Optional[str] = Field(None, description="Service start time (e.g., '0700')")
    hours_end: Optional[str] = Field(None, description="Service end time (e.g., '1900')")
    
    # Conditions
    is_obligatory: bool = Field(True, description="Whether notification is mandatory")
    schengen_only: bool = Field(False, description="Only applies to Schengen flights")
    non_schengen_only: bool = Field(False, description="Only applies to non-Schengen flights")
    conditions: Optional[Dict[str, Any]] = Field(None, description="Additional conditions")
    
    # Source tracking
    raw_text: Optional[str] = Field(None, description="Original text this was extracted from")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Extraction confidence")
    extraction_method: str = Field("regex", description="How this was extracted (regex/llm)")

    def get_weekday_description(self) -> str:
        """Get human-readable weekday description."""
        days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        if self.weekday_start is None:
            return "all days"
        if self.weekday_end is None:
            return days[self.weekday_start]
        if self.weekday_start == 0 and self.weekday_end == 4:
            return "weekdays"
        if self.weekday_start == 5 and self.weekday_end == 6:
            return "weekends"
        return f"{days[self.weekday_start]}-{days[self.weekday_end]}"


class ParsedNotificationRules(BaseModel):
    """Complete parsed notification rules for an airport."""
    icao: str
    rules: List[NotificationRule] = Field(default_factory=list)
    raw_text: str = Field(..., description="Original AIP text")
    source_std_field_id: int = Field(302, description="AIP field ID (302 = customs/immigration)")
    parse_warnings: List[str] = Field(default_factory=list, description="Warnings during parsing")
    
    @property
    def has_rules(self) -> bool:
        return len(self.rules) > 0
    
    @property 
    def is_h24(self) -> bool:
        """Check if any rule indicates H24 availability."""
        return any(r.notification_type == NotificationType.H24 for r in self.rules)
    
    @property
    def is_on_request(self) -> bool:
        """Check if notification is on request only."""
        return all(r.notification_type == NotificationType.ON_REQUEST for r in self.rules) and self.has_rules
    
    @property
    def max_hours_notice(self) -> Optional[int]:
        """Get maximum hours notice required across all rules."""
        hours = [r.hours_notice for r in self.rules if r.hours_notice is not None]
        return max(hours) if hours else None
    
    def get_summary(self) -> str:
        """Generate a human-readable summary of the rules."""
        if not self.has_rules:
            return "No notification rules parsed"
        
        if self.is_h24:
            return "H24 - No prior notice required"
        
        if self.is_on_request:
            return "On request / by arrangement"
        
        # Collect unique descriptions
        summaries = []
        for rule in self.rules:
            if rule.notification_type == NotificationType.HOURS and rule.hours_notice:
                weekday_desc = rule.get_weekday_description()
                if weekday_desc == "all days":
                    summaries.append(f"PPR {rule.hours_notice}h")
                else:
                    summaries.append(f"{weekday_desc}: PPR {rule.hours_notice}h")
            elif rule.notification_type == NotificationType.BUSINESS_DAY:
                time_str = f" before {rule.specific_time}" if rule.specific_time else ""
                summaries.append(f"Last business day{time_str}")
            elif rule.notification_type == NotificationType.ON_REQUEST:
                summaries.append("O/R")
        
        return "; ".join(summaries) if summaries else "See detailed rules"


class HassleLevel(str, Enum):
    """Overall hassle level for notifications."""
    NONE = "none"          # H24, no hassle
    LOW = "low"            # Simple O/R or same-day
    MODERATE = "moderate"  # 24h notice
    HIGH = "high"          # 48h+ notice or business day rules
    VERY_HIGH = "very_high"  # 72h+ or complex rules
    NOT_AVAILABLE = "not_available"  # Service not available


class HassleScore(BaseModel):
    """Hassle score for an airport's notification requirements."""
    icao: str
    level: HassleLevel
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized score (0=no hassle, 1=max hassle)")
    summary: str = Field(..., description="Human-readable summary")
    max_hours_notice: Optional[int] = Field(None, description="Maximum hours notice required")
    has_weekend_rules: bool = Field(False, description="Different rules for weekends")
    has_schengen_rules: bool = Field(False, description="Different rules for Schengen/non-Schengen")
    
    @classmethod
    def from_parsed_rules(cls, parsed: ParsedNotificationRules) -> "HassleScore":
        """Compute hassle score from parsed rules."""
        icao = parsed.icao
        
        if not parsed.has_rules:
            return cls(
                icao=icao,
                level=HassleLevel.MODERATE,  # Unknown = assume moderate
                score=0.5,
                summary="Unable to parse notification rules",
            )
        
        if parsed.is_h24:
            return cls(
                icao=icao,
                level=HassleLevel.NONE,
                score=0.0,
                summary="H24 - No prior notice required",
            )
        
        if parsed.is_on_request:
            return cls(
                icao=icao,
                level=HassleLevel.LOW,
                score=0.2,
                summary="On request / by arrangement",
            )
        
        # Check for "as AD hours" - low hassle
        if all(r.notification_type == NotificationType.AS_AD_HOURS for r in parsed.rules):
            return cls(
                icao=icao,
                level=HassleLevel.LOW,
                score=0.15,
                summary="As aerodrome hours",
            )
        
        # Calculate based on hours notice
        max_hours = parsed.max_hours_notice
        has_weekend = any(r.weekday_start == 5 or r.includes_holidays for r in parsed.rules)
        has_schengen = any(r.schengen_only or r.non_schengen_only for r in parsed.rules)
        
        if max_hours is None:
            # Business day rules or other complex rules
            level = HassleLevel.HIGH
            score = 0.7
        elif max_hours <= 2:
            level = HassleLevel.LOW
            score = 0.15
        elif max_hours <= 12:
            level = HassleLevel.LOW
            score = 0.25
        elif max_hours <= 24:
            level = HassleLevel.MODERATE
            score = 0.4
        elif max_hours <= 48:
            level = HassleLevel.HIGH
            score = 0.6
        elif max_hours <= 72:
            level = HassleLevel.HIGH
            score = 0.75
        else:
            level = HassleLevel.VERY_HIGH
            score = 0.9
        
        # Increase score if weekend rules are stricter
        if has_weekend:
            score = min(1.0, score + 0.1)
        
        return cls(
            icao=icao,
            level=level,
            score=score,
            summary=parsed.get_summary(),
            max_hours_notice=max_hours,
            has_weekend_rules=has_weekend,
            has_schengen_rules=has_schengen,
        )

