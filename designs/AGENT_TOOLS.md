# Aviation Agent Tools

> Tool catalog, missing_info pattern, and aircraft speeds.

## Quick Reference

| File | Purpose |
|------|---------|
| `shared/airport_tools.py` | MCP tool implementations (single source of truth) |
| `shared/aviation_agent/tools.py` | Tool wrappers for agent |
| `shared/aircraft_speeds.py` | GA aircraft cruise speed lookup |

**Key Exports:**
- `get_shared_tool_specs()` - Tool manifest
- `AIRCRAFT_CRUISE_SPEEDS` - Speed lookup table
- `resolve_cruise_speed()` - Speed resolution

**Prerequisites:** Read `AGENT_ARCHITECTURE.md` first.

---

## Tool Catalog

All tools are defined in `shared/airport_tools.py` as the **single source of truth**.

### Airport Tools

| Tool | Required Args | Optional Args | Returns |
|------|--------------|---------------|---------|
| `search_airports` | `query` | `max_results`, `filters` | List of matching airports |
| `find_airports_near_location` | `location_query` | `max_distance_nm`, `filters`, `max_hours_notice` | Airports near point |
| `find_airports_near_route` | `from_location`, `to_location` | `max_distance_nm`, `filters`, `max_leg_time_hours` | Airports along route |
| `get_airport_details` | `icao_code` | – | Full airport details |
| `get_notification_for_airport` | `icao` | `day_of_week` | PPR/notification info |
| `calculate_flight_distance` | `from_location`, `to_location` | `cruise_speed_kts`, `aircraft_type` | Distance and time |

### AIP Field Tools

| Tool | Required Args | Optional Args | Returns |
|------|--------------|---------------|---------|
| `list_aip_fields` | – | – | Available fields with airport counts |
| `query_aip_fields` | `field` | `country`, `icao_codes`, `changed_since`, `max_results` | Field values + staleness |

See `AIP_FIELD_TOOLS_DESIGN.md` for full details.

### Rules Tools

| Tool | Required Args | Optional Args | Returns |
|------|--------------|---------------|---------|
| `answer_rules_question` | `country_code`, `question` | `tags`, `use_rag` | Answer with citations |
| `browse_rules` | `country_code` | `tags`, `offset`, `limit` | Paginated rules list |
| `compare_rules_between_countries` | `countries` | `category`, `tags` | Comparison data |

---

## Tool-to-UI Mapping

| Tool | `ui_payload.kind` | Visualization Type |
|------|------------------|-------------------|
| `search_airports` | `route` | `markers` |
| `find_airports_near_location` | `route` | `point_with_markers` |
| `find_airports_near_route` | `route` | `route_with_markers` |
| `get_airport_details` | `airport` | `marker_with_details` |
| `get_notification_for_airport` | `airport` | `marker_with_details` |
| `calculate_flight_distance` | `route` | `route` |
| `list_aip_fields` | `data` | – |
| `query_aip_fields` | `data` | – |
| `answer_rules_question` | `rules` | – |
| `browse_rules` | `rules` | – |
| `compare_rules_between_countries` | `rules` | – |

---

## missing_info Pattern

Tools can request additional information via a **generic, reusable pattern**:

### Schema

```python
class MissingInfoItem(TypedDict):
    key: str          # Machine-readable identifier
    reason: str       # Why this info is needed
    prompt: str       # Suggested question for user
    examples: list[str]  # Help user understand what to provide
```

### Tool Response with missing_info

```python
{
    # Partial results (what we could calculate)
    "found": True,
    "distance_nm": 596.4,
    "estimated_time_formatted": None,  # Can't calculate without speed

    # Request for missing info
    "missing_info": [{
        "key": "cruise_speed",
        "reason": "Required to calculate flight time",
        "prompt": "What's your cruise speed or aircraft type?",
        "examples": ["120 knots", "Cessna 172", "SR22"]
    }]
}
```

### How It Works

1. **Tool** returns partial results + `missing_info` array
2. **Formatter** sees `missing_info`, includes prompt in response
3. **User** provides the missing info (e.g., "140 knots")
4. **Planner** recognizes follow-up, re-runs tool with complete params

