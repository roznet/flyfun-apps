//
//  ModelManager.swift
//  FlyFunEuroAIP
//
//  Manages the offline model lifecycle: download, storage, and capability checking.
//  Matches Android ModelManager implementation.
//

import Foundation
import OSLog
import RZUtilsSwift
import UIKit
import Combine

/// Manages the offline model lifecycle: download, storage, and capability checking.
@MainActor
final class ModelManager: ObservableObject {
    
    // MARK: - Configuration
    
    static let modelFilename = "gemma-3n-e2b.task"
    static let modelSizeBytes: Int64 = 1_500_000_000  // ~1.4 GB for Gemma 3n E2B
    static let modelDir = "models"
    
    // Device requirements
    static let minRAMMB: UInt64 = 4096  // 4 GB minimum
    static let recommendedRAMMB: UInt64 = 6144  // 6 GB recommended
    
    // MARK: - Published State
    
    @Published var modelState: ModelState = .checking
    
    // MARK: - Private
    
    private var deviceCapability: DeviceCapability?
    private var externalModelPath: String?
    
    // MARK: - Init
    
    init() {
        checkInitialState()
    }
    
    // MARK: - Model State
    
    enum ModelState: Equatable {
        case checking
        case notDownloaded
        case downloading(progress: Float, downloadedBytes: Int64, totalBytes: Int64)
        case ready
        case loading
        case loaded
        case error(String)
        case deviceNotSupported(String)
    }
    
    // MARK: - Device Capability
    
    struct DeviceCapability {
        let totalRAMMB: UInt64
        let availableRAMMB: UInt64
        let isSupported: Bool
        let isRecommended: Bool
        let warningMessage: String?
    }
    
    // MARK: - Public API
    
    /// Set an external model path for testing purposes.
    func setExternalModelPath(_ path: String) {
        externalModelPath = path
        let fileManager = FileManager.default
        if fileManager.fileExists(atPath: path) {
            Logger.app.info("External model path set: \(path)")
            modelState = .ready
        } else {
            Logger.app.warning("External model file not found: \(path)")
        }
    }
    
    /// Get the model file path
    var modelFile: URL {
        let documentsDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let modelDir = documentsDir.appendingPathComponent(Self.modelDir)
        
        // Create directory if needed
        try? FileManager.default.createDirectory(at: modelDir, withIntermediateDirectories: true)
        
        return modelDir.appendingPathComponent(Self.modelFilename)
    }
    
    /// Get model path as string - returns external path if set and exists
    var modelPath: String {
        if let externalPath = externalModelPath,
           FileManager.default.fileExists(atPath: externalPath) {
            return externalPath
        }
        return modelFile.path
    }
    
    /// Check if model file exists and is complete
    var isModelAvailable: Bool {
        // Check external path first
        if let externalPath = externalModelPath,
           FileManager.default.fileExists(atPath: externalPath) {
            return true
        }
        
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: modelFile.path) else {
            return false
        }
        
