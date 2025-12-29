package me.zhaoqian.flyfun.di

import android.content.Context
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import me.zhaoqian.flyfun.offline.LocalInferenceEngine
import me.zhaoqian.flyfun.offline.LocalToolDispatcher
import me.zhaoqian.flyfun.offline.LiteRtLmInferenceEngine
import me.zhaoqian.flyfun.offline.MediaPipeInferenceEngine
import me.zhaoqian.flyfun.offline.ModelManager
import me.zhaoqian.flyfun.offline.OfflineChatClient
import okhttp3.OkHttpClient
import javax.inject.Singleton

/**
 * Hilt module for offline mode dependencies.
 */
@Module
@InstallIn(SingletonComponent::class)
object OfflineModule {
    
    @Provides
    @Singleton
    fun provideLocalInferenceEngine(): LocalInferenceEngine {
        return LocalInferenceEngine()
    }
    
    @Provides
    @Singleton
    fun provideMediaPipeInferenceEngine(
        @ApplicationContext context: Context
    ): MediaPipeInferenceEngine {
        return MediaPipeInferenceEngine(context)
    }
    
    @Provides
    @Singleton
    fun provideLiteRtLmInferenceEngine(
        @ApplicationContext context: Context
    ): LiteRtLmInferenceEngine {
        return LiteRtLmInferenceEngine(context)
    }
    
    @Provides
    @Singleton
    fun provideModelManager(
        @ApplicationContext context: Context,
        okHttpClient: OkHttpClient
    ): ModelManager {
        return ModelManager(context, okHttpClient)
    }
    
    @Provides
    @Singleton
    fun provideLocalToolDispatcher(
        @ApplicationContext context: Context
    ): LocalToolDispatcher {
        return LocalToolDispatcher(context)
    }
    
    @Provides
    @Singleton
    fun provideOfflineChatClient(
        liteRtLmEngine: LiteRtLmInferenceEngine,
        mediaPipeEngine: MediaPipeInferenceEngine,
        toolDispatcher: LocalToolDispatcher,
        modelManager: ModelManager
    ): OfflineChatClient {
        return OfflineChatClient(liteRtLmEngine, mediaPipeEngine, toolDispatcher, modelManager)
    }
}
