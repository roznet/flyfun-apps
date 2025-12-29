package me.zhaoqian.flyfun.offline

import android.content.Context
import android.util.Log
import com.google.mediapipe.tasks.genai.llminference.LlmInference
import com.google.mediapipe.tasks.genai.llminference.LlmInferenceSession
import com.google.mediapipe.tasks.genai.llminference.LlmInferenceSession.LlmInferenceSessionOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * MediaPipe-based inference engine for on-device LLM execution.
 * 
 * Uses LlmInferenceSession-based API matching parttimenerd/local-android-ai.
 * Configured for Gemma 3n E2B model with CPU backend for stability.
 */
@Singleton
class MediaPipeInferenceEngine @Inject constructor(
    private val context: Context
) {
    
    companion object {
        private const val TAG = "MediaPipeInference"
        
        // Model configuration matching Gemma 3n settings from local-android-ai
        const val DEFAULT_MAX_TOKENS = 4096
        const val GEMMA_3N_TEMPERATURE = 1.0f
        const val GEMMA_3N_TOP_K = 64
        const val GEMMA_3N_TOP_P = 0.95f
    }
    
    // MediaPipe LLM Inference instances
    private var llmInference: LlmInference? = null
    private var llmSession: LlmInferenceSession? = null
    private var currentModelPath: String? = null
    
    /**
     * Check if a model is loaded and ready for inference.
     */
    fun isLoaded(): Boolean = llmInference != null && llmSession != null
    
    /**
     * Load a model from the given path.
     * 
     * @param modelPath Absolute path to the .task model file
     * @return Result indicating success or failure
     */
    suspend fun loadModel(modelPath: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val modelFile = File(modelPath)
            if (!modelFile.exists()) {
                return@withContext Result.failure(
                    IllegalArgumentException("Model file not found: $modelPath")
                )
            }
            
            val fileSizeMB = modelFile.length() / 1024 / 1024
            Log.i(TAG, "Loading model: $modelPath ($fileSizeMB MB)")
            
            // Unload previous model if any
            closeResources()
            
            // Try GPU first, fall back to CPU if it fails
            val (inference, usedBackend) = tryCreateInferenceWithFallback(modelPath)
            llmInference = inference
            
            // Create inference session
            createSession()
            
            currentModelPath = modelPath
            Log.i(TAG, "Model loaded successfully with MediaPipe $usedBackend backend")
            Result.success(Unit)
            
        } catch (e: OutOfMemoryError) {
            Log.e(TAG, "Out of memory while loading model: ${e.message}", e)
            Result.failure(IllegalStateException("Out of memory. Try restarting the app.", e))
        } catch (e: Exception) {
            Log.e(TAG, "Error loading model: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * Try to create inference engine. Uses GPU for .litertlm models, CPU for .task models.
     * Returns the inference engine and the backend that was successfully used.
     */
    private fun tryCreateInferenceWithFallback(modelPath: String): Pair<LlmInference, String> {
        Log.d(TAG, "Creating LLM inference engine...")
        val engineStartTime = System.currentTimeMillis()
        
        // Check model format - .litertlm supports GPU, .task is CPU-only
        val isGpuCompatible = modelPath.endsWith(".litertlm")
        
        if (isGpuCompatible) {
            // Try GPU first for .litertlm models
            try {
                Log.i(TAG, "Attempting GPU backend (.litertlm model)...")
                val gpuOptions = LlmInference.LlmInferenceOptions.builder()
                    .setModelPath(modelPath)
                    .setMaxTokens(DEFAULT_MAX_TOKENS)
                    .setMaxNumImages(1)
                    .setPreferredBackend(LlmInference.Backend.GPU)
                    .build()
                
                val inference = LlmInference.createFromOptions(context, gpuOptions)
                val engineTime = System.currentTimeMillis() - engineStartTime
                Log.i(TAG, "GPU backend initialized successfully in ${engineTime}ms")
                return Pair(inference, "GPU")
                
            } catch (e: Exception) {
                Log.w(TAG, "GPU backend failed: ${e.message}, falling back to CPU")
            }
        }
        
        // Use CPU for .task models or as fallback
        try {
            val reason = if (isGpuCompatible) "(fallback)" else "(.task model)"
            Log.i(TAG, "Using CPU backend $reason...")
            val cpuOptions = LlmInference.LlmInferenceOptions.builder()
                .setModelPath(modelPath)
                .setMaxTokens(DEFAULT_MAX_TOKENS)
                .setMaxNumImages(1)
                .setPreferredBackend(LlmInference.Backend.CPU)
                .build()
            
            val inference = LlmInference.createFromOptions(context, cpuOptions)
            val engineTime = System.currentTimeMillis() - engineStartTime
            Log.i(TAG, "CPU backend initialized successfully in ${engineTime}ms")
            return Pair(inference, "CPU")
            
        } catch (e: Exception) {
            Log.e(TAG, "CPU backend failed: ${e.message}", e)
            throw e
        }
    }
    
    /**
     * Create inference session with Gemma 3n parameters.
     */
    private fun createSession() {
        val inference = llmInference
            ?: throw IllegalStateException("LLM inference engine not initialized")
        
        Log.d(TAG, "Creating inference session...")
        val sessionStartTime = System.currentTimeMillis()
        
        val sessionOptions = LlmInferenceSessionOptions.builder()
            .setTemperature(GEMMA_3N_TEMPERATURE)
            .setTopK(GEMMA_3N_TOP_K)
            .setTopP(GEMMA_3N_TOP_P)
            .build()
        
        Log.d(TAG, "Session options: temp=$GEMMA_3N_TEMPERATURE, topK=$GEMMA_3N_TOP_K, topP=$GEMMA_3N_TOP_P")
        
        llmSession = LlmInferenceSession.createFromOptions(inference, sessionOptions)
        
        val sessionTime = System.currentTimeMillis() - sessionStartTime
        Log.i(TAG, "Inference session created in ${sessionTime}ms")
    }
    
    /**
     * Generate text from a prompt with streaming output.
     * Uses LlmInferenceSession-based generation matching local-android-ai.
     * 
     * @param prompt The input prompt
     * @param maxTokens Maximum tokens to generate
     * @return Flow of generated tokens
     */
    fun generateStream(
        prompt: String,
        maxTokens: Int = DEFAULT_MAX_TOKENS
    ): Flow<String> = flow {
        val session = llmSession
        
        if (session == null) {
            throw IllegalStateException("Model not loaded. Call loadModel() first.")
        }
        
        Log.d(TAG, "Starting generation for prompt (${prompt.length} chars)")
        val startTime = System.currentTimeMillis()
        
        try {
            // Add prompt to session
            session.addQueryChunk(prompt)
            
            // Generate response asynchronously with progress callback
            val fullResponse = StringBuilder()
            
            val future = session.generateResponseAsync { partialResult, isDone ->
                Log.d(TAG, "Progress: isDone=$isDone, partial='${partialResult.take(50)}...'")
            }
            
            // Wait for completion
            val response = future.get()
            
            val inferenceTime = System.currentTimeMillis() - startTime
            Log.i(TAG, "Generation completed in ${inferenceTime}ms, response length: ${response.length}")
            
            // Emit response
            if (response.isNotEmpty()) {
                emit(response)
            }
            
            // Recreate session for next query (session can't be reused after addQueryChunk)
            Log.d(TAG, "Recreating session for next query...")
            llmSession?.close()
            createSession()
            
        } catch (e: Exception) {
            Log.e(TAG, "Generation error: ${e.message}", e)
            throw e
        }
    }.flowOn(Dispatchers.IO)
    
    /**
     * Generate text synchronously (blocking).
     */
    suspend fun generate(
        prompt: String,
        maxTokens: Int = DEFAULT_MAX_TOKENS
    ): Result<String> = withContext(Dispatchers.IO) {
        val session = llmSession
        
        if (session == null) {
            return@withContext Result.failure(
                IllegalStateException("Model not loaded. Call loadModel() first.")
            )
        }
        
        try {
            Log.d(TAG, "Starting sync generation for prompt (${prompt.length} chars)")
            val startTime = System.currentTimeMillis()
            
            session.addQueryChunk(prompt)
            
            val future = session.generateResponseAsync { _, _ -> }
            val response = future.get()
            
            val inferenceTime = System.currentTimeMillis() - startTime
            Log.i(TAG, "Sync generation completed in ${inferenceTime}ms")
            
            // Recreate session for next query
            llmSession?.close()
            createSession()
            
            Result.success(response)
        } catch (e: Exception) {
            Log.e(TAG, "Generation error: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * Reset the inference session.
     */
    suspend fun resetSession() = withContext(Dispatchers.IO) {
        try {
            llmSession?.close()
            createSession()
            Log.d(TAG, "Session reset")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to reset session: ${e.message}", e)
        }
    }
    
    /**
     * Close all resources.
     */
    private fun closeResources() {
        llmSession?.close()
        llmSession = null
        llmInference?.close()
        llmInference = null
    }
    
    /**
     * Unload the current model and free resources.
     */
    fun unload() {
        closeResources()
        currentModelPath = null
        Log.i(TAG, "Model unloaded")
    }
    
    /**
     * Get current model path if loaded.
     */
    fun getCurrentModelPath(): String? = currentModelPath
}
