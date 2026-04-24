#!/usr/bin/env python3

"""
Build Navigation Database
=========================

Builds a compact nav.db with airports, runways, and waypoints for route
resolution. Airports come from OurAirports (GA-filtered), waypoints from
Eurocontrol FRA and OpenNav. Uses euro_aip DatabaseStorage for compatibility
with the rest of the toolchain.

Airport filters:
- Types: small_airport, medium_airport, large_airport
- ICAO ident: exactly 4 characters
- Has coordinates
- Continents: configurable (default: EU + NA)

Waypoint sources:
- Eurocontrol FRA: ~8,100 FRA-significant waypoints across ECAC
- OpenNav: ~12,000+ additional waypoints per country

Usage:
    python tools/build_nav_db.py [OPTIONS]

    # Default: EU + NA continents
    python tools/build_nav_db.py

    # All continents
    python tools/build_nav_db.py --continents all

    # Custom output path
    python tools/build_nav_db.py -o /tmp/nav.db
"""

import argparse
import logging
import pandas as pd
from pathlib import Path
from typing import List, Optional

from euro_aip.models import EuroAipModel, Airport
from euro_aip.models.runway import Runway
from euro_aip.storage import DatabaseStorage
from euro_aip.sources.eurocontrol_fra import EurocontrolFRASource
from euro_aip.sources.opennav import OpenNavSource
from euro_aip.sources.ourairports_navaids import OurAirportsNavaidSource
from euro_aip.sources.faa_nasr_fix import FAANasrFixSource

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"

GA_TYPES = ['small_airport', 'medium_airport', 'large_airport']
ALL_CONTINENTS = ['AF', 'AN', 'AS', 'EU', 'NA', 'OC', 'SA']


def download_csv(url: str, cache_dir: Path) -> pd.DataFrame:
    """Download CSV from URL, using cache if available."""
    filename = cache_dir / url.split('/')[-1]
    if not filename.exists():
        logger.info(f"Downloading {url}")
        import urllib.request
        cache_dir.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, filename)
    else:
        logger.info(f"Using cached {filename}")
    # keep_default_na=False prevents pandas from reading continent "NA" as NaN
    return pd.read_csv(filename, encoding='utf-8-sig', keep_default_na=False, na_values=[''])


def safe_get(row: pd.Series, key: str):
    """Get value from row, converting NaN to None."""
    value = row.get(key)
    if pd.isna(value):
        return None
    return value


def build_model(airports_df: pd.DataFrame, runways_df: pd.DataFrame) -> EuroAipModel:
    """Build EuroAipModel from filtered DataFrames."""
    model = EuroAipModel()

    # Pre-filter runways to target airports
    target_idents = set(airports_df['ident'])
    runways_df = runways_df[runways_df['airport_ident'].isin(target_idents)]

    # Join airports with runways
    merged = airports_df.merge(
        runways_df, left_on='ident', right_on='airport_ident', how='left'
    )

    airports_to_add = []
    for icao, group in merged.groupby('ident'):
        row = group.iloc[0]
        airport = Airport(
            ident=icao,
            name=safe_get(row, 'name'),
            type=safe_get(row, 'type'),
            latitude_deg=safe_get(row, 'latitude_deg'),
            longitude_deg=safe_get(row, 'longitude_deg'),
            elevation_ft=safe_get(row, 'elevation_ft'),
            continent=safe_get(row, 'continent'),
            iso_country=safe_get(row, 'iso_country'),
            iso_region=safe_get(row, 'iso_region'),
            municipality=safe_get(row, 'municipality'),
            scheduled_service=safe_get(row, 'scheduled_service'),
            gps_code=safe_get(row, 'gps_code'),
            iata_code=safe_get(row, 'iata_code'),
            local_code=safe_get(row, 'local_code'),
            home_link=safe_get(row, 'home_link'),
            wikipedia_link=safe_get(row, 'wikipedia_link'),
            keywords=safe_get(row, 'keywords'),
        )
        airport.add_source('worldairports')

        # Add runways (skip rows where airport_ident is NaN = no runway data)
        for _, rwy_row in group[group['airport_ident'].notna()].iterrows():
            runway = Runway(
                airport_ident=icao,
                length_ft=safe_get(rwy_row, 'length_ft'),
                width_ft=safe_get(rwy_row, 'width_ft'),
                surface=safe_get(rwy_row, 'surface'),
                lighted=safe_get(rwy_row, 'lighted'),
                closed=safe_get(rwy_row, 'closed'),
                le_ident=safe_get(rwy_row, 'le_ident'),
                le_latitude_deg=safe_get(rwy_row, 'le_latitude_deg'),
                le_longitude_deg=safe_get(rwy_row, 'le_longitude_deg'),
                le_elevation_ft=safe_get(rwy_row, 'le_elevation_ft'),
                le_heading_degT=safe_get(rwy_row, 'le_heading_degT'),
                le_displaced_threshold_ft=safe_get(rwy_row, 'le_displaced_threshold_ft'),
                he_ident=safe_get(rwy_row, 'he_ident'),
                he_latitude_deg=safe_get(rwy_row, 'he_latitude_deg'),
                he_longitude_deg=safe_get(rwy_row, 'he_longitude_deg'),
                he_elevation_ft=safe_get(rwy_row, 'he_elevation_ft'),
                he_heading_degT=safe_get(rwy_row, 'he_heading_degT'),
                he_displaced_threshold_ft=safe_get(rwy_row, 'he_displaced_threshold_ft'),
            )
            airport.add_runway(runway)

        airports_to_add.append(airport)

    # validate=False because we already filtered to valid 4-char idents
    result = model.bulk_add_airports(airports_to_add, merge="update_existing",
                                     validate=False, update_derived=True)
    logger.info(f"Added {result['added']} airports, updated {result['updated']}")
    return model


