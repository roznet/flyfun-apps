#!/usr/bin/env python3
"""
LangChain chat endpoint using in-process MCP tools (like old codebase).

Dependencies:
    pip install langchain langchain-core langchain-openai pydantic fastapi fastmcp

Environment:
    OPENAI_API_KEY=sk-...
    OPENAI_MODEL=gpt-4o (optional)
    AIRPORTS_DB=path/to/airports.db
    RULES_JSON=path/to/rules.json
"""
from __future__ import annotations

import os
import asyncio
import logging
import json
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# LangChain
from langchain.agents import create_agent
from langchain.tools import tool

# Euro AIP models (in-process, like old codebase)
from euro_aip.storage.database_storage import DatabaseStorage
from euro_aip.storage.enrichment_storage import EnrichmentStorage
from euro_aip.models.euro_aip_model import EuroAipModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are an assistant specialized in European GA/IFR/VFR operations. "
    "Prefer tools for factual data (AIP entries, rules, border crossing, procedures, airports near a route). "
    "Return concise, practical answers. Use ICAO identifiers and ISO-2 country codes where relevant."
)

# -----------------------
# Config via environment
# -----------------------
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
AIRPORTS_DB = os.getenv("AIRPORTS_DB", "airports.db")
RULES_JSON = os.getenv("RULES_JSON", "rules.json")

# ------------------------------------
# Lazy, global initialization (warm)
# ------------------------------------
_model: Optional[EuroAipModel] = None
_enrichment_storage: Optional[EnrichmentStorage] = None
_agent = None
_rules: Optional[Dict[str, Any]] = None
_rules_index: Optional[Dict[str, Any]] = None
_init_lock = asyncio.Lock()


# Import MCP tool functions directly
def _build_rules_index(rules: Dict[str, Any]) -> Dict[str, Any]:
    """Build rules index (copied from mcp_server/main.py)"""
    questions = rules.get("questions", []) or []
    by_id: Dict[str, Dict[str, Any]] = {}
    by_category: Dict[str, List[str]] = {}
    by_tag: Dict[str, List[str]] = {}
    categories: set[str] = set()
    tags: set[str] = set()
    for q in questions:
        qid = q.get("question_id")
        if not qid:
            continue
        by_id[qid] = q
        cat = (q.get("category") or "").strip()
        if cat:
            categories.add(cat)
            by_category.setdefault(cat.lower(), []).append(qid)
        for t in (q.get("tags") or []):
            tt = (t or "").strip()
            if not tt:
                continue
            tags.add(tt)
            by_tag.setdefault(tt.lower(), []).append(qid)
    return {
        "by_id": by_id,
        "by_category": by_category,
        "by_tag": by_tag,
        "categories": sorted(categories),
        "tags": sorted(tags),
    }


