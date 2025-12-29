package me.zhaoqian.flyfun.offline

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Local inference engine using llama.cpp for on-device model execution.
 * 
 * This wraps the native llama.cpp library via JNI and provides a Kotlin-friendly
 * Flow-based API for streaming token generation.
 */
@Singleton
class LocalInferenceEngine @Inject constructor() {
    
    companion object {
        private const val TAG = "LocalInferenceEngine"
        
        // Model configuration
        const val DEFAULT_MAX_TOKENS = 512
        const val DEFAULT_TEMPERATURE = 0.7f
        const val DEFAULT_N_GPU_LAYERS = 5  // Minimal GPU offload to work around Adreno Vulkan driver crash
        
        init {
            try {
                // Load Vulkan first to ensure it's in the namespace
                try {
                    System.loadLibrary("vulkan")
                    Log.i(TAG, "Vulkan system library loaded successfully")
                } catch (e: Exception) {
                    Log.w(TAG, "Note: Vulkan system library not found via System.loadLibrary")
                }
                
                // Load OpenCL as well just in case of future fallback
                try {
                    System.loadLibrary("OpenCL")
                    Log.i(TAG, "OpenCL system library loaded successfully")
                } catch (e: Exception) {
                    Log.w(TAG, "Note: OpenCL system library not found")
                }
                
                System.loadLibrary("flyfun_llama")
                Log.i(TAG, "Native library loaded successfully")
            } catch (e: UnsatisfiedLinkError) {
                Log.e(TAG, "Failed to load native library: ${e.message}")
            }
        }
    }
    
    // Track if model is loaded
    private var isInitialized = false
    private var currentModelPath: String? = null
    
    // Native methods - implemented in llama_bridge.cpp
    private external fun nativeInit()
    private external fun nativeLoadModel(modelPath: String, nGpuLayers: Int): Boolean
    private external fun nativeIsLoaded(): Boolean
    private external fun nativeGenerate(
        prompt: String,
        maxTokens: Int,
        temperature: Float,
        callback: TokenCallback
    ): String
    private external fun nativeUnload()
    private external fun nativeCleanup()
    private external fun nativeGetMemoryUsage(): Long
    
    /**
     * Callback interface for receiving tokens during generation.
     * Called from native code via JNI.
     */
    interface TokenCallback {
        fun onToken(token: String)
    }
    
    /**
     * Initialize the llama backend.
     * Should be called once when the app starts.
     */
    fun initialize() {
        if (!isInitialized) {
            try {
                nativeInit()
                isInitialized = true
                Log.i(TAG, "Backend initialized")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to initialize backend: ${e.message}")
            }
        }
    }
    
    /**
     * Load a GGUF model from the given path.
     * 
     * @param modelPath Absolute path to the GGUF model file
     * @param nGpuLayers Number of layers to offload to GPU (0 = CPU only)
     * @return Result indicating success or failure with error message
     */
    suspend fun loadModel(
        modelPath: String,
        nGpuLayers: Int = DEFAULT_N_GPU_LAYERS
    ): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            if (!isInitialized) {
                initialize()
            }
            
            val modelFile = File(modelPath)
            if (!modelFile.exists()) {
                return@withContext Result.failure(IllegalArgumentException("Model file not found: $modelPath"))
            }
            
            Log.i(TAG, "Loading model: $modelPath (${modelFile.length() / 1024 / 1024} MB)")
            
            val success = nativeLoadModel(modelPath, nGpuLayers)
            if (success) {
                currentModelPath = modelPath
                Log.i(TAG, "Model loaded successfully")
                Result.success(Unit)
            } else {
                Result.failure(RuntimeException("Failed to load model"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error loading model: ${e.message}")
            Result.failure(e)
        }
    }
    
    /**
     * Check if a model is currently loaded and ready for inference.
     */
    fun isModelLoaded(): Boolean {
        return try {
            nativeIsLoaded()
        } catch (e: Exception) {
            false
        }
    }
    
    /**
     * Generate text from a prompt with streaming output.
     * 
     * @param prompt The input prompt
     * @param maxTokens Maximum number of tokens to generate
     * @param temperature Sampling temperature (higher = more random)
     * @return Flow emitting tokens as they are generated
     */
    fun generate(
        prompt: String,
        maxTokens: Int = DEFAULT_MAX_TOKENS,
        temperature: Float = DEFAULT_TEMPERATURE
    ): Flow<String> = callbackFlow {
        Log.d(TAG, "Starting generation with prompt length: ${prompt.length}")
        
        if (!isModelLoaded()) {
            close(IllegalStateException("Model not loaded"))
            return@callbackFlow
        }
        
        val callback = object : TokenCallback {
            override fun onToken(token: String) {
                trySend(token)
            }
        }
        
        // Run generation on IO dispatcher
        withContext(Dispatchers.IO) {
            try {
                nativeGenerate(prompt, maxTokens, temperature, callback)
            } catch (e: Exception) {
                Log.e(TAG, "Generation error: ${e.message}")
                close(e)
            }
        }
        
        close()
        
        awaitClose {
            Log.d(TAG, "Generation flow closed")
        }
    }.flowOn(Dispatchers.IO)
    
    /**
     * Generate a complete response (non-streaming).
     * 
     * @param prompt The input prompt
     * @param maxTokens Maximum number of tokens to generate
     * @param temperature Sampling temperature
     * @return The complete generated text
     */
    suspend fun generateComplete(
        prompt: String,
        maxTokens: Int = DEFAULT_MAX_TOKENS,
        temperature: Float = DEFAULT_TEMPERATURE
    ): Result<String> = withContext(Dispatchers.IO) {
        try {
            if (!isModelLoaded()) {
                return@withContext Result.failure(IllegalStateException("Model not loaded"))
            }
            
            val tokens = StringBuilder()
            val callback = object : TokenCallback {
                override fun onToken(token: String) {
                    tokens.append(token)
                }
            }
            
            val result = nativeGenerate(prompt, maxTokens, temperature, callback)
            Result.success(result)
        } catch (e: Exception) {
            Log.e(TAG, "Generation error: ${e.message}")
            Result.failure(e)
        }
    }
    
    /**
     * Unload the current model and free memory.
     */
    fun unloadModel() {
        try {
            nativeUnload()
            currentModelPath = null
            Log.i(TAG, "Model unloaded")
        } catch (e: Exception) {
            Log.e(TAG, "Error unloading model: ${e.message}")
        }
    }
    
    /**
     * Get approximate memory usage of the loaded model.
     * 
     * @return Memory usage in bytes, or 0 if no model is loaded
     */
    fun getMemoryUsage(): Long {
        return try {
            nativeGetMemoryUsage()
        } catch (e: Exception) {
            0L
        }
    }
    
    /**
     * Cleanup resources. Call when the app is shutting down.
     */
    fun cleanup() {
        try {
            nativeCleanup()
            isInitialized = false
            currentModelPath = null
            Log.i(TAG, "Cleanup complete")
        } catch (e: Exception) {
            Log.e(TAG, "Error during cleanup: ${e.message}")
        }
    }
}

/**
 * Events emitted during inference with tool calling support.
 */
sealed class InferenceEvent {
    /** A token was generated */
    data class Token(val text: String) : InferenceEvent()
    
    /** Model wants to call a tool */
    data class ToolCall(
        val name: String,
        val arguments: Map<String, Any>
    ) : InferenceEvent()
    
    /** Generation is complete */
    data class Done(val fullResponse: String) : InferenceEvent()
    
    /** An error occurred */
    data class Error(val message: String) : InferenceEvent()
}
