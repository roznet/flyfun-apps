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
        - {"event": "final_answer", "data": {"state": {...}}} - Final complete state for logging
        - {"event": "done", "data": {"session_id": "...", "tokens": {...}}}
        - {"event": "error", "data": {"message": "..."}} - Error occurred
    """
    # Track token usage across all LLM calls
    total_input_tokens = 0
    total_output_tokens = 0
    final_state = None

    try:
        # Use LangGraph's astream_events for fine-grained streaming
        # This is the standard LangGraph pattern for streaming + token tracking
        # Note: We don't filter by include_names for LLM events - they come from inside chains
        # Don't filter by names - we want to capture all events including LLM streaming
        # The LLM events might not have the node name in their name field
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
        ):
            kind = event.get("event")
            name = event.get("name", "")
            
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
            elif kind == "on_llm_end" or kind == "on_chat_model_end":
                # Extract token usage from LLM response
                # Output might be an AIMessage object, not a dict
                output = event.get("data", {}).get("output")
                
                # Try different paths for token usage
                usage = None
                if hasattr(output, "response_metadata"):
                    # AIMessage object
                    usage = output.response_metadata.get("token_usage") if output.response_metadata else None
                elif isinstance(output, dict):
                    # Dict output
                    usage = (
                        output.get("response_metadata", {}).get("token_usage") or
                        output.get("token_usage")
                    )
                
                # Also check event data directly
                if not usage:
                    usage = event.get("data", {}).get("token_usage")
                
                if usage:
                    if isinstance(usage, dict):
                        total_input_tokens += usage.get("prompt_tokens", 0)
                        total_output_tokens += usage.get("completion_tokens", 0)
                    elif hasattr(usage, "prompt_tokens"):
                        # TokenUsage object
                        total_input_tokens += usage.prompt_tokens or 0
                        total_output_tokens += usage.completion_tokens or 0
            
            # Capture LLM streaming - LangGraph uses on_chat_model_stream for ChatOpenAI
            # This is emitted when the LLM streams chunks inside a chain.invoke() call
            # We want to capture this from the formatter's LLM, not the planner's
            elif kind == "on_chat_model_stream":
                # Only capture if it's from the formatter (not planner)
                # The name will be the LLM instance name, but we can check the parent chain
                # For now, capture all chat_model_stream events (planner doesn't stream)
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    # Handle AIMessageChunk - has .content attribute
                    content = None
                    if hasattr(chunk, "content"):
                        content = chunk.content
                    elif isinstance(chunk, dict):
                        content = chunk.get("content") or chunk.get("text") or chunk.get("delta", {}).get("content", "")
                    elif isinstance(chunk, str):
                        content = chunk
                    
                    if content:
                        yield {
                            "event": "message",
                            "data": {"content": content}
                        }
            
            # Also capture streaming from StrOutputParser (which streams strings)
            # This is important - StrOutputParser streams string chunks after LLM
            # Capture all chain_stream events (they'll be from formatter's StrOutputParser)
            elif kind == "on_chain_stream":
                # StrOutputParser outputs strings directly
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    if isinstance(chunk, str) and chunk.strip():
                        yield {
                            "event": "message",
                            "data": {"content": chunk}
                        }
                    elif hasattr(chunk, "content") and not isinstance(chunk, str):
                        yield {
                            "event": "message",
                            "data": {"content": chunk.content}
                        }
                    elif isinstance(chunk, dict) and "content" in chunk:
                        yield {
                            "event": "message",
                            "data": {"content": chunk["content"]}
                        }
            
            elif kind == "on_chain_end" and event.get("name") == "formatter":
                # Formatter completed - emit final results
                # Output should be a dict from the formatter node
                output = event.get("data", {}).get("output")
                
                # Handle case where output might not be a dict
                if output is None:
                    output = {}
                elif not isinstance(output, dict):
                    # If output is not a dict, try to extract from it
                    # This shouldn't happen, but handle gracefully
                    logger.warning(f"Formatter output is not a dict: {type(output)}")
                    output = {}
                
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

                # Capture complete state from input (which includes all state fields)
                # The formatter receives the entire state as input
                input_data = event.get("data", {}).get("input")
                if input_data:
                    # Merge output into state to get final complete state
                    final_state = dict(input_data) if isinstance(input_data, dict) else {}
                    final_state.update(output)

                    # Filter out non-serializable objects (like HumanMessage) for JSON serialization
                    # Only include JSON-serializable fields for logging
                    serializable_state = {
                        k: v for k, v in final_state.items()
                        if k != "messages" and not hasattr(v, "model_dump")
                    }

                    # Emit final_answer event with serializable state for logging
                    yield {
                        "event": "final_answer",
                        "data": {"state": serializable_state}
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

