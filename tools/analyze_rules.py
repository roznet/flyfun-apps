#!/usr/bin/env python3
"""
Analyze aviation rules using LLM for cross-country insights and video script generation.

PURPOSE:
    Generate video presentation content that shows "typical behavior across Europe"
    plus "notable exceptions" for aviation topics. Input is a list of topics (e.g.,
    "IFR/VFR transition", "When is a flight plan mandatory"). Output is structured
    markdown with typical approach, 2-3 country exceptions, and practical takeaway.

COMMANDS:
    - identify: Find questions in rules.json relevant to a topic (via tags or RAG)
    - video-script: Generate video presentation segments (typical behavior + exceptions)
    - cross-country-summary: Comprehensive analysis across countries

QUESTION IDENTIFICATION:
    Topics like "IFR/VFR transition" are matched to questions in rules.json via:
    1. Tag inference: Keywords in topic -> tags (e.g., "transition" -> vfr_ifr_transition)
    2. RAG: Semantic similarity search in vector DB
    Use --method tag|rag|both to control this.

QUESTION FILTERING (--filter-method):
    When many questions match (e.g., 20+), you can filter to most relevant:
    - none: Send all matched questions to LLM (default, works well with gpt-4o)
    - llm: Ask LLM to pick most relevant questions for the topic
    - rag: Rank questions by embedding similarity to topic text

    Note: LLM filtering can be too selective (returning 0 questions for some topics).
    The "none" approach with a better model (gpt-4o) often gives best results.

OUTPUT:
    - Individual files per topic: video_*.md, script_*.txt, video_*.json
    - Combined file: tmp/video_scripts/combined/run_XX_<method>_<model>.md
    - Each run file includes a configuration header for reproducibility

    Use tmp/runs_to_excel.py to compare multiple runs in Excel format.

USAGE EXAMPLES:
    # Basic: process topics file with no filtering
    python tools/analyze_rules.py --model gpt-4o video-script --topics-file tmp/questions_europediffs.md

    # With LLM filtering (picks most relevant questions)
    python tools/analyze_rules.py --model gpt-4o-mini video-script --topics-file tmp/questions.md --filter-method llm

    # Single topic
    python tools/analyze_rules.py video-script "IFR/VFR transition"

    # Identify questions only (no analysis)
    python tools/analyze_rules.py identify "flight plan requirements" --method both

ARCHITECTURE:
    QuestionIdentifier: Finds relevant questions via tags or RAG
    RulesAnalyzer: Generates video scripts using LLM

    Flow: Topic -> Tag inference -> Question matching -> [Optional filtering] -> LLM analysis

KEY FILES:
    - data/rules.json: Source aviation rules with questions and country answers
    - cache/rules_vector_db: ChromaDB vector database for RAG
    - tmp/questions_europediffs.md: Topics file (one topic per line)
    - tmp/video_scripts/combined/: Output runs with config headers
    - tmp/runs_to_excel.py: Companion script to compare runs in Excel

DEPENDENCIES:
    pip install langchain-core langchain-openai pandas openpyxl
    Environment: OPENAI_API_KEY
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent to path for shared imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
except ImportError:
    print("This tool requires langchain packages. Try: pip install langchain-core langchain-openai", file=sys.stderr)
    sys.exit(1)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class QuestionMatch:
    """A question matched via identification."""
    question_id: str
    question_text: str
    category: str
    tags: List[str]
    similarity: Optional[float] = None  # For RAG matches
    match_method: str = "unknown"  # "tag", "rag", or "both"


@dataclass
class IdentificationResult:
    """Result of question identification for a topic."""
    topic: str
    method: str  # "tag", "rag", or "both"
    tag_matches: List[QuestionMatch] = field(default_factory=list)
    rag_matches: List[QuestionMatch] = field(default_factory=list)
    combined_matches: List[QuestionMatch] = field(default_factory=list)
    inferred_tags: List[str] = field(default_factory=list)


@dataclass
class CountryException:
    """A notable exception for a country."""
    country: str
    country_name: str
    what_differs: str
    why_it_matters: str


@dataclass
class VideoSegment:
    """A video script segment for a topic."""
    topic: str
    question_ids: List[str]
    typical_behavior: str
    exceptions: List[CountryException]
    practical_takeaway: str
    countries_analyzed: List[str]
    # Metadata about how this was generated
    method: str = "keyword"  # "keyword", "rag", "embedding"
    questions_before_filter: int = 0
    questions_after_filter: int = 0
    min_difference_threshold: float = 0.0


@dataclass
class CrossCountrySummary:
    """Comprehensive cross-country analysis."""
    question_id: str
    question_text: str
    category: str
    tags: List[str]
    common_practices: str
    key_differences: str
    country_specific: str
    cross_border_advice: str
    countries_analyzed: List[str]


# =============================================================================
# Country Code Mapping
# =============================================================================

COUNTRY_NAMES = {
    "AT": "Austria",
    "BE": "Belgium",
    "CH": "Switzerland",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DK": "Denmark",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "GR": "Greece",
    "HR": "Croatia",
    "HU": "Hungary",
    "IE": "Ireland",
    "IT": "Italy",
    "LU": "Luxembourg",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "SE": "Sweden",
    "SI": "Slovenia",
    "SK": "Slovakia",
}


def get_country_name(code: str) -> str:
    """Get full country name from ISO-2 code."""
    return COUNTRY_NAMES.get(code, code)


# =============================================================================
# Tag Inference from Topics
# =============================================================================

# Mapping of keywords/phrases to tags
TAG_KEYWORDS = {
    "flight plan": ["flight_plan"],
    "fpl": ["flight_plan"],
    "filing": ["flight_plan"],
    "closing": ["flight_plan"],
    "opening": ["flight_plan"],
    "amending": ["flight_plan"],
    "transponder": ["transponder"],
    "squawk": ["transponder"],
    "mode s": ["transponder"],
    "radio": ["transponder"],  # Often grouped
    "vfr": ["vfr"],
    "visual": ["vfr"],
    "ifr": ["ifr"],
    "instrument": ["ifr"],
    "transition": ["vfr_ifr_transition"],
    "airspace": ["airspace", "zones"],
    "controlled": ["airspace", "clearance"],
    "uncontrolled": ["uncontrolled"],
    "class": ["airspace"],
    "zone": ["zones"],
    "restricted": ["zones"],
    "danger": ["zones"],
    "prohibited": ["zones"],
    "clearance": ["clearance"],
    "penetration": ["penetration"],
    "permission": ["permission", "prior_permision"],
    "ppr": ["permission", "prior_permision"],
    "slot": ["permission", "prior_permision"],
    "airfield": ["airfield"],
    "aerodrome": ["airfield"],
    "airport": ["airfield"],
    "military": ["airfield", "permission"],  # Military airfields
    "circuit": ["join"],
    "join": ["join"],
    "pattern": ["join"],
    "ats": ["air_traffic_service"],
    "fis": ["air_traffic_service"],
    "service": ["air_traffic_service"],
    "international": ["international"],
    "customs": ["international"],
    "border": ["international"],
    "tools": ["tools"],
    "autorouter": ["tools"],
    "foreflight": ["tools"],
    "procedure": ["procedure"],
    "semicircle": ["semicircle"],
    "altitude": ["semicircle"],
    "night": ["vfr"],  # Night VFR is under vfr tag
    "nvfr": ["vfr"],
    "special vfr": ["vfr", "clearance"],
    "svfr": ["vfr", "clearance"],
    "tmz": ["transponder", "zones"],  # Transponder Mandatory Zone
    "rmz": ["transponder", "zones"],  # Radio Mandatory Zone
    "routing": ["ifr"],
    "fra": ["ifr"],  # Free Route Airspace
    "design": ["airspace"],
    "authority": ["air_traffic_service", "airfield"],
    "transit": ["airspace", "clearance"],
    "accessibility": ["airfield", "permission"],
}


def infer_tags_from_topic(topic: str, apply_preferences: bool = True) -> List[str]:
    """
    Infer relevant tags from a natural language topic.

    Args:
        topic: Natural language topic/question
        apply_preferences: If True, apply tag suppression rules (e.g., vfr_ifr_transition suppresses vfr/ifr)

    Returns:
        List of inferred tags
    """
    from shared.rules_manager import apply_tag_preferences

    topic_lower = topic.lower()
    inferred = set()

    for keyword, tags in TAG_KEYWORDS.items():
        if keyword in topic_lower:
            inferred.update(tags)

    tags = sorted(list(inferred))

    # Apply tag preference rules (specific tags suppress broader ones)
    if apply_preferences and tags:
        tags = apply_tag_preferences(tags)

    return tags


def extract_countries_from_topic(topic: str) -> List[str]:
    """Extract country codes mentioned in a topic."""
    topic_lower = topic.lower()
    countries = []

    # Common aliases
    COUNTRY_ALIASES = {
        "uk": "GB",
        "britain": "GB",
        "england": "GB",  # Not technically correct but common usage
        "swiss": "CH",
        "holland": "NL",
    }

    # Check for aliases first
    for alias, code in COUNTRY_ALIASES.items():
        if re.search(rf'\b{alias}\b', topic_lower):
            if code not in countries:
                countries.append(code)

    # Check for country names
    name_to_code = {name.lower(): code for code, name in COUNTRY_NAMES.items()}
    for name, code in name_to_code.items():
        if name in topic_lower:
            if code not in countries:
                countries.append(code)

    # Check for country codes (CASE SENSITIVE - codes are uppercase)
    # This avoids matching "it" in "it provides" as Italy
    for code in COUNTRY_NAMES.keys():
        # Match isolated codes - must be uppercase in text
        if re.search(rf'\b{code}\b', topic):
            if code not in countries:
                countries.append(code)

    return countries


# =============================================================================
# Question Identifier
# =============================================================================

class QuestionIdentifier:
    """Identifies relevant questions from rules.json using tags or RAG."""

    def __init__(
        self,
        rules_manager,
        rules_rag=None,
        verbose: bool = False
    ):
        self.rules_manager = rules_manager
        self.rules_rag = rules_rag
        self.verbose = verbose

    def identify_by_tags(
        self,
        topic: str,
        explicit_tags: Optional[List[str]] = None
    ) -> Tuple[List[QuestionMatch], List[str]]:
        """
        Identify questions by tag matching.

        Returns tuple of (matches, inferred_tags).
        """
        # Infer tags from topic if not provided
        tags = explicit_tags or infer_tags_from_topic(topic)

        if not tags:
            if self.verbose:
                print(f"  No tags inferred from topic: {topic}", file=sys.stderr)
            return [], []

        if self.verbose:
            print(f"  Inferred tags: {tags}", file=sys.stderr)

        # Get questions matching any of the tags
        question_ids = self.rules_manager.get_questions_by_tags(tags)

        matches = []
        for qid in question_ids:
            q = self.rules_manager.question_map.get(qid)
            if q:
                matches.append(QuestionMatch(
                    question_id=qid,
                    question_text=q.get("question_text", qid),
                    category=q.get("category", ""),
                    tags=q.get("tags", []),
                    match_method="tag"
                ))

        return matches, tags

    def filter_by_rag_similarity(
        self,
        topic: str,
        question_ids: List[str],
        max_questions: int = 10
    ) -> List[str]:
        """
        Filter questions by RAG similarity to the topic.

        Args:
            topic: The human question/topic
            question_ids: Candidate question IDs to filter
            max_questions: Maximum questions to return

        Returns:
            List of question IDs ranked by similarity to topic
        """
        if not self.rules_rag:
            if self.verbose:
                print("  RAG not available, returning original order", file=sys.stderr)
            return question_ids[:max_questions]

        if len(question_ids) <= max_questions:
            return question_ids

        try:
            # Query RAG with a high top_k to get similarity scores
            results = self.rules_rag.retrieve_rules(
                query=topic,
                top_k=50,  # Get many results to increase chance of overlap
                similarity_threshold=0.0  # Get all similarities
            )

            # Build similarity map (question_id -> best similarity)
            similarity_map = {}
            for r in results:
                qid = r.get("question_id")
                sim = r.get("similarity", 0)
                if qid and qid in question_ids:
                    # Keep best similarity if question appears multiple times
                    if qid not in similarity_map or sim > similarity_map[qid]:
                        similarity_map[qid] = sim

            # Sort candidate questions by similarity
            scored = [(qid, similarity_map.get(qid, 0)) for qid in question_ids]
            scored.sort(key=lambda x: x[1], reverse=True)

            result = [qid for qid, _ in scored[:max_questions]]

            if self.verbose:
                found = sum(1 for qid in result if qid in similarity_map)
                print(f"  RAG ranked {len(result)} questions ({found} with similarity scores)", file=sys.stderr)

            return result

        except Exception as e:
            if self.verbose:
                print(f"  RAG filtering failed: {e}, using original order", file=sys.stderr)
            return question_ids[:max_questions]

    def identify_by_rag(
        self,
        topic: str,
        top_k: int = 5,
        similarity_threshold: float = 0.3
    ) -> List[QuestionMatch]:
        """Identify questions by RAG semantic search."""
        if not self.rules_rag:
            if self.verbose:
                print("  RAG not available, skipping semantic search", file=sys.stderr)
            return []

        try:
            results = self.rules_rag.retrieve_rules(
                query=topic,
                top_k=top_k,
                similarity_threshold=similarity_threshold
            )
        except Exception as e:
            if self.verbose:
                print(f"  RAG retrieval failed: {e}", file=sys.stderr)
            return []

        # Deduplicate by question_id (RAG may return same question for multiple countries)
        seen = set()
        matches = []
        for r in results:
            qid = r.get("question_id")
            if qid and qid not in seen:
                seen.add(qid)
                matches.append(QuestionMatch(
                    question_id=qid,
                    question_text=r.get("question_text", qid),
                    category=r.get("category", ""),
                    tags=r.get("tags", []),
                    similarity=r.get("similarity"),
                    match_method="rag"
                ))

        return matches

    def identify(
        self,
        topic: str,
        method: str = "both",
        explicit_tags: Optional[List[str]] = None,
        top_k: int = 5
    ) -> IdentificationResult:
        """
        Identify relevant questions for a topic.

        Args:
            topic: Natural language topic/question
            method: "tag", "rag", or "both"
            explicit_tags: Override inferred tags
            top_k: Number of RAG results

        Returns:
            IdentificationResult with matches from requested methods
        """
        result = IdentificationResult(topic=topic, method=method)

        if method in ("tag", "both"):
            tag_matches, inferred_tags = self.identify_by_tags(topic, explicit_tags)
            result.tag_matches = tag_matches
            result.inferred_tags = inferred_tags

        if method in ("rag", "both"):
            result.rag_matches = self.identify_by_rag(topic, top_k=top_k)

        # Combine matches (union, preserving order and deduping)
        seen = set()
        combined = []

        # Tag matches first (deterministic)
        for m in result.tag_matches:
            if m.question_id not in seen:
                seen.add(m.question_id)
                combined.append(m)

        # Then RAG matches (by similarity)
        for m in result.rag_matches:
            if m.question_id not in seen:
                seen.add(m.question_id)
                combined.append(m)
            else:
                # Mark as found by both methods
                for c in combined:
                    if c.question_id == m.question_id:
                        c.match_method = "both"
                        c.similarity = m.similarity
                        break

        result.combined_matches = combined
        return result


# =============================================================================
# Rules Analyzer
# =============================================================================

class RulesAnalyzer:
    """Analyzes rules using LLM for various output formats."""

    def __init__(
        self,
        rules_manager,
        llm,
        answer_comparer=None,
        verbose: bool = False
    ):
        self.rules_manager = rules_manager
        self.llm = llm
        self.answer_comparer = answer_comparer
        self.verbose = verbose

    def filter_questions_by_llm_relevance(
        self,
        topic: str,
        question_ids: List[str],
        max_questions: int = 10
    ) -> List[str]:
        """
        Use LLM to select the most relevant questions for a topic.

        Args:
            topic: The human question/topic
            question_ids: Candidate question IDs from tag matching
            max_questions: Maximum questions to return

        Returns:
            List of question IDs ranked by relevance
        """
        if len(question_ids) <= max_questions:
            return question_ids

        # Format questions for the prompt
        question_list = []
        for i, qid in enumerate(question_ids, 1):
            q = self.rules_manager.question_map.get(qid)
            if q:
                question_list.append(f"{i}. [{qid}] {q.get('question_text', qid)}")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert at matching aviation topics to relevant questions.

Your task is to select questions that would help answer or provide context for the user's topic.
Include questions that are directly relevant OR tangentially useful for understanding the topic.
When in doubt, INCLUDE the question - it's better to have more context than miss something."""),
            ("human", """USER TOPIC: {topic}

CANDIDATE QUESTIONS:
{questions}

Select up to {max_questions} questions that are relevant or useful for this topic.
Include both directly relevant questions AND questions that provide helpful context.
You should aim to select close to {max_questions} questions unless very few are relevant.

Return ONLY a JSON array of question IDs (the text in brackets), ordered by relevance.

Example: ["question-id-1", "question-id-2", "question-id-3"]

Return ONLY the JSON array, no other text.""")
        ])

        chain = prompt | self.llm

        try:
            response = chain.invoke({
                "topic": topic,
                "questions": "\n".join(question_list),
                "max_questions": max_questions
            })
            content = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            selected_ids = json.loads(content.strip())

            # Validate that returned IDs are in our list
            valid_ids = [qid for qid in selected_ids if qid in question_ids]

            if self.verbose:
                print(f"  LLM selected {len(valid_ids)} questions from {len(question_ids)}", file=sys.stderr)

            return valid_ids[:max_questions]

        except Exception as e:
            if self.verbose:
                print(f"  LLM filtering failed: {e}, using all questions", file=sys.stderr)
            return question_ids[:max_questions]

    def _format_answers_for_prompt(
        self,
        question_id: str,
        countries: Optional[List[str]] = None
    ) -> str:
        """Format all country answers for a question into prompt text."""
        q = self.rules_manager.question_map.get(question_id)
        if not q:
            return f"[Question {question_id} not found]"

        answers = q.get("answers_by_country", {})
        if countries:
            answers = {c: a for c, a in answers.items() if c in countries}

        lines = []
        for country in sorted(answers.keys()):
            answer_data = answers[country]
            answer_text = answer_data.get("answer_html", "").strip()
            if not answer_text:
                answer_text = "[No answer provided]"

            country_name = get_country_name(country)
            lines.append(f"\n{country_name} ({country}):")
            lines.append(f"  {answer_text}")

            links = answer_data.get("links", []) or answer_data.get("links_json", [])
            if links:
                lines.append(f"  Links: {', '.join(links)}")

        return "\n".join(lines)

    def analyze_video_script(
        self,
        topic: str,
        question_ids: List[str],
        countries: Optional[List[str]] = None,
        max_exceptions: int = 3
    ) -> VideoSegment:
        """
        Generate a video script segment for a topic.

        Args:
            topic: The topic/question being analyzed
            question_ids: List of relevant question IDs from rules.json
            countries: Optional filter for specific countries
            max_exceptions: Maximum number of exceptions to highlight
        """
        # Gather all answers for the questions
        all_answers_text = []
        all_countries = set()

        for qid in question_ids:
            q = self.rules_manager.question_map.get(qid)
            if not q:
                continue

            question_text = q.get("question_text", qid)
            answers_text = self._format_answers_for_prompt(qid, countries)
            all_answers_text.append(f"## {question_text}\n{answers_text}")

            answers = q.get("answers_by_country", {})
            if countries:
                all_countries.update(c for c in answers.keys() if c in countries)
            else:
                all_countries.update(answers.keys())

        combined_answers = "\n\n".join(all_answers_text)
        countries_list = sorted(list(all_countries))

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert aviation consultant creating video content for GA pilots flying in Europe.

