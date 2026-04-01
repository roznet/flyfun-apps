//
//  AuthenticationService.swift
//  FlyFunBrief
//
//  Handles authentication via Apple Sign-In and Google OAuth.
//  Google uses ASWebAuthenticationSession with server-side OAuth flow.
//

import Foundation
import AuthenticationServices
import OSLog
import Observation

/// Service for handling authentication (Apple Sign-In + Google OAuth)
@MainActor
@Observable
final class AuthenticationService: NSObject {

    // MARK: - Observable Properties

    private(set) var isAuthenticated = false
    private(set) var currentUser: AuthUser?
    private(set) var authError: String?
    private(set) var isLoading = false

    // MARK: - Configuration

    /// FlyFunBrief API server (briefing endpoints)
    private let backendURL: String
    /// OAuth server (shared flyfun-common auth, e.g. forms.flyfun.aero)
    private let authURL: String
    private let logger = Logger(subsystem: "net.ro-z.FlyFunBrief", category: "Auth")

    /// URL scheme for OAuth callback redirect
    private let callbackScheme = "flyfunbrief"

    /// Retained so the session isn't deallocated before the callback fires
    private var authSession: ASWebAuthenticationSession?

    // Keychain keys
    private let keychainServiceToken = "net.ro-z.FlyFunBrief.authToken"
    private let keychainServiceUser = "net.ro-z.FlyFunBrief.authUser"

    /// Callback when auth state changes (token obtained or cleared)
    var onAuthChanged: ((String?) -> Void)?

    // MARK: - Initialization

    init(backendURL: String = SecretsManager.shared.apiBaseURL,
         authURL: String = SecretsManager.shared.authBaseURL) {
        self.backendURL = backendURL
        self.authURL = authURL
        super.init()

        // Check for existing session on init
        Task {
            await checkExistingSession()
        }
    }

    // MARK: - Public Properties

    /// The current session token (JWT), if authenticated
    var sessionToken: String? {
        guard let data = loadFromKeychain(service: keychainServiceToken, account: "sessionToken") else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    // MARK: - Apple Sign-In

    /// Handle an authorization from SignInWithAppleButton
    func handleAppleAuthorization(_ authorization: ASAuthorization) async throws {
        isLoading = true
        authError = nil

        defer { isLoading = false }

        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            throw AuthError.invalidCredential
        }

        let userId = credential.user
        let email = credential.email
        let firstName = credential.fullName?.givenName
        let lastName = credential.fullName?.familyName

        guard let identityTokenData = credential.identityToken,
              let identityToken = String(data: identityTokenData, encoding: .utf8) else {
            throw AuthError.missingToken
        }

        let authorizationCode: String?
        if let codeData = credential.authorizationCode {
            authorizationCode = String(data: codeData, encoding: .utf8)
        } else {
            authorizationCode = nil
        }

        // Create user object — Apple only provides email on first auth
        var user = AuthUser(userId: userId, email: email, firstName: firstName, lastName: lastName, provider: .apple)

        // For returning users, restore email from Keychain
        if email == nil,
           let storedData = loadFromKeychain(service: keychainServiceUser, account: "authUser"),
           let storedUser = try? JSONDecoder().decode(AuthUser.self, from: storedData),
           storedUser.provider == .apple {
            user = AuthUser(
                userId: userId,
                email: storedUser.email,
                firstName: storedUser.firstName ?? firstName,
                lastName: storedUser.lastName ?? lastName,
                provider: .apple
            )
        }

        logger.info("Apple Sign-In successful for user")

        // Persist user data
        if let userData = try? JSONEncoder().encode(user) {
            saveToKeychain(service: keychainServiceUser, account: "authUser", data: userData)
        }

        // Exchange token with backend to get session JWT
        if let code = authorizationCode {
            do {
                try await exchangeAppleTokenWithBackend(
                    identityToken: identityToken,
                    authorizationCode: code,
                    user: user
                )
            } catch {
                logger.warning("Backend token exchange failed: \(error.localizedDescription)")
            }
        }

        currentUser = user
        isAuthenticated = true
        onAuthChanged?(sessionToken)
    }

    // MARK: - Google Sign-In

