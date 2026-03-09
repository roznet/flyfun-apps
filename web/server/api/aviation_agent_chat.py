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
from sqlalchemy.orm import Session

from flyfun_common.db import current_user_id, SessionLocal

from shared.aviation_agent.adapters import (
    ChatRequest,
    ChatResponse,
    build_agent,
    build_chat_response,
    run_aviation_agent,
    stream_aviation_agent,
)
from shared.aviation_agent.adapters.logging import (
    find_conversation_by_run_id,
    log_conversation_from_state,
    log_feedback,
)
from shared.aviation_agent.config import AviationAgentSettings, get_settings

router = APIRouter(tags=["aviation-agent"])
logger = logging.getLogger(__name__)

# Lazy-loaded LangSmith client for feedback
_langsmith_client = None


def _get_langsmith_client():
    """Get or create LangSmith client (lazy initialization)."""
    global _langsmith_client
    if _langsmith_client is None:
        try:
            from langsmith import Client
            _langsmith_client = Client()
        except Exception as e:
            logger.warning(f"Failed to initialize LangSmith client: {e}")
            return None
    return _langsmith_client


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


class FeedbackRequest(BaseModel):
    """User feedback for a conversation."""
    run_id: str
    score: int  # 1 = thumbs up, 0 = thumbs down
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""
    status: str
    feedback_id: Optional[str] = None


def feature_enabled(settings: Optional[AviationAgentSettings] = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.enabled)


@router.post("/chat", response_model=ChatResponse)
def aviation_agent_chat(
    request: ChatRequest,
    user_id: str = Depends(current_user_id),
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
    user_id: str = Depends(current_user_id),
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

    # Check per-user daily rate limit before starting the expensive LLM call
    from api.chat_usage import check_chat_rate_limit, log_chat_usage
    db_session = SessionLocal()
    try:
        check_chat_rate_limit(db_session, user_id)
    finally:
        db_session.close()

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
        log_dir = Path(os.getenv("CONVERSATION_LOG_DIR", "logs/conversations"))

        async def event_generator():
            final_state = None
            run_id = None
            captured_input_tokens = 0
            captured_output_tokens = 0
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

                    # Capture run_id and token counts from done event
                    if event_name == "done":
                        run_id = event_data.get("run_id")
                        tokens = event_data.get("tokens", {})
                        captured_input_tokens = tokens.get("input", 0)
                        captured_output_tokens = tokens.get("output", 0)

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
                            run_id=run_id,
                        )
                        logger.info("Conversation logged successfully")
                    else:
                        logger.warning("Final state not captured during streaming, skipping conversation logging")
                except Exception as e:
                    logger.error(f"Error in conversation logging: {e}", exc_info=True)

                # Log chat usage and cost
                try:
                    usage_db = SessionLocal()
                    try:
                        log_chat_usage(
                            usage_db,
                            user_id,
                            model=settings.model_name,
                            input_tokens=captured_input_tokens,
                            output_tokens=captured_output_tokens,
                            thread_id=thread_id,
                            persona_id=request.persona_id,
                        )
                        usage_db.commit()
                    except Exception as e:
                        usage_db.rollback()
                        logger.error(f"Failed to log chat usage: {e}")
                    finally:
                        usage_db.close()
                except Exception as e:
                    logger.error(f"Error creating usage session: {e}")
        
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


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    user_id: str = Depends(current_user_id),
    settings: AviationAgentSettings = Depends(get_settings),
) -> FeedbackResponse:
    """
    Submit user feedback (thumbs up/down) for a conversation.

    This feedback is sent to LangSmith for quality monitoring and analysis,
    and also saved locally to conversation logs.

    Args:
        request: FeedbackRequest with run_id, score (1=good, 0=bad), and optional comment

    Returns:
        FeedbackResponse with status and feedback_id
    """
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Aviation agent is disabled.")

    # Send feedback to LangSmith
    client = _get_langsmith_client()
    feedback_id = None
    if client is None:
        logger.warning("LangSmith client not available, feedback not recorded to LangSmith")
    else:
        try:
            feedback = client.create_feedback(
                run_id=request.run_id,
                key="user-rating",
                score=request.score,
                comment=request.comment,
            )
            feedback_id = str(feedback.id)
            logger.info(f"Feedback submitted to LangSmith for run {request.run_id}: score={request.score}")
        except Exception as e:
            logger.error(f"Failed to submit feedback to LangSmith: {e}")
            # Continue to save locally even if LangSmith fails

    # Also save feedback locally to conversation logs
    try:
        log_dir = Path(os.getenv("CONVERSATION_LOG_DIR", "logs/conversations"))
        conversation_entry = find_conversation_by_run_id(request.run_id, log_dir)
        log_feedback(
            run_id=request.run_id,
            score=request.score,
            comment=request.comment,
            conversation_entry=conversation_entry,
            log_dir=log_dir,
        )
    except Exception as e:
        logger.error(f"Failed to save feedback locally: {e}", exc_info=True)
        # Don't fail the request if local logging fails

    return FeedbackResponse(
        status="ok" if feedback_id else "skipped",
        feedback_id=feedback_id,
    )

