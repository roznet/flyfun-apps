//
//  ConnectivityMonitor.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import Network
import OSLog
import RZUtilsSwift

/// Monitors network connectivity and publishes state changes
@Observable
@MainActor
final class ConnectivityMonitor {
    // MARK: - State
    var isConnected: Bool = false
    var connectionType: ConnectionType = .none
    var mode: ConnectivityMode {
        isConnected ? .online : .offline
    }
    
    // MARK: - Types
    enum ConnectionType: String, Sendable {
        case none
        case wifi
        case cellular
        case wired
    }
    
    // MARK: - Private
    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "net.ro-z.flyfun.connectivity")
    
    // MARK: - Init
    init() {}
    
    // MARK: - Actions
    
    /// Start monitoring network changes
    func startMonitoring() {
        Logger.net.info("Starting connectivity monitoring")
        
        monitor.pathUpdateHandler = { [weak self] path in
            Task { @MainActor in
                self?.handlePathUpdate(path)
            }
        }
        monitor.start(queue: queue)
    }
    
    /// Stop monitoring (call when app enters background)
    func stopMonitoring() {
        Logger.net.info("Stopping connectivity monitoring")
        monitor.cancel()
    }
    
    // MARK: - Private
    
    private func handlePathUpdate(_ path: NWPath) {
        let wasConnected = isConnected
        isConnected = path.status == .satisfied
        connectionType = mapConnectionType(path)
        
        if wasConnected != isConnected {
            Logger.net.info("Connectivity changed: \(self.isConnected ? "online" : "offline") via \(self.connectionType.rawValue)")
        }
    }
    
    private func mapConnectionType(_ path: NWPath) -> ConnectionType {
        if path.usesInterfaceType(.wifi) { return .wifi }
        if path.usesInterfaceType(.cellular) { return .cellular }
        if path.usesInterfaceType(.wiredEthernet) { return .wired }
        return .none
    }
    
    // MARK: - Async Stream (for domain observation)
    
    /// Async stream of connectivity mode changes
    var modeStream: AsyncStream<ConnectivityMode> {
        AsyncStream { continuation in
            // Yield current state immediately
            continuation.yield(mode)
            
            // Set up path handler to yield changes
            let monitor = NWPathMonitor()
            monitor.pathUpdateHandler = { path in
                let newMode: ConnectivityMode = path.status == .satisfied ? .online : .offline
                continuation.yield(newMode)
            }
            monitor.start(queue: DispatchQueue(label: "net.ro-z.flyfun.connectivity.stream"))
            
            continuation.onTermination = { _ in
                monitor.cancel()
            }
        }
    }
}

