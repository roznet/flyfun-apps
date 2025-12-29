/**
 * FlyFun llama.cpp JNI Bridge
 *
 * Provides native bindings between Kotlin and llama.cpp for on-device
 * language model inference.
 */

#include <android/log.h>
#include <chrono>
#include <jni.h>
#include <mutex>
#include <string>

#ifdef GGML_USE_OPENCL
#include <CL/cl.h>
#endif

#include "ggml.h"
#include "llama.h"

#define LOG_TAG "FlyFunLlama"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)

// ========== Batch Helper Functions (inline versions of common_batch_*)
// ==========

static void batch_clear(struct llama_batch &batch) { batch.n_tokens = 0; }

static void batch_add(struct llama_batch &batch, llama_token id, llama_pos pos,
                      const std::vector<llama_seq_id> &seq_ids, bool logits) {
  batch.token[batch.n_tokens] = id;
  batch.pos[batch.n_tokens] = pos;
  batch.n_seq_id[batch.n_tokens] = seq_ids.size();
  for (size_t i = 0; i < seq_ids.size(); ++i) {
    batch.seq_id[batch.n_tokens][i] = seq_ids[i];
  }
  batch.logits[batch.n_tokens] = logits;
  batch.n_tokens++;
}

// Global state for the loaded model
struct LlamaContext {
  llama_model *model = nullptr;
  llama_context *ctx = nullptr;
  const llama_vocab *vocab = nullptr;
  std::mutex mutex;
  bool is_loaded = false;
};

static LlamaContext g_llama_ctx;

static void llama_log_callback(ggml_log_level level, const char *text,
                               void *user_data) {
  (void)user_data;
  int android_level = ANDROID_LOG_INFO;
  switch (level) {
  case GGML_LOG_LEVEL_ERROR:
    android_level = ANDROID_LOG_ERROR;
    break;
  case GGML_LOG_LEVEL_WARN:
    android_level = ANDROID_LOG_WARN;
    break;
  case GGML_LOG_LEVEL_INFO:
    android_level = ANDROID_LOG_INFO;
    break;
  case GGML_LOG_LEVEL_DEBUG:
    android_level = ANDROID_LOG_DEBUG;
    break;
  default:
    break;
  }
  __android_log_print(android_level, LOG_TAG, "%s", text);
}

