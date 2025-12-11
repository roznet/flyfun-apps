#!/usr/bin/env python3

from fastapi import APIRouter, Query, HTTPException, Request, Path, Body
from typing import List, Optional, Dict, Any, Union, TypeAlias
import logging

from euro_aip.models.euro_aip_model import EuroAipModel
from euro_aip.models.airport import Airport
from euro_aip.models.navpoint import NavPoint
from .models import AirportSummary, AirportDetail, AIPEntryResponse, GAFriendlySummary
from .ga_friendliness import get_service as get_ga_service
from shared.airport_tools import ToolContext, find_airports_near_location

# Type alias for route airports (can be ICAO codes or NavPoint objects)
Route: TypeAlias = List[Union[str, NavPoint]]

logger = logging.getLogger(__name__)

router = APIRouter()

# Global model reference
model: Optional[EuroAipModel] = None

def set_model(m: EuroAipModel):
    """Set the global model reference."""
    global model
    model = m

def _matches_aip_field(airport: Airport, field_name: str, value: Optional[str] = None, operator: str = "contains") -> bool:
    """
    Check if an airport matches AIP field criteria.
    
    Args:
        airport: Airport object to check
        field_name: Standardized AIP field name
        value: Value to search for (optional for not_empty operator)
        operator: Comparison operator
        
    Returns:
        True if airport matches the criteria
    """
    # Get all entries for this field
    field_entries = [entry for entry in airport.aip_entries if entry.std_field == field_name]
    
    if not field_entries:
        return False
    
    # Check each entry value
    for entry in field_entries:
        entry_value = entry.value.lower() if entry.value else ""
        search_value = value.lower() if value else ""
        
        # Handle negative values that should return False
        if entry_value in ["nil", "none", "na", "n/a", "no", "not available", "unavailable"]:
            continue  # Skip this entry, it's a negative value
        
        if operator == "contains":
            # Special handling for AVGAS detection
            if search_value == "avgas" and field_name.lower() in ["fuel and oil types", "fuel types", "fuel"]:
                # Check for various AVGAS/100LL variations
                if any(avgas_term in entry_value for avgas_term in ["avgas", "100ll", "100 ll", "100/ll"]):
                    return True
            else:
                # Standard contains logic
                if search_value in entry_value:
                    return True
        elif operator == "equals":
            if entry_value == search_value:
                return True
        elif operator == "not_empty":
            # Enhanced not_empty logic - exclude negative values
            if entry_value and entry_value not in ["nil", "none", "na", "n/a", "no", "not available", "unavailable", ""]:
                return True
        elif operator == "starts_with":
            if entry_value.startswith(search_value):
                return True
        elif operator == "ends_with":
            if entry_value.endswith(search_value):
                return True
    
    return False

# API models are now imported from ../models

