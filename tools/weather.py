#!/usr/bin/env python3

"""
Weather Analysis Tool - METAR/TAF analysis using euro_aip library.

Supports three modes:
1. Historical (single ICAO + date): Fetches from ogimet.com, caches in SQLite
2. Live (single or multiple ICAOs, no date): Fetches from aviationweather.gov
3. Route (--route flag): Finds airports along a route corridor, fetches live weather

Usage:
    # Historical: show all reports for a day (chronological)
    python tools/weather.py EGLL 20250115

    # Historical: show reports up to a specific time with flight categories
    python tools/weather.py EGLL 20250115 1430 -c

    # Historical: with runway wind components
    python tools/weather.py EGLL 20250115 -c -r 27,09

    # Historical: with crosswind/gust limits (highlights red/green)
    python tools/weather.py EGLL 20250115 -c -r 27,09 -x 20 -g 35

    # Historical: daily summary statistics
    python tools/weather.py EGLL 20250115 -s

    # Historical: use existing database
    python tools/weather.py EGLL 20250115 --db tmp/metar_taf.db

    # Live: single airport
    python tools/weather.py EGLL -c

    # Live: multiple airports
    python tools/weather.py EGLL LFPG LSGG -c

    # Route: find airports along route corridor
    python tools/weather.py --route EGLL LFPG -d 25 -c

    # Route: with more waypoints and runway wind components
    python tools/weather.py --route EGLL LFRN LFMN -d 50 -c -r 27,09
"""

import argparse
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from euro_aip.briefing.weather import (
    FlightCategory,
    WeatherAnalyzer,
    WeatherCollection,
    WeatherReport,
    WeatherType,
)


# --- ANSI color helpers ---

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
COLORS = {
    FlightCategory.VFR: "\033[92m",    # Green
    FlightCategory.MVFR: "\033[94m",   # Blue
    FlightCategory.IFR: "\033[91m",    # Red
    FlightCategory.LIFR: "\033[95m",   # Magenta
}
RED = "\033[91m"
GREEN = "\033[92m"

WIND_ARROWS = {
    "headwind": "↓",
    "tailwind": "↑",
    "crosswind_right": "→",
    "crosswind_left": "←",
}


# --- Data layer: Ogimet fetcher + SQLite cache ---


