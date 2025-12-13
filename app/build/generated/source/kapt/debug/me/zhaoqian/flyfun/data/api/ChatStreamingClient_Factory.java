package me.zhaoqian.flyfun.data.api;

import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;
import kotlinx.serialization.json.Json;
import okhttp3.OkHttpClient;

@ScopeMetadata("javax.inject.Singleton")
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava"
})
public final class ChatStreamingClient_Factory implements Factory<ChatStreamingClient> {
  private final Provider<OkHttpClient> okHttpClientProvider;

  private final Provider<Json> jsonProvider;

  public ChatStreamingClient_Factory(Provider<OkHttpClient> okHttpClientProvider,
      Provider<Json> jsonProvider) {
    this.okHttpClientProvider = okHttpClientProvider;
    this.jsonProvider = jsonProvider;
  }

  @Override
  public ChatStreamingClient get() {
    return newInstance(okHttpClientProvider.get(), jsonProvider.get());
  }

  public static ChatStreamingClient_Factory create(Provider<OkHttpClient> okHttpClientProvider,
      Provider<Json> jsonProvider) {
    return new ChatStreamingClient_Factory(okHttpClientProvider, jsonProvider);
  }

  public static ChatStreamingClient newInstance(OkHttpClient okHttpClient, Json json) {
    return new ChatStreamingClient(okHttpClient, json);
  }
}
