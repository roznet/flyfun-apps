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
    
    // MARK: - Left Overlay Mode
    /// Controls what's shown in the left overlay (search/filter or chat)
    var leftOverlayMode: LeftOverlayMode = .search
    /// Whether the left overlay panel is visible (for iPad/Mac - slides in from left)
    var showingLeftOverlay: Bool = false
    
    // MARK: - Bottom Tab State
    /// Selected bottom tab (Airport Info, AIP, Rules)
    var selectedBottomTab: BottomTab = .airportInfo
    /// Whether the bottom tab bar is visible (can be hidden even when airport is selected)
    var showingBottomTabBar: Bool = false
    
    // MARK: - Sheet State
    var showingChat: Bool = false
    var showingSearchSheet: Bool = false
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
    
    enum LeftOverlayMode: String, Sendable {
        case search
        case chat
    }
    
    enum BottomTab: String, CaseIterable, Identifiable, Sendable {
        case airportInfo = "Airport"
        case aip = "AIP"
        case rules = "Rules"
        
        var id: String { rawValue }
        
        var systemImage: String {
            switch self {
            case .airportInfo: return "airplane"
            case .aip: return "doc.text"
            case .rules: return "book"
            }
        }
        
        var displayName: String {
            rawValue
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
    
    func showSearchSheet() {
        showingSearchSheet = true
    }
    
    func hideSearchSheet() {
        showingSearchSheet = false
    }
    
    func toggleSearchSheet() {
        showingSearchSheet.toggle()
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
    
    // MARK: - Left Overlay Actions
    
    func toggleLeftOverlay() {
        leftOverlayMode = leftOverlayMode == .search ? .chat : .search
    }
    
    func showSearchInLeftOverlay() {
        leftOverlayMode = .search
        showingLeftOverlay = true
    }
    
    func showChatInLeftOverlay() {
        leftOverlayMode = .chat
        showingLeftOverlay = true
    }
    
    func showLeftOverlay() {
        showingLeftOverlay = true
    }
    
    func hideLeftOverlay() {
        showingLeftOverlay = false
    }
    
    func toggleLeftOverlayVisibility() {
        showingLeftOverlay.toggle()
    }
    
    // MARK: - Bottom Tab Actions
    
    func selectBottomTab(_ tab: BottomTab) {
        selectedBottomTab = tab
    }
    
    func showBottomTabBar() {
        showingBottomTabBar = true
    }
    
    func hideBottomTabBar() {
        showingBottomTabBar = false
    }
    
    func toggleBottomTabBar() {
        showingBottomTabBar.toggle()
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

