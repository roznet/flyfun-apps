# GA Notification Agent Design

## Overview

The GA Notification Agent extracts structured notification requirements (PPR, customs, immigration) from free-text AIP data and produces two outputs:

| Database | Purpose | Mutability |
|----------|---------|------------|
| `ga_notifications.db` | **Factual** extraction - structured rules from AIP | Immutable truth |
| `ga_persona.db` | **Subjective** scores - hassle levels, friendliness | Can change with scoring logic |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA FLOW                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   airports.db                                                                │
│   (aip_entries, std_field_id=302)                                           │
│          │                                                                   │
│          ▼                                                                   │
│   ┌──────────────────┐                                                       │
│   │ NotificationParser │  ◄── configs/ga_notification_agent/default.json    │
│   │   (Waterfall)      │      configs/ga_notification_agent/prompts/        │
│   │                    │                                                     │
│   │  1. Regex patterns │  Fast, high confidence for simple cases            │
│   │  2. Complexity check│  Detect when LLM needed                           │
│   │  3. LLM fallback   │  OpenAI API for complex rules                      │
│   └────────┬───────────┘                                                     │
│            │                                                                 │
│            ▼                                                                 │
│   ParsedNotificationRules                                                    │
│   (List[NotificationRule])                                                   │
│            │                                                                 │
│      ┌─────┴─────┐                                                           │
│      ▼           ▼                                                           │
│ ┌─────────┐  ┌─────────────┐                                                 │
│ │ Batch   │  │ Scorer      │                                                 │
│ │Processor│  │             │                                                 │
│ └────┬────┘  └──────┬──────┘                                                 │
│      │              │                                                        │
│      ▼              ▼                                                        │
│ ga_notifications.db    ga_persona.db                                         │
│ (factual rules)        (hassle scores)                                       │
│      │                                                                       │
│      ▼                                                                       │
│ NotificationService                                                          │
│ (Query API)                                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
shared/ga_notification_agent/
├── __init__.py           # Public exports
├── config.py             # Configuration loader (JSON-based)
├── models.py             # Pydantic models (NotificationRule, HassleScore, etc.)
├── parser.py             # Waterfall parser (regex + LLM)
├── scorer.py             # HassleScore computation
├── batch_processor.py    # Batch extraction to ga_notifications.db
└── service.py            # Query interface for notification data

configs/ga_notification_agent/
├── default.json          # Behavior configuration
└── prompts/
    └── parser_v1.md      # LLM system prompt

tools/
└── build_ga_notifications.py  # CLI tool
```

## Configuration

Following the same pattern as `aviation_agent`, configuration is split:

### Behavior Config (`configs/ga_notification_agent/default.json`)

```json
{
  "version": "1.0",
  "name": "default",
  "llm": {
    "model": "gpt-4o-mini",
    "temperature": 0.0
  },
  "parsing": {
    "use_llm_fallback": true,
    "complexity_threshold": 2,
    "confidence": {
      "h24": 0.95,
      "on_request": 0.90,
      "hours_rules": 0.80,
      "llm_extracted": 0.85
    }
  },
  "prompts": {
    "parser": "prompts/parser_v1.md"
  }
}
```

### Environment Variables (Infrastructure)

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | API key for LLM fallback |
| `GA_NOTIFICATIONS_DB` | Path to output database |
| `AIRPORTS_DB` | Path to source AIP database |

## Waterfall Parsing Strategy

The parser uses a 3-stage waterfall approach:

### Stage 1: Quick Regex Patterns

Fast, high-confidence extraction for simple cases:

| Pattern | Confidence | Example |
|---------|------------|---------|
| H24 | 0.95 | "H24", "Customs H24" |
| On Request | 0.90 | "O/R", "sur demande", "by arrangement" |
| As AD Hours | 0.90 | "As AD hours", "AD OPR HR" |
| Hours Notice | 0.80 | "PPR 24 HR", "PN 48 HR" |
| Business Day | 0.75 | "last working day before 1500" |
| Weekday Rules | 0.80 | "MON-FRI: PPR 24 HR" |

### Stage 2: Complexity Detection

If regex is insufficient, check for complexity indicators:

- Multiple day ranges (3+ day references)
- Schengen-specific conditions
- Multiple time cutoffs
- Long text (>300 chars)
- Conditional language (if/when/except)

If complexity score > threshold (default: 2), proceed to LLM.

### Stage 3: LLM Fallback

For complex cases, use OpenAI structured output:

```python
response = client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": system_prompt},  # From config
        {"role": "user", "content": f"Airport: {icao}\nText: {text}"}
    ],
    response_format=ExtractedRules,  # Pydantic model
    temperature=0,
)
```

## Data Models

### NotificationRule

```python
@dataclass
class NotificationRule:
    rule_type: RuleType              # PPR, CUSTOMS, IMMIGRATION
    notification_type: NotificationType  # HOURS, H24, ON_REQUEST, BUSINESS_DAY
    hours_notice: Optional[int]      # 24, 48, 72
    weekday_start: Optional[int]     # 0=Monday, 6=Sunday
    weekday_end: Optional[int]
    specific_time: Optional[str]     # "1500"
    business_day_offset: Optional[int]  # -1 = last business day
    schengen_only: bool
    non_schengen_only: bool
    includes_holidays: bool
    confidence: float                # 0.0-1.0
    extraction_method: str           # "regex" or "llm"
