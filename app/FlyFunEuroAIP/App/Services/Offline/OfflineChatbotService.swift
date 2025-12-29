//
//  OfflineChatbotService.swift
//  FlyFunEuroAIP
//
//  Offline chatbot using on-device LLM (MediaPipe) and local tools.
//  Implements the same ChatbotService protocol as OnlineChatbotService.
//  Matches Android OfflineChatClient.kt implementation.
//

import Foundation
import OSLog
import RZUtilsSwift

/// Offline chatbot using on-device LLM and local tools
final class OfflineChatbotService: ChatbotService, @unchecked Sendable {
    
    // MARK: - Dependencies
    
    private let inferenceEngine: InferenceEngine
    private let toolDispatcher: LocalToolDispatcher
    private let modelManager: ModelManager
    
    // MARK: - Configuration
    
    private static let maxToolIterations = 5
    
    private static let systemPrompt = """
    You are FlyFun, an expert aviation planning assistant for European pilots.

    ## Available Tools
    Use JSON format to call tools: {"name": "tool_name", "arguments": {...}}

    - search_airports: Search airports by ICAO code, name, or city
      Parameters: {"query": "search term", "limit": 10}
    
    - get_airport_details: Get detailed information about a specific airport
      Parameters: {"icao": "LFPG"}
    
    - find_airports_near_route: Find airports along a flight route
      Parameters: {"from": "LFPG", "to": "EGLL", "max_distance_nm": 50}
    
    - find_airports_near_location: Find airports near a city or airport, optionally filter by notification
      Parameters: {"location_query": "EDRR", "max_distance_nm": 50, "max_hours_notice": 24}
    
    - get_border_crossing_airports: Get customs/border crossing airports
      Parameters: {"country": "FR"}
    
    - find_airports_by_notification: Find airports ONLY by notification (no location), filter by country
      Parameters: {"max_hours": 24, "country": "DE"}
    
    - list_rules_for_country: Get aviation rules for a country
      Parameters: {"country": "FR"}
    
    - compare_rules_between_countries: Compare rules between two countries
      Parameters: {"country1": "FR", "country2": "DE"}

    **CRITICAL - Tool Selection:**
    
    **LOCATION + NOTIFICATION - Use find_airports_near_location:**
    When user mentions a LOCATION (airport ICAO or city) WITH notification/hours:
    - "Airports near EDRR with less than 24h notice" → {"name": "find_airports_near_location", "arguments": {"location_query": "EDRR", "max_hours_notice": 24}}
    - "Airports near Paris with 24h notice" → {"name": "find_airports_near_location", "arguments": {"location_query": "Paris", "max_hours_notice": 24}}
    
    **NOTIFICATION ONLY (no location) - Use find_airports_by_notification:**
    - "Airports with less than 24h notice in Germany" → {"name": "find_airports_by_notification", "arguments": {"max_hours": 24, "country": "DE"}}
    
    **ROUTE QUERIES - Use find_airports_near_route:**
    - "Airports between EGLL and LFPG" → {"name": "find_airports_near_route", "arguments": {"from": "EGLL", "to": "LFPG"}}
    
    **LOCATION ONLY - Use find_airports_near_location:**
    - "Airports near Paris" → {"name": "find_airports_near_location", "arguments": {"location_query": "Paris"}}

    After receiving tool results, provide a helpful answer based on the data.
    Be concise and practical. Focus on information relevant to GA pilots.
    """
    
    // MARK: - Init
    
    init(inferenceEngine: InferenceEngine, toolDispatcher: LocalToolDispatcher, modelManager: ModelManager) {
        self.inferenceEngine = inferenceEngine
        self.toolDispatcher = toolDispatcher
        self.modelManager = modelManager
    }
    
    // MARK: - ChatbotService
    