async def _get_agent():
    """
    Lazily initialize and memoize the Agent that uses OpenAI tool-calling
    and in-process MCP tools (like the old codebase).
    """
    global _model, _enrichment_storage, _agent, _rules, _rules_index
    if _agent:
        return _agent

    async with _init_lock:
        if _agent:
            return _agent

        # 1) Load model in-process (like old codebase)
        try:
            logger.info(f"📦 Loading model from database at '{AIRPORTS_DB}'")
            db_storage = DatabaseStorage(AIRPORTS_DB)
            _model = db_storage.load_model()
            _enrichment_storage = EnrichmentStorage(AIRPORTS_DB)
            logger.info(f"✅ Loaded model with {len(_model.airports)} airports")
        except Exception as e:
            error_msg = f"Failed to load model from {AIRPORTS_DB}"
            logger.error(f"{error_msg}: {type(e).__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"{error_msg}. Please check AIRPORTS_DB path."
            )

        # 2) Load rules
        try:
            logger.info(f"📦 Loading rules from '{RULES_JSON}'")
            with open(RULES_JSON, "r", encoding="utf-8") as f:
                _rules = json.load(f)
            _rules_index = _build_rules_index(_rules)
            logger.info(f"✅ Loaded {len(_rules.get('questions', []))} rules")
        except Exception as e:
            logger.warning(f"Failed to load rules: {e}. Continuing without rules.")
            _rules = {"questions": []}
            _rules_index = _build_rules_index(_rules)

        # 3) Import MCP server tool implementations
        try:
            import sys
            mcp_server_path = str(Path(__file__).parent.parent.parent / "mcp_server")
            if mcp_server_path not in sys.path:
                sys.path.insert(0, mcp_server_path)

            import main as mcp_main

            # Set the global variables in mcp_server module
            mcp_main._model = _model
            mcp_main._enrichment_storage = _enrichment_storage
            mcp_main._rules = _rules
            mcp_main._rules_index = _rules_index

            logger.info(f"✅ MCP server module loaded")
        except Exception as e:
            error_msg = "Failed to load MCP server module"
            logger.error(f"{error_msg}: {type(e).__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"{error_msg}. Check mcp_server/main.py is accessible."
            )

        # 4) Convert FastMCP tools to LangChain tools
        tools = []
        try:
            # Define all tool functions with their metadata
            tool_definitions = [
                ("search_airports", mcp_main.search_airports,
                 "Search airports by name, ICAO code, IATA code, or municipality. Returns matching airports with details."),

                ("get_airport_details", mcp_main.get_airport_details,
                 "Get detailed information about a specific airport by ICAO code. Returns runways, procedures, and border crossing status."),

                ("find_airports_near_route", mcp_main.find_airports_near_route,
                 "Find airports within a specified distance (in nautical miles) of a direct route between two airports. Useful for finding alternates or fuel stops."),

                ("get_border_crossing_airports", mcp_main.get_border_crossing_airports,
                 "List airports that are designated border crossing points (customs/immigration). Optional country filter (ISO-2 code)."),

                ("get_airport_statistics", mcp_main.get_airport_statistics,
                 "Get statistics about airports: total count, customs availability, fuel types, procedures. Optional country filter."),

                ("list_rules_for_country", mcp_main.list_rules_for_country,
                 "List aviation rules and regulations for a specific country (use ISO-2 code like FR, GB, CH). Can filter by category or tags."),

                ("compare_rules_between_countries", mcp_main.compare_rules_between_countries,
                 "Compare aviation rules between two countries (use ISO-2 codes). Shows differences in regulations."),

                ("get_answers_for_questions", mcp_main.get_answers_for_questions,
                 "Get answers for specific aviation rule questions by question IDs. Returns answers by country."),

                ("list_rule_categories_and_tags", mcp_main.list_rule_categories_and_tags,
                 "List available categories and tags in the aviation rules database. Useful for discovering what rules are available."),

                ("list_rule_countries", mcp_main.list_rule_countries,
                 "List all countries (ISO-2 codes) that have aviation rules in the database."),

                ("get_airport_pricing", mcp_main.get_airport_pricing,
                 "Get pricing information for an airport from airfield.directory: landing fees by aircraft type, fuel prices."),

                ("get_pilot_reviews", mcp_main.get_pilot_reviews,
                 "Get community pilot reviews (PIREPs) for an airport from airfield.directory. Includes ratings and comments."),

                ("get_fuel_prices", mcp_main.get_fuel_prices,
                 "Get fuel availability and current prices for an airport from airfield.directory: AVGAS, Jet A1, etc."),
            ]

            for name, func, desc in tool_definitions:
                # Wrap the function to remove ctx parameter and return just the pretty field
                def make_wrapper(f, n, d):
                    @tool(name=n, description=d)
                    def wrapper(**kwargs):
                        # Remove ctx if present (MCP Context parameter)
                        kwargs.pop("ctx", None)
                        result = f(**kwargs)
                        # Return pretty field for better LLM readability
                        if isinstance(result, dict) and "pretty" in result:
                            return result["pretty"]
                        return str(result)
                    return wrapper

                tools.append(make_wrapper(func, name, desc))

            logger.info(f"📦 Loaded {len(tools)} in-process MCP tools for LangChain")
            logger.info(f"   Available tools: {', '.join(t.name for t in tools)}")
        except Exception as e:
            error_msg = "Failed to convert MCP tools to LangChain format"
            logger.error(f"{error_msg}: {type(e).__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"{error_msg}. Check tool definitions."
            )

        # 5) Create LangChain agent with tools
        try:
            logger.info(f"🤖 Creating LangChain agent with model: {OPENAI_MODEL}")

            # Create agent using langchain 1.0.4 API
            _agent = create_agent(
                model=OPENAI_MODEL,
                tools=tools,
                system_prompt=SYSTEM_PROMPT
            )

            logger.info(f"✅ Agent created successfully with {len(tools)} tools")
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"Failed to create agent: {error_type}: {error_msg}", exc_info=True)

            if "API key" in error_msg or "authentication" in error_msg.lower():
                raise HTTPException(
                    status_code=500,
                    detail="OpenAI API authentication failed. Please check OPENAI_API_KEY environment variable."
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create agent: {error_type}. Check logs for details."
                )

        return _agent


