#!/usr/bin/env python3
"""
Rules Manager for Aviation Regulations
Handles loading, indexing, filtering, and comparing country-specific aviation rules.
"""

import json
import logging
import os
import re
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)


def normalize_tag(tag: str) -> str:
    """Normalize tag names: lowercase and replace spaces with underscores."""
    return tag.lower().strip().replace(" ", "_")


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
        self.question_map: Dict[str, Dict[str, Any]] = {}
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
        """Build indexes for fast rule lookups based on the consolidated rules schema."""

        def _resolve_links(answer_entry: Dict[str, Any]) -> List[str]:
            links = answer_entry.get("links")
            if isinstance(links, list) and links:
                return links
            links_json = answer_entry.get("links_json")
            if isinstance(links_json, list) and links_json:
                return links_json
            if isinstance(links_json, str) and links_json:
                return [links_json]
            if isinstance(links, str) and links:
                return [links]
            return []

        self.rules_index = {
            'by_country': {},
            'by_id': {},
            'categories': {},
            'tags': {}
        }
        self.question_map = {}

        for question in self.rules:
            question_id = question.get('question_id') or question.get('id')
            if not question_id:
                continue

            question_text = question.get('question_text') or question.get('question') or ""
            question_raw = question.get('question_raw', "")
            question_prefix = question.get('question_prefix', "")
            category = question.get('category') or "General"
            # Normalize tags: lowercase and replace spaces with underscores
            # Tags are dynamically injected into the planner prompt via get_available_tags()
            raw_tags = question.get('tags') or []
            tags = [normalize_tag(t) for t in raw_tags]
            answers_by_country = question.get('answers_by_country') or {}

            question_info = {
                'question_id': question_id,
                'question_text': question_text,
                'question_raw': question_raw,
                'question_prefix': question_prefix,
                'category': category,
                'tags': tags,
                'answers_by_country': answers_by_country
            }

            self.question_map[question_id] = question_info
            self.rules_index['by_id'][question_id] = question_info
            self.rules_index['categories'].setdefault(category, set()).add(question_id)
            for tag in tags:
                self.rules_index['tags'].setdefault(tag, set()).add(question_id)

            for country_code, answer in answers_by_country.items():
                if not country_code:
                    continue
                country_code = country_code.upper()
                entry = {
                    'question_id': question_id,
                    'question_text': question_text,
                    'question_raw': question_raw,
                    'question_prefix': question_prefix,
                    'category': category,
                    'tags': tags,
                    'country_code': country_code,
                    'answer_html': answer.get('answer_html', ''),
                    'links': _resolve_links(answer),
                    'last_reviewed': answer.get('last_reviewed'),
                    'confidence': answer.get('confidence'),
                }
                self.rules_index['by_country'].setdefault(country_code, []).append(entry)

        # Sort entries for deterministic output
        for entries in self.rules_index['by_country'].values():
            entries.sort(key=lambda x: x['question_text'].lower())

        country_counts = {c: len(entries) for c, entries in self.rules_index['by_country'].items()}
        logger.info(
            "Built rules index: %d questions, %d countries, %d categories",
            len(self.question_map),
            len(self.rules_index['by_country']),
            len(self.rules_index['categories'])
        )
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
        if not self.loaded:
            return []

        country_code = country_code.upper()
        entries = list(self.rules_index.get('by_country', {}).get(country_code, []))
        logger.debug(
            "Looking up %s in index, found %d rules. Available countries: %s",
            country_code,
            len(entries),
            list(self.rules_index.get('by_country', {}).keys())
        )

        # Apply category filter
        if category:
            entries = [r for r in entries if category.lower() in r.get('category').lower()]

        # Apply tags filter
        if tags:
            entries = [
                r for r in entries
                if any(tag in (r.get('tags') or []) for tag in tags)
            ]

        # Apply search term filter
        if search_term:
            search_lower = search_term.lower()
            entries = [
                r for r in entries
                if search_lower in (r.get('question_text') or '').lower()
                or search_lower in (r.get('answer_html') or '').lower()
            ]

        return entries

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
            logger.warning("Rules not loaded in compare, loading now...")
            self.load_rules()
        if not self.loaded:
            return {}

        logger.info(
            "Comparing rules for %s vs %s (category=%s) - total questions=%d",
            country1, country2, category, len(self.question_map)
        )

        country1 = country1.upper()
        country2 = country2.upper()

        rules1 = {
            r['question_id']: r
            for r in self.get_rules_for_country(country1, category=category)
            if r.get('question_id')
        }
        rules2 = {
            r['question_id']: r
            for r in self.get_rules_for_country(country2, category=category)
            if r.get('question_id')
        }

        logger.info("Found %d entries for %s and %d entries for %s", len(rules1), country1, len(rules2), country2)

        # Find differences
        common_ids = set(rules1.keys()) & set(rules2.keys())
        only_in_1 = set(rules1.keys()) - set(rules2.keys())
        only_in_2 = set(rules2.keys()) - set(rules1.keys())

        differences = []
        for qid in common_ids:
            r1 = rules1[qid]
            r2 = rules2[qid]

            # Compare answers (simplified - just check if different)
            if (r1.get('answer_html') or '').strip() != (r2.get('answer_html') or '').strip():
                question = self.question_map.get(qid, {})
                differences.append({
                    'question_id': qid,
                    'question': question.get('question_text', r1.get('question_text')),
                    'category': question.get('category', r1.get('category')),
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
            "differences_count": len(differences),
            'summary': self._format_comparison_summary(
                country1, country2, differences, only_in_1, only_in_2, rules1, rules2
            )
        }

    def compare_rules_across_countries(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate a comparison of rules for all available countries, grouped by category.

        Args:
            category: Optional category filter. If provided, only rules within this category are included.
            tags: Optional list of tags; if provided, rules must have at least one matching tag.

        Returns:
            Dict containing:
                - categories: list of category summaries
                - country_list: list of countries included
                - total_rules: total number of unique questions included
        """
        if not self.loaded:
            self.load_rules()
        if not self.loaded:
            return {"categories": [], "country_list": [], "total_rules": 0}

        countries = self.get_available_countries()
        questions: Dict[str, Dict[str, Any]] = {}

        for country in countries:
            rules = self.get_rules_for_country(
                country_code=country,
                category=category,
                tags=tags
            )
            for rule in rules:
                question_id = rule.get('question_id') or rule.get('id')
                if not question_id:
                    continue

                info = questions.setdefault(question_id, {
                    "question_id": question_id,
                    "question_text": rule.get('question_text') or rule.get('question') or '',
                    "category": rule.get('category') or 'General',
                    "tags": rule.get('tags') or [],
                    "answers_by_country": {}
                })

                info['answers_by_country'][country.upper()] = {
                    "answer_html": rule.get('answer_html') or '',
                    "links": rule.get('links') or [],
                    "last_reviewed": rule.get('last_reviewed'),
                    "confidence": rule.get('confidence'),
                }

        categories: Dict[str, List[Dict[str, Any]]] = {}
        for question in questions.values():
            categories.setdefault(question["category"], []).append(question)

        category_summaries = []
        for cat_name, cat_questions in sorted(categories.items(), key=lambda item: item[0].lower()):
            cat_questions.sort(key=lambda q: q["question_text"].lower())
            category_summaries.append({
                "name": cat_name,
                "count": len(cat_questions),
                "questions": cat_questions,
            })

        return {
            "categories": category_summaries,
            "country_list": countries,
            "total_rules": len(questions),
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
                rule = rules1_map.get(qid) or {}
                question = self.question_map.get(qid, {})
                lines.append(f"• {question.get('question_text', rule.get('question_text', 'Unknown'))}")
            if len(only_in_1) > 3:
                lines.append(f"  ... and {len(only_in_1) - 3} more")

        if only_in_2:
            lines.append(f"\n**Only in {country2.upper()} ({len(only_in_2)}):**")
            for qid in list(only_in_2)[:3]:
                rule = rules2_map.get(qid) or {}
                question = self.question_map.get(qid, {})
                lines.append(f"• {question.get('question_text', rule.get('question_text', 'Unknown'))}")
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
                for rule in cat_rules:
                    lines.append(f"\n• **{rule.get('question_text', 'Unknown')}**")
                    answer = rule.get('answer_html', 'No answer available')
                    # Strip HTML tags for display
                    answer_text = re.sub('<[^<]+?>', '', answer)
                    lines.append(f"  {answer_text[:200]}...")

                    if rule.get('links'):
                        lines.append(f"  📎 Links: {', '.join(rule['links'][:2])}")

            return "\n".join(lines)
        else:
            # Simple list
            lines = []
            for rule in rules[:20]:  # Limit total
                lines.append(f"\n• **{rule.get('question_text', 'Unknown')}**")
                answer = rule.get('answer_html', 'No answer available')
                answer_text = re.sub('<[^<]+?>', '', answer)
                lines.append(f"  {answer_text[:200]}...")

            if len(rules) > 20:
                lines.append(f"\n... and {len(rules) - 20} more rules")

            return "\n".join(lines)

    def get_available_countries(self) -> List[str]:
        """Get list of available country codes."""
        if not self.loaded:
            self.load_rules()
        if not self.loaded:
            return []
        return sorted(self.rules_index.get('by_country', {}).keys())

    def get_available_categories(self) -> List[str]:
        """Get list of available categories."""
        if not self.loaded:
            self.load_rules()
        if not self.loaded:
            return []
        return sorted(self.rules_index.get('categories', {}).keys())

    def get_available_tags(self) -> List[str]:
        """Get list of available tags."""
        if not self.loaded:
            self.load_rules()
        if not self.loaded:
            return []
        return sorted(self.rules_index.get('tags', {}).keys())

    def get_questions_by_tag(self, tag: str) -> List[str]:
        """
        Get question IDs that have a specific tag.

        Args:
            tag: Tag name to filter by (will be normalized)

        Returns:
            List of question IDs
        """
        if not self.loaded:
            self.load_rules()
        if not self.loaded:
            return []
        # Normalize input tag to match indexed tags
        normalized_tag = normalize_tag(tag)
        question_ids = self.rules_index.get('tags', {}).get(normalized_tag, set())
        return sorted(question_ids)

    def get_questions_by_tags(self, tags: List[str]) -> List[str]:
        """
        Get question IDs that have any of the specified tags (union).

        Args:
            tags: List of tag names to filter by (each will be normalized)

        Returns:
            List of question IDs matching any of the tags
        """
        if not self.loaded:
            self.load_rules()
        if not self.loaded:
            return []

        question_id_set: Set[str] = set()
        for tag in tags:
            normalized_tag = normalize_tag(tag)
            question_id_set.update(self.rules_index.get('tags', {}).get(normalized_tag, set()))
        return sorted(question_id_set)

    def get_questions_by_category(self, category: str) -> List[str]:
        """
        Get question IDs that belong to a specific category.

        Args:
            category: Category name to filter by

        Returns:
            List of question IDs
        """
        if not self.loaded:
            self.load_rules()
        if not self.loaded:
            return []
        question_ids = self.rules_index.get('categories', {}).get(category, set())
        return sorted(question_ids)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about loaded rules."""
        if not self.loaded:
            self.load_rules()
        if not self.loaded:
            return {}

        return {
            'total_questions': len(self.question_map),
            'countries': len(self.rules_index.get('by_country', {})),
            'categories': len(self.rules_index.get('categories', {})),
            'tags': len(self.rules_index.get('tags', {})),
            'country_list': self.get_available_countries(),
            'category_list': self.get_available_categories(),
            'tag_list': self.get_available_tags()
        }

