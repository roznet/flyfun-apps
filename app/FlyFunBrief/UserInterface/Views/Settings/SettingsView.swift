//
//  SettingsView.swift
//  FlyFunBrief
//
//  User settings and preferences view.
//

import SwiftUI
import AuthenticationServices

/// Settings view for app preferences
struct SettingsView: View {
    @Environment(\.appState) private var appState

    var body: some View {
        Form {
            // Account
            Section("Account") {
                if let auth = appState?.auth, auth.isAuthenticated {
                    HStack {
                        Image(systemName: auth.currentUser?.providerIcon ?? "person.crop.circle.fill")
                            .foregroundStyle(.green)
                        VStack(alignment: .leading) {
                            Text(auth.currentUser?.displayName ?? "Signed In")
                                .font(.body)
                            if let email = auth.currentUser?.email {
                                Text(email)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    Button(role: .destructive) {
                        auth.signOut()
                    } label: {
                        Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                } else {
                    Text("Sign in to fetch live NOTAMs for your route via the Autorouter API.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        Task {
                            if case .success(let authorization) = result {
                                try? await appState?.auth.handleAppleAuthorization(authorization)
                            }
                        }
                    }
                    .signInWithAppleButtonStyle(.black)
                    .frame(height: 44)

                    Button {
                        Task {
                            do {
                                try await appState?.auth.signInWithGoogle()
                            } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
                                // User cancelled — no error to show
                            } catch {
                                appState?.auth.authError = error.localizedDescription
                            }
                        }
                    } label: {
                        Text("Sign in with Google")
                            .fontWeight(.medium)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background {
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.primary.opacity(0.3), lineWidth: 1)
                        }
                    }
                    .buttonStyle(.plain)

                    if let error = appState?.auth.authError {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
            }

            // Priority Profile
            Section("Priority Profile") {
                Picker("Profile", selection: profileBinding) {
                    ForEach(PriorityProfiles.all) { profile in
                        Text(profile.displayName).tag(profile.id)
                    }
                }

                if let profile = appState?.settings.priorityProfile {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(profile.levels), id: \.self) { level in
                            if let desc = profile.levelDescriptions[level] {
                                HStack(alignment: .top, spacing: 8) {
                                    let priority = NotamPriority(level: level, maxLevel: profile.maxLevel)
                                    Text(priority.label)
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(priority.color)
                                        .frame(width: 28, alignment: .leading)
                                    Text(desc)
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }

                Text("Determines how NOTAMs are prioritized based on flight type.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Display Settings
            Section("Display") {
                Toggle("Show Raw NOTAM Text", isOn: showRawTextBinding)

                Toggle("Show NOTAM Map", isOn: showNotamMapBinding)

                Picker("Default Grouping", selection: defaultGroupingBinding) {
                    ForEach(NotamGrouping.allCases) { grouping in
                        Text(grouping.rawValue).tag(grouping)
                    }
                }
            }

            // Behavior Settings
            Section("Behavior") {
                Toggle("Auto-Mark as Read", isOn: autoMarkAsReadBinding)

                Text("Automatically mark NOTAMs as read when viewing details.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // API Settings
            Section("Server") {
                TextField("API URL", text: apiURLBinding)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)

                Text("URL of the FlyFun server for briefing parsing.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // About
            Section("About") {
                HStack {
                    Text("Version")
                    Spacer()
                    Text(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Text("Build")
                    Spacer()
                    Text(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1")
                        .foregroundStyle(.secondary)
                }

                Link(destination: URL(string: "https://flyfun.aero")!) {
                    Label("FlyFun Website", systemImage: "globe")
                }
            }

            // Reset
            Section {
                Button(role: .destructive) {
                    appState?.settings.resetToDefaults()
                } label: {
                    Label("Reset to Defaults", systemImage: "arrow.counterclockwise")
                }
            }
        }
        .navigationTitle("Settings")
    }

    // MARK: - Bindings

    private var showRawTextBinding: Binding<Bool> {
        Binding(
            get: { appState?.settings.showRawText ?? true },
            set: { appState?.settings.showRawText = $0 }
        )
    }

    private var showNotamMapBinding: Binding<Bool> {
        Binding(
            get: { appState?.settings.showNotamMap ?? true },
            set: { appState?.settings.showNotamMap = $0 }
        )
    }

    private var autoMarkAsReadBinding: Binding<Bool> {
        Binding(
            get: { appState?.settings.autoMarkAsRead ?? false },
            set: { appState?.settings.autoMarkAsRead = $0 }
        )
    }

    private var defaultGroupingBinding: Binding<NotamGrouping> {
        Binding(
            get: { appState?.settings.defaultGrouping ?? .airport },
            set: { appState?.settings.defaultGrouping = $0 }
        )
    }

    private var profileBinding: Binding<String> {
        Binding(
            get: { appState?.settings.priorityProfileId ?? PriorityProfiles.default.id },
            set: { appState?.settings.priorityProfileId = $0 }
        )
    }

    private var apiURLBinding: Binding<String> {
        Binding(
            get: { appState?.settings.apiBaseURL ?? "" },
            set: { appState?.settings.apiBaseURL = $0 }
        )
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        SettingsView()
    }
    .environment(\.appState, AppState.preview())
}
