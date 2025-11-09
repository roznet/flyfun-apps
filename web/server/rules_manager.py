#!/usr/bin/env python3
"""
Rules Manager for Aviation Regulations
Handles loading, indexing, filtering, and comparing country-specific aviation rules.
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)


class RulesManager:
    """Manages aviation rules data for multiple countries."""

    def __init__(self, rules_json_path: Optional[str] = None):
        """
        Initialize rules manager.

        Args:
            rules_json_path: Path to rules.json file. If None, looks for RULES_JSON env var.
        """
        self.rules_json_path = rules_json_path or os.getenv("RULES_JSON", "rules.json")
        self.rules = []
        self.rules_index = {}
        self.loaded = False

    def load_rules(self) -> bool:
        """
        Load rules from JSON file.

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            rules_path = Path(self.rules_json_path)

            if not rules_path.exists():
                logger.warning(f"Rules file not found: {self.rules_json_path}")
                return False

            with open(rules_path, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)

            # Handle both list format and dict format with "questions" key
            if isinstance(rules_data, list):
                self.rules = rules_data
            elif isinstance(rules_data, dict) and 'questions' in rules_data:
                self.rules = rules_data['questions']
            else:
                self.rules = []
                logger.warning(f"Unexpected rules format in {self.rules_json_path}")

            logger.info(f"Loaded {len(self.rules)} rules from {self.rules_json_path}")

            # Build index for fast lookups
            self._build_index()
            self.loaded = True
            return True

        except Exception as e:
            logger.error(f"Error loading rules: {e}", exc_info=True)
            return False

    def _build_index(self):
        """Build indexes for fast rule lookups."""
        self.rules_index = {
            'by_country': {},
            'by_category': {},
            'by_id': {},
            'by_tags': {}
        }

        for rule in self.rules:
            country = rule.get('country_code', 'UNKNOWN')
            category = rule.get('category', 'General')
            rule_id = rule.get('question_id', '')
            tags = rule.get('tags', [])

            # Index by country
            if country not in self.rules_index['by_country']:
                self.rules_index['by_country'][country] = []
            self.rules_index['by_country'][country].append(rule)

            # Index by category
            if category not in self.rules_index['by_category']:
                self.rules_index['by_category'][category] = []
            self.rules_index['by_category'][category].append(rule)

            # Index by ID
            if rule_id:
                self.rules_index['by_id'][rule_id] = rule

            # Index by tags
            for tag in tags:
                if tag not in self.rules_index['by_tags']:
                    self.rules_index['by_tags'][tag] = []
                self.rules_index['by_tags'][tag].append(rule)

        # Log index details
        country_counts = {c: len(rules) for c, rules in self.rules_index['by_country'].items()}
        logger.info(f"Built index: {len(self.rules_index['by_country'])} countries, "
                   f"{len(self.rules_index['by_category'])} categories")
        logger.info(f"Rules per country: {country_counts}")

    def get_rules_for_country(
        self,
        country_code: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search_term: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get rules for a specific country with optional filters.

        Args:
            country_code: ISO-2 country code (e.g., 'FR', 'GB', 'DE')
            category: Optional category filter
            tags: Optional list of tags to filter by
            search_term: Optional search term for question/answer text

        Returns:
            List of matching rules
        """
        if not self.loaded:
            self.load_rules()

        country_code = country_code.upper()
        rules = self.rules_index['by_country'].get(country_code, [])
        logger.debug(f"Looking up {country_code} in index, found {len(rules)} rules. Available countries: {list(self.rules_index['by_country'].keys())}")

        # Apply category filter
        if category:
            rules = [r for r in rules if r.get('category') == category]

        # Apply tags filter
        if tags:
            rules = [r for r in rules if any(tag in r.get('tags', []) for tag in tags)]

        # Apply search term filter
        if search_term:
            search_lower = search_term.lower()
            rules = [
                r for r in rules
                if search_lower in r.get('question', '').lower()
                or search_lower in r.get('answer_html', '').lower()
            ]

        return rules

    def compare_rules_between_countries(
        self,
        country1: str,
        country2: str,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare rules between two countries.

        Args:
            country1: First country ISO-2 code
            country2: Second country ISO-2 code
            category: Optional category filter

        Returns:
            Dict with comparison results
        """
        if not self.loaded:
            logger.warning(f"Rules not loaded in compare, loading now...")
            self.load_rules()

        logger.info(f"DEBUG compare: About to get rules for {country1} and {country2}, loaded={self.loaded}, total_rules={len(self.rules)}")
        rules1 = self.get_rules_for_country(country1, category=category)
        logger.info(f"DEBUG compare: Got {len(rules1)} rules for {country1}")
        rules2 = self.get_rules_for_country(country2, category=category)
        logger.info(f"DEBUG compare: Got {len(rules2)} rules for {country2}")

        # Build maps by question_id for comparison
        rules1_map = {r['question_id']: r for r in rules1 if r.get('question_id')}
        rules2_map = {r['question_id']: r for r in rules2 if r.get('question_id')}

        # Find differences
        common_ids = set(rules1_map.keys()) & set(rules2_map.keys())
        only_in_1 = set(rules1_map.keys()) - set(rules2_map.keys())
        only_in_2 = set(rules2_map.keys()) - set(rules1_map.keys())

        differences = []
        for qid in common_ids:
            r1 = rules1_map[qid]
            r2 = rules2_map[qid]

            # Compare answers (simplified - just check if different)
            if r1.get('answer_html') != r2.get('answer_html'):
                differences.append({
                    'question_id': qid,
                    'question': r1.get('question'),
                    'category': r1.get('category'),
                    country1: {
                        'answer': r1.get('answer_html', ''),
                        'links': r1.get('links', [])
                    },
                    country2: {
                        'answer': r2.get('answer_html', ''),
                        'links': r2.get('links', [])
                    }
                })

        return {
            'country1': country1.upper(),
            'country2': country2.upper(),
            'total_rules_country1': len(rules1),
            'total_rules_country2': len(rules2),
            'common_rules': len(common_ids),
            'only_in_country1': len(only_in_1),
            'only_in_country2': len(only_in_2),
            'differences': differences,
            'summary': self._format_comparison_summary(
                country1, country2, differences, only_in_1, only_in_2, rules1_map, rules2_map
            )
        }

    def _format_comparison_summary(
        self,
        country1: str,
        country2: str,
        differences: List[Dict],
        only_in_1: Set[str],
        only_in_2: Set[str],
        rules1_map: Dict,
        rules2_map: Dict
    ) -> str:
        """Format a human-readable comparison summary."""
        lines = []
        lines.append(f"\n**Rules Comparison: {country1.upper()} vs {country2.upper()}**\n")

        if differences:
            lines.append(f"**Different Answers ({len(differences)}):**\n")
            for diff in differences[:5]:  # Show first 5
                lines.append(f"• **{diff['question']}**")
                lines.append(f"  - {country1.upper()}: {diff[country1]['answer'][:100]}...")
                lines.append(f"  - {country2.upper()}: {diff[country2]['answer'][:100]}...")
                lines.append("")

            if len(differences) > 5:
                lines.append(f"  ... and {len(differences) - 5} more differences\n")

        if only_in_1:
            lines.append(f"\n**Only in {country1.upper()} ({len(only_in_1)}):**")
            for qid in list(only_in_1)[:3]:
                rule = rules1_map[qid]
                lines.append(f"• {rule.get('question', 'Unknown')}")
            if len(only_in_1) > 3:
                lines.append(f"  ... and {len(only_in_1) - 3} more")

        if only_in_2:
            lines.append(f"\n**Only in {country2.upper()} ({len(only_in_2)}):**")
            for qid in list(only_in_2)[:3]:
                rule = rules2_map[qid]
                lines.append(f"• {rule.get('question', 'Unknown')}")
            if len(only_in_2) > 3:
                lines.append(f"  ... and {len(only_in_2) - 3} more")

        return "\n".join(lines)

    def format_rules_for_display(
        self,
        rules: List[Dict[str, Any]],
        group_by_category: bool = True
    ) -> str:
        """
        Format rules for user-friendly display.

        Args:
            rules: List of rules to format
            group_by_category: Whether to group by category

        Returns:
            Formatted string
        """
        if not rules:
            return "No rules found matching your criteria."

        if group_by_category:
            # Group by category
            by_category = {}
            for rule in rules:
                cat = rule.get('category', 'General')
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(rule)

            lines = []
            for category, cat_rules in sorted(by_category.items()):
                lines.append(f"\n**{category}** ({len(cat_rules)} rules):")
                for rule in cat_rules[:10]:  # Limit per category
                    lines.append(f"\n• **{rule.get('question', 'Unknown')}**")
                    answer = rule.get('answer_html', 'No answer available')
                    # Strip HTML tags for display
                    import re
                    answer_text = re.sub('<[^<]+?>', '', answer)
                    lines.append(f"  {answer_text[:200]}...")

                    if rule.get('links'):
                        lines.append(f"  📎 Links: {', '.join(rule['links'][:2])}")

                if len(cat_rules) > 10:
                    lines.append(f"  ... and {len(cat_rules) - 10} more in this category")

            return "\n".join(lines)
        else:
            # Simple list
            lines = []
            for rule in rules[:20]:  # Limit total
                lines.append(f"\n• **{rule.get('question', 'Unknown')}**")
                answer = rule.get('answer_html', 'No answer available')
                import re
                answer_text = re.sub('<[^<]+?>', '', answer)
                lines.append(f"  {answer_text[:200]}...")

            if len(rules) > 20:
                lines.append(f"\n... and {len(rules) - 20} more rules")

            return "\n".join(lines)

    def get_available_countries(self) -> List[str]:
        """Get list of available country codes."""
        if not self.loaded:
            self.load_rules()
        return sorted(self.rules_index['by_country'].keys())

    def get_available_categories(self) -> List[str]:
        """Get list of available categories."""
        if not self.loaded:
            self.load_rules()
        return sorted(self.rules_index['by_category'].keys())

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about loaded rules."""
        if not self.loaded:
            self.load_rules()

        return {
            'total_rules': len(self.rules),
            'countries': len(self.rules_index['by_country']),
            'categories': len(self.rules_index['by_category']),
            'country_list': self.get_available_countries(),
            'category_list': self.get_available_categories()
        }