@router.get("/", response_model=List[AirportSummary])
async def get_airports(
    request: Request,
    country: Optional[str] = Query(None, description="Filter by ISO country code", max_length=3),
    has_procedures: Optional[bool] = Query(None, description="Filter airports with procedures"),
    has_aip_data: Optional[bool] = Query(None, description="Filter airports with AIP data"),
    has_hard_runway: Optional[bool] = Query(None, description="Filter airports with hard runways"),
    point_of_entry: Optional[bool] = Query(None, description="Filter border crossing airports"),
    # New AIP field filters
    aip_field: Optional[str] = Query(None, description="AIP standardized field name to filter by", max_length=100),
    aip_value: Optional[str] = Query(None, description="Value to search for in the AIP field", max_length=200),
    aip_operator: str = Query("contains", description="Operator for AIP field filtering: contains, equals, not_empty, starts_with, ends_with", max_length=20),
    limit: int = Query(1000, description="Maximum number of airports to return", ge=1, le=10000),
    offset: int = Query(0, description="Number of airports to skip", ge=0, le=100000),
    # GA Friendliness integration
    include_ga: bool = Query(True, description="Include GA friendliness scores (all personas pre-computed)")
):
    """Get a list of airports with optional filtering."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    # Validate offset against actual data size
    if offset >= len(model.airports):
        raise HTTPException(status_code=400, detail="Offset too large")
    
    airports = list(model.airports.values())
    
    # Apply filters
    if country:
        airports = [a for a in airports if a.iso_country == country]
    
    if has_procedures is not None:
        airports = [a for a in airports if bool(a.procedures) == has_procedures]
    
    if has_aip_data is not None:
        airports = [a for a in airports if bool(a.aip_entries) == has_aip_data]
    
    if has_hard_runway is not None:
        airports = [a for a in airports if a.has_hard_runway == has_hard_runway]
    
    if point_of_entry is not None:
        airports = [a for a in airports if a.point_of_entry == point_of_entry]
    
    # Apply AIP field filtering
    if aip_field:
        airports = [a for a in airports if _matches_aip_field(a, aip_field, aip_value, aip_operator)]
    
    # Always sort by longest runway length (descending) to prioritize larger airports
    # Airports without runway data will be sorted last
    airports.sort(key=lambda a: a.longest_runway_length_ft or 0, reverse=True)
    
    # Apply pagination
    airports = airports[offset:offset + limit]
    
    # Get GA data if requested and service is available
    ga_data: Dict[str, GAFriendlySummary] = {}
    if include_ga:
        ga_service = get_ga_service()
        if ga_service and ga_service.enabled:
            icaos = [a.ident for a in airports]
            ga_data = ga_service.get_summaries_batch(icaos)
    
    # Convert to response format using factory methods
    return [
        AirportSummary.from_airport(airport, ga_data.get(airport.ident))
        for airport in airports
    ]

@router.get("/route-search")
async def get_airports_near_route(
    request: Request,
    airports: str = Query(..., description="Comma-separated list of ICAO airport codes defining the route", max_length=200),
    segment_distance_nm: float = Query(50.0, description="Max perpendicular distance from route (NM)", ge=0.1, le=500.0),
    # Backward compatibility: accept legacy distance_nm if provided
    legacy_distance_nm: Optional[float] = Query(None, alias="distance_nm", description="Deprecated: use segment_distance_nm"),
    # Optional enroute distance filter (distance from first route airport)
    enroute_distance_max_nm: Optional[float] = Query(
        None,
        description="Max great-circle distance from the first route airport (NM)"),
    country: Optional[str] = Query(None, description="Filter by ISO country code", max_length=3),
    has_procedures: Optional[bool] = Query(None, description="Filter airports with procedures"),
    has_aip_data: Optional[bool] = Query(None, description="Filter airports with AIP data"),
    has_hard_runway: Optional[bool] = Query(None, description="Filter airports with hard runways"),
    point_of_entry: Optional[bool] = Query(None, description="Filter border crossing airports"),
    # New AIP field filters
    aip_field: Optional[str] = Query(None, description="AIP standardized field name to filter by", max_length=100),
    aip_value: Optional[str] = Query(None, description="Value to search for in the AIP field", max_length=200),
    aip_operator: str = Query("contains", description="Operator for AIP field filtering: contains, equals, not_empty, starts_with, ends_with", max_length=20),
    # GA Friendliness integration
    include_ga: bool = Query(True, description="Include GA friendliness scores (all personas pre-computed)")
):
    """Find airports within a specified distance from a route defined by airport ICAO codes, with optional filtering."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    # Parse airport codes
    try:
        route_airports: Route = [code.strip().upper() for code in airports.split(',') if code.strip()]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid airport codes format: {str(e)}")
    
    if len(route_airports) < 1:
        raise HTTPException(status_code=400, detail="Route must contain at least 1 airport")
    
    # Validate airport codes
    # Type narrowing: we know all elements are strings since we just created them
    for item in route_airports:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail=f"Invalid route item type: expected str, got {type(item)}")
        icao = item
        if len(icao) != 4:
            raise HTTPException(status_code=400, detail=f"Invalid ICAO code: {icao}")
        if not model.get_airport(icao):
            raise HTTPException(status_code=404, detail=f"Airport {icao} not found")
    
    # Resolve effective segment distance (support legacy query param)
    effective_segment_distance_nm = legacy_distance_nm if legacy_distance_nm is not None else segment_distance_nm
    
    # Find airports near the route
    nearby_airports = model.find_airports_near_route(route_airports, effective_segment_distance_nm)
   
    # Apply additional filters
    filtered_airports = []
    # Prepare enroute distance context if needed
    first_route_item = route_airports[0]
    if not isinstance(first_route_item, str):
        raise HTTPException(status_code=400, detail="First route item must be a string ICAO code")
    from_airport = model.get_airport(first_route_item) if enroute_distance_max_nm is not None else None
    for item in nearby_airports:
        airport = item['airport']
        
        # Apply enroute (trip) distance max filter from first route airport
        if from_airport is not None:
            try:
                _, gc_distance_nm = from_airport.navpoint.haversine_distance(airport.navpoint) if from_airport.navpoint and airport.navpoint else (0, 0)
                if gc_distance_nm > float(enroute_distance_max_nm or 0):
                    continue
            except Exception:
                # If distance can't be computed, conservatively include
                pass
        
        # Apply country filter
        if country and airport.iso_country != country:
            continue
            
        # Apply procedures filter
        if has_procedures is not None:
            has_procs = bool(airport.procedures)
            if has_procs != has_procedures:
                continue
                
        # Apply AIP data filter
        if has_aip_data is not None:
            has_aip = bool(airport.aip_entries)
            if has_aip != has_aip_data:
                continue
                
        # Apply hard runway filter
        if has_hard_runway is not None:
            if airport.has_hard_runway != has_hard_runway:
                continue
                
        # Apply border crossing filter
        if point_of_entry is not None:
            if airport.point_of_entry != point_of_entry:
                continue
        
        # Apply AIP field filtering
        if aip_field and not _matches_aip_field(airport, aip_field, aip_value, aip_operator):
            continue
        
        # Airport passed all filters
        filtered_airports.append(item)
    
    # Get GA data if requested and service is available
    ga_data: Dict[str, GAFriendlySummary] = {}
    if include_ga:
        ga_service = get_ga_service()
        if ga_service and ga_service.enabled:
            icaos = [item['airport'].ident for item in filtered_airports]
            ga_data = ga_service.get_summaries_batch(icaos)
    
    # Convert to response format
    result = []
    for item in filtered_airports:
        airport = item['airport']
        ga_summary = ga_data.get(airport.ident)
        airport_summary = AirportSummary.from_airport(airport, ga_summary)
        
        result.append({
            'airport': airport_summary.model_dump(),
            'segment_distance_nm': item.get('segment_distance_nm'),
            'enroute_distance_nm': item.get('enroute_distance_nm'),
            'closest_segment': item.get('closest_segment')
        })
    
    return {
        'route_airports': route_airports,
        'segment_distance_nm': effective_segment_distance_nm,
        'airports_found': len(result),
        'total_nearby': len(nearby_airports),
        'filters_applied': {
            'enroute_distance_max_nm': enroute_distance_max_nm,
            'country': country,
            'has_procedures': has_procedures,
            'has_aip_data': has_aip_data,
            'has_hard_runway': has_hard_runway,
            'point_of_entry': point_of_entry,
            'aip_field': aip_field,
            'aip_value': aip_value,
            'aip_operator': aip_operator
        },
        'airports': result
    }

