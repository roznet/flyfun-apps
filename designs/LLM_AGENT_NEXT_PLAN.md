# Aviation Agent - Next Implementation Plan

This document captures planned improvements for the aviation agent.

**Last Updated:** 2024-12-20
**Session:** `langsmith-feedback`

---

## Overview

Two main improvements identified during code review:

1. **LangSmith Feedback Integration** - Enable thumbs up/down rating from UI - **IMPLEMENTED**
2. **Tests for NextQueryPredictor** - Currently untested module - **PENDING**

---

## 1. LangSmith Feedback Integration

### Implementation Summary (Completed 2024-12-20)

**Files Modified:**
- `shared/aviation_agent/adapters/streaming.py` - Added `run_id` to config and done events
- `shared/aviation_agent/adapters/langgraph_runner.py` - Added `run_id` to config
- `web/server/api/aviation_agent_chat.py` - Added `POST /feedback` endpoint
- `web/client/ts/managers/chatbot-manager.ts` - Added feedback UI (thumbs up/down, comment input)
- `web/client/css/chatbot.css` - Added feedback styles

**Features:**
- Thumbs up/down buttons appear after each response
- Thumbs up submits immediately (score=1)
- Thumbs down shows comment textarea, then submits (score=0)
- Skip option for thumbs down without comment
- Feedback sent to LangSmith via `client.create_feedback()`
- Thanks message with fade-out after submission

### Original Design (for reference)

#### Current State

LangSmith integration is minimal:
- Basic tags and metadata in `langgraph_runner.py` and `streaming.py`
- Run names like `aviation-agent-{run_id[:8]}`
- Tracing works if `LANGCHAIN_API_KEY` and `LANGCHAIN_PROJECT` env vars are set
- **No feedback tracking** - run_id is not exposed to UI

### Goal

Allow users to provide thumbs up/down feedback on agent responses, which gets logged to LangSmith for:
- Quality monitoring
- Model fine-tuning data collection
- Identifying problem areas

### Implementation Plan

#### Phase 1: Expose Run ID to UI

**File: `shared/aviation_agent/adapters/streaming.py`**

The `done` event already includes `session_id` and `thread_id`. Add `run_id`:

```python
# In stream_aviation_agent()
# Generate run_id at the start (currently just used for config)
run_id = str(uuid.uuid4())  # Make this the canonical run_id

# ... in the done event ...
yield {
    "event": "done",
    "data": {
        "session_id": session_id,
        "thread_id": effective_thread_id,
        "run_id": run_id,  # ADD THIS - for LangSmith feedback
        "tokens": {...},
        "metadata": {...}
    }
}
```

Also update the config to use this run_id:

```python
config = {
    "run_id": run_id,  # Ensure LangSmith uses this exact ID
    "run_name": f"aviation-agent-{run_id[:8]}",
    ...
}
```

#### Phase 2: Add Feedback Endpoint

**File: `web/server/api/aviation_agent_chat.py`**

Add new endpoint:

```python
from langsmith import Client

class FeedbackRequest(BaseModel):
    run_id: str
    score: int  # 1 = thumbs up, 0 = thumbs down
    comment: Optional[str] = None

@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    settings: AviationAgentSettings = Depends(get_settings),
) -> dict:
    """
    Submit user feedback for a conversation run.

    Args:
        request: FeedbackRequest with run_id and score (1=good, 0=bad)

    Returns:
        {"status": "ok", "feedback_id": "..."}
    """
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")

    try:
        client = Client()  # Uses LANGCHAIN_API_KEY from env
        feedback = client.create_feedback(
            run_id=request.run_id,
            key="user-rating",
            score=request.score,
            comment=request.comment,
        )
        return {"status": "ok", "feedback_id": str(feedback.id)}
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit feedback")
```

#### Phase 3: UI Integration

The UI needs to:
1. Store `run_id` from the `done` SSE event
2. Show thumbs up/down buttons after response completes
3. On thumbs down, show a comment input before submitting
4. Call `POST /api/aviation-agent/feedback` with the run_id

**UI Flow:**

```
[Response completes]
     |
     v
[👍] [👎]  <-- Thumbs buttons appear
     |
     v (user clicks 👎)
     |
+----------------------------------+
| What went wrong?                 |
| +------------------------------+ |
| |                              | |
| +------------------------------+ |
| [Skip]              [Submit]    |
+----------------------------------+
     |
     v
[Feedback sent - thank you!]
```

**UI changes (not in this repo):**

