package me.zhaoqian.flyfun.offline

import android.content.Context
import android.util.Log
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.Message
import com.google.ai.edge.litertlm.SamplerConfig
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.Result

/**
 * LiteRT-LM based inference engine for GPU-accelerated LLM inference.
 * Uses .litertlm model format which supports GPU, CPU, and NPU backends.
 */
@Singleton
class LiteRtLmInferenceEngine @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        private const val TAG = "LiteRtLmInference"
        
        // Model parameters
        private const val DEFAULT_MAX_TOKENS = 4096
        private const val DEFAULT_TEMPERATURE = 0.7
        private const val DEFAULT_TOP_K = 40
        private const val DEFAULT_TOP_P = 0.95
    }
    
    private var engine: Engine? = null
    private var conversation: Conversation? = null
    private var currentBackend: String = "unknown"
    private var isModelLoaded = false
    
    /**
     * Load the LLM model with GPU-first approach.
     */
    suspend fun loadModel(modelPath: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            Log.i(TAG, "Loading LiteRT-LM model from: $modelPath")
            val startTime = System.currentTimeMillis()
            
            // Verify model file exists
            val modelFile = File(modelPath)
            if (!modelFile.exists()) {
                return@withContext Result.failure(
                    IllegalStateException("Model file not found: $modelPath")
                )
            }
            Log.d(TAG, "Model file size: ${modelFile.length() / 1024 / 1024} MB")
            
            // Try GPU first, fallback to CPU
            val (createdEngine, backend) = tryCreateEngine(modelPath)
            engine = createdEngine
            currentBackend = backend
            
            // Create initial conversation
            createConversation()
            
            val loadTime = System.currentTimeMillis() - startTime
            Log.i(TAG, "Model loaded successfully with $currentBackend backend in ${loadTime}ms")
            isModelLoaded = true
            
            Result.success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Error loading model: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * Try to create engine with GPU first, fallback to CPU.
     */
    private fun tryCreateEngine(modelPath: String): Pair<Engine, String> {
        // Try GPU first
        try {
            Log.i(TAG, "Attempting GPU backend...")
            val gpuConfig = EngineConfig(
                modelPath = modelPath,
                backend = Backend.GPU,
                maxNumTokens = DEFAULT_MAX_TOKENS,
                cacheDir = context.cacheDir.absolutePath
            )
            val gpuEngine = Engine(gpuConfig)
            gpuEngine.initialize()
            Log.i(TAG, "GPU backend initialized successfully")
            return Pair(gpuEngine, "GPU")
        } catch (e: Exception) {
            Log.w(TAG, "GPU backend failed: ${e.message}, falling back to CPU")
        }
        
        // Fallback to CPU
        try {
            Log.i(TAG, "Attempting CPU backend (fallback)...")
            val cpuConfig = EngineConfig(
                modelPath = modelPath,
                backend = Backend.CPU,
                maxNumTokens = DEFAULT_MAX_TOKENS,
                cacheDir = context.cacheDir.absolutePath
            )
            val cpuEngine = Engine(cpuConfig)
            cpuEngine.initialize()
            Log.i(TAG, "CPU backend initialized successfully")
            return Pair(cpuEngine, "CPU")
        } catch (e: Exception) {
            Log.e(TAG, "CPU backend also failed: ${e.message}", e)
            throw e
        }
    }
    
    /**
     * Create a new conversation with default settings.
     */
    private fun createConversation() {
        val eng = engine ?: throw IllegalStateException("Engine not initialized")
        
        conversation?.close()
        
        val config = ConversationConfig(
            samplerConfig = SamplerConfig(
                topK = DEFAULT_TOP_K,
                topP = DEFAULT_TOP_P,
                temperature = DEFAULT_TEMPERATURE
            )
        )
        
        conversation = eng.createConversation(config)
        Log.d(TAG, "New conversation created")
    }
    
    /**
     * Reset the conversation (clears context).
     */
    fun resetConversation() {
        try {
            createConversation()
        } catch (e: Exception) {
            Log.e(TAG, "Error resetting conversation: ${e.message}", e)
        }
    }
    
    /**
     * Generate a complete response (blocking).
     * Resets conversation before each call to avoid context accumulation.
     */
    suspend fun generate(prompt: String): String = withContext(Dispatchers.IO) {
        val eng = engine ?: throw IllegalStateException("Engine not initialized")
        
        Log.d(TAG, "Generating response (${prompt.length} chars) on $currentBackend")
        val startTime = System.currentTimeMillis()
        
        // Create a fresh conversation for each call to avoid context accumulation
        // This is necessary because accumulated context causes the model to hang
        val config = ConversationConfig(
            samplerConfig = SamplerConfig(
                topK = DEFAULT_TOP_K,
                topP = DEFAULT_TOP_P,
                temperature = DEFAULT_TEMPERATURE
            )
        )
        val conv = eng.createConversation(config)
        
        try {
            // Create a Message from the prompt string and send it
            val inputMessage = Message.of(prompt)
            val responseMessage = conv.sendMessage(inputMessage)
            val result = responseMessage.toString()
            
            val genTime = System.currentTimeMillis() - startTime
            Log.d(TAG, "Generated ${result.length} chars in ${genTime}ms on $currentBackend")
            
            result
        } finally {
            // Close the conversation to free resources
            try { conv.close() } catch (_: Exception) {}
        }
    }
    
    /**
     * Check if model is loaded.
     */
    fun isLoaded(): Boolean = isModelLoaded
    
    /**
     * Get current backend (GPU/CPU).
     */
    fun getBackend(): String = currentBackend
    
    /**
     * Clean up resources.
     */
    fun close() {
        try {
            conversation?.close()
            conversation = null
            engine = null
            isModelLoaded = false
            Log.d(TAG, "LiteRT-LM engine closed")
        } catch (e: Exception) {
            Log.e(TAG, "Error closing engine: ${e.message}", e)
        }
    }
}
