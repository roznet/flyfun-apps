from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from shared.aviation_agent.adapters import (
    ChatRequest,
    ChatResponse,
    build_agent,
    build_chat_response,
    run_aviation_agent,
    stream_aviation_agent,
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


@router.post("/chat/stream")
async def aviation_agent_chat_stream(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
) -> StreamingResponse:
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")
    
    try:
        graph = build_agent(settings=settings)
        
        async def event_generator():
            session_id = getattr(request, 'session_id', None)  # Extract from request if available
            async for event in stream_aviation_agent(
                request.to_langchain(),
                graph,
                session_id=session_id
            ):
                event_name = event.get("event")
                event_data = event.get("data", {})
                yield f"event: {event_name}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as exc:
        logger.exception("Aviation agent streaming failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

