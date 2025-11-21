from __future__ import annotations

from typing import Dict

from .planning import AviationPlan
from .tools import AviationToolClient


class ToolRunner:
    def __init__(self, tool_client: AviationToolClient):
        self.tool_client = tool_client

    def run(self, plan: AviationPlan) -> Dict:
        return self.tool_client.invoke(plan.selected_tool, plan.arguments or {})

