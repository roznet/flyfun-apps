//
//  FlyFunBriefApp.swift
//  FlyFunBrief
//
//  iOS app for reviewing ForeFlight briefings with NOTAM management.
//

import SwiftUI
import OSLog

@main
struct FlyFunBriefApp: App {

    @State private var appState = AppState()

    /// App Group identifier for sharing data with extension
    private let appGroupId = "group.net.ro-z.flyfunbrief"

    /// UserDefaults key for pending import path
    private let pendingImportKey = "pendingBriefingImportPath"

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.appState, appState)
                .onOpenURL { url in
                    handleOpenURL(url)
                }
        }
    }

    /// Handle URLs opened via deep link or "Open In"
    /// Supports:
    /// - flyfunbrief://import?path=<encoded-file-path> (from share extension)
    /// - file://<path-to-pdf> (from "Open In" / document handler)
    private func handleOpenURL(_ url: URL) {
        Logger.app.info("Received URL: \(url.absoluteString)")

        // Handle file:// URLs (from "Open In" document handler)
        if url.isFileURL {
            // Check if it's a PDF
            guard url.pathExtension.lowercased() == "pdf" else {
                Logger.app.warning("Ignoring non-PDF file: \(url.lastPathComponent)")
                return
            }

            // Need to access security-scoped resource for files from other apps
            let accessing = url.startAccessingSecurityScopedResource()
            defer {
                if accessing {
                    url.stopAccessingSecurityScopedResource()
                }
            }

            importBriefing(from: url)
            return
        }

        // Handle flyfunbrief:// deep links
        guard url.scheme == "flyfunbrief" else {
            Logger.app.warning("Unknown URL scheme: \(url.scheme ?? "nil")")
            return
        }

        // Import deep link (flyfunbrief://import?path=...)
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let pathParam = components.queryItems?.first(where: { $0.name == "path" })?.value,
              !pathParam.isEmpty else {
            Logger.app.error("Invalid deep link - missing path parameter: \(url.absoluteString)")
            return
        }

        importBriefing(fromPath: pathParam)
    }

    /// Check for pending imports from share extension (fallback mechanism)
    func checkForPendingImports() {
        guard let defaults = UserDefaults(suiteName: appGroupId) else {
            Logger.app.warning("Could not access shared UserDefaults")
            return
        }

        guard let pendingPath = defaults.string(forKey: pendingImportKey),
              !pendingPath.isEmpty else {
            return
        }

        Logger.app.info("Found pending import: \(pendingPath)")

        // Clear the pending import immediately to prevent double-import
        defaults.removeObject(forKey: pendingImportKey)
        defaults.synchronize()

        importBriefing(fromPath: pendingPath)
    }

    /// Import briefing from a file path (from share extension)
    private func importBriefing(fromPath path: String) {
        let fileURL = URL(fileURLWithPath: path)

        // Verify file exists
        guard FileManager.default.fileExists(atPath: path) else {
            Logger.app.error("Briefing file not found: \(path)")
            return
        }

        importBriefing(from: fileURL)
    }

    /// Import briefing from a URL (from "Open In" or direct file access)
    private func importBriefing(from url: URL) {
        Logger.app.info("Importing briefing from: \(url.path)")

        Task {
            await appState.briefing.importBriefing(from: url)
        }
    }
}

// MARK: - Content View

struct ContentView: View {
    @Environment(\.appState) private var appState
    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.scenePhase) private var scenePhase

    /// App Group identifier for sharing data with extension
    private let appGroupId = "group.net.ro-z.flyfunbrief"

    /// UserDefaults key for pending import path
    private let pendingImportKey = "pendingBriefingImportPath"

    var body: some View {
        Group {
            if sizeClass == .compact {
                iPhoneLayoutView()
            } else {
                iPadLayoutView()
            }
        }
        .task {
            await appState?.onAppear()

            // Check for pending imports from share extension
            checkForPendingImports()
        }
        .onChange(of: scenePhase) { oldPhase, newPhase in
            // Check for pending imports when app becomes active (returning from background)
            if newPhase == .active {
                Logger.app.debug("App became active - checking for pending imports")
                checkForPendingImports()
            }
        }
    }

    /// Check for pending imports from share extension (fallback mechanism)
    private func checkForPendingImports() {
        guard let defaults = UserDefaults(suiteName: appGroupId) else {
            Logger.app.warning("Could not access shared UserDefaults")
            return
        }

        guard let pendingPath = defaults.string(forKey: pendingImportKey),
              !pendingPath.isEmpty else {
            return
        }

        Logger.app.info("Found pending import: \(pendingPath)")

        // Clear the pending import immediately to prevent double-import
        defaults.removeObject(forKey: pendingImportKey)
        defaults.synchronize()

        // Verify file exists
        guard FileManager.default.fileExists(atPath: pendingPath) else {
            Logger.app.error("Briefing file not found: \(pendingPath)")
            return
        }

        let fileURL = URL(fileURLWithPath: pendingPath)
        Logger.app.info("Importing briefing from: \(fileURL.path)")

        Task {
            await appState?.briefing.importBriefing(from: fileURL)
        }
    }
}

// MARK: - Logger Extension

extension Logger {
    static let app = Logger(subsystem: "com.ro-z.flyfunbrief", category: "app")
    static let network = Logger(subsystem: "com.ro-z.flyfunbrief", category: "network")
    static let ui = Logger(subsystem: "com.ro-z.flyfunbrief", category: "ui")
}
