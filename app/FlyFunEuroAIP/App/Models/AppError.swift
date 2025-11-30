//
//  AppError.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation

/// Unified error type for the app
/// Provides user-friendly messages and logging context
enum AppError: LocalizedError, Equatable {
    // Data errors
    case databaseOpenFailed(path: String)
    case databaseCorrupted
    case airportNotFound(icao: String)
    case syncFailed(reason: String)
    case incompatibleSchema(server: Int, app: Int)
    
    // Network errors
    case networkUnavailable
    case serverError(statusCode: Int)
    case apiDecodingFailed(endpoint: String)
    case timeout
    
    // Chat errors
    case chatStreamFailed
    case toolExecutionFailed(tool: String)
    
    // General
    case unknown(message: String)
    
    var errorDescription: String? {
        switch self {
        case .databaseOpenFailed: return "Could not open airport database"
        case .databaseCorrupted: return "Airport database is corrupted"
        case .airportNotFound(let icao): return "Airport \(icao) not found"
        case .syncFailed(let reason): return "Database sync failed: \(reason)"
        case .incompatibleSchema: return "Please update the app to use latest database"
        case .networkUnavailable: return "No internet connection"
        case .serverError(let code): return "Server error (\(code))"
        case .apiDecodingFailed: return "Failed to parse server response"
        case .timeout: return "Request timed out"
        case .chatStreamFailed: return "Chat connection interrupted"
        case .toolExecutionFailed(let tool): return "Could not execute \(tool)"
        case .unknown(let msg): return msg
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .networkUnavailable: return "Check your internet connection and try again"
        case .serverError, .timeout: return "Try again later"
        case .syncFailed: return "You can continue using cached data"
        case .incompatibleSchema: return "Visit the App Store to update"
        default: return nil
        }
    }
    
    /// Create from any Error
    init(from error: Error) {
        if let appError = error as? AppError {
            self = appError
        } else if let urlError = error as? URLError {
            switch urlError.code {
            case .notConnectedToInternet: self = .networkUnavailable
            case .timedOut: self = .timeout
            default: self = .unknown(message: urlError.localizedDescription)
            }
        } else {
            self = .unknown(message: error.localizedDescription)
        }
    }
}

