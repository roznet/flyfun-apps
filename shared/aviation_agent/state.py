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
    """

    messages: Annotated[List[BaseMessage], operator.add]
    plan: Optional[AviationPlan]
    tool_result: Optional[Any]
    final_answer: Optional[str]
    ui_payload: Optional[dict]