Your task is to analyze aviation rules and produce a concise, engaging video script segment.

Key principles:
- Be conversational and clear - this is for spoken narration
- Focus on PRACTICAL differences that affect pilots
- Only report what is EXPLICITLY stated in the provided answers
- Do not add outside knowledge or assumptions"""),
            ("human", """Analyze the following topic and country-by-country answers.

TOPIC: {topic}

COUNTRY ANSWERS:
{answers}

Produce a video script segment with EXACTLY this structure:

1. TYPICAL APPROACH (2-3 sentences):
What do MOST countries do? What's the common/default behavior a pilot can expect?

2. NOTABLE EXCEPTIONS (max {max_exceptions}):
Which countries differ MEANINGFULLY from the typical approach?
For each exception, explain:
- Which country
- What's different
- Why it matters for a pilot

Only include exceptions that would actually affect a pilot's planning or operations.
Skip minor variations that don't change pilot behavior.

3. PRACTICAL TAKEAWAY (1 sentence):
One actionable piece of advice for pilots.

Format your response as JSON:
{{
    "typical_behavior": "...",
    "exceptions": [
        {{"country": "XX", "country_name": "...", "what_differs": "...", "why_it_matters": "..."}}
    ],
    "practical_takeaway": "..."
}}""")
        ])

        chain = prompt | self.llm

        try:
            response = chain.invoke({
                "topic": topic,
                "answers": combined_answers,
                "max_exceptions": max_exceptions
            })
            content = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON from response
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())

            exceptions = [
                CountryException(
                    country=e.get("country", ""),
                    country_name=e.get("country_name", ""),
                    what_differs=e.get("what_differs", ""),
                    why_it_matters=e.get("why_it_matters", "")
                )
                for e in data.get("exceptions", [])
            ]

            return VideoSegment(
                topic=topic,
                question_ids=question_ids,
                typical_behavior=data.get("typical_behavior", ""),
                exceptions=exceptions,
                practical_takeaway=data.get("practical_takeaway", ""),
                countries_analyzed=countries_list
            )

        except Exception as e:
            if self.verbose:
                print(f"  Error generating video script: {e}", file=sys.stderr)
            return VideoSegment(
                topic=topic,
                question_ids=question_ids,
                typical_behavior=f"[Error: {str(e)}]",
                exceptions=[],
                practical_takeaway="",
                countries_analyzed=countries_list
            )

    def analyze_video_script_with_embeddings(
        self,
        topic: str,
        question_ids: List[str],
        countries: Optional[List[str]] = None,
        max_exceptions: int = 3,
        min_difference: float = 0.1,
        max_questions: int = 10
    ) -> VideoSegment:
        """
        Two-stage video script generation using embedding-based pre-filtering.

        Stage 1: Use AnswerComparer to find questions where countries actually differ
        Stage 2: Send only differing questions to LLM for synthesis

        Args:
            topic: The topic being analyzed
            question_ids: List of candidate question IDs
            countries: Optional filter for specific countries (None = all)
            max_exceptions: Maximum exceptions to highlight
            min_difference: Minimum embedding difference threshold (0-1)
            max_questions: Maximum questions to analyze after filtering
        """
        if not self.answer_comparer:
            if self.verbose:
                print("  AnswerComparer not available, falling back to standard method", file=sys.stderr)
            return self.analyze_video_script(topic, question_ids, countries, max_exceptions)

        # Get all countries if not specified
        if not countries:
            all_countries = set()
            for qid in question_ids:
                q = self.rules_manager.question_map.get(qid)
                if q:
                    all_countries.update(q.get("answers_by_country", {}).keys())
            countries = sorted(list(all_countries))

        if len(countries) < 2:
            if self.verbose:
                print(f"  Need at least 2 countries, got {len(countries)}", file=sys.stderr)
            return self.analyze_video_script(topic, question_ids, countries, max_exceptions)

        # Stage 1: Find questions with actual differences using embeddings
        if self.verbose:
            print(f"  Stage 1: Finding questions with differences (threshold={min_difference})...", file=sys.stderr)

        questions_before = len(question_ids)
        differences = self.answer_comparer.find_most_different_questions(
            question_ids=question_ids,
            countries=countries,
            max_questions=max_questions,
            min_difference=min_difference
        )

        if not differences:
            if self.verbose:
                print(f"  No significant differences found, lowering threshold...", file=sys.stderr)
            # Try with lower threshold
            differences = self.answer_comparer.find_most_different_questions(
                question_ids=question_ids,
                countries=countries,
                max_questions=max_questions,
                min_difference=0.05
            )

        if not differences:
            if self.verbose:
                print(f"  Still no differences, falling back to standard method", file=sys.stderr)
            return self.analyze_video_script(topic, question_ids, countries, max_exceptions)

        questions_after = len(differences)
        if self.verbose:
            print(f"  Found {questions_after} questions with differences (from {questions_before})", file=sys.stderr)

        # Stage 2: For each differing question, find outlier countries
        if self.verbose:
            print(f"  Stage 2: Identifying outlier countries for each question...", file=sys.stderr)

        # Build focused prompt with pre-identified differences
        diff_sections = []
        for diff in differences:
            # Find outliers for this question
            outlier_result = self.answer_comparer.find_outliers_for_question(
                diff.question_id,
                countries,
                top_n=5
            )

            section_lines = [
                f"## Question: {diff.question_text}",
                f"Difference Score: {diff.difference_score:.2f} (higher = more different)",
                "",
                "Outlier countries (furthest from typical):"
            ]

            for outlier in outlier_result.outliers:
                section_lines.append(f"  - {get_country_name(outlier['country'])} ({outlier['country']}): distance={outlier['distance']:.2f}")
                answer_preview = outlier.get('answer', '')[:200]
                section_lines.append(f"    Answer: {answer_preview}...")

            section_lines.append("")
            section_lines.append("All country answers:")
            for country, answer in sorted(diff.answers.items()):
                answer_preview = answer[:150] if answer else "[No answer]"
                section_lines.append(f"  {get_country_name(country)} ({country}): {answer_preview}...")

            diff_sections.append("\n".join(section_lines))

        combined_diffs = "\n\n---\n\n".join(diff_sections)

        # Focused prompt for pre-filtered differences
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert aviation consultant creating video content for GA pilots flying in Europe.

You are given questions where country answers DIFFER significantly (pre-filtered by embedding analysis).
The "outlier countries" are those whose answers are furthest from the European norm.

Your task is to synthesize these differences into a clear, engaging video script segment.

Key principles:
- Focus on PRACTICAL differences that affect pilots
- The outlier countries with higher distance scores are more likely to be notable exceptions
- Only report what is explicitly stated in the provided answers"""),
            ("human", """Analyze the following topic and pre-identified differences between countries.

TOPIC: {topic}

PRE-IDENTIFIED DIFFERENCES (sorted by significance):
{differences}

Based on these pre-filtered differences, produce a video script segment:

1. TYPICAL APPROACH (2-3 sentences):
What do MOST countries do? What's the common behavior across Europe?

2. NOTABLE EXCEPTIONS (max {max_exceptions}):
Which countries are genuine outliers?
For each exception:
- Which country
- What's actually different (based on their answer)
- Why it matters for a pilot

Focus on the countries with highest difference scores - they're the real outliers.

3. PRACTICAL TAKEAWAY (1 sentence):
One actionable piece of advice.

Format as JSON:
{{
    "typical_behavior": "...",
    "exceptions": [
        {{"country": "XX", "country_name": "...", "what_differs": "...", "why_it_matters": "..."}}
    ],
    "practical_takeaway": "..."
}}""")
        ])

        chain = prompt | self.llm

        try:
            response = chain.invoke({
                "topic": topic,
                "differences": combined_diffs,
                "max_exceptions": max_exceptions
            })
            content = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())

            exceptions = [
                CountryException(
                    country=e.get("country", ""),
                    country_name=e.get("country_name", ""),
                    what_differs=e.get("what_differs", ""),
                    why_it_matters=e.get("why_it_matters", "")
                )
                for e in data.get("exceptions", [])
            ]

            return VideoSegment(
                topic=topic,
                question_ids=[d.question_id for d in differences],
                typical_behavior=data.get("typical_behavior", ""),
                exceptions=exceptions,
                practical_takeaway=data.get("practical_takeaway", ""),
                countries_analyzed=countries,
                method="embedding",
                questions_before_filter=questions_before,
                questions_after_filter=questions_after,
                min_difference_threshold=min_difference
            )

        except Exception as e:
            if self.verbose:
                print(f"  Error generating video script: {e}", file=sys.stderr)
            return VideoSegment(
                topic=topic,
                question_ids=question_ids,
                typical_behavior=f"[Error: {str(e)}]",
                exceptions=[],
                practical_takeaway="",
                countries_analyzed=countries,
                method="embedding",
                questions_before_filter=questions_before,
                questions_after_filter=questions_after,
                min_difference_threshold=min_difference
            )

    def analyze_cross_country(
        self,
        question_id: str,
        countries: Optional[List[str]] = None
    ) -> CrossCountrySummary:
        """
        Generate comprehensive cross-country analysis for a question.
        """
        q = self.rules_manager.question_map.get(question_id)
        if not q:
            return CrossCountrySummary(
                question_id=question_id,
                question_text=question_id,
                category="",
                tags=[],
                common_practices="[Question not found]",
                key_differences="",
                country_specific="",
                cross_border_advice="",
                countries_analyzed=[]
            )

        question_text = q.get("question_text", question_id)
        answers_text = self._format_answers_for_prompt(question_id, countries)

        answers = q.get("answers_by_country", {})
        if countries:
            countries_list = [c for c in sorted(answers.keys()) if c in countries]
        else:
            countries_list = sorted(answers.keys())

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert aviation consultant helping general aviation pilots in Europe.

