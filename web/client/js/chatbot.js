/**
 * FlyFun Aviation Assistant Chatbot
 * Main chatbot UI component with message handling and visualization integration
 */

class Chatbot {
    constructor() {
        this.sessionId = null;
        this.history = [];
        this.isProcessing = false;
        this.mapIntegration = null; // Will be set by chat-map-integration.js

        // Initialize UI elements
        this.initializeUI();
        this.attachEventListeners();
        this.loadQuickActions();
    }

    initializeUI() {
        // Chat container
        this.chatContainer = document.getElementById('chat-container');
        this.chatPanel = document.getElementById('chat-panel');
        this.chatBackdrop = document.getElementById('chat-backdrop');
        this.chatMessages = document.getElementById('chat-messages-new');
        this.chatInput = document.getElementById('chat-input-new');
        this.sendButton = document.getElementById('chat-send-btn-new');
        this.toggleButton = document.getElementById('chat-toggle-btn');
        this.closeButton = document.getElementById('chat-close-btn');
        this.clearButton = document.getElementById('chatbot-clear-btn-new');
        this.expandButton = document.getElementById('chatbot-expand-btn-new');
        this.quickActionsContainer = document.getElementById('quick-actions-container-new');

        // Initialize state
        this.isExpanded = false;

        // Initialize as closed
        if (this.chatPanel) {
            this.chatPanel.classList.remove('open');
        }
    }

    attachEventListeners() {
        // Toggle chat panel
        if (this.toggleButton) {
            this.toggleButton.addEventListener('click', () => this.toggleChat());
        }

        // Close chat panel
        if (this.closeButton) {
            this.closeButton.addEventListener('click', () => this.closeChat());
        }

        // Expand/collapse chat panel
        if (this.expandButton) {
            this.expandButton.addEventListener('click', () => this.toggleExpand());
        }

        // Click backdrop to collapse
        if (this.chatBackdrop) {
            this.chatBackdrop.addEventListener('click', () => {
                if (this.isExpanded) {
                    this.toggleExpand();
                }
            });
        }

        // Send message
        if (this.sendButton) {
            this.sendButton.addEventListener('click', () => this.sendMessage());
        }

        // Send on Enter key
        if (this.chatInput) {
            this.chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });

