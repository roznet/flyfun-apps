#!/usr/bin/env python3

"""
AIP Data Export Tool using EuroAipModel
======================================

Description
-----------
Builds a unified EuroAipModel by combining one or more data sources (e.g. WorldAirports,
France/UK eAIP, Autorouter, Border Crossing) and exports to a database with change
tracking and/or JSON. Optionally starts from an existing database as the base model.

Key behavior
------------
- Base model: If --database is provided, the base model is loaded from that DB (or from
  AIRPORTS_DB / airports.db if no path is given), then other sources update/augment it.
- WorldAirports filtering: --worldairports-filter can be one of:
  required (default) | europe | all
- Border crossing: Enable with --pointdepassage. If --pointdepassage-journal is given,
  it will be used as input; otherwise, the source falls back to its defaults.
- Saving fields: By default, only standardized fields are saved to DB storage.
  Use --save-all-fields to save all fields.

Usage
-----
python tools/aipexport.py [AIRPORTS ...]
  [--database[=PATH]]
  [--worldairports --worldairports-db PATH --worldairports-filter {required,europe,all}]
  [--france-eaip DIR | --france-web [--eaip-date YYYY-MM-DD]]
  [--uk-eaip DIR | --uk-web]
  [--autorouter --autorouter-username USER --autorouter-password PASS]
  [--pointdepassage [--pointdepassage-journal FILE]]
  [--database-storage[=PATH]] [--json FILE] [--save-all-fields]
  [-c CACHE_DIR] [--force-refresh | --never-refresh] [-v]

Examples
--------
# Start from existing DB, enrich with border crossing, save only std fields to new DB:
python tools/aipexport.py \
  --database \
  --pointdepassage \
  --database-storage

# WorldAirports (EU only) + France/UK web, export JSON and DB with all fields:
python tools/aipexport.py \
  --worldairports --worldairports-filter europe \
  --france-web --uk-web --airac-date 2025-11-13 \
  --json /tmp/model.json \
  --database-storage /tmp/airports.db \
  --save-all-fields
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import sqlite3
import json
from datetime import datetime

from euro_aip.sources import (
    AutorouterSource, FranceEAIPSource, UKEAIPSource, WorldAirportsSource, 
    DatabaseSource, BorderCrossingSource
)
from euro_aip.sources.france_eaip_web import FranceEAIPWebSource
from euro_aip.sources.uk_eaip_web import UKEAIPWebSource
from euro_aip.models import EuroAipModel, Airport
from euro_aip.sources.base import SourceInterface
from euro_aip.utils.field_standardization_service import FieldStandardizationService
from euro_aip.utils.airac_date_calculator import AIRACDateCalculator
from euro_aip.storage import DatabaseStorage
from euro_aip.parsers import ProcedureParserFactory
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _database_path(path: Optional[str]) -> str:
    if not path:
        if os.environ.get('AIRPORTS_DB') and os.path.exists(os.environ.get('AIRPORTS_DB')):
            return os.environ.get('AIRPORTS_DB')
        if os.path.exists('airports.db'):
            return 'airports.db'
        else:
            raise ValueError("No database file found")
    return path

class ModelBuilder:
    """Builds EuroAipModel from multiple sources."""
    
    def __init__(self, args):
        """Initialize the model builder with configuration."""
        self.args = args
        self.cache_dir = Path(args.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize field standardization service
        self.field_service = FieldStandardizationService()
        
        # Optional base model from database
        self.base_model: Optional[EuroAipModel] = None
        if getattr(self.args, 'database', None) is not None:
            storage = DatabaseStorage(_database_path(self.args.database))
            self.base_model = storage.load_model()
        
        # Initialize sources
        self.sources = {}
        self._initialize_sources()
    
    def _initialize_sources(self):
        """Initialize all configured sources."""
        if self.args.worldairports:
            self.sources['worldairports'] = WorldAirportsSource(
                cache_dir=str(self.cache_dir),
                database=_database_path(self.args.worldairports_db)
            )
        
        if self.args.france_eaip:
            self.sources['france_eaip'] = FranceEAIPSource(
                cache_dir=str(self.cache_dir),
                root_dir=self.args.france_eaip
            )
        
        if getattr(self.args, 'france_web', False):
            self.sources['france_eaip_web'] = FranceEAIPWebSource(
                cache_dir=str(self.cache_dir),
                airac_date=self.args.airac_date,
                eaip_date=getattr(self.args, 'eaip_date', None)
            )
        
        if getattr(self.args, 'uk_web', False):
            self.sources['uk_eaip_web'] = UKEAIPWebSource(
                cache_dir=str(self.cache_dir),
                airac_date=self.args.airac_date
            )
        
        if self.args.uk_eaip:
            self.sources['uk_eaip'] = UKEAIPSource(
                cache_dir=str(self.cache_dir),
                root_dir=self.args.uk_eaip
            )
        
        if self.args.autorouter:
            self.sources['autorouter'] = AutorouterSource(
                cache_dir=str(self.cache_dir),
                username=self.args.autorouter_username,
                password=self.args.autorouter_password
            )
        
        if self.args.pointdepassage:
            # Initialize border crossing source with CSV file if provided
            inputs = []
            if self.args.pointdepassage_journal:
                inputs.append(("airfield_map", self.args.pointdepassage_journal))
            
            self.sources['border_crossing'] = BorderCrossingSource(
                cache_dir=str(self.cache_dir),
                inputs=inputs if inputs else None
            )
        
        # Configure refresh behavior
        if self.args.force_refresh:
            for source in self.sources.values():
                source.set_force_refresh()
        if self.args.never_refresh:
            for source in self.sources.values():
                source.set_never_refresh()
        
        logger.info(f"Initialized {len(self.sources)} sources: {list(self.sources.keys())}")

    def build_model(self, airports: Optional[List[str]] = None) -> EuroAipModel:
        """Build EuroAipModel from all configured sources."""
        model = self.base_model if self.base_model is not None else EuroAipModel()
        
        # Prepare ordered sources: worldairports always last
        sources_items = list(self.sources.items())
        if 'worldairports' in self.sources:
            sources_items = [(k, v) for k, v in sources_items if k != 'worldairports'] + [
                ('worldairports', self.sources['worldairports'])
            ]
        
        for source_name, source in sources_items:
            try:
                logger.info(f"Updating model with {source_name} source")
                
                if isinstance(source, SourceInterface):
                    if source_name == 'worldairports':
                        self._update_model_with_worldairports(source, model, airports)
                    else:
                        source.update_model(model, airports)
                    logger.info(f"Updated model with {source_name}: {model.airports.count()} airports")
                else:
                    logger.warning(f"Source {source_name} doesn't implement SourceInterface, skipping")
            except Exception as e:
                logger.error(f"Error updating model with {source_name}: {e}")
        
        # Filter to specific airports if provided
        if airports:
            logger.info(f"Filtering model to {len(airports)} specified airports")
            filtered_model = EuroAipModel()

            # Get airports to add
            airports_to_add = []
            for airport_code in airports:
                airport = model.airports.where(ident=airport_code).first()
                if airport:
                    airports_to_add.append(airport)
                else:
                    logger.warning(f"Airport {airport_code} not found in model")

            # Use bulk add for efficiency
            if airports_to_add:
                result = filtered_model.bulk_add_airports(airports_to_add)
                logger.info(f"Filtered model created: {result['added']} airports added")
                model = filtered_model
            else:
                logger.warning("No airports found to add to filtered model, using original model")

        
        # Log field mapping statistics
        mapping_stats = model.get_field_mapping_statistics()
        logger.info(f"Field mapping statistics: {mapping_stats['mapped_fields']}/{mapping_stats['total_fields']} fields mapped ({mapping_stats['mapping_rate']:.1%})")
        logger.info(f"Average mapping score: {mapping_stats['average_mapping_score']:.2f}")
        
        logger.info(f"Final model contains {model.airports.count()} airports")
        return model

    def _update_model_with_worldairports(self, source, model, airports):
        """Special update logic for WorldAirportsSource with filtering."""
        if self.args.worldairports_filter == 'required':
            existing_airports = [a.ident for a in model.airports]
            if existing_airports:
                source.update_model(model, existing_airports)
                logger.info(f"Updated WorldAirports with {len(existing_airports)} existing airports")
            else:
                logger.warning("No existing airports in model, skipping WorldAirports default filter")
        elif self.args.worldairports_filter == 'europe':
            european_airports = self._get_european_airports(source)
            if european_airports:
                source.update_model(model, european_airports)
                logger.info(f"Updated WorldAirports with {len(european_airports)} European airports")
            else:
                logger.warning("No European airports found in WorldAirports")
        elif self.args.worldairports_filter == 'all':
            source.update_model(model, airports)
            logger.info(f"Updated WorldAirports with all airports")
        else:
            source.update_model(model, airports)
    
    def _get_european_airports(self, worldairports_source) -> List[str]:
        """Get list of European airports from WorldAirports source."""
        try:
            airports_df = worldairports_source.get_airports()
            european_airports = airports_df[
                (airports_df['continent'] == 'EU') & 
                (~airports_df['type'].isin(['heliport', 'closed']))
            ]['ident'].tolist()
            return european_airports
        except Exception as e:
            logger.error(f"Error getting European airports from WorldAirports: {e}")
            return []
    
    def get_all_airports(self) -> List[str]:
        """Get list of all available airports from all sources that support it."""
        all_airports = set()
        
        for source_name, source in self.sources.items():
            # worldairports contains all airports in the world, so it's not useful to find available airports
            if source_name == 'worldairports' and self.args.worldairports_filter != 'all':
                continue
            if hasattr(source, 'find_available_airports'):
                try:
                    airports = source.find_available_airports()
                    all_airports.update(airports)
                    logger.info(f"Found {len(airports)} airports in {source_name}")
                except Exception as e:
                    logger.warning(f"Error getting airports from {source_name}: {e}")
            else:
                logger.debug(f"Source {source_name} does not support find_available_airports")
        
        if not all_airports:
            if self.base_model is not None:
                base_airports = [a.ident for a in self.base_model.airports]
                logger.info(f"Using {len(base_airports)} airports from base model")
                return base_airports
            logger.warning("No airports found from any source that supports find_available_airports")
            return []
        
        sorted_airports = sorted(list(all_airports))
        logger.info(f"Total unique airports found across all sources: {len(sorted_airports)}")
        return sorted_airports


class JSONExporter:
    """Exports EuroAipModel to JSON file."""
    
    def __init__(self, json_path: str):
        """Initialize JSON exporter."""
        self.json_path = json_path
    
    def save_model(self, model: EuroAipModel):
        """Export the entire model to JSON."""
        logger.info(f"Exporting {model.airports.count()} airports to JSON")
        
        # Convert model to dictionary
        model_data = model.to_dict()
        
        # Write to file
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(model_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"Successfully exported model to {self.json_path}")

class AIPExporter:
    """Main exporter class that coordinates model building and export."""
    
    def __init__(self, args):
        """Initialize the exporter."""
        self.args = args
        self.model_builder = ModelBuilder(args)
        self.exporters = {}
        
        # Initialize exporters based on output format
        if self.args.database_storage is not None:
            self.exporters['database_storage'] = DatabaseStorage(
                _database_path(self.args.database_storage),
                save_only_std_fields=not getattr(self.args, 'save_all_fields', False)
            )
        
        if self.args.json:
            self.exporters['json'] = JSONExporter(self.args.json)
    
    def run(self):
        """Run the export process."""
        # Get airports to export
        if self.args.airports:
            airports = self.args.airports
        else:
            airports = self.model_builder.get_all_airports()
        
        if not airports:
            logger.error("No airports to export")
            #return
        
        logger.info(f"Building model for {len(airports)} airports")
        
        # Build the model
        model = self.model_builder.build_model(airports)
        
        if not model.airports:
            logger.error("No airport data found in model")
            return
        
        # Export to all configured formats
        for exporter_name, exporter in self.exporters.items():
            try:
                logger.info(f"Exporting to {exporter_name}")
                exporter.save_model(model)
            except Exception as e:
                logger.error(f"Error exporting to {exporter_name}: {e}")
        
        # Close exporters that need cleanup
        for exporter in self.exporters.values():
            if hasattr(exporter, 'close'):
                exporter.close()
        
        logger.info(f"Export completed successfully")

def main():
    parser = argparse.ArgumentParser(description='AIP Data Export Tool using EuroAipModel')
    
    # Airport selection
    parser.add_argument('airports', help='List of ICAO airport codes to export (or all if empty)', nargs='*')
    
    # Source configuration
    parser.add_argument(
        '--database',
        nargs='?',
        const='',
        default=None,
        help='Load base model from existing database file (omit value to use default from AIRPORTS_DB or airports.db)'
    )
    parser.add_argument('--worldairports', help='Enable WorldAirports source', action='store_true')
    parser.add_argument('--worldairports-db', help='WorldAirports database file', default=None)
    parser.add_argument('--worldairports-filter', 
                       choices=['required', 'europe', 'all'], 
                       default='required',
                       help='WorldAirports filtering mode: required=only airports from other sources, europe=EU continent only, all=all airports')
    
    parser.add_argument('--france-eaip', help='France eAIP root directory')
    parser.add_argument('--france-web', help='Enable France eAIP web source (HTML index)', action='store_true')
    parser.add_argument('--eaip-date', help='eAIP date (YYYY-MM-DD) for France web source (defaults to AIRAC date if not provided)', required=False)
    parser.add_argument('--uk-eaip', help='UK eAIP root directory')
    parser.add_argument('--uk-web', help='Enable UK eAIP web source (HTML index)', action='store_true')
    parser.add_argument('--airac-date', help='AIRAC effective date (YYYY-MM-DD) for web sources', required=False)
    
    parser.add_argument('--autorouter', help='Enable Autorouter source', action='store_true')
    parser.add_argument('--autorouter-username', help='Autorouter username')
    parser.add_argument('--autorouter-password', help='Autorouter password')
    
    parser.add_argument('--pointdepassage', help='Enable Point de Passage source', action='store_true')
    parser.add_argument('--pointdepassage-journal', help='Point de Passage journal PDF path')
    parser.add_argument('--pointdepassage-db', help='Point de Passage database file', default='airports.db')
    
    # Output configuration
    parser.add_argument(
        '--database-storage',
        nargs='?',
        const='',
        default=None,
        help='New unified database storage file with change tracking (omit value to use default from AIRPORTS_DB or airports.db)'
    )
    parser.add_argument('--save-all-fields', help='Save all AIP fields (default saves only standardized fields)', action='store_true')
    parser.add_argument('--json', help='JSON output file')
    
    # General options
    parser.add_argument('-c', '--cache-dir', help='Directory to cache files', default='cache')
    parser.add_argument('-v', '--verbose', help='Verbose output', action='store_true')
    parser.add_argument('--force-refresh', help='Force refresh of cached data', action='store_true')
    parser.add_argument('--never-refresh', help='Never refresh cached data if it exists', action='store_true')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate that at least one source and one output format are specified
    sources_enabled = any([
        args.database is not None, args.worldairports, args.france_eaip, getattr(args, 'france_web', False), 
        args.uk_eaip, getattr(args, 'uk_web', False), args.autorouter, args.pointdepassage
    ])
    
    outputs_enabled = bool(args.json) or args.database_storage is not None
    
    if not sources_enabled:
        logger.error("At least one data source must be enabled")
        return
    
    if not outputs_enabled:
        logger.error("At least one output format must be specified")
        return
    
    # Handle AIRAC date for web sources
    web_sources_enabled = getattr(args, 'france_web', False) or getattr(args, 'uk_web', False)
    if web_sources_enabled and not args.airac_date:
        # Calculate the current effective AIRAC date
        calculator = AIRACDateCalculator()
        args.airac_date = calculator.get_current_airac_date()
        logger.info(f"No AIRAC date provided, using current effective AIRAC: {args.airac_date}")
    
    exporter = AIPExporter(args)
    exporter.run()

if __name__ == '__main__':
    main() 