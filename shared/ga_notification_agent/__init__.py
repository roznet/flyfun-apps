"""
GA Notification Agent - Parse AIP notification requirements.

This module extracts structured notification rules from AIP customs/immigration
text fields and computes hassle scores for GA friendliness.
"""

from .models import (
    NotificationRule,
    RuleType,
    NotificationType,
    ParsedNotificationRules,
    HassleScore,
)
from .parser import NotificationParser
from .scorer import NotificationScorer

__all__ = [
    "NotificationRule",
    "RuleType", 
    "NotificationType",
    "ParsedNotificationRules",
    "HassleScore",
    "NotificationParser",
    "NotificationScorer",
]

