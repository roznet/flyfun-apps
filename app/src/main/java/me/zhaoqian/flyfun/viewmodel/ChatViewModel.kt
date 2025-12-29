package me.zhaoqian.flyfun.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import me.zhaoqian.flyfun.data.models.*
import me.zhaoqian.flyfun.data.repository.FlyFunRepository
import me.zhaoqian.flyfun.data.repository.RouteStateHolder
import me.zhaoqian.flyfun.offline.ModelManager
import java.util.UUID
import javax.inject.Inject

/**
 * ViewModel for the Chat screen - manages conversation with the aviation agent.
 */
@HiltViewModel
class ChatViewModel @Inject constructor(
    private val repository: FlyFunRepository,
    private val routeStateHolder: RouteStateHolder,
    private val modelManager: ModelManager
) : ViewModel() {
    
    // Chat messages
    private val _messages = MutableStateFlow<List<UiChatMessage>>(emptyList())
    val messages: StateFlow<List<UiChatMessage>> = _messages.asStateFlow()
    
    // UI State
    private val _isStreaming = MutableStateFlow(false)
    val isStreaming: StateFlow<Boolean> = _isStreaming.asStateFlow()
    
    private val _currentThinking = MutableStateFlow<String?>(null)
    val currentThinking: StateFlow<String?> = _currentThinking.asStateFlow()
    
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()
    
    // Route visualization from chat results
    private val _routeVisualization = MutableStateFlow<RouteVisualization?>(null)
    val routeVisualization: StateFlow<RouteVisualization?> = _routeVisualization.asStateFlow()
    
    // Suggested follow-up questions
    private val _suggestedQueries = MutableStateFlow<List<SuggestedQuery>>(emptyList())
    val suggestedQueries: StateFlow<List<SuggestedQuery>> = _suggestedQueries.asStateFlow()
    
    // Personas for chat - default to SR22 IFR touring
    private val _personas = MutableStateFlow<List<Persona>>(listOf(
        Persona("ifr_touring_sr22", "IFR touring (SR22)", "IFR capable single engine touring", emptyMap()),
        Persona("vfr_budget_flyer", "VFR budget flyer", "VFR budget conscious pilot", emptyMap()),
        Persona("lunch_stop", "Lunch stop", "Looking for nice airport restaurants", emptyMap()),
        Persona("training_flight", "Training flight", "Training or practice flights", emptyMap())
    ))
    val personas: StateFlow<List<Persona>> = _personas.asStateFlow()
    
    private val _selectedPersonaId = MutableStateFlow("ifr_touring_sr22")
    val selectedPersonaId: StateFlow<String?> = _selectedPersonaId.asStateFlow()
    
    // ========== Offline Mode ==========
    
    /** Expose offline state from repository */
    val isOffline: StateFlow<Boolean> = repository.isOffline
    
    /** Expose force offline toggle from repository */
    val forceOfflineMode: StateFlow<Boolean> = repository.forceOfflineMode
    
    /** Expose model state for UI */
    val modelState: StateFlow<ModelManager.ModelState> = modelManager.modelState
    
    /** Check if offline mode is available */
    fun isOfflineModeAvailable(): Boolean = repository.isOfflineModeAvailable()
    
    /** Toggle force offline mode for testing */
    fun toggleForceOfflineMode() {
        repository.setForceOfflineMode(!repository.forceOfflineMode.value)
    }
    
    /** Set force offline mode */
    fun setForceOfflineMode(enabled: Boolean) {
        repository.setForceOfflineMode(enabled)
    }
    
    /** Get device capability info */
    fun getDeviceCapability(): ModelManager.DeviceCapability {
        return modelManager.checkDeviceCapability()
    }
    
    /** Download the offline model */
    fun downloadModel(url: String) = modelManager.downloadModel(url)
    
    /** Set external model path for testing (e.g., adb pushed model) */
    fun setExternalModelPath(path: String) {
        modelManager.setExternalModelPath(path)
    }
    
    /** Check if model is ready for use */
    fun isModelReady(): Boolean = modelManager.isModelAvailable()
    
    init {
        loadPersonas()
    }
    
    private fun loadPersonas() {
        viewModelScope.launch {
            repository.getGAConfig().onSuccess { config ->
                _personas.value = config.personas
                // Only update selection if API returns a default
                if (config.defaultPersona.isNotEmpty()) {
                    _selectedPersonaId.value = config.defaultPersona
                }
            }
            // On failure, use hardcoded fallback personas
        }
    }
    
    fun selectPersona(personaId: String) {
        _selectedPersonaId.value = personaId
    }
    
    fun sendMessage(content: String) {
        if (content.isBlank() || _isStreaming.value) return
        
        // Clear previous visualization and suggestions when starting new chat
        _routeVisualization.value = null
        _suggestedQueries.value = emptyList()
        
        viewModelScope.launch {
            // Add user message
            val userMessage = UiChatMessage(
                id = UUID.randomUUID().toString(),
                role = Role.USER,
                content = content
            )
            _messages.update { it + userMessage }
            
            // Create assistant message placeholder
            val assistantMessageId = UUID.randomUUID().toString()
            val assistantMessage = UiChatMessage(
                id = assistantMessageId,
                role = Role.ASSISTANT,
                content = "",
                isStreaming = true
            )
            _messages.update { it + assistantMessage }
            
            _isStreaming.value = true
            _error.value = null
            
            // Build request with all messages (history + current)
            val allMessages = _messages.value
                .dropLast(1) // Exclude the assistant placeholder we just added
                .map { ChatMessage(role = it.role.value, content = it.content) }
            
            val request = ChatRequest(messages = allMessages, personaId = _selectedPersonaId.value)
            
            // Stream response
            var accumulatedContent = StringBuilder()
            
            repository.streamChat(request)
                .catch { e ->
                    _error.value = e.message ?: "Failed to get response"
                    _isStreaming.value = false
                    updateAssistantMessage(assistantMessageId, "Sorry, an error occurred. Please try again.", false)
                }
                .collect { event ->
                    when (event) {
                        is ChatStreamEvent.TokenEvent -> {
                            accumulatedContent.append(event.token)
                            updateAssistantMessage(assistantMessageId, accumulatedContent.toString(), true)
                        }
                        is ChatStreamEvent.ThinkingEvent -> {
                            _currentThinking.value = event.content
                        }
                        is ChatStreamEvent.ToolCallEvent -> {
                            // Show tool usage in the chat message with clear formatting
                            val toolCall = event.toolCall
                            val toolInfo = buildString {
                                appendLine("---")
                                appendLine("**🔧 Tool: ${toolCall.name}**")
                                if (!toolCall.args.isNullOrEmpty()) {
                                    appendLine("*Arguments:* ${toolCall.args.entries.joinToString { "${it.key}=${it.value}" }}")
                                }
                                if (!toolCall.result.isNullOrBlank()) {
                                    appendLine()
                                    appendLine("*Result Preview:*")
                                    appendLine("```")
                                    appendLine(toolCall.result)
                                    appendLine("```")
                                }
                                appendLine("---")
                                appendLine()
                                appendLine("**📝 Answer:**")
                                appendLine()
                            }
                            accumulatedContent.append(toolInfo)
                            updateAssistantMessage(assistantMessageId, accumulatedContent.toString(), true)
                        }
                        is ChatStreamEvent.UiPayloadEvent -> {
                            // Process visualization payload for map display
                            processVisualization(event.payload)
                            // Extract suggested queries if present
                            event.payload.suggestedQueries?.let { queries ->
                                if (queries.isNotEmpty()) {
                                    _suggestedQueries.value = queries
                                }
                            }
                        }
                        is ChatStreamEvent.FinalAnswerEvent -> {
                            updateAssistantMessage(assistantMessageId, event.response, false)
                            _isStreaming.value = false
                            _currentThinking.value = null
                        }
                        is ChatStreamEvent.ErrorEvent -> {
                            _error.value = event.message
                            _isStreaming.value = false
                            updateAssistantMessage(assistantMessageId, "Error: ${event.message}", false)
                        }
                        is ChatStreamEvent.DoneEvent -> {
                            _isStreaming.value = false
                            _currentThinking.value = null
                            // Finalize with accumulated content if no final answer was received
                            if (accumulatedContent.isNotEmpty()) {
                                updateAssistantMessage(assistantMessageId, accumulatedContent.toString(), false)
                            }
                        }
                    }
                }
        }
    }
    
    private fun processVisualization(payload: VisualizationPayload) {
        android.util.Log.d("ChatVM", "processVisualization: kind=${payload.kind}, mcpRaw=${payload.mcpRaw != null}")
        
        // Use mcpRaw.airports (raw tool output) as primary source, fallback to root airports
        // This ensures we show all airports returned by the tool (e.g. "find airports near route")
        val markerList = payload.mcpRaw?.airports ?: payload.airports ?: emptyList()
        
        if (markerList.size < 2) {
            android.util.Log.w("ChatVM", "Not enough airports for route: ${markerList.size}")
            return
        }
        
        // First airport is departure, second is destination (sorted by enroute_distance)
        val fromAirportMarker = markerList.first()
        val toAirportMarker = markerList.find { it.enrouteDistanceNm != null && it.enrouteDistanceNm > 0 }
            ?: markerList[1]
        
        val fromIcao = fromAirportMarker.ident ?: fromAirportMarker.icao ?: "DEP"
        val toIcao = toAirportMarker.ident ?: toAirportMarker.icao ?: "ARR"
        
        val fromLat = fromAirportMarker.latitude ?: return
        val fromLon = fromAirportMarker.longitude ?: return
        val toLat = toAirportMarker.latitude ?: return
        val toLon = toAirportMarker.longitude ?: return
        
        android.util.Log.d("ChatVM", "Route: $fromIcao ($fromLat,$fromLon) -> $toIcao ($toLat,$toLon)")
        
        // Extract highlighted airports from the chat payload (these are what the LLM specifically mentioned)
        val highlightedAirports = markerList.mapNotNull { it.ident ?: it.icao }
        
        // Launch coroutine to fetch full airport list from backend API
        viewModelScope.launch {
            android.util.Log.d("ChatVM", "Fetching full route details for $fromIcao -> $toIcao")
            val routeResponseResult = repository.searchAirportsNearRoute(listOf(fromIcao, toIcao))
            
            val finalAirports = routeResponseResult.getOrNull()?.airports?.map { it.airport }
            
            val airportsToDisplay = if (finalAirports != null && finalAirports.isNotEmpty()) {
                android.util.Log.d("ChatVM", "Using ${finalAirports.size} airports from API search")
                finalAirports
            } else {
                android.util.Log.w("ChatVM", "API search failed or empty, falling back to chat payload")
                // Fallback to mapping MarkerData to Airport
                markerList.mapNotNull { marker ->
                    if (marker.latitude == null || marker.longitude == null) return@mapNotNull null
                    val icao = marker.ident ?: marker.icao ?: return@mapNotNull null
                    
                    Airport(
                        icao = icao,
                        name = marker.name,
                        country = marker.country,
                        latitude = marker.latitude,
                        longitude = marker.longitude,
                        pointOfEntry = marker.pointOfEntry,
                        hasProcedures = marker.hasProcedures ?: false,
                        hasHardRunway = marker.hasHardRunway ?: false,
                        hasRunways = true
                    )
                }
            }
            
            if (airportsToDisplay.isEmpty()) return@launch
            
            val routeViz = RouteVisualization(
                fromLat = fromLat,
                fromLon = fromLon,
                toLat = toLat,
                toLon = toLon,
                fromIcao = fromIcao,
                toIcao = toIcao,
                highlightedAirports = highlightedAirports,
                airports = airportsToDisplay
            )
            
            android.util.Log.d("ChatVM", "RouteVisualization ready with ${airportsToDisplay.size} airports")
            _routeVisualization.value = routeViz
            routeStateHolder.setRouteVisualization(routeViz)
        }
    }
    
    private fun updateAssistantMessage(id: String, content: String, isStreaming: Boolean) {
        _messages.update { messages ->
            messages.map { msg ->
                if (msg.id == id) msg.copy(content = content, isStreaming = isStreaming)
                else msg
            }
        }
    }
    
    fun clearError() {
        _error.value = null
    }
    
    fun clearChat() {
        _messages.value = emptyList()
        _currentThinking.value = null
        _error.value = null
        _routeVisualization.value = null
        _suggestedQueries.value = emptyList()
        routeStateHolder.setRouteVisualization(null)
    }
    
    fun clearRouteVisualization() {
        _routeVisualization.value = null
    }
}

data class UiChatMessage(
    val id: String,
    val role: Role,
    val content: String,
    val isStreaming: Boolean = false,
    val toolCalls: List<ToolCall>? = null
)

enum class Role(val value: String) {
    USER("user"),
    ASSISTANT("assistant")
}
