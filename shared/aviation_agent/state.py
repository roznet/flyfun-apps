from __future__ import annotations

import operator
from typing import Any, List, Optional

from langchain_core.messages import BaseMessage
from typing_extensions import Annotated, TypedDict

from .planning import AviationPlan


class AgentState(TypedDict, total=False):
    """
    Canonical state shared between LangGraph nodes.

    LangGraph reducers merge dictionaries, so we annotate messages with
    operator.add semantics via typing_extensions.Annotated (per LangGraph docs).

    Flow: Planner → [Predict Next Queries] → Tool → Formatter → END

    The planner handles all tool selection including:
    - answer_rules_question: For specific questions about ONE country (uses RAG)
    - browse_rules: For listing/browsing rules by category/tags
    - compare_rules_between_countries: For comparing 2+ countries
    - Airport tools: search_airports, find_airports_near_location, etc.
    """

    messages: Annotated[List[BaseMessage], operator.add]

    # Planning
    plan: Optional[AviationPlan]  # Tool selection plan
    planning_reasoning: Optional[str]  # Planner's reasoning (why this tool/approach)

    # Tool execution
    tool_result: Optional[Any]  # Result from tool execution

    # Output
    formatting_reasoning: Optional[str]  # Formatter's reasoning (how to present results)
    final_answer: Optional[str]  # Final answer to user
    thinking: Optional[str]  # Combined reasoning for UI (planning + formatting)
    ui_payload: Optional[dict]  # UI-specific data (charts, maps, etc.)
    error: Optional[str]  # Error message if execution fails

    # User preferences
    persona_id: Optional[str]  # Persona ID for airport prioritization

    # Next query prediction
    suggested_queries: Optional[List[dict]]  # Suggested follow-up queries

