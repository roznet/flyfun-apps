package me.zhaoqian.flyfun.data.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.serialization.json.Json
import me.zhaoqian.flyfun.data.models.ChatRequest
import me.zhaoqian.flyfun.data.models.ChatStreamEvent
import me.zhaoqian.flyfun.data.models.ToolCall
import me.zhaoqian.flyfun.data.models.UiPayloadWrapper
import me.zhaoqian.flyfun.data.models.VisualizationPayload
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
        private const val CHAT_STREAM_ENDPOINT = "api/aviation-agent/chat/stream"
    }
    
    fun streamChat(baseUrl: String, request: ChatRequest): Flow<ChatStreamEvent> = flow {
        val requestBody = json.encodeToString(ChatRequest.serializer(), request)
            .toRequestBody("application/json".toMediaType())
        
        val httpRequest = Request.Builder()
            .url("$baseUrl$CHAT_STREAM_ENDPOINT")
            .post(requestBody)
            .header("Accept", "text/event-stream")
            .header("Cache-Control", "no-cache")
            .header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
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
                "message" -> {
                    // Streaming content tokens: {"content": "token"}
                    val parsed = json.decodeFromString<Map<String, String>>(data)
                    ChatStreamEvent.TokenEvent(parsed["content"] ?: "")
                }
                "thinking" -> {
                    val parsed = json.decodeFromString<Map<String, String>>(data)
                    ChatStreamEvent.ThinkingEvent(parsed["content"] ?: "")
                }
                "thinking_done" -> {
                    // Ignore - thinking phase complete
                    null
                }
                "ui_payload" -> {
                    // Parse visualization payload for route/markers display
                    // Data might be:
                    // 1. { "ui_payload": ... } (Wrapper)
                    // 2. { "state": { "ui_payload": ... } } (State object)
                    // 3. { "kind": "route", "mcp_raw": ... } (Direct payload)
                    try {
                        android.util.Log.d("ChatStream", "ui_payload event received: $data")
                        val rootObj = json.decodeFromString<kotlinx.serialization.json.JsonObject>(data)
                        
                        // Try to find ui_payload at root or inside state
                        val uiPayloadJson = rootObj["ui_payload"] 
                            ?: rootObj["state"]?.let { 
                                if (it is kotlinx.serialization.json.JsonObject) it["ui_payload"] else null 
                            }
                        
                        val payload = if (uiPayloadJson != null) {
                            json.decodeFromString<VisualizationPayload>(uiPayloadJson.toString())
                        } else {
                            // Fallback: Assume the root object is the payload itself
                            android.util.Log.d("ChatStream", "No nested ui_payload found, attempting direct parse")
                            json.decodeFromString<VisualizationPayload>(data)
                        }
                        
                        android.util.Log.d("ChatStream", "ui_payload parsed: kind=${payload.kind}, airports=${payload.mcpRaw?.airports?.size}")
                        ChatStreamEvent.UiPayloadEvent(payload)

                    } catch (e: Exception) {
                        android.util.Log.e("ChatStream", "ui_payload parse error: ${e.message}", e)
                        null
                    }
                }
                "final_answer" -> {
                    // Final answer has nested structure: {"state": {"final_answer": "..."}}
                    val parsed = json.decodeFromString<kotlinx.serialization.json.JsonObject>(data)
                    val state = parsed["state"]?.let { 
                        json.decodeFromString<kotlinx.serialization.json.JsonObject>(it.toString()) 
                    }
                    val finalAnswer = state?.get("final_answer")?.let {
                        it.toString().trim('"').replace("\\n", "\n").replace("\\\"", "\"")
                    } ?: ""
                    ChatStreamEvent.FinalAnswerEvent(finalAnswer)
                }
                "done" -> ChatStreamEvent.DoneEvent
                "error" -> {
                    val parsed = json.decodeFromString<Map<String, String>>(data)
                    ChatStreamEvent.ErrorEvent(parsed["message"] ?: parsed["error"] ?: "Unknown error")
                }
                else -> null
            }
        } catch (e: Exception) {
            // Log but don't fail on parse errors for unknown event types
            null
        }
    }
}
