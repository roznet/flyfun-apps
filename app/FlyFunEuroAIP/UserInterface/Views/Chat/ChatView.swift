//
//  ChatView.swift
//  FlyFunEuroAIP
//
//  Main chat interface for the aviation agent.
//

import SwiftUI

struct ChatView: View {
    @Environment(\.appState) private var state
    @FocusState private var isInputFocused: Bool
    
    var body: some View {
        VStack(spacing: 0) {
            // Messages list
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        // Welcome message if empty
                        if let chat = state?.chat, chat.messages.isEmpty {
                            WelcomeView()
                                .padding(.top, 40)
                        }
                        
                        // Messages
                        if let messages = state?.chat.messages {
                            ForEach(messages) { message in
                                ChatBubble(message: message)
                                    .id(message.id)
                            }
                        }
                        
                        // Thinking indicator
                        if let chat = state?.chat {
                            if chat.isStreaming {
                                ThinkingIndicator(
                                    thinking: chat.currentThinking,
                                    toolCall: chat.currentToolCall
                                )
                                .id("thinking")
                            }
                        }
                    }
                    .padding()
                }
                .onChange(of: state?.chat.messages.count) { _, _ in
                    // Scroll to bottom when new messages arrive
                    withAnimation {
                        if let lastMessage = state?.chat.messages.last {
                            proxy.scrollTo(lastMessage.id, anchor: .bottom)
                        }
                    }
                }
                .onChange(of: state?.chat.isStreaming) { _, isStreaming in
                    if isStreaming == true {
                        withAnimation {
                            proxy.scrollTo("thinking", anchor: .bottom)
                        }
                    }
                }
            }
            
            Divider()
            
            // Input bar
            ChatInputBar(
                text: Binding(
                    get: { state?.chat.input ?? "" },
                    set: { state?.chat.input = $0 }
                ),
                isStreaming: state?.chat.isStreaming ?? false,
                onSend: {
                    Task {
                        await state?.chat.send()
                    }
                }
            )
            .focused($isInputFocused)
        }
        // Only show navigation title/toolbar when in a NavigationStack (not in overlay)
        .navigationTitle("Assistant")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                // Offline mode toggle
                Button {
                    state?.chat.setOfflineMode(!(state?.chat.isOfflineMode ?? false))
                } label: {
                    Label(
                        state?.chat.isOfflineMode == true ? "Offline" : "Online",
                        systemImage: state?.chat.isOfflineMode == true ? "airplane.circle.fill" : "cloud.fill"
                    )
                    .foregroundStyle(state?.chat.isOfflineMode == true ? .orange : .blue)
                }
            }
            
            ToolbarItem(placement: .primaryAction) {
                Button {
                    state?.chat.clear()
                } label: {
                    Image(systemName: "trash")
                }
                .disabled(state?.chat.messages.isEmpty ?? true)
            }
        }
    }
}

// MARK: - Welcome View

struct WelcomeView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "airplane.circle.fill")
                .font(.system(size: 60))
                .foregroundStyle(.blue)
            
            Text("Aviation Assistant")
                .font(.title2.bold())
            
            Text("Ask me about airports, procedures, routes, and more!")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            
            // Example queries
            VStack(alignment: .leading, spacing: 8) {
                Text("Try asking:")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                
                ExampleQueryButton(text: "Find airports with ILS near London")
                ExampleQueryButton(text: "Border crossing airports in France")
                ExampleQueryButton(text: "Show me airports along EGLL to LFPG")
            }
            .padding(.top, 8)
        }
        .padding()
    }
}

struct ExampleQueryButton: View {
    @Environment(\.appState) private var state
    let text: String
    
    var body: some View {
        Button {
            state?.chat.input = text
        } label: {
            HStack {
                Image(systemName: "text.bubble")
                    .font(.caption)
                Text(text)
                    .font(.caption)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.blue.opacity(0.1))
            .foregroundStyle(.blue)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        ChatView()
    }
}