class WeatherDB:
    """Thin SQLite adapter compatible with existing metar_taf.db schema."""

    def __init__(self, db_path="metar_taf.db"):
        self.db_path = db_path
        self._initialize()

    def _initialize(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    icao TEXT NOT NULL,
                    report_datetime DATETIME NOT NULL,
                    report_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    report_data TEXT NOT NULL,
                    UNIQUE(icao, report_datetime, report_type)
                )
            """)

    def has_data(self, icao, date):
        """Check if we have any data for icao on given date."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE icao = ? AND date(report_datetime) = date(?)",
                (icao, date.strftime("%Y-%m-%d")),
            ).fetchone()
            return row[0] > 0

    def store_reports(self, reports):
        """Store raw report dicts (ogimet format)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO reports
                   (icao, report_datetime, report_type, source_type, report_data)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (r["icao"], r["report_datetime"], r["report_type"],
                     r["source_type"], r["report_data"])
                    for r in reports
                ],
            )

    def get_reports(self, icao, date):
        """Get all raw reports for icao on date, ordered chronologically."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                """SELECT report_datetime, report_data, report_type
                   FROM reports
                   WHERE icao = ? AND date(report_datetime) = date(?)
                   ORDER BY report_datetime ASC""",
                (icao, date.strftime("%Y-%m-%d")),
            ).fetchall()


class OgimetFetcher:
    """Fetch METAR/TAF from ogimet.com with HTML caching."""

    def __init__(self, cache_dir="cache"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch(self, icao, date):
        """Fetch data for a single day from ogimet."""
        cache_file = self._cache_path(icao, date)
        if not os.path.exists(cache_file):
            url = self._build_url(icao, date, date)
            print(f"Fetching from: {url}", file=sys.stderr)
            subprocess.run(["curl", "-s", "-o", cache_file, url], check=True)
        else:
            print(f"Using cached: {cache_file}", file=sys.stderr)

        return self._parse_html(cache_file)

    def _cache_path(self, icao, date):
        return os.path.join(self.cache_dir, f"{icao}_{date.strftime('%Y%m%d')}.html")

    def _build_url(self, icao, start_date, end_date):
        params = {
            "lang": "en", "lugar": icao, "tipo": "ALL", "ord": "REV",
            "nil": "SI", "fmt": "html",
            "ano": start_date.year, "mes": start_date.month,
            "day": start_date.day, "hora": "00",
            "anof": end_date.year, "mesf": end_date.month,
            "dayf": end_date.day, "horaf": "23", "minf": "59",
            "send": "send",
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://www.ogimet.com/display_metars2.php?{qs}"

    def _parse_html(self, path):
        with open(path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        reports = []
        icao_pattern = re.compile(r"from ([A-Z]{4}),")

        for table in soup.find_all("table"):
            if not table.find_parent("table"):
                continue
            caption = table.find("caption")
            if not caption:
                continue
            caption_text = caption.get_text()
            match = icao_pattern.search(caption_text)
            if not match:
                continue

            icao = match.group(1)
            if "METAR" not in caption_text and "TAF" not in caption_text:
                continue

            for row in table.find_all("tr"):
                cells = [c.get_text() for c in row.find_all(["td", "th"])]
                if len(cells) != 3:
                    continue
                report_type = "METAR" if "METAR" in cells[2] else "TAF"
                try:
                    dt = datetime.strptime(
                        cells[1].split("->")[0], "%d/%m/%Y %H:%M"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                reports.append({
                    "icao": icao,
                    "report_datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "report_type": report_type,
                    "source_type": cells[0],
                    "report_data": cells[2],
                })
        return reports


# --- Parse DB rows into WeatherReport objects ---


def _fix_validity_dates(report, ref_time):
    """Fix validity dates that the parser created using datetime.now().

    The metar_taf_parser only gets day/hour from TAF validity strings (e.g., 1518/1624),
    so the parser fills in year/month from now(). For historical data we need to
    replace year/month based on the actual report time from the database.
    """
    def _adjust(dt):
        if dt is None:
            return None
        try:
            return dt.replace(year=ref_time.year, month=ref_time.month)
        except ValueError:
            # Day doesn't exist in target month — likely spans to next month
            next_month = ref_time.month % 12 + 1
            next_year = ref_time.year + (1 if next_month == 1 else 0)
            try:
                return dt.replace(year=next_year, month=next_month)
            except ValueError:
                return dt

    report.validity_start = _adjust(report.validity_start)
    report.validity_end = _adjust(report.validity_end)

    for trend in report.trends:
        trend.validity_start = _adjust(trend.validity_start)
        trend.validity_end = _adjust(trend.validity_end)
        # Handle end crossing into next month
        if trend.validity_start and trend.validity_end and trend.validity_end < trend.validity_start:
            next_month = trend.validity_start.month % 12 + 1
            next_year = trend.validity_start.year + (1 if next_month == 1 else 0)
            try:
                trend.validity_end = trend.validity_end.replace(year=next_year, month=next_month)
            except ValueError:
                pass


def parse_db_rows(rows):
    """Convert DB rows into WeatherReport objects, skipping unparseable ones."""
    reports = []
    for row in rows:
        raw = row["report_data"]
        rtype = row["report_type"]
        if rtype == "TAF":
            report = WeatherReport.from_taf(raw, source="ogimet")
        else:
            report = WeatherReport.from_metar(raw, source="ogimet")
        if report:
            # Override observation_time from DB datetime (more reliable)
            db_time = datetime.strptime(row["report_datetime"], "%Y-%m-%d %H:%M:%S")
            report.observation_time = db_time
            # Fix validity dates for historical data
            if report.report_type == WeatherType.TAF:
                _fix_validity_dates(report, db_time)
            reports.append(report)
    return reports


# --- Display layer ---


class WeatherDisplay:
    """Format and display weather reports with ANSI colors."""

    def __init__(self, show_category=False, runways=None, visibility_in_sm=False,
                 crosswind_limit=None, gust_limit=None):
        self.show_category = show_category
        self.runways = runways  # dict: {"27": 270, "09": 90}
        self.visibility_in_sm = visibility_in_sm
        self.crosswind_limit = crosswind_limit
        self.gust_limit = gust_limit

    def show_chronological(self, reports):
        """Display reports in chronological order with TAF trend comparisons."""
        if not reports:
            print("\nNo reports found.")
            return

        print("\nReports in chronological order:")
        current_taf = None

        for report in reports:
            if report.report_type == WeatherType.TAF:
                current_taf = report
                print(f"\n{self._fmt_time(report)} {report.raw_text}\n")
            else:
                self._print_metar_line(report)
                if current_taf:
                    self._print_taf_comparisons(report, current_taf)

    def show_live(self, collection):
        """Display live weather for one or more airports."""
        groups = collection.group_by_airport()
        for icao in sorted(groups.keys()):
            group = groups[icao]
            metars = group.metars().chronological().all()
            tafs = group.tafs().chronological().all()

            print(f"\n{BOLD}--- {icao} ---{RESET}")

            if metars:
                print("METARs:")
                for m in metars:
                    self._print_metar_line(m)
            else:
                print("  No METARs")

            if tafs:
                print("TAFs:")
                for t in tafs:
                    print(f"  {t.raw_text}")
            else:
                print("  No TAFs")

    def show_route_weather(self, result):
        """Display weather along a route corridor."""
        from euro_aip.briefing.weather.route_weather import RouteWeatherResult

        print(f"\n{BOLD}Route: {' → '.join(result.route_icaos)} "
              f"(corridor: {result.corridor_nm}nm){RESET}")

        with_wx = result.airports_with_weather
        total = len(result.airports)

        for apt in with_wx:
            # Header line
            name = f" ({apt.name})" if apt.name else ""
            dist = f"{apt.distance_from_route_nm:.0f}nm from route"
            enroute = ""
            if apt.enroute_distance_nm is not None:
                enroute = f", {apt.enroute_distance_nm:.0f}nm enroute"
            print(f"\n{BOLD}{apt.icao}{name}{RESET} — {dist}{enroute}")

            # Latest METAR
            metar = apt.latest_metar
            if metar:
                self._print_metar_line(metar)

            # Latest TAF
            taf = apt.latest_taf
            if taf:
                print(f"  TAF: {taf.raw_text}")

        print(f"\n{DIM}{len(with_wx)}/{total} airports with weather along route{RESET}")

    def show_summary(self, metars, tafs):
        """Display daily summary statistics."""
        print("\nDaily Forecast Analysis:")
        print(f"Total METARs: {len(metars)}")
        print(f"Total TAFs: {len(tafs)}")

        # Category breakdown
        cat_counts = {}
        for m in metars:
            cat = m.flight_category
            if cat:
                cat_counts[cat.value] = cat_counts.get(cat.value, 0) + 1

        print("\nMETAR Categories:")
        total = len(metars) or 1
        for cat_name in ["VFR", "MVFR", "IFR", "LIFR"]:
            count = cat_counts.get(cat_name, 0)
            pct = count / total * 100
            print(f"  {cat_name}: {count} ({pct:.1f}%)")

        # Forecast accuracy
        matched = 0
        exact = worse = better = 0
        for metar in metars:
            if not metar.flight_category:
                continue
            for taf in reversed(tafs):
                applicable = WeatherAnalyzer.find_applicable_taf(taf, metar.observation_time)
                if applicable and applicable.flight_category:
                    matched += 1
                    cmp = WeatherAnalyzer.compare_categories(
                        metar.flight_category, applicable.flight_category
                    )
                    if cmp == "exact":
                        exact += 1
                    elif cmp == "worse":
                        worse += 1
                    else:
                        better += 1
                    break

        if matched:
            print(f"\nForecast Accuracy (METARs with TAF coverage: {matched}):")
            print(f"  Exact:  {exact} ({exact/matched*100:.1f}%)")
            print(f"  Worse:  {worse} ({worse/matched*100:.1f}%)")
            print(f"  Better: {better} ({better/matched*100:.1f}%)")
        else:
            print("\nNo TAF coverage for comparison.")

    # --- Internal formatting ---

    def _fmt_time(self, report):
        if report.observation_time:
            return report.observation_time.strftime("%d%H%M")
        return "------"

    def _fmt_category(self, report, color_override=None):
        cat = report.flight_category
        if not cat:
            return ""
        color = color_override or COLORS.get(cat, "")
        parts = [f"{color}{cat.value}{RESET}"]

        details = []
        if report.visibility_meters is not None:
            details.append(f"vis:{self._fmt_visibility(report)}")
        if report.ceiling_ft is not None:
            details.append(f"ceil:{report.ceiling_ft}ft")
        if details:
            parts.append(f"{color}[{' '.join(details)}]{RESET}")

        return " ".join(parts)

    def _fmt_visibility(self, report):
        if self.visibility_in_sm and report.visibility_sm is not None:
            return f"{report.visibility_sm:.1f}SM"
        if report.visibility_meters is not None:
            m = report.visibility_meters
            return f"{m}m" if m < 2000 else f"{m // 1000}km"
        return ""

    def _fmt_wind_components(self, report):
        """Format runway wind components for a report."""
        if not self.runways:
            return ""
        parts = []
        for ident, heading in self.runways.items():
            wc = report.wind_components(heading, ident)
            if not wc:
                continue

            head_tail = WIND_ARROWS["headwind"] if wc.headwind >= 0 else WIND_ARROWS["tailwind"]
            xwind_arrow = WIND_ARROWS["crosswind_right"] if wc.crosswind >= 0 else WIND_ARROWS["crosswind_left"]

            hw_str = str(abs(round(wc.headwind)))
            if wc.gust_headwind is not None:
                hw_str = f"{abs(round(wc.headwind))}G{abs(round(wc.gust_headwind))}"

            xw_str = str(abs(round(wc.crosswind)))
            if wc.gust_crosswind is not None:
                xw_str = f"{abs(round(wc.crosswind))}G{abs(round(wc.gust_crosswind))}"

            within = self._check_wind_limits(wc)
            wind_str = f"{ident}:{head_tail}{hw_str}{xwind_arrow}{xw_str}"

            if within is not None:
                wind_str = f"{GREEN if within else RED}{wind_str}{RESET}"
            parts.append(wind_str)
        return f"[{' '.join(parts)}]" if parts else ""

    def _check_wind_limits(self, wc):
        """Return True if within limits, False if not, None if no limits set."""
        if not self.crosswind_limit and not self.gust_limit:
            return None
        within = True
        if self.crosswind_limit:
            if abs(wc.crosswind) > self.crosswind_limit:
                within = False
            if wc.gust_crosswind is not None and abs(wc.gust_crosswind) > self.crosswind_limit:
                within = False
        if self.gust_limit:
            if wc.gust_headwind is not None and abs(wc.gust_headwind) > self.gust_limit:
                within = False
            if wc.gust_crosswind is not None and abs(wc.gust_crosswind) > self.gust_limit:
                within = False
        return within

    def _print_metar_line(self, report):
        parts = [self._fmt_time(report)]
        if self.show_category:
            cat_str = self._fmt_category(report)
            if cat_str:
                parts.append(cat_str)
        wind_str = self._fmt_wind_components(report)
        if wind_str:
            parts.append(wind_str)
        parts.append(report.raw_text)
        print(" ".join(parts))

    def _print_taf_comparisons(self, metar, taf):
        """Print applicable TAF trends with comparison symbols."""
        if not metar.flight_category:
            return

        trends = WeatherAnalyzer.applicable_trends(taf, metar.observation_time)
        if not trends:
            return

        for trend in trends:
            cmp = "?"
            highlight = False
            if trend.flight_category:
                result = WeatherAnalyzer.compare_categories(
                    metar.flight_category, trend.flight_category
                )
                if result == "exact":
                    cmp, highlight = "M", True
                elif result == "better":
                    cmp, highlight = "B", True
                elif result == "worse":
                    cmp, highlight = "W", False

            self._print_trend_line(trend, cmp, highlight)

    def _print_trend_line(self, trend, cmp_symbol, highlight):
        wrap = "" if highlight or not self.show_category else DIM
        parts = []

        # Validity
        validity = self._fmt_trend_validity(trend)
        parts.append(f"{wrap}{validity}{RESET}")
        parts.append(f"{wrap}{cmp_symbol}{RESET}")

        # Trend type (TEMPO, BECMG, etc.)
        if self.show_category:
            cat_color = COLORS.get(trend.flight_category, "") if highlight else DIM
            if trend.probability:
                parts.append(f"{cat_color}PROBA{trend.probability}{RESET}")
            if trend.trend_type:
                parts.append(f"{cat_color}{trend.trend_type}{RESET}")
            cat_str = self._fmt_category(trend, color_override=DIM if not highlight else None)
            if cat_str:
                parts.append(cat_str)

        # Runway winds
        wind_str = self._fmt_wind_components(trend)
        if wind_str:
            parts.append(wind_str)

        # Raw text
        if trend.raw_text:
            parts.append(f"{wrap}{trend.raw_text}{RESET}")

        print(f"   {' '.join(parts)}")

    def _fmt_trend_validity(self, trend):
        if trend.validity_start and trend.validity_end:
            s = trend.validity_start
            e = trend.validity_end
            return f"{s.day:02d}{s.hour:02d}/{e.day:02d}{e.hour:02d}"
        return "----/----"


# --- CLI ---


def parse_runways(runway_arg):
    """Parse '27,09' into {'27': 270, '09': 90}."""
    if not runway_arg:
        return None
    runways = {}
    for rwy in runway_arg.split(","):
        rwy = rwy.strip()
        try:
            heading = int(rwy) * 10
            runways[rwy] = heading
        except ValueError:
            print(f"Warning: ignoring invalid runway '{rwy}'", file=sys.stderr)
    return runways or None


def _is_date(value):
    """Check if a string looks like a YYYYMMDD date."""
    if len(value) != 8:
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def run_historical(args, display):
    """Historical mode: single ICAO + date, fetch from ogimet."""
    icao = args.icao[0].upper()
    report_dt = datetime.strptime(args.date, "%Y%m%d")
    if args.time:
        time_str = f"{args.time[:2]}:{args.time[2:]}"
        report_dt = datetime.strptime(f"{args.date} {time_str}", "%Y%m%d %H:%M")

    db = WeatherDB(args.db)
    if not db.has_data(icao, report_dt):
        fetcher = OgimetFetcher(cache_dir=args.cache_dir)
        raw_reports = fetcher.fetch(icao, report_dt)
        db.store_reports(raw_reports)
        print(f"Stored {len(raw_reports)} reports for {icao}", file=sys.stderr)

    rows = db.get_reports(icao, report_dt)
    all_reports = parse_db_rows(rows)
    collection = WeatherCollection(all_reports)
    metars = collection.metars().chronological().all()
    tafs = collection.tafs().chronological().all()

    if args.summary:
        display.show_summary(metars, tafs)
    elif args.time:
        filtered = collection.before(report_dt).chronological().all()
        recent_tafs = [t for t in tafs if t.observation_time and t.observation_time <= report_dt]
        if recent_tafs:
            last_taf = recent_tafs[-1]
            filtered = [
                r for r in collection.chronological().all()
                if r.observation_time and last_taf.observation_time <= r.observation_time <= report_dt
            ]
        display.show_chronological(filtered)
    else:
        display.show_chronological(collection.chronological().all())


def run_live(args, display):
    """Live mode: fetch from aviationweather.gov for one or more airports."""
    from euro_aip.briefing.sources.avwx import AvWxSource

    icaos = [i.upper() for i in args.icao]
    print(f"Fetching live weather for: {', '.join(icaos)}", file=sys.stderr)

    source = AvWxSource()
    reports = source.fetch_weather(icaos)
    collection = WeatherCollection(reports)

    if args.summary:
        metars = collection.metars().chronological().all()
        tafs = collection.tafs().chronological().all()
        display.show_summary(metars, tafs)
    else:
        display.show_live(collection)


def run_route(args, display):
    """Route mode: find airports along route, fetch weather."""
    from euro_aip.briefing.weather.route_weather import RouteWeatherService
    from euro_aip.storage import DatabaseStorage

    icaos = [i.upper() for i in args.icao]
    corridor = args.distance

    if not args.airport_db:
        print("Error: --airport-db required for route mode", file=sys.stderr)
        sys.exit(1)

    print(f"Loading airport database: {args.airport_db}", file=sys.stderr)
    model = DatabaseStorage(args.airport_db).load_model()

    print(f"Finding airports along {' → '.join(icaos)} "
          f"within {corridor}nm corridor...", file=sys.stderr)

    service = RouteWeatherService()
    result = service.fetch_route_weather(
        route_icaos=icaos,
        corridor_nm=corridor,
        model=model,
    )

    display.show_route_weather(result)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and analyze METAR/TAF reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("icao", type=str, nargs="+",
                        help="ICAO airport code(s) (e.g., EGLL or EGLL LFPG)")
    parser.add_argument("date", type=str, nargs="?", default=None,
                        help="Date in YYYYMMDD format (historical mode)")
    parser.add_argument("time", type=str, nargs="?",
                        help="Optional time in HHMM format (historical mode)")

    parser.add_argument("--route", action="store_true",
                        help="Route mode: find airports along route corridor")
    parser.add_argument("-d", "--distance", type=float, default=25,
                        help="Route corridor width in nm (default: 25)")
    parser.add_argument("--airport-db", type=str,
                        help="Airport database path for route mode")

    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("-c", "--category", action="store_true", help="Show flight categories")
    parser.add_argument("-r", "--runway", type=str, help="Runway numbers, comma-separated (e.g., '27,09')")
    parser.add_argument("-s", "--summary", action="store_true", help="Show summary statistics")
    parser.add_argument("--statute-miles", action="store_true", help="Visibility in statute miles")
    parser.add_argument("-x", "--xwind-limit", type=int, help="Max crosswind in knots")
    parser.add_argument("-g", "--gust-limit", type=int, help="Max gust speed in knots")
    parser.add_argument("--db", type=str, default="metar_taf.db", help="SQLite database path (default: metar_taf.db)")
    parser.add_argument("--cache-dir", type=str, default="cache", help="HTML cache directory (default: cache)")

    args = parser.parse_args()

    # Disambiguate: if the last "icao" looks like a date, move it to date
    if args.date is None and len(args.icao) >= 2 and _is_date(args.icao[-1]):
        args.date = args.icao.pop()

    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    display = WeatherDisplay(
        show_category=args.category,
        runways=parse_runways(args.runway),
        visibility_in_sm=args.statute_miles,
        crosswind_limit=args.xwind_limit,
        gust_limit=args.gust_limit,
    )

    # Mode detection
    if args.route:
        run_route(args, display)
    elif args.date:
        run_historical(args, display)
    else:
        run_live(args, display)


if __name__ == "__main__":
    main()