        // Check file size (allow some tolerance)
        if let attributes = try? fileManager.attributesOfItem(atPath: modelFile.path),
           let fileSize = attributes[.size] as? Int64 {
            return fileSize > Self.modelSizeBytes / 2  // At least half the expected size
        }
        return false
    }
    
    /// Check device capability for running the model
    func checkDeviceCapability() -> DeviceCapability {
        if let cached = deviceCapability {
            return cached
        }
        
        let totalRAM = ProcessInfo.processInfo.physicalMemory
        let totalRAMMB = totalRAM / (1024 * 1024)
        
        // Estimate available RAM (iOS doesn't expose this directly)
        let availableRAMMB = totalRAMMB / 2  // Conservative estimate
        
        let isSupported = totalRAMMB >= Self.minRAMMB
        let isRecommended = totalRAMMB >= Self.recommendedRAMMB
        
        let warningMessage: String?
        if !isSupported {
            warningMessage = "Your device has \(totalRAMMB)MB RAM. The model requires at least \(Self.minRAMMB)MB."
        } else if !isRecommended {
            warningMessage = "Your device meets minimum requirements but may experience slower performance."
        } else {
            warningMessage = nil
        }
        
        let capability = DeviceCapability(
            totalRAMMB: totalRAMMB,
            availableRAMMB: availableRAMMB,
            isSupported: isSupported,
            isRecommended: isRecommended,
            warningMessage: warningMessage
        )
        
        deviceCapability = capability
        Logger.app.info("Device capability: \(totalRAMMB)MB RAM, supported: \(isSupported)")
        
        return capability
    }
    
    /// Check if offline mode should be available
    var isOfflineModeAvailable: Bool {
        let capability = checkDeviceCapability()
        return capability.isSupported && isModelAvailable
    }
    
    /// Download the model from the given URL with progress updates
    func downloadModel(from url: URL) -> AsyncThrowingStream<DownloadProgress, Error> {
        AsyncThrowingStream { continuation in
            Task {
                Logger.app.info("Starting model download from: \(url.absoluteString)")
                
                let capability = checkDeviceCapability()
                if !capability.isSupported {
                    modelState = .deviceNotSupported(capability.warningMessage ?? "Device not supported")
                    continuation.finish(throwing: ModelError.deviceNotSupported)
                    return
                }
                
                modelState = .downloading(progress: 0, downloadedBytes: 0, totalBytes: Self.modelSizeBytes)
                continuation.yield(.started)
                
                do {
                    let (tempURL, response) = try await URLSession.shared.download(from: url, delegate: nil)
                    
                    guard let httpResponse = response as? HTTPURLResponse,
                          httpResponse.statusCode == 200 else {
                        let error = "Download failed: HTTP error"
                        modelState = .error(error)
                        continuation.finish(throwing: ModelError.downloadFailed(error))
                        return
                    }
                    
                    // Move temp file to final location
                    let fileManager = FileManager.default
                    if fileManager.fileExists(atPath: modelFile.path) {
                        try fileManager.removeItem(at: modelFile)
                    }
                    try fileManager.moveItem(at: tempURL, to: modelFile)
                    
                    Logger.app.info("Model download complete: \(self.modelFile.path)")
                    modelState = .ready
                    continuation.yield(.completed(modelFile))
                    continuation.finish()
                    
                } catch {
                    Logger.app.error("Download error: \(error.localizedDescription)")
                    modelState = .error(error.localizedDescription)
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    /// Delete the downloaded model file
    func deleteModel() throws {
        let fileManager = FileManager.default
        if fileManager.fileExists(atPath: modelFile.path) {
            try fileManager.removeItem(at: modelFile)
            Logger.app.info("Model deleted")
            modelState = .notDownloaded
        } else {
            modelState = .notDownloaded
        }
    }
    
    /// Get available storage space in bytes
    var availableStorage: Int64 {
        let fileManager = FileManager.default
        if let attributes = try? fileManager.attributesOfFileSystem(forPath: NSHomeDirectory()),
           let freeSpace = attributes[.systemFreeSize] as? Int64 {
            return freeSpace
        }
        return 0
    }
    
    /// Check if there's enough storage for the model
    var hasEnoughStorage: Bool {
        // Require extra 500MB buffer
        return availableStorage > Self.modelSizeBytes + (500 * 1024 * 1024)
    }
    
    // MARK: - Private
    
    private func checkInitialState() {
        modelState = .checking
        
        // Check external path first
        if let externalPath = externalModelPath,
           FileManager.default.fileExists(atPath: externalPath) {
            Logger.app.info("External model found: \(externalPath)")
            modelState = .ready
            return
        }
        
        if isModelAvailable {
            Logger.app.info("Model found: \(modelFile.path)")
            modelState = .ready
        } else {
            Logger.app.info("Model not found")
            modelState = .notDownloaded
        }
    }
}

// MARK: - Download Progress

enum DownloadProgress {
    case started
    case inProgress(progress: Float, downloadedBytes: Int64, totalBytes: Int64)
    case completed(URL)
    case error(String)
}

// MARK: - Errors

enum ModelError: LocalizedError {
    case deviceNotSupported
    case downloadFailed(String)
    case insufficientStorage
    
    var errorDescription: String? {
        switch self {
        case .deviceNotSupported:
            return "Device does not meet minimum requirements for offline mode"
        case .downloadFailed(let message):
            return "Download failed: \(message)"
        case .insufficientStorage:
            return "Not enough storage space for the model"
        }
    }
}
