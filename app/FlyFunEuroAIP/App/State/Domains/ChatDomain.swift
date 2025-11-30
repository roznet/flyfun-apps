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
    var currentToolCall: String?
    var error: String?
    
    /// Tools used during current streaming session
    private var toolsUsed: [String] = []
    
    // MARK: - Cross-Domain Callback
    /// Called when chat produces a visualization payload
    /// AppState wires this to AirportDomain.applyVisualization
    var onVisualization: ((ChatVisualizationPayload) -> Void)?
    
    // MARK: - Dependencies
    private var chatbotService: ChatbotService?
    
    // MARK: - Init
    
    init() {}
    
    /// Initialize with a chatbot service
    func configure(service: ChatbotService) {
        self.chatbotService = service
    }
    
    // MARK: - Actions
    
    /// Send a message to the chatbot
    func send() async {
        let userMessage = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !userMessage.isEmpty else { return }
        
        // Check if service is available
        guard let service = chatbotService else {
            Logger.app.warning("Chatbot service not configured")
            addOfflineResponse(for: userMessage)
            return
        }
        
        // Add user message
        messages.append(ChatMessage(role: .user, content: userMessage))
        input = ""
        error = nil
        
        isStreaming = true
        currentThinking = nil
        currentToolCall = nil
        toolsUsed = []  // Reset tools for new message
        
        Logger.app.info("Sending chat message: \(userMessage)")
        
        do {
            // Stream response from service
            var accumulatedContent = ""
            
            for try await event in service.sendMessage(userMessage, history: messages.dropLast()) {
                await handleEvent(event, accumulatedContent: &accumulatedContent)
            }
            
            // Ensure we have a final message
            if !accumulatedContent.isEmpty {
                finishStreaming()
            }
            
        } catch {
            Logger.app.error("Chat error: \(error.localizedDescription)")
            self.error = error.localizedDescription
            messages.append(ChatMessage(
                role: .assistant,
                content: "Sorry, I encountered an error: \(error.localizedDescription)"
            ))
        }
        
        isStreaming = false
        currentThinking = nil
        currentToolCall = nil
    }
    
    /// Handle a streaming event
    private func handleEvent(_ event: ChatEvent, accumulatedContent: inout String) async {
        switch event {
        case .thinking(let content):
            currentThinking = content
            Logger.app.info("Thinking: \(content.prefix(100))...")
            
        case .thinkingDone:
            currentThinking = nil
            
        case .toolCallStart(let name, _):
            currentToolCall = name
            // Track all tools used (avoid duplicates)
            if !toolsUsed.contains(name) {
                toolsUsed.append(name)
            }
            Logger.app.info("Tool call: \(name)")
            
        case .toolCallEnd(let name, _):
            if currentToolCall == name {
                currentToolCall = nil
            }
            
        case .message(let content):
            accumulatedContent += content
            updateLastAssistantMessage(accumulatedContent)
            
        case .uiPayload(let payload):
            Logger.app.info("Received visualization: \(payload.kind.rawValue)")
            onVisualization?(payload)
            
        case .plan(let plan):
            if let tool = plan.selectedTool {
                Logger.app.info("Plan: \(tool)")
            }
            
        case .finalAnswer:
            // Final state received - streaming is complete
            break
            
        case .done(let sessionId, let tokens):
            if let tokens = tokens {
                Logger.app.info("Chat complete. Tokens: \(tokens.total) (session: \(sessionId ?? "unknown"))")
            }
            
        case .error(let message):
            Logger.app.error("Chat error event: \(message)")
            error = message
            
        case .unknown(let event, _):
            Logger.app.warning("Unknown chat event: \(event)")
        }
    }
    
    /// Add a fallback response when offline
    private func addOfflineResponse(for message: String) {
        messages.append(ChatMessage(role: .user, content: message))
        input = ""
        
        // Simple offline response
        let response = """
        I'm currently offline and can't process complex queries. \
        Here are some things you can do:
        
        • Use the search bar to find airports by ICAO or name
        • Use filters to narrow down airports
        • Tap an airport on the map for details
        
        Once you're online, I can help with questions like:
        • "Find airports near London with ILS approaches"
        • "Show me border crossing airports in France"
        • "What procedures does EGLL have?"
        """
        
        messages.append(ChatMessage(role: .assistant, content: response))
    }
    
    /// Clear chat history
    func clear() {
        messages = []
        currentThinking = nil
        currentToolCall = nil
        error = nil
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
        let message = messages[lastIndex]
        // Create final message with tools used
        messages[lastIndex] = ChatMessage(
            role: message.role,
            content: message.content,
            isStreaming: false,
            toolsUsed: toolsUsed
        )
        isStreaming = false
        Logger.app.info("Finished streaming. Tools used: \(toolsUsed)")
    }
}

// MARK: - Chat Message

struct ChatMessage: Identifiable, Equatable, Sendable {
    let id: UUID
    let role: Role
    let content: String
    let timestamp: Date
    let isStreaming: Bool
    let toolsUsed: [String]
    
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
        isStreaming: Bool = false,
        toolsUsed: [String] = []
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.isStreaming = isStreaming
        self.toolsUsed = toolsUsed
    }
}

// MARK: - Array Extension for History

extension Array where Element == ChatMessage {
    /// Convert to format expected by API
    func toAPIFormat() -> [[String: String]] {
        map { msg in
            ["role": msg.role == .user ? "user" : "assistant", "content": msg.content]
        }
    }
}
