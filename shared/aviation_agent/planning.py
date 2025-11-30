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
    
    Uses native structured output when available (e.g., ChatOpenAI.with_structured_output),
    which is more reliable with conversation history. Falls back to PydanticOutputParser if not available.
    """

    tool_catalog = render_tool_catalog(tools)

    # Use native structured output when available (more reliable with conversation history)
    # This is especially important for multi-turn conversations where PydanticOutputParser can fail
    if hasattr(llm, 'with_structured_output'):
        try:
            # Use function_calling method to avoid OpenAI's strict json_schema validation
            with_structured_output = getattr(llm, 'with_structured_output')
            structured_llm = with_structured_output(AviationPlan, method="function_calling")
            
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        (
                            "You are AviationPlan, a planning agent that selects exactly one aviation tool.\n"
                            "Tools:\n{tool_catalog}\n\n"
                            "**CRITICAL - Argument Extraction:**\n"
                            "You MUST extract ALL required arguments for the selected tool:\n"
                            "- find_airports_near_route: ALWAYS set 'from_location' and 'to_location' (pass location names exactly as user provides them, including country context)\n"
                            "- find_airports_near_location: ALWAYS set 'location_query' (include country if user mentions it, e.g., 'Vik, Iceland')\n"
                            "- get_airport_details: ALWAYS set 'icao_code'\n"
                            "- search_airports: ALWAYS set 'query'\n"
                            "- get_border_crossing_airports: optionally set 'country'\n"
                            "- list_rules_for_country: ALWAYS set 'country_code'\n"
                            "- compare_rules_between_countries: ALWAYS set 'country1' and 'country2'\n\n"
                            "**Filter Extraction:**\n"
                            "If the user mentions specific requirements (AVGAS, customs, runway length, country, etc.),\n"
                            "extract them as a 'filters' object in the 'arguments' field. Only include filters the user explicitly requests.\n"
                            "Available filters: has_avgas, has_jet_a, has_hard_runway, has_procedures, point_of_entry,\n"
                            "country (ISO-2 code), min_runway_length_ft, max_runway_length_ft, max_landing_fee.\n\n"
                            "Example: 'airports between Paris and LOWI' → {{'from_location': 'Paris', 'to_location': 'LOWI'}}\n"
                            "Example: 'airports near Vik, Iceland' → {{'location_query': 'Vik, Iceland'}}\n"
                            "Example: 'route from LFPG to LEMD with AVGAS' → {{'from_location': 'LFPG', 'to_location': 'LEMD', 'filters': {{'has_avgas': true}}}}\n\n"
                            "Pick the tool that can produce the most authoritative answer for the pilot."
                        ),
                    ),
                    MessagesPlaceholder(variable_name="messages"),
                    (
                        "human",
                        (
                            "Analyze the conversation above and select one tool from the manifest. "
                            "Do not invent tools. You MUST populate the 'arguments' field with ALL required arguments for the selected tool. "
                            "Extract any filters the user mentioned into arguments.filters."
                        ),
                    ),
                ]
            )
            
            chain = prompt | structured_llm
            
            def _invoke(state: Dict[str, Any]) -> AviationPlan:
                plan = chain.invoke({"messages": state["messages"], "tool_catalog": tool_catalog})
                _validate_selected_tool(plan.selected_tool, tools)
                return plan
            
            return RunnableLambda(_invoke)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to use native structured output, falling back to PydanticOutputParser: {e}", exc_info=True)

    # Fallback: Use PydanticOutputParser (less reliable with conversation history)
    parser = PydanticOutputParser(pydantic_object=AviationPlan)
    format_instructions = parser.get_format_instructions()

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are AviationPlan, a planning agent that selects exactly one aviation tool.\n"
                    "Tools:\n{tool_catalog}\n\n"
                    "**CRITICAL - Argument Extraction:**\n"
                    "You MUST extract ALL required arguments for the selected tool:\n"
                    "- find_airports_near_route: ALWAYS set 'from_location' and 'to_location' (pass location names exactly as user provides them, including country context)\n"
                    "- find_airports_near_location: ALWAYS set 'location_query' (include country if user mentions it, e.g., 'Vik, Iceland')\n"
                    "- get_airport_details: ALWAYS set 'icao_code'\n"
                    "- search_airports: ALWAYS set 'query'\n"
                    "- get_border_crossing_airports: optionally set 'country'\n"
                    "- list_rules_for_country: ALWAYS set 'country_code'\n"
                    "- compare_rules_between_countries: ALWAYS set 'country1' and 'country2'\n\n"
                    "**Filter Extraction:**\n"
                    "If the user mentions specific requirements (AVGAS, customs, runway length, country, etc.),\n"
                    "extract them as a 'filters' object in the 'arguments' field. Only include filters the user explicitly requests.\n"
                    "Available filters: has_avgas, has_jet_a, has_hard_runway, has_procedures, point_of_entry,\n"
                    "country (ISO-2 code), min_runway_length_ft, max_runway_length_ft, max_landing_fee.\n\n"
                    "Example: 'airports between Paris and LOWI' → {{'from_location': 'Paris', 'to_location': 'LOWI'}}\n"
                    "Example: 'airports near Vik, Iceland' → {{'location_query': 'Vik, Iceland'}}\n"
                    "Example: 'route from LFPG to LEMD with AVGAS' → {{'from_location': 'LFPG', 'to_location': 'LEMD', 'filters': {{'has_avgas': true}}}}\n\n"
                    "Pick the tool that can produce the most authoritative answer for the pilot."
                ),
            ),
            MessagesPlaceholder(variable_name="messages"),
            (
                "human",
                (
                    "Analyze the conversation above and emit a JSON plan. You must use one tool "
                    "from the manifest. Do not invent tools. You MUST populate the 'arguments' field with ALL required arguments for the selected tool. "
                    "Return an actual plan instance with 'selected_tool', 'arguments', and 'answer_style' fields, not the schema description.\n\n"
                    "{format_instructions}"
                ),
            ),
        ]
    )

    def _prepare_input(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "messages": state["messages"],
            "tool_catalog": tool_catalog,
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