extern "C" {

/**
 * Initialize the llama backend (call once at app startup)
 */
JNIEXPORT void JNICALL
Java_me_zhaoqian_flyfun_offline_LocalInferenceEngine_nativeInit(JNIEnv *env,
                                                                jobject thiz) {
  LOGI("Initializing llama backend");

  llama_log_set(llama_log_callback, NULL);

  llama_backend_init();
  LOGI("Backend initialized");

  // Log system info to check for GPU support
  const char *system_info = llama_print_system_info();
  LOGI("System Info: %s", system_info);
}

/**
 * Load a GGUF model from the given path
 *
 * @param modelPath Absolute path to the GGUF file
 * @param nGpuLayers Number of layers to offload to GPU (0 for CPU-only)
 * @return true if successful, false otherwise
 */
JNIEXPORT jboolean JNICALL
Java_me_zhaoqian_flyfun_offline_LocalInferenceEngine_nativeLoadModel(
    JNIEnv *env, jobject thiz, jstring modelPath, jint nGpuLayers) {
  std::lock_guard<std::mutex> lock(g_llama_ctx.mutex);

  // Unload previous model if any
  if (g_llama_ctx.is_loaded) {
    if (g_llama_ctx.ctx) {
      llama_free(g_llama_ctx.ctx);
      g_llama_ctx.ctx = nullptr;
    }
    if (g_llama_ctx.model) {
      llama_model_free(g_llama_ctx.model);
      g_llama_ctx.model = nullptr;
    }
    g_llama_ctx.vocab = nullptr;
    g_llama_ctx.is_loaded = false;
  }

  const char *path = env->GetStringUTFChars(modelPath, nullptr);
  LOGI("Loading model from: %s", path);

  // Initialize model parameters
  llama_model_params model_params = llama_model_default_params();
  model_params.n_gpu_layers = nGpuLayers;

  // Load the model using new API
  g_llama_ctx.model = llama_model_load_from_file(path, model_params);
  env->ReleaseStringUTFChars(modelPath, path);

  if (!g_llama_ctx.model) {
    LOGE("Failed to load model");
    return JNI_FALSE;
  }

  // Get vocabulary
  g_llama_ctx.vocab = llama_model_get_vocab(g_llama_ctx.model);
  if (!g_llama_ctx.vocab) {
    LOGE("Failed to get vocabulary");
    llama_model_free(g_llama_ctx.model);
    g_llama_ctx.model = nullptr;
    return JNI_FALSE;
  }

  // Initialize context parameters
  llama_context_params ctx_params = llama_context_default_params();
  ctx_params.n_ctx = 2048;  // Context window size (reduced for mobile)
  ctx_params.n_batch = 32;  // Reduced batch size for Adreno Vulkan stability
  ctx_params.n_threads = 8; // More threads for generation
  ctx_params.n_threads_batch = 8; // More threads for batch processing

  // Create context using new API
  g_llama_ctx.ctx = llama_init_from_model(g_llama_ctx.model, ctx_params);

  if (!g_llama_ctx.ctx) {
    LOGE("Failed to create context");
    llama_model_free(g_llama_ctx.model);
    g_llama_ctx.model = nullptr;
    g_llama_ctx.vocab = nullptr;
    return JNI_FALSE;
  }

  g_llama_ctx.is_loaded = true;
  LOGI("Model loaded successfully");
  return JNI_TRUE;
}

/**
 * Check if a model is currently loaded
 */
JNIEXPORT jboolean JNICALL
Java_me_zhaoqian_flyfun_offline_LocalInferenceEngine_nativeIsLoaded(
    JNIEnv *env, jobject thiz) {
  return g_llama_ctx.is_loaded ? JNI_TRUE : JNI_FALSE;
}

/**
 * Generate text from a prompt with streaming callback
 *
 * @param prompt The input prompt
 * @param maxTokens Maximum tokens to generate
 * @param temperature Sampling temperature
 * @param callback Kotlin callback for each generated token
 * @return The complete generated text
 */
JNIEXPORT jstring JNICALL
Java_me_zhaoqian_flyfun_offline_LocalInferenceEngine_nativeGenerate(
    JNIEnv *env, jobject thiz, jstring prompt, jint maxTokens,
    jfloat temperature, jobject callback) {
  std::lock_guard<std::mutex> lock(g_llama_ctx.mutex);

  if (!g_llama_ctx.is_loaded) {
    LOGE("Model not loaded");
    return env->NewStringUTF("");
  }

  const char *prompt_cstr = env->GetStringUTFChars(prompt, nullptr);
  std::string prompt_str(prompt_cstr);
  env->ReleaseStringUTFChars(prompt, prompt_cstr);

  LOGD("Generating from prompt (length: %zu)", prompt_str.length());

  // Tokenize the prompt using vocab
  const int n_prompt_tokens = -llama_tokenize(
      g_llama_ctx.vocab, prompt_str.c_str(), prompt_str.length(), nullptr, 0,
      true, // add_special
      true  // parse_special
  );

  std::vector<llama_token> tokens(n_prompt_tokens);
  if (llama_tokenize(g_llama_ctx.vocab, prompt_str.c_str(), prompt_str.length(),
                     tokens.data(), tokens.size(), true, true) < 0) {
    LOGE("Failed to tokenize prompt");
    return env->NewStringUTF("");
  }

  LOGD("Prompt tokenized: %d tokens", n_prompt_tokens);

  // Clear the KV cache for new generation
  llama_memory_t memory = llama_get_memory(g_llama_ctx.ctx);
  if (memory) {
    llama_memory_clear(memory, true);
  }

  // Process prompt in smaller batches for mobile performance
  // NOTE: Batch size 32 is used to workaround Adreno Vulkan driver crashes with
  // larger batches
  llama_batch batch = llama_batch_init(32, 0, 1);
  const int batch_size = 32;

  LOGD("Processing %zu tokens in batches of %d...", tokens.size(), batch_size);
  auto start_time = std::chrono::high_resolution_clock::now();

  for (size_t i = 0; i < tokens.size(); i += batch_size) {
    batch_clear(batch);

    size_t batch_end = std::min(i + batch_size, tokens.size());
    for (size_t j = i; j < batch_end; j++) {
      bool is_last = (j == tokens.size() - 1);
      batch_add(batch, tokens[j], j, {0}, is_last);
    }

    LOGD("Decoding batch %zu-%zu...", i, batch_end - 1);

    if (llama_decode(g_llama_ctx.ctx, batch) != 0) {
      LOGE("Failed to decode prompt batch");
      llama_batch_free(batch);
      return env->NewStringUTF("");
    }
  }

  auto end_time = std::chrono::high_resolution_clock::now();
  auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(
      end_time - start_time);
  LOGD("Prompt decode completed in %lldms", duration.count());

  // Get callback method
  jclass callbackClass = env->GetObjectClass(callback);
  jmethodID onTokenMethod =
      env->GetMethodID(callbackClass, "onToken", "(Ljava/lang/String;)V");

  // Generate tokens
  std::string result;
  // n_cur should be the position AFTER the prompt, i.e., prompt length
  int n_cur = tokens.size();

  // Initialize sampler
  llama_sampler *sampler =
      llama_sampler_chain_init(llama_sampler_chain_default_params());
  llama_sampler_chain_add(sampler, llama_sampler_init_temp(temperature));
  llama_sampler_chain_add(sampler, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));

  for (int i = 0; i < maxTokens; i++) {
    // Sample next token
    llama_token new_token = llama_sampler_sample(sampler, g_llama_ctx.ctx, -1);

    // Check for end of generation
    if (llama_vocab_is_eog(g_llama_ctx.vocab, new_token)) {
      LOGD("End of generation token reached");
      break;
    }

    // Convert token to text
    char buf[256];
    int n = llama_token_to_piece(g_llama_ctx.vocab, new_token, buf, sizeof(buf),
                                 0, true);
    if (n < 0) {
      LOGE("Failed to convert token to text");
      break;
    }

    std::string token_str(buf, n);
    result += token_str;

    // Call Kotlin callback with the token
    jstring token_jstr = env->NewStringUTF(token_str.c_str());
    env->CallVoidMethod(callback, onTokenMethod, token_jstr);
    env->DeleteLocalRef(token_jstr);

    // Prepare next batch
    batch_clear(batch);
    batch_add(batch, new_token, n_cur, {0}, true);
    n_cur++;

    if (llama_decode(g_llama_ctx.ctx, batch) != 0) {
      LOGE("Failed to decode");
      break;
    }
  }

  llama_sampler_free(sampler);
  llama_batch_free(batch);

  LOGD("Generation complete: %zu chars", result.length());

  // Print performance timings to logcat
  llama_perf_context_print(g_llama_ctx.ctx);

  return env->NewStringUTF(result.c_str());
}

