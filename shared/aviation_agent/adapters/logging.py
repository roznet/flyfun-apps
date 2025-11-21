"""
Conversation logging adapter for aviation agent.

Simple post-execution logging approach - extracts data from final agent state
and saves to JSON log files (one file per day).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


def log_conversation_from_state(
    session_id: str,
    state: Dict[str, Any],
    messages: List[BaseMessage],
    start_time: float,
    end_time: float,
    log_dir: Path,
) -> None:
    """
    Log conversation from final agent state (simple post-execution approach).
    
    Args:
        session_id: Unique session identifier
        state: Final AgentState from agent execution
        messages: Conversation messages
        start_time: Request start timestamp (from time.time())
        end_time: Request end timestamp (from time.time())
        log_dir: Directory to save log files
    """
    try:
        # Extract data from state
        plan = state.get("plan")
        tool_result = state.get("tool_result")
        final_answer = state.get("final_answer", "")
        thinking = state.get("thinking", "")
        ui_payload = state.get("ui_payload")
        error = state.get("error")
        
        # Build tool_calls list
        tool_calls = []
        if plan and tool_result:
            # Handle both Pydantic model and dict
            if hasattr(plan, "selected_tool"):
                tool_name = plan.selected_tool
                tool_args = plan.arguments if hasattr(plan, "arguments") else {}
            else:
                tool_name = plan.get("selected_tool", "")
                tool_args = plan.get("arguments", {})
            
            tool_calls.append({
                "name": tool_name,
                "arguments": tool_args,
                "result": tool_result
            })
        
        # Extract user question from last message
        question = ""
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                question = last_message.content
            elif isinstance(last_message, dict):
                question = last_message.get("content", "")
        
        # Calculate duration
        duration_seconds = end_time - start_time
        
        # Build log entry (reuse existing format for backward compatibility)
        log_entry = {
            "session_id": session_id,
            "timestamp": datetime.fromtimestamp(start_time).isoformat(),
            "timestamp_end": datetime.fromtimestamp(end_time).isoformat(),
            "duration_seconds": round(duration_seconds, 2),
            "question": question,
            "answer": final_answer,
            "thinking": thinking,
            "tool_calls": tool_calls,
            "metadata": {
                "has_visualizations": ui_payload is not None,
                "num_tool_calls": len(tool_calls),
                "has_error": error is not None,
            }
        }
        
        # Add error if present
        if error:
            log_entry["error"] = error
        
        # Save to file
        _save_log_entry(log_entry, log_dir)
        
    except Exception as e:
        logger.error(f"Error logging conversation: {e}", exc_info=True)
        # Don't fail request if logging fails


def _save_log_entry(log_entry: Dict[str, Any], log_dir: Path) -> None:
    """
    Save log entry to JSON file (one file per day).
    
    Format: conversation_logs/YYYY-MM-DD.json
    """
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename: YYYY-MM-DD.json (one file per day)
        timestamp_str = log_entry["timestamp"]
        if isinstance(timestamp_str, str):
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = datetime.fromtimestamp(timestamp_str)
        
        date_str = timestamp.strftime("%Y-%m-%d")
        log_file = log_dir / f"{date_str}.json"
        
        # Read existing logs for today
        logs = []
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Could not read existing log file {log_file}, starting fresh")
                logs = []
        
        # Append new entry
        logs.append(log_entry)
        
        # Write back
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Conversation logged to {log_file} (duration: {log_entry['duration_seconds']:.2f}s)")
        
    except Exception as e:
        logger.error(f"Error saving log entry: {e}", exc_info=True)
        # Don't fail request if logging fails

