from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


async def stream_aviation_agent(
    messages: List[BaseMessage],
    graph: Any,  # Compiled graph from LangGraph (type: CompiledGraph from langgraph.checkpoint)
    session_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream agent execution with SSE-compatible events and token tracking.
    
    Uses LangGraph's astream_events() which is the standard pattern for:
    - Streaming node execution
    - Tracking token usage from LLM calls
    - Capturing tool execution
    
    Yields SSE events:
        - {"event": "plan", "data": {...}} - Planner output
        - {"event": "thinking", "data": {"content": "..."}} - Planning reasoning
        - {"event": "tool_call_start", "data": {"name": "...", "arguments": {...}}}
        - {"event": "tool_call_end", "data": {"name": "...", "result": {...}}}
        - {"event": "message", "data": {"content": "..."}} - Character-by-character answer
        - {"event": "thinking_done", "data": {}} - Thinking complete
        - {"event": "ui_payload", "data": {...}} - Visualization data
        - {"event": "done", "data": {"session_id": "...", "tokens": {...}}}
        - {"event": "error", "data": {"message": "..."}} - Error occurred
    """
    # Track token usage across all LLM calls
    total_input_tokens = 0
    total_output_tokens = 0
    
    try:
        # Use LangGraph's astream_events for fine-grained streaming
        # This is the standard LangGraph pattern for streaming + token tracking
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
            include_names=["planner", "tool", "formatter"],
        ):
            kind = event.get("event")
            
            if kind == "on_chain_start" and event.get("name") == "planner":
                # Planner started
                continue
            
            elif kind == "on_chain_end" and event.get("name") == "planner":
                # Planner completed - emit plan and thinking
                output = event.get("data", {}).get("output", {})
                plan = output.get("plan") if isinstance(output, dict) else output
                
                if plan:
                    plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan
                    yield {
                        "event": "plan",
                        "data": plan_dict
                    }
                
                # Emit thinking if planning_reasoning is available
                if isinstance(output, dict) and output.get("planning_reasoning"):
                    yield {
                        "event": "thinking",
                        "data": {"content": output["planning_reasoning"]}
                    }
            
            elif kind == "on_chain_start" and event.get("name") == "tool":
                # Tool execution started
                plan = event.get("data", {}).get("input", {}).get("plan")
                if plan:
                    plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan
                    yield {
                        "event": "tool_call_start",
                        "data": {
                            "name": plan_dict.get("selected_tool") if isinstance(plan_dict, dict) else getattr(plan, "selected_tool", ""),
                            "arguments": plan_dict.get("arguments") if isinstance(plan_dict, dict) else getattr(plan, "arguments", {})
                        }
                    }
            
            elif kind == "on_chain_end" and event.get("name") == "tool":
                # Tool execution completed
                output = event.get("data", {}).get("output", {})
                result = output.get("tool_result") if isinstance(output, dict) else None
                plan = event.get("data", {}).get("input", {}).get("plan")
                
                if plan and result:
                    plan_dict = plan.model_dump() if hasattr(plan, "model_dump") else plan
                    yield {
                        "event": "tool_call_end",
                        "data": {
                            "name": plan_dict.get("selected_tool") if isinstance(plan_dict, dict) else getattr(plan, "selected_tool", ""),
                            "arguments": plan_dict.get("arguments") if isinstance(plan_dict, dict) else getattr(plan, "arguments", {}),
                            "result": result
                        }
                    }
            
            # Track token usage from LLM calls (LangGraph standard pattern)
            elif kind == "on_llm_end":
                # Extract token usage from LLM response
                usage = event.get("data", {}).get("output", {}).get("response_metadata", {}).get("token_usage")
                if usage:
                    total_input_tokens += usage.get("prompt_tokens", 0)
                    total_output_tokens += usage.get("completion_tokens", 0)
            
            elif kind == "on_llm_stream":
                # Stream LLM output (from formatter node)
                # Note: We capture all LLM stream events - in our graph, only formatter uses LLM streaming
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    # Handle different chunk types
                    if hasattr(chunk, "content") and chunk.content:
                        yield {
                            "event": "message",
                            "data": {"content": chunk.content}
                        }
                    elif isinstance(chunk, dict) and "content" in chunk:
                        yield {
                            "event": "message",
                            "data": {"content": chunk["content"]}
                        }
                    elif isinstance(chunk, str):
                        yield {
                            "event": "message",
                            "data": {"content": chunk}
                        }
            
            elif kind == "on_chain_end" and event.get("name") == "formatter":
                # Formatter completed - emit final results
                output = event.get("data", {}).get("output", {})
                
                if isinstance(output, dict):
                    # Emit thinking if available (combined from planning + formatting)
                    if output.get("thinking"):
                        # Thinking was already streamed from planner, just mark as done
                        yield {
                            "event": "thinking_done",
                            "data": {}
                        }
                    
                    # Emit error if present
                    if output.get("error"):
                        yield {
                            "event": "error",
                            "data": {"message": output["error"]}
                        }
                    
                    # Emit UI payload
                    if output.get("ui_payload"):
                        yield {
                            "event": "ui_payload",
                            "data": output.get("ui_payload")
                        }
                    
                    # Emit done event
                    yield {
                        "event": "done",
                        "data": {
                            "session_id": session_id,
                            "tokens": {
                                "input": total_input_tokens,
                                "output": total_output_tokens,
                                "total": total_input_tokens + total_output_tokens
                            }
                        }
                    }
        
    except Exception as e:
        logger.exception("Error in stream_aviation_agent")
        yield {
            "event": "error",
            "data": {"message": str(e)}
        }