# ---------------
# API models
# ---------------
class ChatMsg(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    input: str
    chat_history: Optional[List[ChatMsg]] = None


class AskResponse(BaseModel):
    text: str


# ---------------
# Endpoints
# ---------------
@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    """
    Chat endpoint that lets the model use your aviation MCP tools when helpful.
    Uses in-process MCP tools (like old codebase) with LangChain agents.
    """
    logger.info("=" * 80)
    logger.info(f"📨 New chat request received")
    logger.info(f"   User input: {req.input[:100]}{'...' if len(req.input) > 100 else ''}")
    logger.info(f"   Chat history: {len(req.chat_history or [])} messages")

    try:
        agent = await _get_agent()
    except HTTPException:
        # Re-raise HTTP exceptions (like 502 Bad Gateway)
        raise
    except Exception as e:
        logger.error(f"Failed to initialize agent: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize chat agent. Please try again later."
        )

    try:
        # Build messages for agent
        messages = []
        for msg in (req.chat_history or []):
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": req.input})

        logger.info(f"🤖 Invoking LangChain agent...")
        logger.info(f"   Total messages in context: {len(messages)}")

        result = await agent.ainvoke({"messages": messages})

        logger.info(f"✅ Agent invocation completed")
        logger.info(f"   Result type: {type(result)}")

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Agent invocation failed: {error_type}: {error_msg}", exc_info=True)

        # Provide user-friendly error messages based on error type
        if "API key" in error_msg or "authentication" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail="OpenAI API authentication failed. Please check API key configuration."
            )
        elif "rate limit" in error_msg.lower() or "429" in error_msg:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Please try again in a moment. Error: {error_msg}"
            )
        elif "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=504,
                detail="Request timed out. The operation may be slow or unresponsive."
            )
        else:
            # Generic error for unexpected issues
            raise HTTPException(
                status_code=500,
                detail="An error occurred while processing your request. Please try again."
            )

    # Extract text response from messages
    text_response = ""
    if isinstance(result, dict) and "messages" in result:
        # Get the last message from the agent
        messages = result["messages"]
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict):
                text_response = last_msg.get("content", "")
            else:
                text_response = getattr(last_msg, "content", str(last_msg))
    else:
        text_response = str(result)

    logger.info(f"📤 Returning response to user")
    logger.info(f"   Response length: {len(text_response)} characters")
    logger.info(f"   Preview: {text_response[:150]}{'...' if len(text_response) > 150 else ''}")
    logger.info("=" * 80)

    try:
        return AskResponse(text=text_response)
    except Exception as e:
        logger.error(f"Failed to format response: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to format agent response. Please try again."
        )


@router.get("/health")
async def chat_health():
    """
    Lightweight health check (verifies model loading the first time).
    """
    try:
        await _get_agent()
        return {
            "ok": True,
            "model": OPENAI_MODEL,
            "airports": len(_model.airports) if _model else 0,
            "rules": len(_rules.get("questions", [])) if _rules else 0
        }
    except HTTPException as e:
        # Re-raise HTTP exceptions with their status codes
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Health check failed: {error_type}: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {error_type}. Check logs for details."
        )
