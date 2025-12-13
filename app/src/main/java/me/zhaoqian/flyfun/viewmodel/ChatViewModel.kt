package me.zhaoqian.flyfun.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import me.zhaoqian.flyfun.data.models.*
import me.zhaoqian.flyfun.data.repository.FlyFunRepository
import java.util.UUID
import javax.inject.Inject

/**
 * ViewModel for the Chat screen - manages conversation with the aviation agent.
 */
@HiltViewModel
class ChatViewModel @Inject constructor(
    private val repository: FlyFunRepository
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
    
    // Session ID for conversation continuity
    private val sessionId = UUID.randomUUID().toString()
    
    fun sendMessage(content: String) {
        if (content.isBlank() || _isStreaming.value) return
        
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
            
            // Build request
            val history = _messages.value
                .dropLast(2) // Exclude the messages we just added
                .map { ChatMessage(role = it.role.value, content = it.content) }
            
            val request = ChatRequest(
                message = content,
                history = history,
                sessionId = sessionId
            )
            
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
