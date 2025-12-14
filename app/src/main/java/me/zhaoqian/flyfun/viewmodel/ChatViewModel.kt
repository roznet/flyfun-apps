package me.zhaoqian.flyfun.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import me.zhaoqian.flyfun.data.models.*
import me.zhaoqian.flyfun.data.repository.FlyFunRepository
import me.zhaoqian.flyfun.data.repository.RouteStateHolder
import java.util.UUID
import javax.inject.Inject

/**
 * ViewModel for the Chat screen - manages conversation with the aviation agent.
 */
@HiltViewModel
class ChatViewModel @Inject constructor(
    private val repository: FlyFunRepository,
    private val routeStateHolder: RouteStateHolder
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
    
    
    fun sendMessage(content: String) {
        if (content.isBlank() || _isStreaming.value) return
        
        // Clear previous visualization when starting new chat
        _routeVisualization.value = null
        
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
            
            val request = ChatRequest(messages = allMessages)
            
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
                            // Could show tool usage in UI
                        }
                        is ChatStreamEvent.UiPayloadEvent -> {
                            // Process visualization payload for map display
                            processVisualization(event.payload)
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
        val fromAirport = markerList.first()
        val toAirport = markerList.find { it.enrouteDistanceNm != null && it.enrouteDistanceNm > 0 }
            ?: markerList[1]
        
        val fromLat = fromAirport.latitude ?: return
        val fromLon = fromAirport.longitude ?: return
        val toLat = toAirport.latitude ?: return
        val toLon = toAirport.longitude ?: return
        
        android.util.Log.d("ChatVM", "Route: ${fromAirport.ident} ($fromLat,$fromLon) -> ${toAirport.ident} ($toLat,$toLon)")
        
        // Extract all airport ICAOs for highlighting
        val highlightedAirports = markerList.mapNotNull { it.ident ?: it.icao }
        
        // Map MarkerData to Airport objects
        val mappedAirports = markerList.mapNotNull { marker ->
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
                hasRunways = true // Assumption for visualized airports
            )
        }
        
        val routeViz = RouteVisualization(
            fromLat = fromLat,
            fromLon = fromLon,
            toLat = toLat,
            toLon = toLon,
            fromIcao = fromAirport.ident ?: "DEP",
            toIcao = toAirport.ident ?: "ARR",
            highlightedAirports = highlightedAirports,
            airports = mappedAirports
        )
        
        android.util.Log.d("ChatVM", "RouteVisualization created with ${mappedAirports.size} airports")
        _routeVisualization.value = routeViz
        // Also publish to shared state for MapViewModel
        routeStateHolder.setRouteVisualization(routeViz)
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
