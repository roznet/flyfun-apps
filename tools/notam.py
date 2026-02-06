#!/usr/bin/env python3

"""
NOTAM Extractor - Extract NOTAMs from ForeFlight PDF briefings to CSV or test fixture text.

Parses ForeFlight briefing PDFs and outputs NOTAM data in CSV format
for analysis and review. Supports optional route distance calculation.

Usage:
    # Basic extraction to CSV
    python tools/notam.py briefing.pdf

    # Output to specific file
    python tools/notam.py briefing.pdf -o notams.csv

    # With route distance calculation (uses AIRPORTS_DB env var or airports.db)
    python tools/notam.py briefing.pdf --route LFPT LSGS

    # Extract raw NOTAM text blocks for Swift test fixtures
    python tools/notam.py briefing.pdf --extract-text -o fixtures.txt

    # Limit number of extracted NOTAMs
    python tools/notam.py briefing.pdf --extract-text --limit 5

    # Verbose output
    python tools/notam.py briefing.pdf -v

Examples:
    # Extract NOTAMs from a briefing
    python tools/notam.py ~/Documents/ForeFlight/Briefing_LFPT_LSGS.pdf

    # Extract with route distance (auto-detects airports.db or AIRPORTS_DB)
    python tools/notam.py briefing.pdf --route LFPT LSGS

    # Extract raw text for test fixtures
    python tools/notam.py briefing.pdf --extract-text --limit 10 -o test_fixtures.txt
"""

import argparse
import csv
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional, List, Tuple

from euro_aip.briefing.sources.foreflight import ForeFlightSource
from euro_aip.briefing.models.notam import Notam
from euro_aip.briefing.parsers.notam_parser import NotamParser
from euro_aip.briefing.categorization.q_code import parse_q_code
from euro_aip.models.navpoint import NavPoint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def resolve_database_path(path: Optional[str]) -> Optional[str]:
    """
    Resolve database path, falling back to AIRPORTS_DB env var or airports.db.

    Args:
        path: Explicit path (if provided) or None

    Returns:
        Resolved database path or None if not found
    """
    if path:
        return path

    # Try AIRPORTS_DB environment variable
    env_db = os.environ.get('AIRPORTS_DB')
    if env_db and os.path.exists(env_db):
        return env_db

    # Try local airports.db
    if os.path.exists('airports.db'):
        return 'airports.db'

    return None


