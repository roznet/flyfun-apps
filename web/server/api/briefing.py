#!/usr/bin/env python3

"""
Briefing API endpoint for parsing ForeFlight PDFs and other briefing sources.

POST /api/briefing/parse - Parse a briefing file and return structured NOTAM data.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime, timezone
import tempfile
import logging
import os


def serialize_datetime(dt: datetime) -> str:
    """Serialize datetime to ISO8601 format compatible with Swift's .iso8601 decoder."""
    if dt is None:
        return None
    # Ensure timezone-aware and format without fractional seconds
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

from euro_aip.briefing import ForeFlightSource, CategorizationPipeline
from euro_aip.briefing.categorization import parse_q_code
from euro_aip.models.euro_aip_model import EuroAipModel

logger = logging.getLogger(__name__)

# Global model reference (set by main.py during startup)
model: Optional[EuroAipModel] = None

def set_model(m: EuroAipModel):
    """Set the global model reference for geocoding."""
    global model
    model = m
    logger.info(f"Briefing API: model set with {m.airports.count()} airports")

def geocode_route(route) -> None:
    """Geocode route departure/destination using airport coordinates."""
    if route is None:
        return

    if model is None:
        logger.warning("No model available for geocoding")
        return

    # Geocode departure
    if route.departure and not route.departure_coords:
        airport = model.airports.get(route.departure)
        if airport and airport.latitude_deg is not None:
            route.departure_coords = (airport.latitude_deg, airport.longitude_deg)
            logger.info(f"Geocoded departure {route.departure}: {route.departure_coords}")

    # Geocode destination
    if route.destination and not route.destination_coords:
        airport = model.airports.get(route.destination)
        if airport and airport.latitude_deg is not None:
            route.destination_coords = (airport.latitude_deg, airport.longitude_deg)
            logger.info(f"Geocoded destination {route.destination}: {route.destination_coords}")

router = APIRouter()


# =============================================================================
# Pydantic Response Models
# =============================================================================

class SwiftCompatibleModel(BaseModel):
    """Base model with Swift-compatible datetime serialization."""
    model_config = ConfigDict(
        json_encoders={datetime: serialize_datetime}
    )


class RoutePointResponse(SwiftCompatibleModel):
    """A waypoint along a flight route."""
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    point_type: str = "waypoint"


class RouteResponse(SwiftCompatibleModel):
    """Flight route information."""
    departure: str
    destination: str
    alternates: List[str] = Field(default_factory=list)
    waypoints: List[str] = Field(default_factory=list)
    departure_coords: Optional[List[float]] = None
    destination_coords: Optional[List[float]] = None
    waypoint_coords: List[RoutePointResponse] = Field(default_factory=list)
    aircraft_type: Optional[str] = None
    departure_time: Optional[datetime] = None
    arrival_time: Optional[datetime] = None
    flight_level: Optional[int] = None


class QCodeInfoResponse(SwiftCompatibleModel):
    """Parsed Q-code information."""
    q_code: str
    subject_code: str
    subject_meaning: str
    subject_phrase: str
    subject_category: str
    condition_code: str
    condition_meaning: str
    condition_phrase: str
    condition_category: str
    display_text: str
    short_text: str
    is_checklist: bool = False
    is_plain_language: bool = False


class NotamResponse(SwiftCompatibleModel):
    """NOTAM data from a parsed briefing."""
    id: str
    location: str
    raw_text: str = ""
    message: str = ""

    # Identity
    series: Optional[str] = None
    number: Optional[int] = None
    year: Optional[int] = None

    # Location
    fir: Optional[str] = None
    affected_locations: List[str] = Field(default_factory=list)

    # Q-code fields
    q_code: Optional[str] = None
    q_code_info: Optional[QCodeInfoResponse] = None
    traffic_type: Optional[str] = None
    purpose: Optional[str] = None
    scope: Optional[str] = None
    lower_limit: Optional[int] = None
    upper_limit: Optional[int] = None
    coordinates: Optional[List[float]] = None
    radius_nm: Optional[float] = None

    # Category
    category: Optional[str] = None
    subcategory: Optional[str] = None

    # Schedule
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    is_permanent: bool = False
    schedule_text: Optional[str] = None

    # Metadata
    source: Optional[str] = None
    parsed_at: datetime = Field(default_factory=datetime.now)
    parse_confidence: float = 1.0

    # Custom categorization
    primary_category: Optional[str] = None
    custom_categories: List[str] = Field(default_factory=list)
    custom_tags: List[str] = Field(default_factory=list)


class BriefingResponse(SwiftCompatibleModel):
    """Response from parsing a briefing file."""
    id: str
    created_at: datetime
    source: str
    route: Optional[RouteResponse] = None
    notams: List[NotamResponse]
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    notam_count: int = 0


# =============================================================================
# Source Registry
# =============================================================================

# Multi-source architecture: extensible for future sources
SOURCES = {
    "foreflight": ForeFlightSource,
    # Future: "skydemon": SkyDemonSource, "autorouter": AutoRouterSource, etc.
}


# =============================================================================
# Helper Functions
# =============================================================================