Your task is to analyze aviation rules across multiple countries. Focus on:
1. What is COMMON across countries (universal practices)
2. DIFFERENCES and country-specific requirements
3. PRACTICAL advice for pilots crossing borders

IMPORTANT: Only report information explicitly stated in the provided answers.
Do not add outside knowledge or assumptions."""),
            ("human", """Analyze this question and all country answers:

Question: {question}
Category: {category}
Tags: {tags}

Answers by Country:
{answers}

Provide a structured analysis:

1. **Common Practices**: What is common across most/all countries?

2. **Key Differences**: Significant variations between countries?

3. **Country-Specific Requirements**: Any countries with unique requirements?

4. **Cross-Border Advice**: Practical advice for pilots flying across borders?

Be concise and actionable.""")
        ])

        chain = prompt | self.llm

        try:
            response = chain.invoke({
                "question": question_text,
                "category": q.get("category", ""),
                "tags": ", ".join(q.get("tags", [])),
                "answers": answers_text
            })
            content = response.content if hasattr(response, 'content') else str(response)

            # Parse sections from response
            sections = {
                "common_practices": "",
                "key_differences": "",
                "country_specific": "",
                "cross_border_advice": ""
            }

            # Simple parsing - look for headers
            current_section = None
            current_lines = []

            for line in content.split("\n"):
                line_lower = line.lower()
                if "common practice" in line_lower:
                    if current_section:
                        sections[current_section] = "\n".join(current_lines).strip()
                    current_section = "common_practices"
                    current_lines = []
                elif "key difference" in line_lower:
                    if current_section:
                        sections[current_section] = "\n".join(current_lines).strip()
                    current_section = "key_differences"
                    current_lines = []
                elif "country-specific" in line_lower or "country specific" in line_lower:
                    if current_section:
                        sections[current_section] = "\n".join(current_lines).strip()
                    current_section = "country_specific"
                    current_lines = []
                elif "cross-border" in line_lower or "cross border" in line_lower:
                    if current_section:
                        sections[current_section] = "\n".join(current_lines).strip()
                    current_section = "cross_border_advice"
                    current_lines = []
                elif current_section:
                    current_lines.append(line)

            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()

            return CrossCountrySummary(
                question_id=question_id,
                question_text=question_text,
                category=q.get("category", ""),
                tags=q.get("tags", []),
                common_practices=sections["common_practices"],
                key_differences=sections["key_differences"],
                country_specific=sections["country_specific"],
                cross_border_advice=sections["cross_border_advice"],
                countries_analyzed=countries_list
            )

        except Exception as e:
            if self.verbose:
                print(f"  Error generating analysis: {e}", file=sys.stderr)
            return CrossCountrySummary(
                question_id=question_id,
                question_text=question_text,
                category=q.get("category", ""),
                tags=q.get("tags", []),
                common_practices=f"[Error: {str(e)}]",
                key_differences="",
                country_specific="",
                cross_border_advice="",
                countries_analyzed=countries_list
            )


# =============================================================================
# Output Formatters
# =============================================================================

def format_identification_result(result: IdentificationResult) -> str:
    """Format identification result as readable text."""
    lines = [
        f"# Question Identification: {result.topic}",
        f"Method: {result.method}",
        ""
    ]

    if result.inferred_tags:
        lines.append(f"Inferred tags: {', '.join(result.inferred_tags)}")
        lines.append("")

    if result.method in ("tag", "both") and result.tag_matches:
        lines.append(f"## Tag Matches ({len(result.tag_matches)})")
        for m in result.tag_matches:
            lines.append(f"- [{m.category}] {m.question_text[:80]}...")
            lines.append(f"  Tags: {', '.join(m.tags)}")
        lines.append("")

    if result.method in ("rag", "both") and result.rag_matches:
        lines.append(f"## RAG Matches ({len(result.rag_matches)})")
        for m in result.rag_matches:
            sim = f" (sim: {m.similarity:.3f})" if m.similarity else ""
            lines.append(f"- [{m.category}] {m.question_text[:80]}...{sim}")
        lines.append("")

    if result.combined_matches:
        lines.append(f"## Combined Matches ({len(result.combined_matches)})")
        for m in result.combined_matches:
            method_note = f" [{m.match_method}]" if result.method == "both" else ""
            sim = f" (sim: {m.similarity:.3f})" if m.similarity else ""
            lines.append(f"- {m.question_text[:80]}...{method_note}{sim}")

    return "\n".join(lines)


def format_video_segment_markdown(segment: VideoSegment) -> str:
    """Format video segment as markdown."""
    lines = [
        f"# {segment.topic}",
        "",
        f"**Questions analyzed:** {len(segment.question_ids)}",
        f"**Countries:** {', '.join(segment.countries_analyzed)}",
        "",
        "---",
        "",
        "## Typical Approach",
        "",
        segment.typical_behavior,
        "",
    ]

    if segment.exceptions:
        lines.append("## Notable Exceptions")
        lines.append("")
        for exc in segment.exceptions:
            lines.append(f"### {exc.country_name} ({exc.country})")
            lines.append(f"**What's different:** {exc.what_differs}")
            lines.append(f"**Why it matters:** {exc.why_it_matters}")
            lines.append("")

    lines.append("## Practical Takeaway")
    lines.append("")
    lines.append(f"_{segment.practical_takeaway}_")

    return "\n".join(lines)


def format_video_segment_script(segment: VideoSegment) -> str:
    """Format video segment as spoken script."""
    lines = [
        f"[TOPIC: {segment.topic}]",
        "",
        segment.typical_behavior,
        "",
    ]

    if segment.exceptions:
        lines.append("However, there are some notable exceptions you should know about:")
        lines.append("")
        for exc in segment.exceptions:
            # Use the what_differs directly since it should be a complete sentence
            what_differs = exc.what_differs.strip() if exc.what_differs else ""
            # Capitalize first letter if needed
            if what_differs and what_differs[0].islower():
                what_differs = what_differs[0].upper() + what_differs[1:]

            lines.append(f"In {exc.country_name}: {what_differs}")
            if exc.why_it_matters:
                why = exc.why_it_matters.strip()
                if why and why[0].islower():
                    why = why[0].upper() + why[1:]
                lines.append(f"Why this matters: {why}")
            lines.append("")

    lines.append(f"So remember: {segment.practical_takeaway}")

    return "\n".join(lines)


# =============================================================================
# Topic File Parser
# =============================================================================

def parse_topics_file(file_path: Path) -> List[str]:
    """Parse topics from a file (one per line, supports numbered lists)."""
    topics = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Remove leading numbers like "1)" or "1." or "1:"
            line = re.sub(r'^\d+[\)\.\:]\s*', '', line)
            if line:
                topics.append(line)
    return topics


# =============================================================================
# Main CLI
# =============================================================================

def cmd_identify(args, rules_manager, rules_rag):
    """Run identify command."""
    identifier = QuestionIdentifier(
        rules_manager=rules_manager,
        rules_rag=rules_rag,
        verbose=args.verbose
    )

    topics = []
    if args.topic:
        topics = [args.topic]
    elif args.topics_file:
        topics = parse_topics_file(args.topics_file)

    if not topics:
        print("No topics provided. Use --topic or --topics-file", file=sys.stderr)
        return

    output_dir = args.output_dir or (project_root / "tmp" / "analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, topic in enumerate(topics, 1):
        print(f"[{i}/{len(topics)}] Identifying: {topic[:60]}...", file=sys.stderr)

        result = identifier.identify(
            topic=topic,
            method=args.method,
            top_k=args.top_k
        )

        # Output
        text_output = format_identification_result(result)
        print(text_output)
        print()

        # Save to file
        safe_name = re.sub(r'[^\w\s-]', '', topic)[:50].strip().replace(' ', '_').lower()
        json_file = output_dir / f"identify_{safe_name}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "topic": result.topic,
                "method": result.method,
                "inferred_tags": result.inferred_tags,
                "tag_matches": [asdict(m) for m in result.tag_matches],
                "rag_matches": [asdict(m) for m in result.rag_matches],
                "combined_matches": [asdict(m) for m in result.combined_matches]
            }, f, indent=2, ensure_ascii=False)
        print(f"  Saved to {json_file}", file=sys.stderr)


def cmd_video_script(args, rules_manager, rules_rag, llm):
    """Run video-script command."""
    identifier = QuestionIdentifier(
        rules_manager=rules_manager,
        rules_rag=rules_rag,
        verbose=args.verbose
    )

    analyzer = RulesAnalyzer(
        rules_manager=rules_manager,
        llm=llm,
        verbose=args.verbose
    )

    topics = []
    if args.topic:
        topics = [args.topic]
    elif args.topics_file:
        topics = parse_topics_file(args.topics_file)

    if not topics:
        print("No topics provided. Use --topic or --topics-file", file=sys.stderr)
        return

    output_dir = args.output_dir or (project_root / "tmp" / "video_scripts")
    output_dir.mkdir(parents=True, exist_ok=True)

    all_segments = []
    filter_method = getattr(args, 'filter_method', 'none')
    max_questions = getattr(args, 'max_questions', 10)

    for i, topic in enumerate(topics, 1):
        print(f"[{i}/{len(topics)}] Processing: {topic[:60]}...", file=sys.stderr)

        # Extract countries mentioned in topic
        topic_countries = extract_countries_from_topic(topic)
        if args.verbose and topic_countries:
            print(f"  Countries in topic: {topic_countries}", file=sys.stderr)

        # Step 1: Identify relevant questions (tag matching)
        print(f"  Identifying questions ({args.method})...", file=sys.stderr)
        id_result = identifier.identify(
            topic=topic,
            method=args.method,
            top_k=args.top_k
        )

        question_ids = [m.question_id for m in id_result.combined_matches]

        if not question_ids:
            print(f"  No matching questions found, skipping", file=sys.stderr)
            continue

        original_count = len(question_ids)
        print(f"  Found {original_count} questions", file=sys.stderr)

        # Step 2: Filter questions by relevance (if filter method specified)
        if filter_method == "llm" and len(question_ids) > max_questions:
            print(f"  Filtering by LLM relevance (max {max_questions})...", file=sys.stderr)
            question_ids = analyzer.filter_questions_by_llm_relevance(
                topic=topic,
                question_ids=question_ids,
                max_questions=max_questions
            )
        elif filter_method == "rag" and len(question_ids) > max_questions:
            print(f"  Filtering by RAG similarity (max {max_questions})...", file=sys.stderr)
            question_ids = identifier.filter_by_rag_similarity(
                topic=topic,
                question_ids=question_ids,
                max_questions=max_questions
            )

        # Step 3: Generate video script
        print(f"  Generating video script ({len(question_ids)} questions)...", file=sys.stderr)
        segment = analyzer.analyze_video_script(
            topic=topic,
            question_ids=question_ids,
            countries=topic_countries if topic_countries else None,
            max_exceptions=args.max_exceptions
        )
        # Store filter metadata
        segment.method = filter_method if filter_method != "none" else "keyword"
        segment.questions_before_filter = original_count
        segment.questions_after_filter = len(question_ids)

        all_segments.append(segment)

        # Save individual file
        safe_name = re.sub(r'[^\w\s-]', '', topic)[:50].strip().replace(' ', '_').lower()

        # Markdown version
        md_file = output_dir / f"video_{safe_name}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(format_video_segment_markdown(segment))

        # Script version (spoken)
        script_file = output_dir / f"script_{safe_name}.txt"
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(format_video_segment_script(segment))

        # JSON version
        json_file = output_dir / f"video_{safe_name}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "topic": segment.topic,
                "question_ids": segment.question_ids,
                "typical_behavior": segment.typical_behavior,
                "exceptions": [asdict(e) for e in segment.exceptions],
                "practical_takeaway": segment.practical_takeaway,
                "countries_analyzed": segment.countries_analyzed,
                "identification": {
                    "method": id_result.method,
                    "inferred_tags": id_result.inferred_tags,
                    "matches": [asdict(m) for m in id_result.combined_matches]
                }
            }, f, indent=2, ensure_ascii=False)

        print(f"  Saved: {md_file.name}, {script_file.name}, {json_file.name}", file=sys.stderr)

    # Save combined output
    if len(all_segments) > 1:
        # Create combined output directory
        combined_dir = output_dir / "combined"
        combined_dir.mkdir(parents=True, exist_ok=True)

        # Generate run name based on method and model
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Method name for file
        if filter_method == "llm":
            method_name = "llm_filter"
        elif filter_method == "rag":
            method_name = "rag_filter"
        else:
            method_name = "no_filter"
        model_name = args.model.replace("-", "").replace(".", "")

        # Find next run number
        all_runs = list(combined_dir.glob("run_*.md"))
        if all_runs:
            run_nums = [int(r.stem.split("_")[1]) for r in all_runs if r.stem.split("_")[1].isdigit()]
            run_num = max(run_nums) + 1 if run_nums else 1
        else:
            run_num = 1

        combined_file = combined_dir / f"run_{run_num:02d}_{method_name}_{model_name}.md"

        with open(combined_file, "w", encoding="utf-8") as f:
            # Write configuration header
            f.write(f"# Video Script Analysis - Run {run_num:02d}\n\n")
            f.write("## Configuration\n")
            f.write(f"- **Date**: {date_str}\n")
            f.write(f"- **Model**: {args.model}\n")
            if filter_method == "llm":
                f.write(f"- **Method**: LLM-based question relevance filtering\n")
                f.write(f"- **Question Identification**: Tag matching → LLM picks most relevant\n")
                f.write(f"- **Max Questions**: {max_questions}\n")
            elif filter_method == "rag":
                f.write(f"- **Method**: RAG-based question relevance filtering\n")
                f.write(f"- **Question Identification**: Tag matching → RAG ranks by similarity\n")
                f.write(f"- **Max Questions**: {max_questions}\n")
            else:
                f.write(f"- **Method**: No filtering (all tag-matched questions)\n")
                f.write(f"- **Question Identification**: Tag matching (keyword → tag mapping)\n")
            f.write(f"- **Topics File**: {args.topics_file}\n\n")

            f.write("## Approach Summary\n")
            if filter_method == "llm":
                f.write("1. Topic → Keywords → Inferred tags\n")
                f.write("2. All questions matching any inferred tag identified\n")
                f.write("3. LLM selects most relevant questions for the topic\n")
                f.write("4. Selected questions + all country answers sent to LLM\n")
                f.write("5. LLM determines typical behavior + exceptions\n\n")
            elif filter_method == "rag":
                f.write("1. Topic → Keywords → Inferred tags\n")
                f.write("2. All questions matching any inferred tag identified\n")
                f.write("3. RAG ranks questions by embedding similarity to topic\n")
                f.write("4. Top questions + all country answers sent to LLM\n")
                f.write("5. LLM determines typical behavior + exceptions\n\n")
            else:
                f.write("1. Topic → Keywords → Inferred tags\n")
                f.write("2. All questions matching any inferred tag included\n")
                f.write("3. All country answers sent to LLM\n")
                f.write("4. LLM determines typical behavior + exceptions\n\n")

            f.write("## Results\n")

            for segment in all_segments:
                f.write(format_video_segment_markdown(segment))
                f.write("\n\n---\n\n")

        # Also keep a simple all_scripts.md for quick access
        simple_combined = output_dir / "all_scripts.md"
        with open(simple_combined, "w", encoding="utf-8") as f:
            for segment in all_segments:
                f.write(format_video_segment_markdown(segment))
                f.write("\n\n---\n\n")

        print(f"\nCombined output: {combined_file}", file=sys.stderr)
        print(f"Simple output: {simple_combined}", file=sys.stderr)


def cmd_cross_country(args, rules_manager, llm):
    """Run cross-country-summary command."""
    analyzer = RulesAnalyzer(
        rules_manager=rules_manager,
        llm=llm,
        verbose=args.verbose
    )

    output_dir = args.output_dir or (project_root / "tmp" / "analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get questions to analyze
    if args.question_id:
        question_ids = [args.question_id]
    elif args.category:
        question_ids = rules_manager.get_questions_by_category(args.category)
    elif args.tag:
        question_ids = rules_manager.get_questions_by_tag(args.tag)
    else:
        # All questions
        question_ids = list(rules_manager.question_map.keys())

    if not question_ids:
        print("No questions found", file=sys.stderr)
        return

    print(f"Analyzing {len(question_ids)} questions...", file=sys.stderr)

    for i, qid in enumerate(question_ids, 1):
        q = rules_manager.question_map.get(qid, {})
        print(f"[{i}/{len(question_ids)}] {q.get('question_text', qid)[:60]}...", file=sys.stderr)

        summary = analyzer.analyze_cross_country(qid)

        # Save output
        safe_name = re.sub(r'[^\w\s-]', '', qid)[:50].strip().replace(' ', '_').lower()

        md_file = output_dir / f"summary_{safe_name}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# {summary.question_text}\n\n")
            f.write(f"**Category:** {summary.category}\n")
            f.write(f"**Tags:** {', '.join(summary.tags)}\n")
            f.write(f"**Countries:** {', '.join(summary.countries_analyzed)}\n\n")
            f.write("---\n\n")
            f.write("## Common Practices\n\n")
            f.write(summary.common_practices + "\n\n")
            f.write("## Key Differences\n\n")
            f.write(summary.key_differences + "\n\n")
            f.write("## Country-Specific Requirements\n\n")
            f.write(summary.country_specific + "\n\n")
            f.write("## Cross-Border Advice\n\n")
            f.write(summary.cross_border_advice + "\n")

        print(f"  Saved: {md_file.name}", file=sys.stderr)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze aviation rules using LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Global options
    parser.add_argument("--rules-json", type=Path, default=None,
                       help="Path to rules.json (default: data/rules.json)")
    parser.add_argument("--vector-db", type=Path, default=None,
                       help="Path to vector DB for RAG (default: cache/rules_vector_db)")
    parser.add_argument("--model", type=str, default="gpt-4o-mini",
                       help="LLM model (default: gpt-4o-mini)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # identify command
    identify_parser = subparsers.add_parser("identify",
        help="Identify questions relevant to a topic")
    identify_parser.add_argument("topic", nargs="?", help="Topic to search for")
    identify_parser.add_argument("--topics-file", type=Path,
                                help="File with topics (one per line)")
    identify_parser.add_argument("--method", choices=["tag", "rag", "both"],
                                default="both", help="Identification method")
    identify_parser.add_argument("--top-k", type=int, default=5,
                                help="Number of RAG results")
    identify_parser.add_argument("--output-dir", type=Path,
                                help="Output directory")

    # video-script command
    video_parser = subparsers.add_parser("video-script",
        help="Generate video script segments")
    video_parser.add_argument("topic", nargs="?", help="Topic to analyze")
    video_parser.add_argument("--topics-file", type=Path,
                             help="File with topics (one per line)")
    video_parser.add_argument("--method", choices=["tag", "rag", "both"],
                             default="both", help="Question identification method")
    video_parser.add_argument("--top-k", type=int, default=5,
                             help="Number of RAG results")
    video_parser.add_argument("--max-exceptions", type=int, default=3,
                             help="Max exceptions to highlight")
    video_parser.add_argument("--output-dir", type=Path,
                             help="Output directory")
    video_parser.add_argument("--filter-method", choices=["none", "llm", "rag"],
                             default="none",
                             help="Question relevance filtering: none (all tags), llm (LLM picks), rag (embedding similarity)")
    video_parser.add_argument("--max-questions", type=int, default=10,
                             help="Max questions after filtering (default: 10)")

    # cross-country-summary command
    summary_parser = subparsers.add_parser("cross-country-summary",
        help="Generate comprehensive cross-country analysis")
    summary_parser.add_argument("--question-id", type=str,
                               help="Specific question ID to analyze")
    summary_parser.add_argument("--category", type=str,
                               help="Analyze all questions in category")
    summary_parser.add_argument("--tag", type=str,
                               help="Analyze all questions with tag")
    summary_parser.add_argument("--output-dir", type=Path,
                               help="Output directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Resolve paths
    rules_json_path = args.rules_json or (project_root / "data" / "rules.json")
    vector_db_path = args.vector_db or (project_root / "cache" / "rules_vector_db")

    if not rules_json_path.exists():
        print(f"Error: rules.json not found at {rules_json_path}", file=sys.stderr)
        sys.exit(1)

    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable required", file=sys.stderr)
        sys.exit(1)

    # Initialize components
    print(f"Loading rules from {rules_json_path}...", file=sys.stderr)

    from shared.rules_manager import RulesManager
    rules_manager = RulesManager(str(rules_json_path))
    rules_manager.load_rules()

    print(f"Loaded {len(rules_manager.question_map)} questions", file=sys.stderr)

    # Initialize RAG if available
    rules_rag = None
    if args.command in ("identify", "video-script"):
        if vector_db_path.exists():
            try:
                from shared.aviation_agent.rules_rag import RulesRAG
                rules_rag = RulesRAG(
                    vector_db_path=str(vector_db_path),
                    rules_manager=rules_manager,
                    enable_reformulation=False  # Keep it simple for now
                )
                print(f"RAG initialized from {vector_db_path}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Could not initialize RAG: {e}", file=sys.stderr)
        else:
            print(f"Warning: Vector DB not found at {vector_db_path}, RAG disabled", file=sys.stderr)

    # Initialize LLM
    llm = None
    if args.command in ("video-script", "cross-country-summary"):
        llm = ChatOpenAI(model=args.model, temperature=0.0)
        print(f"Using LLM: {args.model}", file=sys.stderr)

    print("", file=sys.stderr)

    # Run command
    if args.command == "identify":
        cmd_identify(args, rules_manager, rules_rag)
    elif args.command == "video-script":
        cmd_video_script(args, rules_manager, rules_rag, llm)
    elif args.command == "cross-country-summary":
        cmd_cross_country(args, rules_manager, llm)


if __name__ == "__main__":
    main()
