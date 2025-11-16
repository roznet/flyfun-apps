#!/usr/bin/env python3

"""
Display recorded airport data changes from airports.db

Overview
- Reads the unified change-tracking tables created by euro_aip DatabaseStorage:
  - aip_entries_changes, procedures_changes, runways_changes, airports_changes
- Slices by airport(s), date/range, change type(s), fields, std_field_id, and country.
- Outputs as a formatted table (default), CSV, or JSON.
- If --since is omitted, defaults to the latest date with changes (that full day).

Database path resolution
- --database if provided
- else $AIRPORTS_DB if it exists
- else ./airports.db

Key options
- Airports: positional ICAO list (e.g., "LFAT EGMC"). If omitted, includes all.
- Dates: --since YYYY-MM-DD | today | yesterday | Nd | latest; optional --until YYYY-MM-DD (exclusive).
- Types: --aip | --procedures | --runways | --airport (default is only --aip if none specified).
- Fields: -f/--fields for AIP std_field/raw field name, or field_name for other types.
- AIP std field id: --std-field-id (comma-separated or repeatable).
- Country filter: --country-filter FR,GB (by airports.iso_country).
- Output: --format table|csv|json; --group-by airport|field|none (table); --plain-text to disable colors.
- Summary: --summary prints counts by type, top airports, and top fields (table format).

Examples
- Latest day’s AIP changes:
    python tools/aipchange.py
- Past 7 days for FR, by std_field_id 101 and 302:
    python tools/aipchange.py --aip --since 7d --country-filter FR --std-field-id 101,302
- Procedures and AIP for LFAT today, grouped by field:
    python tools/aipchange.py LFAT --aip --procedures --since today --group-by field
- Summary view for yesterday:
    python tools/aipchange.py --aip --since yesterday --summary
- Export JSON:
    python tools/aipchange.py --aip --since latest --format json --output changes.json
- Plain table (no colors):
    python tools/aipchange.py --aip --since latest --plain-text
"""

import sys
import argparse
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from collections import defaultdict
import csv
import json
from datetime import date

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CHANGE_TABLES = {
    'aip': {
        'table': 'aip_entries_changes',
        'date_col': 'changed_at',
        'select': '''
            SELECT 
                airport_icao,
                {date_expr} AS change_date,
                changed_at,
                'aip' AS change_type,
                COALESCE(std_field, field) AS field_name,
                section,
                field,
                std_field,
                std_field_id,
                source,
                old_value,
                new_value
            FROM aip_entries_changes
        '''
    },
    'procedures': {
        'table': 'procedures_changes',
        'date_col': 'changed_at',
        'select': '''
            SELECT 
                airport_icao,
                {date_expr} AS change_date,
                changed_at,
                'procedures' AS change_type,
                field_name,
                NULL AS section,
                field_name AS field,
                NULL AS std_field,
                NULL AS std_field_id,
                source,
                old_value,
                new_value
            FROM procedures_changes
        '''
    },
    'runways': {
        'table': 'runways_changes',
        'date_col': 'changed_at',
        'select': '''
            SELECT 
                rc.airport_icao,
                {date_expr} AS change_date,
                rc.changed_at,
                'runways' AS change_type,
                rc.field_name,
                NULL AS section,
                rc.field_name AS field,
                NULL AS std_field,
                NULL AS std_field_id,
                rc.source,
                rc.old_value,
                rc.new_value
            FROM runways_changes rc
        '''
    },
    'airport': {
        'table': 'airports_changes',
        'date_col': 'changed_at',
        'select': '''
            SELECT 
                airport_icao,
                {date_expr} AS change_date,
                changed_at,
                'airport' AS change_type,
                field_name,
                NULL AS section,
                field_name AS field,
                NULL AS std_field,
                NULL AS std_field_id,
                source,
                old_value,
                new_value
            FROM airports_changes
        '''
    }
}


