package me.zhaoqian.flyfun.di;

import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.Preconditions;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;
import me.zhaoqian.flyfun.data.api.FlyFunApiService;
import retrofit2.Retrofit;

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
public final class NetworkModule_ProvideFlyFunApiServiceFactory implements Factory<FlyFunApiService> {
  private final Provider<Retrofit> retrofitProvider;

  public NetworkModule_ProvideFlyFunApiServiceFactory(Provider<Retrofit> retrofitProvider) {
    this.retrofitProvider = retrofitProvider;
  }

  @Override
  public FlyFunApiService get() {
    return provideFlyFunApiService(retrofitProvider.get());
  }

  public static NetworkModule_ProvideFlyFunApiServiceFactory create(
      Provider<Retrofit> retrofitProvider) {
    return new NetworkModule_ProvideFlyFunApiServiceFactory(retrofitProvider);
  }

  public static FlyFunApiService provideFlyFunApiService(Retrofit retrofit) {
    return Preconditions.checkNotNullFromProvides(NetworkModule.INSTANCE.provideFlyFunApiService(retrofit));
  }
}
