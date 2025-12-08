from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .config import get_settings, get_behavior_config
from .execution import ToolRunner
from .formatting import build_formatter_chain
from .planning import AviationPlan
from .routing import QueryRouter, RouterDecision
from .rules_rag import RulesRAG
from .rules_agent import RulesAgent
from .state import AgentState
from .next_query_predictor import NextQueryPredictor, extract_context_from_plan

logger = logging.getLogger(__name__)


def build_agent_graph(
    planner,
    tool_runner: ToolRunner,
    formatter_llm,
    router_llm=None,
    rules_llm=None,
    enable_routing: bool = True,
    enable_next_query_prediction: bool = True,
    behavior_config=None,
):
    """
    Assemble the LangGraph workflow with routing support.

    Args:
        planner: Planner runnable for database path
        tool_runner: Tool execution runner
        formatter_llm: LLM for formatting responses
        router_llm: Optional LLM for query routing (uses default if None)
        rules_llm: Optional LLM for rules synthesis (uses formatter_llm if None)
        enable_routing: Whether to enable routing (default True)
        enable_next_query_prediction: Whether to enable next query prediction (default True)

    Flow:
        1. Router decides: rules, database, or both
        2a. Rules path: RAG retrieval → Rules agent → END
        2b. Database path: Planner → Predict Next Queries → Tool → Formatter → END
        2c. Both path: Database → Rules → Formatter → END
    """
    
    settings = get_settings()
    if behavior_config is None:
        behavior_config = get_behavior_config(settings.agent_config_name)
    
    # Initialize routing components (if enabled)
    router = None
    rag_system = None
    rules_agent = None
    
    if enable_routing and behavior_config.routing.enabled:
        router = QueryRouter(llm=router_llm)

        # Initialize RAG system
        # NOTE: ChromaDB requires local filesystem (not CIFS/NFS)
        # Vector DB is stored at /root/Projects/flyfun/rules_vector_db
        try:
            # Get RulesManager from ToolContext for multi-country lookups
            tool_context = settings.build_tool_context(load_rules=True)
            rules_manager = tool_context.rules_manager
            
            rag_system = RulesRAG(
                vector_db_path=settings.vector_db_path if not settings.vector_db_url else None,
                vector_db_url=settings.vector_db_url,
                embedding_model=behavior_config.rag.embedding_model,
                enable_reformulation=behavior_config.query_reformulation.enabled,
                enable_reranking=behavior_config.reranking.enabled,
                reranking_provider=behavior_config.reranking.provider,
                reranking_config=behavior_config.reranking,
                retrieval_config=behavior_config.rag.retrieval,
                llm=router_llm,
                rules_manager=rules_manager
            )
            if settings.vector_db_url:
                logger.info(f"✓ RAG system initialized with service: {settings.vector_db_url}")
            else:
                logger.info(f"✓ RAG system initialized: {settings.vector_db_path}")
        except Exception as e:
            logger.warning(f"Could not initialize RAG system: {e}")
            logger.warning("Rules path will be disabled")
            rag_system = None

        # Initialize rules agent with prompt from config
        rules_prompt = behavior_config.load_prompt("rules_agent")
        rules_agent = RulesAgent(llm=rules_llm or formatter_llm, system_prompt=rules_prompt)

    # Initialize next query predictor (if enabled)
    predictor = None
    if enable_next_query_prediction and behavior_config.next_query_prediction.enabled:
        predictor = NextQueryPredictor(rules_json_path=settings.rules_json)
        logger.info("✓ Next query predictor enabled")

    graph = StateGraph(AgentState)

    def router_node(state: AgentState) -> Dict[str, Any]:
        """Route query to appropriate path (rules, database, or both)."""
        if not enable_routing or router is None:
            # Skip routing, go directly to planner (backward compatibility)
            return {}
        
        try:
            messages = state.get("messages") or []
            if not messages:
                return {"error": "No messages to route"}
            
            # Get last user message
            query = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])
            
            # Route query
            decision = router.route(query, conversation=messages)
            
            logger.info(f"Router: {decision.path} path (confidence: {decision.confidence:.2f}, countries: {decision.countries})")
            
            return {"router_decision": decision}
        except Exception as e:
            logger.error(f"Router error: {e}", exc_info=True)
            # Fallback to database path on error
            return {"router_decision": RouterDecision(
                path="database",
                confidence=0.5,
                reasoning=f"Router failed, defaulting to database: {e}"
            )}
    
    def rules_rag_node(state: AgentState) -> Dict[str, Any]:
        """Retrieve relevant rules using RAG."""
        if rag_system is None:
            return {"error": "RAG system not available"}
        
        try:
            decision = state.get("router_decision")
            if not decision:
                return {"error": "No routing decision"}
            
            messages = state.get("messages") or []
            query = messages[-1].content if messages and hasattr(messages[-1], 'content') else ""
            
            # Retrieve rules
            retrieved_rules = rag_system.retrieve_rules(
                query=query,
                countries=decision.countries if decision.countries else None,
                top_k=behavior_config.rag.retrieval.top_k,
                similarity_threshold=behavior_config.rag.retrieval.similarity_threshold
            )
            
            logger.info(f"RAG: Retrieved {len(retrieved_rules)} rules for countries: {decision.countries}")
            
            return {"retrieved_rules": retrieved_rules}
        except Exception as e:
            logger.error(f"RAG retrieval error: {e}", exc_info=True)
            return {"error": str(e)}
    
    def rules_agent_node(state: AgentState) -> Dict[str, Any]:
        """Synthesize answer from retrieved rules."""
        if rules_agent is None:
            return {"error": "Rules agent not available"}

        try:
            decision = state.get("router_decision")
            retrieved_rules = state.get("retrieved_rules") or []
            messages = state.get("messages") or []

            query = messages[-1].content if messages and hasattr(messages[-1], 'content') else ""
            countries = decision.countries if decision else []

            # Synthesize answer
            result = rules_agent.synthesize(
                query=query,
                retrieved_rules=retrieved_rules,
                countries=countries,
                conversation=messages
            )

            logger.info(f"Rules Agent: Generated answer using {len(retrieved_rules)} rules")

            # Build response with suggested queries if available
            response = {
                "rules_answer": result["answer"],
                "rules_sources": result["sources"],
                "final_answer": result["answer"],  # For rules-only path
                "thinking": f"Retrieved {len(retrieved_rules)} relevant regulations. Countries: {', '.join(countries) if countries else 'N/A'}"
            }

            # Build ui_payload with show_rules for frontend to display country rules
            # result["sources"] contains categories grouped by country: {country: [categories]}
            ui_payload = {
                "show_rules": {
                    "countries": countries,
                    "categories_by_country": result.get("sources", {}),  # {country: [categories...]}
                    "rules_used_count": len(result.get("rules_used", []))
                }
            }

            # Include suggested queries if they were generated
            suggested_queries = state.get("suggested_queries")
            if suggested_queries:
                ui_payload["suggested_queries"] = suggested_queries
                logger.info(f"Including {len(suggested_queries)} suggested queries in rules response")

            response["ui_payload"] = ui_payload
            logger.info(f"Rules response includes show_rules for countries: {countries}")

            return response
        except Exception as e:
            logger.error(f"Rules agent error: {e}", exc_info=True)
            return {"error": str(e)}

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
        if not enable_next_query_prediction or predictor is None:
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

    def predict_next_queries_for_rules_node(state: AgentState) -> Dict[str, Any]:
        """
        Generate next query suggestions for rules-only path.

        Simpler than database path - just suggests other rule questions
        based on the user's query without needing a plan.
        """
        if not enable_next_query_prediction or predictor is None:
            return {}

        try:
            # Extract user query
            messages = state.get("messages", [])
            user_query = messages[-1].content if messages and hasattr(messages[-1], 'content') else ""

            # Extract countries from router decision
            decision = state.get("router_decision")
            countries = decision.countries if decision else []

            # Create a simple context for rules queries
            # We use "list_rules_for_country" as the tool since that's what rules queries map to
            from .next_query_predictor import QueryContext
            context = QueryContext(
                user_query=user_query,
                tool_used="list_rules_for_country",
                tool_arguments={},
                filters_applied={},
                locations_mentioned=[],
                icao_codes_mentioned=[],
                countries_mentioned=countries  # Include countries from router decision
            )

            # Generate suggestions
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

            logger.info(f"Generated {len(suggested_queries)} query suggestions for rules path (countries: {countries})")

            return {"suggested_queries": suggested_queries}

        except Exception as e:
            logger.error(f"Next query prediction for rules failed: {e}", exc_info=True)
            return {}

    def tool_node(state: AgentState) -> Dict[str, Any]:
        if state.get("error"):
            return {}  # Skip if planner failed
        plan = state.get("plan")
        if not plan:
            return {"error": "No plan available"}
        try:
            result = tool_runner.run(plan)
            return {"tool_result": result}
        except Exception as e:
            return {"error": str(e)}

    # Build formatter chain directly - this allows LangGraph to capture streaming
    # Load prompt from config
    formatter_prompt = behavior_config.load_prompt("formatter")
    formatter_chain = build_formatter_chain(formatter_llm, system_prompt=formatter_prompt)
    
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
            decision = state.get("router_decision")
            
            # Check if this is a "both" path (has both rules and database results)
            has_rules = state.get("rules_answer") is not None
            has_database = state.get("tool_result") is not None
            
            if decision and decision.path == "both" and has_rules and has_database:
                # Combine rules and database answers
                rules_answer = state.get("rules_answer", "")
                tool_result = state.get("tool_result") or {}
                
                # Format database results
                plan = state.get("plan")
                db_result_json = json.dumps(tool_result, indent=2, ensure_ascii=False)
                
                chain_result = formatter_chain.invoke({
                    "messages": state.get("messages") or [],
                    "answer_style": plan.answer_style if plan else "narrative_markdown",
                    "tool_result_json": db_result_json,
                    "pretty_text": tool_result.get("pretty", ""),
                })
                
                db_answer = chain_result if isinstance(chain_result, str) else str(chain_result.content if hasattr(chain_result, 'content') else chain_result)
                
                # Combine answers
                combined_answer = f"{db_answer}\n\n---\n\n## Relevant Regulations\n\n{rules_answer}"
                
                from .formatting import build_ui_payload
                suggested_queries = state.get("suggested_queries")
                ui_payload = build_ui_payload(plan, tool_result, suggested_queries) if plan else None

                return {
                    "final_answer": combined_answer,
                    "thinking": f"Combined database results with regulations from {', '.join(decision.countries)}",
                    "ui_payload": ui_payload
                }
            
            # Rules-only path (answer already in state from rules_agent_node)
            if has_rules and not has_database:
                # Rules answer is already final_answer from rules_agent_node
                return {}  # No changes needed
            
            # Database-only path (existing formatter logic)
            plan = state.get("plan")
            tool_result = state.get("tool_result") or {}
            
            chain_result = formatter_chain.invoke(
                {
                    "messages": state.get("messages") or [],
                    "answer_style": plan.answer_style if plan else "narrative_markdown",
                    "tool_result_json": json.dumps(tool_result, indent=2, ensure_ascii=False),
                    "pretty_text": tool_result.get("pretty", ""),
                }
            )
            
            # Process the answer and build UI payload
            from .formatting import build_ui_payload, _extract_icao_codes, _enhance_visualization
            
            # Handle different return types from the chain
            if isinstance(chain_result, str):
                answer = chain_result.strip()
            elif hasattr(chain_result, "content"):
                answer = str(chain_result.content).strip()
            else:
                answer = str(chain_result).strip()
            
            # Build UI payload with suggested queries
            suggested_queries = state.get("suggested_queries")
            try:
                ui_payload = build_ui_payload(plan, tool_result, suggested_queries) if plan else None
            except Exception as e:
                logger.error(f"Failed to build UI payload: {e}", exc_info=True)
                ui_payload = None

            # Optional: Enhance visualization with ICAOs from answer
            mentioned_icaos = []
            logger.info(f"📍 FORMATTER: ui_payload kind={ui_payload.get('kind') if ui_payload else None}, answer length={len(answer) if answer else 0}, plan tool={plan.selected_tool if plan else None}")
            if ui_payload and ui_payload.get("kind") in ["route", "airport"]:
                mentioned_icaos = _extract_icao_codes(answer)
                logger.info(f"📍 FORMATTER: Extracted {len(mentioned_icaos)} ICAO codes from answer: {mentioned_icaos[:10]}...")
                if mentioned_icaos:
                    ui_payload = _enhance_visualization(ui_payload, mentioned_icaos, tool_result)
                    logger.info(f"📍 FORMATTER: Enhanced visualization applied")
            
            # Generate simple formatting reasoning
            formatting_reasoning = f"Formatted answer using {plan.answer_style if plan else 'default'} style."
            if mentioned_icaos:
                formatting_reasoning += f" Mentioned {len(mentioned_icaos)} airports."
            
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
    if enable_routing and router:
        graph.add_node("router", router_node)
        graph.add_node("rules_rag", rules_rag_node)
        # rules_agent node will be added with wrapper below
        if enable_next_query_prediction and predictor:
            graph.add_node("predict_next_queries_for_rules", predict_next_queries_for_rules_node)

    graph.add_node("planner", planner_node)
    if enable_next_query_prediction and predictor:
        graph.add_node("predict_next_queries", predict_next_queries_node)
    graph.add_node("tool", tool_node)
    graph.add_node("formatter", formatter_node)

    # Set entry point
    if enable_routing and router:
        graph.set_entry_point("router")
        
        # Conditional routing based on RouterDecision
        def route_decision(state: AgentState) -> str:
            """Route based on router decision."""
            decision = state.get("router_decision")
            if not decision:
                return "planner"  # Fallback to database path
            
            if decision.path == "rules":
                return "rules_rag"
            elif decision.path == "both":
                return "planner"  # Start with database, then add rules
            else:  # database
                return "planner"
        
        # Add conditional edge from router
        graph.add_conditional_edges(
            "router",
            route_decision,
            {
                "rules_rag": "rules_rag",
                "planner": "planner"
            }
        )
        
        # Rules path: RAG → Predict Next Queries (optional) → Rules Agent → END
        if enable_next_query_prediction and predictor:
            graph.add_edge("rules_rag", "predict_next_queries_for_rules")
            graph.add_edge("predict_next_queries_for_rules", "rules_agent")
        else:
            graph.add_edge("rules_rag", "rules_agent")
        graph.add_edge("rules_agent", END)
        
        # Database path: Planner → Predict Next Queries → Tool → check if "both"
        if enable_next_query_prediction and predictor:
            graph.add_edge("planner", "predict_next_queries")
            graph.add_edge("predict_next_queries", "tool")
        else:
            graph.add_edge("planner", "tool")
        
        def after_tool_routing(state: AgentState) -> str:
            """After tool execution, check if we need rules too."""
            decision = state.get("router_decision")
            if decision and decision.path == "both":
                return "rules_rag"  # Add rules to database results
            else:
                return "formatter"  # Just format database results
        
        graph.add_conditional_edges(
            "tool",
            after_tool_routing,
            {
                "rules_rag": "rules_rag",
                "formatter": "formatter"
            }
        )
        
        # Both path: after rules, go to formatter to combine
        # (rules_agent already added edge to END, but we override for "both")
        # Actually, we need a different flow for "both" - let me think...
        # For "both": Tool → Rules RAG → Rules Agent (but skip the END edge)
        
        # Let's use a wrapper for rules_agent that checks the path
        def rules_agent_with_both_support(state: AgentState) -> Dict[str, Any]:
            """Rules agent that doesn't set final_answer for 'both' path."""
            result = rules_agent_node(state)
            decision = state.get("router_decision")
            
            if decision and decision.path == "both":
                # Don't set final_answer yet, let formatter combine
                result_copy = result.copy()
                result_copy.pop("final_answer", None)
                return result_copy
            return result
        
        # Replace the rules_agent node with the wrapper
        graph.add_node("rules_agent", rules_agent_with_both_support)
        
        # After rules_agent, check if "both" path
        def after_rules_routing(state: AgentState) -> str:
            """After rules agent, check if we need to combine with database."""
            decision = state.get("router_decision")
            if decision and decision.path == "both":
                return "formatter"  # Combine results
            else:
                return END  # Rules-only, already have final answer
        
        graph.add_conditional_edges(
            "rules_agent",
            after_rules_routing,
            {
                "formatter": "formatter",
                END: END
            }
        )
        
        # Formatter always goes to END
        graph.add_edge("formatter", END)
        
    else:
        # Original flow (backward compatibility)
        graph.set_entry_point("planner")
        if enable_next_query_prediction and predictor:
            graph.add_edge("planner", "predict_next_queries")
            graph.add_edge("predict_next_queries", "tool")
        else:
            graph.add_edge("planner", "tool")
        graph.add_edge("tool", "formatter")
        graph.add_edge("formatter", END)

    return graph.compile()

