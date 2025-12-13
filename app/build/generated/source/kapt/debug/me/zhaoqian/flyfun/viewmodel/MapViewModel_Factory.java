package me.zhaoqian.flyfun.viewmodel;

import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;
import me.zhaoqian.flyfun.data.repository.FlyFunRepository;

@ScopeMetadata
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
public final class MapViewModel_Factory implements Factory<MapViewModel> {
  private final Provider<FlyFunRepository> repositoryProvider;

  public MapViewModel_Factory(Provider<FlyFunRepository> repositoryProvider) {
    this.repositoryProvider = repositoryProvider;
  }

  @Override
  public MapViewModel get() {
    return newInstance(repositoryProvider.get());
  }

  public static MapViewModel_Factory create(Provider<FlyFunRepository> repositoryProvider) {
    return new MapViewModel_Factory(repositoryProvider);
  }

  public static MapViewModel newInstance(FlyFunRepository repository) {
    return new MapViewModel(repository);
  }
}