```typescript
// State
const [runId, setRunId] = useState<string | null>(null);
const [showFeedbackInput, setShowFeedbackInput] = useState(false);
const [feedbackComment, setFeedbackComment] = useState('');
const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

// After receiving 'done' event:
const handleDoneEvent = (event: SSEEvent) => {
    setRunId(event.data.run_id);
};

// Thumbs up - submit immediately
const handleThumbsUp = async () => {
    await submitFeedback(1, null);
    setFeedbackSubmitted(true);
};

// Thumbs down - show comment input first
const handleThumbsDown = () => {
    setShowFeedbackInput(true);
};

// Submit feedback (with optional comment for thumbs down)
const submitFeedback = async (score: number, comment: string | null) => {
    await fetch('/api/aviation-agent/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            run_id: runId,
            score: score,
            comment: comment
        })
    });
    setFeedbackSubmitted(true);
    setShowFeedbackInput(false);
};

// Skip comment (submit thumbs down without comment)
const handleSkip = () => submitFeedback(0, null);

// Submit with comment
const handleSubmitComment = () => submitFeedback(0, feedbackComment);
```

**Component structure:**

```tsx
{runId && !feedbackSubmitted && (
    <div className="feedback-container">
        {!showFeedbackInput ? (
            // Initial state: show thumbs buttons
            <div className="thumbs-buttons">
                <button onClick={handleThumbsUp}>👍</button>
                <button onClick={handleThumbsDown}>👎</button>
            </div>
        ) : (
            // After thumbs down: show comment input
            <div className="feedback-input">
                <label>What went wrong?</label>
                <textarea
                    value={feedbackComment}
                    onChange={(e) => setFeedbackComment(e.target.value)}
                    placeholder="The answer was incorrect because..."
                />
                <div className="feedback-actions">
                    <button onClick={handleSkip}>Skip</button>
                    <button onClick={handleSubmitComment}>Submit</button>
                </div>
            </div>
        )}
    </div>
)}

{feedbackSubmitted && (
    <div className="feedback-thanks">Thanks for your feedback!</div>
)}
```

### Dependencies

```bash
pip install langsmith  # If not already installed
```

### Environment Variables

Already configured if LangSmith tracing works:
- `LANGCHAIN_API_KEY` - API key for LangSmith
- `LANGCHAIN_PROJECT` - Project name in LangSmith

### Testing Strategy

1. **Unit test for feedback endpoint:**
   - Mock the LangSmith client
   - Test success and error cases

2. **Integration test:**
   - Run a query, capture run_id
   - Submit feedback with that run_id
   - Verify in LangSmith (manual or API check)

---

## 2. Tests for NextQueryPredictor

### Current State

`shared/aviation_agent/next_query_predictor.py` has:
- `QueryContext` dataclass
- `SuggestedQuery` dataclass
- `extract_context_from_plan()` function
- `NextQueryPredictor` class with rule-based prediction

**No tests exist** for this module.

### Implementation Plan

**File: `tests/aviation_agent/test_next_query_predictor.py`**