def _resolve_db_path(path: Optional[str]) -> str:
    if path is None or path == '':
        env_path = os.environ.get('AIRPORTS_DB')
        if env_path and os.path.exists(env_path):
            return env_path
        if os.path.exists('airports.db'):
            return 'airports.db'
        raise ValueError("No database file found (set AIRPORTS_DB or provide --database)")
    return path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_relative_dates(since: Optional[str], until: Optional[str], conn: sqlite3.Connection, types: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Interpret relative date tokens:
    - today: since = today, until = tomorrow
    - yesterday: since = yesterday, until = today
    - Nd (e.g. 7d, 30d): since = now - N days, until = tomorrow
    - latest: since = latest change date in DB, until = next day
    If since is a concrete YYYY-MM-DD, leave existing logic to compute until if not provided.
    """
    if not since:
        return since, until
    token = since.strip().lower()
    today = date.today()
    if token == 'today':
        s = today.isoformat()
        u = (today + timedelta(days=1)).isoformat()
        return s, u
    if token == 'yesterday':
        y = today - timedelta(days=1)
        return y.isoformat(), today.isoformat()
    if token.endswith('d') and token[:-1].isdigit():
        days = int(token[:-1])
        start = (today - timedelta(days=days)).isoformat()
        end = (today + timedelta(days=1)).isoformat()
        return start, end
    if token == 'latest':
        latest = _get_latest_change_date(conn, types)
        if latest:
            d = datetime.fromisoformat(latest).date()
            return d.isoformat(), (d + timedelta(days=1)).isoformat()
        # fall through to original handling if none
        return None, None
    # Not a token; let caller compute default until
    return since, until


def _get_latest_change_date(conn: sqlite3.Connection, types: Sequence[str]) -> Optional[str]:
    dates: List[str] = []
    for t in types:
        meta = CHANGE_TABLES[t]
        sql = f"SELECT DATE(MAX({meta['date_col']})) AS d FROM {meta['table']}"
        row = conn.execute(sql).fetchone()
        if row and row['d']:
            dates.append(row['d'])
    if not dates:
        return None
    return max(dates)


def _build_where_clauses(
    airports: Optional[Sequence[str]],
    since: Optional[str],
    until: Optional[str],
    fields: Optional[Sequence[str]],
    type_key: str
) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    date_col = CHANGE_TABLES[type_key]['date_col']
    table = CHANGE_TABLES[type_key]['table']

    if airports:
        placeholders = ','.join(['?'] * len(airports))
        clauses.append(f"airport_icao IN ({placeholders})")
        params.extend([a.strip().upper() for a in airports])

    if since and until:
        clauses.append(f"{table}.{date_col} >= ? AND {table}.{date_col} < ?")
        # until is exclusive end; if only date provided, treat until = date + 1 day
        params.append(since)
        params.append(until)
    elif since:
        # If only since and it's a YYYY-MM-DD, show that full day
        clauses.append(f"DATE({table}.{date_col}) = DATE(?)")
        params.append(since)

    if fields:
        if type_key == 'aip':
            # match against std_field or raw field
            placeholders = ','.join(['?'] * len(fields))
            clauses.append(f"(COALESCE(std_field, field) IN ({placeholders}))")
            params.extend(fields)
        else:
            placeholders = ','.join(['?'] * len(fields))
            clauses.append(f"(field_name IN ({placeholders}))")
            params.extend(fields)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _query_changes(
    conn: sqlite3.Connection,
    types: Sequence[str],
    airports: Optional[Sequence[str]],
    since: Optional[str],
    until: Optional[str],
    fields: Optional[Sequence[str]],
    std_field_ids: Optional[Sequence[int]] = None,
    country_filter: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    all_rows: List[Dict[str, Any]] = []
    for t in types:
        meta = CHANGE_TABLES[t]
        # Normalize date expression to a DATE() string for grouping/printing
        select_sql = meta['select'].format(date_expr=f"DATE({meta['date_col']})")
        where, params = _build_where_clauses(airports, since, until, fields, t)
        extra_clauses: List[str] = []
        extra_params: List[Any] = []
        # std_field_id filter (only for AIP changes)
        if t == 'aip' and std_field_ids:
            placeholders = ','.join(['?'] * len(std_field_ids))
            extra_clauses.append(f"std_field_id IN ({placeholders})")
            extra_params.extend(std_field_ids)
        # country filter via airports table
        if country_filter:
            placeholders = ','.join(['?'] * len(country_filter))
            extra_clauses.append(
                f"airport_icao IN (SELECT icao_code FROM airports WHERE iso_country IN ({placeholders}))"
            )
            extra_params.extend([c.strip().upper() for c in country_filter])
        if extra_clauses:
            where = (where + (" AND " if where else "WHERE ") + " AND ".join(extra_clauses))
        sql = f"""
            {select_sql}
            {where}
            ORDER BY changed_at DESC
        """
        for row in conn.execute(sql, params + extra_params).fetchall():
            all_rows.append(dict(row))
    # Sort across types by changed_at desc
    all_rows.sort(key=lambda r: r['changed_at'], reverse=True)
    return all_rows


class _Ansi:
    def __init__(self, enabled: bool):
        self.enabled = enabled
    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"
    def bold(self, text: str) -> str:
        return self._wrap('1', text)
    def dim(self, text: str) -> str:
        return self._wrap('2', text)
    def cyan(self, text: str) -> str:
        return self._wrap('36', text)
    def yellow(self, text: str) -> str:
        return self._wrap('33', text)
    def green(self, text: str) -> str:
        return self._wrap('32', text)
    def red(self, text: str) -> str:
        return self._wrap('31', text)


def _format_change_line(r: Dict[str, Any], c: _Ansi) -> str:
    ts = r['changed_at']
    icao = r['airport_icao']
    typ = r['change_type']
    section = r.get('section')
    field = r.get('field_name') or r.get('field')
    label = f"{section}.{field}" if section else f"{field}"
    old_v = r.get('old_value') or ''
    new_v = r.get('new_value') or ''
    type_str = c.cyan(f"[{typ}]")
    airport_str = c.bold(icao)
    field_str = c.yellow(label)
    arrow = c.dim("->")
    return f"{ts}\t{type_str}\t{airport_str}\t{field_str}\t{old_v} {arrow} {new_v}"


def _print_table(rows: List[Dict[str, Any]], group_by: str = 'airport', plain_text: bool = False) -> None:
    if not rows:
        logger.info("No changes found.")
        return
    c = _Ansi(enabled=sys.stdout.isatty() and not plain_text)
    if group_by == 'airport':
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in rows:
            grouped[r['airport_icao']].append(r)
        for icao in sorted(grouped.keys()):
            header = f"=== {icao} ==="
            print(c.bold(header))
            for r in grouped[icao]:
                print(_format_change_line(r, c))
    elif group_by == 'field':
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in rows:
            key = r.get('field_name') or r.get('field')
            grouped[str(key)].append(r)
        for field in sorted(grouped.keys(), key=lambda x: x or ''):
            header = f"=== {field} ==="
            print(c.bold(header))
            for r in grouped[field]:
                print(_format_change_line(r, c))
    else:
        # flat
        for r in rows:
            print(_format_change_line(r, c))


def _print_summary(rows: List[Dict[str, Any]]) -> None:
    total = len(rows)
    by_type: Dict[str, int] = defaultdict(int)
    by_airport: Dict[str, int] = defaultdict(int)
    by_field: Dict[str, int] = defaultdict(int)
    for r in rows:
        by_type[r['change_type']] += 1
        by_airport[r['airport_icao']] += 1
        field = r.get('field_name') or r.get('field') or ''
        by_field[str(field)] += 1
    print(f"Total changes: {total}")
    print("\nBy type:")
    for t, n in sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {t}: {n}")
    print("\nTop airports:")
    for icao, n in sorted(by_airport.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
        print(f"  {icao}: {n}")
    print("\nTop fields:")
    for f, n in sorted(by_field.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
        print(f"  {f}: {n}")


def _write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'airport_icao', 'change_type', 'changed_at', 'change_date',
            'section', 'field', 'std_field', 'std_field_id', 'source',
            'old_value', 'new_value'
        ])
        for r in rows:
            writer.writerow([
                r.get('airport_icao'),
                r.get('change_type'),
                r.get('changed_at'),
                r.get('change_date'),
                r.get('section'),
                r.get('field'),
                r.get('std_field'),
                r.get('std_field_id'),
                r.get('source'),
                r.get('old_value'),
                r.get('new_value'),
            ])
    logger.info(f"Wrote CSV to {path} ({len(rows)} rows)")


def _write_json(rows: List[Dict[str, Any]], path: str) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    logger.info(f"Wrote JSON to {path} ({len(rows)} rows)")


def main():
    parser = argparse.ArgumentParser(description='Display recorded changes from airports.db')
    parser.add_argument('airports', help='ICAO airport codes (space-separated). If omitted, shows all airports with changes.', nargs='*')
    parser.add_argument(
        '--database',
        nargs='?',
        const='',
        default=None,
        help='SQLite database file (omit value to use AIRPORTS_DB or airports.db)'
    )
    parser.add_argument('--since', help='Show changes since date (YYYY-MM-DD). If omitted, defaults to latest change date (that day).')
    parser.add_argument('--until', help='End date exclusive (YYYY-MM-DD). Used only with --since; default is since + 1 day.')
    parser.add_argument('--aip', help='Include AIP changes', action='store_true')
    parser.add_argument('--procedures', help='Include Procedures changes', action='store_true')
    parser.add_argument('--runways', help='Include Runways changes', action='store_true')
    parser.add_argument('--airport', dest='airport_fields', help='Include Airport field changes', action='store_true')
    parser.add_argument('-f', '--fields', help='Filter by field name(s) (std_field for AIP; field_name for others). Comma-separated or repeatable.', nargs='*')
    parser.add_argument('--group-by', choices=['airport', 'field', 'none'], default='airport', help='Grouping for table output')
    parser.add_argument('--format', choices=['table', 'csv', 'json'], default='table', help='Output format')
    parser.add_argument('--output', help='Output file for CSV/JSON formats')
    parser.add_argument('--std-field-id', help='Filter AIP changes by std_field_id (comma-separated or repeatable)', nargs='*')
    parser.add_argument('--country-filter', help='Filter by ISO country code(s) (e.g. FR, GB). Comma-separated or repeatable.', nargs='*')
    parser.add_argument('--summary', help='Show summary counts instead of detailed rows (table format only)', action='store_true')
    parser.add_argument('--plain-text', help='Disable ANSI colors/styles in table output', action='store_true')
    parser.add_argument('-v', '--verbose', help='Verbose output', action='store_true')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve DB
    db_path = _resolve_db_path(args.database)
    conn = _connect(db_path)

    # Determine which types to include
    selected_types: List[str] = []
    if args.aip or args.procedures or args.runways or args.airport_fields:
        if args.aip:
            selected_types.append('aip')
        if args.procedures:
            selected_types.append('procedures')
        if args.runways:
            selected_types.append('runways')
        if args.airport_fields:
            selected_types.append('airport')
    else:
        # Default: only AIP
        selected_types = ['aip']

    # Normalize fields option
    fields: Optional[List[str]] = None
    if args.fields:
        combined: List[str] = []
        for grp in args.fields:
            combined.extend([f.strip() for f in grp.split(',') if f.strip()])
        fields = combined or None
    std_field_ids: Optional[List[int]] = None
    if args.std_field_id:
        combined_ids: List[int] = []
        for grp in args.std_field_id:
            for part in grp.split(','):
                part = part.strip()
                if part.isdigit():
                    combined_ids.append(int(part))
        std_field_ids = combined_ids or None
    country_filter: Optional[List[str]] = None
    if args.country_filter:
        combined_countries: List[str] = []
        for grp in args.country_filter:
            combined_countries.extend([c.strip().upper() for c in grp.split(',') if c.strip()])
        country_filter = combined_countries or None

    # Date handling: default to latest change date across selected types
    since = args.since
    until = args.until
    since, until = _parse_relative_dates(since, until, conn, selected_types)
    if not since:
        latest_date = _get_latest_change_date(conn, selected_types)
        if latest_date:
            since = latest_date
            # until is next day exclusive
            try:
                d = datetime.fromisoformat(latest_date)
            except ValueError:
                d = datetime.strptime(latest_date, '%Y-%m-%d')
            until = (d + timedelta(days=1)).date().isoformat()
            logger.info(f"No --since provided, defaulting to latest change day: {since}")
        else:
            logger.info("No changes found in database.")
            print("No changes found.")
            return
    else:
        if not until:
            # if user provides a full date, default to that single day
            try:
                d = datetime.fromisoformat(since)
            except ValueError:
                d = datetime.strptime(since, '%Y-%m-%d')
            until = (d + timedelta(days=1)).date().isoformat()

    # Query
    rows = _query_changes(
        conn=conn,
        types=selected_types,
        airports=args.airports or None,
        since=since,
        until=until,
        fields=fields,
        std_field_ids=std_field_ids,
        country_filter=country_filter,
    )

    # Output
    if args.format == 'table':
        if args.summary:
            _print_summary(rows)
        else:
            group_by = {'airport': 'airport', 'field': 'field'}.get(args.group_by, 'none')
            _print_table(rows, group_by=group_by, plain_text=args.plain_text)
    elif args.format == 'csv':
        if not args.output:
            logger.error("Please specify --output for CSV format")
            sys.exit(1)
        _write_csv(rows, args.output)
    else:
        if not args.output:
            logger.error("Please specify --output for JSON format")
            sys.exit(1)
        _write_json(rows, args.output)

    conn.close()

if __name__ == '__main__':
    main()

