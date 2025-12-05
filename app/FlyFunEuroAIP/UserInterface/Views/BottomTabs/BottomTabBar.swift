//
//  BottomTabBar.swift
//  FlyFunEuroAIP
//
//  Bottom tab bar for switching between Airport Info, AIP, and Rules views
//

import SwiftUI
import RZFlight

/// Bottom tab bar that shows airport detail information in tabs
struct BottomTabBar: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        Group {
            // Only show if an airport is selected AND tab bar is visible
            if state?.airports.selectedAirport != nil && (state?.navigation.showingBottomTabBar ?? false) {
                VStack(spacing: 0) {
                    // Tab content with close button
                    ZStack(alignment: .topTrailing) {
                        tabContent
                            .frame(height: tabContentHeight)
                        
                        // Close button
                        Button {
                            state?.navigation.hideBottomTabBar()
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.title2)
                                .foregroundStyle(.secondary)
                                .background(.ultraThinMaterial, in: Circle())
                        }
                        .padding(8)
                    }
                    
                    // Tab bar
                    tabBar
                }
                .background(.ultraThinMaterial)
                .transition(.move(edge: .bottom))
            }
        }
        .onAppear {
            // Show tab bar if airport is already selected (e.g., from saved state)
            if state?.airports.selectedAirport != nil {
                state?.navigation.showBottomTabBar()
            }
        }
        .onChange(of: state?.airports.selectedAirport) { oldValue, newValue in
            // Automatically show tab bar when airport is selected
            if newValue != nil {
                state?.navigation.showBottomTabBar()
            }
        }
    }
    
    // MARK: - Tab Content
    
    private var tabContent: some View {
        Group {
            if let airport = state?.airports.selectedAirport {
                switch state?.navigation.selectedBottomTab ?? .airportInfo {
                case .airportInfo:
                    AirportInfoTab(airport: airport)
                case .aip:
                    AIPTab(airport: airport)
                case .rules:
                    RulesTab(airport: airport)
                }
            }
        }
    }
    
    // MARK: - Tab Bar
    
    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(NavigationDomain.BottomTab.allCases) { tab in
                Button {
                    state?.navigation.selectBottomTab(tab)
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: tab.systemImage)
                            .font(.title3)
                        Text(tab.displayName)
                            .font(.caption2)
                    }
                    .frame(maxWidth: .infinity)
                    .foregroundStyle(isSelected(tab) ? .primary : .secondary)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.plain)
            }
        }
        .background(.regularMaterial)
    }
    
    // MARK: - Helpers
    
    private func isSelected(_ tab: NavigationDomain.BottomTab) -> Bool {
        state?.navigation.selectedBottomTab == tab
    }
    
    private var tabContentHeight: CGFloat {
        #if os(macOS)
        400
        #else
        300
        #endif
    }
}

// MARK: - Preview

#Preview {
    BottomTabBar()
        .frame(height: 400)
}

