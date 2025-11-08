#!/usr/bin/env python3
"""
Chatbot Service for Euro AIP Pilot Assistant
Integrates LLM with MCP tools for aviation assistance.
"""

import os
import json
import logging
import re
from typing import List, Dict, Any, Optional, Generator
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from mcp_client import MCPClient

logger = logging.getLogger(__name__)


class ChatbotService:
    """Main chatbot service that orchestrates LLM and tool calls."""

    def __init__(self):
        # Initialize primary LLM client (yunwu.ai)
        self.llm_api_base = os.getenv("DEFAULT_LLM_API_BASE", "https://yunwu.ai/v1")
        self.llm_model = os.getenv("DEFAULT_LLM_MODEL", "gpt-5-2025-08-07")
        self.llm_api_key = os.getenv("DEFAULT_LLM_API_KEY", "")
        self.llm_temperature = float(os.getenv("DEFAULT_LLM_TEMPERATURE", "0.0"))
        self.llm_max_tokens = int(os.getenv("DEFAULT_LLM_MAX_TOKENS", "-1"))

        self.client = OpenAI(
            api_key=self.llm_api_key,
            base_url=self.llm_api_base
        )

        # Initialize fallback LLM client (OpenAI official)
        self.fallback_llm_model = os.getenv("FALLBACK_LLM_MODEL", "gpt-5")
        self.fallback_llm_api_key = os.getenv("FALLBACK_LLM_API_KEY", "")
        self.fallback_llm_api_base = os.getenv("FALLBACK_LLM_API_BASE", "https://api.openai.com/v1")

        self.fallback_client = None
        if self.fallback_llm_api_key:
            self.fallback_client = OpenAI(
                api_key=self.fallback_llm_api_key,
                base_url=self.fallback_llm_api_base
            )
            logger.info(f"Fallback client initialized: {self.fallback_llm_model}")

        # Initialize MCP client for tool calls
        self.mcp_client = MCPClient()

        # Get available tools
        self.tools = self.mcp_client.get_available_tools()

        # System prompt for the pilot assistant
        self.system_prompt = self._create_system_prompt()

        # Setup conversation logging
        self.conversation_log_dir = Path(os.getenv("CONVERSATION_LOG_DIR", "conversation_logs"))
        self.conversation_log_dir.mkdir(exist_ok=True)
        logger.info(f"Conversation logs directory: {self.conversation_log_dir}")

        logger.info(f"ChatbotService initialized with model: {self.llm_model}")
        logger.info(f"Available tools: {len(self.tools)}")

    def _extract_thinking_and_answer(self, text: str) -> tuple[str, str]:
        """
        Extract thinking process and final answer from LLM response.
        Returns (thinking, answer) tuple.
        """
        if not text:
            return "", ""

        # Extract thinking content from <thinking>...</thinking> tags
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', text, flags=re.DOTALL | re.IGNORECASE)

        if thinking_match:
            thinking = thinking_match.group(1).strip()
            # Remove thinking tags from the answer
            answer = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        else:
            # No thinking tags found - treat entire response as answer
            thinking = ""
            answer = text.strip()

        # Clean up thinking section: remove JSON artifacts and tool call syntax
        if thinking:
            # Remove JSON objects like {"icao_code":"LFPB"}
            thinking = re.sub(r'\{[^}]*"[^"]*"[^}]*\}', '', thinking, flags=re.DOTALL)
            # Remove repeated phrases
            thinking = re.sub(r'(I(?:\'m going to|\'ll|will) .*?)\s*\1', r'\1', thinking, flags=re.IGNORECASE)
            # Remove standalone JSON-like syntax
            thinking = re.sub(r'^\s*\{.*?\}\s*$', '', thinking, flags=re.MULTILINE)
            # Clean up multiple newlines
            thinking = re.sub(r'\n{3,}', '\n\n', thinking)
            thinking = thinking.strip()

        # Clean up the answer part (remove any residual thinking tokens)
        answer = self._clean_llm_response(answer)

        return thinking, answer

    def _clean_llm_response(self, text: str) -> str:
        """
        Clean LLM response by removing internal thinking tokens and formatting.
        Some models output thinking process with special tokens that should be hidden from users.
        """
        if not text:
            return ""

        # Remove thinking/commentary tokens commonly used by reasoning models
        # These are internal thought processes that shouldn't be shown to users

        # Remove <|channel|>...content pattern (thinking tokens)
        # This catches both single-line and multi-line thinking blocks
        text = re.sub(r'<\|channel\|>[^<]*', '', text, flags=re.DOTALL)

        # Remove common thinking patterns
        text = re.sub(r'<\|channel\|>commentary\s*to=\w+[^<]*<\|message\|>', '', text, flags=re.DOTALL)
        text = re.sub(r'<\|channel\|>commentary[^<]*<\|message\|>', '', text, flags=re.DOTALL)

        # Remove <|message|> tokens
        text = re.sub(r'<\|message\|>', '', text)

        # Remove other common thinking markers
        text = re.sub(r'<\|.*?\|>', '', text)

        # Remove any leftover channel/message artifacts
        text = re.sub(r'<\|\w+\|>', '', text)

        # Clean up any remaining XML-style thinking tags (as backup)
        text = re.sub(r'<channel>.*?</channel>', '', text, flags=re.DOTALL)
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)

        # Clean up multiple blank lines
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

        # Clean up any remaining artifacts
        text = text.strip()

        return text

    def _save_conversation_log(
        self,
        session_id: str,
        question: str,
        answer: str,
        thinking: str,
        tool_calls: List[Dict[str, Any]],
        start_time: float,
        end_time: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Save conversation to JSON log file with timestamps and duration.

        Args:
            session_id: Unique session identifier
            question: User's question
            answer: Assistant's answer
            thinking: Assistant's thinking process
            tool_calls: List of tool calls made
            start_time: Request start timestamp (from time.time())
            end_time: Request end timestamp (from time.time())
            metadata: Additional metadata (model used, etc.)
        """
        try:
            # Create log entry
            duration_seconds = end_time - start_time
            log_entry = {
                "session_id": session_id,
                "timestamp": datetime.fromtimestamp(start_time).isoformat(),
                "timestamp_end": datetime.fromtimestamp(end_time).isoformat(),
                "duration_seconds": round(duration_seconds, 2),
                "question": question,
                "answer": answer,
                "thinking": thinking,
                "tool_calls": tool_calls,
                "metadata": metadata or {}
            }

            # Create filename: YYYY-MM-DD.json (one file per day)
            date_str = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d")
            log_file = self.conversation_log_dir / f"{date_str}.json"

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

            logger.info(f"💾 Conversation logged to {log_file} (duration: {duration_seconds:.2f}s)")

        except Exception as e:
            logger.error(f"Error saving conversation log: {e}", exc_info=True)
            # Don't fail the request if logging fails

    def _call_llm_with_fallback(self, **kwargs):
        """
        Make an LLM call with automatic fallback to OpenAI if primary fails.
        Handles temperature parameter differences between APIs.
        """
        # Try primary API (yunwu.ai) first
        try:
            # yunwu.ai supports temperature parameter
            primary_kwargs = kwargs.copy()
            if 'temperature' not in primary_kwargs and self.llm_temperature:
                primary_kwargs['temperature'] = self.llm_temperature

            logger.debug(f"Trying primary API: {self.llm_model}")
            return self.client.chat.completions.create(**primary_kwargs)

        except Exception as primary_error:
            logger.warning(f"Primary API failed: {str(primary_error)}")

            # Try fallback API (OpenAI official) if available
            if self.fallback_client:
                try:
                    logger.info("Falling back to OpenAI official API...")
                    fallback_kwargs = kwargs.copy()
                    fallback_kwargs['model'] = self.fallback_llm_model

                    # OpenAI GPT-5 doesn't support custom temperature, so remove it
                    if 'temperature' in fallback_kwargs:
                        del fallback_kwargs['temperature']

                    logger.debug(f"Using fallback model: {self.fallback_llm_model}")
                    return self.fallback_client.chat.completions.create(**fallback_kwargs)

                except Exception as fallback_error:
                    logger.error(f"Fallback API also failed: {str(fallback_error)}")
                    raise fallback_error
            else:
                logger.error("No fallback API configured")
                raise primary_error

    def _format_tool_response(self, tool_name: str, tool_args: Dict[str, Any], tool_result: Dict[str, Any]) -> str:
        """
        Format tool results into a natural language response when LLM fails to do so.
        This is a fallback for models that don't follow system prompt instructions well.
        """
        if tool_name == "find_airports_near_route":
            airports = tool_result.get("airports", [])
            count = tool_result.get("count", 0)
            from_icao = tool_args.get("from_icao", "").upper()
            to_icao = tool_args.get("to_icao", "").upper()

            if count == 0:
                return f"I searched for airports along the route from {from_icao} to {to_icao}, but found no suitable airports within the specified distance. You may need to widen the search radius."

            # Filter for AVGAS if mentioned in context
            avgas_airports = [a for a in airports if a.get("point_of_entry")]

            response = f"For your route from **{from_icao}** to **{to_icao}**, I found {count} airports along the way. "

            if avgas_airports and len(avgas_airports) > 0:
                response += f"\n\nHere are recommended fuel stops with customs clearance:\n\n"
                for i, airport in enumerate(avgas_airports[:3]):  # Show top 3
                    response += f"**{airport['ident']}** - {airport.get('name', 'Unknown')}\n"
                    response += f"- Location: {airport.get('municipality', 'N/A')}, {airport.get('country', 'N/A')}\n"
                    if airport.get('distance_nm'):
                        response += f"- Distance from route: {airport['distance_nm']:.1f}nm\n"
                    if airport.get('longest_runway_length_ft'):
                        response += f"- Longest runway: {airport['longest_runway_length_ft']}ft\n"
                    response += "\n"

            response += "\nI've marked these airports on the map for your review."
            return response

        elif tool_name == "search_airports":
            airports = tool_result.get("airports", [])
            count = tool_result.get("count", 0)
            query = tool_args.get("query", "")

            if count == 0:
                return f"I couldn't find any airports matching '{query}'. Please check the spelling or try a different search term."

            response = f"I found {count} airport(s) matching '{query}':\n\n"
            for airport in airports[:5]:  # Show top 5
                response += f"**{airport['ident']}** - {airport.get('name', 'Unknown')}\n"
                response += f"- Location: {airport.get('municipality', 'N/A')}, {airport.get('country', 'N/A')}\n"
                if airport.get('longest_runway_length_ft'):
                    response += f"- Longest runway: {airport['longest_runway_length_ft']}ft\n"
                response += "\n"

            response += "These airports are shown on the map."
            return response

        elif tool_name == "get_airport_details":
            if not tool_result.get("found"):
                icao = tool_args.get("icao_code", "").upper()
                return f"I couldn't find airport {icao} in the database."

            airport = tool_result.get("airport", {})
            runways = tool_result.get("runways", [])

            response = f"**{airport['ident']}** - {airport.get('name', 'Unknown')}\n\n"
            response += f"**Location:** {airport.get('municipality', 'N/A')}, {airport.get('country', 'N/A')}\n"
            if airport.get('elevation_ft'):
                response += f"**Elevation:** {airport['elevation_ft']}ft\n"
            if airport.get('point_of_entry'):
                response += f"**Customs:** Yes (Border crossing point)\n"

            if runways:
                response += f"\n**Runways:**\n"
                for rwy in runways:
                    response += f"- {rwy['le_ident']}/{rwy['he_ident']}: {rwy['length_ft']}ft x {rwy['width_ft']}ft, {rwy['surface']}\n"

            response += "\nDetails are shown on the map."
            return response

        elif tool_name == "get_border_crossing_airports":
            airports = tool_result.get("airports", [])
            count = tool_result.get("count", 0)
            country = tool_args.get("country")

            if count == 0:
                return "I couldn't find any border crossing airports matching your criteria."

            response = f"I found {count} border crossing (customs) airports"
            if country:
                response += f" in {country}"
            response += ":\n\n"

            # Group by country
            by_country = tool_result.get("by_country", {})
            for country_code, country_airports in list(by_country.items())[:5]:  # Limit to 5 countries
                response += f"**{country_code}:** "
                icaos = [a['ident'] for a in country_airports[:10]]  # Limit to 10 per country
                response += ", ".join(icaos)
                if len(country_airports) > 10:
                    response += f" and {len(country_airports) - 10} more"
                response += "\n"

            response += "\nAll border crossing airports are shown on the map."
            return response

        # Default fallback
        return "I've processed your request and the results are displayed on the map."

    def _create_system_prompt(self) -> str:
        """Create the system prompt that defines the assistant's behavior."""
        return """You are an expert European aviation assistant helping pilots with flight planning and airport information.

**Your Role:**
- Help pilots plan routes, find fuel stops, and locate customs airports
- Provide detailed airport information including runways, facilities, and procedures
- Suggest alternatives and backups for safety
- Always prioritize safety and regulatory compliance

**Your Knowledge:**
- Access to 2,951 airports across Europe
- Border crossing and customs information
- Fuel availability (AVGAS, Jet A)
- Runway details, lengths, and surface types
- Instrument procedures and approaches
- AIP (Aeronautical Information Publication) data

**CRITICAL - Thinking Process Format:**
ALWAYS structure your response in TWO parts:

1. **Thinking Process** (wrapped in <thinking>...</thinking> tags):
   - HIGH-LEVEL reasoning only (2-4 sentences max)
   - Why this query needs this approach
   - What you'll search for and why
   - All search progress updates ("Searching for...", "Now searching...", "Continuing search...")
   - All internal warnings and reminders to yourself
   - All meta-commentary about what you will do
   - DO NOT include tool call arguments or JSON
   - DO NOT repeat yourself
   - Keep it concise and strategic

2. **Final Answer** (outside the thinking tags):
   - MUST start with "Brief analysis:" followed by your explanation
   - The actual response to the user
   - Clear, concise, helpful information
   - References to map visualization

**CRITICAL - What NEVER Goes in Final Answer:**
❌ NEVER include these in your final answer (they belong in <thinking> tags):
   - "Searching for..." or "Now searching..." or "Continuing search..."
   - "I will search for..." or "I'm going to..."
   - "Warning: Always verify..." (internal reminders)
   - "Now providing..." or "Let me provide..."
   - Any commentary about your search process or strategy

✅ Final answer should ONLY contain:
   - Brief analysis of the query
   - Direct information for the user
   - Specific recommendations with details
   - Map visualization references

**Example (CORRECT FORMAT):**
<thinking>
User needs PAF contact info at LFPG. This isn't in our database, so I'll use web_search to find official DGAC/PAF resources and French ICAO General Declaration form.
</thinking>

Brief analysis:
For GA arrivals at LFPG from outside Schengen, you'll need to contact Police aux Frontières (PAF) and complete a French ICAO General Declaration.

**PAF Contact at LFPG:**
- Phone: +33 1 48 62 31 22 (PAF Terminal 2)
- Email: paf-cdg@interieur.gouv.fr
- Available 24/7 for general aviation

**Required Documentation:**
- ICAO General Declaration (available from DGAC website)
- Passenger manifests if applicable

⚠️ **Important**: Always verify contact details and current procedures with your handling agent before arrival.

**Example (WRONG - DO NOT DO THIS):**
<thinking>
User needs PAF contact. I'll search for it.
</thinking>

Warning: Always verify web search results with official aviation sources before making operational decisions.

I will search the web for current information, then provide official links and contacts.

Searching for LFPG Police aux Frontières (PAF) contact...
Searching for French "Déclaration générale d'aviation" form...
Continuing search for official DGAC/PAF resources...
Now providing the most relevant official links.

Brief analysis:
[answer content]

❌ The "Warning", "I will search", "Searching for", "Continuing", "Now providing" statements should ALL be in <thinking> tags, not in the answer!

**Another WRONG Example - DO NOT Output JSON:**
<thinking>
First search didn't find direct contact, need to try again with more specific query.
</thinking>

{"query":"PAF CDG contact email phone","max_results":10}
{"query":"Police aux Frontières Roissy contact","max_results":10}

Brief analysis: I couldn't find exact contact information...

❌ NEVER output tool call JSON syntax in your answer! If the first search didn't work perfectly, work with what you have or tell the user the information isn't available in web results. Do NOT try to make multiple searches by outputting JSON.

**Communication Style:**
- Be concise but thorough
- Always include ICAO codes for clarity
- Use nautical miles (nm) for distances
- Mention key facilities (customs, fuel, restaurants)
- Highlight safety considerations
- When listing multiple options, prioritize by convenience and safety
- ALWAYS use the <thinking>...</thinking> format for your reasoning

**Response Structure:**
When answering queries with tool results, structure your response as follows:

1. **Brief Analysis** (1-2 sentences):
   - Explain what you're looking for based on the query
   - Mention key criteria (fuel type, customs, distance range, etc.)

2. **Main Answer with Details**:
   - List specific airports with ICAO codes
   - Include relevant details (fuel availability, runway specs, customs status)
   - Prioritize recommendations by convenience and safety
   - Be specific with numbers (distances, runway lengths, etc.)

3. **Map Reference** (1 brief sentence at the end):
   - Mention that results are shown on the map
   - E.g., "I've marked these airports on the map for your review."

**Example Response:**
User: "Plan a route from EGTF to LFMD with a fuel stop that has AVGAS"

Good Response:
"For your route from EGTF (Fairoaks) to LFMD (Cannes Mandelieu), you'll need a fuel stop with AVGAS. I searched for airports within 50nm of the direct route.

I recommend **LFLW (Auxerre-Branches)** as your primary fuel stop:
- Located 26nm from your route, 245nm from departure
- Fuel: AVGAS available
- Runway: 05/23, 4,593ft hard surface
- Customs: Point of entry available

Alternative options along the route:
- **LFLD (Bourges)** - 18nm off route, AVGAS, 10,827ft runway
- **LFLJ (Montluçon-Guéret)** - 32nm off route, AVGAS available

I've marked your route and these fuel stop options on the map."

**CRITICAL - Response Format:**
- NEVER return JSON output to users
- ALWAYS use natural language with complete sentences
- DO NOT output raw data structures, paths, or query strings
- DO NOT output tool call syntax like {"query":"...", "max_results":...}
- Your response must be conversational and helpful
- If you already called a tool and the results aren't perfect, work with what you have
- Do NOT try to make multiple tool calls - use the results from the first call

**Important:**
- When you use tools, results will be visualized on the interactive map automatically
- Use proper aviation terminology
- Distances are in nautical miles (nm), altitudes in feet (ft)
- Be specific and actionable in your recommendations

**Available Tools:**
- search_airports: Find airports by name, ICAO, or city
- find_airports_near_route: Find stops along a route (USE THIS for route planning!)
- get_airport_details: Detailed info about specific airport (use sparingly, only for single airport queries)
- get_border_crossing_airports: List customs airports
- get_airport_statistics: Database statistics
- list_rules_for_country: Get aviation rules/regulations for a country (customs, flight plans, airspace, IFR/VFR)
- compare_rules_between_countries: Compare regulations between two countries for international flight planning
- web_search: Search the web for information NOT in the database (fees, NOTAMs, current regulations, weather)

**IMPORTANT - When to Use Rules Tools:**
Use `list_rules_for_country` when:
- User asks about country-specific aviation regulations
- Questions about customs requirements, flight plan procedures
- Airspace classification and IFR/VFR rules
- Fuel requirements or restrictions
- Border crossing procedures

Use `compare_rules_between_countries` when:
- Planning international flights between two countries
- User wants to understand regulatory differences
- Comparing customs, airspace, or operational requirements

Examples:
- "What are the customs rules for France?" → Use list_rules_for_country with country_code="FR"
- "Compare flight plan requirements between UK and Germany" → Use compare_rules_between_countries
- "Flying from France to Spain, what are the differences?" → Use compare_rules_between_countries

**IMPORTANT - When to Use Web Search:**
Use `web_search` when:
- User asks about landing/parking FEES (not in database)
- User asks about current NOTAMs or temporary restrictions
- User asks about weather or operational status
- User asks about regulations or procedures not in rules database
- Database tools return no results or insufficient information

Examples:
- "What are the fees for LFPG?" → Use web_search with query "LFPG landing fees general aviation"
- "Any NOTAMs for EGLL?" → Use web_search with query "EGLL Heathrow NOTAM current"
- "What's the weather at LFMD?" → Use web_search with query "LFMD Cannes weather METAR"

ALWAYS remind users to verify web search results with official sources (AIP, NOTAM, airport authorities).

**IMPORTANT - Tool Usage for Route Queries:**
When asked about routes, trips, or planning flights between airports:
- ALWAYS use `find_airports_near_route` to generate route visualization
- For multi-leg trips (e.g., "London to Rome via Alps"), break into legs and call `find_airports_near_route` for EACH leg
- Example: "London to Rome via Alps"
  → Call find_airports_near_route(from_icao="EGKB", to_icao="LFMN", max_distance_nm=50)
  → Call find_airports_near_route(from_icao="LFMN", to_icao="LIRF", max_distance_nm=50)
- This ensures the route lines and stops are drawn on the map

Remember: You're helping pilots make informed decisions. Provide clear reasoning, specific details, then reference the map visualization."""

    def chat(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a chat message and return response with visualization data.

        Args:
            message: User's message
            history: Conversation history (list of {role, content} dicts)
            session_id: Optional session ID for tracking

        Returns:
            Dict with:
                - message: Assistant's text response
                - visualization: Data for map visualization (if applicable)
                - tool_calls: List of tools that were called
                - history: Updated conversation history
        """
        try:
            # Build messages array
            messages = [{"role": "system", "content": self.system_prompt}]

            # Add history
            if history:
                messages.extend(history)

            # Add current message
            messages.append({"role": "user", "content": message})

            # Track visualization data from tool calls
            visualizations = []
            tool_calls_made = []

            # Make initial LLM call with fallback
            response = self._call_llm_with_fallback(
                model=self.llm_model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                max_completion_tokens=None if self.llm_max_tokens == -1 else self.llm_max_tokens,
            )

            # Debug: Log response type
            logger.info(f"LLM Response type: {type(response)}")
            if isinstance(response, str):
                logger.error(f"LLM returned string instead of ChatCompletion: {response[:200]}")
                raise ValueError("LLM API returned string instead of proper response object")

            assistant_message = response.choices[0].message

            # Check if LLM wants to call tools
            if assistant_message.tool_calls:
                logger.info(f"LLM requested {len(assistant_message.tool_calls)} tool calls")

                # Add assistant's tool call request to messages
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })

                # Execute each tool call
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    logger.info(f"Calling tool: {function_name} with args: {function_args}")

                    # Call the tool via MCP client
                    tool_result = self.mcp_client._call_tool(function_name, function_args)

                    tool_calls_made.append({
                        "name": function_name,
                        "arguments": function_args,
                        "result": tool_result
                    })

                    # Extract visualization data if present
                    if "visualization" in tool_result:
                        visualizations.append(tool_result["visualization"])

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": json.dumps(tool_result)
                    })

                # Make second LLM call with tool results and fallback
                final_response = self._call_llm_with_fallback(
                    model=self.llm_model,
                    messages=messages,
                    max_completion_tokens=None if self.llm_max_tokens == -1 else self.llm_max_tokens,
                )

                # Extract thinking and answer from response
                raw_content = final_response.choices[0].message.content
                thinking, final_message = self._extract_thinking_and_answer(raw_content)

                # Check if LLM response is problematic (too short, JSON-like, empty)
                # If so, use our formatted response as fallback
                if (
                    not final_message
                    or len(final_message) < 20
                    or final_message.strip().startswith('{')
                    or final_message.strip().startswith('[')
                    or '"path"' in final_message
                    or '"query"' in final_message
                ):
                    logger.warning(f"LLM produced poor response: '{final_message[:100]}'. Using fallback formatter.")
                    # Use our fallback formatter with the first tool call
                    if tool_calls_made:
                        first_tool = tool_calls_made[0]
                        final_message = self._format_tool_response(
                            first_tool["name"],
                            first_tool["arguments"],
                            first_tool["result"]
                        )
                        # No thinking for fallback responses
                        thinking = ""

            else:
                # No tool calls, use direct response
                raw_content = assistant_message.content
                thinking, final_message = self._extract_thinking_and_answer(raw_content)
                messages.append({"role": "assistant", "content": final_message})

            # Prepare response
            return {
                "message": final_message,
                "thinking": thinking,  # Add thinking to response
                "visualization": visualizations[0] if len(visualizations) == 1 else visualizations if visualizations else None,
                "tool_calls": tool_calls_made,
                "history": messages[1:],  # Exclude system prompt from returned history
                "session_id": session_id
            }

        except Exception as e:
            logger.error(f"Error in chat: {e}", exc_info=True)
            return {
                "message": f"I apologize, but I encountered an error: {str(e)}. Please try again.",
                "visualization": None,
                "tool_calls": [],
                "history": history or [],
                "error": str(e)
            }

    def chat_stream(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        Stream chat response with thinking and answer as separate events.
        Yields SSE-formatted events: thinking, message, visualization, tool_calls, done.
        """
        import time

        try:
            start_time = time.time()
            logger.info(f"⏱️ TIMING: chat_stream started for message: '{message[:50]}...'")

            # Build messages array
            messages = [{"role": "system", "content": self.system_prompt}]
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": message})

            prep_time = time.time()
            logger.info(f"⏱️ TIMING: Message prep took {prep_time - start_time:.2f}s")

            # Track state
            visualizations = []
            tool_calls_made = []
            in_thinking = False
            thinking_buffer = ""
            answer_buffer = ""
            full_response = ""

            # First pass: Check if LLM wants to call tools (non-streaming) with fallback
            logger.info(f"⏱️ TIMING: Starting first LLM call (tool detection)...")
            llm_start = time.time()
            initial_response = self._call_llm_with_fallback(
                model=self.llm_model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                max_completion_tokens=None if self.llm_max_tokens == -1 else self.llm_max_tokens,
            )

            llm_end = time.time()
            logger.info(f"⏱️ TIMING: First LLM call completed in {llm_end - llm_start:.2f}s")

            assistant_message = initial_response.choices[0].message

            # If tools needed, execute them
            if assistant_message.tool_calls:
                tools_start = time.time()
                logger.info(f"⏱️ TIMING: LLM requested {len(assistant_message.tool_calls)} tool calls")

                # Add assistant's tool call request
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })

                # Execute tools
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    tool_exec_start = time.time()
                    logger.info(f"⏱️ TIMING: Calling tool: {function_name} with args: {function_args}")

                    tool_result = self.mcp_client._call_tool(function_name, function_args)

                    tool_exec_end = time.time()
                    logger.info(f"⏱️ TIMING: Tool {function_name} completed in {tool_exec_end - tool_exec_start:.2f}s")
                    tool_calls_made.append({
                        "name": function_name,
                        "arguments": function_args,
                        "result": tool_result
                    })

                    if "visualization" in tool_result:
                        visualizations.append(tool_result["visualization"])

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": json.dumps(tool_result)
                    })

                tools_end = time.time()
                logger.info(f"⏱️ TIMING: All tools completed in {tools_end - tools_start:.2f}s")

            # Stream final response with fallback
            logger.info(f"⏱️ TIMING: Starting second LLM call (streaming response generation)...")
            stream_start = time.time()
            stream = self._call_llm_with_fallback(
                model=self.llm_model,
                messages=messages,
                max_completion_tokens=None if self.llm_max_tokens == -1 else self.llm_max_tokens,
                stream=True
            )

            # Process stream chunks with TRUE immediate streaming (from first token)
            tag_buffer = ""  # Only used when we detect potential tag start
            first_chunk_received = False

            for chunk in stream:
                # Check if chunk has choices and content
                if not chunk.choices or len(chunk.choices) == 0:
                    continue

                delta = chunk.choices[0].delta
                if not delta or not hasattr(delta, 'content') or not delta.content:
                    continue

                if not first_chunk_received:
                    first_chunk_time = time.time()
                    logger.info(f"⏱️ TIMING: First streaming chunk received in {first_chunk_time - stream_start:.2f}s")
                    first_chunk_received = True

                content = delta.content
                full_response += content

                logger.debug(f"Stream chunk: {repr(content)}, in_thinking: {in_thinking}")

                # Process character by character with TRUE immediate streaming
                for char in content:
                    # If we have a tag buffer, we're in the middle of checking for a tag
                    if tag_buffer:
                        tag_buffer += char

                        # Check for opening tag completion
                        if tag_buffer == "<thinking>":
                            in_thinking = True
                            thinking_buffer = ""
                            tag_buffer = ""
                            logger.info("Detected <thinking> tag - starting thinking mode")
                            continue

                        # Check for closing tag completion
                        elif tag_buffer == "</thinking>":
                            in_thinking = False
                            thinking_clean = self._clean_thinking(thinking_buffer)
                            logger.info(f"Detected </thinking> tag - full thinking: {repr(thinking_clean[:200])}")
                            yield f"event: thinking_done\ndata: {json.dumps({})}\n\n"
                            tag_buffer = ""
                            thinking_buffer = ""
                            continue

                        # Check if this could still be a tag
                        elif "<thinking>".startswith(tag_buffer) or "</thinking>".startswith(tag_buffer):
                            # Still potentially a tag, keep buffering
                            continue

                        # Not a tag, flush buffer and continue
                        else:
                            # Flush the buffer content
                            if in_thinking:
                                thinking_buffer += tag_buffer
                                for c in tag_buffer:
                                    if c not in ['{', '}', '"']:
                                        yield f"event: thinking\ndata: {json.dumps({'content': c})}\n\n"
                            else:
                                answer_buffer += tag_buffer
                                for c in tag_buffer:
                                    yield f"event: message\ndata: {json.dumps({'content': c})}\n\n"
                            tag_buffer = ""
                            # Don't continue, process current char below

                    # Check if this char starts a potential tag
                    if char == '<' and not tag_buffer:
                        tag_buffer = '<'
                        continue

                    # Normal character - stream immediately!
                    if in_thinking:
                        thinking_buffer += char
                        if char not in ['{', '}', '"']:
                            yield f"event: thinking\ndata: {json.dumps({'content': char})}\n\n"
                    else:
                        answer_buffer += char
                        yield f"event: message\ndata: {json.dumps({'content': char})}\n\n"

            # Flush remaining tag_buffer at end of stream
            if tag_buffer:
                if in_thinking:
                    thinking_buffer += tag_buffer
                    for c in tag_buffer:
                        if c not in ['{', '}', '"']:
                            yield f"event: thinking\ndata: {json.dumps({'content': c})}\n\n"
                else:
                    answer_buffer += tag_buffer
                    for c in tag_buffer:
                        yield f"event: message\ndata: {json.dumps({'content': c})}\n\n"

            # Send tool calls if any
            if tool_calls_made:
                yield f"event: tool_calls\ndata: {json.dumps(tool_calls_made)}\n\n"

            # Send visualization if any
            if visualizations:
                viz_data = visualizations[0] if len(visualizations) == 1 else visualizations
                yield f"event: visualization\ndata: {json.dumps(viz_data)}\n\n"

            # Final timing summary
            end_time = time.time()
            total_time = end_time - start_time
            logger.info(f"⏱️ TIMING: ═══════════════════════════════════════")
            logger.info(f"⏱️ TIMING: TOTAL request time: {total_time:.2f}s")
            logger.info(f"⏱️ TIMING: ═══════════════════════════════════════")

            # Save conversation log
            self._save_conversation_log(
                session_id=session_id or "unknown",
                question=message,
                answer=answer_buffer,
                thinking=thinking_buffer,
                tool_calls=tool_calls_made,
                start_time=start_time,
                end_time=end_time,
                metadata={
                    "model": self.llm_model,
                    "temperature": self.llm_temperature,
                    "total_time_seconds": round(total_time, 2),
                    "has_visualizations": len(visualizations) > 0,
                    "num_tool_calls": len(tool_calls_made)
                }
            )

            # Send done event
            yield f"event: done\ndata: {json.dumps({'session_id': session_id})}\n\n"

        except Exception as e:
            logger.error(f"Error in streaming chat: {e}", exc_info=True)
            error_msg = f"I apologize, but I encountered an error: {str(e)}"
            yield f"event: error\ndata: {json.dumps({'message': error_msg})}\n\n"

    def _clean_thinking(self, text: str) -> str:
        """Clean thinking content from JSON artifacts."""
        if not text:
            return ""
        # Remove JSON objects
        text = re.sub(r'\{[^}]*"[^"]*"[^}]*\}', '', text, flags=re.DOTALL)
        # Remove repeated phrases
        text = re.sub(r'(I(?:\'m going to|\'ll|will) .*?)\s*\1', r'\1', text, flags=re.IGNORECASE)
        # Remove standalone JSON
        text = re.sub(r'^\s*\{.*?\}\s*$', '', text, flags=re.MULTILINE)
        # Clean up newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def get_quick_actions(self) -> List[Dict[str, str]]:
        """
        Return a list of quick action prompts for the UI.
        These help pilots get started quickly with example questions.
        """
        return [
            {
                "title": "Search",
                "prompt": "Find airports in Paris",
                "icon": "🔍"
            },
            {
                "title": "Route",
                "prompt": "Plan a route from EGTF to LFMD with a fuel stop that has AVGAS",
                "icon": "🛫"
            },
            {
                "title": "Details",
                "prompt": "Tell me about LFPG - runways, facilities, and procedures",
                "icon": "ℹ️"
            },
            {
                "title": "Border",
                "prompt": "Show all border crossing airports in Germany",
                "icon": "🛂"
            }
        ]