            // Auto-resize textarea
            this.chatInput.addEventListener('input', () => {
                this.chatInput.style.height = 'auto';
                this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 150) + 'px';
            });
        }

        // Clear conversation
        if (this.clearButton) {
            this.clearButton.addEventListener('click', () => this.clearConversation());
        }

        // Keyboard shortcut: Ctrl+K to open chat
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.toggleChat();
                if (this.chatPanel.classList.contains('open')) {
                    this.chatInput.focus();
                }
            }
        });
    }

    toggleChat() {
        if (this.chatPanel) {
            this.chatPanel.classList.toggle('open');
            if (this.chatPanel.classList.contains('open')) {
                this.chatInput.focus();
                // Show welcome message if first time
                if (this.chatMessages.children.length === 0) {
                    this.addWelcomeMessage();
                }
            }
        }
    }

    closeChat() {
        if (this.chatPanel) {
            this.chatPanel.classList.remove('open');
        }
    }

    toggleExpand() {
        if (this.chatPanel && this.expandButton) {
            this.isExpanded = !this.isExpanded;

            if (this.isExpanded) {
                // Expand mode
                this.chatPanel.classList.add('expanded');
                this.expandButton.innerHTML = '<i class="fas fa-compress"></i>';
                this.expandButton.title = 'Collapse';

                // Show backdrop
                if (this.chatBackdrop) {
                    this.chatBackdrop.classList.add('active');
                }
            } else {
                // Normal mode
                this.chatPanel.classList.remove('expanded');
                this.expandButton.innerHTML = '<i class="fas fa-expand"></i>';
                this.expandButton.title = 'Expand';

                // Hide backdrop
                if (this.chatBackdrop) {
                    this.chatBackdrop.classList.remove('active');
                }
            }

            // Scroll to bottom after expansion change
            this.scrollToBottom();
        }
    }

    addWelcomeMessage() {
        const welcomeText = `👋 Welcome to FlyFun Aviation Assistant!

I can help you with **2,951 European airports**:

🔍 **Search & Discover**
• Find airports by name, ICAO, or city
• Get detailed airport information (runways, facilities, procedures)
• View database statistics

🗺️ **Flight Planning**
• Plan routes with fuel stops (AVGAS/Jet A)
• Find emergency alternate airports
• Locate border crossing/customs airports

💰 **Operational Info** (via web search)
• Landing fees and airport charges
• Customs and immigration procedures
• Current NOTAMs and restrictions

Try the quick actions below or ask me anything!`;

        this.addMessage('assistant', welcomeText, null);
    }

    async loadQuickActions() {
        try {
            const response = await fetch('/api/chat/quick-actions', {
                credentials: 'include'
            });
            const data = await response.json();

            if (data.actions && this.quickActionsContainer) {
                this.quickActionsContainer.innerHTML = '';
                data.actions.forEach(action => {
                    const button = document.createElement('button');
                    button.className = 'btn btn-sm btn-outline-primary quick-action-btn';
                    // Use emoji directly if icon starts with emoji, otherwise use Font Awesome
                    const iconHtml = action.icon.length <= 2 ?
                        `<span class="quick-action-emoji">${action.icon}</span>` :
                        `<i class="fas fa-${action.icon}"></i>`;
                    button.innerHTML = `${iconHtml} ${action.title}`;
                    button.onclick = () => this.useQuickAction(action.prompt);
                    this.quickActionsContainer.appendChild(button);
                });
            }
        } catch (error) {
            console.error('Error loading quick actions:', error);
        }
    }

    useQuickAction(prompt) {
        this.chatInput.value = prompt;
        // Focus on input so user can see and edit the question before sending
        this.chatInput.focus();
    }

    async sendMessage() {
        const message = this.chatInput.value.trim();
        if (!message || this.isProcessing) return;

        // Add user message to UI
        this.addMessage('user', message);

        // Clear input
        this.chatInput.value = '';
        this.chatInput.style.height = 'auto';

        // Show loading indicator
        this.isProcessing = true;
        this.updateSendButton(true);
        const loadingId = this.addLoadingIndicator();

        try {
            // Use streaming (passes loadingId to remove it when stream starts)
            await this.sendMessageStreaming(message, loadingId);
        } catch (error) {
            // Remove loading indicator on error
            this.removeLoadingIndicator(loadingId);
            this.addMessage('assistant', `Sorry, I encountered an error: ${error.message}. Please try again.`, null);
        } finally {
            this.isProcessing = false;
            this.updateSendButton(false);
        }
    }

    async sendMessageStreaming(message, loadingId) {
        try {
            // Call streaming API
            const response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',  // Include session cookie
                body: JSON.stringify({
                    message: message,
                    session_id: this.sessionId,
                    history: this.history
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Keep loading indicator until first content arrives
            let loadingRemoved = false;

            // Create message containers
            let thinkingContent = '';
            let messageContent = '';
            let visualization = null;
            let toolCalls = null;

            // Create message div for streaming updates (but don't add to DOM yet)
            const messageDiv = document.createElement('div');
            messageDiv.className = 'chat-message assistant-message';

            // Thinking section
            const thinkingSection = document.createElement('div');
            thinkingSection.className = 'thinking-section expanded'; // Start expanded
            const thinkingHeader = document.createElement('div');
            thinkingHeader.className = 'thinking-header';
            thinkingHeader.innerHTML = `
                <i class="fas fa-brain"></i>
                <span>Thinking Process</span>
                <i class="fas fa-chevron-down thinking-toggle"></i>
            `;
            const thinkingContentDiv = document.createElement('div');
            thinkingContentDiv.className = 'thinking-content';

            thinkingHeader.addEventListener('click', () => {
                thinkingSection.classList.toggle('expanded');
            });

            thinkingSection.appendChild(thinkingHeader);
            thinkingSection.appendChild(thinkingContentDiv);
            thinkingSection.style.display = 'none'; // Hidden until we get thinking content

            // Answer section
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.style.display = 'none'; // Hidden until answer starts

            messageDiv.appendChild(thinkingSection);
            messageDiv.appendChild(contentDiv);

            // Parse SSE stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // Keep incomplete event in buffer

                for (const line of lines) {
                    if (line.trim() === '') continue;

                    const eventMatch = line.match(/^event: (.+)\ndata: (.+)$/s);
                    if (eventMatch) {
                        const eventType = eventMatch[1];
                        const data = JSON.parse(eventMatch[2]);

                        switch (eventType) {
                            case 'thinking':
                                // First thinking event: remove loading, add message to DOM
                                if (!loadingRemoved) {
                                    console.log('First thinking event - removing loading and showing thinking section');
                                    if (loadingId) {
                                        this.removeLoadingIndicator(loadingId);
                                    }
                                    this.chatMessages.appendChild(messageDiv);
                                    thinkingSection.style.display = 'block';
                                    loadingRemoved = true;
                                }

                                // Stream thinking character by character
                                thinkingContent += data.content;
                                thinkingContentDiv.innerHTML = this.formatMessage(thinkingContent);
                                this.scrollToBottom();
                                break;

                            case 'thinking_done':
                                // Collapse thinking section when done
                                console.log('Thinking done - collapsing section');
                                thinkingSection.classList.remove('expanded');
                                break;

                            case 'message':
                                // First message event: remove loading if not done, show answer section
                                if (!loadingRemoved) {
                                    if (loadingId) {
                                        this.removeLoadingIndicator(loadingId);
                                    }
                                    this.chatMessages.appendChild(messageDiv);
                                    loadingRemoved = true;
                                }

                                // Auto-collapse thinking when first real answer content arrives
                                if (messageContent === '' && thinkingSection.style.display === 'block') {
                                    console.log('First answer content - collapsing thinking');
                                    thinkingSection.classList.remove('expanded');
                                    contentDiv.style.display = 'block';
                                }

                                // Accumulate answer content
                                messageContent += data.content;

                                // Only show answer if we have substantial content (not just whitespace)
                                if (messageContent.trim().length > 0) {
                                    contentDiv.style.display = 'block';
                                    contentDiv.innerHTML = this.formatMessage(messageContent);
                                }

                                this.scrollToBottom();
                                break;

                            case 'tool_calls':
                                toolCalls = data;
                                console.log('[DEBUG] Received tool_calls event:', JSON.stringify(data, null, 2));

                                // Add tool indicator
                                if (toolCalls && toolCalls.length > 0) {
                                    const toolsDiv = document.createElement('div');
                                    toolsDiv.className = 'message-tools';
                                    toolsDiv.innerHTML = `<small><i class="fas fa-tools"></i> Used: ${toolCalls.map(t => t.name).join(', ')}</small>`;
                                    messageDiv.appendChild(toolsDiv);

                                    // Extract and apply filter profile from tool results
                                    for (const toolCall of toolCalls) {
                                        console.log('[DEBUG] Checking toolCall:', toolCall.name, 'has result?', !!toolCall.result, 'has filter_profile?', !!(toolCall.result && toolCall.result.filter_profile));
                                        if (toolCall.result && toolCall.result.filter_profile) {
                                            console.log('[DEBUG] Found filter_profile:', toolCall.result.filter_profile);
                                            this.applyFilterProfile(toolCall.result.filter_profile);
                                            break; // Use first filter profile found
                                        }
                                    }
                                }
                                break;

                            case 'visualization':
                                visualization = data;
                                // Add visualization indicator
                                const vizDiv = document.createElement('div');
                                vizDiv.className = 'message-visualization-indicator';
                                vizDiv.innerHTML = '<small><i class="fas fa-map-marked-alt"></i> Results shown on map</small>';
                                messageDiv.appendChild(vizDiv);

                                // Handle map visualization
                                if (this.mapIntegration) {
                                    this.mapIntegration.visualizeData(visualization);
                                }
                                break;

                            case 'done':
                                this.sessionId = data.session_id;
                                break;

                            case 'error':
                                contentDiv.innerHTML = this.formatMessage(data.message);
                                break;
                        }
                    }
                }
            }

        } catch (error) {
            console.error('Error in streaming:', error);
            throw error; // Re-throw to be handled by sendMessage
        }
    }

    addMessage(role, content, visualization = null, toolCalls = null, thinking = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}-message`;

        // Add thinking section if available (for assistant messages only)
        if (role === 'assistant' && thinking && thinking.trim()) {
            const thinkingSection = document.createElement('div');
            thinkingSection.className = 'thinking-section';

            const thinkingHeader = document.createElement('div');
            thinkingHeader.className = 'thinking-header';
            thinkingHeader.innerHTML = `
                <i class="fas fa-brain"></i>
                <span>Thinking Process</span>
                <i class="fas fa-chevron-down thinking-toggle"></i>
            `;

            const thinkingContent = document.createElement('div');
            thinkingContent.className = 'thinking-content';
            thinkingContent.innerHTML = this.formatMessage(thinking);

            // Toggle thinking section on click
            thinkingHeader.addEventListener('click', () => {
                thinkingSection.classList.toggle('expanded');
            });

            thinkingSection.appendChild(thinkingHeader);
            thinkingSection.appendChild(thinkingContent);
            messageDiv.appendChild(thinkingSection);
        }

        // Message content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Format message with markdown-like support
        contentDiv.innerHTML = this.formatMessage(content);

        messageDiv.appendChild(contentDiv);

        // Add tool calls info if available (for debugging/transparency)
        if (toolCalls && toolCalls.length > 0) {
            const toolsDiv = document.createElement('div');
            toolsDiv.className = 'message-tools';
            toolsDiv.innerHTML = `<small><i class="fas fa-tools"></i> Used: ${toolCalls.map(t => t.name).join(', ')}</small>`;
            messageDiv.appendChild(toolsDiv);
        }

        // Add visualization indicator if available
        if (visualization) {
            const vizDiv = document.createElement('div');
            vizDiv.className = 'message-visualization-indicator';
            vizDiv.innerHTML = '<small><i class="fas fa-map-marked-alt"></i> Results shown on map</small>';
            messageDiv.appendChild(vizDiv);
        }

        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();

        return messageDiv;
    }

    formatMessage(text) {
        if (!text) return '';

        // Convert markdown-style formatting
        let formatted = text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Bold
            .replace(/\*(.*?)\*/g, '<em>$1</em>') // Italic
            .replace(/`(.*?)`/g, '<code>$1</code>') // Code
            // Convert URLs to clickable links (must be before line breaks)
            .replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="chat-link">$1</a>')
            .replace(/\n/g, '<br>'); // Line breaks

        return formatted;
    }

    addLoadingIndicator() {
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'chat-message assistant-message loading-message';
        loadingDiv.id = 'loading-' + Date.now();
        loadingDiv.innerHTML = `
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;
        this.chatMessages.appendChild(loadingDiv);
        this.scrollToBottom();
        return loadingDiv.id;
    }

    removeLoadingIndicator(loadingId) {
        const loadingDiv = document.getElementById(loadingId);
        if (loadingDiv) {
            loadingDiv.remove();
        }
    }

    updateSendButton(loading) {
        if (this.sendButton) {
            if (loading) {
                this.sendButton.disabled = true;
                this.sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            } else {
                this.sendButton.disabled = false;
                this.sendButton.innerHTML = '<i class="fas fa-paper-plane"></i>';
            }
        }
    }

    scrollToBottom() {
        if (this.chatMessages) {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        }
    }

    clearConversation() {
        if (confirm('Clear conversation history?')) {
            this.chatMessages.innerHTML = '';
            this.history = [];

            // Clear chat visualizations on map and restore all airports
            if (typeof chatMapIntegration !== 'undefined' && chatMapIntegration) {
                chatMapIntegration.clearChatVisualizations();
            }

            // Clear airport details panel on the right
            const airportContent = document.getElementById('airport-content');
            const noSelection = document.getElementById('no-selection');
            if (airportContent) {
                airportContent.style.display = 'none';
            }
            if (noSelection) {
                noSelection.style.display = 'block';
            }

            // Clear session on server
            if (this.sessionId) {
                fetch(`/api/chat/sessions/${this.sessionId}`, {
                    method: 'DELETE',
                    credentials: 'include'
                }).catch(err => console.error('Error clearing session:', err));
            }

            this.sessionId = null;
            this.addWelcomeMessage();
        }
    }

    // Method to handle map clicks (called from map.js)
    handleAirportClick(icaoCode, airportName) {
        if (this.chatPanel && !this.chatPanel.classList.contains('open')) {
            this.toggleChat();
        }

        const prompt = `Tell me about ${icaoCode} airport`;
        this.chatInput.value = prompt;

        // Optional: auto-send
        // this.sendMessage();
    }

    // Method to handle route drawing (called from map.js)
    handleRouteDrawn(fromIcao, toIcao) {
        if (this.chatPanel && !this.chatPanel.classList.contains('open')) {
            this.toggleChat();
        }

        const prompt = `Find airports with fuel along the route from ${fromIcao} to ${toIcao}`;
        this.chatInput.value = prompt;
    }

    /**
     * Apply filter profile from chatbot tool results to UI filters
     * This syncs the chatbot's search criteria with the filter panel
     */
    applyFilterProfile(filterProfile) {
        if (!filterProfile || typeof filterManager === 'undefined') {
            return;
        }

        console.log('Applying filter profile from chatbot:', filterProfile);

        // Apply country filter
        if (filterProfile.country) {
            const countrySelect = document.getElementById('country-filter');
            if (countrySelect) {
                countrySelect.value = filterProfile.country;
            }
        }

        // Apply has_procedures filter
        if (filterProfile.has_procedures) {
            const hasProcedures = document.getElementById('has-procedures');
            if (hasProcedures) {
                hasProcedures.checked = true;
            }
        }

        // Apply has_aip_data filter
        if (filterProfile.has_aip_data) {
            const hasAipData = document.getElementById('has-aip-data');
            if (hasAipData) {
                hasAipData.checked = true;
            }
        }

        // Apply has_hard_runway filter
        if (filterProfile.has_hard_runway) {
            const hasHardRunway = document.getElementById('has-hard-runway');
            if (hasHardRunway) {
                hasHardRunway.checked = true;
            }
        }

        // Apply point_of_entry (border crossing) filter
        if (filterProfile.point_of_entry) {
            const borderCrossing = document.getElementById('border-crossing-only');
            if (borderCrossing) {
                borderCrossing.checked = true;
            }
        }

        // Apply route distance filter
        if (filterProfile.route_distance) {
            const routeDistance = document.getElementById('route-distance');
            if (routeDistance) {
                routeDistance.value = filterProfile.route_distance;
            }
        }

        // Apply search query if present
        if (filterProfile.search_query) {
            const searchInput = document.getElementById('search-input');
            if (searchInput) {
                searchInput.value = filterProfile.search_query;
            }
        }

        // Note: We don't automatically apply filters here to avoid interfering with
        // the chatbot's visualization. The user can manually apply them if they want
        // to modify the filter criteria.
    }
}

// Initialize chatbot when DOM is ready
let chatbot = null;

function initChatbot() {
    chatbot = new Chatbot();
    console.log('Chatbot initialized');
    // Show welcome message on initialization
    if (chatbot && chatbot.chatMessages) {
        chatbot.addWelcomeMessage();
    }
    return chatbot;
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Chatbot, initChatbot };
}
