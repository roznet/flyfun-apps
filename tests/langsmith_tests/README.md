# LangSmith Aviation Agent Testing Pipeline

This directory contains the LangSmith-based automated testing and evaluation infrastructure for the FlyFun aviation agent.

## Overview

The testing pipeline enables systematic evaluation of the aviation agent's:
- **Tool selection**: Does the planner choose the correct tool for each query type?
- **Filter extraction**: Are filters correctly extracted from natural language?
- **Answer quality**: Is the final answer complete, accurate, and well-formatted?

## Directory Structure

```
tests/langsmith/
├── datasets/
│   └── issue_8_baseline.py      # Test cases from GitHub issue #8
├── evaluators/
│   ├── tool_selection.py         # Tool selection evaluators
│   ├── filter_extraction.py      # Filter extraction evaluators
│   └── answer_quality.py         # Answer quality evaluators
├── runners/
│   └── run_evaluation.py         # Main evaluation runner script
└── ci/
    └── (GitHub Actions workflows)
```

## Quick Start

### 1. Prerequisites

Ensure you have the required environment variables set:

```bash
# In your .env file or environment
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=FlyFun
OPENAI_API_KEY=your_openai_api_key
AVIATION_AGENT_PLANNER_MODEL=gpt-4o-mini
AVIATION_AGENT_FORMATTER_MODEL=gpt-4o-mini
```

### 2. List Available Test Categories

```bash
python tests/langsmith/runners/run_evaluation.py --list-categories
```

Output:
```
Available test case categories:
  - geographic_search: 4 test cases
  - smart_filtering: 4 test cases
  - regulatory: 5 test cases
  - complex: 2 test cases
```

### 3. Create Dataset in LangSmith

```bash
python tests/langsmith/runners/run_evaluation.py \
    --dataset issue-8-baseline \
    --create-dataset
```

This creates a dataset in LangSmith with all 15 test cases from issue #8.

### 4. Run Evaluation

**Run all test cases:**
```bash
python tests/langsmith/runners/run_evaluation.py \
    --dataset issue-8-baseline \
    --experiment baseline-v1
```

**Run specific category:**
```bash
python tests/langsmith/runners/run_evaluation.py \
    --dataset issue-8-baseline \
    --category geographic_search \
    --experiment geo-test-v1
```

**Run with concurrency:**
```bash
python tests/langsmith/runners/run_evaluation.py \
    --dataset issue-8-baseline \
    --experiment parallel-test \
    --concurrency 3
```

### 5. View Results

Results are automatically uploaded to LangSmith:
- Visit: https://smith.langchain.com/
- Navigate to your project: "FlyFun"
- View experiments and detailed trace comparisons

## Test Cases

### Geographic Search (4 cases)
- `geo_01`: Distance-based search from ICAO code
- `geo_02`: Midpoint calculation between two airports
- `geo_03`: Border proximity search
- `geo_04`: Route search with IFR approach filter

### Smart Filtering (4 cases)
- `filter_01`: General aviation filtering to exclude major hubs
- `filter_02`: Amenity filtering (restaurants)
- `filter_03`: Multiple amenity filters (hotels + maintenance)
- `filter_04`: Landing fees and runway surface filtering

### Regulatory Intelligence (5 cases)
- `reg_01`: Country-specific rules (uncontrolled airfields in France)
- `reg_02`: Cross-country regulatory comparison (UK vs Germany)
- `reg_03`: Specific regulatory requirements (GAR submission UK)
- `reg_04`: Airport-specific customs information
- `reg_05`: Multi-country PPR comparison

### Complex Queries (2 cases)
- `complex_01`: Multi-filter query with regulatory info
- `complex_02`: Route optimization with exclusions

## Evaluators

### Tool Selection Evaluators
- `evaluate_tool_selection`: Checks if correct tool was selected
- `evaluate_tool_execution`: Verifies tool executed without errors

### Filter Extraction Evaluators
- `evaluate_filter_extraction`: Validates filter accuracy
- `evaluate_filter_completeness`: Ensures no filters were missed

