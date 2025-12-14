#!/usr/bin/env python3

from fastapi import APIRouter, Query, HTTPException, Request, Path
from typing import List, Optional, Dict, Any
import logging

from euro_aip.models.euro_aip_model import EuroAipModel
from .models import ProcedureSummary

logger = logging.getLogger(__name__)

router = APIRouter()

# Global model reference
model: Optional[EuroAipModel] = None

def set_model(m: EuroAipModel):
    """Set the global model reference."""
    global model
    model = m

# API models are now imported from ../models

@router.get("/", response_model=List[ProcedureSummary])
async def get_procedures(
    request: Request,
    procedure_type: Optional[str] = Query(None, description="Filter by procedure type", max_length=50),
    approach_type: Optional[str] = Query(None, description="Filter by approach type", max_length=50),
    runway: Optional[str] = Query(None, description="Filter by runway identifier", max_length=10),
    authority: Optional[str] = Query(None, description="Filter by authority", max_length=100),
    source: Optional[str] = Query(None, description="Filter by source", max_length=100),
    airport: Optional[str] = Query(None, description="Filter by airport ICAO", max_length=4, min_length=4),
    limit: int = Query(100, description="Maximum number of procedures to return", ge=1, le=1000),
    offset: int = Query(0, description="Number of procedures to skip", ge=0, le=10000)
):
    """Get a list of procedures with optional filtering."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Start with all procedures using modern query API
    proc_collection = model.procedures

    # Apply filters using chainable methods
    if procedure_type:
        # Filter by procedure type (approach, departure, arrival)
        proc_type_lower = procedure_type.lower()
        if proc_type_lower == "approach":
            proc_collection = proc_collection.approaches()
        elif proc_type_lower == "departure":
            proc_collection = proc_collection.departures()
        elif proc_type_lower == "arrival":
            proc_collection = proc_collection.arrivals()
        else:
            # Custom procedure type filter
            proc_collection = proc_collection.filter(
                lambda p: p.procedure_type.lower() == proc_type_lower
            )

    if approach_type:
        proc_collection = proc_collection.by_type(approach_type)

    if runway:
        proc_collection = proc_collection.by_runway(runway)

    if authority:
        proc_collection = proc_collection.by_authority(authority)

    if source:
        proc_collection = proc_collection.by_source(source)

    if airport:
        # Filter procedures for a specific airport
        proc_collection = proc_collection.filter(
            lambda p: p.airport_ident == airport.upper()
        )

    # Apply pagination and convert to response format
    procedures = proc_collection.skip(offset).take(limit).all()

    # Find airport for each procedure to build response
    # Build a quick airport lookup map
    airport_map = {a.ident: a for a in model.airports}

    return [
        ProcedureSummary.from_procedure(proc, airport_map.get(proc.airport_ident))
        for proc in procedures
    ]

@router.get("/approaches")
async def get_approaches(
    request: Request,
    approach_type: Optional[str] = Query(None, description="Filter by approach type", max_length=50),
    runway: Optional[str] = Query(None, description="Filter by runway identifier", max_length=10),
    airport: Optional[str] = Query(None, description="Filter by airport ICAO", max_length=4, min_length=4),
    limit: int = Query(100, description="Maximum number of approaches to return", ge=1, le=1000)
):
    """Get all approach procedures with optional filtering."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Use modern query API - start with all approaches
    proc_collection = model.procedures.approaches()

    # Apply filters
    if approach_type:
        proc_collection = proc_collection.by_type(approach_type)

    if runway:
        proc_collection = proc_collection.by_runway(runway)

    if airport:
        proc_collection = proc_collection.filter(
            lambda p: p.airport_ident == airport.upper()
        )

    # Get results with limit
    procedures = proc_collection.take(limit).all()

    # Build airport lookup map
    airport_map = {a.ident: a for a in model.airports}

    # Convert to response format
    return [
        {
            "name": proc.name,
            "approach_type": proc.approach_type,
            "runway_ident": proc.runway_ident,
            "authority": proc.authority,
            "source": proc.source,
            "airport_ident": proc.airport_ident,
            "airport_name": airport_map.get(proc.airport_ident).name if airport_map.get(proc.airport_ident) else None,
            "precision": proc.get_approach_precision()
        }
        for proc in procedures
    ]

