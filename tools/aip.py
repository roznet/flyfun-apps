#!/usr/bin/env python3

"""
AIP Viewer - display airport information from the unified EuroAIP database.

Usage:
  python tools/aip.py ICAO [ICAO ...] [--summary] [--aip] [--procedures] [--all]
                           [--database [PATH]] [--log-level LEVEL] [-v|--verbose]

Arguments:
  ICAO                   One or more ICAO airport codes (e.g., LFAT EGTF).

Options:
  --summary              Show airport summary (default if no section flag is provided).
  --aip                  Show AIP entries for the airport(s).
  --procedures           Show procedures for the airport(s).
  --all                  Show summary + AIP entries + procedures.

Database selection (aligned with tools/aipexport.py):
  --database             If provided without a value, uses AIRPORTS_DB env var (if set) or airports.db.
  --database PATH        Use the specified database path.
  (If --database is omitted entirely, the tool also falls back to AIRPORTS_DB or airports.db.)

Logging:
  --log-level LEVEL      One of: NONE, CRITICAL, ERROR, WARNING, INFO, DEBUG. Default NONE (no logs).
  -v, --verbose          Backward compatibility: enables DEBUG when --log-level is not set.

Examples:
  python tools/aip.py LFAT                           # Summary only (default)
  python tools/aip.py LFAT EGTF --all                # Show all sections for both airports
  python tools/aip.py LFAT --aip --procedures        # AIP entries + procedures
  AIRPORTS_DB=/data/airports.db python tools/aip.py EGTF --all
  python tools/aip.py LFAT --database /path/db.sqlite --log-level INFO --all
"""

import sys
import argparse
import logging
import os
from typing import Any, Dict, List, Optional

from euro_aip.storage import DatabaseStorage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _database_path(path: Optional[str]) -> str:
    """
    Resolve database path consistent with tools/aipexport.py:
    - If --database omitted entirely: None (we will compute default here)
    - If --database provided with no value (const=''): use AIRPORTS_DB env or airports.db
    - If explicit path provided: use it
    """
    if path is None:
        # Not provided in args; fall back like aipexport would when saving/loading
        if os.environ.get('AIRPORTS_DB') and os.path.exists(os.environ.get('AIRPORTS_DB')):
            return os.environ.get('AIRPORTS_DB')  # type: ignore[return-value]
        if os.path.exists('airports.db'):
            return 'airports.db'
        raise ValueError("No database file found (set AIRPORTS_DB or provide --database)")
    if path == '':
        if os.environ.get('AIRPORTS_DB') and os.path.exists(os.environ.get('AIRPORTS_DB')):
            return os.environ.get('AIRPORTS_DB')  # type: ignore[return-value]
        if os.path.exists('airports.db'):
            return 'airports.db'
        raise ValueError("No database file found (set AIRPORTS_DB or create airports.db)")
    return path


def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    return getattr(obj, attr, default)

# Simple ANSI styling helpers
RESET = '\033[0m'
BOLD = '\033[1m'
CYAN = '\033[36m'
YELLOW = '\033[33m'
GREEN = '\033[32m'
DIM = '\033[2m'
ENABLE_COLOR = sys.stdout.isatty()

def fmt(text: str, *styles: str) -> str:
    if not ENABLE_COLOR or not styles:
        return text
    return "".join(styles) + text + RESET


def _format_summary(airport) -> List[str]:
    lines: List[str] = []
    lines.append(fmt(f"{airport.ident} - {airport.name or 'Unknown name'}", BOLD, CYAN))
    if _safe_get(airport, "municipality") or _safe_get(airport, "iso_country"):
        lines.append(f"{airport.municipality or 'Unknown city'}, {airport.iso_country or 'Unknown country'}")

    lat = _safe_get(airport, "latitude_deg")
    lon = _safe_get(airport, "longitude_deg")
    elev = _safe_get(airport, "elevation_ft")
    coord_line = []
    if lat is not None and lon is not None:
        coord_line.append(f"{lat:.4f}, {lon:.4f}")
    if elev is not None:
        coord_line.append(f"{int(elev)} ft")
    if coord_line:
        lines.append(" / ".join(coord_line))

    # Runways overview
    runways = _safe_get(airport, "runways", []) or []
    longest = _safe_get(airport, "longest_runway_length_ft")
    if runways:
        lines.append(f"Runways: {len(runways)}" + (f" (longest {longest} ft)" if longest else ""))
    else:
        lines.append("Runways: none")

    # Basic facilities/flags (safe access)
    flags: List[str] = []
    if _safe_get(airport, "has_hard_runway", False):
        flags.append("Hard")
    if _safe_get(airport, "has_lighted_runway", False):
        flags.append("Lighted")
    if _safe_get(airport, "point_of_entry", False):
        flags.append("Border entry")
    if flags:
        lines.append(fmt("Features: ", BOLD) + ", ".join(flags))

    # Sources and timestamps if available
    sources = _safe_get(airport, "sources", [])
    if sources:
        lines.append(fmt("Sources: ", DIM) + ", ".join(sources))
    created = _safe_get(airport, "created_at")
    updated = _safe_get(airport, "updated_at")
    if created or updated:
        lines.append(fmt(f"Timestamps: created={created or '-'} updated={updated or '-'}", DIM))

    # Brief runway listing
    if runways:
        lines.append("")
        lines.append(fmt("Runways:", BOLD, YELLOW))
        for r in runways:
            # Runway objects are dataclasses/attrs-like; access safely
            le = _safe_get(r, "le_ident") or "-"
            he = _safe_get(r, "he_ident") or "-"
            length = _safe_get(r, "length_ft")
            width = _safe_get(r, "width_ft")
            surface = _safe_get(r, "surface") or "-"
            seg = f"  {le}/{he} - {surface}"
            dims = []
            if length:
                dims.append(f"{length}x")
            if width:
                dims.append(f"{width}")
            if dims:
                seg += f" ({''.join(dims)} ft)"
            lines.append(seg)
    return lines


