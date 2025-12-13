package me.zhaoqian.flyfun.data.repository;

import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;
import me.zhaoqian.flyfun.data.api.ChatStreamingClient;
import me.zhaoqian.flyfun.data.api.FlyFunApiService;

@ScopeMetadata("javax.inject.Singleton")
@QualifierMetadata("javax.inject.Named")
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
public final class FlyFunRepository_Factory implements Factory<FlyFunRepository> {
  private final Provider<FlyFunApiService> apiServiceProvider;

  private final Provider<ChatStreamingClient> chatStreamingClientProvider;

  private final Provider<String> baseUrlProvider;

  public FlyFunRepository_Factory(Provider<FlyFunApiService> apiServiceProvider,
      Provider<ChatStreamingClient> chatStreamingClientProvider, Provider<String> baseUrlProvider) {
    this.apiServiceProvider = apiServiceProvider;
    this.chatStreamingClientProvider = chatStreamingClientProvider;
    this.baseUrlProvider = baseUrlProvider;
  }

  @Override
  public FlyFunRepository get() {
    return newInstance(apiServiceProvider.get(), chatStreamingClientProvider.get(), baseUrlProvider.get());
  }

  public static FlyFunRepository_Factory create(Provider<FlyFunApiService> apiServiceProvider,
      Provider<ChatStreamingClient> chatStreamingClientProvider, Provider<String> baseUrlProvider) {
    return new FlyFunRepository_Factory(apiServiceProvider, chatStreamingClientProvider, baseUrlProvider);
  }

  public static FlyFunRepository newInstance(FlyFunApiService apiService,
      ChatStreamingClient chatStreamingClient, String baseUrl) {
    return new FlyFunRepository(apiService, chatStreamingClient, baseUrl);
  }
}