### Supported Use Cases

**Flight time without speed:**
```python
"missing_info": [{
    "key": "cruise_speed",
    "reason": "Required to calculate flight time",
    "prompt": "What's your cruise speed or aircraft type?",
    "examples": ["120 knots", "Cessna 172", "SR22"]
}]
```

**Ambiguous location:**
```python
"missing_info": [{
    "key": "location_clarification",
    "reason": "Multiple airports match 'Paris'",
    "prompt": "Which Paris airport did you mean?",
    "examples": ["Le Bourget", "LFPB", "the GA-friendly one"]
}]
```

**Time constraint without speed:**
```python
"missing_info": [{
    "key": "cruise_speed",
    "reason": "Required to filter airports within 3h flight time",
    "prompt": "What's your cruise speed to calculate the 3-hour range?",
    "examples": ["120 knots", "Cessna 172"]
}]
```

---

## Aircraft Speed Lookup

Curated lookup table for common GA aircraft:

### AIRCRAFT_CRUISE_SPEEDS

```python
AIRCRAFT_CRUISE_SPEEDS = {
    "c150": {"name": "Cessna 150", "cruise_kts": 105},
    "c152": {"name": "Cessna 152", "cruise_kts": 110},
    "c172": {"name": "Cessna 172", "cruise_kts": 120},
    "c182": {"name": "Cessna 182", "cruise_kts": 145},
    "c206": {"name": "Cessna 206", "cruise_kts": 150},
    "pa28": {"name": "Piper PA-28 Cherokee", "cruise_kts": 125},
    "pa32": {"name": "Piper PA-32 Cherokee Six", "cruise_kts": 150},
    "pa34": {"name": "Piper PA-34 Seneca", "cruise_kts": 180},
    "sr20": {"name": "Cirrus SR20", "cruise_kts": 155},
    "sr22": {"name": "Cirrus SR22", "cruise_kts": 170},
    "s22t": {"name": "Cirrus SR22T", "cruise_kts": 180},
    "da40": {"name": "Diamond DA40", "cruise_kts": 130},
    "da42": {"name": "Diamond DA42", "cruise_kts": 170},
    "tb10": {"name": "Socata TB10 Tobago", "cruise_kts": 130},
    "tb20": {"name": "Socata TB20 Trinidad", "cruise_kts": 155},
    "dr400": {"name": "Robin DR400", "cruise_kts": 125},
}
```

### Speed Resolution Logic

```python
def resolve_cruise_speed(
    cruise_speed_kts: float | None,
    aircraft_type: str | None
) -> tuple[float | None, str | None]:
    """Returns (speed, source_description) or (None, None)."""

    # Explicit speed takes priority
    if cruise_speed_kts:
        return cruise_speed_kts, "provided"

    # Try aircraft lookup
    if aircraft_type:
        normalized = normalize_aircraft_type(aircraft_type)
        data = AIRCRAFT_CRUISE_SPEEDS.get(normalized)
        if data:
            return data["cruise_kts"], f"typical {data['name']} cruise"

    return None, None


def normalize_aircraft_type(aircraft_type: str) -> str:
    """Normalize user input to lookup key."""
    # "Cessna 172" → "c172"
    # "C172" → "c172"
    # "Skyhawk" → "c172"
    normalized = aircraft_type.lower().replace(" ", "").replace("-", "")
    # ... alias handling ...
    return normalized
```

---

## calculate_flight_distance Tool

### Parameters

```python
{
    "from_location": str,      # Required - ICAO or location query
    "to_location": str,        # Required - ICAO or location query
    "cruise_speed_kts": float, # Optional - explicit cruise speed
    "aircraft_type": str,      # Optional - e.g., "c172", "sr22"
}
```

### Response

```python
{
    "from": {"icao": "EGTF", "name": "Fairoaks", "lat": 51.348, "lon": -0.559},
    "to": {"icao": "LFMD", "name": "Cannes-Mandelieu", "lat": 43.542, "lon": 6.953},
    "distance_nm": 596.4,
    "cruise_speed_kts": 120,                    # null if not resolved
    "cruise_speed_source": "typical Cessna 172 cruise",  # or "provided"
    "estimated_time_hours": 4.97,               # null if no speed
    "estimated_time_formatted": "4h 58m",       # null if no speed
    "visualization": {
        "type": "route",
        "route": {"from": {...}, "to": {...}}
    },
    "missing_info": [...]  # Present if speed needed for time calc
}
```

