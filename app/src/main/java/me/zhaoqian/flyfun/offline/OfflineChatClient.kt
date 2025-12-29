package me.zhaoqian.flyfun.offline

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.serialization.json.*
import me.zhaoqian.flyfun.data.models.ChatMessage
import me.zhaoqian.flyfun.data.models.ChatRequest
import me.zhaoqian.flyfun.data.models.ChatStreamEvent
import me.zhaoqian.flyfun.data.models.ToolCall
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Offline chat client that uses local LLM inference and tool execution.
 * 
 * Uses LiteRT-LM for GPU acceleration when .litertlm model is available,
 * falls back to MediaPipe for CPU inference with .task model.
 */
@Singleton
class OfflineChatClient @Inject constructor(
    private val liteRtLmEngine: LiteRtLmInferenceEngine,
    private val mediaPipeEngine: MediaPipeInferenceEngine,
    private val toolDispatcher: LocalToolDispatcher,
    private val modelManager: ModelManager
) {
    // Track which engine is active
    private var useLiteRtLm = true
    companion object {
        private const val TAG = "OfflineChatClient"
        
        // Tool definitions for the model
        val AVAILABLE_TOOLS = listOf(
            ToolDefinition(
                name = "find_airports_near_location",
                description = "Find airports near a specific location (ICAO code, city, or place name). Optionally filter by notification/customs requirements.",
                parameters = mapOf(
                    "location_query" to "ICAO code, city name, or place name to search near",
                    "max_distance_nm" to "Maximum distance in nautical miles (default: 50)",
                    "max_hours_notice" to "Filter to airports with customs notice <= this many hours (e.g. 24 for same-day)",
                    "limit" to "Maximum results (default: 20)"
                )
            ),
            ToolDefinition(
                name = "find_airports_near_route",
                description = "Find airports along a flight route between two locations",
                parameters = mapOf(
                    "from_location" to "Departure ICAO code or city",
                    "to_location" to "Destination ICAO code or city",
                    "max_distance_nm" to "Maximum distance from route centerline (default: 50)"
                )
            ),
            ToolDefinition(
                name = "get_border_crossing_airports",
                description = "Get list of airports with customs/immigration facilities for border crossing (point of entry airports)",
                parameters = mapOf(
                    "country" to "Two-letter country code to filter (e.g. DE, FR). Optional - returns all if not specified."
                )
            ),
            ToolDefinition(
                name = "get_notification_for_airport",
                description = "Get customs/immigration notification requirements for a specific airport",
                parameters = mapOf(
                    "icao" to "ICAO code of the airport",
                    "day_of_week" to "Optional day of week (Monday, Saturday, etc.)"
                )
            ),
            ToolDefinition(
                name = "find_airports_by_notification",
                description = "Find airports filtered by notification requirements",
                parameters = mapOf(
                    "max_hours_notice" to "Maximum hours of advance notice required (e.g. 24)",
                    "notification_type" to "Type of notification (e.g. 'h24' for 24/7 airports)",
                    "country" to "Two-letter country code to filter"
                )
            ),
            ToolDefinition(
                name = "search_airports",
                description = "Search for airports by ICAO code, name, or city",
                parameters = mapOf(
                    "query" to "Search term (ICAO, name, or city)",
                    "limit" to "Maximum results to return (default: 10)"
                )
            ),
            ToolDefinition(
                name = "get_airport_details",
                description = "Get detailed information about a specific airport",
                parameters = mapOf(
                    "icao" to "ICAO code of the airport"
                )
            ),
            ToolDefinition(
                name = "get_airport_runways",
                description = "Get runway information for an airport",
                parameters = mapOf(
                    "icao" to "ICAO code of the airport"
                )
            ),
            ToolDefinition(
                name = "list_rules_for_country",
                description = "List aviation rules for a specific country",
                parameters = mapOf(
                    "country" to "Two-letter country code (e.g., DE, FR, GB)"
                )
            ),
            ToolDefinition(
                name = "compare_rules_between_countries",
                description = "Compare aviation rules between two countries",
                parameters = mapOf(
                    "country1" to "First country code",
                    "country2" to "Second country code"
                )
            )
        )
        
        // System prompt for the aviation assistant (matches web version planner_v1.md)
        private val SYSTEM_PROMPT = """
You are FlyFun, an expert aviation planning assistant for European pilots.

## Available Tools
Use JSON format to call tools: {"tool": "tool_name", "arguments": {...}}

{TOOL_CATALOG}

**CRITICAL - Argument Extraction:**
You MUST extract ALL required and optional arguments for the selected tool:
- find_airports_near_location: ALWAYS set 'location_query', AND set 'max_hours_notice' if user mentions customs notice time (e.g., "less than 24h notice" → max_hours_notice=24)
- find_airports_near_route: ALWAYS set 'from_location' and 'to_location'
- get_airport_details: ALWAYS set 'icao'
- search_airports: ALWAYS set 'query'
- get_border_crossing_airports: optionally set 'country'
- list_rules_for_country: ALWAYS set 'country_code'
- compare_rules_between_countries: ALWAYS set 'country1' and 'country2'
- get_notification_for_airport: ALWAYS set 'icao', optionally set 'day_of_week' (Saturday, Sunday, etc.)
- find_airports_by_notification: optionally set 'max_hours_notice', 'notification_type', 'country'

**BORDER CROSSING / CUSTOMS AIRPORTS - Use get_border_crossing_airports:**
When user asks for airports with customs, point of entry, or border crossing:
- "Border crossing airports in Germany" → {"tool": "get_border_crossing_airports", "arguments": {"country": "DE"}}
- "Customs airports in France" → {"tool": "get_border_crossing_airports", "arguments": {"country": "FR"}}
- "Point of entry airports" → {"tool": "get_border_crossing_airports", "arguments": {}}

**LOCATION + NOTIFICATION QUERIES - Use find_airports_near_location with max_hours_notice:**
When user asks for airports near a location WITH customs/notification requirements:
- "Airports near EDDR with less than 24h notice" → {"tool": "find_airports_near_location", "arguments": {"location_query": "EDDR", "max_hours_notice": 24}}
- "Airports near Paris with customs" → {"tool": "find_airports_near_location", "arguments": {"location_query": "Paris"}}

**NOTIFICATION-ONLY QUERIES - Use find_airports_by_notification:**
When user asks for airports ONLY filtered by notification (no location):
- "Airports with less than 24h notice in France" → {"tool": "find_airports_by_notification", "arguments": {"max_hours_notice": 24, "country": "FR"}}
- "H24 airports in Germany" → {"tool": "find_airports_by_notification", "arguments": {"notification_type": "h24", "country": "DE"}}

**SPECIFIC AIRPORT NOTIFICATION - Use get_notification_for_airport:**
- "What's the notification for LFRG?" → {"tool": "get_notification_for_airport", "arguments": {"icao": "LFRG"}}

Pick the tool that can produce the most authoritative answer for the pilot.
After receiving tool results, list ALL results with ICAO codes, names, and notification/customs details.
        """.trimIndent()
    }
    
    private val json = Json { ignoreUnknownKeys = true }
    
    data class ToolDefinition(
        val name: String,
        val description: String,
        val parameters: Map<String, String>
    )
    
    data class ParsedToolCall(
        val name: String,
        val arguments: Map<String, Any?>
    )
    
    /**
     * Process a chat request offline, emitting the same events as the online client.
     */
    fun streamChat(request: ChatRequest): Flow<ChatStreamEvent> = flow {
        Log.d(TAG, "Starting offline chat with ${request.messages.size} messages")
        
        // Try to load LiteRT-LM model first (GPU), then fallback to MediaPipe (CPU)
        if (!liteRtLmEngine.isLoaded() && !mediaPipeEngine.isLoaded()) {
            emit(ChatStreamEvent.ThinkingEvent("Loading offline model..."))
            
            // Try LiteRT-LM first if .litertlm model exists
            val liteRtLmPath = ModelManager.LITERTLM_MODEL_PATH
            if (File(liteRtLmPath).exists()) {
                Log.i(TAG, "Attempting LiteRT-LM with GPU support...")
                val loadResult = liteRtLmEngine.loadModel(liteRtLmPath)
                if (loadResult.isSuccess) {
                    useLiteRtLm = true
                    Log.i(TAG, "Using LiteRT-LM engine (${liteRtLmEngine.getBackend()} backend)")
                } else {
                    Log.w(TAG, "LiteRT-LM failed: ${loadResult.exceptionOrNull()?.message}")
                }
            }
            
            // Fallback to MediaPipe if LiteRT-LM didn't load
            if (!liteRtLmEngine.isLoaded()) {
                Log.i(TAG, "Falling back to MediaPipe (CPU)...")
                val mediaPipePath = ModelManager.MEDIAPIPE_TEST_MODEL_PATH
                val loadResult = mediaPipeEngine.loadModel(mediaPipePath)
                if (loadResult.isFailure) {
                    emit(ChatStreamEvent.ErrorEvent("Failed to load offline model: ${loadResult.exceptionOrNull()?.message}"))
                    return@flow
                }
                useLiteRtLm = false
                Log.i(TAG, "Using MediaPipe engine (CPU backend)")
            }
        }
        
        // Initialize tool dispatcher (copies database from assets if needed)
        val dispatcherResult = toolDispatcher.initialize()
        if (dispatcherResult.isFailure) {
            Log.e(TAG, "Failed to initialize tool dispatcher: ${dispatcherResult.exceptionOrNull()?.message}")
            // Continue anyway - tools just won't work but chat will still function
        }
        
        emit(ChatStreamEvent.ThinkingEvent("Processing locally..."))
        
        // Build the full prompt
        val prompt = buildPrompt(request)
        Log.d(TAG, "Prompt built, length: ${prompt.length}")
        
        // Generate response using appropriate engine
        val fullResponse = StringBuilder()
        
        try {
            if (useLiteRtLm && liteRtLmEngine.isLoaded()) {
                // Use LiteRT-LM (GPU/CPU)
                val response = liteRtLmEngine.generate(prompt)
                fullResponse.append(response)
                // Don't emit TokenEvent here - wait to see if it's a tool call
            } else {
                // Use MediaPipe (CPU)
                mediaPipeEngine.generateStream(prompt, maxTokens = 1024)
                    .collect { token ->
                        fullResponse.append(token)
                        // Don't emit TokenEvent here - wait to see if it's a tool call
                    }
            }
            
            val responseText = fullResponse.toString()
            Log.d(TAG, "Full response: $responseText")
            
            // Check if the response contains a tool call
            val toolCallMatch = extractToolCall(responseText)
            
            if (toolCallMatch != null) {
                Log.d(TAG, "Tool call detected: ${toolCallMatch.name}")
                
                // Emit thinking event while executing tool
                emit(ChatStreamEvent.ThinkingEvent("Calling ${toolCallMatch.name}..."))
                
                // Execute the tool
                val toolResult = toolDispatcher.dispatch(
                    LocalToolDispatcher.ToolCallRequest(
                        name = toolCallMatch.name,
                        arguments = toolCallMatch.arguments
                    )
                )
                
                // Emit ToolCallEvent with result
                val toolResultText = when (toolResult) {
                    is LocalToolDispatcher.ToolResult.Success -> toolResult.data
                    is LocalToolDispatcher.ToolResult.Error -> "Error: ${toolResult.message}"
                }
                
                // Convert arguments to String map for ToolCall
                val argsStringMap = toolCallMatch.arguments.mapValues { it.value?.toString() ?: "" }
                emit(ChatStreamEvent.ToolCallEvent(
                    ToolCall(
                        name = toolCallMatch.name,
                        args = argsStringMap,
                        result = toolResultText.take(500) + if (toolResultText.length > 500) "..." else ""
                    )
                ))
                
                // Log full tool result for debugging
                Log.i(TAG, "=== TOOL OUTPUT START ===")
                Log.i(TAG, "Tool: ${toolCallMatch.name}")
                Log.i(TAG, "Full result length: ${toolResultText.length}")
                // Log in chunks to avoid logcat truncation
                toolResultText.chunked(1000).forEachIndexed { i, chunk ->
                    Log.i(TAG, "Result chunk $i: $chunk")
                }
                Log.i(TAG, "=== TOOL OUTPUT END ===")
                
                // Truncate tool result to prevent token limit exceeded (max ~4000 chars)
                val truncatedResult = if (toolResultText.length > 4000) {
                    Log.d(TAG, "Truncating tool result from ${toolResultText.length} to 4000 chars")
                    toolResultText.take(4000) + "...(truncated)"
                } else {
                    toolResultText
                }
                
                Log.d(TAG, "Tool result for model: ${truncatedResult.take(500)}...")
                
                val followUpPrompt = buildFollowUpPrompt(prompt, toolCallMatch, truncatedResult)
                Log.d(TAG, "Follow-up prompt length: ${followUpPrompt.length}")
                
                // Generate the final answer using appropriate engine
                val followUpResponse = StringBuilder()
                if (useLiteRtLm && liteRtLmEngine.isLoaded()) {
                    val response = liteRtLmEngine.generate(followUpPrompt)
                    Log.d(TAG, "Follow-up response from LiteRT-LM: ${response.take(200)}...")
                    followUpResponse.append(response)
                    emit(ChatStreamEvent.TokenEvent(response))
                } else {
                    mediaPipeEngine.generateStream(followUpPrompt, maxTokens = 512)
                        .collect { token ->
                            followUpResponse.append(token)
                            emit(ChatStreamEvent.TokenEvent(token))
                        }
                }
                
                // Log full final answer for debugging
                Log.i(TAG, "=== FINAL ANSWER START ===")
                Log.i(TAG, "Answer length: ${followUpResponse.length}")
                followUpResponse.toString().chunked(1000).forEachIndexed { i, chunk ->
                    Log.i(TAG, "Answer chunk $i: $chunk")
                }
                Log.i(TAG, "=== FINAL ANSWER END ===")
                
                Log.d(TAG, "Emitting FinalAnswerEvent with ${followUpResponse.length} chars")
                emit(ChatStreamEvent.FinalAnswerEvent(followUpResponse.toString()))
            } else {
                // No tool call, use the response directly
                emit(ChatStreamEvent.FinalAnswerEvent(responseText))
            }
            
            Log.d(TAG, "Emitting DoneEvent")
            emit(ChatStreamEvent.DoneEvent)
            
        } catch (e: Exception) {
            Log.e(TAG, "Generation error: ${e.message}", e)
            emit(ChatStreamEvent.ErrorEvent(e.message ?: "Unknown error during generation"))
        }
    }.flowOn(Dispatchers.IO)
    
    /**
     * Build the full prompt from the chat request
     */
    private fun buildPrompt(request: ChatRequest): String {
        val sb = StringBuilder()
        
        // Build tool catalog for the prompt
        val toolCatalog = AVAILABLE_TOOLS.joinToString("\n") { tool ->
            "- ${tool.name}: ${tool.description}\n  Parameters: ${tool.parameters}"
        }
        val systemPromptWithTools = SYSTEM_PROMPT.replace("{TOOL_CATALOG}", toolCatalog)
        
        // Iterate through messages
        var isFirstUserMessage = true
        
        for (message in request.messages) {
            when (message.role) {
                "user" -> {
                    sb.appendLine("<start_of_turn>user")
                    // Prepend system prompt to the first user message
                    if (isFirstUserMessage) {
                        sb.appendLine(systemPromptWithTools)
                        sb.appendLine()
                        // Add persona context if available
                        request.personaId?.let { personaId ->
                            sb.appendLine("User persona: $personaId")
                            sb.appendLine()
                        }
                        isFirstUserMessage = false
                    }
                    sb.appendLine(message.content)
                    sb.appendLine("<end_of_turn>")
                }
                "assistant" -> {
                    sb.appendLine("<start_of_turn>model")
                    sb.appendLine(message.content)
                    sb.appendLine("<end_of_turn>")
                }
            }
        }
        
        // If there were no user messages (rare edge case), force system prompt
        if (isFirstUserMessage) {
             sb.appendLine("<start_of_turn>user")
             sb.appendLine(SYSTEM_PROMPT)
             sb.appendLine("<end_of_turn>")
        }
        
        // Prompt for model response
        sb.appendLine("<start_of_turn>model")
        
        return sb.toString()
    }
    
    /**
     * Build a follow-up prompt after tool execution
     */
    private fun buildFollowUpPrompt(
        originalPrompt: String,
        toolCall: ParsedToolCall,
        toolResult: String
    ): String {
        // Use a clear formatter-style prompt that instructs the model to synthesize an answer
        return """
<start_of_turn>user
${SYSTEM_PROMPT.replace("{TOOL_CATALOG}", "")}

User question: ${extractUserQuestion(originalPrompt)}

I called the tool "${toolCall.name}" and got these results:
$toolResult

Please provide a helpful, natural language response to the user's question based on these results.
- Format your response using clean markdown (headers, bullet points)
- List the relevant airports with their ICAO codes, names, and key details
- Mention notification requirements if available
- Be concise but comprehensive
- Do NOT use tables - use bullet point lists instead
<end_of_turn>
<start_of_turn>model
""".trimIndent()
    }
    
    /**
     * Extract the original user question from the prompt
     */
    private fun extractUserQuestion(prompt: String): String {
        // Find the last user message content
        val userPattern = Regex("<start_of_turn>user\\s*(.+?)\\s*<end_of_turn>", RegexOption.DOT_MATCHES_ALL)
        val matches = userPattern.findAll(prompt).toList()
        return if (matches.isNotEmpty()) {
            // Get the content of the last user turn, remove system prompt if present
            val lastUserContent = matches.last().groupValues[1]
            // Find actual question (after any system prompts)
            val lines = lastUserContent.lines()
            val questionStart = lines.indexOfLast { it.isNotBlank() && !it.startsWith("You are") }
            if (questionStart >= 0) lines[questionStart] else lastUserContent.takeLast(200)
        } else {
            prompt.takeLast(200)
        }
    }
    
    /**
     * Extract a tool call from the model's response
     */
    private fun extractToolCall(response: String): ParsedToolCall? {
        // Look for JSON tool call pattern - support newlines
        val toolPattern = Regex("""\{"tool"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{.*?\})\}""", setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE))
        val match = toolPattern.find(response) ?: return null
        
        return try {
            val toolName = match.groupValues[1]
            val argsJson = match.groupValues[2]
            
            val arguments = json.parseToJsonElement(argsJson).jsonObject
                .mapValues { (_, value) ->
                    when (value) {
                        is JsonPrimitive -> value.content
                        else -> value.toString()
                    }
                }
            
            ParsedToolCall(toolName, arguments)
        } catch (e: Exception) {
            Log.w(TAG, "Failed to parse tool call: ${e.message}")
            null
        }
    }
}