### Answer Quality Evaluators
- `evaluate_answer_mentions`: Checks for expected keywords/ICAOs
- `evaluate_answer_length`: Validates answer length is reasonable
- `evaluate_answer_format`: Verifies markdown formatting

## CI/CD Integration

The GitHub Actions workflow (`.github/workflows/langsmith-evaluation.yml`) runs automatically on:
- Push to `main` or `features/**` branches
- Pull requests to `main`
- Manual workflow dispatch

### Manual Trigger

From GitHub Actions UI, you can manually trigger with:
- **Experiment name**: Custom name for the evaluation run
- **Category**: Specific test category (or empty for all)

### PR Comments

On pull requests, the workflow automatically comments with:
- Evaluation success/failure
- Link to LangSmith results
- Summary of what was tested

## Adding New Test Cases

To add new test cases:

1. Edit `tests/langsmith/datasets/issue_8_baseline.py`
2. Add your test case to the appropriate category list:

```python
{
    "id": "geo_05",
    "category": "geographic_search",
    "inputs": {"query": "Your test query here"},
    "expected": {
        "tool": "airport_search",
        "filters": {"your": "filters"},
        "should_mention": ["keywords", "to", "check"],
    },
    "description": "What this test validates"
}
```

3. Re-create the dataset:
```bash
python tests/langsmith/runners/run_evaluation.py --create-dataset --dataset issue-8-baseline
```

4. Run evaluation to verify it works

## Creating Custom Evaluators

To add a new evaluator:

1. Create file in `tests/langsmith/evaluators/your_evaluator.py`
2. Implement evaluation function:

```python
def evaluate_your_metric(run, example):
    """
    Your evaluator description.

    Args:
        run: LangSmith run object with outputs
        example: Test case with expected values

    Returns:
        Dict with score (0.0-1.0) and comment
    """
    # Extract data from run.outputs
    actual = run.outputs.get("your_field")
    expected = example.outputs.get("expected", {}).get("your_field")

    score = 1.0 if actual == expected else 0.0

    return {
        "key": "your_metric_name",
        "score": score,
        "comment": f"Your feedback here"
    }
```

3. Import and add to `run_evaluation.py`:

```python
from tests.langsmith.evaluators.your_evaluator import evaluate_your_metric

# Add to evaluators list
evaluators=[
    evaluate_tool_selection,
    # ... existing evaluators ...
    evaluate_your_metric,  # Your new evaluator
]
```

## Best Practices

### Regression Testing
1. Run baseline evaluation before making changes
2. Make your improvements to the aviation agent
3. Run evaluation again with same dataset
4. Compare results in LangSmith to see impact

### A/B Testing Prompts
1. Create a dataset with your test cases
2. Run evaluation with current prompt (experiment: "prompt-v1")
3. Modify the planner/formatter prompts
4. Run evaluation again (experiment: "prompt-v2")
5. Compare side-by-side in LangSmith

### Continuous Improvement Workflow
1. Review failed test cases in LangSmith traces
2. Identify patterns in failures (wrong tool, missing filters, etc.)
3. Update prompts, add examples, or improve tools
4. Re-run evaluation to verify fixes
5. Track metrics over time

## Troubleshooting

**"No API key" error:**
- Ensure `LANGCHAIN_API_KEY` is set in environment or `.env` file

**"Aviation agent disabled" error:**
- Set `AVIATION_AGENT_ENABLED=true` in your config

**"Dataset not found" error:**
- Run with `--create-dataset` flag first

**Evaluation runs but all scores are 0:**
- Check that `run.outputs` structure matches what evaluators expect
- Review a trace in LangSmith to see actual output structure

## Related Documentation

- LangSmith Evaluation Guide: https://docs.smith.langchain.com/evaluation
- LangSmith Python SDK: https://docs.smith.langchain.com/reference/python-sdk
- GitHub Issue #8: https://github.com/roznet/flyfun-apps/issues/8