/**
 * Unload the current model and free resources
 */
JNIEXPORT void JNICALL
Java_me_zhaoqian_flyfun_offline_LocalInferenceEngine_nativeUnload(
    JNIEnv *env, jobject thiz) {
  std::lock_guard<std::mutex> lock(g_llama_ctx.mutex);

  LOGI("Unloading model");

  if (g_llama_ctx.ctx) {
    llama_free(g_llama_ctx.ctx);
    g_llama_ctx.ctx = nullptr;
  }

  if (g_llama_ctx.model) {
    llama_model_free(g_llama_ctx.model);
    g_llama_ctx.model = nullptr;
  }

  g_llama_ctx.vocab = nullptr;
  g_llama_ctx.is_loaded = false;
}

/**
 * Cleanup llama backend (call at app shutdown)
 */
JNIEXPORT void JNICALL
Java_me_zhaoqian_flyfun_offline_LocalInferenceEngine_nativeCleanup(
    JNIEnv *env, jobject thiz) {
  LOGI("Cleaning up llama backend");

  // Ensure model is unloaded first
  Java_me_zhaoqian_flyfun_offline_LocalInferenceEngine_nativeUnload(env, thiz);

  llama_backend_free();
}

/**
 * Get memory usage information for the loaded model
 */
JNIEXPORT jlong JNICALL
Java_me_zhaoqian_flyfun_offline_LocalInferenceEngine_nativeGetMemoryUsage(
    JNIEnv *env, jobject thiz) {
  if (!g_llama_ctx.is_loaded || !g_llama_ctx.ctx) {
    return 0;
  }

  // Return approximate memory usage in bytes
  size_t state_size = llama_state_get_size(g_llama_ctx.ctx);
  return static_cast<jlong>(state_size);
}

} // extern "C"
