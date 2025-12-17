from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


async def stream_aviation_agent(
    messages: List[BaseMessage],
    graph: Any,  # Compiled graph from LangGraph (type: CompiledGraph from langgraph.checkpoint)
    session_id: Optional[str] = None,
    persona_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream agent execution with SSE-compatible events and token tracking.

    Uses LangGraph's astream_events() which is the standard pattern for:
    - Streaming node execution
    - Tracking token usage from LLM calls
    - Capturing tool execution

    Args:
        messages: List of messages to process
        graph: Compiled LangGraph graph
        session_id: Optional session ID for tracing
        persona_id: Optional persona ID for the agent
        thread_id: Optional thread ID for conversation memory. When provided with
            checkpointing enabled, enables multi-turn conversation resume.

    Yields SSE events:
        - {"event": "plan", "data": {...}} - Planner output
        - {"event": "thinking", "data": {"content": "..."}} - Planning reasoning
        - {"event": "tool_call_start", "data": {"name": "...", "arguments": {...}}}
        - {"event": "tool_call_end", "data": {"name": "...", "result": {...}}}
        - {"event": "message", "data": {"content": "..."}} - Character-by-character answer
        - {"event": "thinking_done", "data": {}} - Thinking complete
        - {"event": "ui_payload", "data": {...}} - Visualization data
        - {"event": "final_answer", "data": {"state": {...}}} - Final complete state for logging
        - {"event": "done", "data": {"session_id": "...", "thread_id": "...", "tokens": {...}}}
        - {"event": "error", "data": {"message": "..."}} - Error occurred
    """
    # Track token usage across all LLM calls
    total_input_tokens = 0
    total_output_tokens = 0
    final_state = None
    
    # Track if we've seen streaming from rules_agent's LLM
    # This helps us decide whether to emit the full answer or just references
    # We track this by checking if streaming happens between rules_rag and rules_agent completion
    rules_agent_streamed = False
    rules_rag_completed = False

    # Track the routing path for metadata (updated when router completes)
    routing_path: Optional[str] = None

    # Generate a unique run ID if session_id not provided
    run_id = session_id or str(uuid.uuid4())

    try:
        # Use LangGraph's astream_events for fine-grained streaming
        # This is the standard LangGraph pattern for streaming + token tracking
        # Note: We don't filter by include_names for LLM events - they come from inside chains
        # Don't filter by names - we want to capture all events including LLM streaming
        # The LLM events might not have the node name in their name field
        initial_state = {"messages": messages}
        if persona_id:
            initial_state["persona_id"] = persona_id

        # Generate thread_id if not provided (checkpointing requires it)
        # This enables conversation memory even for single-turn requests
        effective_thread_id = thread_id or f"thread_{uuid.uuid4().hex[:12]}"

        # Config for LangSmith observability and checkpointing
        # See: https://docs.langchain.com/langsmith
        config = {
            "run_name": f"aviation-agent-{run_id[:8]}",
            "tags": ["aviation-agent", "streaming"],
            "metadata": {
                "session_id": session_id,
                "persona_id": persona_id,
                "thread_id": effective_thread_id,
                "agent_version": "1.0",
            },
            # thread_id is required when checkpointing is enabled
            "configurable": {"thread_id": effective_thread_id},
        }

        async for event in graph.astream_events(
            initial_state,
            version="v2",
            config=config,
        ):
            kind = event.get("event")
            name = event.get("name", "")
            
            if kind == "on_chain_start" and event.get("name") == "planner":
                # Planner started
                continue

            elif kind == "on_chain_end" and event.get("name") == "router":
                # Router completed - capture the routing path for metadata
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    decision = output.get("router_decision")
                    if decision:
                        routing_path = getattr(decision, "path", None) or decision.get("path")
                        if routing_path:
                            logger.info(f"Routing path determined: {routing_path}")
            
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
            
            elif kind == "on_chain_end" and event.get("name") == "rules_rag":
                # Rules RAG completed - mark this so we can detect rules_agent streaming
                rules_rag_completed = True
            
            # Capture LLM streaming - LangGraph uses on_chat_model_stream for ChatOpenAI
            # This is emitted when the LLM streams chunks inside a chain.invoke() call
            # We want to capture this from the formatter's LLM, not the planner's
            elif kind == "on_chat_model_stream":
                # If we've seen rules_rag complete but not rules_agent, this streaming is likely from rules_agent
                if rules_rag_completed and not rules_agent_streamed:
                    rules_agent_streamed = True
                    logger.debug("Detected streaming from rules_agent LLM")
                
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

            elif kind == "on_chain_end" and event.get("name") == "rules_agent":
                # Rules agent completed (rules-only path) - emit final results
                output = event.get("data", {}).get("output")

                # Handle case where output might not be a dict
                if output is None:
                    output = {}
                elif not isinstance(output, dict):
                    logger.warning(f"Rules agent output is not a dict: {type(output)}")
                    output = {}

                # Handle answer emission based on whether LLM streamed or not
                if output.get("rules_answer"):
                    answer_with_refs = output["rules_answer"]
                    refs_marker = "\n\n---\n\n### References\n\n"
                    
                    if rules_agent_streamed:
                        # LLM answer was already streamed, only emit references if they exist
                        if refs_marker in answer_with_refs:
                            refs_section = answer_with_refs.split(refs_marker, 1)[1]
                            logger.info(f"LLM streamed, emitting references section only ({len(refs_section)} chars)")
                            yield {
                                "event": "message",
                                "data": {"content": refs_section}
                            }
                        else:
                            logger.debug("LLM streamed, no references section to emit")
                    else:
                        # LLM didn't stream, emit the full answer (including references if present)
                        logger.info(f"LLM did not stream, emitting full answer ({len(answer_with_refs)} chars)")
                        yield {
                            "event": "message",
                            "data": {"content": answer_with_refs}
                        }

                # Emit thinking if available
                if output.get("thinking"):
                    yield {
                        "event": "thinking",
                        "data": {"content": output["thinking"]}
                    }
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

                # Emit UI payload (suggested queries)
                if output.get("ui_payload"):
                    yield {
                        "event": "ui_payload",
                        "data": output.get("ui_payload")
                    }

                # Capture complete state from input
                input_data = event.get("data", {}).get("input")
                if input_data:
                    # Merge output into state to get final complete state
                    final_state = dict(input_data) if isinstance(input_data, dict) else {}
                    final_state.update(output)

                    # Filter out non-serializable objects for JSON serialization
                    serializable_state = {
                        k: v for k, v in final_state.items()
                        if k != "messages" and not hasattr(v, "model_dump")
                    }

                    # Emit final_answer event with serializable state for logging
                    yield {
                        "event": "final_answer",
                        "data": {"state": serializable_state}
                    }

                # Emit done event with metadata for observability
                yield {
                    "event": "done",
                    "data": {
                        "session_id": session_id,
                        "thread_id": effective_thread_id,
                        "tokens": {
                            "input": total_input_tokens,
                            "output": total_output_tokens,
                            "total": total_input_tokens + total_output_tokens
                        },
                        "metadata": {
                            "persona_id": persona_id,
                            "path": routing_path or "rules",  # rules path if router chose it
                        }
                    }
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

                # Emit done event with metadata for observability
                yield {
                    "event": "done",
                    "data": {
                        "session_id": session_id,
                        "thread_id": effective_thread_id,
                        "tokens": {
                            "input": total_input_tokens,
                            "output": total_output_tokens,
                            "total": total_input_tokens + total_output_tokens
                        },
                        "metadata": {
                            "persona_id": persona_id,
                            "path": routing_path or "database",  # database/both path if router chose it
                        }
                    }
                }

    except Exception as e:
        logger.exception("Error in stream_aviation_agent")
        yield {
            "event": "error",
            "data": {"message": str(e)}
        }

