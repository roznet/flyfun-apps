#!/usr/bin/env python3

"""
LLM-as-judge comparison of full agent answers across model providers.

Runs full agent queries through two configs, collects final answers,
and uses a judge LLM to compare them on accuracy, completeness, clarity,
and helpfulness.

Usage:
  python tools/ab_compare.py --configs default anthropic --query "Find airports near Paris with AVGAS"
  python tools/ab_compare.py --configs default anthropic --queries queries.txt
  python tools/ab_compare.py --configs default anthropic --query "VFR rules in France" --judge openai

Requires:
  - API keys set for each provider being tested
  - Judge LLM API key (defaults to openai)
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage

from shared.aviation_agent.adapters import build_agent, stream_aviation_agent
from shared.aviation_agent.adapters.langgraph_runner import _resolve_llm
from shared.aviation_agent.config import AviationAgentSettings

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
# Data types
# ---------------------------------------------------------------------------
@dataclass
class JudgeScores:
    accuracy: int = 0
    completeness: int = 0
    clarity: int = 0
    helpfulness: int = 0

    @property
    def total(self) -> int:
        return self.accuracy + self.completeness + self.clarity + self.helpfulness


@dataclass
class ComparisonResult:
    query: str
    answer_a: str
    answer_b: str
    scores_a: JudgeScores = field(default_factory=JudgeScores)
    scores_b: JudgeScores = field(default_factory=JudgeScores)
    winner: str = "tie"
    reasoning: str = ""
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------
async def run_agent_query(query: str, config_name: str) -> str:
    """Run a full agent query and return the final answer text."""
    settings = AviationAgentSettings(
        enabled=True,
        agent_config_name=config_name,
    )
    graph = build_agent(settings=settings)
    messages = [HumanMessage(content=query)]

    answer = ""
    async for event in stream_aviation_agent(messages, graph):
        event_type = event.get("event")
        data = event.get("data", {})
        if event_type == "message":
            answer += data.get("content", "")
        elif event_type == "error":
            raise RuntimeError(data.get("message", "Unknown agent error"))

    return answer


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------
def load_judge_prompt() -> str:
    """Load judge prompt template."""
    prompt_path = (
        Path(__file__).parent.parent
        / "configs" / "aviation_agent" / "prompts" / "ab_judge_v1.md"
    )
    return prompt_path.read_text(encoding="utf-8")


def create_judge_llm(provider: str = "openai", model: Optional[str] = None):
    """Create the judge LLM."""
    default_models = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-sonnet-4-5-20250929",
        "google": "gemini-2.0-flash",
    }
    model = model or default_models.get(provider, "gpt-4o-mini")

    return _resolve_llm(
        None, model, role="judge",
        provider=provider, temperature=0.0,
    )


def judge_answers(
    judge_llm,
    query: str,
    config_a: str, answer_a: str,
    config_b: str, answer_b: str,
) -> ComparisonResult:
    """Use judge LLM to compare two answers."""
    prompt_template = load_judge_prompt()
    prompt = prompt_template.format(
        question=query,
        config_a=config_a, answer_a=answer_a,
        config_b=config_b, answer_b=answer_b,
    )

    result = ComparisonResult(query=query, answer_a=answer_a, answer_b=answer_b)

    try:
        response = judge_llm.invoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)

        # Extract JSON from response (may be wrapped in markdown code block)
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        data = json.loads(json_str.strip())

        result.scores_a = JudgeScores(**data.get("a", {}))
        result.scores_b = JudgeScores(**data.get("b", {}))
        result.winner = data.get("winner", "tie")
        result.reasoning = data.get("reasoning", "")

    except Exception as e:
        result.error = str(e)

    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def print_comparison_report(
    config_a: str,
    config_b: str,
    results: List[ComparisonResult],
) -> None:
    """Print formatted comparison report."""
    print(f"\n{fmt('='*75, BOLD)}")
    print(fmt("  LLM JUDGE COMPARISON", BOLD, CYAN))
    print(fmt("="*75, BOLD))

    # Per-query results
    header = f"{'Query':<35} | {config_a + ' (A)':<14} | {config_b + ' (B)':<14} | {'Winner':<8}"
    print(f"\n{fmt(header, BOLD)}")
    print("-" * len(header))

    total_a = 0
    total_b = 0
    max_possible = 0

    for r in results:
        if r.error:
            print(f"{r.query[:35]:<35} | {'ERROR':<14} | {'ERROR':<14} | {'-':<8}")
            continue

        score_a = f"{r.scores_a.total}/20"
        score_b = f"{r.scores_b.total}/20"
        total_a += r.scores_a.total
        total_b += r.scores_b.total
        max_possible += 20

        winner_str = r.winner.upper()
        if r.winner == "a":
            winner_str = fmt("A", GREEN, BOLD)
        elif r.winner == "b":
            winner_str = fmt("B", GREEN, BOLD)
        else:
            winner_str = fmt("Tie", YELLOW)

        print(f"{r.query[:35]:<35} | {score_a:<14} | {score_b:<14} | {winner_str:<8}")

    # Summary
    if max_possible > 0:
        print(f"\n{fmt('Overall:', BOLD)} {config_a} {total_a}/{max_possible}, "
              f"{config_b} {total_b}/{max_possible}")

        if total_a > total_b:
            print(fmt(f"  Winner: {config_a} (A)", GREEN, BOLD))
        elif total_b > total_a:
            print(fmt(f"  Winner: {config_b} (B)", GREEN, BOLD))
        else:
            print(fmt("  Result: Tie", YELLOW, BOLD))

    # Detailed reasoning
    print(f"\n{fmt('Detailed Reasoning:', BOLD, CYAN)}")
    for r in results:
        if r.error:
            print(f"\n  {r.query[:60]}")
            print(fmt(f"    Error: {r.error}", RED))
        elif r.reasoning:
            print(f"\n  {r.query[:60]}")
            print(f"    {r.reasoning}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare full agent answers across configs using LLM judge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --configs default anthropic --query "Find airports near Paris with AVGAS"
  %(prog)s --configs default anthropic --queries queries.txt
  %(prog)s --configs default anthropic --query "VFR rules in France" --judge openai
""",
    )
    parser.add_argument(
        "--configs", nargs=2, required=True, metavar="NAME",
        help="Two config names to compare (A and B)",
    )

    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument(
        "--query", type=str,
        help="Single query to compare",
    )
    query_group.add_argument(
        "--queries", type=str, metavar="FILE",
        help="File with one query per line",
    )

    parser.add_argument(
        "--judge", type=str, default="openai",
        choices=["openai", "anthropic", "google"],
        help="Judge LLM provider (default: openai)",
    )
    parser.add_argument(
        "--judge-model", type=str, default=None,
        help="Override judge model name",
    )
    return parser