@router.get("/locate")
async def locate_airports(
    request: Request,
    q: Optional[str] = Query(None, description="Free-text location to search around", max_length=200),
    radius_nm: float = Query(50.0, description="Max distance from location (NM)", ge=0.1, le=500.0),
    center_lat: Optional[float] = Query(None, description="Pre-resolved center latitude (bypass geocoding)"),
    center_lon: Optional[float] = Query(None, description="Pre-resolved center longitude (bypass geocoding)"),
    country: Optional[str] = Query(None, description="Filter by ISO country code", max_length=3),
    has_procedures: Optional[bool] = Query(None, description="Filter airports with procedures"),
    has_aip_data: Optional[bool] = Query(None, description="Filter airports with AIP data"),
    has_hard_runway: Optional[bool] = Query(None, description="Filter airports with hard runways"),
    point_of_entry: Optional[bool] = Query(None, description="Filter border crossing airports"),
    # GA Friendliness integration
    include_ga: bool = Query(True, description="Include GA friendliness scores (all personas pre-computed)")
):
    """
    Locate airports near a free-text location, leveraging Geoapify geocoding via shared tool.
    """
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    filters: Dict[str, Any] = {}
    if country:
        filters["country"] = country
    if has_procedures is not None:
        filters["has_procedures"] = has_procedures
    if has_aip_data is not None:
        filters["has_aip_data"] = has_aip_data
    if has_hard_runway is not None:
        filters["has_hard_runway"] = has_hard_runway
    if point_of_entry is not None:
        filters["point_of_entry"] = point_of_entry

    # If center provided, bypass geocoding and compute directly
    if center_lat is not None and center_lon is not None:
        # Prepare center navpoint
        center = NavPoint(latitude=center_lat, longitude=center_lon, name=q or "Center")
        # Compute distances and filter
        filtered_airports = []
        for a in model.airports.values():
            ap = getattr(a, "navpoint", None)
            if not ap:
                continue
            try:
                _, d_nm = ap.haversine_distance(center)
            except Exception:
                continue
            if d_nm > float(radius_nm):
                continue
            # Apply filters (same semantics as route-search)
            if country and a.iso_country != country:
                continue
            if has_procedures is not None and bool(a.procedures) != has_procedures:
                continue
            if has_aip_data is not None and bool(a.aip_entries) != has_aip_data:
                continue
            if has_hard_runway is not None and getattr(a, "has_hard_runway", False) != has_hard_runway:
                continue
            if point_of_entry is not None and getattr(a, "point_of_entry", False) != point_of_entry:
                continue
            filtered_airports.append((a, float(d_nm)))

        # Sort by distance
        filtered_airports.sort(key=lambda x: x[1])
        
        # Get GA data if requested and service is available
        ga_data: Dict[str, GAFriendlySummary] = {}
        if include_ga:
            ga_service = get_ga_service()
            if ga_service and ga_service.enabled:
                icaos = [a.ident for a, _ in filtered_airports]
                ga_data = ga_service.get_summaries_batch(icaos)

        # Build response
        airports_resp = []
        for a, d_nm in filtered_airports:
            ga_summary = ga_data.get(a.ident)
            summary = AirportSummary.from_airport(a, ga_summary).model_dump()
            summary["distance_nm"] = round(d_nm, 2)
            airports_resp.append(summary)

        pretty = (
            f"Found {len(airports_resp)} airports within {radius_nm}nm of {q or 'center'}."
            if airports_resp else
            f"No airports within {radius_nm}nm."
        )
        result = {
            "found": True,
            "count": len(airports_resp),
            "center": {"lat": center_lat, "lon": center_lon, "label": q or "Center"},
            "airports": airports_resp[:20],
            "pretty": pretty,
            "filter_profile": {
                "location_query": q or "",
                "radius_nm": radius_nm,
                **({ "country": country } if country else {}),
                **({ "has_procedures": True } if has_procedures else {}),
                **({ "has_aip_data": True } if has_aip_data else {}),
                **({ "has_hard_runway": True } if has_hard_runway else {}),
                **({ "point_of_entry": True } if point_of_entry else {}),
            },
            "visualization": {
                "type": "point_with_markers",
                "point": {"label": q or "Center", "lat": center_lat, "lon": center_lon},
                "markers": airports_resp
            }
        }
    else:
        if not q:
            raise HTTPException(status_code=400, detail="q (query) is required when center_lat/center_lon are not provided")
        # Build a lightweight tool context with the existing in-memory model
        ctx = ToolContext(model=model)
        result = find_airports_near_location(
            ctx,
            location_query=q,
            max_distance_nm=radius_nm,
            filters=filters or None
        )

    # Pass through relevant fields for client
    return {
        "count": result.get("count", 0),
        "center": result.get("center"),
        "airports": result.get("airports") or [],
        "pretty": result.get("pretty"),
        "filter_profile": result.get("filter_profile"),
        "visualization": result.get("visualization"),
        "found": result.get("found", False)
    }