def get_airport_coordinates(icao: str, database_path: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """
    Look up airport coordinates from database.

    Args:
        icao: ICAO airport code
        database_path: Path to airports database

    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    database_path = resolve_database_path(database_path)
    if not database_path:
        return None

    try:
        from euro_aip.storage.database_storage import DatabaseStorage
        storage = DatabaseStorage(database_path)
        model = storage.load_model()
        airport = model.airports.get(icao)
        if airport and airport.latitude_deg and airport.longitude_deg:
            return (airport.latitude_deg, airport.longitude_deg)
    except Exception as e:
        logger.warning(f"Could not look up coordinates for {icao}: {e}")

    return None


def calculate_route_distance(
    notam: Notam,
    route_points: List[NavPoint]
) -> Optional[float]:
    """
    Calculate minimum distance from NOTAM to route.

    Args:
        notam: NOTAM with coordinates
        route_points: List of route NavPoints

    Returns:
        Minimum distance in NM to route, or None if cannot calculate
    """
    if not notam.coordinates or len(notam.coordinates) != 2:
        return None

    if len(route_points) < 2:
        return None

    notam_point = NavPoint(
        latitude=notam.coordinates[0],
        longitude=notam.coordinates[1],
        name=notam.id
    )

    min_distance = float('inf')

    # Calculate distance to each route segment
    for i in range(len(route_points) - 1):
        segment_start = route_points[i]
        segment_end = route_points[i + 1]
        distance = notam_point.distance_to_segment(segment_start, segment_end)
        min_distance = min(min_distance, distance)

    return min_distance if min_distance != float('inf') else None


def format_datetime(dt) -> str:
    """Format datetime for CSV output."""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def escape_csv_text(text: str) -> str:
    """
    Escape text for CSV output.

    Handles newlines, quotes, and other special characters.
    """
    if not text:
        return ""
    # Replace newlines with spaces (preserves readability)
    text = text.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
    # Collapse multiple spaces
    while '  ' in text:
        text = text.replace('  ', ' ')
    return text.strip()


def notam_to_row(notam: Notam, route_distance: Optional[float] = None) -> dict:
    """
    Convert NOTAM to CSV row dictionary.

    Args:
        notam: NOTAM object
        route_distance: Optional distance to route in NM

    Returns:
        Dictionary with CSV fields
    """
    # Parse Q-code for subject/condition
    subject_code = ""
    subject_meaning = ""
    condition_code = ""
    condition_meaning = ""

    if notam.q_code:
        q_info = parse_q_code(notam.q_code)
        subject_code = q_info.subject_code
        subject_meaning = q_info.subject_meaning
        condition_code = q_info.condition_code
        condition_meaning = q_info.condition_meaning

    # Format coordinates
    latitude = ""
    longitude = ""
    if notam.coordinates and len(notam.coordinates) == 2:
        latitude = f"{notam.coordinates[0]:.4f}"
        longitude = f"{notam.coordinates[1]:.4f}"

    # Format altitude
    lower_limit = str(notam.lower_limit) if notam.lower_limit is not None else ""
    upper_limit = str(notam.upper_limit) if notam.upper_limit is not None else ""

    # Format route distance
    distance_nm = ""
    if route_distance is not None:
        distance_nm = f"{route_distance:.1f}"

    return {
        'id': notam.id,
        'location': notam.location,
        'fir': notam.fir or "",
        'effective_from': format_datetime(notam.effective_from),
        'effective_to': format_datetime(notam.effective_to),
        'is_permanent': 'Y' if notam.is_permanent else 'N',
        'q_code': notam.q_code or "",
        'subject_code': subject_code,
        'subject': subject_meaning,
        'condition_code': condition_code,
        'condition': condition_meaning,
        'traffic': notam.traffic_type or "",
        'scope': notam.scope or "",
        'lower_limit_ft': lower_limit,
        'upper_limit_ft': upper_limit,
        'radius_nm': str(notam.radius_nm) if notam.radius_nm else "",
        'latitude': latitude,
        'longitude': longitude,
        'distance_nm': distance_nm,
        'raw_text': escape_csv_text(notam.raw_text),
    }


def extract_notams(
    pdf_path: Path,
    output_path: Optional[Path] = None,
    route_airports: Optional[List[str]] = None,
    database_path: Optional[str] = None,
) -> List[dict]:
    """
    Extract NOTAMs from PDF and write to CSV.

    Args:
        pdf_path: Path to ForeFlight briefing PDF
        output_path: Output CSV path (defaults to pdf_path with .csv extension)
        route_airports: Optional list of route airport ICAO codes for distance calculation
        database_path: Optional path to airports database

    Returns:
        List of NOTAM row dictionaries
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Parse briefing
    logger.info(f"Parsing briefing: {pdf_path}")
    source = ForeFlightSource()
    briefing = source.parse(pdf_path)

    logger.info(f"Found {len(briefing.notams)} NOTAMs")

    # Build route NavPoints if route specified
    route_points: List[NavPoint] = []
    if route_airports and len(route_airports) >= 2:
        logger.info(f"Building route: {' -> '.join(route_airports)}")
        for icao in route_airports:
            coords = get_airport_coordinates(icao, database_path)
            if coords:
                route_points.append(NavPoint(
                    latitude=coords[0],
                    longitude=coords[1],
                    name=icao
                ))
                logger.debug(f"  {icao}: {coords}")
            else:
                logger.warning(f"  {icao}: coordinates not found")

        if len(route_points) < 2:
            logger.warning("Insufficient route points for distance calculation")
            route_points = []

    # Convert NOTAMs to rows
    rows = []
    for notam in briefing.notams:
        route_distance = None
        if route_points:
            route_distance = calculate_route_distance(notam, route_points)
        rows.append(notam_to_row(notam, route_distance))

    # Determine output path
    if output_path is None:
        output_path = pdf_path.with_suffix('.csv')

    # Write CSV
    if rows:
        fieldnames = list(rows[0].keys())
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Wrote {len(rows)} NOTAMs to {output_path}")
    else:
        logger.warning("No NOTAMs found in briefing")

    return rows


# MARK: - Text Extraction for Test Fixtures

# Map Q-code subject codes to human-readable tag prefixes
SUBJECT_TAG_MAP = {
    'MR': 'movement_area',
    'MT': 'movement_area',
    'MX': 'movement_area',
    'IL': 'ils',
    'IG': 'ils',
    'IM': 'ils',
    'IS': 'ils',
    'IT': 'ils',
    'IU': 'ils',
    'ID': 'ils',
    'IW': 'ils',
    'IX': 'ils',
    'IY': 'ils',
    'RA': 'airspace',
    'RR': 'airspace',
    'RT': 'airspace',
    'AR': 'airspace',
    'OB': 'obstacle',
    'OL': 'obstacle',
    'NV': 'navaid',
    'ND': 'navaid',
    'NB': 'navaid',
    'NT': 'navaid',
    'NL': 'navaid',
    'FH': 'helicopter',
    'FP': 'helicopter',
    'FA': 'facility',
    'FF': 'facility',
    'FS': 'facility',
    'PI': 'procedure',
    'PA': 'procedure',
    'PD': 'procedure',
    'PU': 'procedure',
    'PH': 'procedure',
    'PB': 'procedure',
    'PE': 'procedure',
    'PK': 'procedure',
    'PM': 'procedure',
    'PN': 'procedure',
    'LA': 'lighting',
    'LB': 'lighting',
    'LC': 'lighting',
    'LE': 'lighting',
    'LF': 'lighting',
    'LI': 'lighting',
    'LK': 'lighting',
}

# Map Q-code condition codes to tags
CONDITION_TAG_MAP = {
    'LC': 'closure',
    'LI': 'closure',
    'LV': 'closure',
    'AS': 'unserviceable',
    'AU': 'unavailable',
    'CN': 'canceled',
    'CH': 'changed',
}


def generate_test_id(notam: Notam, index: int) -> str:
    """Generate a readable test ID from Q-code subject and location."""
    q_code = notam.q_code or ""
    location = (notam.location or "unknown").lower()

    # Get subject prefix from Q-code (first 2 chars = subject)
    subject_prefix = "notam"
    if len(q_code) >= 2:
        subject_code = q_code[:2]
        tag = SUBJECT_TAG_MAP.get(subject_code, subject_code.lower())
        subject_prefix = tag

    # Get condition suffix
    condition_suffix = ""
    if len(q_code) >= 4:
        condition_code = q_code[2:4]
        condition_tag = CONDITION_TAG_MAP.get(condition_code)
        if condition_tag:
            condition_suffix = f"_{condition_tag}"

    return f"{subject_prefix}{condition_suffix}_{location}_{index:02d}"


def generate_tags(notam: Notam) -> List[str]:
    """Generate tags from Q-code for test metadata."""
    tags = []
    q_code = notam.q_code or ""

    if len(q_code) >= 2:
        subject_code = q_code[:2]
        subject_tag = SUBJECT_TAG_MAP.get(subject_code)
        if subject_tag:
            tags.append(subject_tag)

    if len(q_code) >= 4:
        condition_code = q_code[2:4]
        condition_tag = CONDITION_TAG_MAP.get(condition_code)
        if condition_tag:
            tags.append(condition_tag)

    if notam.is_permanent:
        tags.append("permanent")

    if notam.scope == 'E':
        tags.append("enroute")
    elif notam.scope == 'A':
        tags.append("aerodrome")

    return tags


def extract_text_blocks(
    pdf_path: Path,
    output_path: Optional[Path] = None,
    limit: Optional[int] = None,
) -> int:
    """
    Extract raw NOTAM text blocks from PDF for use as Swift test fixtures.

    Output format uses ===NOTAM=== separator with ### metadata headers.

    Args:
        pdf_path: Path to ForeFlight briefing PDF
        output_path: Output text file path (defaults to pdf_path with .txt extension)
        limit: Maximum number of NOTAMs to extract

    Returns:
        Number of NOTAMs extracted
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Extract raw text from PDF
    logger.info(f"Extracting text from: {pdf_path}")
    source = ForeFlightSource()
    raw_text = source._extract_text(pdf_path)

    # Split into individual NOTAM text chunks
    chunks = source._split_notam_section(raw_text)
    logger.info(f"Found {len(chunks)} NOTAM text blocks")

    if limit:
        chunks = chunks[:limit]

    # Determine output path
    if output_path is None:
        output_path = pdf_path.with_suffix('.txt')

    # Build fixture output
    blocks = []
    for i, chunk in enumerate(chunks):
        # Quick-parse to extract metadata
        notam = NotamParser.parse(chunk, source='foreflight')
        if not notam:
            logger.warning(f"  Skipping unparseable chunk {i}")
            continue

        q_code = notam.q_code or ""
        location = notam.location or ""
        test_id = generate_test_id(notam, i)
        tags = generate_tags(notam)

        # Build metadata header
        lines = []
        lines.append(f"### id: {test_id}")
        if q_code:
            lines.append(f"### expected_qcode: Q{q_code}")
        if location:
            lines.append(f"### expected_location: {location}")
        if tags:
            lines.append(f"### tags: {', '.join(tags)}")

        # Add raw text
        lines.append(chunk.strip())

        blocks.append('\n'.join(lines))

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n===NOTAM===\n'.join(blocks))
        f.write('\n')

    logger.info(f"Wrote {len(blocks)} NOTAM text blocks to {output_path}")
    return len(blocks)


def main():
    parser = argparse.ArgumentParser(
        description='Extract NOTAMs from ForeFlight briefing PDFs to CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'pdf',
        type=Path,
        help='Path to ForeFlight briefing PDF'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output CSV file (default: <pdf>.csv)'
    )

    parser.add_argument(
        '--route',
        nargs='+',
        metavar='ICAO',
        help='Route airports for distance calculation (e.g., LFPT LSGS)'
    )

    parser.add_argument(
        '-d', '--database',
        help='Path to airports database (default: AIRPORTS_DB env var or airports.db)'
    )

    parser.add_argument(
        '--extract-text',
        action='store_true',
        help='Extract raw NOTAM text blocks for test fixtures (instead of CSV)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        metavar='N',
        help='Limit number of NOTAMs extracted (used with --extract-text)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Route to extract-text mode if requested
        if args.extract_text:
            count = extract_text_blocks(
                pdf_path=args.pdf,
                output_path=args.output,
                limit=args.limit,
            )
            print(f"\nExtracted {count} NOTAM text blocks")
            return

        rows = extract_notams(
            pdf_path=args.pdf,
            output_path=args.output,
            route_airports=args.route,
            database_path=args.database,
        )

        # Print summary
        if rows:
            print(f"\nExtracted {len(rows)} NOTAMs")

            # Count by location
            locations = {}
            for row in rows:
                loc = row['location']
                locations[loc] = locations.get(loc, 0) + 1

            print("\nBy location:")
            for loc, count in sorted(locations.items(), key=lambda x: -x[1])[:10]:
                print(f"  {loc}: {count}")

            # Count by subject
            subjects = {}
            for row in rows:
                subj = row['subject'] or 'Unknown'
                subjects[subj] = subjects.get(subj, 0) + 1

            print("\nBy subject:")
            for subj, count in sorted(subjects.items(), key=lambda x: -x[1])[:10]:
                print(f"  {subj}: {count}")

    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
