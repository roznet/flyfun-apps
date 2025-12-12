from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field

from .tools import AviationTool, render_tool_catalog


class ToolCall(BaseModel):
    """Single tool call with name and arguments."""
    tool_name: str = Field(..., description="Name of the tool to call.")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to call the tool with.",
    )


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
    
    def get_tool_calls(self) -> List[ToolCall]:
        """Get tool calls for compatibility with tool_node."""
        return [ToolCall(tool_name=self.selected_tool, arguments=self.arguments)]


def _build_planner_prompt_messages(
    system_prompt: str,
    example_messages: list[BaseMessage],
    final_instruction: str,
) -> list[Any]:
    """
    Build prompt messages list for planner: system, examples, conversation placeholder, final instruction.
    """
    # Use Any type since ChatPromptTemplate.from_messages accepts mixed types
    prompt_messages: list[Any] = [
        (
            "system",
            system_prompt,  # ChatPromptTemplate will handle {tool_catalog} variable
        ),
    ]
    # Add example messages if available
    if example_messages:
        prompt_messages.extend(example_messages)
    # Add conversation history placeholder
    prompt_messages.append(MessagesPlaceholder(variable_name="messages"))
    # Add final instruction
    prompt_messages.append(("human", final_instruction))
    return prompt_messages


def build_planner_runnable(
    llm: Runnable,
    tools: Sequence[AviationTool],
    system_prompt: Optional[str] = None,
) -> Runnable:
    """
    Create a runnable that turns conversation history into an AviationPlan.
    
    Uses native structured output when available (e.g., ChatOpenAI.with_structured_output),
    which is more reliable with conversation history. Falls back to PydanticOutputParser if not available.
    """

    tool_catalog = render_tool_catalog(tools)
    
    # Load system prompt and examples from config if not provided
    example_messages: list[BaseMessage] = []
    if system_prompt is None:
        from .config import get_settings, get_behavior_config
        settings = get_settings()
        behavior_config = get_behavior_config(settings.agent_config_name)
        system_prompt = behavior_config.load_prompt("planner")
        
        # Load examples and convert to LangChain messages
        examples = behavior_config.load_examples("planner")
        example_messages = _convert_examples_to_messages(examples)
    
    # Ensure system_prompt is not None (should always be set by now)
    if system_prompt is None:
        raise ValueError("System prompt must be provided or available in config")

    # Use native structured output when available (more reliable with conversation history)
    # This is especially important for multi-turn conversations where PydanticOutputParser can fail
    if hasattr(llm, 'with_structured_output'):
        try:
            # Use function_calling method to avoid OpenAI's strict json_schema validation
            with_structured_output = getattr(llm, 'with_structured_output')
            structured_llm = with_structured_output(AviationPlan, method="function_calling")
            
            final_instruction = (
                "Analyze the conversation above and select one tool from the manifest. "
                "Do not invent tools. You MUST populate the 'arguments' field with ALL required arguments for the selected tool. "
                "Extract any filters the user mentioned into arguments.filters."
            )
            prompt_messages = _build_planner_prompt_messages(
                system_prompt, example_messages, final_instruction
            )
            prompt = ChatPromptTemplate.from_messages(prompt_messages)
            
            chain = prompt | structured_llm
            
            def _invoke(state: Dict[str, Any]) -> AviationPlan:
                plan = chain.invoke({"messages": state["messages"], "tool_catalog": tool_catalog})
                _validate_plan(plan, tools)
                return plan
            
            return RunnableLambda(_invoke)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to use native structured output, falling back to PydanticOutputParser: {e}", exc_info=True)

    # Fallback: Use PydanticOutputParser (less reliable with conversation history)
    parser = PydanticOutputParser(pydantic_object=AviationPlan)
    format_instructions = parser.get_format_instructions()

    final_instruction = (
        "Analyze the conversation above and emit a JSON plan. You must use one tool "
        "from the manifest. Do not invent tools. You MUST populate the 'arguments' field with ALL required arguments for the selected tool. "
        "Return an actual plan instance with 'selected_tool', 'arguments', and 'answer_style' fields, not the schema description.\n\n"
        "{format_instructions}"
    )
    prompt_messages = _build_planner_prompt_messages(
        system_prompt, example_messages, final_instruction
    )
    prompt = ChatPromptTemplate.from_messages(prompt_messages)

    def _prepare_input(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "messages": state["messages"],
            "tool_catalog": tool_catalog,
            "format_instructions": format_instructions,
        }

    chain = prompt | llm | parser

    def _invoke(state: Dict[str, Any]) -> AviationPlan:
        plan = chain.invoke(_prepare_input(state))
        _validate_plan(plan, tools)
        return plan

    return RunnableLambda(_invoke)


def _convert_examples_to_messages(examples: list[dict[str, str]]) -> list[BaseMessage]:
    """
    Convert example JSON structure to LangChain messages.
    
    Each example has 'question' (user input) and 'answer' (JSON string of AviationPlan).
    Returns list of HumanMessage/AIMessage pairs.
    """
    messages: list[BaseMessage] = []
    for example in examples:
        question = example.get("question", "")
        answer = example.get("answer", "")
        if question and answer:
            messages.append(HumanMessage(content=question))
            # The answer is already a JSON string representing the AviationPlan
            messages.append(AIMessage(content=answer))
    return messages


def _validate_selected_tool(tool_name: str, tools: Sequence[AviationTool]) -> None:
    """Validate a single tool name is in the manifest."""
    valid_names = {tool.name for tool in tools}
    if tool_name and tool_name not in valid_names:
        raise ValueError(
            f"Planner chose '{tool_name}', which is not defined in the manifest."
        )


def _validate_plan(plan: "AviationPlan", tools: Sequence[AviationTool]) -> None:
    """Validate an AviationPlan - handles both single and multi-tool patterns."""
    valid_names = {tool.name for tool in tools}
    
    tool_calls = plan.get_tool_calls()
    if not tool_calls:
        raise ValueError("Plan has no tool calls (neither selected_tool nor tool_calls populated).")
    
    for tc in tool_calls:
        if tc.tool_name not in valid_names:
            raise ValueError(
                f"Planner chose '{tc.tool_name}', which is not defined in the manifest."
            )


