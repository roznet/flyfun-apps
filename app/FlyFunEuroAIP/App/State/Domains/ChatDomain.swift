//
//  ChatDomain.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation
import OSLog
import RZUtilsSwift

/// Domain: Chat messages and streaming state
/// This is a composed part of AppState, not a standalone ViewModel.
@Observable
@MainActor
final class ChatDomain {
    // MARK: - State
    var messages: [ChatMessage] = []
    var input: String = ""
    var isStreaming: Bool = false
    var currentThinking: String?
    
    // MARK: - Cross-Domain Callback
    /// Called when chat produces a visualization payload
    /// AppState wires this to AirportDomain.applyVisualization
    var onVisualization: ((VisualizationPayload) -> Void)?
    
    // MARK: - Dependencies (will be set later when chatbot service is implemented)
    // private var chatbotService: ChatbotService?
    
    // MARK: - Init
    
    init() {}
    
    // MARK: - Actions
    
    /// Send a message to the chatbot
    func send() async {
        let userMessage = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !userMessage.isEmpty else { return }
        
        // Add user message
        messages.append(ChatMessage(role: .user, content: userMessage))
        input = ""
        
        isStreaming = true
        defer { isStreaming = false }
        
        // TODO: Implement actual chatbot service call
        // For now, add a placeholder response
        Logger.app.info("Chat message sent: \(userMessage)")
        
        // Placeholder response
        try? await Task.sleep(for: .milliseconds(500))
        messages.append(ChatMessage(
            role: .assistant,
            content: "Chat functionality coming soon. You asked: \(userMessage)"
        ))
    }
    
    /// Clear chat history
    func clear() {
        messages = []
        currentThinking = nil
    }
    
    /// Add a message programmatically
    func addMessage(_ message: ChatMessage) {
        messages.append(message)
    }
    
    /// Update the last assistant message (for streaming)
    func updateLastAssistantMessage(_ content: String) {
        guard let lastIndex = messages.lastIndex(where: { $0.role == .assistant }) else {
            messages.append(ChatMessage(role: .assistant, content: content, isStreaming: true))
            return
        }
        messages[lastIndex] = ChatMessage(
            role: .assistant,
            content: content,
            isStreaming: true
        )
    }
    
    /// Finish streaming for the last message
    func finishStreaming() {
        guard let lastIndex = messages.lastIndex(where: { $0.role == .assistant }) else { return }
        var message = messages[lastIndex]
        message = ChatMessage(role: message.role, content: message.content, isStreaming: false)
        messages[lastIndex] = message
        isStreaming = false
    }
}

// MARK: - Chat Message

struct ChatMessage: Identifiable, Equatable, Sendable {
    let id: UUID
    let role: Role
    let content: String
    let timestamp: Date
    let isStreaming: Bool
    
    enum Role: String, Sendable {
        case user
        case assistant
        case system
    }
    
    init(
        id: UUID = UUID(),
        role: Role,
        content: String,
        timestamp: Date = Date(),
        isStreaming: Bool = false
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.isStreaming = isStreaming
    }
}