```

### HassleScore

```python
@dataclass
class HassleScore:
    icao: str
    level: HassleLevel  # NONE, LOW, MODERATE, HIGH, VERY_HIGH
    score: float        # 0.0-1.0
    summary: str
    max_hours_notice: Optional[int]
```

Scoring logic:
| Condition | Level | Score |
|-----------|-------|-------|
| H24 | NONE | 0.0 |
| On Request | LOW | 0.2 |
| ≤12h notice | LOW | 0.25 |
| ≤24h notice | MODERATE | 0.4 |
| ≤48h notice | HIGH | 0.6 |
| >72h notice | VERY_HIGH | 0.9 |

## CLI Tool

```bash
# Build notification database for French airports
python tools/build_ga_notifications.py --prefix LF

# Build for specific airports
python tools/build_ga_notifications.py --icaos LFRG,LFPT,EGLL

# Incremental update (skip existing)
python tools/build_ga_notifications.py --incremental

# Regex-only (no LLM)
python tools/build_ga_notifications.py --no-llm

# Use via data_update.py (preferred — handles --changed mode)
python tools/data_update.py notifications
python tools/data_update.py notifications LF EG  # French and UK only

# Only reprocess airports where AIP text changed (default in data_update.py)
python tools/build_ga_notifications.py --changed

# Filter by multiple prefixes
python tools/build_ga_notifications.py --prefixes LF,EG,ED
```

## Database Schema

### ga_notifications.db (Factual)

```sql
CREATE TABLE ga_notification_requirements (
    id INTEGER PRIMARY KEY,
    icao TEXT UNIQUE,
    rule_type TEXT,           -- "customs", "immigration", "ppr"
    notification_type TEXT,   -- "hours", "h24", "on_request", "business_day"
    hours_notice INTEGER,     -- Max hours required
    weekday_rules TEXT,       -- JSON: {"Mon-Fri": "24h", "Sat-Sun": "48h"}
    schengen_rules TEXT,      -- JSON: {"schengen_only": false, ...}
    summary TEXT,             -- Human-readable summary
    raw_text TEXT,            -- Original AIP text
    confidence REAL,          -- Extraction confidence
    extraction_method TEXT,   -- "regex" or "llm"
    created_utc TEXT
);
```

### ga_notifications.db Metadata

```sql
-- Created by data_update.py after sync; tracks which AIRAC cycle was last applied
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
-- Key: "last_airac_date", Value: "2026-02-19"
```

See [Data Update Pipeline](./DATA_UPDATE_PIPELINE.md) for AIRAC tracking details.

### ga_persona.db (Subjective)

```sql
-- In ga_airfield_stats table
notification_hassle_score REAL  -- 0.0-1.0

-- In ga_aip_rule_summary table
notification_summary TEXT
hassle_level TEXT               -- "none", "low", "moderate", "high", "very_high"
notification_score REAL
```

## Testing

```bash
# Run regex-only tests (default)
pytest tests/ga_notification_agent/

# Run with LLM tests
RUN_PARSER_LLM_TESTS=1 pytest tests/ga_notification_agent/

# Verbose output
pytest tests/ga_notification_agent/ -v -s
```

Test cases in `tests/ga_notification_agent/fixtures/parser_test_cases.json`:

```json
{
  "icao": "LFPT",
  "text": "PPR 24 HR",
  "expected": {
    "notification_type": "hours",
    "hours_notice": 24
  },
  "description": "Simple PPR 24 hours"
}
```

## Usage

### Parsing

```python
from shared.ga_notification_agent import NotificationParser

parser = NotificationParser()  # Uses default config
result = parser.parse("LFRG", "PPR 24 HR")

print(result.rules[0].notification_type)  # NotificationType.HOURS
print(result.rules[0].hours_notice)       # 24
print(result.max_hours_notice)            # 24
```

### Scoring

```python
from shared.ga_notification_agent import NotificationScorer

scorer = NotificationScorer()
scores = scorer.load_and_score_from_airports_db(Path("airports.db"))
scorer.write_to_ga_meta(Path("ga_persona.db"), scores)
```

### Batch Processing

```python
from shared.ga_notification_agent import NotificationBatchProcessor

processor = NotificationBatchProcessor(output_db_path=Path("ga_notifications.db"))
stats = processor.process_airports(
    airports_db_path=Path("airports.db"),
    icao_prefix="LF",
    incremental=True,
)
```

### Querying

```python
from shared.ga_notification_agent.service import NotificationService

service = NotificationService()
info = service.get_notification_info("LFRG")
print(info.get_easiness_score())  # 0-100 scale
```

## Adding New Countries

1. Run the CLI tool with the country prefix:
   ```bash
   python tools/build_ga_notifications.py --prefix ED  # Germany
   ```

2. Review results and add test cases for country-specific patterns:
   ```json
   {
     "icao": "EDDF",
     "text": "German-specific pattern here",
     "expected": { ... },
     "description": "German pattern description"
   }
   ```

3. If regex fails on common patterns, add new regex patterns to `parser.py`

4. Complex patterns will automatically fall back to LLM