@router.get("/aip-filter-presets")
async def get_aip_filter_presets(request: Request):
    """Get predefined AIP filter presets for common use cases."""
    presets = [
        {
            "id": "hotels",
            "name": "Hotels Available",
            "description": "Airports with hotel information",
            "field": "Hotels",
            "operator": "not_empty",
            "value": None,
            "icon": "🏨"
        },
        {
            "id": "restaurants", 
            "name": "Restaurants Available",
            "description": "Airports with restaurant information",
            "field": "Restaurants",
            "operator": "not_empty",
            "value": None,
            "icon": "🍽️"
        },
        {
            "id": "avgas",
            "name": "AVGAS Available",
            "description": "Airports with AVGAS fuel",
            "field": "Fuel and oil types",
            "operator": "contains",
            "value": "avgas",
            "icon": "⛽"
        },
        {
            "id": "jet_a",
            "name": "Jet A Available",
            "description": "Airports with Jet A fuel",
            "field": "Fuel and oil types",
            "operator": "contains", 
            "value": "jet a",
            "icon": "✈️"
        },
        {
            "id": "customs",
            "name": "Customs Available",
            "description": "Airports with customs facilities",
            "field": "Customs and immigration",
            "operator": "not_empty",
            "value": None,
            "icon": "🛂"
        },
        {
            "id": "deicing",
            "name": "De-icing Available",
            "description": "Airports with de-icing facilities",
            "field": "De-icing facilities",
            "operator": "not_empty",
            "value": None,
            "icon": "❄️"
        },
        {
            "id": "hangar",
            "name": "Hangar Space",
            "description": "Airports with hangar space for visiting aircraft",
            "field": "Hangar space for visiting aircraft",
            "operator": "not_empty",
            "value": None,
            "icon": "🏭"
        },
        {
            "id": "medical",
            "name": "Medical Facilities",
            "description": "Airports with medical facilities",
            "field": "Medical facilities",
            "operator": "not_empty",
            "value": None,
            "icon": "🏥"
        }
    ]
    
    return presets