```python
"""Tests for next_query_predictor module."""
import pytest
from shared.aviation_agent.next_query_predictor import (
    NextQueryPredictor,
    QueryContext,
    SuggestedQuery,
    extract_context_from_plan,
)
from shared.aviation_agent.planning import AviationPlan


class TestExtractContextFromPlan:
    """Tests for extract_context_from_plan function."""

    def test_extracts_route_locations(self):
        """Extracts from_location and to_location from route query."""
        plan = AviationPlan(
            selected_tool="find_airports_near_route",
            arguments={
                "from_location": "EGTF",
                "to_location": "LFMD",
                "filters": {}
            },
            answer_style="brief"
        )

        context = extract_context_from_plan("Find airports from EGTF to LFMD", plan)

        assert context.tool_used == "find_airports_near_route"
        assert "EGTF" in context.locations_mentioned
        assert "LFMD" in context.locations_mentioned
        assert "EGTF" in context.icao_codes_mentioned
        assert "LFMD" in context.icao_codes_mentioned

    def test_extracts_location_query(self):
        """Extracts location_query from near-location search."""
        plan = AviationPlan(
            selected_tool="find_airports_near_location",
            arguments={
                "location_query": "Paris",
                "filters": {"has_avgas": True}
            },
            answer_style="detailed"
        )

        context = extract_context_from_plan("Find airports near Paris", plan)

        assert context.tool_used == "find_airports_near_location"
        assert "Paris" in context.locations_mentioned
        assert context.filters_applied.get("has_avgas") is True

    def test_extracts_icao_code(self):
        """Extracts icao_code from airport details query."""
        plan = AviationPlan(
            selected_tool="get_airport_details",
            arguments={"icao_code": "EGLL"},
            answer_style="detailed"
        )

        context = extract_context_from_plan("Details for EGLL", plan)

        assert "EGLL" in context.icao_codes_mentioned

    def test_extracts_countries(self):
        """Extracts country from various argument positions."""
        plan = AviationPlan(
            selected_tool="list_rules_for_country",
            arguments={"country_code": "FR"},
            answer_style="detailed"
        )

        context = extract_context_from_plan("Rules for France", plan)

        assert "FR" in context.countries_mentioned

    def test_extracts_country_from_filters(self):
        """Extracts country from filters dict."""
        plan = AviationPlan(
            selected_tool="search_airports",
            arguments={
                "query": "airports",
                "filters": {"country": "DE"}
            },
            answer_style="brief"
        )

        context = extract_context_from_plan("Airports in Germany", plan)

        assert "DE" in context.countries_mentioned


class TestNextQueryPredictor:
    """Tests for NextQueryPredictor class."""

    @pytest.fixture
    def predictor(self):
        """Create predictor without rules.json."""
        return NextQueryPredictor(rules_json_path=None)

    def test_route_suggestions_include_customs(self, predictor):
        """Route queries suggest customs when not filtered."""
        context = QueryContext(
            user_query="Find airports from EGTF to LFMD",
            tool_used="find_airports_near_route",
            tool_arguments={"from_location": "EGTF", "to_location": "LFMD"},
            filters_applied={},
            locations_mentioned=["EGTF", "LFMD"],
            icao_codes_mentioned=["EGTF", "LFMD"],
            countries_mentioned=[]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=10)

        # Should suggest customs since not filtered
        customs_suggestions = [s for s in suggestions if "customs" in s.query_text.lower()]
        assert len(customs_suggestions) > 0

    def test_route_suggestions_include_avgas(self, predictor):
        """Route queries suggest AVGAS when not filtered."""
        context = QueryContext(
            user_query="Find airports from EGTF to LFMD",
            tool_used="find_airports_near_route",
            tool_arguments={"from_location": "EGTF", "to_location": "LFMD"},
            filters_applied={},
            locations_mentioned=["EGTF", "LFMD"],
            icao_codes_mentioned=["EGTF", "LFMD"],
            countries_mentioned=[]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=10)

        avgas_suggestions = [s for s in suggestions if "avgas" in s.query_text.lower()]
        assert len(avgas_suggestions) > 0

    def test_route_suggestions_skip_avgas_if_filtered(self, predictor):
        """Route queries don't suggest AVGAS when already filtered."""
        context = QueryContext(
            user_query="Find airports with AVGAS from EGTF to LFMD",
            tool_used="find_airports_near_route",
            tool_arguments={"from_location": "EGTF", "to_location": "LFMD"},
            filters_applied={"has_avgas": True},  # Already filtering
            locations_mentioned=["EGTF", "LFMD"],
            icao_codes_mentioned=["EGTF", "LFMD"],
            countries_mentioned=[]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=10)

        # Should NOT suggest AVGAS filter since already applied
        avgas_filter_suggestions = [
            s for s in suggestions
            if "avgas" in s.query_text.lower() and s.tool_name == "find_airports_near_route"
        ]
        assert len(avgas_filter_suggestions) == 0

    def test_airport_details_suggests_pricing(self, predictor):
        """Airport details queries suggest pricing."""
        context = QueryContext(
            user_query="Details for EGLL",
            tool_used="get_airport_details",
            tool_arguments={"icao_code": "EGLL"},
            filters_applied={},
            locations_mentioned=[],
            icao_codes_mentioned=["EGLL"],
            countries_mentioned=[]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=10)

        pricing_suggestions = [s for s in suggestions if s.category == "pricing"]
        assert len(pricing_suggestions) > 0
        assert any("EGLL" in s.query_text for s in pricing_suggestions)

    def test_airport_details_suggests_fuel(self, predictor):
        """Airport details queries suggest fuel prices."""
        context = QueryContext(
            user_query="Details for LFPG",
            tool_used="get_airport_details",
            tool_arguments={"icao_code": "LFPG"},
            filters_applied={},
            locations_mentioned=[],
            icao_codes_mentioned=["LFPG"],
            countries_mentioned=[]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=10)

        fuel_suggestions = [s for s in suggestions if "fuel" in s.query_text.lower()]
        assert len(fuel_suggestions) > 0

    def test_rules_query_suggests_customs_airports(self, predictor):
        """Rules queries suggest border crossing airports."""
        context = QueryContext(
            user_query="What are the rules for France?",
            tool_used="list_rules_for_country",
            tool_arguments={"country_code": "FR"},
            filters_applied={},
            locations_mentioned=[],
            icao_codes_mentioned=[],
            countries_mentioned=["FR"]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=10)

        border_suggestions = [s for s in suggestions if s.tool_name == "get_border_crossing_airports"]
        assert len(border_suggestions) > 0

    def test_max_suggestions_respected(self, predictor):
        """Respects max_suggestions limit."""
        context = QueryContext(
            user_query="Find airports from EGTF to LFMD",
            tool_used="find_airports_near_route",
            tool_arguments={"from_location": "EGTF", "to_location": "LFMD"},
            filters_applied={},
            locations_mentioned=["EGTF", "LFMD"],
            icao_codes_mentioned=["EGTF", "LFMD"],
            countries_mentioned=[]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=2)

        assert len(suggestions) <= 2

    def test_suggestions_are_unique(self, predictor):
        """No duplicate suggestions."""
        context = QueryContext(
            user_query="Find airports from EGTF to LFMD",
            tool_used="find_airports_near_route",
            tool_arguments={"from_location": "EGTF", "to_location": "LFMD"},
            filters_applied={},
            locations_mentioned=["EGTF", "LFMD"],
            icao_codes_mentioned=["EGTF", "LFMD"],
            countries_mentioned=[]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=10)

        query_texts = [s.query_text for s in suggestions]
        assert len(query_texts) == len(set(query_texts))

    def test_suggestions_have_diverse_categories(self, predictor):
        """First suggestions should cover different categories."""
        context = QueryContext(
            user_query="Find airports from EGTF to LFMD",
            tool_used="find_airports_near_route",
            tool_arguments={"from_location": "EGTF", "to_location": "LFMD"},
            filters_applied={},
            locations_mentioned=["EGTF", "LFMD"],
            icao_codes_mentioned=["EGTF", "LFMD"],
            countries_mentioned=[]
        )

        suggestions = predictor.predict_next_queries(context, max_suggestions=4)

        if len(suggestions) >= 3:
            categories = set(s.category for s in suggestions[:3])
            # Should have at least 2 different categories in first 3
            assert len(categories) >= 2


class TestSuggestedQuery:
    """Tests for SuggestedQuery dataclass."""

    def test_has_required_fields(self):
        """SuggestedQuery has all required fields."""
        sq = SuggestedQuery(
            query_text="Test query",
            tool_name="search_airports",
            category="route",
            priority=3
        )

        assert sq.query_text == "Test query"
        assert sq.tool_name == "search_airports"
        assert sq.category == "route"
        assert sq.priority == 3


class TestQueryContext:
    """Tests for QueryContext dataclass."""

    def test_has_required_fields(self):
        """QueryContext has all required fields."""
        ctx = QueryContext(
            user_query="test",
            tool_used="search_airports",
            tool_arguments={},
            filters_applied={},
            locations_mentioned=[],
            icao_codes_mentioned=[],
            countries_mentioned=[]
        )

        assert ctx.user_query == "test"
        assert ctx.tool_used == "search_airports"
```

