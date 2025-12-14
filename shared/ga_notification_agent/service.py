"""
Notification Service - Main entry point for notification data access.

This service provides access to all parsed notification/customs data collected
by the notification agent. It owns the database connection and provides all
query functionality.
"""

import os
import json
import sqlite3
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for accessing parsed notification/customs requirements.
    
    This is the main entry point for all notification data. It owns the database
    connection and provides all query methods.
    """
    
    def __init__(self, db_path: Optional[str] = None, airports_db_path: Optional[str] = None):
        """
        Initialize the notification service.
        
        Args:
            db_path: Path to ga_notifications.db. If None, uses centralized config.
            airports_db_path: Path to airports.db for airport lookups. If None, uses centralized config.
        """
        if db_path is None:
            from shared.aviation_agent.config import get_ga_notifications_db_path
            db_path = get_ga_notifications_db_path()
        
        self.db_path = db_path
        self.airports_db_path = airports_db_path
        self._check_db()
    
    def _check_db(self):
        """Check if database exists."""
        if not os.path.exists(self.db_path):
            logger.warning(f"Notification database not found: {self.db_path}")
            self.db_available = False
        else:
            self.db_available = True
            logger.info(f"Notification database loaded: {self.db_path}")
    
    def _get_airports_db_path(self) -> Optional[str]:
        """Get airports database path for lookups."""
        if self.airports_db_path:
            return self.airports_db_path
        
        # Try to get from centralized config
        try:
            from shared.aviation_agent.config import _default_airports_db
            return str(_default_airports_db())
        except Exception:
            # Fallback to common locations
            candidates = [
                Path(__file__).parent.parent.parent / "web" / "server" / "airports.db",
                Path(__file__).parent.parent.parent / "data" / "airports.db",
                Path("airports.db"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate)
        return None
    
    def _parse_weekday_rules(self, weekday_rules_json: Optional[str], day: str) -> Optional[str]:
        """
        Parse weekday_rules JSON and extract rule for specific day.
        
        Args:
            weekday_rules_json: JSON string like '{"Mon-Fri": "24h notice", "Sat-Sun": "48h notice"}'
            day: Day name like 'Saturday', 'Sunday', 'Monday', etc.
            
        Returns:
            The applicable rule string or None if not found.
        """
        if not weekday_rules_json:
            return None
        
        try:
            rules = json.loads(weekday_rules_json)
        except json.JSONDecodeError:
            return None
        
        day_lower = day.lower()
        
        # Map day to category
        weekend_days = ["saturday", "sunday", "sat", "sun"]
        
        # Check for specific day rules
        for key, value in rules.items():
            key_lower = key.lower()
            if day_lower in key_lower or day_lower[:3] in key_lower:
                return value
        
        # Check for range rules
        if day_lower in weekend_days or day_lower[:3] in ["sat", "sun"]:
            # Weekend
            for key, value in rules.items():
                if "sat" in key.lower() or "sun" in key.lower() or "weekend" in key.lower():
                    return value
        else:
            # Weekday
            for key, value in rules.items():
                if "mon" in key.lower() and "fri" in key.lower():
                    return value
                if "weekday" in key.lower():
                    return value
        
        return None
    
    def get_notification_summary(self, icao: str) -> Optional[Dict[str, Any]]:
        """
        Get parsed notification summary for an airport.
        
        Returns dict with summary, contact_info, confidence, etc.
        Returns None if not found or database unavailable.
        """
        if not self.db_available:
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute('''
                SELECT 
                    icao, rule_type, notification_type, hours_notice,
                    operating_hours_start, operating_hours_end,
                    weekday_rules, schengen_rules, contact_info,
                    summary, confidence
                FROM ga_notification_requirements
                WHERE icao = ?
            ''', (icao.upper(),))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "icao": row["icao"],
                    "rule_type": row["rule_type"],
                    "notification_type": row["notification_type"],
                    "hours_notice": row["hours_notice"],
                    "operating_hours_start": row["operating_hours_start"],
                    "operating_hours_end": row["operating_hours_end"],
                    "weekday_rules": row["weekday_rules"],
                    "schengen_rules": row["schengen_rules"],
                    "contact_info": row["contact_info"],
                    "summary": row["summary"],
                    "confidence": row["confidence"],
                    "parsed": True
                }
            return None
            
        except Exception as e:
            logger.error(f"Error fetching notification for {icao}: {e}")
            return None
    
    def has_parsed_notification(self, icao: str) -> bool:
        """Check if airport has a parsed notification summary."""
        return self.get_notification_summary(icao) is not None
    
    def get_notification_for_airport(
        self,
        icao: str,
        day_of_week: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get customs/immigration notification requirements for a specific airport.
        
        This is the main query method for getting notification data for an airport.
        Returns formatted data suitable for agent tools and API responses.
        
        Args:
            icao: Airport ICAO code (e.g., LFRG, LFPT)
            day_of_week: Optional day to get specific rules for (e.g., "Saturday", "Monday")
            
        Returns:
            Notification requirements including notice period, hours, and contact info.
        """
        if not self.db_available:
            return {
                "found": False,
                "icao": icao.upper(),
                "error": "Notification database not available.",
                "pretty": f"Notification database not available. Cannot look up {icao.upper()}."
            }
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute('''
                SELECT 
                    icao, rule_type, notification_type, hours_notice,
                    operating_hours_start, operating_hours_end,
                    weekday_rules, schengen_rules, contact_info,
                    summary, confidence
                FROM ga_notification_requirements
                WHERE icao = ?
            ''', (icao.upper(),))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return {
                    "found": False,
                    "icao": icao.upper(),
                    "pretty": f"No parsed notification data for {icao.upper()}. This airport may not have customs/immigration requirements parsed yet."
                }
            
            result = {
                "found": True,
                "icao": row["icao"],
                "rule_type": row["rule_type"],
                "notification_type": row["notification_type"],
                "hours_notice": row["hours_notice"],
                "operating_hours": f"{row['operating_hours_start']}-{row['operating_hours_end']}" if row["operating_hours_start"] else None,
                "summary": row["summary"],
                "confidence": row["confidence"],
            }
            
            # Lookup airport coordinates for visualization
            airports_db = self._get_airports_db_path()
            airport_coords = None
            airport_name = None
            if airports_db and os.path.exists(airports_db):
                try:
                    apt_conn = sqlite3.connect(airports_db)
                    apt_conn.row_factory = sqlite3.Row
                    apt_cursor = apt_conn.execute(
                        "SELECT name, latitude_deg, longitude_deg FROM airports WHERE icao_code = ?", 
                        (icao.upper(),)
                    )
                    apt_row = apt_cursor.fetchone()
                    apt_conn.close()
                    if apt_row:
                        airport_name = apt_row["name"]
                        if apt_row["latitude_deg"] and apt_row["longitude_deg"]:
                            airport_coords = {
                                "lat": apt_row["latitude_deg"],
                                "lon": apt_row["longitude_deg"]
                            }
                except Exception:
                    pass
            
            # Parse contact info
            if row["contact_info"]:
                try:
                    contact = json.loads(row["contact_info"])
                    result["phone"] = contact.get("phone")
                    result["email"] = contact.get("email")
                except json.JSONDecodeError:
                    pass
            
            # Format pretty output
            pretty_lines = [f"**Notification Requirements for {row['icao']}**", ""]
            
            # If day specified, get specific rule
            if day_of_week:
                day_rule = self._parse_weekday_rules(row["weekday_rules"], day_of_week)
                if day_rule:
                    pretty_lines.append(f"**For {day_of_week}:** {day_rule}")
                    result["day_specific_rule"] = day_rule
                else:
                    # Fall back to general notice
                    if row["hours_notice"]:
                        pretty_lines.append(f"**For {day_of_week}:** {row['hours_notice']}h notice required")
            
            # General summary
            if row["summary"]:
                pretty_lines.append("")
                pretty_lines.append("**Full Requirements:**")
                pretty_lines.append(row["summary"])
            
            # Notification type description
            type_descriptions = {
                "h24": "Available 24 hours, no prior notice needed",
                "hours": f"Notice required during operating hours",
                "on_request": "Available on request only",
                "business_day": "Previous business day notification required",
            }
            if row["notification_type"] and row["notification_type"] in type_descriptions:
                pretty_lines.append("")
                pretty_lines.append(f"**Type:** {type_descriptions[row['notification_type']]}")
            
            result["pretty"] = "\n".join(pretty_lines)
            
            # Add visualization for map display
            if airport_coords:
                result["visualization"] = {
                    "type": "marker_with_details",
                    "marker": {
                        "ident": icao.upper(),
                        "name": airport_name,
                        "lat": airport_coords["lat"],
                        "lon": airport_coords["lon"],
                        "zoom": 10,
                        "highlight": True,
                        "style": "notification"
                    }
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error looking up notification for {icao}: {e}")
            return {
                "found": False,
                "icao": icao.upper(),
                "error": str(e),
                "pretty": f"Error looking up notification for {icao.upper()}: {e}"
            }
    
    def find_airports_by_notification(
        self,
        max_hours_notice: Optional[int] = None,
        notification_type: Optional[str] = None,
        country: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Find airports filtered by notification requirements.
        
        Args:
            max_hours_notice: Maximum hours notice required (e.g., 24 for "<24h notice")
            notification_type: Type filter - "h24", "hours", "on_request", "business_day"
            country: Optional ISO-2 country code (e.g., FR, DE, GB)
            limit: Maximum results to return
            
        Returns:
            List of airports matching the criteria.
        """
        if not self.db_available:
            return {
                "found": False,
                "error": "Notification database not available.",
                "pretty": "Notification database not available."
            }
        
        airports_db = self._get_airports_db_path()
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Attach airports database for country lookup
            has_airports_db = False
            if airports_db and os.path.exists(airports_db):
                conn.execute(f"ATTACH DATABASE '{airports_db}' AS airports_db")
                has_airports_db = True
            
            # Build query
            if has_airports_db and country:
                query = """
                    SELECT n.icao, n.rule_type, n.notification_type, n.hours_notice,
                           n.weekday_rules, n.summary, n.confidence,
                           a.name as airport_name, a.municipality, a.iso_country,
                           a.latitude_deg, a.longitude_deg
                    FROM ga_notification_requirements n
                    LEFT JOIN airports_db.airports a ON n.icao = a.icao_code
                    WHERE 1=1
                """
            elif has_airports_db:
                query = """
                    SELECT n.icao, n.rule_type, n.notification_type, n.hours_notice,
                           n.weekday_rules, n.summary, n.confidence,
                           a.name as airport_name, a.municipality, a.iso_country,
                           a.latitude_deg, a.longitude_deg
                    FROM ga_notification_requirements n
                    LEFT JOIN airports_db.airports a ON n.icao = a.icao_code
                    WHERE 1=1
                """
            else:
                query = """
                    SELECT icao, rule_type, notification_type, hours_notice,
                           weekday_rules, summary, confidence
                    FROM ga_notification_requirements
                    WHERE 1=1
                """
            
            params = []
            
            if max_hours_notice is not None:
                query += " AND (notification_type = 'h24' OR (hours_notice IS NOT NULL AND hours_notice <= ?))"
                params.append(max_hours_notice)
            
            if notification_type:
                query += " AND notification_type = ?"
                params.append(notification_type.lower())
            
            if country and has_airports_db:
                query += " AND a.iso_country = ?"
                params.append(country.upper())
            
            query += f" ORDER BY n.hours_notice ASC NULLS LAST LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return {
                    "found": False,
                    "count": 0,
                    "airports": [],
                    "pretty": "No airports found matching the criteria."
                }
            
            airports = []
            for row in rows:
                airport = {
                    "icao": row["icao"],
                    "ident": row["icao"],
                    "notification_type": row["notification_type"],
                    "hours_notice": row["hours_notice"],
                    "summary": row["summary"][:100] + "..." if row["summary"] and len(row["summary"]) > 100 else row["summary"],
                }
                if "airport_name" in row.keys():
                    airport["name"] = row["airport_name"]
                    airport["municipality"] = row["municipality"]
                    airport["country"] = row["iso_country"]
                if "latitude_deg" in row.keys() and row["latitude_deg"] and row["longitude_deg"]:
                    airport["latitude_deg"] = row["latitude_deg"]
                    airport["longitude_deg"] = row["longitude_deg"]
                airports.append(airport)
            
            # Format pretty output
            pretty_lines = ["**Airports by Notification Requirements**", ""]
            
            filters_desc = []
            if max_hours_notice:
                filters_desc.append(f"≤{max_hours_notice}h notice")
            if notification_type:
                filters_desc.append(f"type={notification_type}")
            if country:
                filters_desc.append(f"country={country}")
            
            if filters_desc:
                pretty_lines.append(f"Filters: {', '.join(filters_desc)}")
                pretty_lines.append("")
            
            pretty_lines.append(f"Found **{len(airports)}** airports:")
            pretty_lines.append("")
            
            for apt in airports[:10]:
                name = apt.get("name", "")
                hours = apt.get("hours_notice")
                ntype = apt.get("notification_type", "")
                
                if hours:
                    notice_str = f"{hours}h notice"
                elif ntype == "h24":
                    notice_str = "No notice needed (H24)"
                else:
                    notice_str = ntype or "Unknown"
                
                pretty_lines.append(f"- **{apt['icao']}** ({name}): {notice_str}")
            
            if len(airports) > 10:
                pretty_lines.append(f"... and {len(airports) - 10} more")
            
            return {
                "found": True,
                "count": len(airports),
                "airports": airports,
                "pretty": "\n".join(pretty_lines),
                "visualization": {
                    "type": "markers",
                    "data": airports,
                    "markers": airports,
                    "style": "customs"
                }
            }
            
        except Exception as e:
            logger.error(f"Error querying notifications: {e}")
            return {
                "found": False,
                "error": str(e),
                "pretty": f"Error querying notifications: {e}"
            }
    
    def get_notification_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about parsed notification requirements.
        
        Returns summary statistics about notification types, average notice periods, etc.
        """
        if not self.db_available:
            return {
                "found": False,
                "error": "Notification database not available.",
                "pretty": "Notification database not available."
            }
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Get counts by notification type
            cursor = conn.execute("""
                SELECT notification_type, COUNT(*) as count
                FROM ga_notification_requirements
                GROUP BY notification_type
                ORDER BY count DESC
            """)
            by_type = {row["notification_type"]: row["count"] for row in cursor}
            
            # Get total and average confidence
            cursor = conn.execute("""
                SELECT COUNT(*) as total, 
                       AVG(confidence) as avg_confidence,
                       AVG(hours_notice) as avg_hours
                FROM ga_notification_requirements
            """)
            stats = cursor.fetchone()
            
            conn.close()
            
            pretty_lines = [
                "**Notification Parsing Statistics**",
                "",
                f"Total airports parsed: **{stats['total']}**",
                f"Average confidence: **{stats['avg_confidence']:.2f}**",
                f"Average notice hours: **{stats['avg_hours']:.1f}h**" if stats['avg_hours'] else "Average notice: N/A",
                "",
                "**By Notification Type:**",
            ]
            
            for ntype, count in by_type.items():
                pretty_lines.append(f"- {ntype or 'unknown'}: {count}")
            
            return {
                "found": True,
                "total": stats["total"],
                "avg_confidence": stats["avg_confidence"],
                "avg_hours_notice": stats["avg_hours"],
                "by_type": by_type,
                "pretty": "\n".join(pretty_lines)
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {
                "found": False,
                "error": str(e),
                "pretty": f"Error getting statistics: {e}"
            }