@router.get("/{icao}", response_model=AirportDetail)
async def get_airport_detail(
    request: Request,
    icao: str = Path(..., description="ICAO airport code", max_length=4, min_length=4)
):
    """Get detailed information about a specific airport."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    airport = model.get_airport(icao.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found")
    
    return AirportDetail.from_airport(airport)

@router.get("/{icao}/aip-entries")
async def get_airport_aip_entries(
    request: Request,
    icao: str = Path(..., description="ICAO airport code", max_length=4, min_length=4),
    section: Optional[str] = Query(None, description="Filter by AIP section", max_length=100),
    std_field: Optional[str] = Query(None, description="Filter by standardized field name", max_length=100)
):
    """Get AIP entries for a specific airport."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    airport = model.get_airport(icao.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found")
    
    entries = airport.aip_entries
    
    # Apply filters
    if section:
        entries = [e for e in entries if e.section == section]
    
    if std_field:
        entries = [e for e in entries if e.std_field == std_field]
    
    # Get parsed notification summary if available
    from notification_service import get_notification_service
    notification_service = get_notification_service()
    parsed_notification = notification_service.get_notification_summary(icao.upper())
    
    # Convert entries to dicts, injecting parsed notifications for field 302
    result = []
    for e in entries:
        entry_dict = e.to_dict()
        
        # If this is customs/immigration and we have a parsed summary
        if e.std_field_id == 302 and parsed_notification and parsed_notification.get("summary"):
            # Clean up summary - remove empty lines
            summary = parsed_notification["summary"]
            cleaned_lines = []
            for line in summary.split("\n"):
                line = line.strip()
                # Skip empty lines or lines that are just "Hours:" with nothing after
                if not line:
                    continue
                # Skip lines with empty hours or contact info
                if line in ("Hours:", "📞", "📧", "| Hours:", "Schengen |", "Non-Schengen only |"):
                    continue
                # Skip lines ending with "| Hours:" or "Hours:" (empty hours)
                if line.endswith("| Hours:") or line.endswith("Hours:"):
                    continue
                # Skip lines that are just "something | Hours:" pattern
                if "| Hours:" in line and line.split("| Hours:")[-1].strip() == "":
                    continue
                if line.endswith(" |") and "|" not in line[:-2]:
                    continue
                cleaned_lines.append(line)
            
            # Keep raw text in value, add parsed summary as separate field
            entry_dict["parsed_summary"] = "\n".join(cleaned_lines)
            entry_dict["parsed_notification"] = True
            entry_dict["notification_confidence"] = parsed_notification.get("confidence")
        
        result.append(entry_dict)
    
    return result

