from __future__ import annotations

from typing import Any, Dict, Optional

from .planning import AviationPlan
from .state import AgentState
from .tools import AviationToolClient


class ToolRunner:
    def __init__(self, tool_client: AviationToolClient):
        self.tool_client = tool_client

    def run(self, plan: AviationPlan, state: Optional[AgentState] = None) -> Dict[str, Any]:
        arguments = plan.arguments or {}
        
        # Extract persona_id from state and inject into arguments for tools to use
        if state and "persona_id" in state:
            # Inject persona_id as a special parameter that tools can extract
            # Tools will check for this and pass it to PriorityEngine
            arguments = dict(arguments)  # Make a copy to avoid mutating original
            arguments["_persona_id"] = state["persona_id"]
        
        return self.tool_client.invoke(plan.selected_tool, arguments)

