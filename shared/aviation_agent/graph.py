from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from langgraph.graph import END, StateGraph

from .config import get_settings, get_behavior_config
from shared.tool_context import get_tool_context_settings
from .execution import ToolRunner
from .formatting import build_formatter_chain
from .planning import AviationPlan
from .state import AgentState
from .next_query_predictor import NextQueryPredictor, extract_context_from_plan

logger = logging.getLogger(__name__)


def _build_agent_graph(
    planner,
    tool_runner: ToolRunner,
    formatter_llm,
    behavior_config=None,
    checkpointer=None,
):
    """
    Internal: Assemble the LangGraph workflow.

    This is a private function called by build_agent(). Feature flags
    (next_query_prediction) are controlled via behavior_config, not parameters.

    Args:
        planner: Planner runnable for tool selection
        tool_runner: Tool execution runner
        formatter_llm: LLM for formatting responses
        behavior_config: AgentBehaviorConfig instance (loaded from JSON)
        checkpointer: Optional LangGraph checkpointer for conversation memory.
            When provided, enables multi-turn conversations via thread_id.

    Flow:
        Planner → [Predict Next Queries] → Tool → Formatter → END

    The planner handles all tool selection including:
        - answer_rules_question: For specific questions about ONE country (uses RAG)
        - browse_rules: For listing/browsing rules by category/tags
        - compare_rules_between_countries: For comparing 2+ countries
        - Airport tools: search_airports, find_airports_near_location, etc.
    """

    settings = get_settings()
    if behavior_config is None:
        behavior_config = get_behavior_config(settings.agent_config_name)

    # Initialize next query predictor (if enabled)
    predictor = None
    if behavior_config.next_query_prediction.enabled:
        tool_context_settings = get_tool_context_settings()
        predictor = NextQueryPredictor(
            rules_json_path=tool_context_settings.rules_json,
            config=behavior_config.next_query_prediction
        )
        logger.info("✓ Next query predictor enabled")

    graph = StateGraph(AgentState)

    def planner_node(state: AgentState) -> Dict[str, Any]:
        try:
            plan: AviationPlan = planner.invoke({"messages": state.get("messages") or []})
            # Generate simple reasoning from plan
            reasoning_parts = [f"Selected tool: {plan.selected_tool}"]
            if plan.arguments.get("filters"):
                filter_str = ", ".join(f"{k}={v}" for k, v in plan.arguments["filters"].items())
                reasoning_parts.append(f"with filters: {filter_str}")
            if plan.arguments:
                other_args = {k: v for k, v in plan.arguments.items() if k != "filters"}
                if other_args:
                    arg_str = ", ".join(f"{k}={v}" for k, v in other_args.items())
                    reasoning_parts.append(f"with arguments: {arg_str}")

            reasoning = ". ".join(reasoning_parts) + "."
            return {"plan": plan, "planning_reasoning": reasoning}
        except Exception as e:
            return {"error": str(e)}

    def predict_next_queries_node(state: AgentState) -> Dict[str, Any]:
        """
        Generate next query suggestions based on plan ONLY.

        Runs AFTER planner, uses only:
        - User query text
        - Tool selected
        - Tool arguments (including filters)

        Does NOT use tool results.
        """
        if predictor is None:
            return {}

        try:
            plan = state.get("plan")
            if not plan:
                return {}

            # Extract context from query and plan only (NO RESULTS)
            messages = state.get("messages", [])
            user_query = messages[-1].content if messages and hasattr(messages[-1], 'content') else ""

            context = extract_context_from_plan(user_query, plan)

            # Generate suggestions (rule-based, fast)
            suggestions = predictor.predict_next_queries(
                context, max_suggestions=behavior_config.next_query_prediction.max_suggestions
            )

            # Format for UI
            suggested_queries = [
                {
                    "text": s.query_text,
                    "tool": s.tool_name,
                    "category": s.category,
                    "priority": s.priority
                }
                for s in suggestions
            ]

            logger.info(f"Generated {len(suggested_queries)} query suggestions")

            # Store in state for formatter to include in ui_payload
            return {"suggested_queries": suggested_queries}

        except Exception as e:
            logger.error(f"Next query prediction failed: {e}", exc_info=True)
            return {}


    def tool_node(state: AgentState) -> Dict[str, Any]:
        if state.get("error"):
            return {}  # Skip if planner failed
        plan = state.get("plan")
        if not plan:
            return {"error": "No plan available"}
        
        try:
            # Execute the tool
            tool_calls = plan.get_tool_calls()
            
            if not tool_calls:
                return {"error": "No tools selected in plan"}
            
            # Single tool execution
            result = tool_runner.run(plan, state)
            
            # POST-PROCESSING: Enrich airport results with notification data
            # Check if this is a location/route tool and query mentions notifications
            messages = state.get("messages", [])
            user_query = messages[-1].content.lower() if messages and hasattr(messages[-1], 'content') else ""
            
            notification_keywords = ["notification", "notify", "customs", "notice", "prior", "how early", "when should"]
            wants_notifications = any(kw in user_query for kw in notification_keywords)
            
            location_tools = {"find_airports_near_location", "find_airports_near_route", "search_airports"}
            first_tool = tool_calls[0].tool_name if tool_calls else plan.selected_tool
            
            if wants_notifications and first_tool in location_tools and result.get("airports"):
                logger.info(f"📋 POST-PROCESSING: Enriching {len(result['airports'])} airports with notification data")
                
                # Import notification service
                from shared.ga_notification_agent.service import NotificationService
                
                notification_service = NotificationService()
                
                # Extract day_of_week from query if mentioned
                day_of_week = None
                for day in ["saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday"]:
                    if day in user_query:
                        day_of_week = day.capitalize()
                        break
                
                # Enrich each airport with notification data
                enriched_airports = []
                notification_summaries = []
                
                for airport in result["airports"][:15]:  # Limit to first 15 airports
                    icao = airport.get("ident") or airport.get("icao")
                    if icao:
                        notif = notification_service.get_notification_for_airport(icao, day_of_week)
                        airport["notification"] = notif
                        if notif.get("found"):
                            summary = notif.get("day_specific_rule") or notif.get("summary") or f"{notif.get('hours_notice', '?')}h notice"
                            notification_summaries.append(f"**{icao}**: {summary[:100]}")
                    enriched_airports.append(airport)
                
                # Update result with enriched data
                result["airports"] = enriched_airports
                result["notifications_enriched"] = True
                
                # Append notification summary to pretty output
                if notification_summaries:
                    result["pretty"] = result.get("pretty", "") + "\n\n**Notification Requirements" + (f" ({day_of_week}):" if day_of_week else ":") + "**\n" + "\n".join(notification_summaries)
                else:
                    result["pretty"] = result.get("pretty", "") + "\n\n**Notification Requirements:** No parsed notification data available for these airports."
                
                logger.info(f"📋 Enriched {len(notification_summaries)} airports with notification data")
            
            return {"tool_result": result}
            
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {"error": str(e)}

    # Build formatter chains - this allows LangGraph to capture streaming
    # Load prompts from config for different strategies
    formatter_prompt = behavior_config.load_prompt("formatter")
    formatter_chain = build_formatter_chain(formatter_llm, system_prompt=formatter_prompt)

    # Build comparison formatter chain with specialized prompt
    comparison_prompt = behavior_config.load_prompt("comparison_synthesis")
    comparison_formatter_chain = None
    if comparison_prompt:
        from .formatting import build_comparison_formatter_chain
        comparison_formatter_chain = build_comparison_formatter_chain(
            formatter_llm, system_prompt=comparison_prompt
        )
    
    def formatter_node(state: AgentState) -> Dict[str, Any]:
        # Handle errors gracefully
        error = state.get("error")
        if error:
            return {
                "final_answer": f"I encountered an error: {error}. Please try again.",
                "error": error,
                "thinking": state.get("planning_reasoning", ""),
            }

        try:
            plan = state.get("plan")
            tool_result = state.get("tool_result") or {}

            # Check if this is a comparison tool - use specialized formatter
            if tool_result.get("_tool_type") == "comparison" and comparison_formatter_chain:
                logger.info(f"📋 Using comparison formatter for synthesis")

                rules_context = tool_result.get("rules_context", "").strip()

                # Short-circuit: if no rules data, don't call LLM (prevents hallucination)
                if not rules_context:
                    countries_str = ", ".join(tool_result.get("countries", []))
                    answer = (
                        "I don't have specific comparison data for "
                        f"{countries_str} on this topic in my rules database."
                    )
                    from .formatting import build_ui_payload
                    suggested_queries = state.get("suggested_queries")
                    ui_payload = build_ui_payload(plan, tool_result, suggested_queries) if plan else None
                    return {
                        "final_answer": answer,
                        "thinking": state.get("planning_reasoning", ""),
                        "ui_payload": ui_payload,
                    }

                # Build topic context for prompt
                topic_parts = []
                if tool_result.get("tag"):
                    topic_parts.append(f"Topic: {tool_result['tag']}")
                if tool_result.get("category"):
                    topic_parts.append(f"Category: {tool_result['category']}")
                topic_context = "\n".join(topic_parts) if topic_parts else ""

                # Invoke comparison formatter with structured context
                chain_result = comparison_formatter_chain.invoke({
                    "countries": ", ".join(tool_result.get("countries", [])),
                    "topic_context": topic_context,
                    "rules_context": rules_context,
                })

                answer = chain_result if isinstance(chain_result, str) else str(
                    chain_result.content if hasattr(chain_result, 'content') else chain_result
                )

                from .formatting import build_ui_payload
                suggested_queries = state.get("suggested_queries")
                ui_payload = build_ui_payload(plan, tool_result, suggested_queries) if plan else None

                return {
                    "final_answer": answer.strip(),
                    "thinking": state.get("planning_reasoning", ""),
                    "ui_payload": ui_payload,
                }

            chain_result = formatter_chain.invoke(
                {
                    "messages": state.get("messages") or [],
                    "answer_style": plan.answer_style if plan else "narrative_markdown",
                    "tool_result_json": json.dumps(tool_result, indent=2, ensure_ascii=False),
                    "pretty_text": tool_result.get("pretty", ""),
                }
            )
            
            # Process the answer and build UI payload
            from .formatting import build_ui_payload
            
            # Handle different return types from the chain
            if isinstance(chain_result, str):
                answer = chain_result.strip()
            elif hasattr(chain_result, "content"):
                answer = str(chain_result.content).strip()
            else:
                answer = str(chain_result).strip()
            
            # Build UI payload with suggested queries
            # Visualization comes entirely from tool result - no modification based on answer text
            suggested_queries = state.get("suggested_queries")
            try:
                ui_payload = build_ui_payload(plan, tool_result, suggested_queries) if plan else None
            except Exception as e:
                logger.error(f"Failed to build UI payload: {e}", exc_info=True)
                ui_payload = None
            
            # Generate simple formatting reasoning
            formatting_reasoning = f"Formatted answer using {plan.answer_style if plan else 'default'} style."
            
            # Combine planning and formatting reasoning
            thinking_parts = []
            planning_reasoning = state.get("planning_reasoning")
            if planning_reasoning:
                thinking_parts.append(planning_reasoning)
            thinking_parts.append(formatting_reasoning)
            
            return {
                "final_answer": answer,
                "thinking": "\n\n".join(thinking_parts) if thinking_parts else None,
                "ui_payload": ui_payload,
            }
        except Exception as e:
            logger.exception("Formatter node error")
            return {
                "final_answer": f"Error formatting response: {str(e)}",
                "error": str(e),
                "thinking": state.get("planning_reasoning", ""),
            }

    # Add nodes
    graph.add_node("planner", planner_node)
    if predictor:
        graph.add_node("predict_next_queries", predict_next_queries_node)
    graph.add_node("tool", tool_node)
    graph.add_node("formatter", formatter_node)

    # Build graph: Planner → [Predict Next Queries] → Tool → Formatter → END
    graph.set_entry_point("planner")
    if predictor:
        graph.add_edge("planner", "predict_next_queries")
        graph.add_edge("predict_next_queries", "tool")
    else:
        graph.add_edge("planner", "tool")
    graph.add_edge("tool", "formatter")
    graph.add_edge("formatter", END)

    # Compile with optional checkpointer for conversation memory
    return graph.compile(checkpointer=checkpointer)

