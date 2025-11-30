//
//  NavigationDomain.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import SwiftUI

/// Domain: Navigation state (tabs, sheets, paths)
/// This is a composed part of AppState, not a standalone ViewModel.
@Observable
@MainActor
final class NavigationDomain {
    // MARK: - Tab State
    var selectedTab: Tab = .map
    
    // MARK: - Sheet State
    var showingChat: Bool = false
    var showingFilters: Bool = false
    var showingSettings: Bool = false
    var showingAirportDetail: Bool = false
    
    // MARK: - Navigation Path (for programmatic navigation)
    var path = NavigationPath()
    
    // MARK: - Types
    
    enum Tab: String, CaseIterable, Identifiable, Sendable {
        case map = "Map"
        case search = "Search"
        case chat = "Chat"
        case settings = "Settings"
        
        var id: String { rawValue }
        
        var systemImage: String {
            switch self {
            case .map: return "map"
            case .search: return "magnifyingglass"
            case .chat: return "bubble.left.and.bubble.right"
            case .settings: return "gear"
            }
        }
    }
    
    // MARK: - Init
    
    init() {}
    
    // MARK: - Actions
    
    func navigate(to tab: Tab) {
        selectedTab = tab
    }
    
    func showChat() {
        showingChat = true
    }
    
    func hideChat() {
        showingChat = false
    }
    
    func toggleChat() {
        showingChat.toggle()
    }
    
    func showFilters() {
        showingFilters = true
    }
    
    func hideFilters() {
        showingFilters = false
    }
    
    func toggleFilters() {
        showingFilters.toggle()
    }
    
    func showSettings() {
        showingSettings = true
    }
    
    func hideSettings() {
        showingSettings = false
    }
    
    func showAirportDetail() {
        showingAirportDetail = true
    }
    
    func hideAirportDetail() {
        showingAirportDetail = false
    }
    
    // MARK: - Navigation Path
    
    func push<T: Hashable>(_ value: T) {
        path.append(value)
    }
    
    func pop() {
        if !path.isEmpty {
            path.removeLast()
        }
    }
    
    func popToRoot() {
        path = NavigationPath()
    }
}

