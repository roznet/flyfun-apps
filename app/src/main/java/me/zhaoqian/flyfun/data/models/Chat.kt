package me.zhaoqian.flyfun.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Chat/Aviation Agent data models.
 */

@Serializable
data class ChatRequest(
    val message: String,
    val history: List<ChatMessage> = emptyList(),
    @SerialName("session_id") val sessionId: String? = null
)

@Serializable
data class ChatMessage(
    val role: String, // "user" or "assistant"
    val content: String
)

@Serializable
data class ChatResponse(
    val response: String,
    @SerialName("tool_calls") val toolCalls: List<ToolCall>? = null,
    val thinking: String? = null
)

@Serializable
data class ToolCall(
    val name: String,
    val args: Map<String, String>? = null,
    val result: String? = null
)

/**
 * SSE Event types for streaming chat
 */
sealed class ChatStreamEvent {
    data class TokenEvent(val token: String) : ChatStreamEvent()
    data class ThinkingEvent(val content: String) : ChatStreamEvent()
    data class ToolCallEvent(val toolCall: ToolCall) : ChatStreamEvent()
    data class FinalAnswerEvent(val response: String) : ChatStreamEvent()
    data class ErrorEvent(val message: String) : ChatStreamEvent()
    object DoneEvent : ChatStreamEvent()
}
