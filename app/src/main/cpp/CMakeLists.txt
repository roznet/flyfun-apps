cmake_minimum_required(VERSION 3.22.1)
project(flyfun_llama LANGUAGES CXX)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Android logging
find_library(log-lib log)
find_library(android-lib android)

# llama.cpp build options (reduce binary size)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
# ========== Vulkan Hybrid Configuration for Adreno 830 ==========
# Using partial GPU offload (n_gpu_layers=15) to work around Adreno Vulkan driver crash
# while still getting GPU acceleration for some layers
set(GGML_VULKAN ON CACHE BOOL "" FORCE)
set(GGML_OPENCL OFF CACHE BOOL "" FORCE)

# Explicitly set glslc path from NDK for shader generation
set(Vulkan_GLSLC_EXECUTABLE "/Users/qianzhao/Library/Android/sdk/ndk/27.0.12077973/shader-tools/darwin-x86_64/glslc" CACHE FILEPATH "" FORCE)

# Disable problematic Vulkan extensions for Adreno mobile stability
set(GGML_VULKAN_COOPMAT OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN_COOPMAT2 OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN_BFLOAT16 OFF CACHE BOOL "" FORCE)

# Force static linking for backends
set(GGML_BACKEND_DL OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)

# Link against Vulkan (NDK stub)
find_library(VULKAN_LIB vulkan)

# Include llama.cpp as subdirectory
add_subdirectory(llama.cpp)

# Define our JNI bridge library
add_library(flyfun_llama SHARED
    llama_bridge.cpp
)

# Include headers from llama.cpp
target_include_directories(flyfun_llama PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/llama.cpp/include
    ${CMAKE_CURRENT_SOURCE_DIR}/llama.cpp/ggml/include
)

target_compile_definitions(flyfun_llama PRIVATE GGML_USE_VULKAN)

# Link libraries
target_link_libraries(flyfun_llama
    llama
    ggml
    ${log-lib}
    ${android-lib}
    ${VULKAN_LIB}
)

# Compiler optimizations for release
target_compile_options(flyfun_llama PRIVATE
    $<$<CONFIG:Release>:-O3 -DNDEBUG>
    $<$<CONFIG:Debug>:-g -O0>
)