@router.get("/{icao}/procedures")
async def get_airport_procedures(
    request: Request,
    icao: str = Path(..., description="ICAO airport code", max_length=4, min_length=4),
    procedure_type: Optional[str] = Query(None, description="Filter by procedure type", max_length=50),
    runway: Optional[str] = Query(None, description="Filter by runway identifier", max_length=10)
):
    """Get procedures for a specific airport."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    airport = model.get_airport(icao.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found")
    
    procedures = airport.procedures
    
    # Apply filters
    if procedure_type:
        procedures = airport.get_procedures_by_type(procedure_type)
    
    if runway:
        procedures = airport.get_procedures_by_runway(runway)
    
    return [p.to_dict() for p in procedures]

@router.get("/{icao}/runways")
async def get_airport_runways(
    request: Request,
    icao: str = Path(..., description="ICAO airport code", max_length=4, min_length=4)
):
    """Get runways for a specific airport."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    airport = model.get_airport(icao.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found")
    
    return [r.to_dict() for r in airport.runways]

@router.get("/{icao}/procedure-lines")
async def get_airport_procedure_lines(
    request: Request,
    icao: str = Path(..., description="ICAO airport code", max_length=4, min_length=4),
    distance_nm: float = Query(10.0, description="Distance in nautical miles for procedure lines", ge=0.1, le=100.0)
):
    """Get procedure lines for an airport."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    airport = model.get_airport(icao.upper())
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found")
    
    return airport.get_procedure_lines(distance_nm)

@router.post("/bulk/procedure-lines")
async def get_bulk_procedure_lines(
    request: Request,
    airports: List[str] = Body(..., description="List of ICAO airport codes", max_items=100),
    distance_nm: float = Body(10.0, description="Distance in nautical miles for procedure lines", ge=0.1, le=100.0)
):
    """Get procedure lines for multiple airports in a single request."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    if len(airports) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 airports allowed per request")
    
    result = {}
    
    for icao in airports:
        airport = model.get_airport(icao.upper())
        if airport:
            try:
                procedure_lines = airport.get_procedure_lines(distance_nm)
                result[icao.upper()] = procedure_lines
            except Exception as e:
                # Log error but continue with other airports
                print(f"Error getting procedure lines for {icao}: {e}")
                result[icao.upper()] = {"procedure_lines": [], "error": str(e)}
        else:
            result[icao.upper()] = {"procedure_lines": [], "error": "Airport not found"}
    
    return result

@router.get("/search/{query}")
async def search_airports(
    request: Request,
    query: str = Path(..., description="Search query", max_length=100, min_length=1),
    limit: int = Query(20, description="Maximum number of results", ge=1, le=100)
):
    """Search airports by name, ICAO code, or free-text location (geocoded via Geoapify)."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    query_upper = query.upper()
    results = []
    
    # First try direct database search
    for airport in model.airports.values():
        if (query_upper in airport.ident or 
            (airport.name and query_upper in airport.name.upper()) or 
            (airport.iata_code and query_upper in airport.iata_code) or
            (airport.municipality and query_upper in airport.municipality.upper())):
            results.append(AirportSummary.from_airport(airport))
            if len(results) >= limit:
                break
    
    # If no results found, try geocoding via Geoapify
    if not results:
        ctx = ToolContext(model=model)
        geo_result = find_airports_near_location(
            ctx,
            location_query=query,
            max_distance_nm=50.0,  # 50nm default radius
            filters=None
        )
        if geo_result.get("found") and geo_result.get("airports"):
            for apt_data in geo_result["airports"][:limit]:
                # Look up actual airport object from model
                icao = apt_data.get("ident")
                if icao:
                    airport = model.get_airport(icao)
                    if airport:
                        results.append(AirportSummary.from_airport(airport))
    
    return results 