# GA Friendliness Implementation Plan

This document defines the **implementation architecture, module structure, and function signatures** for the GA friendliness enrichment system. This is a planning document; function bodies will be implemented after review and iteration.

---

## 1. Library Structure & Organization

### 1.1 Decision: Standalone Library vs. Shared Module

**Choice:** Create a new standalone Python library `ga_friendliness` that can be used independently or integrated into the flyfun-apps ecosystem.

**Rationale:**
- **Pros:**
  - Clean separation of concerns (follows design principle)
  - Can be shared/reused by other projects
  - Easier to version and test independently
  - Clear dependency boundaries
- **Cons:**
  - Slightly more complex import paths
  - Need to manage dependencies carefully

**Location:** `shared/ga_friendliness/` (following the pattern of `shared/filtering/`, `shared/prioritization/`)

**Alternative Considered:** Separate package in `src/ga-friendliness/` (like `src/euro-aip/`)
- **Rejected because:** We want tight integration with flyfun-apps tooling and shared utilities, while still maintaining logical separation.

### 1.2 Module Structure

```
shared/ga_friendliness/
├── __init__.py                 # Public API exports
├── config.py                   # Configuration loading (JSON, env vars)
├── models.py                   # Pydantic models for ontology, personas, reviews
├── exceptions.py               # Exception hierarchy
├── database.py                 # SQLite schema creation, connection management, migrations
├── storage.py                  # Read/write operations for ga_meta.sqlite
├── ontology.py                 # Ontology loading, validation, aspect/label lookup
├── personas.py                 # Persona loading, validation, score computation
├── cache.py                    # Caching utility for remote data sources
├── nlp/
│   ├── __init__.py
│   ├── extractor.py           # LLM-based review tag extraction
│   ├── aggregator.py           # Tag aggregation → feature scores
│   ├── summarizer.py           # LLM-based airport summary generation
│   └── aip_rule_extractor.py   # LLM-based AIP rule parsing (notification, handling, etc.)
├── aip/
│   ├── __init__.py
│   ├── aip_source.py           # Source for AIP data from euro_aip.sqlite
│   ├── rule_parser.py          # Parse structured rules from AIP text
│   └── rule_summarizer.py      # Generate high-level summaries from detailed rules
├── features.py                 # Feature engineering (label distributions → scores)
├── scoring.py                  # Persona-based scoring functions
└── builder.py                  # Main pipeline orchestrator

tools/
└── build_ga_friendliness.py    # CLI tool for rebuilding ga_meta.sqlite

data/
├── ontology.json               # Ontology definition (versioned)
├── personas.json               # Persona definitions (versioned)
├── feature_mappings.json       # Feature mapping configurations (versioned)
└── aip_rule_schema.json       # Schema for AIP rule extraction (notification patterns, etc.)
```

---

## 2. AIP Rule Parsing Extension

### 2.1 Overview

**Goal:** Parse structured rules from euro_aip database (notification requirements, handling rules, etc.) into detailed structured data and high-level summaries for scoring.

**Key Requirements:**
- Parse complex notification rules (weekday-specific, time-based, conditional)
- Store detailed breakdown for operational use
- Generate high-level summary for scoring
- Separate NLP pipeline (different from review extraction)
- Support incremental updates
- Optional feature (works with or without euro_aip)

**Design Principles:**
- **Separation:** AIP parsing is separate module, optional step in pipeline
- **Two-stage processing:** Extract details → Summarize for scoring
- **Incremental:** Track processed AIP entries, only reparse changed ones
- **Extensible:** Can add other AIP rule types (handling, customs, etc.)

### 2.2 Module Structure

```
shared/ga_friendliness/aip/
├── __init__.py
├── aip_source.py           # Load AIP text from euro_aip.sqlite
├── rule_parser.py          # Parse structured rules using LLM
└── rule_summarizer.py      # Generate high-level summaries
```

### 2.3 Database Schema Extensions

**New Table: `ga_notification_requirements`**

```sql
CREATE TABLE ga_notification_requirements (
    id                  INTEGER PRIMARY KEY,
    icao                TEXT NOT NULL,
    rule_type           TEXT NOT NULL,  -- 'ppr', 'pn', 'customs_notification', 'handling_ppr'
    weekday_start       INTEGER,         -- 0=Monday, 6=Sunday, NULL=all days
    weekday_end         INTEGER,         -- NULL=single day, or end of range (inclusive)
    notification_hours  INTEGER,         -- Hours before flight (24, 48, etc.), NULL if not hours-based
    notification_type   TEXT NOT NULL,  -- 'hours', 'business_day', 'specific_time', 'on_request', 'h24'
    specific_time        TEXT,           -- e.g., "1300" for "before 1300", NULL if not applicable
    business_day_offset  INTEGER,        -- e.g., -1 for "last business day before", NULL if not applicable
    is_obligatory        INTEGER,        -- 0/1, whether notification is mandatory
    conditions_json     TEXT,            -- JSON for complex conditions (holidays, seasons, etc.)
    raw_text             TEXT,            -- Original AIP text this rule was extracted from
    source_field         TEXT,            -- Which AIP field this came from
    source_section       TEXT,            -- Which AIP section (customs, handling, etc.)
    source_std_field_id   INTEGER,        -- euro_aip std_field_id (e.g., 302 for customs)
    aip_entry_id         TEXT,            -- Reference to euro_aip entry (if available)
    confidence           REAL,            -- LLM extraction confidence [0, 1]
    created_utc          TEXT,
    updated_utc           TEXT
);

CREATE INDEX idx_notification_icao ON ga_notification_requirements(icao);
CREATE INDEX idx_notification_type ON ga_notification_requirements(icao, rule_type);
CREATE INDEX idx_notification_weekday ON ga_notification_requirements(icao, weekday_start, weekday_end);
```

**Examples of stored rules:**

For text: "PPR 24 HR weekdays, 48 HR weekends"
- Row 1: `rule_type='ppr'`, `weekday_start=0`, `weekday_end=4`, `notification_hours=24`, `notification_type='hours'`
- Row 2: `rule_type='ppr'`, `weekday_start=5`, `weekday_end=6`, `notification_hours=48`, `notification_type='hours'`

For text: "Last business day before 1300"
- Row: `rule_type='ppr'`, `weekday_start=NULL`, `weekday_end=NULL`, `notification_type='business_day'`, `business_day_offset=-1`, `specific_time='1300'`

For text: "Tue-Fri: 24h, Sat-Mon: 48h"
- Row 1: `rule_type='ppr'`, `weekday_start=1`, `weekday_end=4`, `notification_hours=24`
- Row 2: `rule_type='ppr'`, `weekday_start=5`, `weekday_end=0`, `notification_hours=48` (Sat-Mon wraps)

**New Table: `ga_aip_rule_summary`**

```sql
CREATE TABLE ga_aip_rule_summary (
    icao                TEXT PRIMARY KEY,
    notification_summary TEXT,     -- High-level summary: "24h weekdays, 48h weekends"
    hassle_level        TEXT,      -- 'low', 'moderate', 'high', 'very_high'
    notification_score  REAL,      -- Normalized score [0, 1] for scoring
    last_updated_utc    TEXT
);
```

**Update `ga_airfield_stats`:**

Add column:
```sql
ALTER TABLE ga_airfield_stats ADD COLUMN notification_hassle_score REAL;
-- Derived from ga_aip_rule_summary.notification_score
```

### 2.4 AIP Source (`aip/aip_source.py`)

```python
# aip/aip_source.py - Load AIP text from euro_aip.sqlite

class AIPSource:
    """
    Loads AIP text data from euro_aip.sqlite for rule parsing.
    
    Extracts relevant fields:
        - Customs/immigration notification requirements
        - Handling/PPR requirements
        - Other structured rules
    """
    
    def __init__(self, euro_aip_path: Path):
        """
        Initialize AIP source.
        
        Args:
            euro_aip_path: Path to euro_aip.sqlite
        """
        # Store path
        # Validate database exists
    
    def get_airport_aip_text(self, icao: str) -> Optional[Dict[str, str]]:
        """
        Get AIP text fields for an airport.
        
        Queries euro_aip.sqlite for relevant sections:
            - Customs/immigration (section='customs')
            - Handling (section='handling')
            - Other relevant sections
        
        Returns:
            Dict mapping section -> field -> text value
            Example:
                {
                    'customs': {
                        'notification': 'PPR 24 HR weekdays, 48 HR weekends',
                        'availability': 'H24'
                    },
                    'handling': {
                        'ppr_required': 'PPR 2 HR',
                        'services': 'Available on PPR'
                    }
                }
        """
        # ATTACH euro_aip.sqlite
        # Query aip_entries table for airport
        # Filter by relevant sections (customs, handling)
        # Group by section and field
        # Return structured dict
    
    def get_all_airports(self) -> List[str]:
        """Get list of all ICAOs in euro_aip.sqlite."""
        # Query euro_aip for distinct ICAOs
        # Return list
    
    def get_last_aip_change_timestamp(self, icao: str) -> Optional[datetime]:
        """
        Get when AIP data was last changed for this airport.
        
        Queries euro_aip change tracking tables.
        
        Returns:
            Timestamp of last change, or None if not found.
        """
        # Query aip_entries_changes for max(changed_at)
        # Return datetime or None
```

### 2.5 AIP Rule Parser (`aip/rule_parser.py`)

**Design Decision: LLM vs. Regex for Rule Parsing**

