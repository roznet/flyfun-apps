package me.zhaoqian.flyfun.di;

import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.Preconditions;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;
import kotlinx.serialization.json.Json;
import me.zhaoqian.flyfun.data.api.ChatStreamingClient;
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
public final class NetworkModule_ProvideChatStreamingClientFactory implements Factory<ChatStreamingClient> {
  private final Provider<OkHttpClient> okHttpClientProvider;

  private final Provider<Json> jsonProvider;

  public NetworkModule_ProvideChatStreamingClientFactory(
      Provider<OkHttpClient> okHttpClientProvider, Provider<Json> jsonProvider) {
    this.okHttpClientProvider = okHttpClientProvider;
    this.jsonProvider = jsonProvider;
  }

  @Override
  public ChatStreamingClient get() {
    return provideChatStreamingClient(okHttpClientProvider.get(), jsonProvider.get());
  }

  public static NetworkModule_ProvideChatStreamingClientFactory create(
      Provider<OkHttpClient> okHttpClientProvider, Provider<Json> jsonProvider) {
    return new NetworkModule_ProvideChatStreamingClientFactory(okHttpClientProvider, jsonProvider);
  }

  public static ChatStreamingClient provideChatStreamingClient(OkHttpClient okHttpClient,
      Json json) {
    return Preconditions.checkNotNullFromProvides(NetworkModule.INSTANCE.provideChatStreamingClient(okHttpClient, json));
  }
}