### Test Coverage Areas

| Area | Tests |
|------|-------|
| `extract_context_from_plan()` | Route locations, location_query, ICAO codes, countries from args, countries from filters |
| `NextQueryPredictor.predict_next_queries()` | Route suggestions, filter awareness, airport details suggestions, rules suggestions, max limit, uniqueness, diversity |
| Dataclasses | Field validation |

### Running Tests

```bash
# Run just the new tests
pytest tests/aviation_agent/test_next_query_predictor.py -v

# Run with coverage
pytest tests/aviation_agent/test_next_query_predictor.py --cov=shared/aviation_agent/next_query_predictor
```

---

## Implementation Priority

| Task | Effort | Value | Priority |
|------|--------|-------|----------|
| NextQueryPredictor tests | Low | Medium | 1 (do first - quick win) |
| LangSmith Phase 1 (expose run_id) | Low | High | 2 |
| LangSmith Phase 2 (feedback endpoint) | Medium | High | 3 |
| LangSmith Phase 3 (UI integration) | Medium | High | 4 (requires UI work) |

---

## Files to Modify

### For LangSmith Feedback:
- `shared/aviation_agent/adapters/streaming.py` - Add run_id to done event
- `shared/aviation_agent/adapters/langgraph_runner.py` - Ensure run_id in config
- `web/server/api/aviation_agent_chat.py` - Add feedback endpoint
- `requirements.txt` or `pyproject.toml` - Add `langsmith` dependency if needed

### For NextQueryPredictor Tests:
- `tests/aviation_agent/test_next_query_predictor.py` - New file

---

## Notes

- The `AviationPlan` class is imported from `planning.py` - check if it needs `answer_style` or if that's optional
- LangSmith client uses `LANGCHAIN_API_KEY` from environment
- UI changes for feedback buttons are outside this repo
