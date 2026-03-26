//
//  BriefingService.swift
//  FlyFunBrief
//
//  Service for communicating with the briefing API.
//

import Foundation
import RZFlight
import OSLog

/// Errors from BriefingService operations
enum BriefingServiceError: LocalizedError {
    case invalidURL
    case networkError(Error)
    case parseError(String)
    case serverError(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid API URL configuration"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .parseError(let message):
            return "Failed to parse response: \(message)"
        case .serverError(let code, let message):
            return "Server error (\(code)): \(message)"
        }
    }
}

/// Service for parsing briefings via the API
actor BriefingService {
    // MARK: - Configuration

    /// Base URL for API requests
    var baseURL: String = "http://localhost:8000"

    /// Auth token for authenticated requests (JWT from Apple Sign-In)
    var authToken: String?

    // MARK: - API Methods

    /// Parse a briefing PDF and return structured data
    ///
    /// - Parameters:
    ///   - pdfData: Raw PDF file data
    ///   - source: Briefing source identifier (default: "foreflight")
    /// - Returns: Parsed Briefing with NOTAMs
    /// - Throws: BriefingServiceError on failure
    func parseBriefing(pdfData: Data, source: String = "foreflight") async throws -> Briefing {
        Logger.network.info("Parsing briefing via API (source: \(source), \(pdfData.count) bytes)")

        // Build URL
        guard let url = URL(string: "\(baseURL)/api/briefing/parse?source=\(source)") else {
            throw BriefingServiceError.invalidURL
        }

        // Create multipart form request
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        // Build body
        var body = Data()

        // Add file field
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"briefing.pdf\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/pdf\r\n\r\n".data(using: .utf8)!)
        body.append(pdfData)
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        // Perform request
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw BriefingServiceError.networkError(error)
        }

        // Check HTTP status
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BriefingServiceError.parseError("Invalid response type")
        }

        if httpResponse.statusCode != 200 {
            // Try to parse error message from body
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw BriefingServiceError.serverError(httpResponse.statusCode, errorMessage)
        }

        // Parse JSON response
        do {
            let briefing = try Briefing.load(from: data)
            Logger.network.info("Parsed briefing with \(briefing.notams.count) NOTAMs")
            return briefing
        } catch {
            Logger.network.error("Failed to parse briefing JSON: \(error.localizedDescription)")
            throw BriefingServiceError.parseError(error.localizedDescription)
        }
    }

    /// Get available briefing sources from the API
    func getSources() async throws -> [String] {
        guard let url = URL(string: "\(baseURL)/api/briefing/sources") else {
            throw BriefingServiceError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw BriefingServiceError.serverError(
                (response as? HTTPURLResponse)?.statusCode ?? 0,
                "Failed to get sources"
            )
        }

        struct SourcesResponse: Codable {
            let sources: [String]
        }

        let sourcesResponse = try JSONDecoder().decode(SourcesResponse.self, from: data)
        return sourcesResponse.sources
    }

    /// Fetch live NOTAMs for a flight route from the server
    ///
    /// Calls the server's Autorouter NOTAM proxy endpoint which resolves
    /// the route to nearby airports and FIR areas, then fetches NOTAMs.
    ///
    /// - Parameters:
    ///   - departure: Departure airport ICAO code
    ///   - destination: Destination airport ICAO code
    ///   - waypoints: Intermediate waypoint ICAO codes
    ///   - departureTime: Departure time for validity filtering
    ///   - arrivalTime: Arrival time for validity filtering
    ///   - corridorNm: Route corridor width in NM (default: 25)
    /// - Returns: Briefing containing fetched NOTAMs
    func fetchRouteNotams(
        departure: String,
        destination: String,
        waypoints: [String] = [],
        departureTime: Date? = nil,
        arrivalTime: Date? = nil,
        corridorNm: Double = 25.0
    ) async throws -> Briefing {
        Logger.network.info("Fetching route NOTAMs: \(departure)→\(destination)")

        // Build URL with query parameters
        guard var components = URLComponents(string: "\(baseURL)/api/briefing/notams") else {
            throw BriefingServiceError.invalidURL
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]

        var queryItems = [
            URLQueryItem(name: "departure", value: departure),
            URLQueryItem(name: "destination", value: destination),
            URLQueryItem(name: "corridor_nm", value: String(corridorNm)),
        ]
        if !waypoints.isEmpty {
            queryItems.append(URLQueryItem(name: "waypoints", value: waypoints.joined(separator: ",")))
        }
        if let departureTime {
            queryItems.append(URLQueryItem(name: "departure_time", value: formatter.string(from: departureTime)))
        }
        if let arrivalTime {
            queryItems.append(URLQueryItem(name: "arrival_time", value: formatter.string(from: arrivalTime)))
        }
        components.queryItems = queryItems

        guard let url = components.url else {
            throw BriefingServiceError.invalidURL
        }

        // Build authenticated request
        var request = URLRequest(url: url)
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        // Perform GET request
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw BriefingServiceError.networkError(error)
        }

        // Check HTTP status
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BriefingServiceError.parseError("Invalid response type")
        }

        if httpResponse.statusCode != 200 {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw BriefingServiceError.serverError(httpResponse.statusCode, errorMessage)
        }

        // Parse JSON response using same path as parseBriefing
        do {
            let briefing = try Briefing.load(from: data)
            Logger.network.info("Fetched \(briefing.notams.count) route NOTAMs")
            return briefing
        } catch {
            Logger.network.error("Failed to parse route NOTAMs JSON: \(error.localizedDescription)")
            throw BriefingServiceError.parseError(error.localizedDescription)
        }
    }

    // MARK: - Configuration

    /// Update the API base URL
    func configure(baseURL: String) {
        self.baseURL = baseURL
        Logger.network.info("BriefingService configured with URL: \(baseURL)")
    }

    /// Update the auth token (call after sign-in or token refresh)
    func setAuthToken(_ token: String?) {
        self.authToken = token
    }
}
