from __future__ import annotations

from typing import List, Literal, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..state import AgentState


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    def to_langchain(self) -> BaseMessage:
        if self.role == "system":
            return SystemMessage(content=self.content)
        if self.role == "assistant":
            return AIMessage(content=self.content)
        return HumanMessage(content=self.content)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)

    def to_langchain(self) -> List[BaseMessage]:
        if not self.messages:
            raise ValueError("ChatRequest.messages cannot be empty.")
        return [msg.to_langchain() for msg in self.messages]


class ChatResponse(BaseModel):
    answer: str
    planner_meta: dict | None = None
    ui_payload: dict | None = None


def build_chat_response(state: AgentState) -> ChatResponse:
    planner = state.get("plan")
    planner_meta = planner.model_dump() if hasattr(planner, "model_dump") else planner
    return ChatResponse(
        answer=state.get("final_answer") or "",
        planner_meta=planner_meta,
        ui_payload=state.get("ui_payload"),
    )

