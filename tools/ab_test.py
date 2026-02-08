#!/usr/bin/env python3

"""
A/B test runner for planner behavior across model providers.

Runs planner test cases from fixtures/planner_test_cases.json against multiple
config profiles (e.g., default/openai, anthropic, gemini) and produces a
comparison table and optional CSV output.

Usage:
  python tools/ab_test.py --configs default anthropic gemini
  python tools/ab_test.py --configs default anthropic --cases 5
  python tools/ab_test.py --configs default anthropic --output results/comparison.csv

Requires:
  - API keys set for each provider (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY)
  - Test fixture at tests/aviation_agent/fixtures/planner_test_cases.json
"""

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage

from shared.aviation_agent.adapters.langgraph_runner import _resolve_llm
from shared.aviation_agent.config import get_behavior_config, AviationAgentSettings
from shared.aviation_agent.planning import build_planner_runnable
from shared.aviation_agent.tools import AviationToolClient
from tests.aviation_agent.test_utils import (
    load_test_cases,
    match_tool_and_args,
    normalize_expected,
)

# ---------------------------------------------------------------------------
# ANSI styling
# ---------------------------------------------------------------------------
RESET = '\033[0m'
BOLD = '\033[1m'
CYAN = '\033[36m'
YELLOW = '\033[33m'
GREEN = '\033[32m'
RED = '\033[31m'
DIM = '\033[2m'

ENABLE_COLOR = sys.stdout.isatty()


def fmt(text: str, *styles: str) -> str:
    if not ENABLE_COLOR or not styles:
        return text
    return "".join(styles) + text + RESET


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class CaseResult:
    """Result for a single test case."""
    question: str
    description: str
    tool_match: bool
    args_match: bool
    passed: bool
    elapsed: float
    selected_tool: str
    expected_tools: List[str]
    reason: str = ""