    /// Start Google OAuth flow via ASWebAuthenticationSession.
    /// Cancellation (user dismisses browser) is silently ignored.
    /// Other errors are stored in ``authError``.
    func signInWithGoogle() async {
        isLoading = true
        authError = nil

        defer {
            isLoading = false
            authSession = nil
        }

        var components = URLComponents(string: "\(authURL)/auth/login/google")!
        components.queryItems = [
            URLQueryItem(name: "platform", value: "ios"),
            URLQueryItem(name: "scheme", value: callbackScheme)
        ]

        guard let loginURL = components.url else {
            authError = AuthError.invalidURL.localizedDescription
            return
        }

        logger.info("Starting Google OAuth flow")

        let callbackURL: URL
        do {
            callbackURL = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URL, Error>) in
                let session = ASWebAuthenticationSession(
                    url: loginURL,
                    callback: .customScheme(callbackScheme)
                ) { url, error in
                    if let error {
                        continuation.resume(throwing: error)
                    } else if let url {
                        continuation.resume(returning: url)
                    } else {
                        continuation.resume(throwing: AuthError.missingToken)
                    }
                }
                session.presentationContextProvider = self
                session.prefersEphemeralWebBrowserSession = false
                self.authSession = session
                session.start()
            }
        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            // User cancelled the browser — not an error
            return
        } catch {
            authError = error.localizedDescription
            return
        }

        guard let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false),
              let token = components.queryItems?.first(where: { $0.name == "token" })?.value,
              !token.isEmpty else {
            logger.error("No token in callback URL: \(callbackURL)")
            authError = AuthError.missingToken.localizedDescription
            return
        }

        do {
            // Fetch user info before persisting anything — if this fails,
            // we don't leave an orphaned token in Keychain
            let user = try await fetchUserInfo(token: token)

            // Persist token and user together
            saveToKeychain(service: keychainServiceToken, account: "sessionToken", data: Data(token.utf8))
            if let userData = try? JSONEncoder().encode(user) {
                saveToKeychain(service: keychainServiceUser, account: "authUser", data: userData)
            }
            logger.info("Google OAuth: signed in successfully")

            currentUser = user
            isAuthenticated = true
            onAuthChanged?(sessionToken)
        } catch {
            logger.error("Google OAuth failed: \(error.localizedDescription)")
            authError = error.localizedDescription
        }
    }

    // MARK: - Sign Out

    /// Sign out and clear stored credentials
    func signOut() {
        logger.info("Signing out user")

        deleteFromKeychain(service: keychainServiceToken, account: "sessionToken")
        deleteFromKeychain(service: keychainServiceUser, account: "authUser")

        currentUser = nil
        isAuthenticated = false
        authError = nil
        onAuthChanged?(nil)

        Task { await notifyBackendSignOut() }
    }

    // MARK: - Credential Validation

    /// Check if user's Apple ID credentials are still valid
    func checkCredentialState() async {
        guard let user = currentUser, user.provider == .apple else { return }

        let provider = ASAuthorizationAppleIDProvider()
        do {
            let state = try await provider.credentialState(forUserID: user.userId)
            switch state {
            case .authorized:
                logger.debug("Apple ID credential is valid")
            case .revoked, .notFound:
                logger.warning("Apple ID credential revoked or not found, signing out")
                signOut()
            case .transferred:
                logger.info("Apple ID credential transferred")
            @unknown default:
                break
            }
        } catch {
            logger.error("Failed to check credential state: \(error.localizedDescription)")
        }
    }

    // MARK: - Private Methods

    private func checkExistingSession() async {
        var userData = loadFromKeychain(service: keychainServiceUser, account: "authUser")

        // Migrate from legacy "appleUser" key if needed
        if userData == nil,
           let legacyData = loadFromKeychain(service: keychainServiceUser, account: "appleUser") {
            userData = legacyData
            saveToKeychain(service: keychainServiceUser, account: "authUser", data: legacyData)
            deleteFromKeychain(service: keychainServiceUser, account: "appleUser")
            logger.info("Migrated session from legacy Keychain key")
        }

        guard let userData,
              let user = try? JSONDecoder().decode(AuthUser.self, from: userData) else {
            return
        }

        self.currentUser = user
        self.isAuthenticated = true
        logger.info("Restored existing session (\(user.provider.rawValue))")

        // Notify so BriefingService gets the token
        onAuthChanged?(sessionToken)

        if user.provider == .apple {
            await checkCredentialState()
        } else if user.provider == .google, let token = sessionToken {
            // Validate Google token is still valid
            do {
                _ = try await fetchUserInfo(token: token, provider: .google)
                logger.debug("Google session token is valid")
            } catch {
                logger.warning("Google session token expired, signing out")
                signOut()
            }
        }
    }

    /// Fetch user info from /auth/me using a JWT token
    private func fetchUserInfo(token: String, provider: AuthProvider = .google) async throws -> AuthUser {
        guard let url = URL(string: "\(authURL)/auth/me") else {
            throw AuthError.invalidURL
        }

        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw AuthError.invalidResponse
        }

        let meResponse = try JSONDecoder().decode(AuthMeResponse.self, from: data)

        guard !meResponse.id.isEmpty else {
            throw AuthError.invalidResponse
        }

        // Split name into first/last
        let nameParts = meResponse.name?.split(separator: " ", maxSplits: 1)
        let firstName = nameParts?.first.map(String.init)
        let lastName = nameParts?.count ?? 0 > 1 ? String(nameParts![1]) : nil

        return AuthUser(userId: meResponse.id, email: meResponse.email, firstName: firstName, lastName: lastName, provider: provider)
    }

    private func exchangeAppleTokenWithBackend(
        identityToken: String,
        authorizationCode: String,
        user: AuthUser
    ) async throws {
        guard let url = URL(string: "\(authURL)/auth/apple/token") else {
            throw AuthError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "identity_token": identityToken,
            "authorization_code": authorizationCode,
            "user": [
                "user_id": user.userId,
                "email": user.email as Any,
                "first_name": user.firstName as Any,
                "last_name": user.lastName as Any
            ]
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            logger.error("Backend auth failed with status: \(httpResponse.statusCode)")
            throw AuthError.backendError(httpResponse.statusCode)
        }

        // Parse response for session token
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let token = json["session_token"] as? String {
            saveToKeychain(service: keychainServiceToken, account: "sessionToken", data: Data(token.utf8))
            logger.info("Successfully exchanged token with backend")
        }
    }

    private func notifyBackendSignOut() async {
        guard let url = URL(string: "\(authURL)/auth/logout") else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        if let token = sessionToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        do {
            let _ = try await URLSession.shared.data(for: request)
        } catch {
            logger.warning("Failed to notify backend of sign out: \(error.localizedDescription)")
        }
    }

    // MARK: - Keychain Helpers

    private func saveToKeychain(service: String, account: String, data: Data) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: data
        ]
        SecItemDelete(query as CFDictionary)
        let status = SecItemAdd(query as CFDictionary, nil)
        if status != errSecSuccess {
            logger.warning("Failed to save to keychain: \(status)")
        }
    }

    private func loadFromKeychain(service: String, account: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess else { return nil }
        return result as? Data
    }

    private func deleteFromKeychain(service: String, account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}

