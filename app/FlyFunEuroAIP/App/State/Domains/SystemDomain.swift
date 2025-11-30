//
//  SystemDomain.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import OSLog
import RZUtilsSwift

/// Domain: Connectivity, loading, errors, app-wide concerns
/// This is a composed part of AppState, not a standalone ViewModel.
@Observable
@MainActor
final class SystemDomain {
    // MARK: - Dependencies
    private let connectivityMonitor: ConnectivityMonitor
    
    // MARK: - State
    var connectivityMode: ConnectivityMode = .offline
    var isLoading: Bool = false
    var error: AppError?
    
    // MARK: - Init
    
    init(connectivityMonitor: ConnectivityMonitor) {
        self.connectivityMonitor = connectivityMonitor
    }
    
    // MARK: - Actions
    
    func startMonitoring() {
        connectivityMonitor.startMonitoring()
        
        Task {
            for await mode in connectivityMonitor.modeStream {
                self.connectivityMode = mode
                Logger.app.info("Connectivity changed: \(mode.rawValue)")
            }
        }
    }
    
    func stopMonitoring() {
        connectivityMonitor.stopMonitoring()
    }
    
    func setLoading(_ loading: Bool) {
        isLoading = loading
    }
    
    func setError(_ error: Error?) {
        if let error = error {
            let appError = AppError(from: error)
            self.error = appError
            Logger.app.error("App error: \(appError.localizedDescription)")
        } else {
            self.error = nil
        }
    }
    
    func clearError() {
        error = nil
    }
    
    // MARK: - Computed
    
    var isOnline: Bool {
        connectivityMode != .offline
    }
    
    var hasError: Bool {
        error != nil
    }
}

