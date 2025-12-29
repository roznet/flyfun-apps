//
//  InferenceEngine.swift
//  FlyFunEuroAIP
//
//  MediaPipe-based inference engine for on-device LLM execution.
//  Uses LlmInference API matching Android implementation.
//  Configured for Gemma 3n E2B model.
//

import Foundation
import OSLog
import RZUtilsSwift
import MediaPipeTasksGenAI

/// MediaPipe-based inference engine for on-device LLM execution.
/// Matches the Android `MediaPipeInferenceEngine` implementation.
final class InferenceEngine: @unchecked Sendable {
    
    // MARK: - Configuration
    
    static let defaultMaxTokens = 4096
    static let gemma3nTemperature: Float = 1.0
    static let gemma3nTopK: Int = 64
    
    // MARK: - State
    
    private var llmInference: LlmInference?
    private var currentModelPath: String?
    private let queue = DispatchQueue(label: "inference.engine", qos: .userInitiated)
    
    // MARK: - Public API
    
    /// Check if a model is loaded and ready for inference.
    var isLoaded: Bool {
        llmInference != nil
    }
    
    /// Get current model path if loaded.
    var modelPath: String? {
        currentModelPath
    }
    
    /// Load a model from the given path.
    /// - Parameter modelPath: Absolute path to the .task model file
    /// - Throws: Error if model loading fails
    func loadModel(at modelPath: String) async throws {
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: modelPath) else {
            throw InferenceError.modelNotFound(path: modelPath)
        }
        
        let fileSize = (try? fileManager.attributesOfItem(atPath: modelPath)[.size] as? Int64) ?? 0
        let fileSizeMB = fileSize / 1024 / 1024
        Logger.app.info("Loading model: \(modelPath) (\(fileSizeMB) MB)")
        
        // Unload previous model if any
        closeResources()
        
        // Create LlmInference with options on background queue
        let options = LlmInference.Options(modelPath: modelPath)
        options.maxTokens = Self.defaultMaxTokens
        
        // Run heavy model loading on background queue
        let inference = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<LlmInference, Error>) in
            queue.async {
                do {
                    let startTime = Date()
                    let inference = try LlmInference(options: options)
                    let loadTime = Date().timeIntervalSince(startTime) * 1000
                    Logger.app.info("Model loaded successfully in \(Int(loadTime))ms")
                    continuation.resume(returning: inference)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
        
        self.llmInference = inference
        self.currentModelPath = modelPath
    }
    
    /// Generate text from a prompt.
    /// - Parameters:
    ///   - prompt: The input prompt
    ///   - maxTokens: Maximum tokens to generate
    /// - Returns: Generated response string
    func generate(prompt: String, maxTokens: Int = defaultMaxTokens) async throws -> String {
        guard let inference = llmInference else {
            throw InferenceError.modelNotLoaded
        }
        
        Logger.app.info("Starting generation for prompt (\(prompt.count) chars)")
        
        // Run generation on background queue to not block UI
        let response = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<String, Error>) in
            queue.async {
                do {
                    let startTime = Date()
                    let response = try inference.generateResponse(inputText: prompt)
                    let inferenceTime = Date().timeIntervalSince(startTime) * 1000
                    Logger.app.info("Generation completed in \(Int(inferenceTime))ms, response length: \(response.count)")
                    continuation.resume(returning: response)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
        
        return response
    }
    
    /// Generate text with streaming output.
    /// - Parameters:
    ///   - prompt: The input prompt
    ///   - maxTokens: Maximum tokens to generate
    /// - Returns: AsyncStream of generated tokens
    func generateStream(prompt: String, maxTokens: Int = defaultMaxTokens) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    guard let inference = self.llmInference else {
                        throw InferenceError.modelNotLoaded
                    }
                    
                    Logger.app.info("Starting streaming generation for prompt (\(prompt.count) chars)")
                    let startTime = Date()
                    
                    // Use async generation with progress callback
                    let response = try inference.generateResponse(inputText: prompt)
                    
                    // Emit entire response (MediaPipe iOS may not support true streaming yet)
                    if !response.isEmpty {
                        continuation.yield(response)
                    }
                    
                    let inferenceTime = Date().timeIntervalSince(startTime) * 1000
                    Logger.app.info("Streaming generation completed in \(Int(inferenceTime))ms")
                    
                    continuation.finish()
                } catch {
                    Logger.app.error("Generation error: \(error.localizedDescription)")
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    /// Unload the current model and free resources.
    func unload() {
        closeResources()
        currentModelPath = nil
        Logger.app.info("Model unloaded")
    }
    
    // MARK: - Private
    
    private func closeResources() {
        llmInference = nil
    }
}

// MARK: - Errors

enum InferenceError: LocalizedError {
    case modelNotFound(path: String)
    case modelNotLoaded
    case generationFailed(String)
    
    var errorDescription: String? {
        switch self {
        case .modelNotFound(let path):
            return "Model file not found: \(path)"
        case .modelNotLoaded:
            return "Model not loaded. Call loadModel() first."
        case .generationFailed(let message):
            return "Generation failed: \(message)"
        }
    }
}
