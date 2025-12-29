package me.zhaoqian.flyfun.offline

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages the offline model lifecycle: download, storage, and capability checking.
 */
@Singleton
class ModelManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val okHttpClient: OkHttpClient
) {
    companion object {
        private const val TAG = "ModelManager"
        
        // Model configuration
        const val MODEL_FILENAME = "flyfun-gemma-3n-q4_k_m.gguf"
        const val MODEL_SIZE_BYTES = 2_787_805_824L  // ~2.6 GB
        const val MODEL_DIR = "models"
        
        // Local testing path (set to external file for development)
        // This can be used when testing with adb push to device
        const val LOCAL_TEST_MODEL_PATH = "/data/local/tmp/flyfun-gemma-3n-q4_k_m.gguf"
        
        // MediaPipe model path for Gemma 3n E2B (CPU fallback)
        const val MEDIAPIPE_TEST_MODEL_PATH = "/data/data/me.zhaoqian.flyfun/files/gemma-3n-e2b.task"
        
        // LiteRT-LM model path for Gemma 3n E2B (GPU/CPU/NPU support)
        const val LITERTLM_MODEL_PATH = "/data/data/me.zhaoqian.flyfun/files/gemma-3n-E2B-it-int4.litertlm"
        
        // Device requirements
        const val MIN_RAM_MB = 4096  // 4 GB minimum
        const val RECOMMENDED_RAM_MB = 6144  // 6 GB recommended
        const val MIN_SDK_VERSION = Build.VERSION_CODES.O  // Android 8.0
    }
    
    // Model state
    private val _modelState = MutableStateFlow<ModelState>(ModelState.Checking)
    val modelState: StateFlow<ModelState> = _modelState.asStateFlow()
    
    // Device capability info
    private var deviceCapability: DeviceCapability? = null
    
    // External model path (for testing with adb-pushed model)
    private var externalModelPath: String? = null
    
    init {
        checkInitialState()
    }
    
    /**
     * Model download and loading states
     */
    sealed class ModelState {
        /** Checking if model exists */
        object Checking : ModelState()
        
        /** Model not downloaded yet */
        object NotDownloaded : ModelState()
        
        /** Model is being downloaded */
        data class Downloading(
            val progress: Float,
            val downloadedBytes: Long,
            val totalBytes: Long
        ) : ModelState()
        
        /** Model downloaded and ready */
        object Ready : ModelState()
        
        /** Model is being loaded into memory */
        object Loading : ModelState()
        
        /** Model is loaded and ready for inference */
        object Loaded : ModelState()
        
        /** Error state */
        data class Error(val message: String) : ModelState()
        
        /** Device not capable */
        data class DeviceNotSupported(val reason: String) : ModelState()
    }
    
    /**
     * Device capability assessment
     */
    data class DeviceCapability(
        val totalRamMb: Long,
        val availableRamMb: Long,
        val sdkVersion: Int,
        val isSupported: Boolean,
        val isRecommended: Boolean,
        val warningMessage: String?
    )
    
    /**
     * Set an external model path for testing purposes.
     * When set, this path will be used instead of the downloaded model.
     */
    fun setExternalModelPath(path: String) {
        externalModelPath = path
        val file = File(path)
        if (file.exists()) {
            Log.i(TAG, "External model path set: $path")
            _modelState.value = ModelState.Ready
        } else {
            Log.w(TAG, "External model file not found: $path")
        }
    }
    
    /**
     * Check initial model state on startup
     */
    private fun checkInitialState() {
        _modelState.value = ModelState.Checking
        
        // Check external path first
        externalModelPath?.let { path ->
            val externalFile = File(path)
            if (externalFile.exists()) {
                Log.i(TAG, "External model found: $path")
                _modelState.value = ModelState.Ready
                return
            }
        }
        
        val modelFile = getModelFile()
        _modelState.value = if (modelFile.exists() && modelFile.length() == MODEL_SIZE_BYTES) {
            Log.i(TAG, "Model found: ${modelFile.absolutePath}")
            ModelState.Ready
        } else {
            Log.i(TAG, "Model not found")
            ModelState.NotDownloaded
        }
    }
    
    /**
     * Get the model file path
     */
    fun getModelFile(): File {
        val modelDir = File(context.filesDir, MODEL_DIR)
        if (!modelDir.exists()) {
            modelDir.mkdirs()
        }
        return File(modelDir, MODEL_FILENAME)
    }
    
    /**
     * Get model path as string - returns external path if set and exists
     */
    fun getModelPath(): String {
        externalModelPath?.let { path ->
            if (File(path).exists()) {
                return path
            }
        }
        return getModelFile().absolutePath
    }
    
    /**
     * Check if model file exists and is complete
     */
    fun isModelAvailable(): Boolean {
        // Check external path first
        externalModelPath?.let { path ->
            if (File(path).exists()) {
                return true
            }
        }
        val modelFile = getModelFile()
        return modelFile.exists() && modelFile.length() == MODEL_SIZE_BYTES
    }
    
    /**
     * Check device capability for running the model
     */
    fun checkDeviceCapability(): DeviceCapability {
        deviceCapability?.let { return it }
        
        val activityManager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memoryInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memoryInfo)
        
        val totalRamMb = memoryInfo.totalMem / (1024 * 1024)
        val availableRamMb = memoryInfo.availMem / (1024 * 1024)
        val sdkVersion = Build.VERSION.SDK_INT
        
        val isSupported = totalRamMb >= MIN_RAM_MB && sdkVersion >= MIN_SDK_VERSION
        val isRecommended = totalRamMb >= RECOMMENDED_RAM_MB
        
        val warningMessage = when {
            !isSupported && totalRamMb < MIN_RAM_MB -> 
                "Your device has ${totalRamMb}MB RAM. The model requires at least ${MIN_RAM_MB}MB."
            !isSupported && sdkVersion < MIN_SDK_VERSION -> 
                "Your Android version is not supported. Minimum required: Android 8.0"
            !isRecommended -> 
                "Your device meets minimum requirements but may experience slower performance."
            else -> null
        }
        
        val capability = DeviceCapability(
            totalRamMb = totalRamMb,
            availableRamMb = availableRamMb,
            sdkVersion = sdkVersion,
            isSupported = isSupported,
            isRecommended = isRecommended,
            warningMessage = warningMessage
        )
        
        deviceCapability = capability
        Log.i(TAG, "Device capability: $capability")
        
        return capability
    }
    
    /**
     * Check if offline mode should be available
     */
    fun isOfflineModeAvailable(): Boolean {
        val capability = checkDeviceCapability()
        return capability.isSupported && isModelAvailable()
    }
    
    /**
     * Download the model from the given URL with progress updates
     * 
     * @param url URL to download the model from
     * @return Flow of download progress, completes when done
     */
    fun downloadModel(url: String): Flow<DownloadProgress> = flow {
        Log.i(TAG, "Starting model download from: $url")
        
        val capability = checkDeviceCapability()
        if (!capability.isSupported) {
            _modelState.value = ModelState.DeviceNotSupported(
                capability.warningMessage ?: "Device not supported"
            )
            emit(DownloadProgress.Error("Device not supported for offline mode"))
            return@flow
        }
        
        _modelState.value = ModelState.Downloading(0f, 0, MODEL_SIZE_BYTES)
        emit(DownloadProgress.Started)
        
        try {
            val request = Request.Builder()
                .url(url)
                .build()
            
            val response = okHttpClient.newCall(request).execute()
            
            if (!response.isSuccessful) {
                val error = "Download failed: HTTP ${response.code}"
                _modelState.value = ModelState.Error(error)
                emit(DownloadProgress.Error(error))
                return@flow
            }
            
            val body = response.body ?: run {
                val error = "Download failed: Empty response"
                _modelState.value = ModelState.Error(error)
                emit(DownloadProgress.Error(error))
                return@flow
            }
            
            val totalBytes = body.contentLength().takeIf { it > 0 } ?: MODEL_SIZE_BYTES
            val modelFile = getModelFile()
            val tempFile = File(modelFile.parent, "${modelFile.name}.tmp")
            
            var downloadedBytes = 0L
            
            body.byteStream().use { input ->
                FileOutputStream(tempFile).use { output ->
                    val buffer = ByteArray(8192)
                    var bytesRead: Int
                    
                    while (input.read(buffer).also { bytesRead = it } != -1) {
                        output.write(buffer, 0, bytesRead)
                        downloadedBytes += bytesRead
                        
                        val progress = downloadedBytes.toFloat() / totalBytes
                        _modelState.value = ModelState.Downloading(progress, downloadedBytes, totalBytes)
                        emit(DownloadProgress.InProgress(progress, downloadedBytes, totalBytes))
                    }
                }
            }
            
            // Rename temp file to final name
            if (tempFile.renameTo(modelFile)) {
                Log.i(TAG, "Model download complete: ${modelFile.absolutePath}")
                _modelState.value = ModelState.Ready
                emit(DownloadProgress.Completed(modelFile))
            } else {
                val error = "Failed to save model file"
                _modelState.value = ModelState.Error(error)
                emit(DownloadProgress.Error(error))
                tempFile.delete()
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "Download error: ${e.message}", e)
            val error = e.message ?: "Unknown download error"
            _modelState.value = ModelState.Error(error)
            emit(DownloadProgress.Error(error))
        }
    }.flowOn(Dispatchers.IO)
    
    /**
     * Delete the downloaded model file
     */
    suspend fun deleteModel(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val modelFile = getModelFile()
            if (modelFile.exists()) {
                val deleted = modelFile.delete()
                if (deleted) {
                    Log.i(TAG, "Model deleted")
                    _modelState.value = ModelState.NotDownloaded
                    Result.success(Unit)
                } else {
                    Result.failure(Exception("Failed to delete model file"))
                }
            } else {
                _modelState.value = ModelState.NotDownloaded
                Result.success(Unit)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error deleting model: ${e.message}")
            Result.failure(e)
        }
    }
    
    /**
     * Get available storage space in bytes
     */
    fun getAvailableStorage(): Long {
        return context.filesDir.freeSpace
    }
    
    /**
     * Check if there's enough storage for the model
     */
    fun hasEnoughStorage(): Boolean {
        // Require extra 500MB buffer
        return getAvailableStorage() > MODEL_SIZE_BYTES + (500 * 1024 * 1024)
    }
}

/**
 * Download progress events
 */
sealed class DownloadProgress {
    object Started : DownloadProgress()
    
    data class InProgress(
        val progress: Float,
        val downloadedBytes: Long,
        val totalBytes: Long
    ) : DownloadProgress()
    
    data class Completed(val file: File) : DownloadProgress()
    
    data class Error(val message: String) : DownloadProgress()
}