    func sendMessage(
        _ message: String,
        history: [ChatMessage]
    ) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    try await processChat(message: message, history: history, continuation: continuation)
                } catch {
                    Logger.app.error("Offline chat error: \(error.localizedDescription)")
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    func isAvailable() async -> Bool {
        // Available if model is loaded or can be loaded
        if inferenceEngine.isLoaded {
            return true
        }
        
        // Check if model file exists
        return modelManager.isModelAvailable
    }
    
    // MARK: - Private
    
    private func processChat(
        message: String,
        history: [ChatMessage],
        continuation: AsyncThrowingStream<ChatEvent, Error>.Continuation
    ) async throws {
        // Immediately show thinking indicator
        continuation.yield(.thinking(content: "Starting..."))
        
        // Ensure model is loaded
        if !inferenceEngine.isLoaded {
            let modelPath = modelManager.modelPath
            continuation.yield(.thinking(content: "Loading AI model (this may take a moment)..."))
            try await inferenceEngine.loadModel(at: modelPath)
            continuation.yield(.thinking(content: "Model loaded. Generating response..."))
        } else {
            continuation.yield(.thinking(content: "Generating response..."))
        }
        
        // Build prompt with system instructions, history, and current message
        let prompt = buildPrompt(message: message, history: history)
        
        Logger.app.info("Sending prompt to LLM (\(prompt.count) chars)")
        
        // Generate initial response
        var response = try await inferenceEngine.generate(prompt: prompt)
        continuation.yield(.thinking(content: "Analyzing response..."))
        
        // Track accumulated content for progressive streaming
        var toolSections: [String] = []
        
        // Tool-calling loop
        var toolIteration = 0
        while let toolCall = toolDispatcher.parseToolCall(from: response),
              toolIteration < Self.maxToolIterations {
            
            toolIteration += 1
            Logger.app.info("Tool call \(toolIteration): \(toolCall.name)")
            
            // Emit toolCallStart event
            continuation.yield(.toolCallStart(name: toolCall.name, arguments: toolCall.arguments))
            
            // Format arguments for display (one per line for clarity)
            let argsFormatted = toolCall.arguments.map { "  \($0.key): \($0.value)" }.joined(separator: "\n")
            
            // Build tool header
            let toolHeader = "🔧 **Tool:** \(toolCall.name)\n\n**Arguments:**\n\(argsFormatted)"
            
            // Show executing state
            toolSections.append(toolHeader + "\n\n**Executing...**")
            let executingContent = toolSections.joined(separator: "\n\n━━━━━━━━━━\n\n")
            continuation.yield(.message(content: executingContent))
            
            // Execute tool
            let toolResult = await toolDispatcher.dispatch(request: toolCall)
            
            // Update last section with result (replace last entry in array)
            toolSections[toolSections.count - 1] = toolHeader + "\n\n**Result:**\n\(toolResult.value)"
            let resultContent = toolSections.joined(separator: "\n\n━━━━━━━━━━\n\n")
            continuation.yield(.message(content: resultContent))
            
            // Emit toolCallEnd event
            let resultDict: [String: Any] = ["result": toolResult.value]
            continuation.yield(.toolCallEnd(name: toolCall.name, result: ToolResult(from: resultDict)))
            
            // Build follow-up prompt with tool result
            let followUpPrompt = buildFollowUpPrompt(
                originalMessage: message,
                toolCall: toolCall,
                toolResult: toolResult.value
            )
            
            // Show "Generating..." while waiting
            continuation.yield(.thinking(content: "Processing tool result..."))
            
            // Generate response with tool result
            response = try await inferenceEngine.generate(prompt: followUpPrompt)
        }
        
        // Build final content from tool sections + answer
        var finalContent = ""
        if !toolSections.isEmpty {
            finalContent = toolSections.joined(separator: "\n\n━━━━━━━━━━\n\n")
            finalContent += "\n\n━━━━━━━━━━\n\n💬 **Answer:**\n\n"
        }
        finalContent += response
        
        // Yield final response
        continuation.yield(.message(content: finalContent))
        continuation.yield(.done(sessionId: nil, tokens: nil))
        continuation.finish()
    }
    
    private func buildPrompt(message: String, history: [ChatMessage]) -> String {
        var prompt = Self.systemPrompt + "\n\n"
        
        // Add history (last few turns)
        let recentHistory = history.suffix(6)
        for msg in recentHistory {
            let role = msg.role == .user ? "User" : "Assistant"
            prompt += "\(role): \(msg.content)\n"
        }
        
        // Add current message
        prompt += "User: \(message)\nAssistant:"
        
        return prompt
    }
    
    private func buildFollowUpPrompt(
        originalMessage: String,
        toolCall: LocalToolDispatcher.ToolCallRequest,
        toolResult: String
    ) -> String {
        return """
        User asked: \(originalMessage)
        
        You called the tool "\(toolCall.name)" and received this result:
        
        \(toolResult)
        
        Provide a helpful answer listing the airports from the results.
        Include at least 10 airports (or all if fewer) with ICAO codes and notification hours.
        Use a simple bullet list format. Do NOT create separate sections or repeat airports.
        
        Assistant:
        """
    }
}
