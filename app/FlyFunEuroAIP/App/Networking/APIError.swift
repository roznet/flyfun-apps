//
//  APIError.swift
//  FlyFunEuroAIP
//
//  Created for Phase 4: Online Integration
//

import Foundation

/// API-specific errors
enum APIError: Error, LocalizedError, Sendable {
    case invalidURL(String)
    case invalidResponse
    case decodingFailed(Error)
    case badRequest
    case unauthorized
    case notFound
    case serverError(Int)
    case httpError(Int)
    case noData
    case timeout
    case cancelled
    
    var errorDescription: String? {
        switch self {
        case .invalidURL(let url):
            return "Invalid URL: \(url)"
        case .invalidResponse:
            return "Invalid response from server"
        case .decodingFailed(let error):
            return "Failed to decode response: \(error.localizedDescription)"
        case .badRequest:
            return "Bad request (400)"
        case .unauthorized:
            return "Unauthorized (401)"
        case .notFound:
            return "Resource not found (404)"
        case .serverError(let code):
            return "Server error (\(code))"
        case .httpError(let code):
            return "HTTP error (\(code))"
        case .noData:
            return "No data received"
        case .timeout:
            return "Request timed out"
        case .cancelled:
            return "Request was cancelled"
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .invalidURL:
            return "Check the API configuration."
        case .invalidResponse, .decodingFailed:
            return "The server returned an unexpected response. Try again later."
        case .badRequest:
            return "The request was invalid. Check your filters and try again."
        case .unauthorized:
            return "Authentication required. Check your credentials."
        case .notFound:
            return "The requested resource was not found."
        case .serverError:
            return "The server encountered an error. Try again later."
        case .httpError:
            return "An unexpected error occurred. Try again."
        case .noData:
            return "No data was returned. Try again."
        case .timeout:
            return "The request took too long. Check your connection and try again."
        case .cancelled:
            return nil
        }
    }
    
    /// Convert to AppError for unified error handling
    var asAppError: AppError {
        switch self {
        case .invalidURL(let url):
            return .unknown(message: "Invalid URL: \(url)")
        case .invalidResponse, .noData:
            return .apiDecodingFailed(endpoint: "unknown")
        case .decodingFailed:
            return .apiDecodingFailed(endpoint: "unknown")
        case .badRequest, .unauthorized:
            return .unknown(message: errorDescription ?? "API error")
        case .notFound:
            return .unknown(message: "Resource not found")
        case .serverError(let code), .httpError(let code):
            return .serverError(statusCode: code)
        case .timeout:
            return .timeout
        case .cancelled:
            return .unknown(message: "Request cancelled")
        }
    }
}