---

## find_airports_near_route Time Constraint

### Additional Parameters

```python
{
    "max_leg_time_hours": float,  # Filter by flight time from departure
    "cruise_speed_kts": float,    # Required if max_leg_time_hours used
    "aircraft_type": str,         # Alternative to cruise_speed_kts
}
```

### Logic

```python
if max_leg_time_hours and cruise_speed_kts:
    max_distance_nm = max_leg_time_hours * cruise_speed_kts
    # Filter airports within max_distance_nm from departure
```

### Example Query

**User**: "Where can I stop within 3h from EGTF on the way to LFMD with my SR22"

**Planner extracts**:
```python
{
    "tool": "find_airports_near_route",
    "arguments": {
        "from_location": "EGTF",
        "to_location": "LFMD",
        "max_leg_time_hours": 3,
        "aircraft_type": "sr22"  # → 180 kts
    }
}
```

**Tool computes**: 3h × 180 kts = 540nm max range

---

## Tool Result Structure

All tools return consistent structure:

```python
{
    # Core data
    "airports": [...],           # List of airports (if applicable)
    "filter_profile": {...},     # What filters were applied

    # Visualization hints
    "visualization": {
        "type": "route_with_markers",
        "route": {...},
        "markers": [...]
    },

    # Map deep-link (added by MCP server via /api/viz store)
    "action": {
        "type": "present_link",
        "url": "https://maps.flyfun.aero/v/{key}",
        "label": "View on FlyFun Maps",
    },

    # Conversational support
    "missing_info": [...],       # Missing info requests

    # Tool type marker (for formatter routing)
    "_tool_type": "comparison",  # Only for comparison tool
}
```

---

## Testing

```python
# test_calculate_flight_distance.py
def test_distance_only():
    result = calculate_flight_distance("EGTF", "LFMD")
    assert result["distance_nm"] > 0
    assert result["estimated_time_formatted"] is None
    assert "cruise_speed" in [m["key"] for m in result["missing_info"]]


def test_with_aircraft_type():
    result = calculate_flight_distance("EGTF", "LFMD", aircraft_type="c172")
    assert result["cruise_speed_kts"] == 120
    assert result["estimated_time_formatted"] is not None


# test_find_airports_near_route_time.py
def test_time_constrained_search():
    result = find_airports_near_route(
        "EGTF", "LFMD",
        max_leg_time_hours=3,
        cruise_speed_kts=180
    )
    # All airports should be within 540nm of EGTF
    for airport in result["airports"]:
        assert airport["distance_from_departure_nm"] <= 540
```

---

## Conversational Flow

```
Turn 1:
  User: "How long to fly from EGTF to LFMD"
  Tool: → {distance: 596, missing_info: [{cruise_speed}]}
  Answer: "596 nm. What's your cruise speed or aircraft type?"

Turn 2:
  User: "140 knots"
  Planner: Extracts speed from follow-up, same route context
  Tool: → {distance: 596, cruise_speed: 140, time: "4h 16m"}
  Answer: "At 140 kts, about 4 hours 16 minutes."

Turn 3:
  User: "What about with a C172?"
  Planner: Same route, new aircraft
  Tool: → {cruise_speed: 120, source: "typical C172", time: "4h 58m"}
  Answer: "At typical C172 cruise (~120 kts), about 5 hours."
```

---

## Debugging

```bash
# Test tool directly
python tools/avdbg.py "How far is EGTF from LFMD" --tool-result

# See missing_info
python tools/avdbg.py "How long to fly EGTF to LFMD" --tool-result -v
```

```python
# In Python
from shared.airport_tools import calculate_flight_distance

result = calculate_flight_distance("EGTF", "LFMD")
print(result["distance_nm"])
print(result["missing_info"])

result = calculate_flight_distance("EGTF", "LFMD", aircraft_type="c172")
print(result["estimated_time_formatted"])
```