def _route_to_response(route) -> Optional[RouteResponse]:
    """Convert Route model to RouteResponse."""
    if route is None:
        return None

    return RouteResponse(
        departure=route.departure,
        destination=route.destination,
        alternates=route.alternates or [],
        waypoints=route.waypoints or [],
        departure_coords=list(route.departure_coords) if route.departure_coords else None,
        destination_coords=list(route.destination_coords) if route.destination_coords else None,
        waypoint_coords=[
            RoutePointResponse(
                name=wp.name,
                latitude=wp.latitude,
                longitude=wp.longitude,
                point_type=wp.point_type,
            )
            for wp in (route.waypoint_coords or [])
        ],
        aircraft_type=route.aircraft_type,
        departure_time=route.departure_time,
        arrival_time=route.arrival_time,
        flight_level=route.flight_level,
    )


def _notam_to_response(notam) -> NotamResponse:
    """Convert Notam model to NotamResponse."""
    # Parse Q-code info if available
    q_code_info = None
    if notam.q_code:
        info = parse_q_code(notam.q_code)
        q_code_info = QCodeInfoResponse(
            q_code=info.q_code,
            subject_code=info.subject_code,
            subject_meaning=info.subject_meaning,
            subject_phrase=info.subject_phrase,
            subject_category=info.subject_category,
            condition_code=info.condition_code,
            condition_meaning=info.condition_meaning,
            condition_phrase=info.condition_phrase,
            condition_category=info.condition_category,
            display_text=info.display_text,
            short_text=info.short_text,
            is_checklist=info.is_checklist,
            is_plain_language=info.is_plain_language,
        )

    return NotamResponse(
        id=notam.id,
        location=notam.location,
        raw_text=notam.raw_text,
        message=notam.message,
        series=notam.series,
        number=notam.number,
        year=notam.year,
        fir=notam.fir,
        affected_locations=notam.affected_locations or [],
        q_code=notam.q_code,
        q_code_info=q_code_info,
        traffic_type=notam.traffic_type,
        purpose=notam.purpose,
        scope=notam.scope,
        lower_limit=notam.lower_limit,
        upper_limit=notam.upper_limit,
        coordinates=list(notam.coordinates) if notam.coordinates else None,
        radius_nm=notam.radius_nm,
        category=notam.category.value if notam.category else None,
        subcategory=notam.subcategory,
        effective_from=notam.effective_from,
        effective_to=notam.effective_to,
        is_permanent=notam.is_permanent,
        schedule_text=notam.schedule_text,
        source=notam.source,
        parsed_at=notam.parsed_at,
        parse_confidence=notam.parse_confidence,
        primary_category=notam.primary_category,
        custom_categories=list(notam.custom_categories) if notam.custom_categories else [],
        custom_tags=list(notam.custom_tags) if notam.custom_tags else [],
    )


def _briefing_to_response(briefing) -> BriefingResponse:
    """Convert Briefing model to BriefingResponse."""
    return BriefingResponse(
        id=briefing.id,
        created_at=briefing.created_at,
        source=briefing.source,
        route=_route_to_response(briefing.route),
        notams=[_notam_to_response(n) for n in briefing.notams],
        valid_from=briefing.valid_from,
        valid_to=briefing.valid_to,
        notam_count=len(briefing.notams),
    )


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/parse", response_model=BriefingResponse)
async def parse_briefing(
    file: UploadFile = File(..., description="Briefing file (PDF)"),
    source: str = Query("foreflight", description="Briefing source: foreflight, etc.")
):
    """
    Parse a briefing file and return structured NOTAM data.

    Supports multiple sources with consistent JSON output format.
    The `source` field in the response indicates the origin (foreflight, skydemon, etc.).

    **Supported sources:**
    - `foreflight` - ForeFlight briefing PDFs

    **Returns:**
    - Parsed briefing with route information and NOTAMs
    - Each NOTAM includes categorization from the CategorizationPipeline
    """
    # Validate source
    if source not in SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source: {source}. Supported: {list(SOURCES.keys())}"
        )

    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )

    # Save uploaded file to temp location
    temp_path = None
    try:
        # Create temp file with size limit (20 MB)
        max_size = 20 * 1024 * 1024
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            temp_path = tmp.name
            content = await file.read(max_size + 1)
            if len(content) > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {max_size // (1024 * 1024)} MB"
                )
            tmp.write(content)

        logger.info(f"Parsing briefing from {file.filename} (source={source})")

        # Parse using appropriate source handler
        source_handler = SOURCES[source]()
        briefing = source_handler.parse(temp_path)

        # Geocode route with airport coordinates
        geocode_route(briefing.route)

        # Apply categorization pipeline
        pipeline = CategorizationPipeline()
        pipeline.categorize_all(briefing.notams)

        logger.info(f"Parsed {len(briefing.notams)} NOTAMs from briefing")

        return _briefing_to_response(briefing)

    except FileNotFoundError as e:
        logger.error(f"File processing error: {e}")
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")
    except Exception as e:
        logger.error(f"Error parsing briefing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error parsing briefing: {str(e)}")
    finally:
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")


@router.get("/sources")
async def list_sources():
    """
    List available briefing sources.

    Returns a list of supported source identifiers that can be used
    with the POST /parse endpoint.
    """
    return {
        "sources": list(SOURCES.keys()),
        "default": "foreflight",
    }
