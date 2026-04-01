//
//  SecretsManager.swift
//  FlyFunBrief
//
//  Loads configuration from secrets.json file.
//  Replicates pattern from FlyFunEuroAIP.
//

import Foundation
import OSLog

/// Manages loading secrets from secrets.json
/// Usage:
///   1. Copy secrets.json.sample to secrets.json
///   2. Fill in your actual values
///   3. secrets.json is gitignored and won't be committed
struct SecretsManager {

    // MARK: - Singleton

    static let shared = SecretsManager()

    // MARK: - Configuration Values

    /// Base URL for API requests (FlyFunBrief server)
    let apiBaseURL: String

    /// Base URL for OAuth (shared flyfun-common auth server)
    let authBaseURL: String

    // MARK: - Defaults

    private static let defaults: [String: String] = [
        "api_base_url": "http://localhost:8000",
        "auth_base_url": "https://forms.flyfun.aero"
    ]

    // MARK: - Init

    private init() {
        let secrets = Self.loadSecrets()
        let baseURL = secrets["api_base_url"] ?? Self.defaults["api_base_url"]!
        self.apiBaseURL = baseURL
        self.authBaseURL = secrets["auth_base_url"] ?? Self.defaults["auth_base_url"]!

        Logger.app.info("SecretsManager loaded - API: \(baseURL)")
    }

    // MARK: - Loading

    private static func loadSecrets() -> [String: String] {
        // Try to load from bundle first (secrets.json)
        if let url = Bundle.main.url(forResource: "secrets", withExtension: "json") {
            do {
                let data = try Data(contentsOf: url)
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: String] {
                    Logger.app.info("Loaded secrets from secrets.json")
                    return json
                }
            } catch {
                Logger.app.warning("Failed to parse secrets.json: \(error.localizedDescription)")
            }
        }

        // Fallback: try secrets.json.sample (for development)
        if let url = Bundle.main.url(forResource: "secrets.json", withExtension: "sample") {
            do {
                let data = try Data(contentsOf: url)
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: String] {
                    Logger.app.warning("Using secrets.json.sample - copy to secrets.json for production")
                    return json
                }
            } catch {
                Logger.app.warning("Failed to parse secrets.json.sample: \(error.localizedDescription)")
            }
        }

        Logger.app.warning("No secrets.json found - using defaults")
        return [:]
    }

    // MARK: - Convenience URLs

    var apiBaseURLValue: URL? {
        URL(string: apiBaseURL)
    }
}
