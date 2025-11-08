#!/usr/bin/env python3
"""
Chatbot API endpoints for Euro AIP Pilot Assistant
"""

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)

# Global chatbot service instance
chatbot_service = None

# In-memory session storage (in production, use Redis or database)
chat_sessions = {}


class ChatMessage(BaseModel):
    """Model for a chat message"""
    message: str = Field(..., description="User's message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    history: Optional[List[Dict[str, Any]]] = Field(None, description="Conversation history")


class ChatResponse(BaseModel):
    """Model for chat response"""
    message: str = Field(..., description="Assistant's response")
    thinking: Optional[str] = Field(None, description="Thinking process (reasoning)")
    visualization: Optional[Any] = Field(None, description="Map visualization data")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Tools that were called")
    session_id: str = Field(..., description="Session ID")
    history: List[Dict[str, Any]] = Field(default_factory=list, description="Updated conversation history")


def set_chatbot_service(service):
    """Set the global chatbot service instance"""
    global chatbot_service
    chatbot_service = service
    logger.info("Chatbot service registered with API")


@router.post("/", response_model=ChatResponse)
async def chat(chat_request: ChatMessage = Body(...)):
    """
    Main chat endpoint. Processes user messages and returns AI responses with map visualization.
    """
    if chatbot_service is None:
        raise HTTPException(status_code=500, detail="Chatbot service not initialized")

    try:
        # Get or create session ID
        session_id = chat_request.session_id or str(uuid.uuid4())

        # Get history from request or session storage
        history = chat_request.history
        if not history and session_id in chat_sessions:
            history = chat_sessions[session_id]

        logger.info(f"Processing chat request for session {session_id}: {chat_request.message}")

        # Call chatbot service
        response = chatbot_service.chat(
            message=chat_request.message,
            history=history,
            session_id=session_id
        )

        # Store updated history in session
        chat_sessions[session_id] = response["history"]

        return ChatResponse(
            message=response["message"],
            thinking=response.get("thinking"),
            visualization=response.get("visualization"),
            tool_calls=response.get("tool_calls", []),
            session_id=session_id,
            history=response["history"]
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(chat_request: ChatMessage = Body(...)):
    """
    Streaming chat endpoint. Returns SSE (Server-Sent Events) for progressive response.
    Events: thinking, message, tool_calls, visualization, done, error
    """
    if chatbot_service is None:
        raise HTTPException(status_code=500, detail="Chatbot service not initialized")

    try:
        # Get or create session ID
        session_id = chat_request.session_id or str(uuid.uuid4())

        # Get history from request or session storage
        history = chat_request.history
        if not history and session_id in chat_sessions:
            history = chat_sessions[session_id]

        logger.info(f"Processing streaming chat request for session {session_id}: {chat_request.message}")

        # Return streaming response
        return StreamingResponse(
            chatbot_service.chat_stream(
                message=chat_request.message,
                history=history,
                session_id=session_id
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

    except Exception as e:
        logger.error(f"Error in streaming chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quick-actions")
async def get_quick_actions():
    """
    Get list of quick action prompts for the UI.
    """
    if chatbot_service is None:
        raise HTTPException(status_code=500, detail="Chatbot service not initialized")

    try:
        actions = chatbot_service.get_quick_actions()
        return {"actions": actions}
    except Exception as e:
        logger.error(f"Error getting quick actions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """
    Clear a chat session's history.
    """
    if session_id in chat_sessions:
        del chat_sessions[session_id]
        return {"message": "Session cleared", "session_id": session_id}
    else:
        return {"message": "Session not found", "session_id": session_id}


@router.get("/sessions")
async def list_sessions():
    """
    List active chat sessions (for debugging/admin).
    """
    return {
        "sessions": list(chat_sessions.keys()),
        "count": len(chat_sessions)
    }


@router.get("/health")
async def health_check():
    """
    Health check for chatbot service.
    """
    if chatbot_service is None:
        raise HTTPException(status_code=503, detail="Chatbot service not initialized")

    return {
        "status": "healthy",
        "service": "chatbot",
        "llm_model": chatbot_service.llm_model,
        "tools_available": len(chatbot_service.tools)
    }
