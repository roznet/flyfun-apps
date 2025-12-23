from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping

from shared.airport_tools import (
    ToolSpec,
    get_shared_tool_specs,
)
from shared.tool_context import ToolContext


@dataclass(frozen=True)
class AviationTool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Dict[str, Any]]
    expose_to_llm: bool = True


class AviationToolInvocationError(RuntimeError):
    """Raised when an unknown tool is requested or execution fails."""


class AviationToolClient:
    """
    Thin wrapper around the shared tool handlers so LangGraph code can stay agnostic
    of ToolContext and the MCP server implementation.
    """

    def __init__(self, tool_context: ToolContext):
        specs = get_shared_tool_specs()
        self._context = tool_context
        self._tools: Mapping[str, AviationTool] = {
            name: AviationTool(
                name=name,
                description=spec["description"],
                parameters=spec["parameters"],
                handler=spec["handler"],
                expose_to_llm=spec.get("expose_to_llm", True),
            )
            for name, spec in specs.items()
        }

    @property
    def tools(self) -> Mapping[str, AviationTool]:
        return self._tools

    def available_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tool(self, tool_name: str) -> AviationTool:
        try:
            return self._tools[tool_name]
        except KeyError as exc:
            raise AviationToolInvocationError(f"Unknown tool: {tool_name}") from exc

    def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.get_tool(tool_name)
        try:
            # Filter out _persona_id if the tool handler doesn't accept it
            # Check if function accepts **kwargs or has _persona_id parameter
            sig = inspect.signature(tool.handler)
            accepts_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in sig.parameters.values()
            )
            has_persona_param = "_persona_id" in sig.parameters
            
            # Filter arguments based on function signature
            filtered_args = dict(arguments)
            if "_persona_id" in filtered_args and not (accepts_kwargs or has_persona_param):
                filtered_args = {k: v for k, v in filtered_args.items() if k != "_persona_id"}
            
            return tool.handler(self._context, **filtered_args)
        except Exception as exc:  # pragma: no cover - surface entire exception message
            raise AviationToolInvocationError(f"Tool '{tool_name}' failed: {exc}") from exc


def render_tool_catalog(tools: Iterable[AviationTool]) -> str:
    """
    Convert the manifest into a concise string suitable for planner prompts.
    """

    lines: list[str] = []
    for tool in tools:
        params = json.dumps(tool.parameters, indent=2, ensure_ascii=False)
        lines.append(f"- {tool.name}: {tool.description}\n  Parameters: {params}")
    return "\n".join(lines)

