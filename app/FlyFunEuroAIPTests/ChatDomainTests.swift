//
//  ChatDomainTests.swift
//  FlyFunEuroAIPTests
//
//  Tests for ChatDomain message handling and state management.
//

import Testing
import Foundation
@testable import FlyFunEuroAIP

@MainActor
struct ChatDomainTests {

    // MARK: - Initial State

    @Test func initialStateIsEmpty() {
        let domain = ChatDomain()

        #expect(domain.messages.isEmpty)
        #expect(domain.input.isEmpty)
        #expect(domain.isStreaming == false)
        #expect(domain.currentThinking == nil)
        #expect(domain.currentToolCall == nil)
        #expect(domain.error == nil)
    }

    // MARK: - Message Management

    @Test func clearHistoryRemovesAllMessages() {
        let domain = ChatDomain()

        // Add some messages
        domain.messages = [
            ChatMessage(role: .user, content: "Test"),
            ChatMessage(role: .assistant, content: "Response")
        ]

        #expect(domain.messages.count == 2)

        domain.clear()

        #expect(domain.messages.isEmpty)
    }

    // MARK: - Input State

    @Test func inputCanBeSet() {
        let domain = ChatDomain()

        domain.input = "What's EGLL?"

        #expect(domain.input == "What's EGLL?")
    }

    // MARK: - Streaming State

    @Test func streamingStateCanBeSet() {
        let domain = ChatDomain()

        domain.isStreaming = true
        #expect(domain.isStreaming == true)

        domain.isStreaming = false
        #expect(domain.isStreaming == false)
    }

    // MARK: - Tool Call State

    @Test func toolCallStateCanBeSet() {
        let domain = ChatDomain()

        domain.currentToolCall = "search_airports"
        #expect(domain.currentToolCall == "search_airports")

        domain.currentToolCall = nil
        #expect(domain.currentToolCall == nil)
    }

    // MARK: - Thinking State

    @Test func thinkingStateCanBeSet() {
        let domain = ChatDomain()

        domain.currentThinking = "Searching for airports..."
        #expect(domain.currentThinking == "Searching for airports...")

        domain.currentThinking = nil
        #expect(domain.currentThinking == nil)
    }

    // MARK: - Error State

    @Test func errorStateCanBeSet() {
        let domain = ChatDomain()

        domain.error = "Connection failed"
        #expect(domain.error == "Connection failed")

        domain.error = nil
        #expect(domain.error == nil)
    }

    // MARK: - Suggested Queries

    @Test func initialSuggestedQueriesIsEmpty() {
        let domain = ChatDomain()

        #expect(domain.suggestedQueries.isEmpty)
    }

    @Test func clearClearsSuggestedQueries() {
        let domain = ChatDomain()

        domain.suggestedQueries = [
            SuggestedQuery(text: "Query 1"),
            SuggestedQuery(text: "Query 2")
        ]

        #expect(domain.suggestedQueries.count == 2)

        domain.clear()

        #expect(domain.suggestedQueries.isEmpty)
    }

    @Test func suggestedQueriesCanBeSet() {
        let domain = ChatDomain()

        let queries = [
            SuggestedQuery(text: "Show ILS airports"),
            SuggestedQuery(text: "Filter by France")
        ]

        domain.suggestedQueries = queries

        #expect(domain.suggestedQueries.count == 2)
        #expect(domain.suggestedQueries[0].text == "Show ILS airports")
    }
}

// MARK: - ChatMessage Tests

struct ChatMessageTests {

    @Test func userMessageCreation() {
        let message = ChatMessage(role: .user, content: "Hello")

        #expect(message.role == .user)
        #expect(message.content == "Hello")
        #expect(message.isStreaming == false)
    }

    @Test func assistantMessageCreation() {
        let message = ChatMessage(role: .assistant, content: "Hi there!")

        #expect(message.role == .assistant)
        #expect(message.content == "Hi there!")
    }

    @Test func streamingMessageCreation() {
        let message = ChatMessage(role: .assistant, content: "Loading...", isStreaming: true)

        #expect(message.isStreaming == true)
    }

    @Test func messageHasUniqueId() {
        let m1 = ChatMessage(role: .user, content: "Test 1")
        let m2 = ChatMessage(role: .user, content: "Test 2")

        #expect(m1.id != m2.id)
    }
}

// MARK: - ChatEvent Tests

struct ChatEventTests {

    @Test func messageEventCanBeCreated() {
        let event = ChatEvent.message(content: "Hello")

        if case .message(let content) = event {
            #expect(content == "Hello")
        } else {
            Issue.record("Expected message event")
        }
    }

    @Test func thinkingEventCanBeCreated() {
        let event = ChatEvent.thinking(content: "Processing...")

        if case .thinking(let content) = event {
            #expect(content == "Processing...")
        } else {
            Issue.record("Expected thinking event")
        }
    }

    @Test func errorEventCanBeCreated() {
        let event = ChatEvent.error(message: "Connection lost")

        if case .error(let message) = event {
            #expect(message == "Connection lost")
        } else {
            Issue.record("Expected error event")
        }
    }

    @Test func doneEventCanBeCreated() {
        let event = ChatEvent.done(sessionId: "session-123", tokens: nil)

        if case .done(let sessionId, _) = event {
            #expect(sessionId == "session-123")
        } else {
            Issue.record("Expected done event")
        }
    }
}
