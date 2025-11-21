from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from shared.aviation_agent.adapters import (
    ChatRequest,
    ChatResponse,
    build_chat_response,
    run_aviation_agent,
)
from shared.aviation_agent.config import AviationAgentSettings, get_settings

router = APIRouter(tags=["aviation-agent"])
logger = logging.getLogger(__name__)


def feature_enabled(settings: Optional[AviationAgentSettings] = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.enabled)


@router.post("/chat", response_model=ChatResponse)
def aviation_agent_chat(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
) -> ChatResponse:
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")

    try:
        state = run_aviation_agent(request.to_langchain(), settings=settings)
    except Exception as exc:  # pragma: no cover - runtime failure surfaced to clients
        logger.exception("Aviation agent failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return build_chat_response(state)