// MARK: - ASWebAuthenticationPresentationContextProviding

extension AuthenticationService: ASWebAuthenticationPresentationContextProviding {
    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        MainActor.assumeIsolated {
            guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                  let window = scene.windows.first(where: \.isKeyWindow) else {
                return ASPresentationAnchor()
            }
            return window
        }
    }
}

// MARK: - Supporting Types

/// Authentication provider
enum AuthProvider: String, Codable {
    case apple
    case google
}

/// User data from authentication (Apple or Google)
struct AuthUser: Codable, Equatable {
    let userId: String
    let email: String?
    let firstName: String?
    let lastName: String?
    let provider: AuthProvider

    var displayName: String {
        if let first = firstName, let last = lastName {
            return "\(first) \(last)"
        } else if let first = firstName {
            return first
        } else if let email = email {
            return email
        } else {
            return provider == .apple ? "Apple User" : "Google User"
        }
    }

    var providerIcon: String {
        switch provider {
        case .apple: return "apple.logo"
        case .google: return "g.circle.fill"
        }
    }
}

/// Response from /auth/me endpoint
private struct AuthMeResponse: Decodable {
    let id: String
    let email: String?
    let name: String?
}

/// Authentication errors
enum AuthError: LocalizedError {
    case invalidCredential
    case missingToken
    case invalidURL
    case invalidResponse
    case backendError(Int)
    case notAuthenticated

    var errorDescription: String? {
        switch self {
        case .invalidCredential:
            return "Invalid credential"
        case .missingToken:
            return "Missing identity token"
        case .invalidURL:
            return "Invalid backend URL"
        case .invalidResponse:
            return "Invalid backend response"
        case .backendError(let code):
            return "Backend error: \(code)"
        case .notAuthenticated:
            return "Sign in required to fetch live NOTAMs"
        }
    }
}
