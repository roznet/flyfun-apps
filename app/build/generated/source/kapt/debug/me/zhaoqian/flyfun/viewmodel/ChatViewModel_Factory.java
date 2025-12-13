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
public final class ChatViewModel_Factory implements Factory<ChatViewModel> {
  private final Provider<FlyFunRepository> repositoryProvider;

  public ChatViewModel_Factory(Provider<FlyFunRepository> repositoryProvider) {
    this.repositoryProvider = repositoryProvider;
  }

  @Override
  public ChatViewModel get() {
    return newInstance(repositoryProvider.get());
  }

  public static ChatViewModel_Factory create(Provider<FlyFunRepository> repositoryProvider) {
    return new ChatViewModel_Factory(repositoryProvider);
  }

  public static ChatViewModel newInstance(FlyFunRepository repository) {
    return new ChatViewModel(repository);
  }
}