@router.get("/departures")
async def get_departures(
    request: Request,
    runway: Optional[str] = Query(None, description="Filter by runway identifier", max_length=10),
    airport: Optional[str] = Query(None, description="Filter by airport ICAO", max_length=4, min_length=4),
    limit: int = Query(100, description="Maximum number of departures to return", ge=1, le=1000)
):
    """Get all departure procedures with optional filtering."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Use modern query API - start with all departures
    proc_collection = model.procedures.departures()

    # Apply filters
    if runway:
        proc_collection = proc_collection.by_runway(runway)

    if airport:
        proc_collection = proc_collection.filter(
            lambda p: p.airport_ident == airport.upper()
        )

    # Get results with limit
    procedures = proc_collection.take(limit).all()

    # Build airport lookup map
    airport_map = {a.ident: a for a in model.airports}

    # Convert to response format
    return [
        {
            "name": proc.name,
            "runway_ident": proc.runway_ident,
            "authority": proc.authority,
            "source": proc.source,
            "airport_ident": proc.airport_ident,
            "airport_name": airport_map.get(proc.airport_ident).name if airport_map.get(proc.airport_ident) else None
        }
        for proc in procedures
    ]

@router.get("/arrivals")
async def get_arrivals(
    request: Request,
    runway: Optional[str] = Query(None, description="Filter by runway identifier", max_length=10),
    airport: Optional[str] = Query(None, description="Filter by airport ICAO", max_length=4, min_length=4),
    limit: int = Query(100, description="Maximum number of arrivals to return", ge=1, le=1000)
):
    """Get all arrival procedures with optional filtering."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Use modern query API - start with all arrivals
    proc_collection = model.procedures.arrivals()

    # Apply filters
    if runway:
        proc_collection = proc_collection.by_runway(runway)

    if airport:
        proc_collection = proc_collection.filter(
            lambda p: p.airport_ident == airport.upper()
        )

    # Get results with limit
    procedures = proc_collection.take(limit).all()

    # Build airport lookup map
    airport_map = {a.ident: a for a in model.airports}

    # Convert to response format
    return [
        {
            "name": proc.name,
            "runway_ident": proc.runway_ident,
            "authority": proc.authority,
            "source": proc.source,
            "airport_ident": proc.airport_ident,
            "airport_name": airport_map.get(proc.airport_ident).name if airport_map.get(proc.airport_ident) else None
        }
        for proc in procedures
    ]

@router.get("/by-runway/{airport_icao}")
async def get_procedures_by_runway(
    request: Request,
    airport_icao: str = Path(..., description="ICAO airport code", max_length=4, min_length=4)
):
    """Get procedures organized by runway for a specific airport."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    airport = model.airports.where(ident=airport_icao.upper()).first()
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {airport_icao} not found")
    
    return airport.get_runway_procedures_summary()

@router.get("/most-precise/{airport_icao}")
async def get_most_precise_approaches(
    request: Request,
    airport_icao: str = Path(..., description="ICAO airport code", max_length=4, min_length=4)
):
    """Get the most precise approach for each runway at an airport."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    airport = model.airports.where(ident=airport_icao.upper()).first()
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {airport_icao} not found")
    
    return airport.get_most_precise_approaches()

@router.get("/statistics")
async def get_procedure_statistics(request: Request):
    """Get statistics about procedures across all airports."""
    if not model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Use modern query API for efficiency
    total_procedures = model.procedures.count()
    airports_with_procedures = model.airports.with_procedures().count()
    total_airports = model.airports.count()

    procedure_types = {}
    approach_types = {}

    # Iterate through all procedures
    for procedure in model.procedures:
        # Count procedure types
        proc_type = procedure.procedure_type
        procedure_types[proc_type] = procedure_types.get(proc_type, 0) + 1

        # Count approach types
        if procedure.approach_type:
            app_type = procedure.approach_type
            approach_types[app_type] = approach_types.get(app_type, 0) + 1

    return {
        "total_procedures": total_procedures,
        "airports_with_procedures": airports_with_procedures,
        "procedure_types": procedure_types,
        "approach_types": approach_types,
        "average_procedures_per_airport": total_procedures / total_airports if total_airports > 0 else 0
    } 