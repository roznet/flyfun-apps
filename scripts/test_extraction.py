#!/usr/bin/env python3
"""
Quick test script for GA Friendliness review extraction.

This script allows you to iterate on LLM prompts quickly without running 
a full build. It takes a single review text and outputs structured tags.

Usage:
    source venv/bin/activate
    python scripts/test_extraction.py                          # Uses sample review
    python scripts/test_extraction.py "Great airport, cheap!"  # Custom text
    python scripts/test_extraction.py --file etc~/LFQA.json    # From JSON file
    python scripts/test_extraction.py --mock                   # Use fake LLM (no API cost)

Environment:
    OPENAI_API_KEY - Required for real LLM extraction
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# Models
# ============================================================================

class AspectLabel(BaseModel):
    """A single extracted aspect with its label and confidence."""
    aspect: str = Field(description="The aspect being evaluated (e.g., 'cost', 'staff', 'bureaucracy')")
    label: str = Field(description="The label/value for this aspect (e.g., 'cheap', 'friendly', 'simple')")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0")
    evidence: str | None = Field(default=None, description="Quote from review supporting this extraction")


class ReviewExtraction(BaseModel):
    """Full extraction result from a single review."""
    aspects: list[AspectLabel] = Field(default_factory=list)
    raw_review: str | None = Field(default=None, description="Original review text")


# ============================================================================
# Ontology (Minimal for testing)
# ============================================================================

SAMPLE_ONTOLOGY = {
    "cost": ["cheap", "reasonable", "expensive", "unclear"],
    "staff": ["very_positive", "positive", "neutral", "negative", "very_negative"],
    "bureaucracy": ["simple", "moderate", "complex"],
    "food": ["excellent", "good", "available", "limited", "none"],
    "transport": ["excellent", "good", "available", "limited", "poor"],
    "overall_experience": ["very_positive", "positive", "neutral", "negative", "very_negative"],
    "fuel": ["available", "limited", "unavailable"],
    "restaurant": ["on_site", "walking", "nearby", "available", "none"],
    "accommodation": ["on_site", "walking", "nearby", "available", "none"],
}


# ============================================================================
# Extraction Logic
# ============================================================================

def build_extraction_prompt() -> str:
    """Build the system prompt for review extraction."""
    ontology_desc = "\n".join(
        f"  - {aspect}: {', '.join(labels)}"
        for aspect, labels in SAMPLE_ONTOLOGY.items()
    )
    
    return f"""You are an expert at extracting structured information from aviation pilot reviews.

Given a review about an airport/airfield, extract relevant aspects using ONLY the labels below.

ONTOLOGY (aspect: allowed_labels):
{ontology_desc}

RULES:
1. Only extract aspects that are explicitly mentioned or strongly implied
2. Use ONLY the labels from the ontology above
3. Assign confidence based on how explicit the mention is:
   - 0.9-1.0: Explicitly stated ("very cheap", "staff was rude")
   - 0.7-0.9: Clearly implied ("fees were €10" -> cheap)
   - 0.5-0.7: Somewhat implied or ambiguous
4. Include a short quote as evidence when possible
5. Skip aspects not mentioned in the review

