from __future__ import annotations

import operator
from typing import Any, List, Optional

from langchain_core.messages import BaseMessage
from typing_extensions import Annotated, TypedDict

from .planning import AviationPlan
from .routing import RouterDecision


class AgentState(TypedDict, total=False):
    """
    Canonical state shared between LangGraph nodes.

    LangGraph reducers merge dictionaries, so we annotate messages with
    operator.add semantics via typing_extensions.Annotated (per LangGraph docs).
    
    State supports two paths:
    1. Rules path: router → RAG retrieval → rules agent → final answer
    2. Database path: router → planner → tool → formatter → final answer
    3. Both path: router → database + rules → formatter → final answer
    """

    messages: Annotated[List[BaseMessage], operator.add]
    
    # Routing (Phase 2)
    router_decision: Optional[RouterDecision]  # Routing decision (rules/database/both)
    
    # Rules path (Phase 1 & 3)
    retrieved_rules: Optional[List[dict]]  # Rules from RAG retrieval
    rules_answer: Optional[str]  # Synthesized answer from rules agent
    rules_sources: Optional[List[dict]]  # Source links from rules
    
    # Database path (existing)
    plan: Optional[AviationPlan]  # Tool selection plan
    planning_reasoning: Optional[str]  # Planner's reasoning (why this tool/approach)
    tool_result: Optional[Any]  # Result from tool execution
    
    # Common/output
    formatting_reasoning: Optional[str]  # Formatter's reasoning (how to present results)
    final_answer: Optional[str]  # Final answer to user
    thinking: Optional[str]  # Combined reasoning for UI (planning + formatting)
    ui_payload: Optional[dict]  # UI-specific data (charts, maps, etc.)
    error: Optional[str]  # Error message if execution fails

    # User preferences
    persona_id: Optional[str]  # Persona ID for airport prioritization

    # Next query prediction
    suggested_queries: Optional[List[dict]]  # Suggested follow-up queries

