"""
Notification Query API Endpoints.

Provides REST API endpoints for querying customs/immigration notification requirements.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from shared.ga_notification_agent.notification_query import (
    get_notification_for_airport,
    find_airports_by_notification,
    get_notification_statistics,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class AirportNotificationResponse(BaseModel):
    """Response for single airport notification query."""
    found: bool
    icao: str
    rule_type: Optional[str] = None
    notification_type: Optional[str] = None
    hours_notice: Optional[int] = None
    operating_hours: Optional[str] = None
    summary: Optional[str] = None
    confidence: Optional[float] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    day_specific_rule: Optional[str] = None
    pretty: str
    error: Optional[str] = None


class AirportItem(BaseModel):
    icao: str
    notification_type: Optional[str] = None
    hours_notice: Optional[int] = None
    summary: Optional[str] = None
    name: Optional[str] = None
    municipality: Optional[str] = None
    country: Optional[str] = None


class FilteredAirportsResponse(BaseModel):
    """Response for filtered airports query."""
    found: bool
    count: int
    airports: List[AirportItem]
    pretty: str
    error: Optional[str] = None


class NotificationStatsResponse(BaseModel):
    """Response for notification statistics."""
    found: bool
    total: Optional[int] = None
    avg_confidence: Optional[float] = None
    avg_hours_notice: Optional[float] = None
    by_type: Optional[Dict[str, int]] = None
    pretty: str
    error: Optional[str] = None


@router.get("/{icao}", response_model=AirportNotificationResponse)
async def get_airport_notification(
    icao: str,
    day_of_week: Optional[str] = Query(
        None,
        description="Day of week to get specific rules (e.g., Saturday, Monday)"
    )
):
    """
    Get customs/immigration notification requirements for a specific airport.
    
    Pass `day_of_week` to get day-specific rules (e.g., Saturday may require more notice).
    """
    result = get_notification_for_airport(icao, day_of_week)
    return AirportNotificationResponse(**result)


@router.get("/")
async def filter_airports_by_notification(
    max_hours_notice: Optional[int] = Query(
        None,
        description="Maximum hours notice required (e.g., 24 for '<24h notice')"
    ),
    notification_type: Optional[str] = Query(
        None,
        description="Type filter: 'h24', 'hours', 'on_request', 'business_day'"
    ),
    country: Optional[str] = Query(
        None,
        description="ISO-2 country code (e.g., FR, DE, GB)"
    ),
    limit: int = Query(
        20,
        description="Maximum results to return"
    )
) -> FilteredAirportsResponse:
    """
    Find airports filtered by notification requirements.
    
    Examples:
    - `/api/notifications/?max_hours_notice=24&country=FR` - French airports with <24h notice
    - `/api/notifications/?notification_type=h24` - All H24 airports (no notice needed)
    """
    result = find_airports_by_notification(
        max_hours_notice=max_hours_notice,
        notification_type=notification_type,
        country=country,
        limit=limit
    )
    
    # Convert airport dicts to AirportItem objects
    if result.get("airports"):
        result["airports"] = [AirportItem(**apt) for apt in result["airports"]]
    else:
        result["airports"] = []
    
    return FilteredAirportsResponse(**result)


@router.get("/stats/summary", response_model=NotificationStatsResponse)
async def get_statistics():
    """
    Get summary statistics about parsed notification requirements.
    """
    result = get_notification_statistics()
    return NotificationStatsResponse(**result)
