package me.zhaoqian.flyfun.data.api;

import kotlinx.coroutines.Dispatchers;
import kotlinx.coroutines.flow.Flow;
import me.zhaoqian.flyfun.data.models.ChatRequest;
import me.zhaoqian.flyfun.data.models.ChatStreamEvent;
import me.zhaoqian.flyfun.data.models.ToolCall;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import java.io.BufferedReader;
import javax.inject.Inject;
import javax.inject.Singleton;

/**
 * SSE (Server-Sent Events) client for streaming chat responses.
 */
@javax.inject.Singleton()
@kotlin.Metadata(mv = {1, 9, 0}, k = 1, xi = 48, d1 = {"\u0000<\n\u0002\u0018\u0002\n\u0002\u0010\u0000\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0000\n\u0002\u0010\u000e\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0002\b\u0007\u0018\u0000 \u00142\u00020\u0001:\u0001\u0014B\u0017\b\u0007\u0012\u0006\u0010\u0002\u001a\u00020\u0003\u0012\u0006\u0010\u0004\u001a\u00020\u0005\u00a2\u0006\u0002\u0010\u0006J\u001a\u0010\u0007\u001a\u0004\u0018\u00010\b2\u0006\u0010\t\u001a\u00020\n2\u0006\u0010\u000b\u001a\u00020\nH\u0002J\u0016\u0010\f\u001a\b\u0012\u0004\u0012\u00020\b0\r2\u0006\u0010\u000e\u001a\u00020\u000fH\u0002J\u001c\u0010\u0010\u001a\b\u0012\u0004\u0012\u00020\b0\r2\u0006\u0010\u0011\u001a\u00020\n2\u0006\u0010\u0012\u001a\u00020\u0013R\u000e\u0010\u0004\u001a\u00020\u0005X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u000e\u0010\u0002\u001a\u00020\u0003X\u0082\u0004\u00a2\u0006\u0002\n\u0000\u00a8\u0006\u0015"}, d2 = {"Lme/zhaoqian/flyfun/data/api/ChatStreamingClient;", "", "okHttpClient", "Lokhttp3/OkHttpClient;", "json", "Lkotlinx/serialization/json/Json;", "(Lokhttp3/OkHttpClient;Lkotlinx/serialization/json/Json;)V", "parseEvent", "Lme/zhaoqian/flyfun/data/models/ChatStreamEvent;", "eventName", "", "data", "parseSSEStream", "Lkotlinx/coroutines/flow/Flow;", "reader", "Ljava/io/BufferedReader;", "streamChat", "baseUrl", "request", "Lme/zhaoqian/flyfun/data/models/ChatRequest;", "Companion", "app_debug"})
public final class ChatStreamingClient {
    @org.jetbrains.annotations.NotNull()
    private final okhttp3.OkHttpClient okHttpClient = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.serialization.json.Json json = null;
    @org.jetbrains.annotations.NotNull()
    private static final java.lang.String CHAT_STREAM_ENDPOINT = "/aviation-agent/chat/stream";
    @org.jetbrains.annotations.NotNull()
    public static final me.zhaoqian.flyfun.data.api.ChatStreamingClient.Companion Companion = null;
    
    @javax.inject.Inject()
    public ChatStreamingClient(@org.jetbrains.annotations.NotNull()
    okhttp3.OkHttpClient okHttpClient, @org.jetbrains.annotations.NotNull()
    kotlinx.serialization.json.Json json) {
        super();
    }
    
    @org.jetbrains.annotations.NotNull()
    public final kotlinx.coroutines.flow.Flow<me.zhaoqian.flyfun.data.models.ChatStreamEvent> streamChat(@org.jetbrains.annotations.NotNull()
    java.lang.String baseUrl, @org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.data.models.ChatRequest request) {
        return null;
    }
    
    private final kotlinx.coroutines.flow.Flow<me.zhaoqian.flyfun.data.models.ChatStreamEvent> parseSSEStream(java.io.BufferedReader reader) {
        return null;
    }
    
    private final me.zhaoqian.flyfun.data.models.ChatStreamEvent parseEvent(java.lang.String eventName, java.lang.String data) {
        return null;
    }
    
    @kotlin.Metadata(mv = {1, 9, 0}, k = 1, xi = 48, d1 = {"\u0000\u0012\n\u0002\u0018\u0002\n\u0002\u0010\u0000\n\u0002\b\u0002\n\u0002\u0010\u000e\n\u0000\b\u0086\u0003\u0018\u00002\u00020\u0001B\u0007\b\u0002\u00a2\u0006\u0002\u0010\u0002R\u000e\u0010\u0003\u001a\u00020\u0004X\u0082T\u00a2\u0006\u0002\n\u0000\u00a8\u0006\u0005"}, d2 = {"Lme/zhaoqian/flyfun/data/api/ChatStreamingClient$Companion;", "", "()V", "CHAT_STREAM_ENDPOINT", "", "app_debug"})
    public static final class Companion {
        
        private Companion() {
            super();
        }
    }
}