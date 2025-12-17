from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shared.aviation_agent.adapters import (
    ChatRequest,
    ChatResponse,
    build_agent,
    build_chat_response,
    run_aviation_agent,
    stream_aviation_agent,
)
from shared.aviation_agent.adapters.logging import log_conversation_from_state
from shared.aviation_agent.config import AviationAgentSettings, get_settings

router = APIRouter(tags=["aviation-agent"])
logger = logging.getLogger(__name__)


def _generate_thread_id() -> str:
    """Generate a unique thread ID for a new conversation."""
    return f"thread_{uuid.uuid4().hex[:12]}"


class QuickAction(BaseModel):
    """Quick action button definition."""
    icon: str  # Emoji (≤2 chars) or FontAwesome icon name (without 'fa-')
    title: str
    prompt: str


class QuickActionsResponse(BaseModel):
    """Response containing quick actions."""
    actions: List[QuickAction]


def feature_enabled(settings: Optional[AviationAgentSettings] = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.enabled)


@router.post("/chat", response_model=ChatResponse)
def aviation_agent_chat(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
) -> ChatResponse:
    """
    Non-streaming chat endpoint.

    Args:
        request: ChatRequest with messages, persona_id, and optional thread_id.
            If thread_id is provided, continues an existing conversation.
            If thread_id is None, starts a new conversation.

    Returns:
        ChatResponse with answer, metadata, and thread_id for continuation.
    """
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")

    # Generate thread_id if not provided (new conversation)
    thread_id = request.thread_id or _generate_thread_id()

    try:
        state = run_aviation_agent(
            request.to_langchain(),
            settings=settings,
            persona_id=request.persona_id,
            thread_id=thread_id,
        )
    except Exception as exc:  # pragma: no cover - runtime failure surfaced to clients
        logger.exception("Aviation agent failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return build_chat_response(state, thread_id=thread_id)


@router.post("/chat/stream")
async def aviation_agent_chat_stream(
    request: ChatRequest,
    settings: AviationAgentSettings = Depends(get_settings),
    session_id: Optional[str] = None,  # Extract from header if available
) -> StreamingResponse:
    """
    SSE streaming chat endpoint.

    Args:
        request: ChatRequest with messages, persona_id, and optional thread_id.
            If thread_id is provided, continues an existing conversation.
            If thread_id is None, starts a new conversation.

    Returns:
        StreamingResponse with SSE events including thread_id in the 'done' event.
    """
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")

    try:
        graph = build_agent(settings=settings)
        messages = request.to_langchain()
        start_time = time.time()

        # Get session_id from request or header
        if not session_id:
            session_id = getattr(request, 'session_id', None) or f"session_{int(time.time())}"

        # Generate thread_id if not provided (new conversation)
        thread_id = request.thread_id or _generate_thread_id()

        # Setup conversation logging
        log_dir = Path(os.getenv("CONVERSATION_LOG_DIR", "conversation_logs"))

        async def event_generator():
            final_state = None
            try:
                async for event in stream_aviation_agent(
                    messages,
                    graph,
                    session_id=session_id,
                    persona_id=request.persona_id,
                    thread_id=thread_id,
                ):
                    event_name = event.get("event")
                    event_data = event.get("data", {})

                    # Capture final state when graph completes
                    if event_name == "final_answer":
                        final_state = event_data.get("state")

                    yield f"event: {event_name}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
            finally:
                # After streaming completes, log conversation using captured state
                try:
                    end_time = time.time()

                    if final_state:
                        logger.info(f"Logging conversation for session {session_id}...")
                        log_conversation_from_state(
                            session_id=session_id,
                            state=final_state,
                            messages=messages,
                            start_time=start_time,
                            end_time=end_time,
                            log_dir=log_dir,
                        )
                        logger.info("Conversation logged successfully")
                    else:
                        logger.warning("Final state not captured during streaming, skipping conversation logging")
                except Exception as e:
                    logger.error(f"Error in conversation logging: {e}", exc_info=True)
        
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


@router.get("/quick-actions", response_model=QuickActionsResponse)
def get_quick_actions(
    settings: AviationAgentSettings = Depends(get_settings),
) -> QuickActionsResponse:
    """
    Get quick action buttons for the chatbot UI.
    
    Returns a list of predefined actions that users can click to quickly
    send common queries to the aviation agent.
    """
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")
    
    actions = [
        QuickAction(
            icon="✈️",
            title="Airports near route",
            prompt="Find airports between EGTF and LFMD"
        ),
        QuickAction(
            icon="plane",
            title="Border crossing airports",
            prompt="Show me border crossing airports in France"
        ),
        QuickAction(
            icon="map-marker-alt",
            title="Airports near location",
            prompt="Find airports near Paris"
        ),
        QuickAction(
            icon="fuel-pump",
            title="Airports with AVGAS",
            prompt="Find airports with AVGAS in Germany"
        ),
        QuickAction(
            icon="route",
            title="IFR procedures",
            prompt="Show airports with IFR near EGTF"
        ),
        QuickAction(
            icon="book",
            title="Country rules",
            prompt="What are the rules for flying IFR to an uncontrolled airport in France?"
        ),
    ]
    
    return QuickActionsResponse(actions=actions)