- **Option A:** Use regex patterns (like euro_aip's CustomInterpreter)
  - **Pros:** Fast, deterministic, no LLM costs
  - **Cons:** Hard to handle complex/ambiguous rules, brittle
- **Option B:** Use LLM for rule extraction
  - **Pros:** Handles complex rules, natural language variations, extensible
  - **Cons:** LLM costs, potential inconsistencies
- **Choice:** Option B (LLM) for flexibility, but can fall back to regex for simple cases

**Hybrid Approach:**
- Try regex patterns first (fast path for common patterns)
- Fall back to LLM for complex/ambiguous cases
- Cache LLM results to avoid reprocessing

```python
# aip/rule_parser.py - Parse structured rules from AIP text

from typing import List, Optional
from pydantic import BaseModel

class NotificationRule(BaseModel):
    """Structured representation of a notification requirement."""
    rule_type: str  # 'ppr', 'pn', 'customs_notification'
    weekday_start: Optional[int] = None  # 0=Monday, 6=Sunday
    weekday_end: Optional[int] = None  # For ranges
    notification_hours: Optional[int] = None  # Hours before (24, 48, etc.)
    notification_type: str  # 'hours', 'business_day', 'specific_time'
    specific_time: Optional[str] = None  # e.g., "1300"
    business_day_offset: Optional[int] = None  # e.g., -1 for "last business day"
    conditions: Optional[Dict] = None  # Additional conditions

class ParsedAIPRules(BaseModel):
    """Complete parsed rules for an airport."""
    icao: str
    notification_rules: List[NotificationRule]
    handling_rules: List[Dict]  # Future: handling-specific rules
    source_fields: Dict[str, str]  # Map rule -> source field text

class AIPRuleParser:
    """
    Parses structured rules from AIP text using LLM.
    
    Uses specialized prompt for rule extraction (different from review extraction).
    Handles complex patterns:
        - "PPR 24 HR weekdays, 48 HR weekends"
        - "Last business day before 1300"
        - "Tue-Fri: 24h, Sat-Mon: 48h"
    """
    
    def __init__(
        self,
        llm_model: str,
        llm_temperature: float = 0.0,
        api_key: Optional[str] = None,
        max_retries: int = 3
    ):
        """
        Initialize rule parser with LLM.
        
        Creates LangChain chain for structured rule extraction.
        """
        # Build prompt template for rule extraction
        # Create ChatOpenAI instance
        # Create PydanticOutputParser for ParsedAIPRules
        # Chain: prompt | llm | parser
        # Initialize token usage tracking
    
    def parse_rules(self, icao: str, aip_text: Dict[str, str]) -> ParsedAIPRules:
        """
        Parse rules from AIP text.
        
        Uses hybrid approach:
            1. Try regex patterns for common cases (fast path)
            2. Fall back to LLM for complex/ambiguous rules
        
        Args:
            icao: Airport ICAO code
            aip_text: Dict of section -> field -> text (from AIPSource)
            Example:
                {
                    'customs': {
                        'notification': 'PPR 24 HR weekdays, 48 HR weekends',
                        'availability': 'H24'
                    }
                }
        
        Returns:
            ParsedAIPRules with structured notification and handling rules
        
        Raises:
            AIPRuleParsingError if parsing fails
        """
        notification_rules = []
        
        # Extract notification rules from each section
        for section, fields in aip_text.items():
            for field_name, field_text in fields.items():
                # Try regex patterns first (common cases)
                regex_rules = self._try_regex_extraction(field_text, section, field_name)
                if regex_rules:
                    notification_rules.extend(regex_rules)
                else:
                    # Fall back to LLM for complex cases
                    llm_rules = self._llm_extract_rules(icao, field_text, section, field_name)
                    notification_rules.extend(llm_rules)
        
        return ParsedAIPRules(
            icao=icao,
            notification_rules=notification_rules,
            handling_rules=[],  # Future: parse handling rules
            source_fields={rule.source_field: aip_text.get(rule.source_section, {}).get(rule.source_field, '')
                          for rule in notification_rules}
        )
    
    def _try_regex_extraction(
        self,
        text: str,
        section: str,
        field_name: str
    ) -> List[NotificationRule]:
        """
        Try to extract rules using regex patterns (fast path).
        
        Handles common patterns:
            - "PPR 24 HR"
            - "PPR 24 HR weekdays, 48 HR weekends"
            - "H24"
            - "O/R"
        
        Returns:
            List of NotificationRule if patterns match, empty list otherwise
        """
        # Use regex patterns similar to euro_aip CustomInterpreter
        # Extract weekday/weekend patterns
        # Return structured rules or empty list
    
    def _llm_extract_rules(
        self,
        icao: str,
        text: str,
        section: str,
        field_name: str
    ) -> List[NotificationRule]:
        """
        Extract rules using LLM (for complex/ambiguous cases).
        
        Prompt includes:
            - Example patterns and expected output
            - Schema for NotificationRule
            - Instructions to handle:
                - Weekday ranges (Mon-Fri, Tue-Thu, etc.)
                - Business day requirements
                - Specific times
                - Conditional rules (holidays, seasons)
        """
        # Build prompt with text and examples
        # Invoke LLM chain
        # Parse structured output
        # Track token usage
        # Return list of NotificationRule
```

### 2.6 Rule Summarizer (`aip/rule_summarizer.py`)

**Purpose:** Convert detailed structured rules into:
1. **Human-readable summary** for UI (e.g., "24h weekdays, 48h weekends")
2. **Normalized hassle score** [0, 1] for feature engineering

**Scoring Logic:**
- Base score from `notification_hours`:
  - No notification (H24, O/R) → 1.0 (low hassle)
  - 48+ hours → 0.7
  - 24 hours → 0.5
  - 12 hours → 0.3
  - < 12 hours → 0.1 (high hassle)
- Complexity penalties:
  - Multiple rules → -0.1 per additional rule
  - Weekday-specific → -0.1
  - Business day requirements → -0.15
  - Specific time requirements → -0.1
- Final score clamped to [0, 1]

```python
# aip/rule_summarizer.py - Generate high-level summaries from detailed rules

class RuleSummary(BaseModel):
    """High-level summary of notification requirements."""
    notification_summary: str  # Human-readable: "24h weekdays, 48h weekends"
    hassle_level: str  # 'low', 'moderate', 'high', 'very_high'
    notification_score: float  # Normalized [0, 1] for scoring

class AIPRuleSummarizer:
    """
    Generates high-level summaries from detailed notification rules.
    
    Two purposes:
        1. Human-readable summary for UI
        2. Normalized score for ga_hassle_score feature
    """
    
    def __init__(
        self,
        llm_model: str,
        llm_temperature: float = 0.0,
        api_key: Optional[str] = None
    ):
        """
        Initialize summarizer with LLM.
        
        Creates LangChain chain for rule summarization.
        """
        # Build prompt template
        # Create ChatOpenAI instance
        # Create JSON output parser
        # Chain: prompt | llm | parser
    
    def summarize_rules(
        self,
        icao: str,
        rules: ParsedAIPRules
    ) -> RuleSummary:
        """
        Generate high-level summary from detailed rules.
        
        Args:
            icao: Airport ICAO code
            rules: Parsed notification rules
        
        Returns:
            RuleSummary with summary text, hassle level, and score
        
        Process:
            1. Analyze rule complexity (number of rules, time requirements)
            2. Generate human-readable summary
            3. Assign hassle level based on complexity
            4. Calculate normalized score [0, 1]
                - 0.0 = no notification required
                - 1.0 = very complex (multiple rules, short notice, weekday-specific)
        """
        # Build prompt with rules
        # Invoke LLM for summary text and hassle level
        # Calculate score from rules:
        #   - Base score from notification_hours (shorter = higher hassle)
        #   - Complexity penalty (multiple rules, weekday-specific)
        #   - Business day requirements add complexity
        #   - Specific time requirements add complexity
        #   - Clamp to [0, 1]
        # Return RuleSummary
    
    def calculate_hassle_score(self, rules: List[NotificationRule]) -> float:
        """
        Calculate normalized hassle score from rules.
        
        Returns:
            Score [0, 1] where 1.0 = low hassle, 0.0 = high hassle
        """
        if not rules:
            return 1.0  # No rules = no hassle
        
        # Find minimum notification hours (most restrictive)
        min_hours = min(
            (r.notification_hours for r in rules 
             if r.notification_hours is not None and r.notification_type == 'hours'),
            default=None
        )
        
        # Base score from hours
        if min_hours is None:
            # Check for H24 or O/R
            if any(r.notification_type in ['h24', 'on_request'] for r in rules):
                base_score = 1.0
            else:
                base_score = 0.5  # Unknown/ambiguous
        else:
            # Map hours to score
            if min_hours >= 48:
                base_score = 0.7
            elif min_hours >= 24:
                base_score = 0.5
            elif min_hours >= 12:
                base_score = 0.3
            else:
                base_score = 0.1
        
        # Complexity penalties
        penalty = 0.0
        if len(rules) > 1:
            penalty += 0.1 * (len(rules) - 1)  # Multiple rules
        if any(r.weekday_start is not None or r.weekday_end is not None for r in rules):
            penalty += 0.1  # Weekday-specific
        if any(r.notification_type == 'business_day' for r in rules):
            penalty += 0.15  # Business day requirements
        if any(r.specific_time is not None for r in rules):
            penalty += 0.1  # Specific time requirements
        
        # Apply penalty and clamp
        final_score = max(0.0, min(1.0, base_score - penalty))
        return final_score
```

### 2.7 Integration with Builder

```python
# In builder.py

class GAFriendlinessBuilder:
    def __init__(self, ..., enable_aip_parsing: bool = False):
        """
        Args:
            enable_aip_parsing: If True, parse AIP rules in addition to reviews
        """
        # ... existing initialization ...
        # If enable_aip_parsing:
        #   Create AIPSource, AIPRuleParser, AIPRuleSummarizer
    
    def build(
        self,
        reviews_source: ReviewSource,
        euro_aip_path: Optional[Path] = None,
        parse_aip_rules: bool = False,
        ...
    ) -> BuildResult:
        """
        Args:
            parse_aip_rules: If True, parse AIP rules from euro_aip.sqlite
        """
        # ... existing review processing ...
        
        # Optional: Parse AIP rules
        if parse_aip_rules and euro_aip_path:
            self.process_aip_rules(euro_aip_path, incremental=incremental, since=since)
    
    def process_aip_rules(
        self,
        euro_aip_path: Path,
        incremental: bool = False,
        since: Optional[datetime] = None,
        icaos: Optional[List[str]] = None
    ) -> None:
        """
        Process AIP rules for airports.
        
        Pipeline:
            1. Load AIP text from euro_aip.sqlite
            2. Filter for incremental if requested
            3. For each airport:
                a. Parse rules (LLM)
                b. Store detailed rules in ga_notification_requirements
                c. Generate summary (LLM)
                d. Store summary in ga_aip_rule_summary
                e. Update ga_airfield_stats.notification_hassle_score
        4. Update metadata
        
        Args:
            euro_aip_path: Path to euro_aip.sqlite
            incremental: Only process changed airports
            since: Only process if AIP changed since this date
            icaos: Optional list of specific ICAOs
        """
        aip_source = AIPSource(euro_aip_path)
        
        # Get airports to process
        if icaos:
            airports = icaos
        else:
            airports = aip_source.get_all_airports()
        
        # Filter for incremental
        if incremental:
            filtered_airports = []
            for icao in airports:
                # Check if AIP data changed
                last_aip_change = aip_source.get_last_aip_change_timestamp(icao)
                last_processed = self.storage.get_last_aip_processed_timestamp(icao)
                
                # Process if:
                #   - Never processed (last_processed is None)
                #   - AIP changed since last processed
                #   - Since date provided and AIP changed after since
                should_process = (
                    last_processed is None or
                    (last_aip_change and last_aip_change > last_processed) or
                    (since and last_aip_change and last_aip_change > since)
                )
                
                if should_process:
                    filtered_airports.append(icao)
            airports = filtered_airports
            logger.info(
                "aip_incremental_filter",
                airports_before=len(airports) + (len(filtered_airports) - len(airports)),
                airports_after=len(filtered_airports),
                since=since.isoformat() if since else None
            )
        
        # Process each airport
        with self.storage:
            for icao in airports:
                try:
                    # Get AIP text
                    aip_text = aip_source.get_airport_aip_text(icao)
                    if not aip_text:
                        continue
                    
                    # Parse rules
                    parsed_rules = self.aip_rule_parser.parse_rules(icao, aip_text)
                    
                    # Store detailed rules
                    self.storage.write_notification_requirements(icao, parsed_rules.notification_rules)
                    
                    # Generate summary
                    summary = self.aip_rule_summarizer.summarize_rules(icao, parsed_rules)
                    
                    # Store summary
                    self.storage.write_aip_rule_summary(icao, summary)
                    
                    # Update ga_airfield_stats.notification_hassle_score
                    # This feeds into ga_hassle_score feature
                    self.storage.update_notification_hassle_score(icao, summary.notification_score)
                    
                    # Update last processed timestamp
                    self.storage.update_last_aip_processed_timestamp(icao, datetime.utcnow())
                    
                except Exception as e:
                    logger.error("aip_rule_processing_failed", icao=icao, error=str(e))
                    # Handle based on failure_mode
```

### 2.8 Storage Extensions

```python
# In storage.py

class GAMetaStorage:
    def write_notification_requirements(
        self,
        icao: str,
        rules: List[NotificationRule]
    ) -> None:
        """
        Write notification requirements to ga_notification_requirements.
        
        Clears existing rules for this icao first (idempotent rebuild).
        """
        # DELETE existing rules for icao
        # INSERT new rules
        # Use executemany for efficiency
    
    def write_aip_rule_summary(
        self,
        icao: str,
        summary: RuleSummary
    ) -> None:
        """Insert or update ga_aip_rule_summary."""
        # UPSERT
    
    def update_notification_hassle_score(
        self,
        icao: str,
        score: float
    ) -> None:
        """Update notification_hassle_score in ga_airfield_stats."""
        # UPDATE ga_airfield_stats SET notification_hassle_score = ? WHERE icao = ?
    
    def get_last_aip_processed_timestamp(self, icao: str) -> Optional[datetime]:
        """Get when AIP rules were last processed for this airport."""
        # Query ga_meta_info for 'last_aip_processed_{icao}'
        # Return datetime or None
    
    def update_last_aip_processed_timestamp(self, icao: str, timestamp: datetime) -> None:
        """Update last processed timestamp for AIP rules."""
        # Store in ga_meta_info: key='last_aip_processed_{icao}', value=ISO timestamp
```

### 2.9 Feature Integration

```python
# In features.py

class FeatureMapper:
    def map_hassle_score(
        self,
        distribution: Dict[str, float],  # From review tags
        notification_hassle_score: Optional[float] = None  # From AIP rules
    ) -> float:
        """
        Map 'bureaucracy' aspect + AIP notification rules to ga_hassle_score.
        
        Combines:
            - Review tags about bureaucracy (from distribution)
            - AIP notification requirements (from notification_hassle_score)
        
        Returns [0, 1] where 1.0 = low hassle, 0.0 = high hassle.
        """
        # Get score from review distribution (existing logic)
        review_score = self._map_bureaucracy_from_reviews(distribution)
        
        # Combine with AIP notification score if available
        if notification_hassle_score is not None:
            # Weighted combination (e.g., 70% reviews, 30% AIP rules)
            combined = 0.7 * review_score + 0.3 * notification_hassle_score
            return combined
        
        return review_score
```

### 2.10 Design Decisions

**Separation of Concerns:**
- AIP parsing is **optional** and **separate** from review processing
- Can run independently or together
- Different NLP pipeline (rule extraction vs. sentiment extraction)

**Two-Stage Processing:**
- **Stage 1:** Extract detailed structured rules (for operational use)
- **Stage 2:** Summarize to high-level score (for feature engineering)
- Both stored for different use cases

**Incremental Updates:**
- Track `last_aip_processed_{icao}` in ga_meta_info
- Check `aip_entries_changes` table in euro_aip for changes
- Only reprocess airports with AIP changes

**Extensibility:**
- Can add other rule types (handling, customs, etc.)
- Same pattern: extract → summarize → score
- Modular design allows adding new rule parsers

**Integration with Feature Engineering:**
- `notification_hassle_score` from AIP rules feeds into `ga_hassle_score`
- Combined with review-based bureaucracy tags
- Weighted combination (e.g., 70% reviews, 30% AIP rules)
- See `FeatureMapper.map_hassle_score()` for implementation

**Incremental Updates:**
- Track `last_aip_processed_{icao}` in ga_meta_info
- Check `aip_entries_changes` table in euro_aip for changes
- Only reprocess airports with AIP changes
- Works independently from review processing

**CLI Integration:**
```bash
# Parse AIP rules in addition to reviews
python tools/build_ga_friendliness.py \
    --airfield-directory-export ... \
    --euro-aip-db path/to/euro_aip.sqlite \
    --parse-aip-rules \
    --incremental
```

---

## 3. Exception Hierarchy

### 2.1 Exception Classes (`exceptions.py`)

```python
# exceptions.py - Exception hierarchy for ga_friendliness library

class GAFriendlinessError(Exception):
    """Base exception for ga_friendliness library."""
    pass

class OntologyValidationError(GAFriendlinessError):
    """Raised when ontology validation fails."""
    pass

class PersonaValidationError(GAFriendlinessError):
    """Raised when persona validation fails."""
    pass

class ReviewExtractionError(GAFriendlinessError):
    """Raised when LLM extraction fails."""
    pass

class StorageError(GAFriendlinessError):
    """Raised when database operations fail."""
    pass

class FeatureMappingError(GAFriendlinessError):
    """Raised when feature mapping fails."""
    pass

class BuildError(GAFriendlinessError):
    """Raised when build process fails."""
    pass
```

**Design Decision: Exception Hierarchy**

- **Why:** Clear error types for better error handling and debugging
- **Usage:** Components raise specific exceptions, caller can handle appropriately
- **Pattern:** Base exception + specific subclasses for each domain

---

## 3. Core Models & Data Structures

### 2.1 Pydantic Models (`models.py`)

```python
# models.py - Data structures using Pydantic for validation

class AspectLabel(BaseModel):
    """Single label for an aspect (e.g., 'cost': 'expensive')."""
    aspect: str
    label: str
    confidence: float  # 0.0-1.0

class ReviewExtraction(BaseModel):
    """Structured extraction from a single review."""
    review_id: Optional[str]
    aspects: List[AspectLabel]
    raw_text_excerpt: Optional[str]  # For transparency/debugging

class OntologyConfig(BaseModel):
    """Loaded ontology.json structure."""
    version: str
    aspects: Dict[str, List[str]]  # aspect_name -> [allowed_labels]

class PersonaWeights(BaseModel):
    """Weights for a single persona."""
    ga_cost_score: float = 0.0
    ga_review_score: float = 0.0
    ga_hassle_score: float = 0.0
    ga_ops_ifr_score: float = 0.0
    ga_ops_vfr_score: float = 0.0
    ga_access_score: float = 0.0
    ga_fun_score: float = 0.0

class PersonaConfig(BaseModel):
    """Single persona definition."""
    id: str
    label: str
    description: str
    weights: PersonaWeights

class PersonasConfig(BaseModel):
    """Loaded personas.json structure."""
    version: str
    personas: Dict[str, PersonaConfig]  # persona_id -> PersonaConfig

class AirportFeatureScores(BaseModel):
    """Normalized feature scores for an airport."""
    icao: str
    ga_cost_score: float
    ga_review_score: float
    ga_hassle_score: float
    ga_ops_ifr_score: float
    ga_ops_vfr_score: float
    ga_access_score: float
    ga_fun_score: float

class AirportStats(BaseModel):
    """Aggregated stats for ga_airfield_stats table."""
    icao: str
    rating_avg: Optional[float]
    rating_count: int
    last_review_utc: Optional[str]
    fee_band_0_749kg: Optional[float]      # 0-749 kg MTOW
    fee_band_750_1199kg: Optional[float]   # 750-1199 kg MTOW
    fee_band_1200_1499kg: Optional[float]  # 1200-1499 kg MTOW
    fee_band_1500_1999kg: Optional[float]  # 1500-1999 kg MTOW
    fee_band_2000_3999kg: Optional[float]  # 2000-3999 kg MTOW
    fee_band_4000_plus_kg: Optional[float] # 4000+ kg MTOW
    fee_currency: Optional[str]
    mandatory_handling: bool
    ifr_procedure_available: bool  # True if airport has instrument approach procedures (ILS, RNAV, VOR, etc.) from AIP
    night_available: bool
    # ... feature scores ...
    source_version: str
    scoring_version: str
```

---

## 4. Configuration Management

### 3.1 Config Loading (`config.py`)

```python
# config.py - Configuration loading and validation

class GAFriendlinessSettings(BaseSettings):
    """Settings for GA friendliness processing."""
    # Paths
    euro_aip_db_path: Path  # Path to euro_aip.sqlite
    ga_meta_db_path: Path   # Path to ga_meta.sqlite (output)
    ontology_json_path: Path
    personas_json_path: Path
    
    # LLM settings
    llm_model: str = "gpt-4o-mini"  # Default for cost efficiency
    llm_temperature: float = 0.0
    llm_api_key: Optional[str] = None  # From env or explicit
    
    # Processing settings
    confidence_threshold: float = 0.5  # Min confidence for tag inclusion
    batch_size: int = 50  # Reviews per LLM batch
    
    # Versioning
    source_version: str  # e.g., "airfield.directory-2025-11-01"
    scoring_version: str = "ga_scores_v1"

def load_ontology(path: Path) -> OntologyConfig:
    """
    Load and validate ontology.json.
    
    Raises:
        ValidationError if JSON is malformed or structure invalid.
    """
    # Load JSON, validate with Pydantic, return OntologyConfig

def load_personas(path: Path) -> PersonasConfig:
    """
    Load and validate personas.json.
    
    Raises:
        ValidationError if JSON is malformed or weights don't sum reasonably.
    """
    # Load JSON, validate with Pydantic, return PersonasConfig

def get_settings() -> GAFriendlinessSettings:
    """
    Load settings from environment variables and defaults.
    
    Environment variables:
        GA_FRIENDLINESS_EURO_AIP_DB
        GA_FRIENDLINESS_GA_META_DB
        GA_FRIENDLINESS_ONTOLOGY_JSON
        GA_FRIENDLINESS_PERSONAS_JSON
        GA_FRIENDLINESS_LLM_MODEL
        OPENAI_API_KEY (or GA_FRIENDLINESS_LLM_API_KEY)
    """
    # Use pydantic-settings BaseSettings pattern
```

---

## 5. Database Schema & Storage

### 5.1 Schema Creation & Versioning (`database.py`)

```python
# database.py - SQLite schema and connection management with versioning

SCHEMA_VERSION = "1.0"

def get_schema_version(conn: sqlite3.Connection) -> Optional[str]:
    """
    Get current schema version from database.
    
    Returns:
        Schema version string (e.g., "1.0") or None if not set.
    """
    # Query ga_meta_info for 'schema_version' key
    # Return version or None

def create_schema(conn: sqlite3.Connection) -> None:
    """
    Create all tables in ga_meta.sqlite and set schema version.
    
    Tables:
        - ga_airfield_stats (main query table)
        - ga_landing_fees (optional detailed fees)
        - ga_review_ner_tags (structured review tags)
        - ga_review_summary (LLM-generated summaries)
        - ga_meta_info (versioning metadata)
        - ga_notification_requirements (AIP notification rules, optional)
        - ga_aip_rule_summary (AIP rule summaries, optional)
    
    Also creates indexes for performance.
    Sets schema_version in ga_meta_info.
    
    **Note on `ifr_procedure_available` field:**
    This flag indicates the presence of instrument approach procedures (ILS, RNAV, 
    VOR, etc.) as identified from the AIP database, NOT just whether the airfield 
    accepts IFR flight plans. An airfield may accept IFR flight plans but not have 
    published instrument approaches.
    """
    # Execute CREATE TABLE statements
    # Create indexes on icao, (icao, aspect) for ga_review_ner_tags
    # Insert schema_version into ga_meta_info

def migrate_schema(
    conn: sqlite3.Connection,
    from_version: str,
    to_version: str
) -> None:
    """
    Migrate schema from one version to another.
    
    Handles:
        - Adding new columns (ALTER TABLE ADD COLUMN)
        - Modifying existing columns (via table recreation if needed)
        - Data transformations if required
    
    Raises:
        StorageError if migration fails.
    """
    # Check if migration path exists (from_version -> to_version)
    # Execute migration steps
    # Update schema_version in ga_meta_info
    # Commit transaction

def ensure_schema_version(conn: sqlite3.Connection) -> None:
    """
    Ensure database schema is at current version.
    
    If schema doesn't exist, creates it.
    If schema exists but is older version, migrates it.
    If schema is newer version, raises error.
    """
    current_version = get_schema_version(conn)
    
    if current_version is None:
        # No schema, create it
        create_schema(conn)
    elif current_version == SCHEMA_VERSION:
        # Schema is current, nothing to do
        pass
    elif current_version < SCHEMA_VERSION:
        # Schema is older, migrate
        migrate_schema(conn, current_version, SCHEMA_VERSION)
    else:
        # Schema is newer (shouldn't happen), raise error
        raise StorageError(
            f"Database schema version {current_version} is newer than "
            f"library version {SCHEMA_VERSION}. Please upgrade library."
        )

def get_connection(db_path: Path) -> sqlite3.Connection:
    """
    Get a connection to ga_meta.sqlite.
    
    Creates the database and schema if it doesn't exist.
    Ensures schema is at current version.
    
    Returns:
        Connection with schema at current version.
    """
    # Create parent dirs if needed
    # Create database if doesn't exist
    # Call ensure_schema_version()
    # Return connection
```

### 5.2 Storage Operations (`storage.py`)

```python
# storage.py - Read/write operations for ga_meta.sqlite with transaction support

import threading
from contextlib import contextmanager

class GAMetaStorage:
    """
    Handles all database operations for ga_meta.sqlite.
    
    Supports:
        - Transaction management (context manager)
        - Thread-safe operations
        - Batch writes for efficiency
        - Resource cleanup
    """
    
    def __init__(self, db_path: Path):
        """
        Initialize storage.
        
        Creates database and schema if needed.
        Ensures schema is at current version.
        """
        # Store db_path
        # Get connection (ensures schema version)
        # Create thread lock for thread-safety
    
    def __enter__(self):
        """Context manager entry: begin transaction."""
        # Begin transaction
        # Return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit: commit or rollback.
        
        Commits on success, rolls back on exception.
        """
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        # Don't suppress exceptions
    
    def close(self) -> None:
        """Close database connection and cleanup resources."""
        # Close connection if open
        # Cleanup resources
    
    def write_airfield_stats(self, stats: AirportStats) -> None:
        """
        Insert or update a row in ga_airfield_stats.
        
        Uses UPSERT pattern (INSERT OR REPLACE).
        Thread-safe.
        """
        with self._lock:
            # UPSERT pattern (INSERT OR REPLACE)
            # Raise StorageError on failure
    
    def write_review_tags(self, icao: str, tags: List[ReviewExtraction]) -> None:
        """
        Write review tags to ga_review_ner_tags.
        
        Clears existing tags for this icao first (idempotent rebuild).
        Thread-safe.
        """
        with self._lock:
            # DELETE existing tags for icao
            # INSERT new tags (use executemany for efficiency)
            # Raise StorageError on failure
    
    def write_review_tags_batch(
        self,
        tags_by_icao: Dict[str, List[ReviewExtraction]]
    ) -> None:
        """
        Write tags for multiple airports in a single transaction.
        
        More efficient than individual writes.
        Thread-safe.
        """
        with self._lock:
            # For each icao:
            #   DELETE existing tags
            #   INSERT new tags
            # All in single transaction
            # Raise StorageError on failure
    
    def write_review_summary(self, icao: str, summary_text: str, tags_json: List[str]) -> None:
        """Insert or update ga_review_summary for an airport."""
        with self._lock:
            # UPSERT
            # Raise StorageError on failure
    
    def write_meta_info(self, key: str, value: str) -> None:
        """Write to ga_meta_info table."""
        with self._lock:
            # INSERT OR REPLACE
            # Raise StorageError on failure
    
    def get_airfield_stats(self, icao: str) -> Optional[AirportStats]:
        """Read stats for a single airport."""
        # SELECT and map to AirportStats
        # Return None if not found
    
    def get_all_icaos(self) -> List[str]:
        """Get list of all ICAOs in ga_airfield_stats."""
        # SELECT DISTINCT icao
        # Return list
    
    def get_last_processed_timestamp(self, icao: str) -> Optional[datetime]:
        """
        Get when airport was last processed.
        
        Returns:
            Timestamp from ga_meta_info key 'last_processed_{icao}' or
            max(ga_airfield_stats.last_review_utc) for this airport,
            or None if airport not processed.
        """
        # Try ga_meta_info first: 'last_processed_{icao}'
        # If not found, query max(last_review_utc) from ga_airfield_stats
        # Parse ISO timestamp string to datetime
        # Return datetime or None
    
    def get_processed_review_ids(self, icao: str) -> Set[str]:
        """
        Get set of review_ids already processed for this airport.
        
        Returns:
            Set of review_id strings that have been extracted and stored.
        """
        # Query ga_review_ner_tags for distinct review_ids for this icao
        # Return set of review_ids
    
    def has_changes(
        self,
        icao: str,
        reviews: List[RawReview],
        since: Optional[datetime] = None
    ) -> bool:
        """
        Check if airport has new/changed reviews.
        
        Strategy:
            1. If airport never processed → return True
            2. If since date provided → check if any review timestamp > since
            3. Compare review_ids → check for new review_ids
            4. Compare timestamps → check for updated reviews (same ID, newer timestamp)
        
        Args:
            icao: Airport ICAO code
            reviews: List of reviews to check
            since: Optional date filter (only check reviews after this date)
        
        Returns:
            True if reviews have changed since last processing.
        """
        # Get last processed timestamp
        last_processed = self.get_last_processed_timestamp(icao)
        if last_processed is None:
            return True  # Never processed
        
        # Get already processed review_ids
        processed_ids = self.get_processed_review_ids(icao)
        
        # Filter reviews by since date if provided
        if since:
            reviews = [r for r in reviews 
                      if r.timestamp and parse_timestamp(r.timestamp) > since]
        
        # Check for new reviews (review_id not in processed_ids)
        for review in reviews:
            if review.review_id not in processed_ids:
                return True  # New review found
        
        # Check for updated reviews (same ID but newer timestamp)
        for review in reviews:
            if review.review_id in processed_ids and review.timestamp:
                review_time = parse_timestamp(review.timestamp)
                if review_time > last_processed:
                    return True  # Review was updated
        
        return False  # No changes detected
    
    def update_last_processed_timestamp(self, icao: str, timestamp: datetime) -> None:
        """
        Update last processed timestamp for an airport.
        
        Stores in ga_meta_info with key 'last_processed_{icao}'.
        Also updates ga_airfield_stats.last_review_utc if newer.
        """
        # Store in ga_meta_info: key='last_processed_{icao}', value=ISO timestamp
        # Update ga_airfield_stats.last_review_utc if this timestamp is newer
    
    def attach_euro_aip(self, conn: sqlite3.Connection, euro_aip_path: Path) -> None:
        """
        ATTACH euro_aip.sqlite for joint queries.
        
        Usage:
            conn = self.get_connection()
            self.attach_euro_aip(conn, euro_aip_path)
            # Now can query: SELECT * FROM aip.airport JOIN ga.ga_airfield_stats ...
        """
        # Execute: ATTACH DATABASE 'euro_aip_path' AS aip
        # Raise StorageError on failure
```

---

## 6. Caching Layer

### 6.1 Caching Utility (`cache.py`)

```python
# cache.py - Caching utility for remote data sources

from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, Tuple
import json
import gzip
import logging

logger = logging.getLogger(__name__)

class CachedDataLoader(ABC):
    """
    Base class for data loaders that implement caching.
    
    Similar pattern to euro_aip's CachedSource, but independent.
    Provides caching for remote data to avoid repeated downloads.
    
    Usage:
        class MyLoader(CachedDataLoader):
            def fetch_data(self, key: str, **kwargs) -> Any:
                # Fetch from remote source
                return data
        
        loader = MyLoader(cache_dir="/path/to/cache")
        data = loader.get_cached("my_key", max_age_days=7)
    """
    
    def __init__(self, cache_dir: Path):
        """
        Initialize cached loader.
        
        Args:
            cache_dir: Base directory for caching
        """
        # Create cache directory structure
        # Store cache_dir path
    
    def set_force_refresh(self, force_refresh: bool = True) -> None:
        """Set whether to force refresh of cached data."""
        # Store flag
    
    def set_never_refresh(self, never_refresh: bool = True) -> None:
        """Set whether to never refresh cached data (use cache if exists)."""
        # Store flag
    
    def _get_cache_file(self, key: str, ext: str = "json") -> Path:
        """Get cache file path for a key."""
        # Return Path to cache file
    
    def _is_cache_valid(
        self,
        cache_file: Path,
        max_age_days: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if cache file is valid.
        
        Returns:
            (is_valid, reason_if_invalid)
        """
        # Check force_refresh flag
        # Check if file exists
        # Check never_refresh flag
        # Check age if max_age_days provided
        # Return (is_valid, reason)
    
    def _save_to_cache(self, data: Any, key: str, ext: str = "json") -> None:
        """Save data to cache."""
        # Handle JSON (with gzip support)
        # Handle other formats as needed
    
    def _load_from_cache(self, key: str, ext: str = "json") -> Any:
        """Load data from cache."""
        # Handle JSON (with gzip support)
        # Handle other formats as needed
    
    @abstractmethod
    def fetch_data(self, key: str, **kwargs) -> Any:
        """
        Fetch data from remote source.
        
        Must be implemented by subclasses.
        """
        pass
    
    def get_cached(
        self,
        key: str,
        max_age_days: Optional[int] = None,
        ext: str = "json",
        **kwargs
    ) -> Any:
        """
        Get data from cache or fetch if needed.
        
        Args:
            key: Cache key
            max_age_days: Maximum age of cache (None = no limit)
            ext: File extension (json, json.gz)
            **kwargs: Arguments to pass to fetch_data()
        
        Returns:
            Cached or freshly fetched data
        """
        # Get cache file path
        # Check if cache is valid
        # If valid, load and return
        # If not valid, call fetch_data()
        # Save to cache
        # Return data
```

**Design Decision: Independent Caching**

- **Why not reuse CachedSource from euro_aip?**
  - ga_friendliness should be independent (design principle)
  - CachedSource is tightly coupled to euro_aip's fetch method pattern
  - We need simpler caching for our use case (just JSON files)
  
- **Why this pattern?**
  - Follows same conceptual approach (familiar)
  - Simpler implementation (just JSON, no CSV/PDF)
  - Supports gzip for large files
  - Can be extended if needed

- **Alternative considered:**
  - Composition: Use CachedSource if euro_aip available
  - **Rejected:** Adds unnecessary complexity, breaks independence

### 5.2 Caching in Review Sources

```python
# Example: Cached AirfieldDirectorySource

class AirfieldDirectorySource(ReviewSource, CachedDataLoader):
    """
    Loads reviews from airfield.directory with caching.
    """
    
    def __init__(
        self,
        export_path: Optional[Path] = None,  # If None, download from S3
        cache_dir: Path,
        filter_ai_generated: bool = True,
        preferred_language: str = "EN",
        max_age_days: int = 7  # Cache bulk export for 7 days
    ):
        """
        Initialize with caching support.
        
        If export_path is None, will download from S3 and cache.
        """
        # Initialize CachedDataLoader
        # Store config
    
    def fetch_data(self, key: str, **kwargs) -> Dict:
        """
        Fetch data from remote source.
        
        Keys:
            - "bulk_export": Download from S3
            - "airport_{ICAO}": Fetch individual airport JSON
        """
        if key == "bulk_export":
            # Download from S3: airfield-directory-pireps-export-latest.json.gz
            # Return parsed JSON
        elif key.startswith("airport_"):
            icao = key.replace("airport_", "")
            # Fetch https://airfield.directory/airfield/{ICAO}.json
            # Return parsed JSON
        else:
            raise ValueError(f"Unknown key: {key}")
    
    def get_reviews(self) -> List[RawReview]:
        """
        Load reviews with caching.
        
        If export_path provided, use it directly.
        Otherwise, download and cache from S3.
        """
        if self.export_path and self.export_path.exists():
            # Use local file
            # Load and parse
        else:
            # Get from cache or download
            data = self.get_cached(
                "bulk_export",
                max_age_days=self.max_age_days,
                ext="json.gz"
            )
            # Parse and return reviews
    
    def get_airport_stats(self, icao: str) -> Optional[Dict]:
        """
        Get airport stats with caching.
        
        Fetches individual airport JSON with 30-day cache.
        """
        data = self.get_cached(
            f"airport_{icao}",
            max_age_days=30,  # Airport data changes less frequently
            ext="json"
        )
        # Extract and return stats
```

**Caching Strategy:**

1. **Bulk export (S3):**
   - Cache key: `bulk_export`
   - Default max_age: 7 days (export updates regularly)
   - Format: `.json.gz` (compressed)
   - Can force refresh for latest data

2. **Individual airport JSON:**
   - Cache key: `airport_{ICAO}`
   - Default max_age: 30 days (changes less frequently)
   - Format: `.json`
   - Used when fetching airport-level stats

3. **CLI flags:**
   - `--force-refresh`: Force download even if cache exists
   - `--never-refresh`: Use cache if exists, never download
   - `--cache-dir`: Override default cache directory

---

## 7. Ontology & Persona Management

### 7.1 Ontology (`ontology.py`)

```python
# ontology.py - Ontology validation and lookup

class OntologyManager:
    """Manages ontology aspects and labels."""
    
    def __init__(self, config: OntologyConfig):
        """Initialize with loaded ontology."""
        # Store config
    
    def validate_aspect(self, aspect: str) -> bool:
        """Check if aspect exists in ontology."""
        # Return aspect in config.aspects
    
    def validate_label(self, aspect: str, label: str) -> bool:
        """Check if label is allowed for aspect."""
        # Check label in config.aspects[aspect]
    
    def get_allowed_labels(self, aspect: str) -> List[str]:
        """Get list of allowed labels for an aspect."""
        # Return config.aspects.get(aspect, [])
    
    def validate_extraction(self, extraction: ReviewExtraction) -> List[str]:
        """
        Validate a ReviewExtraction against ontology.
        
        Returns:
            List of validation error messages (empty if valid).
        """
        # For each aspect-label pair, validate
        # Check confidence in [0, 1]
        # Return list of errors
```

### 6.2 Personas (`personas.py`)

```python
# personas.py - Persona loading and score computation

class PersonaManager:
    """Manages personas and computes persona-specific scores."""
    
    def __init__(self, config: PersonasConfig):
        """Initialize with loaded personas."""
        # Store config
    
    def get_persona(self, persona_id: str) -> Optional[PersonaConfig]:
        """Get persona by ID."""
        # Return config.personas.get(persona_id)
    
    def list_persona_ids(self) -> List[str]:
        """List all persona IDs."""
        # Return list(config.personas.keys())
    
    def compute_score(
        self,
        persona_id: str,
        features: AirportFeatureScores
    ) -> float:
        """
        Compute persona-specific score from base features.
        
        Formula:
            score = Σ(weight[feature] * feature_value)
        
        Returns:
            Score in [0, 1] range (assuming features are normalized).
        """
        # Get persona config
        # For each feature in features, multiply by persona weight
        # Sum and return
    
    def compute_scores_for_all_personas(
        self,
        features: AirportFeatureScores
    ) -> Dict[str, float]:
        """
        Compute scores for all personas.
        
        Returns:
            Dict mapping persona_id -> score
        """
        # For each persona, call compute_score
        # Return dict
```

---

## 8. NLP Pipeline (LangChain 1.0)

### 8.1 Review Tag Extraction (`nlp/extractor.py`)

```python
# nlp/extractor.py - LLM-based review tag extraction

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

class ReviewExtractor:
    """
    Extracts structured tags from free-text reviews using LLM.
    
    Features:
        - Retry logic for transient failures
        - Token usage tracking
        - Error handling with specific exceptions
    """
    
    def __init__(
        self,
        ontology: OntologyConfig,
        llm_model: str,
        llm_temperature: float,
        api_key: Optional[str] = None,
        max_retries: int = 3
    ):
        """
        Initialize extractor with LLM.
        
        Creates LangChain chain:
            prompt -> llm -> PydanticOutputParser(ReviewExtraction)
        
        Args:
            max_retries: Maximum number of retry attempts for LLM calls
        """
        # Build prompt template with ontology embedded
        # Create ChatOpenAI instance
        # Create PydanticOutputParser for ReviewExtraction
        # Chain: prompt | llm | parser
        # Store max_retries for retry logic
        # Initialize token usage tracking
    
    def extract(self, review_text: str, review_id: Optional[str] = None) -> ReviewExtraction:
        """
        Extract tags from a single review.
        
        Returns:
            ReviewExtraction with aspect-label pairs.
        
        Raises:
            ReviewExtractionError if LLM call fails or output doesn't match schema.
        """
        # Invoke chain with review_text
        # Track token usage
        # Handle retries for transient failures
        # Set review_id on result
        # Return ReviewExtraction
        # Raise ReviewExtractionError on failure
    
    def extract_batch(
        self,
        reviews: List[Tuple[str, Optional[str]]]  # (text, review_id)
    ) -> List[ReviewExtraction]:
        """
        Extract tags from multiple reviews (batched for efficiency).
        
        Can batch multiple reviews into single LLM call if model supports,
        or process sequentially with retries.
        """
        # Option 1: Single prompt with multiple reviews (if LLM supports)
        # Option 2: Process sequentially with batch() for parallelization
        # Apply confidence threshold
        # Return list of ReviewExtraction
```

**Design Decision: Batch Processing**

- **Option A:** Single LLM call with multiple reviews in prompt
  - **Pros:** Fewer API calls, lower cost
  - **Cons:** Token limits, harder error handling per review
- **Option B:** Sequential with LangChain's `batch()` for parallelization
  - **Pros:** Better error isolation, easier retry logic
  - **Cons:** More API calls
- **Choice:** Start with Option B (sequential with batch), add Option A as optimization later.

### 8.2 Tag Aggregation (`nlp/aggregator.py`)

```python
# nlp/aggregator.py - Aggregate tags into feature scores

class TagAggregator:
    """Aggregates review tags into normalized feature scores."""
    
    def __init__(self, ontology: OntologyConfig):
        """Initialize with ontology for label mapping."""
        # Store ontology
    
    def aggregate_tags(
        self,
        icao: str,
        tags: List[ReviewExtraction]
    ) -> AirportFeatureScores:
        """
        Aggregate tags for an airport into feature scores.
        
        Process:
            1. Group tags by aspect
            2. Count label distributions (weighted by confidence)
            3. Map distributions to normalized scores [0, 1]
            4. Return AirportFeatureScores
        
        Feature mappings (examples):
            - ga_cost_score: from 'cost' aspect labels (cheap=1.0, expensive=0.0)
            - ga_hassle_score: from 'bureaucracy' aspect (simple=1.0, complex=0.0)
            - ga_review_score: from 'overall_experience' aspect
            - ga_fun_score: from 'food', 'overall_experience' aspects
        """
        # Group by aspect
        # For each aspect, compute weighted label distribution
        # Map to feature scores using mapping rules
        # Return AirportFeatureScores
    
    def compute_label_distribution(
        self,
        aspect: str,
        tags: List[AspectLabel]
    ) -> Dict[str, float]:
        """
        Compute weighted distribution of labels for an aspect.
        
        Returns:
            Dict mapping label -> weighted count (sum of confidences)
        """
        # Filter tags for this aspect
        # Sum confidences per label
        # Return dict
```

### 8.3 Summary Generation (`nlp/summarizer.py`)

```python
# nlp/summarizer.py - LLM-based airport summary generation

class SummaryGenerator:
    """Generates airport-level summaries from aggregated data."""
    
    def __init__(
        self,
        llm_model: str,
        llm_temperature: float,
        api_key: Optional[str] = None
    ):
        """
        Initialize with LLM.
        
        Creates LangChain chain:
            prompt -> llm -> JSON parser (for summary_text + tags_json)
        """
        # Build prompt template
        # Create ChatOpenAI instance
        # Create JSON output parser
        # Chain: prompt | llm | parser
    
    def generate_summary(
        self,
        icao: str,
        tags: List[ReviewExtraction],
        rating_avg: Optional[float],
        rating_count: int,
        feature_scores: AirportFeatureScores
    ) -> Tuple[str, List[str]]:
        """
        Generate summary text and tags for an airport.
        
        Returns:
            (summary_text, tags_json)
            - summary_text: 2-4 sentence summary
            - tags_json: List of human-readable tags like ["GA friendly", "expensive"]
        
        Prompt includes:
            - Aggregated tags (top aspects)
            - Rating stats
            - Feature scores (for context)
            - Instructions to generate concise, pilot-focused summary
        """
        # Build prompt with all context
        # Invoke chain
        # Parse JSON response
        # Return (summary_text, tags_json)
```

---

## 9. Feature Engineering

### 9.0 Fee Band Aggregation

**Implementation Note:**

A helper function or class should be created to handle the aircraft type → MTOW → fee band mapping:

```python
# features.py or a new fee_aggregator.py

# Standard aircraft type → MTOW (kg) mapping
AIRCRAFT_MTOW_MAP: Dict[str, int] = {
    "A210": 600,
    "C172": 1157,
    "SR22": 1542,
    "DA42": 1999,
    "TBM850": 3350,
    "C510": 4100,
    "PC12": 4740,
    # Extend as needed
}

def get_mtow_for_aircraft(aircraft_type: str) -> Optional[int]:
    """Get MTOW for a given aircraft type."""
    return AIRCRAFT_MTOW_MAP.get(aircraft_type.upper())

def get_fee_band_for_mtow(mtow: int) -> str:
    """Map MTOW to fee band field name."""
    if mtow <= 749:
        return "fee_band_0_749kg"
    elif mtow <= 1199:
        return "fee_band_750_1199kg"
    elif mtow <= 1499:
        return "fee_band_1200_1499kg"
    elif mtow <= 1999:
        return "fee_band_1500_1999kg"
    elif mtow <= 3999:
        return "fee_band_2000_3999kg"
    else:
        return "fee_band_4000_plus_kg"

def aggregate_fees_by_band(landing_fees: Dict[str, List[Dict]]) -> Dict[str, Optional[float]]:
    """
    Aggregate landing fees from aircraft-specific dict to fee bands.
    
    Args:
        landing_fees: Dict[aircraft_type, List[fee_dict]]
            e.g., {"C172": [{"lineNet": 35.0, ...}], "SR22": [{"lineNet": 70.0, ...}]}
    
    Returns:
        Dict mapping fee band field names to representative fees (median if multiple)
        e.g., {"fee_band_750_1199kg": 35.0, "fee_band_1200_1499kg": 70.0, ...}
    """
    # Group fees by band
    # For each band, compute median or representative fee
    # Return dict with all 6 bands (None for missing bands)
```

### 9.0 Fee Band Aggregation (continued)

**Fee Band Structure:**

Based on airfield.directory data structure, landing fees are organized by aircraft type (e.g., C172, SR22, TBM850). These are aggregated into standardized fee bands based on the aircraft's known MTOW:

- `fee_band_0_749kg`: 0-749 kg MTOW
- `fee_band_750_1199kg`: 750-1199 kg MTOW  
- `fee_band_1200_1499kg`: 1200-1499 kg MTOW
- `fee_band_1500_1999kg`: 1500-1999 kg MTOW
- `fee_band_2000_3999kg`: 2000-3999 kg MTOW
- `fee_band_4000_plus_kg`: 4000+ kg MTOW

**Aircraft Type → MTOW Mapping:**

**Critical:** The fee data structure uses aircraft type keys (e.g., "C172", "SR22", "TBM850") as the primary identifier. The `title` field in the fee data is **NOT standardized** and varies by airport. For example:
- EDAZ: C172 title says "MTOW bis 1200kg"
- EGMC: C172 title says "MTOW up to 1499kg"

Therefore, we **must** map from aircraft type to known MTOW, then to fee band. We do **NOT** parse the title field.

```python
# Standard aircraft type → MTOW (kg) mapping
# These are actual aircraft MTOW values, not airport-specific fee ranges
AIRCRAFT_MTOW = {
    "A210": 600,      # Aeroprakt A-22 (varies by model, ~450-600kg)
    "C172": 1157,     # Cessna 172 Skyhawk
    "SR22": 1542,     # Cirrus SR22
    "DA42": 1999,     # Diamond DA42 Twin Star
    "TBM850": 3350,   # TBM 850
    "C510": 4100,     # Citation Mustang
    "PC12": 4740,     # Pilatus PC-12
    # Add more as needed
}
```

**Mapping Logic:**

From airfield.directory `aerops.data.landing_fees`:
1. Extract aircraft type key from `landing_fees` dict (e.g., "C172", "SR22")
2. Look up MTOW from `AIRCRAFT_MTOW` mapping (not from title field)
3. Map MTOW to appropriate fee band:
   - 0-749kg → `fee_band_0_749kg` (A210)
   - 750-1199kg → `fee_band_750_1199kg` (C172)
   - 1200-1499kg → `fee_band_1200_1499kg` (SR22)
   - 1500-1999kg → `fee_band_1500_1999kg` (DA42)
   - 2000-3999kg → `fee_band_2000_3999kg` (TBM850)
   - 4000+kg → `fee_band_4000_plus_kg` (C510, PC12)
4. If multiple aircraft types map to same band, use median or representative fee
5. Store in `ga_airfield_stats` for quick queries
6. Detailed fees also stored in `ga_landing_fees` table for precise lookups

**Rationale:**
- Title field is unreliable and varies by airport
- Aircraft type is consistent across airports
- Known MTOW values provide accurate band assignment
- More granular than original 2-band structure (lt_1500kg, 1500_2000kg)
- Works across different airports with different title formats (e.g., EDAZ vs EGMC)
- Better coverage of common GA aircraft weight ranges
- Supports more accurate cost scoring for different aircraft types

### 9.1 Feature Score Mapping (`features.py`)

```python
# features.py - Map label distributions to normalized feature scores

class FeatureMappingConfig(BaseModel):
    """Configuration for a single feature mapping."""
    aspect: str
    label_weights: Dict[str, float]  # label -> weight (0.0-1.0)

class FeatureMappingsConfig(BaseModel):
    """Loaded feature_mappings.json structure."""
    version: str
    mappings: Dict[str, FeatureMappingConfig]  # feature_name -> mapping

class FeatureMapper:
    """
    Maps ontology label distributions to normalized feature scores.
    
    Supports configurable mappings from JSON file, with hard-coded defaults
    as fallback.
    """
    
    def __init__(
        self,
        ontology: OntologyConfig,
        mappings_path: Optional[Path] = None
    ):
        """
        Initialize with ontology and optional mappings config.
        
        Args:
            ontology: Ontology configuration
            mappings_path: Optional path to feature_mappings.json.
                          If None, uses hard-coded default mappings.
        """
        # Store ontology
        # Load mappings from JSON if provided
        # Validate mappings against ontology
        # Store mappings (or use defaults)
    
    def map_cost_score(self, distribution: Dict[str, float]) -> float:
        """
        Map 'cost' aspect labels to ga_cost_score [0, 1].
        
        Uses mapping from config if available, otherwise defaults:
            - cheap -> 1.0
            - reasonable -> 0.6
            - expensive -> 0.0
            - unclear -> 0.5 (neutral)
        
        Returns weighted average based on distribution.
        
        Raises:
            FeatureMappingError if mapping fails.
        """
        # Get mapping config for 'ga_cost_score' (or use default)
        # Apply label weights to distribution
        # Return normalized score
        # Raise FeatureMappingError on failure
    
    def map_hassle_score(self, distribution: Dict[str, float]) -> float:
        """
        Map 'bureaucracy' aspect labels to ga_hassle_score [0, 1].
        
        Mapping:
            - simple -> 1.0
            - moderate -> 0.5
            - complex -> 0.0
        """
        # Similar to map_cost_score
    
    def map_review_score(self, distribution: Dict[str, float]) -> float:
        """
        Map 'overall_experience' aspect labels to ga_review_score [0, 1].
        
        Mapping:
            - very_positive -> 1.0
            - positive -> 0.75
            - neutral -> 0.5
            - negative -> 0.25
            - very_negative -> 0.0
        """
        # Similar pattern
    
    def map_ops_ifr_score(
        self,
        tags: List[ReviewExtraction],
        aip_data: Optional[Dict]  # From euro_aip if available
    ) -> float:
        """
        Compute ga_ops_ifr_score from tags + AIP data.
        
        Combines:
            - Review tags about IFR capability
            - AIP data (instrument approach procedures available, runway length, etc.)
        
        **Important:** `ifr_procedure_available` flag indicates presence of instrument approach 
        procedures (ILS, RNAV, VOR, etc.) from AIP database, NOT just whether the 
        airfield accepts IFR flight plans. An airfield may accept IFR flight plans 
        but not have published instrument approaches.
        
        Returns [0, 1] where 1.0 = excellent IFR support.
        """
        # Check AIP for instrument approach procedures (ILS, RNAV, VOR, etc.)
        # Check tags for IFR-related aspects
        # Combine into score
    
    def map_ops_vfr_score(
        self,
        tags: List[ReviewExtraction],
        aip_data: Optional[Dict]
    ) -> float:
        """Similar to map_ops_ifr_score but for VFR operations."""
        # Similar pattern
    
    def map_access_score(self, distribution: Dict[str, float]) -> float:
        """
        Map 'transport' aspect labels to ga_access_score [0, 1].
        
        How easy is it to get to/from the airport?
        """
        # Similar pattern
    
    def map_fun_score(
        self,
        tags: List[ReviewExtraction]
    ) -> float:
        """
        Map 'food', 'overall_experience' aspects to ga_fun_score [0, 1].
        
        Combines multiple aspects for "vibe" / enjoyment factor.
        """
        # Combine food, overall_experience distributions
        # Return composite score
```

**Design Decision: AIP Data Integration**

- **Question:** How to get AIP data (IFR procedures, runway info) for feature engineering?
- **Option A:** Query euro_aip.sqlite directly in feature mapper
  - **Pros:** Direct access, no coupling
  - **Cons:** Requires euro_aip dependency in feature mapper
- **Option B:** Pass AIP data as optional parameter (already in signature above)
  - **Pros:** Flexible, can work without euro_aip
  - **Cons:** Caller must fetch AIP data
- **Choice:** Option B (optional parameter). Builder will fetch AIP data when available.

**Design Decision: Configurable Feature Mappings**

- **Why:** Hard-coded mappings are hard to modify without code changes
- **Solution:** Load mappings from `feature_mappings.json` if provided
- **Fallback:** Use hard-coded defaults if config not provided
- **Validation:** Validate mappings against ontology on load
- **Versioning:** Mappings config has version field for tracking changes

---

## 10. Main Pipeline Orchestrator

### 10.1 Builder (`builder.py`)

```python
# builder.py - Main pipeline orchestrator

import structlog
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

logger = structlog.get_logger(__name__)

@dataclass
class BuildMetrics:
    """
    Track comprehensive build statistics.
    
    Includes:
        - Processing counts (airports, reviews)
        - LLM usage (calls, tokens, costs)
        - Error tracking (counts, failed airports)
        - Timing information
        - Cache hits/misses
    """
    # Processing counts
    airports_processed: int = 0
    airports_total: int = 0
    reviews_extracted: int = 0
    reviews_total: int = 0
    
    # LLM usage
    llm_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_total_tokens: int = 0
    llm_cost_usd: float = 0.0
    
    # Error tracking
    errors: int = 0
    failed_icaos: List[str] = field(default_factory=list)
    error_details: List[Tuple[str, str]] = field(default_factory=list)  # (icao, error_message)
    
    # Cache statistics
    cache_hits: int = 0
    cache_misses: int = 0
    
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    def calculate_duration(self) -> float:
        """Calculate duration in seconds."""
        if self.start_time and self.end_time:
            self.duration_seconds = (self.end_time - self.start_time).total_seconds()
            return self.duration_seconds
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "airports_processed": self.airports_processed,
            "airports_total": self.airports_total,
            "reviews_extracted": self.reviews_extracted,
            "reviews_total": self.reviews_total,
            "llm_calls": self.llm_calls,
            "llm_input_tokens": self.llm_input_tokens,
            "llm_output_tokens": self.llm_output_tokens,
            "llm_total_tokens": self.llm_total_tokens,
            "llm_cost_usd": self.llm_cost_usd,
            "errors": self.errors,
            "failed_icaos": self.failed_icaos,
            "error_details": self.error_details,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
        }

@dataclass
class BuildResult:
    """
    Result of build operation.
    
    Includes success status, comprehensive metrics, and any errors.
    """
    success: bool
    metrics: BuildMetrics
    error: Optional[Exception] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "metrics": self.metrics.to_dict(),
            "error": str(self.error) if self.error else None,
            "error_message": self.error_message,
        }

class FailureMode(str, Enum):
    """How to handle failures during build."""
    CONTINUE = "continue"  # Continue processing on errors, collect all failures
    FAIL_FAST = "fail_fast"  # Stop immediately on first error
    SKIP = "skip"  # Skip failed airports, continue with others (same as CONTINUE but clearer intent)

class GAFriendlinessBuilder:
    """
    Orchestrates the full pipeline to build ga_meta.sqlite.
    
    Supports:
        - Full rebuild
        - Incremental updates
        - Dependency injection for testing
        - Progress tracking
        - Error handling with configurable failure modes
        - Comprehensive metrics collection
    """
    
    def __init__(
        self,
        settings: GAFriendlinessSettings,
        *,
        storage: Optional[GAMetaStorage] = None,
        extractor: Optional[ReviewExtractor] = None,
        aggregator: Optional[TagAggregator] = None,
        feature_mapper: Optional[FeatureMapper] = None,
        persona_manager: Optional[PersonaManager] = None,
        failure_mode: FailureMode = FailureMode.CONTINUE
    ):
        """
        Initialize builder with settings and optional dependency injection.
        
        If dependencies not provided, creates them from settings.
        Useful for testing with mocks.
        
        Args:
            settings: Configuration settings
            storage: Optional storage instance (for testing)
            extractor: Optional extractor instance (for testing)
            aggregator: Optional aggregator instance (for testing)
            feature_mapper: Optional feature mapper instance (for testing)
            persona_manager: Optional persona manager instance (for testing)
            failure_mode: How to handle failures (CONTINUE, FAIL_FAST, SKIP)
        
        Loads:
            - Ontology
            - Personas
            - Feature mappings (if configured)
            - Creates storage instance
            - Initializes NLP components
        """
        # Store settings
        # Store failure_mode
        # Load ontology and personas
        # Load feature mappings if configured
        # Create or use injected dependencies:
        #   - storage
        #   - extractor
        #   - aggregator
        #   - feature_mapper
        #   - persona_manager
        # Initialize metrics
    
    def build(
        self,
        reviews_source: ReviewSource,
        euro_aip_path: Optional[Path] = None,
        incremental: bool = False,
        since: Optional[datetime] = None,
        icaos: Optional[List[str]] = None
    ) -> BuildResult:
        """
        Main entry point: build ga_meta.sqlite from reviews.
        
        Pipeline:
            1. Load reviews from source
            2. Group reviews by ICAO
            3. Filter for incremental update if requested
            4. For each ICAO:
                a. Extract tags (LLM) with retry logic
                b. Aggregate tags → feature scores
                c. Generate summary (LLM)
                d. Optionally fetch AIP data for ops scores
                e. Compute persona scores
                f. Write to database (in transaction)
            5. Write metadata (versions, timestamps)
            6. Return build result with comprehensive metrics
        
        Args:
            reviews_source: Provides reviews (see ReviewSource interface)
            euro_aip_path: Optional path to euro_aip.sqlite for AIP data
            incremental: If True, only process airports with changes
            since: For incremental mode, only process reviews updated since this date
            icaos: Optional list of specific ICAOs to process
        
        Returns:
            BuildResult with success status, comprehensive metrics, and any errors
        """
        metrics = BuildMetrics()
        metrics.start_time = datetime.utcnow()
        
        try:
            # Load reviews
            all_reviews = reviews_source.get_reviews()
            metrics.reviews_total = len(all_reviews)
            
            # Group by ICAO
            by_icao: Dict[str, List[RawReview]] = {}
            for review in all_reviews:
                if review.icao not in by_icao:
                    by_icao[review.icao] = []
                by_icao[review.icao].append(review)
            metrics.airports_total = len(by_icao)
            
            # Filter for incremental if requested:
            if incremental:
                filtered_by_icao = {}
                for icao, airport_reviews in by_icao.items():
                    # Filter by specific ICAOs if provided
                    if icaos and icao not in icaos:
                        continue
                    
                    # Check if airport has changes (includes since date check)
                    if self.storage.has_changes(icao, airport_reviews, since=since):
                        # Filter reviews by since date if provided
                        if since:
                            airport_reviews = [
                                r for r in airport_reviews 
                                if r.timestamp and parse_timestamp(r.timestamp) > since
                            ]
                        # Only include if there are reviews to process
                        if airport_reviews:
                            filtered_by_icao[icao] = airport_reviews
                
                by_icao = filtered_by_icao
                metrics.airports_total = len(by_icao)
                logger.info(
                    "incremental_filter",
                    airports_before=len(by_icao) + (metrics.airports_total - len(by_icao)),
                    airports_after=len(by_icao),
                    since=since.isoformat() if since else None
                )
            elif icaos:
                # Filter by specific ICAOs
                by_icao = {icao: by_icao[icao] for icao in icaos if icao in by_icao}
                metrics.airports_total = len(by_icao)
            
            # Process each ICAO (with progress tracking)
            with self.storage:  # Transaction context
                for icao, airport_reviews in by_icao.items():
                    try:
                        logger.info(
                            "processing_airport",
                            icao=icao,
                            review_count=len(airport_reviews),
                            progress=f"{metrics.airports_processed}/{metrics.airports_total}"
                        )
                        
                        # Process airport (tracks LLM usage internally)
                        self.process_airport(icao, airport_reviews, ...)
                        
                        metrics.airports_processed += 1
                        metrics.reviews_extracted += len(airport_reviews)
                        
                        # Update LLM metrics from extractor
                        if hasattr(self.extractor, 'token_usage'):
                            metrics.llm_calls += getattr(self.extractor, 'llm_calls', 0)
                            metrics.llm_input_tokens += self.extractor.token_usage.get('input_tokens', 0)
                            metrics.llm_output_tokens += self.extractor.token_usage.get('output_tokens', 0)
                        
                        logger.info("airport_processed", icao=icao)
                        
                    except Exception as e:
                        error_msg = str(e)
                        logger.error("airport_failed", icao=icao, error=error_msg)
                        
                        metrics.errors += 1
                        metrics.failed_icaos.append(icao)
                        metrics.error_details.append((icao, error_msg))
                        
                        # Handle based on failure mode
                        if self.failure_mode == FailureMode.FAIL_FAST:
                            raise BuildError(f"Failed to process airport {icao}: {e}") from e
                        # Otherwise continue (CONTINUE or SKIP mode)
            
            # Write metadata (versions, timestamps)
            self.storage.write_meta_info("build_timestamp", datetime.utcnow().isoformat())
            self.storage.write_meta_info("source_version", reviews_source.get_source_version())
            
            # Calculate final metrics
            metrics.end_time = datetime.utcnow()
            metrics.calculate_duration()
            metrics.llm_total_tokens = metrics.llm_input_tokens + metrics.llm_output_tokens
            # Calculate cost based on model pricing (if available)
            
            # Log completion
            logger.info(
                "build_complete",
                airports_processed=metrics.airports_processed,
                airports_total=metrics.airports_total,
                errors=metrics.errors,
                duration_seconds=metrics.duration_seconds,
                llm_cost_usd=metrics.llm_cost_usd
            )
            
            success = metrics.errors == 0 or self.failure_mode != FailureMode.FAIL_FAST
            return BuildResult(success=success, metrics=metrics)
            
        except Exception as e:
            logger.error("build_failed", error=str(e))
            metrics.end_time = datetime.utcnow()
            metrics.calculate_duration()
            return BuildResult(
                success=False,
                metrics=metrics,
                error=e,
                error_message=str(e)
            )
    
    def process_airport(
        self,
        icao: str,
        reviews: List[RawReview],
        aip_data: Optional[Dict] = None,
        airport_stats: Optional[Dict] = None
    ) -> None:
        """
        Process a single airport: extract, aggregate, summarize, score, write.
        
        This is the core per-airport processing logic.
        All operations are within the storage transaction context.
        
        Args:
            icao: Airport ICAO code
            reviews: List of reviews for this airport
            aip_data: Optional AIP data from euro_aip.sqlite
            airport_stats: Optional stats from airfield.directory individual JSON:
                - average_rating: float
                - landing_fees: Dict by aircraft type
                - fuel_prices: Dict
        
        Raises:
            BuildError if processing fails (extraction, aggregation, etc.)
        """
        try:
            # Extract tags from reviews (with retry logic)
            # Track LLM token usage
            # Aggregate tags → feature scores
            # Incorporate airport_stats (average_rating, landing fees) if available
            # Aggregate landing fees into fee bands:
            #   - Map aircraft type (e.g., "C172", "SR22") to known MTOW using standard mapping
            #   - Map MTOW to appropriate fee_band_* field (0-749kg, 750-1199kg, 1200-1499kg, 1500-1999kg, 2000-3999kg, 4000+kg)
            #   - Do NOT parse title field (varies by airport, not standardized)
            #   - If multiple aircraft types map to same band, use median or representative fee
            # Generate summary (with retry logic)
            # Compute persona scores
            # Build AirportStats (include rating_avg, fee_band_* from aggregated fees)
            # Write to storage (within transaction)
            # Update last_processed_timestamp for this airport
            # Use max(review.timestamp) as the processed timestamp
            max_review_time = max(
                (parse_timestamp(r.timestamp) for r in reviews if r.timestamp),
                default=datetime.utcnow()
            )
            self.storage.update_last_processed_timestamp(icao, max_review_time)
        except Exception as e:
            logger.error("airport_processing_failed", icao=icao, error=str(e))
            raise BuildError(f"Failed to process airport {icao}: {e}") from e
    
    def fetch_aip_data(self, icao: str, euro_aip_path: Path) -> Optional[Dict]:
        """
        Fetch AIP data for an airport from euro_aip.sqlite.
        
        Returns:
            Dict with:
                - has_ifr_procedures: bool (True if instrument approach procedures exist)
                - ifr_procedure_types: List[str] (e.g., ['ILS', 'RNAV', 'VOR'])
                - runway_length_m: Optional[float]
                - has_customs: bool
                - etc.
        
        **Important:** `has_ifr_procedures` checks for instrument approach procedures 
        (ILS, RNAV, VOR, etc.) from the AIP database, NOT just IFR flight plan acceptance. 
        This is used to set the `ifr_procedure_available` flag in `ga_airfield_stats`. An airfield 
        may accept IFR flight plans but not have published instrument approaches.
        """
        # ATTACH euro_aip
        # Query airport, procedures (filter for instrument approaches), runways
        # Check for instrument approach procedures (ILS, RNAV, VOR, etc.)
        # Return structured dict with has_ifr_procedures flag
```

### 10.2 Review Source Interface

```python
# Abstract interface for review sources

class RawReview(BaseModel):
    """Raw review from source."""
    icao: str
    review_text: str  # Primary language text
    review_id: str  # Unique ID (format: "ICAO#sha256" for airfield.directory)
    rating: Optional[float] = None  # 1-5 scale, can be null
    timestamp: Optional[str] = None  # ISO format: "2025-08-15T00:00:00.000Z"
    language: str = "EN"  # Language code of review_text (EN, DE, IT, FR, ES, NL)
    ai_generated: bool = False  # Whether review is AI-generated
    likes_count: int = 0  # Number of likes (for future use)

class ReviewSource(ABC):
    """Abstract interface for review sources."""
    
    @abstractmethod
    def get_reviews(self) -> List[RawReview]:
        """Load all reviews from source."""
        pass
    
    @abstractmethod
    def get_source_version(self) -> str:
        """Return version identifier for this source snapshot."""
        pass

# Example implementations (not in this library, but interface defined):
# - AirfieldDirectorySource (scrapes/API from airfield.directory)
# - CSVReviewSource (reads from CSV export)
# - JSONReviewSource (reads from JSON file)
# - CompositeReviewSource (combines multiple sources)
# - DatabaseReviewSource (reads from existing ga_meta.sqlite)
# - Custom API sources (future: other review platforms)
```

**Design Decision: Source Abstraction**

- **Why:** Allows different review sources (airfield.directory, manual CSV, future APIs)
- **Implementation:** Abstract base class with concrete implementations outside library
- **CLI tool** will provide a concrete implementation (e.g., `CSVReviewSource`)
- **Multiple sources:** Can combine sources using `CompositeReviewSource` (see below)

### 10.2.1 Combining Multiple Sources

```python
# Composite pattern for combining multiple review sources

class CompositeReviewSource(ReviewSource):
    """
    Combines reviews from multiple sources.
    
    Useful for:
        - Merging airfield.directory + manual CSV reviews
        - Combining different API sources
        - Adding custom reviews to existing data
    """
    
    def __init__(self, sources: List[ReviewSource]):
        """
        Initialize with list of sources.
        
        Args:
            sources: List of ReviewSource instances to combine
        """
        # Store sources list
    
    def get_reviews(self) -> List[RawReview]:
        """
        Combine reviews from all sources.
        
        Handles:
            - Deduplication by review_id (if same ID appears in multiple sources)
            - Merging reviews for same airport
            - Preserving source metadata if needed
        
        Returns:
            Combined list of RawReview objects
        """
        # For each source, call get_reviews()
        # Combine lists
        # Deduplicate by review_id (keep first occurrence or merge)
        # Return combined list
    
    def get_source_version(self) -> str:
        """
        Return composite version string.
        
        Returns:
            String like "composite:airfield.directory-2025-11-23+csv-2025-01-15"
        """
        # Combine source versions from all sources
        # Return composite string
```

**Usage Example:**

```python
# In CLI tool or builder:
airfield_source = AirfieldDirectorySource(export_path)
csv_source = CSVReviewSource(csv_path)
composite = CompositeReviewSource([airfield_source, csv_source])

builder = GAFriendlinessBuilder(settings)
builder.build(composite, euro_aip_path)
```

**Design Decision: Extensibility**

- **Adding new sources:** Simply implement the `ReviewSource` interface
- **No library changes needed:** New sources can be added in CLI tool or separate module
- **Deduplication:** `CompositeReviewSource` handles deduplication by `review_id`
- **Source priority:** In composite, first source takes precedence for duplicate IDs
- **Future sources could include:**
  - Other review platforms/APIs
  - Manual curation sources
  - Scraped data (with proper licensing)
  - User-submitted reviews from your own platform

### 10.3 AirfieldDirectorySource Implementation

Based on the actual airfield.directory API structure, here's the concrete implementation:

```python
# In tools/build_ga_friendliness.py or shared/ga_friendliness/sources.py

class AirfieldDirectorySource(ReviewSource):
    """
    Loads reviews from airfield.directory bulk export.
    
    Supports:
        - Individual airport JSON: https://airfield.directory/airfield/{ICAO}.json
        - Bulk export: S3 bucket airfield-directory-pirep-export
        - Format: airfield-directory-pireps-export-latest.json.gz
    """
    
    def __init__(
        self,
        export_path: Path,  # Path to .json or .json.gz file
        filter_ai_generated: bool = True,  # Filter out AI-generated reviews
        preferred_language: str = "EN"  # Primary language for review text
    ):
        """
        Initialize source.
        
        Args:
            export_path: Path to bulk export JSON file
            filter_ai_generated: If True, exclude reviews with ai_generated=true
            preferred_language: Language code (EN, DE, IT, FR, ES, NL) for review text
        """
        # Store config
        # Load JSON (handle .gz if needed)
        # Parse structure
    
    def get_reviews(self) -> List[RawReview]:
        """
        Load all reviews from bulk export.
        
        Structure:
            {
                "metadata": {...},
                "pireps": {
                    "ICAO": {
                        "ICAO#id": {
                            "id": "...",
                            "content": {"EN": "...", "DE": "...", ...},
                            "language": "EN",
                            "rating": 4 or null,
                            "likes_count": 0,
                            "user": {...},
                            "created_at": "2025-08-15T00:00:00.000Z",
                            "updated_at": "...",
                            "ai_generated": true/false
                        }
                    }
                }
            }
        
        Returns:
            List of RawReview objects, one per PIREP
        """
        # Iterate through pireps dict
        # For each ICAO, iterate through reviews
        # Filter ai_generated if configured
        # Extract review_text from content[preferred_language] or fallback
        # Map to RawReview:
        #   - icao: from outer key
        #   - review_text: content[preferred_language] or first available
        #   - review_id: id field
        #   - rating: rating field (can be null)
        #   - timestamp: created_at or updated_at
        # Return list
    
    def get_source_version(self) -> str:
        """
        Extract version from export metadata.
        
        Returns:
            Version string like "airfield.directory-2025-11-23"
        """
        # Read metadata.export_date
        # Format as "airfield.directory-YYYY-MM-DD"
        # Return
    
    def get_airport_stats(self, icao: str) -> Optional[Dict]:
        """
        Get airport-level stats from individual airport JSON.
        
        Note: This requires fetching individual airport JSON files.
        For bulk processing, this would be called separately if needed.
        
        Returns:
            Dict with:
                - average_rating: float (from airfield.data.average_rating)
                - landing_fees: Dict by aircraft type (from aerops.data.landing_fees)
                    - Key: aircraft type (e.g., "C172", "SR22")
                    - Value: List of fee dicts with structure: `[{"lineNet": ..., "price": ..., "tax": ..., "title": ...}]`
                    - **Note:** The `title` field is NOT used for mapping - it varies by airport
                - fuel_prices: Dict (from aerops.data.fuel_prices)
        
        **Fee Band Mapping:**
        Landing fees from airfield.directory are organized by aircraft type (e.g., "C172", "SR22").
        The title field is NOT standardized and varies by airport (e.g., "MTOW bis 750kg" vs "MTOW up to 1499kg").
        Therefore, map aircraft type → known MTOW → fee band:
            - Use aircraft type key to look up MTOW from standard mapping
            - Map MTOW to appropriate fee band (0-749kg, 750-1199kg, 1200-1499kg, 1500-1999kg, 2000-3999kg, 4000+kg)
            - See section 9.0 for detailed mapping logic
        """
        # Fetch https://airfield.directory/airfield/{ICAO}.json
        # Extract stats
        # Return dict
```

**Key Implementation Details:**

1. **Multi-language handling:**
   - Reviews have `content` dict with multiple languages (EN, DE, IT, FR, ES, NL)
   - Use `preferred_language` parameter, fallback to first available
   - Store primary language in `RawReview` for reference

2. **AI-generated filtering:**
   - Reviews have `ai_generated` boolean field
   - Default to filtering these out (can be configured)
   - Matches the jq filter pattern in documentation

3. **Rating handling:**
   - `rating` can be `null` (especially for AI-generated reviews)
   - Store as `Optional[float]` in `RawReview`
   - Airport-level `average_rating` available in individual airport JSON

4. **Landing fees:**
   - Available in `aerops.data.landing_fees` by aircraft type (PC12, DA42, C172, A210, etc.)
   - **Important:** The `title` field is NOT standardized and varies by airport (e.g., EDAZ uses "MTOW bis 750kg", EGMC uses "MTOW up to 1499kg")
   - **Solution:** Use aircraft type key (e.g., "C172", "SR22") to look up known MTOW, then map to fee band
   - Mapping from aircraft type → MTOW → fee band:
     - A210 (~600kg) → `fee_band_0_749kg`
     - C172 (~1157kg) → `fee_band_750_1199kg`
     - SR22 (~1542kg) → `fee_band_1200_1499kg`
     - DA42 (~2000kg) → `fee_band_1500_1999kg`
     - TBM850 (~3350kg) → `fee_band_2000_3999kg`
     - C510 (~4100kg) → `fee_band_4000_plus_kg`
     - PC12 (~4740kg) → `fee_band_4000_plus_kg`
   - Can be used to populate `ga_landing_fees` table (detailed) and `ga_airfield_stats` (aggregated bands)
   - Fees have structure: `{"lineNet": ..., "price": ..., "tax": ..., "title": ...}`
   - Use `lineNet` (net price) or `price` (with tax) depending on requirements
   - See section 9.0 for the complete aircraft type → MTOW mapping table

5. **Bulk export format:**
   - Nested structure: `pireps[ICAO][review_id]`
   - Need to flatten to list of reviews
   - Metadata includes export date for versioning

**Updated RawReview Model:**

```python
class RawReview(BaseModel):
    """Raw review from source."""
    icao: str
    review_text: str  # Primary language text
    review_id: str  # Unique ID (format: "ICAO#sha256")
    rating: Optional[float] = None  # 1-5 scale, can be null
    timestamp: Optional[str] = None  # ISO format: "2025-08-15T00:00:00.000Z"
    language: str = "EN"  # Language code of review_text
    ai_generated: bool = False  # Whether review is AI-generated
    likes_count: int = 0  # Number of likes
```

---

## 11. CLI Tool

### 11.1 CLI Structure (`tools/build_ga_friendliness.py`)

```python
# tools/build_ga_friendliness.py - CLI tool for rebuilding ga_meta.sqlite

def main():
    """
    CLI entry point.
    
    Usage:
        # From airfield.directory bulk export:
        python tools/build_ga_friendliness.py \
            --airfield-directory-export path/to/airfield-directory-pireps-export-latest.json.gz \
            --euro-aip-db path/to/euro_aip.sqlite \
            --ga-meta-db path/to/ga_meta.sqlite \
            --ontology data/ontology.json \
            --personas data/personas.json \
            [--filter-ai-generated] \
            [--preferred-language EN] \
            [--llm-model gpt-4o-mini] \
            [--confidence-threshold 0.5] \
            [--batch-size 50] \
            [--cache-dir path/to/cache] \
            [--force-refresh] \
            [--never-refresh] \
            [--incremental] \
            [--since YYYY-MM-DD] \
            [--icaos ICAO1,ICAO2,...] \
            [--failure-mode {continue,fail_fast,skip}] \
            [--metrics-output path/to/metrics.json] \
            [--euro-aip-db path/to/euro_aip.sqlite] \
            [--parse-aip-rules]
        
        # From CSV (for testing/manual data):
        python tools/build_ga_friendliness.py \
            --reviews-csv path/to/reviews.csv \
            --ga-meta-db path/to/ga_meta.sqlite \
            ...
        
        # Combining multiple sources:
        python tools/build_ga_friendliness.py \
            --airfield-directory-export path/to/airfield-export.json.gz \
            --reviews-csv path/to/additional-reviews.csv \
            --ga-meta-db path/to/ga_meta.sqlite \
            ...
    """
    # Parse arguments
    # Load settings (merge CLI args with env vars)
    # Create ReviewSource based on input type:
    #   - If --airfield-directory-export: AirfieldDirectorySource
    #   - If --reviews-csv: CSVReviewSource
    # Parse failure_mode from args (default: continue)
    # Create GAFriendlinessBuilder with failure_mode
    # Call builder.build() with:
    #   - reviews_source
    #   - euro_aip_path (if --euro-aip-db provided)
    #   - parse_aip_rules (if --parse-aip-rules flag set)
    # Print summary with metrics:
    #   - Success/failure status
    #   - Airports processed/total
    #   - Reviews extracted/total
    #   - LLM usage (calls, tokens, cost)
    #   - Errors (count, failed ICAOs)
    #   - Duration
    # Write metrics to JSON file if --metrics-output provided
    # Exit with appropriate code (0 for success, 1 for failure)

def create_airfield_directory_source(
    export_path: Path,
    filter_ai_generated: bool = True,
    preferred_language: str = "EN"
) -> ReviewSource:
    """
    Create ReviewSource from airfield.directory bulk export.
    
    Args:
        export_path: Path to .json or .json.gz file
        filter_ai_generated: Filter out AI-generated reviews
        preferred_language: Language code for review text
    """
    # Create AirfieldDirectorySource instance
    # Return

def create_csv_review_source(csv_path: Path) -> ReviewSource:
    """
    Create ReviewSource from CSV file.
    
    CSV format (expected):
        icao,review_text,review_id,rating,timestamp,language,ai_generated
        LFQQ,"Great airport...",rev_123,4.5,2025-01-15T10:00:00Z,EN,false
    """
    # Read CSV
    # Parse rows into RawReview objects
    # Return ReviewSource implementation

def create_composite_source(
    sources: List[ReviewSource]
) -> ReviewSource:
    """
    Create composite source from multiple sources.
    
    Args:
        sources: List of ReviewSource instances to combine
    
    Returns:
        CompositeReviewSource that merges all sources
    """
    # Create CompositeReviewSource
    # Return

def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse ISO format timestamp string to datetime.
    
    Handles various ISO formats:
        - "2025-08-15T00:00:00.000Z"
        - "2025-08-15 00:00:00 UTC"
        - etc.
    """
    # Parse ISO format
    # Return datetime object

# Additional CLI commands (future):
# - validate-ontology: Validate ontology.json
# - validate-personas: Validate personas.json
# - compute-scores: Recompute scores for existing ga_meta.sqlite (without re-extraction)

def print_build_summary(result: BuildResult) -> None:
    """
    Print human-readable build summary to console.
    
    Includes:
        - Success/failure status
        - Processing statistics
        - LLM usage and costs
        - Error summary
        - Duration
    """
    # Format and print summary
    # Use rich or similar for nice formatting

def save_metrics_json(result: BuildResult, output_path: Path) -> None:
    """
    Save build metrics to JSON file.
    
    Args:
        result: BuildResult to serialize
        output_path: Path to output JSON file
    """
    # Convert result to dict
    # Write JSON file
    # Pretty-print for readability
```

**Metrics Output Format:**

The `--metrics-output` flag writes a JSON file with the following structure:

```json
{
  "success": true,
  "metrics": {
    "airports_processed": 150,
    "airports_total": 150,
    "reviews_extracted": 1250,
    "reviews_total": 1250,
    "llm_calls": 2500,
    "llm_input_tokens": 125000,
    "llm_output_tokens": 15000,
    "llm_total_tokens": 140000,
    "llm_cost_usd": 2.50,
    "errors": 0,
    "failed_icaos": [],
    "error_details": [],
    "cache_hits": 120,
    "cache_misses": 30,
    "start_time": "2025-11-23T10:00:00Z",
    "end_time": "2025-11-23T10:45:00Z",
    "duration_seconds": 2700.0
  },
  "error": null,
  "error_message": null
}
```

**Failure Mode Options:**

- `continue` (default): Continue processing on errors, collect all failures in metrics
- `fail_fast`: Stop immediately on first error, raise exception
- `skip`: Same as continue, but clearer intent (skip failed airports, continue with others)

**Design Decision: CLI Tool Location**

- **Option A:** In `tools/` directory (alongside `aipexport.py`, `foreflight.py`)
  - **Pros:** Consistent with existing tooling, easy to find
  - **Cons:** None
- **Option B:** In `shared/ga_friendliness/cli.py`
  - **Pros:** Co-located with library
  - **Cons:** Breaks pattern of tools/ directory
- **Choice:** Option A (`tools/build_ga_friendliness.py`)

---

## 12. Integration with euro_aip

### 12.1 Dependency Management

**Decision:** `ga_friendliness` library should **not** have a hard dependency on `euro_aip`.

**Rationale:**
- Design principle: ga_meta.sqlite is independent
- Runtime consumers may not need euro_aip
- Use ATTACH DATABASE pattern for joint queries

**How it works:**
- `ga_friendliness` uses **ICAO codes** as the linking key (strings)
- When AIP data is needed (for feature engineering), caller provides it
- Storage layer can ATTACH euro_aip.sqlite for queries, but doesn't require it

### 12.2 Integration Points

```python
# In builder.py or feature mapper:

def fetch_aip_data_for_features(icao: str, euro_aip_path: Path) -> Optional[Dict]:
    """
    Fetch AIP data needed for feature engineering.
    
    Uses euro_aip library if available, otherwise queries SQL directly.
    
    Returns:
        Dict with:
            - has_ifr_procedures: bool
            - runway_length_m: Optional[float]
            - has_customs: bool
            - etc.
    """
    # Try to import euro_aip (optional dependency)
    # If available, use DatabaseStorage to load airport
    # Otherwise, query SQL directly via ATTACH
    # Return structured dict
```

**Design Decision: Optional euro_aip Import**

- **Pattern:** Try/except import, fallback to direct SQL
- **Pros:** Works with or without euro_aip installed
- **Cons:** Slightly more complex code
- **Alternative:** Always use direct SQL (simpler, but less type-safe)
- **Choice:** Try/except pattern for flexibility

---

## 13. Web App Integration (Future)

### 13.1 API Endpoints (Conceptual)

```python
# web/server/api/ga_friendliness.py (future)

@router.get("/airports/{icao}/ga-friendliness")
def get_airport_ga_friendliness(
    icao: str,
    persona: Optional[str] = None
) -> Dict:
    """
    Get GA friendliness data for an airport.
    
    Returns:
        - Base feature scores
        - Persona-specific score (if persona provided)
        - Summary text and tags
        - Review stats
    """
    # ATTACH both databases
    # Query ga_airfield_stats, ga_review_summary
    # If persona provided, compute score (or read from denormalized column)
    # Return JSON

@router.get("/route/ga-friendly-airports")
def find_ga_friendly_along_route(
    route: List[Tuple[float, float]],  # lat/lon points
    corridor_width_nm: float = 20,
    persona: str = "ifr_touring_sr22",
    segment_length_nm: int = 100
) -> Dict:
    """
    Find GA-friendly airports along a route.
    
    Uses euro_aip for spatial queries, joins to ga_meta for scores.
    """
    # Use euro_aip spatial queries (R-tree)
    # Join to ga_airfield_stats
    # Compute persona scores
    # Segment by distance
    # Return structured response
```

### 13.2 Integration with Existing Tools

```python
# In shared/airport_tools.py (future extension)

def find_airports_near_route_with_ga_friendliness(
    context: ToolContext,
    route: List[Tuple[float, float]],
    persona: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Extend existing find_airports_near_route to include GA friendliness.
    
    If ga_meta.sqlite is available, attach it and include scores.
    """
    # Call existing find_airports_near_route logic
    # If ga_meta.sqlite exists, ATTACH and join
    # Add ga_friendliness fields to response
    # Return enhanced result
```

**Design Decision: Backward Compatibility**

- Existing tools should work **without** ga_meta.sqlite
- GA friendliness is **opt-in** enhancement
- Use LEFT JOIN so airports without GA data still appear

---

## 13.1 Incremental Update Strategy

### 13.1.1 Change Detection Methods

The incremental update system uses **multiple strategies** to detect changes:

1. **Review ID Tracking:**
   - Store processed `review_id`s in `ga_review_ner_tags` table
   - Compare incoming reviews against stored review_ids
   - New review_ids → new reviews to process

2. **Timestamp Comparison:**
   - Track `last_processed_timestamp` per airport in `ga_meta_info`
   - Compare review timestamps against last processed time
   - Updated reviews (same ID, newer timestamp) → need reprocessing

3. **Date Filtering:**
   - `--since` flag filters reviews by date before change detection
   - Useful for processing only recent reviews

### 13.1.2 Storage Strategy

**Where to track processed reviews:**

- **Option A:** Use `ga_review_ner_tags.review_id` (already stored)
  - **Pros:** No extra table, review_ids already indexed
  - **Cons:** Need to query distinct review_ids per airport
  
- **Option B:** Separate `ga_processed_reviews` table
  - **Pros:** Explicit tracking, faster lookups
  - **Cons:** Extra table, more complexity

**Choice:** Option A (use existing `ga_review_ner_tags` table)
- Query: `SELECT DISTINCT review_id FROM ga_review_ner_tags WHERE icao = ?`
- Efficient with index on `(icao, review_id)`

**Where to track last processed time:**

- Store in `ga_meta_info` with key `last_processed_{icao}`
- Also update `ga_airfield_stats.last_review_utc` (max of all review timestamps)
- Allows quick lookup without querying all reviews

### 13.1.3 Update Scenarios

**Scenario 1: New Review Added**
- Review with new `review_id` appears in source
- `has_changes()` detects new review_id
- Process new review, update timestamp

**Scenario 2: Review Updated**
- Review with existing `review_id` has newer `timestamp`
- `has_changes()` detects timestamp > last_processed
- Reprocess review (may have different content/rating)

**Scenario 3: Review Deleted**
- Review removed from source (not in new export)
- Current design: Keep old tags in database
- Future: Could add "deleted" flag or cleanup process

**Scenario 4: Airport Never Processed**
- Airport not in `ga_airfield_stats`
- `has_changes()` returns True (never processed)
- Process all reviews for airport

### 13.1.4 Implementation Details

```python
# Example: has_changes() logic flow

def has_changes(icao, reviews, since=None):
    # 1. Check if airport exists
    if not airport_exists(icao):
        return True  # New airport
    
    # 2. Get last processed timestamp
    last_processed = get_last_processed_timestamp(icao)
    if last_processed is None:
        return True  # Never processed
    
    # 3. Get processed review_ids
    processed_ids = get_processed_review_ids(icao)
    
    # 4. Filter by since date if provided
    if since:
        reviews = [r for r in reviews if r.timestamp > since]
    
    # 5. Check for new reviews
    for review in reviews:
        if review.review_id not in processed_ids:
            return True  # New review
    
    # 6. Check for updated reviews
    for review in reviews:
        if review.review_id in processed_ids:
            if review.timestamp > last_processed:
                return True  # Review updated
    
    return False  # No changes
```

### 13.1.5 Performance Considerations

**Indexing:**
- Index on `ga_review_ner_tags(icao, review_id)` for fast lookups
- Index on `ga_review_ner_tags(icao, created_utc)` for timestamp queries

**Query Optimization:**
- Use `SELECT DISTINCT review_id` instead of loading all tags
- Cache processed_ids per airport during build (avoid repeated queries)
- Batch check multiple airports in single query if possible

**Incremental vs Full Rebuild:**
- **Incremental:** Fast for small changes, requires change detection logic
- **Full rebuild:** Simpler, always correct, but slower
- **Recommendation:** Use incremental for regular updates, full rebuild periodically (e.g., weekly)

### 13.1.6 Edge Cases

1. **Multiple Sources:**
   - Different sources may have same review_id format
   - Solution: Prefix review_id with source identifier (e.g., "airfield.directory#...")

2. **Timestamp Precision:**
   - Reviews may have timestamps in different formats/timezones
   - Solution: Normalize to UTC, parse ISO format consistently

3. **Missing Timestamps:**
   - Some reviews may not have timestamps
   - Solution: Treat as "always process" or use review_id only

4. **Clock Skew:**
   - System clock vs source timestamps may differ
   - Solution: Use source timestamps, not system time

---

## 14. Testing Strategy

### 14.1 Unit Tests

```python
# tests/ga_friendliness/test_ontology.py
def test_ontology_validation()
def test_label_lookup()

# tests/ga_friendliness/test_personas.py
def test_persona_score_computation()
def test_weight_validation()

# tests/ga_friendliness/test_features.py
def test_cost_score_mapping()
def test_hassle_score_mapping()

# tests/ga_friendliness/test_nlp_extractor.py
def test_review_extraction()  # Mock LLM
def test_batch_extraction()

# tests/ga_friendliness/test_storage.py
def test_schema_creation()
def test_write_read_airfield_stats()
```

### 14.2 Integration Tests

```python
# tests/ga_friendliness/test_builder.py
def test_full_pipeline_with_mock_reviews()
def test_idempotent_rebuild()

# tests/ga_friendliness/test_integration_euro_aip.py
def test_joint_query_with_euro_aip()
def test_feature_engineering_with_aip_data()
```

### 14.3 Golden Data Tests

```python
# tests/ga_friendliness/test_golden_airports.py
def test_known_ga_friendly_airport_scores()
def test_known_expensive_airport_scores()

# Use a small set of airports with known characteristics
# Verify scores match expectations
```

---

## 15. Key Design Decisions Summary

### 15.1 Library Structure
- **Choice:** Standalone library in `shared/ga_friendliness/`
- **Rationale:** Clean separation, reusable, follows existing patterns

### 15.2 Configuration Format
- **Choice:** JSON (not YAML)
- **Rationale:** Simpler parsing, no extra dependency, consistent with project

### 15.3 LLM Framework
- **Choice:** LangChain 1.0
- **Rationale:** Already in project, modern API, good Pydantic integration

### 15.4 Database Linking
- **Choice:** ICAO codes as external keys, ATTACH DATABASE for queries
- **Rationale:** No hard dependency on euro_aip, flexible runtime usage

### 15.5 Persona Scores Storage
- **Choice:** Hybrid: one primary persona denormalized, others computed at runtime
- **Rationale:** Balance between query performance and flexibility

### 15.6 Review Source Abstraction
- **Choice:** Abstract ReviewSource interface, concrete implementations in CLI
- **Rationale:** Library stays source-agnostic, easy to add new sources

### 15.7 Feature Engineering AIP Integration
- **Choice:** Optional AIP data parameter, fetched by builder when available
- **Rationale:** Works with or without euro_aip, flexible

### 15.8 Batch Processing
- **Choice:** Sequential with LangChain batch() for parallelization
- **Rationale:** Better error handling, can optimize later

### 15.9 Caching Strategy
- **Choice:** Independent `CachedDataLoader` utility (not reusing euro_aip's CachedSource)
- **Rationale:** 
  - Maintains library independence (design principle)
  - Simpler implementation (JSON only, no CSV/PDF)
  - Supports gzip for large files
  - Follows same conceptual pattern (familiar to developers)
- **Caching targets:**
  - Bulk export from S3 (7-day cache)
  - Individual airport JSON (30-day cache)
- **CLI flags:** `--force-refresh`, `--never-refresh`, `--cache-dir`

### 15.10 Error Handling & Resilience
- **Choice:** Exception hierarchy with specific error types
- **Rationale:** Clear error handling, better debugging, retry logic support
- **Implementation:** Base `GAFriendlinessError` with domain-specific subclasses

### 15.11 Transaction Management
- **Choice:** Context manager pattern for transactions
- **Rationale:** Atomic operations, automatic rollback on errors, thread-safe
- **Implementation:** Storage class supports `with` statement, batch writes

### 15.12 Configurable Feature Mappings
- **Choice:** Load mappings from JSON with hard-coded defaults
- **Rationale:** Easy to modify without code changes, versioned config
- **Implementation:** `feature_mappings.json` with validation against ontology

### 15.13 Incremental Updates
- **Choice:** Support incremental mode with change detection
- **Rationale:** Efficient updates when only some airports change, faster rebuilds
- **Implementation:** `has_changes()` method, `--incremental` CLI flag, `--since` date filter

### 15.14 Schema Versioning
- **Choice:** Track schema version, support migrations
- **Rationale:** Safe schema evolution, backward compatibility
- **Implementation:** Version in `ga_meta_info`, migration framework

### 15.15 Resource Management
- **Choice:** Context managers for database connections and LLM clients
- **Rationale:** Automatic cleanup, proper resource handling
- **Implementation:** `__enter__`/`__exit__` methods, `close()` methods

### 15.16 Dependency Injection
- **Choice:** Optional dependency injection in Builder constructor
- **Rationale:** Testability with mocks, flexible component replacement
- **Implementation:** Optional parameters with defaults that create dependencies

### 15.17 Structured Logging
- **Choice:** Use structlog for structured logging with context
- **Rationale:** Better observability, easier debugging, progress tracking
- **Implementation:** Structured log events with context (icao, review_count, etc.)

### 15.18 Build Metrics & Partial Failure Handling
- **Choice:** Comprehensive metrics tracking with configurable failure modes
- **Rationale:** 
  - Monitor build progress and costs
  - Flexible error handling (continue vs fail-fast)
  - Detailed error reporting for debugging
- **Implementation:**
  - `BuildMetrics` dataclass with LLM usage, timing, errors
  - `FailureMode` enum (CONTINUE, FAIL_FAST, SKIP)
  - Metrics export to JSON
  - Partial failure support (continue on individual airport errors)

---

## 16. Open Questions & Decisions

*Note: As decisions are made, replace "Suggestion:" with "Decision:" and add rationale if different from suggestion.*

### 16.1 Non-ICAO Fields
- **Question:** How to handle non-ICAO strips?
- **Suggestion:** Start with ICAO-only, add pseudo-ICAO mapping later if needed
- **Decision:** Start with ICAO only

### 16.2 Missing Data Handling
- **Question:** Neutral score (0.5) vs NULL for airports without reviews?
- **Suggestion:** NULL with flag, let UI decide how to display
- **Decision:**  NULL with flag, so we can decide later

### 16.3 Persona Explosion
- **Question:** How many personas to support in UI?
- **Suggestion:** Start with 3 (IFR touring, VFR budget, training), add more as needed
- **Decision:** yes start with these 3

### 16.4 Learned Weights
- **Question:** ML-based persona weights from user feedback?
- **Suggestion:** Phase 2 feature, keep hand-tuned weights for now
- **Decision:** yes, hand-tuned for now, we'll see later

### 16.5 Review Text Storage
- **Question:** Store raw review text excerpts or only tags?
- **Suggestion:** Start with tags only (privacy/licensing), add excerpts later if needed
- **Decision:** tag only

---

## 17. Implementation Phases

### Phase 1: Core Infrastructure & Caching
1. Create library structure
2. Implement exception hierarchy
3. Implement models (Pydantic)
4. Implement caching utility (CachedDataLoader)
5. Implement database schema with versioning
6. Implement storage with transaction support
7. Implement ontology and persona loading
8. Implement feature mappings loading
9. Unit tests for core components

### Phase 2: NLP Pipeline
1. Implement ReviewExtractor with LangChain (with retry logic)
2. Implement TagAggregator
3. Implement SummaryGenerator (with retry logic)
4. Add token usage tracking
5. Integration tests with mock LLM

### Phase 3: Feature Engineering
1. Implement FeatureMapper with configurable mappings
2. Implement scoring functions
3. Integration with optional AIP data
4. Add feature mapping validation
5. Golden data tests

### Phase 4: Builder & CLI
1. Implement GAFriendlinessBuilder with dependency injection
2. Add incremental update support
3. Add structured logging and progress tracking
4. Implement BuildMetrics and BuildResult classes
5. Add error handling with configurable failure modes
6. Add comprehensive metrics collection (LLM usage, timing, errors)
7. Add metrics export to JSON
8. Implement CSVReviewSource
9. Create CLI tool with all flags (including failure-mode, metrics-output)
10. Add resource management (context managers)
11. End-to-end test with sample data
12. Test failure modes (continue, fail_fast, skip)

### Phase 5: Web Integration (Future)
1. API endpoints
2. Integration with existing tools
3. UI components for displaying scores

---

*End of implementation plan. Ready for review and iteration.*

