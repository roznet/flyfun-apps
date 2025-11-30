//
//  APIClient.swift
//  FlyFunEuroAIP
//
//  Created for Phase 4: Online Integration
//

import Foundation
import OSLog
import RZUtilsSwift

/// Base API client for network requests
/// Supports both REST and SSE (Server-Sent Events) streaming
final class APIClient: Sendable {
    
    // MARK: - Configuration
    
    let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    
    // MARK: - Init
    
    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }
    
    /// Convenience initializer with string URL
    convenience init(baseURLString: String) throws {
        guard let url = URL(string: baseURLString) else {
            throw APIError.invalidURL(baseURLString)
        }
        self.init(baseURL: url)
    }
    
    // MARK: - REST Requests
    
    /// Perform a GET request and decode the response
    func get<T: Decodable>(_ endpoint: Endpoint) async throws -> T {
        let request = try buildRequest(for: endpoint, method: "GET")
        return try await perform(request)
    }
    
    /// Perform a POST request with body and decode the response
    func post<T: Decodable, B: Encodable>(_ endpoint: Endpoint, body: B) async throws -> T {
        var request = try buildRequest(for: endpoint, method: "POST")
        request.httpBody = try JSONEncoder().encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return try await perform(request)
    }
    
    /// Perform a POST request with body, no response expected
    func post<B: Encodable>(_ endpoint: Endpoint, body: B) async throws {
        var request = try buildRequest(for: endpoint, method: "POST")
        request.httpBody = try JSONEncoder().encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let (_, response) = try await session.data(for: request)
        try validateResponse(response)
    }
    
    // MARK: - SSE Streaming
    
    /// Stream Server-Sent Events from an endpoint
    func streamSSE(_ endpoint: Endpoint) -> AsyncThrowingStream<SSEEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    var request = try buildRequest(for: endpoint, method: "POST")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    
                    let (bytes, response) = try await session.bytes(for: request)
                    try validateResponse(response)
                    
                    var currentEvent = SSEEvent()
                    var dataBuffer = ""
                    
                    for try await line in bytes.lines {
                        if line.isEmpty {
                            // Empty line = end of event
                            if !dataBuffer.isEmpty {
                                currentEvent.data = dataBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
                                continuation.yield(currentEvent)
                                currentEvent = SSEEvent()
                                dataBuffer = ""
                            }
                        } else if line.hasPrefix("event:") {
                            currentEvent.event = String(line.dropFirst(6)).trimmingCharacters(in: .whitespaces)
                        } else if line.hasPrefix("data:") {
                            let data = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                            if !dataBuffer.isEmpty {
                                dataBuffer += "\n"
                            }
                            dataBuffer += data
                        } else if line.hasPrefix("id:") {
                            currentEvent.id = String(line.dropFirst(3)).trimmingCharacters(in: .whitespaces)
                        }
                    }
                    
                    // Yield any remaining event
                    if !dataBuffer.isEmpty {
                        currentEvent.data = dataBuffer
                        continuation.yield(currentEvent)
                    }
                    
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - Helpers
    
    private func buildRequest(for endpoint: Endpoint, method: String) throws -> URLRequest {
        var urlComponents = URLComponents(url: baseURL.appendingPathComponent(endpoint.path), resolvingAgainstBaseURL: true)
        
        if let queryItems = endpoint.queryItems, !queryItems.isEmpty {
            urlComponents?.queryItems = queryItems
        }
        
        guard let url = urlComponents?.url else {
            throw APIError.invalidURL(endpoint.path)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = endpoint.timeout
        
        // Add any custom headers
        for (key, value) in endpoint.headers {
            request.setValue(value, forHTTPHeaderField: key)
        }
        
        return request
    }
    
    private func perform<T: Decodable>(_ request: URLRequest) async throws -> T {
        Logger.app.info("API Request: \(request.httpMethod ?? "GET") \(request.url?.absoluteString ?? "")")
        
        let (data, response) = try await session.data(for: request)
        try validateResponse(response)
        
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            Logger.app.error("Decode error: \(error.localizedDescription)")
            // Log the raw response for debugging
            if let jsonString = String(data: data, encoding: .utf8) {
                Logger.app.info("Raw response: \(jsonString.prefix(500))")
            }
            throw APIError.decodingFailed(error)
        }
    }
    
    private func validateResponse(_ response: URLResponse) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        switch httpResponse.statusCode {
        case 200...299:
            return // Success
        case 400:
            throw APIError.badRequest
        case 401:
            throw APIError.unauthorized
        case 404:
            throw APIError.notFound
        case 500...599:
            throw APIError.serverError(httpResponse.statusCode)
        default:
            throw APIError.httpError(httpResponse.statusCode)
        }
    }
}

// MARK: - SSE Event

/// Represents a Server-Sent Event
struct SSEEvent: Sendable {
    var event: String?
    var data: String?
    var id: String?
    
    /// Parse the data as JSON
    func decodeData<T: Decodable>(as type: T.Type) throws -> T {
        guard let data = data?.data(using: .utf8) else {
            throw APIError.invalidResponse
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }
}

