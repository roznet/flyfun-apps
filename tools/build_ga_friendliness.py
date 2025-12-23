#!/usr/bin/env python3
"""
CLI tool for building GA friendliness database.

Usage:
    python tools/build_ga_friendliness.py --export path/to/export.json --output data/ga_persona.db
    
Options:
    --export, -e          Path to airfield.directory export JSON
    --output, -o          Output database path (default: data/ga_persona.db)
    --incremental, -i     Only process changed airports
    --since               Only process reviews after this date (ISO format)
    --icaos               Comma-separated list of specific ICAOs
    --resume              Resume from last successful ICAO
    --cache-dir           Cache directory for downloads
    --force-refresh       Force refresh of cached data
    --llm-model           LLM model to use (default: gpt-4o-mini)
    --mock-llm            Use mock LLM (no API calls)
    --failure-mode        How to handle failures: continue, fail_fast, skip
    --verbose, -v         Verbose output
    --dry-run             Don't write to database, just show what would be done
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.ga_friendliness import (
    GAFriendlinessSettings,
    get_settings,
    BuildResult,
    AirfieldDirectorySource,
    AirfieldDirectoryAPISource,
    AirportJsonDirectorySource,
    CSVReviewSource,
    CompositeReviewSource,
    AirportsDatabaseSource,
)
from shared.ga_friendliness.builder import GAFriendlinessBuilder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Build GA friendliness database from reviews",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    # Source options
    source_group = parser.add_argument_group("Source options")
    source_group.add_argument(
        "--export", "-e",
        type=Path,
        help="Path to airfield.directory export JSON",
    )
    source_group.add_argument(
        "--csv",
        type=Path,
        help="Path to CSV file with reviews",
    )
    source_group.add_argument(
        "--json-dir",
        type=Path,
        help="Directory containing per-airport JSON files (e.g., EGTF.json)",
    )
    source_group.add_argument(
        "--download-api",
        action="store_true",
        help="Download from airfield.directory API instead of using local file",
    )
    source_group.add_argument(
        "--api-base-url",
        type=str,
        default="https://airfield.directory/airfield",
        help="Base URL for airfield.directory API (default: https://airfield.directory/airfield)",
    )
    source_group.add_argument(
        "--airports-db",
        type=Path,
        help="Path to airports.db for IFR/hotel/restaurant metadata",
    )
    
    # Output options
    output_group = parser.add_argument_group("Output options")
    output_group.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("data/ga_persona.db"),
        help="Output database path (default: data/ga_persona.db)",
    )
    output_group.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("cache/ga_friendliness"),
        help="Cache directory",
    )
    
    # Processing options
    proc_group = parser.add_argument_group("Processing options")
    proc_group.add_argument(
        "--incremental", "-i",
        action="store_true",
        help="Only process changed airports",
    )
    proc_group.add_argument(
        "--since",
        type=str,
        help="Only process reviews after this date (ISO format)",
    )
    proc_group.add_argument(
        "--icaos",
        type=str,
        help="Comma-separated list of specific ICAOs",
    )
    proc_group.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last successful ICAO",
    )
    proc_group.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force refresh of cached data",
    )
    proc_group.add_argument(
        "--parse-notifications",
        action="store_true",
        help="Parse AIP notification rules (requires --airports-db)",
    )
    proc_group.add_argument(
        "--use-llm-notifications",
        action="store_true",
        help="Use LLM (OpenAI) for complex notification rules",
    )
    
    # LLM options
    llm_group = parser.add_argument_group("LLM options")
    llm_group.add_argument(
        "--llm-model",
        type=str,
        default="gpt-4o-mini",
        help="LLM model to use (default: gpt-4o-mini)",
    )
    llm_group.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM (no API calls)",
    )
    llm_group.add_argument(
        "--api-key",
        type=str,
        help="OpenAI API key (defaults to OPENAI_API_KEY env var)",
    )
    
    # Failure handling
    parser.add_argument(
        "--failure-mode",
        choices=["continue", "fail_fast", "skip"],
        default="continue",
        help="How to handle failures (default: continue)",
    )
    
    # Output options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to database, just show what would be done",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        help="Path to write metrics JSON",
    )
    
    return parser.parse_args()


def create_source(args: argparse.Namespace) -> "ReviewSource":
    """Create review source from arguments."""
    sources = []
    
    # API download mode (requires --icaos)
    if args.download_api:
        if not args.icaos:
            logger.error("--download-api requires --icaos to specify which airports to download")
            sys.exit(1)
        
        icaos = [icao.strip().upper() for icao in args.icaos.split(",")]
        source = AirfieldDirectoryAPISource(
            cache_dir=args.cache_dir,
            icaos=icaos,
            filter_ai_generated=True,
            max_cache_age_days=7,
            base_url=args.api_base_url,
        )
        if args.force_refresh:
            source.set_force_refresh(True)
        return source  # API source is standalone, don't combine with others
    
    if args.export:
        if not args.export.exists():
            logger.error(f"Export file not found: {args.export}")
            sys.exit(1)
        
        source = AirfieldDirectorySource(
            cache_dir=args.cache_dir,
            export_path=args.export,
        )
        if args.force_refresh:
            source.set_force_refresh(True)
        sources.append(source)
    
    if args.csv:
        if not args.csv.exists():
            logger.error(f"CSV file not found: {args.csv}")
            sys.exit(1)
        
        sources.append(CSVReviewSource(args.csv))
    
    if args.json_dir:
        if not args.json_dir.exists():
            logger.error(f"JSON directory not found: {args.json_dir}")
            sys.exit(1)
        
        sources.append(AirportJsonDirectorySource(
            directory=args.json_dir,
            filter_ai_generated=True,
        ))
    
    if not sources:
        return None  # Allow running notification-only mode
    
    if len(sources) == 1:
        return sources[0]
    
    return CompositeReviewSource(sources)


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Parse since date
    since_dt = None
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since)
        except ValueError:
            logger.error(f"Invalid date format: {args.since}")
            return 1
    
    # Parse ICAOs
    icaos = None
    if args.icaos:
        icaos = [icao.strip().upper() for icao in args.icaos.split(",")]
    
    # Create settings
    settings = get_settings(
        ga_meta_db_path=args.output,
        cache_dir=args.cache_dir,
        llm_model=args.llm_model,
        llm_api_key=args.api_key,
        use_mock_llm=args.mock_llm,
        failure_mode=args.failure_mode,
        source_version=f"build-{datetime.now().strftime('%Y%m%d')}",
    )
    
    # Create source (may be None for notification-only mode)
    source = create_source(args)
    
    # Check if we're in notification-only mode
    notification_only = source is None and args.parse_notifications and args.airports_db
    
    if source is None and not notification_only:
        logger.error("No source specified. Use --export, --csv, or --json-dir")
        logger.error("Or use --parse-notifications with --airports-db for notification-only mode")
        return 1
    
    if source:
        logger.info(f"Source: {source.get_source_name()}")
    logger.info(f"Output: {args.output}")
    if not notification_only:
        logger.info(f"Incremental: {args.incremental}")
    
    if args.dry_run and source:
        # Just show what would be done
        # Note: This may load/parse source data but will NOT call LLM
        # For API sources, this may download data (uses cache if available)
        logger.info("DRY RUN MODE: No LLM calls will be made")
        
        icaos_to_process = source.get_icaos()
        if icaos:
            icaos_to_process = icaos_to_process.intersection(set(icaos))
        
        logger.info(f"Would process {len(icaos_to_process)} airports")
        
        # Count reviews (may load data, but no LLM processing)
        total_reviews = sum(len(source.get_reviews_for_icao(i)) for i in icaos_to_process)
        logger.info(f"Total reviews: {total_reviews}")
        
        # Show breakdown by airport (first 10)
        logger.info("\nBreakdown (first 10 airports):")
        for i, icao in enumerate(sorted(icaos_to_process)[:10]):
            count = len(source.get_reviews_for_icao(icao))
            logger.info(f"  {icao}: {count} reviews")
        if len(icaos_to_process) > 10:
            logger.info(f"  ... and {len(icaos_to_process) - 10} more airports")
        
        return 0
    
    # Create airports database source if provided
    airports_db_source = None
    if args.airports_db:
        if not args.airports_db.exists():
            logger.error(f"Airports database not found: {args.airports_db}")
            return 1
        airports_db_source = AirportsDatabaseSource(args.airports_db)
        logger.info(f"Using airports database: {args.airports_db}")
    
    # Handle notification-only mode
    if notification_only:
        logger.info("Running in notification-only mode (no review processing)")
        
        # Ensure database and schema exist
        from shared.ga_friendliness.database import get_connection, ensure_schema_version
        conn = get_connection(args.output)
        ensure_schema_version(conn)
        conn.close()
        
        # Parse notifications
        try:
            from shared.ga_notification_agent import NotificationScorer
            
            use_llm = getattr(args, 'use_llm_notifications', False)
            if use_llm:
                logger.info("Parsing notification rules from airports.db (with LLM fallback)...")
            else:
                logger.info("Parsing notification rules from airports.db...")
            
            notification_scorer = NotificationScorer(
                use_llm_fallback=use_llm,
                llm_model=args.llm_model,
                llm_api_key=args.api_key,
            )
            
            # Score notifications
            scores, parsed_rules = notification_scorer.load_and_score_from_airports_db(
                args.airports_db,
                icaos=icaos,
                return_parsed=True,
            )
            
            # Write to database
            updated = notification_scorer.write_to_ga_meta(
                args.output,
                scores,
                parsed_rules=parsed_rules,
            )
            
            print("\n" + "=" * 60)
            print("NOTIFICATION PARSING SUMMARY")
            print("=" * 60)
            print(f"Airports parsed: {len(scores)}")
            print(f"Rules stored: {sum(len(p.rules) for p in parsed_rules.values())}")
            print(f"Airports updated: {updated}")
            
            return 0
            
        except Exception as e:
            logger.exception(f"Notification parsing failed: {e}")
            return 1
    
    # Create builder
    builder = GAFriendlinessBuilder(settings=settings)
    
    try:
        # Run build
        result = builder.build(
            review_source=source,
            incremental=args.incremental,
            since=since_dt,
            icaos=icaos,
            resume=args.resume,
            airports_db=airports_db_source,
        )
        
        # Print summary
        print("\n" + "=" * 60)
        print("BUILD SUMMARY")
        print("=" * 60)
        print(f"Success: {result.success}")
        print(f"Total airports: {result.metrics.total_airports}")
        print(f"Successful: {result.metrics.successful_airports}")
        print(f"Failed: {result.metrics.failed_airports}")
        print(f"Skipped: {result.metrics.skipped_airports}")
        print(f"Total reviews: {result.metrics.total_reviews}")
        print(f"Total extractions: {result.metrics.total_extractions}")
        if result.metrics.duration_seconds:
            print(f"Duration: {result.metrics.duration_seconds:.1f} seconds")
        
        if result.metrics.errors:
            print(f"\nErrors ({len(result.metrics.errors)}):")
            for error in result.metrics.errors[:10]:  # Show first 10
                print(f"  - {error}")
            if len(result.metrics.errors) > 10:
                print(f"  ... and {len(result.metrics.errors) - 10} more")
        
        # Parse notification rules if requested
        if args.parse_notifications:
            if not args.airports_db:
                logger.error("--parse-notifications requires --airports-db")
                return 1
            
            try:
                from shared.ga_notification_agent import NotificationScorer
                
                use_llm = getattr(args, 'use_llm_notifications', False)
                if use_llm:
                    logger.info("Parsing notification rules from airports.db (with LLM fallback)...")
                else:
                    logger.info("Parsing notification rules from airports.db...")
                
                notification_scorer = NotificationScorer(
                    use_llm_fallback=use_llm,
                    llm_model=args.llm_model,
                    llm_api_key=args.api_key,
                )
                
                # Get ICAOs to process (either specified or from build results)
                notification_icaos = icaos if icaos else None
                
                # Score notifications (also get parsed rules for detailed storage)
                scores, parsed_rules = notification_scorer.load_and_score_from_airports_db(
                    args.airports_db,
                    icaos=notification_icaos,
                    return_parsed=True,
                )
                
                # Write to GA persona database (including detailed rules)
                updated = notification_scorer.write_to_ga_meta(
                    args.output,
                    scores,
                    parsed_rules=parsed_rules,
                )
                
                logger.info(f"Updated {updated} airports with notification scores")
                print(f"Notification scores: {len(scores)} parsed, {updated} updated")
                
            except ImportError as e:
                logger.error(f"Notification agent not available: {e}")
            except Exception as e:
                logger.error(f"Notification parsing failed: {e}")
        
        # Save metrics if requested
        if args.metrics_output:
            metrics_dict = result.metrics.model_dump(mode="json")
            with open(args.metrics_output, "w") as f:
                json.dump(metrics_dict, f, indent=2, default=str)
            logger.info(f"Metrics saved to {args.metrics_output}")
        
        return 0 if result.success else 1
        
    except Exception as e:
        logger.exception(f"Build failed: {e}")
        return 1
    finally:
        builder.close()


if __name__ == "__main__":
    sys.exit(main())