def main():
    parser = argparse.ArgumentParser(description='Build navigation database (airports + waypoints) for route resolution')
    parser.add_argument('-o', '--output', default='nav.db',
                        help='Output database path (default: nav.db)')
    parser.add_argument('-c', '--cache-dir', default='cache',
                        help='Cache directory for downloaded CSVs (default: cache)')
    parser.add_argument('--continents', nargs='*', default=['EU', 'NA'],
                        help='Continents to include (default: EU NA). Use "all" for worldwide.')
    parser.add_argument('--include-faa', action='store_true',
                        help='Include FAA NASR fixes (~70k US named waypoints).')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    continents = ALL_CONTINENTS if args.continents == ['all'] else args.continents

    # Download data
    cache_dir = Path(args.cache_dir)
    airports_df = download_csv(AIRPORTS_URL, cache_dir)
    runways_df = download_csv(RUNWAYS_URL, cache_dir)

    logger.info(f"Raw airports: {len(airports_df)}")

    # Fix OurAirports data: some mainland Spanish airports (LE*) are miscoded as AF
    # ICAO prefix "L" is exclusively Southern Europe, so AF is always wrong
    misclassified = (airports_df['ident'].str.startswith('L')) & (airports_df['continent'] == 'AF')
    if misclassified.sum() > 0:
        logger.info(f"Fixing {misclassified.sum()} L-prefix airports miscoded as AF → EU")
        airports_df.loc[misclassified, 'continent'] = 'EU'

    # Apply GA filters
    airports_df = airports_df[
        airports_df['type'].isin(GA_TYPES)
        & (airports_df['ident'].str.len() == 4)
        & airports_df['latitude_deg'].notna()
        & airports_df['longitude_deg'].notna()
        & airports_df['continent'].isin(continents)
    ]

    # US: only keep K-prefix airports (public), drop FAA LIDs like 00AA (private strips)
    us_private = (airports_df['iso_country'] == 'US') & ~airports_df['ident'].str.startswith('K')
    logger.info(f"Dropping {us_private.sum()} US non-K-prefix airports (private strips)")
    airports_df = airports_df[~us_private]

    logger.info(f"After GA filter ({', '.join(continents)}): {len(airports_df)} airports")
    logger.info(f"By type: {airports_df['type'].value_counts().to_dict()}")
    logger.info(f"By continent: {airports_df['continent'].value_counts().to_dict()}")

    # Build model and save
    model = build_model(airports_df, runways_df)

    # Add waypoints from Eurocontrol FRA and OpenNav
    logger.info("Fetching waypoints...")
    cache_dir_path = Path(args.cache_dir)
    cache_dir_path.mkdir(parents=True, exist_ok=True)

    fra_source = EurocontrolFRASource(cache_dir=str(cache_dir_path))
    fra_source.update_model(model)
    logger.info(f"After FRA: {model.waypoints.count()} waypoints")

    opennav_source = OpenNavSource(cache_dir=str(cache_dir_path))
    opennav_source.update_model(model)
    logger.info(f"After OpenNav: {model.waypoints.count()} waypoints")

    # Scope OurAirports NAVAIDs to countries that are actually in the DB.
    # Using iso_country (authoritative per-row) avoids the continent-miscode
    # problem where e.g. LE* airports were tagged AF in OurAirports data.
    allowed_countries = sorted(airports_df['iso_country'].dropna().unique().tolist())
    logger.info(f"OurAirports NAVAID scope: {len(allowed_countries)} countries")
    ourairports_source = OurAirportsNavaidSource(
        cache_dir=str(cache_dir_path),
        countries=allowed_countries,
    )
    ourairports_source.update_model(model)
    logger.info(f"After OurAirports NAVAIDs: {model.waypoints.count()} waypoints")

    if args.include_faa:
        faa_source = FAANasrFixSource(cache_dir=str(cache_dir_path))
        faa_source.update_model(model)
        logger.info(f"After FAA NASR fixes: {model.waypoints.count()} waypoints")

    # Collapse near-duplicate candidates (same name, coords within tolerance).
    # Keeps genuine geographic collisions (same ident reused in far-apart
    # regions) intact. Source priority: FRA > OpenNav > OurAirports > FAA.
    dedup_result = model.dedup_waypoints(tolerance_nm=0.5)
    logger.info(
        f"Dedup: kept {dedup_result['kept']}, dropped {dedup_result['dropped']} waypoints"
    )

    storage = DatabaseStorage(args.output)
    storage.save_model(model)
    logger.info(f"Saved {model.airports.count()} airports, {model.waypoints.count()} waypoints to {args.output}")


if __name__ == '__main__':
    main()
