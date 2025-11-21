from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Sequence

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field

from .tools import AviationTool, render_tool_catalog


class AviationPlan(BaseModel):
    """
    Structured representation of the planner's decision.

    The planner selects exactly one tool name from the shared manifest and
    provides the arguments that should be sent to that tool. The formatter can
    use `answer_style` to decide between brief, narrative, checklist, etc.
    """

    selected_tool: str = Field(..., description="Name of the tool to call.")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to call the selected tool with.",
    )
    answer_style: str = Field(
        default="narrative_markdown",
        description="Preferred style for the final answer (hint for formatter).",
    )


def build_planner_runnable(
    llm: Runnable,
    tools: Sequence[AviationTool],
) -> Runnable:
    """
    Create a runnable that turns conversation history into an AviationPlan.
    """

    tool_catalog = render_tool_catalog(tools)
    parser = PydanticOutputParser(pydantic_object=AviationPlan)
    format_instructions = parser.get_format_instructions()

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are AviationPlan, a planning agent that selects exactly one aviation tool.\n"
                    "Tools:\n{tool_catalog}\n\n"
                    "**Filter Extraction:**\n"
                    "If the user mentions specific requirements (AVGAS, customs, runway length, country, etc.),\n"
                    "extract them as a 'filters' object in the 'arguments' field. Only include filters the user explicitly requests.\n"
                    "Available filters: has_avgas, has_jet_a, has_hard_runway, has_procedures, point_of_entry,\n"
                    "country (ISO-2 code), min_runway_length_ft, max_runway_length_ft, max_landing_fee.\n\n"
                    "Example: If user says 'fuel stop with AVGAS', set arguments.filters = {{'has_avgas': true}}\n\n"
                    "Always return JSON that matches this schema:\n{schema}\n"
                    "Pick the tool that can produce the most authoritative answer for the pilot."
                ),
            ),
            MessagesPlaceholder(variable_name="messages"),
            (
                "human",
                (
                    "Analyze the conversation above and emit a JSON plan. You must use one tool "
                    "from the manifest. Do not invent tools. Reply with JSON only.\n"
                    "{format_instructions}"
                ),
            ),
        ]
    )

    def _prepare_input(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "messages": state["messages"],
            "tool_catalog": tool_catalog,
            "schema": json.dumps(AviationPlan.model_json_schema(), indent=2),
            "format_instructions": format_instructions,
        }

    chain = prompt | llm | parser

    def _invoke(state: Dict[str, Any]) -> AviationPlan:
        plan = chain.invoke(_prepare_input(state))
        _validate_selected_tool(plan.selected_tool, tools)
        return plan

    return RunnableLambda(_invoke)


def _validate_selected_tool(tool_name: str, tools: Sequence[AviationTool]) -> None:
    if tool_name not in {tool.name for tool in tools}:
        raise ValueError(
            f"Planner chose '{tool_name}', which is not defined in the manifest."
        )


