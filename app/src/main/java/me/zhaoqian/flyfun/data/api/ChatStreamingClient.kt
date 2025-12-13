package me.zhaoqian.flyfun.data.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.serialization.json.Json
import me.zhaoqian.flyfun.data.models.ChatRequest
import me.zhaoqian.flyfun.data.models.ChatStreamEvent
import me.zhaoqian.flyfun.data.models.ToolCall
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.BufferedReader
import javax.inject.Inject
import javax.inject.Singleton

/**
 * SSE (Server-Sent Events) client for streaming chat responses.
 */
@Singleton
class ChatStreamingClient @Inject constructor(
    private val okHttpClient: OkHttpClient,
    private val json: Json
) {
    companion object {
        private const val CHAT_STREAM_ENDPOINT = "/aviation-agent/chat/stream"
    }
    
    fun streamChat(baseUrl: String, request: ChatRequest): Flow<ChatStreamEvent> = flow {
        val requestBody = json.encodeToString(ChatRequest.serializer(), request)
            .toRequestBody("application/json".toMediaType())
        
        val httpRequest = Request.Builder()
            .url("$baseUrl$CHAT_STREAM_ENDPOINT")
            .post(requestBody)
            .header("Accept", "text/event-stream")
            .header("Cache-Control", "no-cache")
            .build()
        
        okHttpClient.newCall(httpRequest).execute().use { response ->
            if (!response.isSuccessful) {
                emit(ChatStreamEvent.ErrorEvent("HTTP ${response.code}: ${response.message}"))
                return@use
            }
            
            val reader = response.body?.charStream()?.buffered() ?: return@use
            parseSSEStream(reader).collect { event ->
                emit(event)
            }
        }
    }.flowOn(Dispatchers.IO)
    
    private fun parseSSEStream(reader: BufferedReader): Flow<ChatStreamEvent> = flow {
        var currentEvent: String? = null
        var currentData = StringBuilder()
        
        reader.lineSequence().forEach { line ->
            when {
                line.startsWith("event:") -> {
                    currentEvent = line.removePrefix("event:").trim()
                }
                line.startsWith("data:") -> {
                    currentData.append(line.removePrefix("data:").trim())
                }
                line.isEmpty() -> {
                    // End of event, process it
                    if (currentEvent != null && currentData.isNotEmpty()) {
                        val event = parseEvent(currentEvent!!, currentData.toString())
                        if (event != null) {
                            emit(event)
                        }
                    }
                    currentEvent = null
                    currentData = StringBuilder()
                }
            }
        }
    }
    
    private fun parseEvent(eventName: String, data: String): ChatStreamEvent? {
        return try {
            when (eventName) {
                "token" -> {
                    val parsed = json.decodeFromString<Map<String, String>>(data)
                    ChatStreamEvent.TokenEvent(parsed["token"] ?: "")
                }
                "thinking" -> {
                    val parsed = json.decodeFromString<Map<String, String>>(data)
                    ChatStreamEvent.ThinkingEvent(parsed["content"] ?: "")
                }
                "tool_call" -> {
                    val toolCall = json.decodeFromString<ToolCall>(data)
                    ChatStreamEvent.ToolCallEvent(toolCall)
                }
                "final_answer" -> {
                    val parsed = json.decodeFromString<Map<String, String>>(data)
                    ChatStreamEvent.FinalAnswerEvent(parsed["response"] ?: "")
                }
                "done" -> ChatStreamEvent.DoneEvent
                "error" -> {
                    val parsed = json.decodeFromString<Map<String, String>>(data)
                    ChatStreamEvent.ErrorEvent(parsed["message"] ?: "Unknown error")
                }
                else -> null
            }
        } catch (e: Exception) {
            ChatStreamEvent.ErrorEvent("Failed to parse event: ${e.message}")
        }
    }
}