@dataclass
class ConfigResults:
    """Aggregated results for a single config."""
    config_name: str
    cases: List[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def tool_match_count(self) -> int:
        return sum(1 for c in self.cases if c.tool_match)

    @property
    def args_match_count(self) -> int:
        return sum(1 for c in self.cases if c.args_match)

    @property
    def avg_time(self) -> float:
        return sum(c.elapsed for c in self.cases) / max(len(self.cases), 1)

    def rate(self, count: int) -> str:
        return f"{count}/{self.total} ({100 * count / max(self.total, 1):.0f}%)"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def build_tool_client() -> AviationToolClient:
    """Build tool client for planner construction."""
    settings = AviationAgentSettings(enabled=True)
    return AviationToolClient(settings.build_tool_context())


def run_config_tests(
    config_name: str,
    test_cases: List[Dict[str, Any]],
    tool_client: AviationToolClient,
) -> ConfigResults:
    """Run all test cases against a single config."""
    behavior_config = get_behavior_config(config_name)

    llm = _resolve_llm(
        None,
        behavior_config.llms.planner.model,
        role="planner",
        provider=behavior_config.llms.planner.provider,
        temperature=behavior_config.llms.planner.temperature,
        max_retries=behavior_config.llms.planner.max_retries,
        request_timeout=behavior_config.llms.planner.request_timeout,
    )

    # Get available tags for dynamic prompt injection
    available_tags = None
    if tool_client._context.rules_manager:
        available_tags = tool_client._context.rules_manager.get_available_tags()

    llm_tools = tuple(t for t in tool_client.tools.values() if t.expose_to_llm)
    planner = build_planner_runnable(llm, llm_tools, available_tags=available_tags)

    results = ConfigResults(config_name=config_name)

    for i, tc in enumerate(test_cases):
        question = tc["question"]
        description = tc.get("description", "")
        expected_tools, expected_args_list = normalize_expected(tc)

        print(f"  [{i + 1}/{len(test_cases)}] {question[:60]}...", end="", flush=True)

        try:
            start = time.time()
            plan = planner.invoke({"messages": [HumanMessage(content=question)]})
            elapsed = time.time() - start

            tool_match, args_match, reason = match_tool_and_args(
                plan.selected_tool, plan.arguments or {},
                expected_tools, expected_args_list,
            )
            passed = tool_match and args_match

            results.cases.append(CaseResult(
                question=question,
                description=description,
                tool_match=tool_match,
                args_match=args_match,
                passed=passed,
                elapsed=elapsed,
                selected_tool=plan.selected_tool,
                expected_tools=expected_tools,
                reason=reason,
            ))

            status = fmt(" PASS", GREEN) if passed else fmt(" FAIL", RED)
            print(f"{status} ({elapsed:.1f}s)")
            if not passed:
                print(f"    {fmt(reason, DIM)}")

        except Exception as e:
            results.cases.append(CaseResult(
                question=question,
                description=description,
                tool_match=False,
                args_match=False,
                passed=False,
                elapsed=0.0,
                selected_tool="ERROR",
                expected_tools=expected_tools,
                reason=str(e),
            ))
            print(fmt(f" ERROR: {e}", RED))

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def print_comparison_table(all_results: Dict[str, ConfigResults]) -> None:
    """Print a summary comparison table."""
    print(f"\n{fmt('='*70, BOLD)}")
    print(fmt("  A/B TEST COMPARISON", BOLD, CYAN))
    print(fmt("="*70, BOLD))

    # Header
    header = f"{'Config':<16} | {'Pass Rate':<14} | {'Tool Match':<14} | {'Args Match':<14} | {'Avg Time':<8}"
    print(f"\n{fmt(header, BOLD)}")
    print("-" * len(header))

    for config_name, results in all_results.items():
        pass_rate = results.rate(results.pass_count)
        tool_rate = results.rate(results.tool_match_count)
        args_rate = results.rate(results.args_match_count)
        avg_time = f"{results.avg_time:.1f}s"

        print(f"{config_name:<16} | {pass_rate:<14} | {tool_rate:<14} | {args_rate:<14} | {avg_time:<8}")

    print()

    # Per-case comparison for failures
    configs = list(all_results.keys())
    if len(configs) >= 2:
        failures = set()
        for config_name, results in all_results.items():
            for case in results.cases:
                if not case.passed:
                    failures.add(case.question)

        if failures:
            print(fmt("  FAILURES BY QUESTION", BOLD, YELLOW))
            print("-" * 70)
            for q in sorted(failures):
                print(f"\n  {q[:65]}")
                for config_name, results in all_results.items():
                    for case in results.cases:
                        if case.question == q:
                            status = fmt("PASS", GREEN) if case.passed else fmt("FAIL", RED)
                            detail = f" ({case.reason})" if case.reason else ""
                            print(f"    {config_name:<14}: {status} → {case.selected_tool}{detail}")
            print()


def save_comparison_csv(
    all_results: Dict[str, ConfigResults],
    output_path: Path,
) -> None:
    """Save detailed per-case results to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "config", "question", "description",
        "status", "tool_match", "args_match",
        "expected_tools", "actual_tool", "elapsed", "reason",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for config_name, results in all_results.items():
            for case in results.cases:
                writer.writerow({
                    "config": config_name,
                    "question": case.question,
                    "description": case.description,
                    "status": "PASS" if case.passed else "FAIL",
                    "tool_match": "YES" if case.tool_match else "NO",
                    "args_match": "YES" if case.args_match else "NO",
                    "expected_tools": json.dumps(case.expected_tools),
                    "actual_tool": case.selected_tool,
                    "elapsed": f"{case.elapsed:.2f}",
                    "reason": case.reason,
                })

    print(fmt(f"Results saved to: {output_path}", DIM))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A/B test planner behavior across model configs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --configs default anthropic
  %(prog)s --configs default anthropic gemini --cases 5
  %(prog)s --configs default anthropic --output results/comparison.csv
""",
    )
    parser.add_argument(
        "--configs", nargs="+", required=True, metavar="NAME",
        help="Config names from configs/aviation_agent/NAME.json",
    )
    parser.add_argument(
        "--cases", type=int, default=None, metavar="N",
        help="Limit to first N test cases",
    )
    parser.add_argument(
        "--output", type=str, default=None, metavar="PATH",
        help="Save detailed CSV results to file",
    )
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    test_cases = load_test_cases()
    if args.cases:
        test_cases = test_cases[:args.cases]

    print(fmt(f"Running {len(test_cases)} test cases across {len(args.configs)} configs", BOLD))
    print(fmt(f"Configs: {', '.join(args.configs)}", DIM))
    print()

    # Build tool client once (shared across configs)
    tool_client = build_tool_client()

    all_results: Dict[str, ConfigResults] = {}
    for config_name in args.configs:
        print(fmt(f"\n--- Config: {config_name} ---", BOLD, CYAN))
        results = run_config_tests(config_name, test_cases, tool_client)
        all_results[config_name] = results

    print_comparison_table(all_results)

    if args.output:
        save_comparison_csv(all_results, Path(args.output))


if __name__ == "__main__":
    main()