def _format_aip_entries(airport) -> List[str]:
    entries = _safe_get(airport, "aip_entries", []) or []
    if not entries:
        return ["No AIP entries."]
    lines: List[str] = [fmt("AIP entries:", BOLD, YELLOW)]
    for e in entries:
        # entries are likely objects; access safely
        section = _safe_get(e, "section") or "-"
        std_field = _safe_get(e, "std_field")
        value = _safe_get(e, "value")
        raw_value = _safe_get(e, "raw_value")
        src = _safe_get(e, "source") or _safe_get(e, "source_name")
        parts = [fmt(f"  [{section}]", GREEN)]
        if std_field is not None:
            parts.append(fmt(f"{std_field}:", BOLD) + f" {value if value is not None else '-'}")
        elif raw_value is not None:
            parts.append(f"{raw_value}")
        if src:
            parts.append(f"(src: {src})")
        lines.append(" ".join(parts))
    return lines


def _format_procedures(airport) -> List[str]:
    procs = _safe_get(airport, "procedures", []) or []
    if not procs:
        return ["No procedures."]
    lines: List[str] = [fmt("Procedures:", BOLD, YELLOW)]
    for p in procs:
        # Prefer dict view if available
        pdata: Dict[str, Any]
        if hasattr(p, "to_dict"):
            try:
                pdata = p.to_dict()
            except Exception:
                pdata = {k: getattr(p, k) for k in dir(p) if not k.startswith("_")}
        elif isinstance(p, dict):
            pdata = p
        else:
            pdata = {k: getattr(p, k) for k in dir(p) if not k.startswith("_")}

        ptype = pdata.get("procedure_type") or pdata.get("type") or "-"
        name = pdata.get("name") or pdata.get("identifier") or "-"
        runway = pdata.get("runway") or pdata.get("runway_id") or pdata.get("runway_ident") or "-"
        approach_type = pdata.get("approach_type") or pdata.get("category") or None
        seg = f"  {ptype}: {name}"
        tail: List[str] = []
        if runway and runway != "-":
            tail.append(f"RWY {runway}")
        if approach_type:
            tail.append(str(approach_type))
        if tail:
            seg += " (" + ", ".join(tail) + ")"
        lines.append(seg)
    return lines


def main():
    parser = argparse.ArgumentParser(description='AIP Viewer - display airport information from unified database')

    # ICAO selection
    parser.add_argument('icao', help='ICAO airport code(s)', nargs='+')

    # Database selection (match aipexport style)
    parser.add_argument(
        '--database',
        nargs='?',
        const='',
        default=None,
        help='Load model from database (omit value to use default from AIRPORTS_DB or airports.db)'
    )

    # Section display options
    parser.add_argument('--summary', help='Show airport summary', action='store_true')
    parser.add_argument('--aip', help='Show AIP entries', action='store_true')
    parser.add_argument('--procedures', help='Show procedures', action='store_true')
    parser.add_argument('--all', help='Show summary, AIP entries, and procedures', action='store_true')

    # General options
    parser.add_argument('-v', '--verbose', help='Verbose output (deprecated, use --log-level)', action='store_true')
    parser.add_argument(
        '--log-level',
        choices=['NONE', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'],
        default='NONE',
        help='Set logging level (NONE disables logs)'
    )

    args = parser.parse_args()

    # Configure logging level
    if args.log_level == 'NONE':
        logging.disable(logging.CRITICAL)
    else:
        level = getattr(logging, args.log_level, logging.WARNING)
        logging.getLogger().setLevel(level)
    if args.verbose and args.log_level == 'NONE':
        # Backward compat: -v implies DEBUG unless explicit log-level provided
        logging.disable(logging.NOTSET)
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        db_path = _database_path(args.database)
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)

    # Load model
    storage = DatabaseStorage(db_path)
    try:
        model = storage.load_model()
    except Exception as e:
        logger.error(f"Failed to load model from {db_path}: {e}")
        sys.exit(1)

    # Determine sections to show
    show_summary = args.summary or args.all or (not args.summary and not args.aip and not args.procedures and not args.all)
    show_aip = args.aip or args.all
    show_procs = args.procedures or args.all

    all_output: List[str] = []
    icao_list = [s.strip().upper() for s in (args.icao or [])]
    first = True
    for icao in icao_list:
        airport = model.airports.where(ident=icao).first()
        if not airport:
            print(f"{icao}: not found.", file=sys.stderr)
            continue
        output_lines: List[str] = []
        if show_summary:
            output_lines.extend(_format_summary(airport))
        if show_aip:
            if output_lines:
                output_lines.append("")
            output_lines.extend(_format_aip_entries(airport))
        if show_procs:
            if output_lines:
                output_lines.append("")
            output_lines.extend(_format_procedures(airport))
        if not first:
            all_output.append("")
            all_output.append("-----")
            all_output.append("")
        all_output.extend(output_lines)
        first = False

    print("\n".join(all_output))


if __name__ == '__main__':
    main()