async def async_main(args: argparse.Namespace) -> None:
    config_a, config_b = args.configs

    # Load queries
    if args.query:
        queries = [args.query]
    else:
        queries_path = Path(args.queries)
        if not queries_path.exists():
            print(fmt(f"Queries file not found: {args.queries}", RED))
            sys.exit(1)
        queries = [
            line.strip() for line in queries_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    print(fmt(f"Comparing {config_a} vs {config_b} on {len(queries)} queries", BOLD))
    print(fmt(f"Judge: {args.judge}" + (f" ({args.judge_model})" if args.judge_model else ""), DIM))
    print()

    # Create judge LLM
    judge_llm = create_judge_llm(args.judge, args.judge_model)

    results: List[ComparisonResult] = []
    for i, query in enumerate(queries):
        print(fmt(f"[{i + 1}/{len(queries)}] {query[:60]}...", BOLD))

        try:
            # Run both configs
            print(f"  Running {config_a}...", end="", flush=True)
            answer_a = await run_agent_query(query, config_a)
            print(fmt(" done", GREEN))

            print(f"  Running {config_b}...", end="", flush=True)
            answer_b = await run_agent_query(query, config_b)
            print(fmt(" done", GREEN))

            # Judge
            print(f"  Judging...", end="", flush=True)
            result = judge_answers(
                judge_llm, query,
                config_a, answer_a,
                config_b, answer_b,
            )
            results.append(result)
            print(fmt(" done", GREEN))

        except Exception as e:
            print(fmt(f" ERROR: {e}", RED))
            results.append(ComparisonResult(
                query=query, answer_a="", answer_b="", error=str(e),
            ))

    print_comparison_report(config_a, config_b, results)


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
