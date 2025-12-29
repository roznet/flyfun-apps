plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.dagger.hilt.android")
    id("org.jetbrains.kotlin.plugin.serialization")
    kotlin("kapt")
}

import java.util.Properties

android {
    namespace = "me.zhaoqian.flyfun"
    compileSdk = 34

    // Read API URL from local.properties
    val localProperties = Properties()
    val localPropertiesFile = rootProject.file("local.properties")
    if (localPropertiesFile.exists()) {
        localPropertiesFile.inputStream().use { localProperties.load(it) }
    }
    val apiBaseUrl = localProperties.getProperty("API_BASE_URL", "http://localhost:8000/")

    defaultConfig {
        applicationId = "me.zhaoqian.flyfun"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        // Add API URL as BuildConfig field
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }

        // NDK configuration for llama.cpp
        ndk {
            abiFilters += listOf("arm64-v8a")  // ARM64 only for OpenCL GPU acceleration
        }

        // External native build arguments
        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DANDROID_STL=c++_shared",
                    "-DLLAMA_BUILD_EXAMPLES=OFF",
                    "-DLLAMA_BUILD_TESTS=OFF",
                    "-DLLAMA_BUILD_SERVER=OFF",
                    "-DGGML_VULKAN=OFF",
                    "-DGGML_OPENCL=ON",
                    "-DCMAKE_MAKE_PROGRAM=/Users/qianzhao/Library/Android/sdk/cmake/3.22.1/bin/ninja"
                )
                cppFlags += listOf("-std=c++17", "-O3")
            }
        }
    }

    sourceSets {
        getByName("main") {
            // Include NDK sysroot libs to pick up the manually installed libOpenCL.so
            // Note: This is hacky. Better to put it in src/main/jniLibs or copy it there.
            // But we can't easily access workspace outside.
            // Actually, we can just copy it to app/src/main/jniLibs/arm64-v8a in a task?
            // Or point jniLibs.srcDirs to it?
            // The path is /Users/qianzhao/Library/Android/sdk/ndk/27.0.12077973/toolchains/llvm/prebuilt/darwin-x86_64/sysroot/usr/lib/aarch64-linux-android/29
            // CAUTION: This might include ALL system libs which is bad.
            // Better to copy libOpenCL.so to project jniLibs.
        }
    }

    // CMake build configuration
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isDebuggable = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // Compose compiler is now handled by the kotlin compose plugin in Kotlin 2.x

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // Core Android
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.activity:activity-compose:1.8.2")

    // Compose BOM
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    // Navigation
    implementation("androidx.navigation:navigation-compose:2.7.6")

    // ViewModel
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.7.0")

    // Hilt Dependency Injection
    implementation("com.google.dagger:hilt-android:2.55")
    kapt("com.google.dagger:hilt-android-compiler:2.55")
    implementation("androidx.hilt:hilt-navigation-compose:1.2.0")

    // Networking - Retrofit + OkHttp
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("com.squareup.okhttp3:okhttp-sse:4.12.0")

    // Kotlinx Serialization
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.2")
    implementation("com.jakewharton.retrofit:retrofit2-kotlinx-serialization-converter:1.0.0")

    // OpenStreetMap - osmdroid (NO API KEY NEEDED!)
    implementation("org.osmdroid:osmdroid-android:6.1.18")
    implementation("org.osmdroid:osmdroid-wms:6.1.18")

    // Coil - Image loading
    implementation("io.coil-kt:coil-compose:2.5.0")

    // Markdown rendering
    implementation("com.halilibo.compose-richtext:richtext-commonmark:0.17.0")
    implementation("com.halilibo.compose-richtext:richtext-ui-material3:0.17.0")

    // MediaPipe LLM Inference (CPU fallback) - 0.10.25 for Gemma 3n
    implementation("com.google.mediapipe:tasks-genai:0.10.25")

    // LiteRT-LM for GPU inference with .litertlm models
    implementation("com.google.ai.edge.litertlm:litertlm-android:0.9.0-alpha01")

    // Testing
    testImplementation("junit:junit:4.13.2")
    testImplementation("io.mockk:mockk:1.13.8")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.7.3")

    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
    androidTestImplementation(platform("androidx.compose:compose-bom:2024.06.00"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")

    // Debug
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}

kapt {
    correctErrorTypes = true
}
