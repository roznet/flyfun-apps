//
//  LeftOverlayContainer.swift
//  FlyFunEuroAIP
//
//  Container for left overlay that toggles between Search/Filter and Chat views
//

import SwiftUI

/// Left overlay container that shows either Search/Filter or Chat based on navigation state
struct LeftOverlayContainer: View {
    @Environment(\.appState) private var state
    
    var body: some View {
        VStack(spacing: 0) {
            // Toolbar with toggle button
            overlayToolbar
            
            // Content area - shows either Search or Chat
            Group {
                switch state?.navigation.leftOverlayMode ?? .search {
                case .search:
                    SearchView()
                case .chat:
                    ChatView()
                }
            }
        }
        .frame(width: overlayWidth)
        .background(.ultraThinMaterial)
    }
    
    // MARK: - Toolbar
    
    private var overlayToolbar: some View {
        HStack {
            // Toggle button
            Button {
                state?.navigation.toggleLeftOverlay()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: toggleIcon)
                        .font(.headline)
                    Text(toggleLabel)
                        .font(.subheadline.bold())
                }
                .foregroundStyle(.primary)
            }
            
            Spacer()
            
            // Filter button (only show in search mode)
            if state?.navigation.leftOverlayMode == .search {
                Button {
                    state?.navigation.toggleFilters()
                } label: {
                    Image(systemName: filterIcon)
                        .foregroundStyle(state?.airports.filters.hasActiveFilters == true ? .blue : .secondary)
                }
            }
            
            // Close button (for iPad/Mac - to dismiss overlay)
            Button {
                state?.navigation.hideLeftOverlay()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.regularMaterial)
    }
    
    // MARK: - Computed Properties
    
    private var overlayWidth: CGFloat {
        #if os(macOS)
        400
        #else
        350
        #endif
    }
    
    private var toggleIcon: String {
        state?.navigation.leftOverlayMode == .search
            ? "bubble.left.and.bubble.right"
            : "magnifyingglass"
    }
    
    private var toggleLabel: String {
        state?.navigation.leftOverlayMode == .search
            ? "Chat"
            : "Search"
    }
    
    private var filterIcon: String {
        state?.airports.filters.hasActiveFilters == true
            ? "line.3.horizontal.decrease.circle.fill"
            : "line.3.horizontal.decrease.circle"
    }
}

// MARK: - Preview

#Preview {
    LeftOverlayContainer()
        .frame(height: 600)
}