Return a JSON object with this structure:
{{{{
  "aspects": [
    {{{{"aspect": "...", "label": "...", "confidence": 0.X, "evidence": "..."}}}},
    ...
  ]
}}}}
"""


def extract_with_llm(review_text: str, use_mock: bool = False) -> ReviewExtraction:
    """Extract aspects from review using LangChain."""
    
    if use_mock:
        # Return a fake extraction for testing without API
        return ReviewExtraction(
            aspects=[
                AspectLabel(aspect="cost", label="reasonable", confidence=0.8, evidence="[mock]"),
                AspectLabel(aspect="staff", label="positive", confidence=0.9, evidence="[mock]"),
            ],
            raw_review=review_text,
        )
    
    # Import LangChain (only when needed)
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        print("ERROR: Install langchain: pip install langchain-core langchain-openai")
        sys.exit(1)
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: Set OPENAI_API_KEY environment variable")
        sys.exit(1)
    
    # Build the chain
    prompt = ChatPromptTemplate.from_messages([
        ("system", build_extraction_prompt()),
        ("human", "Review to analyze:\n\n{review}"),
    ])
    
    llm = ChatOpenAI(
        model="gpt-4o-mini",  # Cost effective for iteration
        temperature=0.0,
    )
    
    # Run the chain
    chain = prompt | llm
    
    print("🤖 Calling LLM...")
    response = chain.invoke({"review": review_text})
    
    # Parse the response
    try:
        # Extract JSON from response
        content = response.content
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        data = json.loads(content)
        aspects = [AspectLabel(**a) for a in data.get("aspects", [])]
        return ReviewExtraction(aspects=aspects, raw_review=review_text)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠️  Failed to parse response: {e}")
        print(f"Raw response:\n{response.content}")
        return ReviewExtraction(aspects=[], raw_review=review_text)


def load_review_from_json(filepath: str) -> str:
    """Load first review from an airfield.directory JSON file."""
    with open(filepath) as f:
        data = json.load(f)
    
    pireps = data.get("pireps", {}).get("data", [])
    if not pireps:
        print(f"No reviews found in {filepath}")
        sys.exit(1)
    
    # Get the English content
    review = pireps[0]
    content = review.get("content", {})
    if isinstance(content, dict):
        return content.get("EN", str(content))
    return str(content)


# ============================================================================
# Output Formatting
# ============================================================================

def format_extraction(extraction: ReviewExtraction) -> str:
    """Format extraction results for display."""
    lines = [
        "=" * 60,
        "EXTRACTION RESULTS",
        "=" * 60,
        "",
    ]
    
    if not extraction.aspects:
        lines.append("No aspects extracted.")
    else:
        for aspect in extraction.aspects:
            conf_bar = "█" * int(aspect.confidence * 10) + "░" * (10 - int(aspect.confidence * 10))
            lines.append(f"📌 {aspect.aspect}: {aspect.label}")
            lines.append(f"   Confidence: [{conf_bar}] {aspect.confidence:.2f}")
            if aspect.evidence:
                evidence = aspect.evidence[:80] + "..." if len(aspect.evidence) > 80 else aspect.evidence
                lines.append(f"   Evidence: \"{evidence}\"")
            lines.append("")
    
    return "\n".join(lines)


# ============================================================================
# Main
# ============================================================================

SAMPLE_REVIEW = """
Great airfield! The staff was incredibly friendly and helpful. Landing fees were 
very reasonable (around €15 for a C172). Getting to the city center is easy with 
Uber, about €20. The restaurant on site had excellent food - we had lunch there 
and it was fantastic. Customs clearance was straightforward, just a quick call 
24h ahead. Would definitely come back!
"""


def main():
    parser = argparse.ArgumentParser(description="Test GA friendliness review extraction")
    parser.add_argument("review", nargs="?", help="Review text to extract from")
    parser.add_argument("--file", "-f", help="Load review from airfield.directory JSON file")
    parser.add_argument("--mock", action="store_true", help="Use mock LLM (no API call)")
    parser.add_argument("--show-prompt", action="store_true", help="Show the system prompt")
    args = parser.parse_args()
    
    if args.show_prompt:
        print(build_extraction_prompt())
        return
    
    # Get review text
    if args.file:
        review_text = load_review_from_json(args.file)
        print(f"📁 Loaded review from {args.file}")
    elif args.review:
        review_text = args.review
    else:
        review_text = SAMPLE_REVIEW
        print("📝 Using sample review (pass --help for options)")
    
    print("\n" + "-" * 60)
    print("INPUT REVIEW:")
    print("-" * 60)
    print(review_text.strip()[:500])
    if len(review_text) > 500:
        print(f"... ({len(review_text)} chars total)")
    print("-" * 60 + "\n")
    
    # Extract
    extraction = extract_with_llm(review_text, use_mock=args.mock)
    
    # Display results
    print(format_extraction(extraction))
    
    # Also print as JSON for debugging
    print("\n📋 JSON Output:")
    print(json.dumps([a.model_dump() for a in extraction.aspects], indent=2))


if __name__ == "__main__":
    main()

