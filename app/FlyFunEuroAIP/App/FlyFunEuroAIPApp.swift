//
//  FlyFunEuroAIPApp.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 26/10/2025.
//

import SwiftUI
import RZUtilsSwift
import RZFlight
import FMDB
import OSLog
import MetricKit

@main
struct FlyFunEuroAIPApp: App {
    #if os(iOS)
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    #endif
    @State private var appState: AppState?
    @State private var isInitialized = false
    @State private var initError: AppError?
    
    var body: some Scene {
        WindowGroup {
            Group {
                if let appState = appState {
            ContentView()
                        .environment(\.appState, appState)
                        .task {
                            await appState.onAppear()
                        }
                } else if let error = initError {
                    ErrorView(error: error) {
                        Task { await initialize() }
                    }
                } else {
                    LoadingView()
                        .task {
                            await initialize()
                        }
                }
            }
        }
        #if os(macOS)
        .commands {
            // Replace default menus
            CommandGroup(replacing: .newItem) { }  // Remove "New" - not applicable
            
            // View menu
            CommandMenu("View") {
                if let state = appState {
                    Button("Toggle Filters") { state.navigation.toggleFilters() }
                        .keyboardShortcut("l")
                    Button("Toggle Chat") { state.navigation.toggleChat() }
                        .keyboardShortcut("k")
                    Divider()
                    Picker("Legend Mode", selection: Binding(
                        get: { state.airports.legendMode },
                        set: { state.airports.legendMode = $0 }
                    )) {
                        ForEach(LegendMode.allCases) { mode in
                            Text(mode.rawValue).tag(mode)
                        }
                    }
                }
            }
            
            // Map menu
            CommandMenu("Map") {
                if let state = appState {
                    Button("Clear Route") { state.airports.clearRoute() }
                        .keyboardShortcut(.delete)
                        .disabled(state.airports.activeRoute == nil)
                    Button("Center on Selection") {
                        if let airport = state.airports.selectedAirport {
                            state.airports.focusMap(on: airport.coord)
                        }
                    }
                    .keyboardShortcut("e")
                    .disabled(state.airports.selectedAirport == nil)
                }
            }
        }
        #endif
        
        // TODO: Add Settings scene for macOS once SwiftUI Settings are working
    }
    
    // MARK: - Initialization
    
    @MainActor
    private func initialize() async {
        Logger.app.info("Starting app initialization")
        
        do {
            // Initialize secrets (for API URL, etc.)
            // secrets.json is gitignored - create locally with: {"api_base_url": "http://localhost:8000"}
            Secrets.shared = Secrets(url: Bundle.main.url(forResource: "secrets", withExtension: "json"))
            
            // Configure API URL from secrets (falls back to production)
            if let apiURL = Secrets.shared["api_base_url"] {
                AirportRepository.apiBaseURL = apiURL
                Logger.app.info("API URL from secrets: \(apiURL)")
            } else {
                Logger.app.info("Using default API URL: \(AirportRepository.apiBaseURL)")
            }
            
            // Initialize database
            guard let dbPath = Bundle.main.path(forResource: "airports", ofType: "db") else {
                throw AppError.databaseOpenFailed(path: "airports.db not found in bundle")
            }
            
            let localDataSource = try LocalAirportDataSource(databasePath: dbPath)
            let connectivityMonitor = ConnectivityMonitor()
            let repository = AirportRepository(
                localDataSource: localDataSource,
                connectivityMonitor: connectivityMonitor
            )
            
            let appState = AppState(
                repository: repository,
                connectivityMonitor: connectivityMonitor
            )
            
            // Configure chatbot with API URL
            appState.configureChatbot(baseURL: AirportRepository.apiBaseURL)
            
            // Configure offline chatbot for on-device inference
            await appState.configureOfflineChatbot(airportDataSource: localDataSource)
            
            self.appState = appState
            
            Logger.app.info("App initialization complete")
        } catch {
            Logger.app.error("App initialization failed: \(error.localizedDescription)")
            self.initError = AppError(from: error)
        }
    }
}

// MARK: - App Delegate (for MetricKit - iOS only)

#if os(iOS)
import UIKit

class AppDelegate: NSObject, UIApplicationDelegate, MXMetricManagerSubscriber {
    
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        // Subscribe to MetricKit for crash reporting
        MXMetricManager.shared.add(self)
        Logger.app.info("MetricKit subscriber added")
        return true
    }
    
    func didReceive(_ payloads: [MXMetricPayload]) {
        for payload in payloads {
            Logger.app.info("Received metrics payload: \(payload.timeStampBegin) - \(payload.timeStampEnd)")
        }
    }
    
    func didReceive(_ payloads: [MXDiagnosticPayload]) {
        for payload in payloads {
            if let crashDiagnostics = payload.crashDiagnostics {
                for crash in crashDiagnostics {
                    Logger.app.error("Crash diagnostic: \(crash.terminationReason ?? "unknown")")
                }
            }
        }
    }
}
#endif

// MARK: - Loading View

struct LoadingView: View {
    var body: some View {
        VStack(spacing: 20) {
            ProgressView()
                .scaleEffect(1.5)
            Text("Loading airports...")
                .font(.headline)
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Error View

struct ErrorView: View {
    let error: AppError
    let retry: () -> Void
    
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 60))
                .foregroundStyle(.red)
            
            Text("Failed to Load")
                .font(.title)
            
            Text(error.localizedDescription)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
            
            if let suggestion = error.recoverySuggestion {
                Text(suggestion)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            
            Button("Try Again", action: retry)
                .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}

// MARK: - Placeholder Settings View (will be expanded later)

#if os(macOS)
struct SettingsView: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Form {
            if let settings = state?.settings {
                Section("Units") {
                    Picker("Distance", selection: Binding(
                        get: { settings.distanceUnit },
                        set: { settings.distanceUnit = $0 }
                    )) {
                        ForEach(SettingsDomain.DistanceUnit.allCases) { unit in
                            Text(unit.displayName).tag(unit)
                        }
                    }
                    
                    Picker("Altitude", selection: Binding(
                        get: { settings.altitudeUnit },
                        set: { settings.altitudeUnit = $0 }
                    )) {
                        ForEach(SettingsDomain.AltitudeUnit.allCases) { unit in
                            Text(unit.displayName).tag(unit)
                        }
                    }
                }
                
                Section("Behavior") {
                    Toggle("Restore session on launch", isOn: Binding(
                        get: { settings.restoreSessionOnLaunch },
                        set: { settings.restoreSessionOnLaunch = $0 }
                    ))
                    Toggle("Auto-sync database", isOn: Binding(
                        get: { settings.autoSyncDatabase },
                        set: { settings.autoSyncDatabase = $0 }
                    ))
                }
            }
        }
        .padding()
        .frame(width: 400, height: 300)
        }
    }
#endif
