/**
 * Mode Manager - Handles layout interactions for the chatbot and detail panels
 */
class ModeManager {
    constructor() {
        this.chatbotExpanded = false;
        this.rightPanelCollapsed = false;
        this.initialized = false;
        this.isProcessing = false;
        this.sessionId = null;
    }

    init() {
        if (this.initialized) return;

        console.log('Initializing Mode Manager...');
        this.setupListeners();
        this.initializeChatbot();
        this.initialized = true;
        console.log('Mode Manager initialized');
    }

    setupListeners() {
        // Expand button
        const expandBtn = document.getElementById('chatbot-expand-btn-new');
        if (expandBtn) {
            expandBtn.addEventListener('click', () => this.toggleExpand());
        }

        // Clear button - handled by chatbot.js to properly clear map visualizations
        // const clearBtn = document.getElementById('chatbot-clear-btn-new');
        // if (clearBtn) {
        //     clearBtn.addEventListener('click', () => this.clearChatbot());
        // }

        // Right panel collapse
        const collapseBtn = document.getElementById('right-panel-collapse');
        if (collapseBtn) {
            collapseBtn.addEventListener('click', () => this.toggleRightPanel());
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+M: Toggle mode
            // Ctrl+E: Expand/collapse chatbot
            if (e.ctrlKey && e.key === 'e') {
                e.preventDefault();
                this.toggleExpand();
            }

            // Ctrl+K: Focus chat input (only in chatbot mode)
            if (e.ctrlKey && e.key === 'k') {
                e.preventDefault();
                const chatInput = document.getElementById('chat-input-new');
                if (chatInput) {
                    chatInput.focus();
                }
            }
        });
    }

    toggleExpand() {
        const mainRow = document.querySelector('.main-content-row');
        this.chatbotExpanded = !this.chatbotExpanded;

        if (this.chatbotExpanded) {
            mainRow.classList.add('expanded');
        } else {
            mainRow.classList.remove('expanded');
        }

        // Update button icon
        const expandBtn = document.getElementById('chatbot-expand-btn-new');
        if (expandBtn) {
            const icon = expandBtn.querySelector('i');
            if (icon) {
                icon.className = this.chatbotExpanded ? 'fas fa-compress' : 'fas fa-expand';
            }
            expandBtn.title = this.chatbotExpanded ? 'Compress' : 'Expand (Ctrl+E)';
        }

        console.log(`Chatbot ${this.chatbotExpanded ? 'expanded' : 'compressed'}`);

        // Resize map
        this.invalidateMap();
    }

    toggleRightPanel() {
        const rightPanel = document.querySelector('.right-panel');
        const rightPanelCol = document.querySelector('.right-panel-col');
        const mapCol = document.querySelector('.map-column-col');
        const leftPanelCol = document.querySelector('.left-panel-col');

        if (rightPanel && rightPanelCol && mapCol && leftPanelCol) {
            this.rightPanelCollapsed = !this.rightPanelCollapsed;

            // Toggle collapsed on right panel
            rightPanel.classList.toggle('collapsed');
            rightPanelCol.classList.toggle('collapsed');

            // Toggle expanded on map and maintain left panel
            mapCol.classList.toggle('map-expanded');
            leftPanelCol.classList.toggle('with-expanded-map');

            console.log(`Right panel ${this.rightPanelCollapsed ? 'collapsed' : 'expanded'}`);

            // Resize map
            this.invalidateMap();
        }
    }

    invalidateMap() {
        // Resize map after layout changes
        // Use multiple timeouts to ensure map resizes after CSS transitions
        setTimeout(() => {
            if (window.airportMap && window.airportMap.map) {
                window.airportMap.map.invalidateSize();
                console.log('Map resized (first attempt)');
            }
        }, 100);

        setTimeout(() => {
            if (window.airportMap && window.airportMap.map) {
                window.airportMap.map.invalidateSize();
                console.log('Map resized (second attempt)');
            }
        }, 350);
    }

    clearChatbot() {
        if (confirm('Clear all chat messages?')) {
            const chatMessages = document.getElementById('chat-messages-new');
            if (chatMessages) {
                chatMessages.innerHTML = '';
                console.log('Chat cleared');
            }

            // Clear chatbot history if available
            if (window.chatbotNew) {
                window.chatbotNew.history = [];
                window.chatbotNew.sessionId = null;
            }
        }
    }

    initializeChatbot() {
        // Initialize new chatbot instance for the integrated panel
        const chatInput = document.getElementById('chat-input-new');
        const sendBtn = document.getElementById('chat-send-btn-new');
        const chatMessages = document.getElementById('chat-messages-new');
        const quickActionsContainer = document.getElementById('quick-actions-container-new');

        if (chatInput && sendBtn && chatMessages) {
            // Auto-resize textarea
            chatInput.addEventListener('input', () => {
                chatInput.style.height = 'auto';
                chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
            });

            // Send on Enter (without Shift)
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendChatMessage();
                }
            });

            // Send button click
            sendBtn.addEventListener('click', () => {
                this.sendChatMessage();
            });

            // Load quick actions
            this.loadQuickActions(quickActionsContainer);

            console.log('Chatbot initialized in new panel');
        }
    }

    async sendChatMessage() {
        const chatInput = document.getElementById('chat-input-new');
        const chatMessages = document.getElementById('chat-messages-new');
        const sendBtn = document.getElementById('chat-send-btn-new');

        const message = chatInput.value.trim();
        if (!message || this.isProcessing) return;

        // Mark as processing
        this.isProcessing = true;

        // Add user message
        this.addMessage('user', message);
        chatInput.value = '';
        chatInput.style.height = 'auto';

        // Disable input
        chatInput.disabled = true;
        sendBtn.disabled = true;
        sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        // Add loading indicator
        const loadingId = 'loading-' + Date.now();
        const loadingDiv = document.createElement('div');
        loadingDiv.id = loadingId;
        loadingDiv.className = 'chat-message assistant-message';
        loadingDiv.innerHTML = '<div class="message-content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>';
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            // Use new aviation agent endpoint
            const response = await fetch('/api/aviation-agent/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-ID': this.sessionId || undefined
                },
                credentials: 'include',
                body: JSON.stringify({
                    messages: [{
                        role: 'user',
                        content: message
                    }]
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Remove loading indicator
            loadingDiv.remove();

            // Create message container for streaming
            const messageDiv = document.createElement('div');
            messageDiv.className = 'chat-message assistant-message';

            // Thinking section
            const thinkingSection = document.createElement('div');
            thinkingSection.className = 'thinking-section expanded';
            thinkingSection.innerHTML = `
                <div class="thinking-header">
                    <i class="fas fa-brain"></i>
                    <span>Thinking Process</span>
                    <i class="fas fa-chevron-down thinking-toggle"></i>
                </div>
                <div class="thinking-content"></div>
            `;
            thinkingSection.style.display = 'none';

            const thinkingHeader = thinkingSection.querySelector('.thinking-header');
            thinkingHeader.addEventListener('click', () => {
                thinkingSection.classList.toggle('expanded');
            });

            // Answer section
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.style.display = 'none';

            messageDiv.appendChild(thinkingSection);
            messageDiv.appendChild(contentDiv);
            chatMessages.appendChild(messageDiv);

            // Parse SSE stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let thinkingContent = '';
            let messageContent = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.trim()) continue;

                    const eventMatch = line.match(/^event: (.+)\ndata: (.+)$/s);
                    if (eventMatch) {
                        const eventType = eventMatch[1];
                        const data = JSON.parse(eventMatch[2]);

                        switch (eventType) {
                            case 'thinking':
                                if (thinkingSection.style.display === 'none') {
                                    thinkingSection.style.display = 'block';
                                }
                                thinkingContent += data.content;
                                thinkingSection.querySelector('.thinking-content').innerHTML = this.formatMessage(thinkingContent);
                                chatMessages.scrollTop = chatMessages.scrollHeight;
                                break;

                            case 'thinking_done':
                                thinkingSection.classList.remove('expanded');
                                break;

                            case 'message':
                                if (messageContent === '' && thinkingSection.style.display === 'block') {
                                    thinkingSection.classList.remove('expanded');
                                }
                                messageContent += data.content;
                                if (messageContent.trim().length > 0) {
                                    contentDiv.style.display = 'block';
                                    contentDiv.innerHTML = this.formatMessage(messageContent);
                                }
                                chatMessages.scrollTop = chatMessages.scrollHeight;
                                break;

                            case 'plan':
                                // New event: plan shows what tool will be used
                                console.log('Plan:', data);
                                break;

                            case 'tool_call_start':
                                // New event: tool execution started
                                console.log('Tool call started:', data.name);
                                break;

                            case 'tool_call_end':
                                // New event: tool execution completed
                                console.log('Tool call completed:', data.name);
                                break;

                            case 'ui_payload':
                                // New event: UI payload contains visualization, filters, airports
                                console.log('UI payload:', data);
                                
                                // Handle map visualization
                                if (window.chatMapIntegration && data.visualization) {
                                    console.log('Visualizing data on map:', data.visualization);
                                    window.chatMapIntegration.visualizeData(data.visualization);
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
            console.error('Error sending message:', error);
            const errorDiv = document.getElementById(loadingId);
            if (errorDiv) errorDiv.remove();
            this.addMessage('assistant', '❌ Sorry, there was an error processing your message. Please try again.');
        } finally {
            // Re-enable input
            this.isProcessing = false;
            chatInput.disabled = false;
            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
            chatInput.focus();
        }
    }

    addMessage(role, content, toolCalls = null, thinking = null) {
        const chatMessages = document.getElementById('chat-messages-new');
        if (!chatMessages) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}-message`;

        // Thinking section (if available)
        if (thinking && role === 'assistant') {
            const thinkingDiv = document.createElement('div');
            thinkingDiv.className = 'thinking-section';
            thinkingDiv.innerHTML = `
                <div class="thinking-header">
                    <i class="fas fa-brain"></i>
                    <span>Thinking Process</span>
                    <i class="fas fa-chevron-down thinking-toggle"></i>
                </div>
                <div class="thinking-content">${this.escapeHtml(thinking)}</div>
            `;

            // Toggle thinking section
            thinkingDiv.querySelector('.thinking-header').addEventListener('click', () => {
                thinkingDiv.classList.toggle('expanded');
            });

            messageDiv.appendChild(thinkingDiv);
        }

        // Main message content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = this.formatMessage(content);
        messageDiv.appendChild(contentDiv);

        // Tool calls (if available)
        if (toolCalls && toolCalls.length > 0 && role === 'assistant') {
            const toolsDiv = document.createElement('div');
            toolsDiv.className = 'message-tools';
            toolsDiv.innerHTML = `<small><i class="fas fa-tools"></i> Used ${toolCalls.length} tool(s)</small>`;
            messageDiv.appendChild(toolsDiv);
        }

        chatMessages.appendChild(messageDiv);

        // Scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    formatMessage(text) {
        if (!text) return '';

        // Escape HTML
        let formatted = this.escapeHtml(text);

        // Convert markdown-style bold
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Convert markdown-style code
        formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');

        // Convert newlines to <br>
        formatted = formatted.replace(/\n/g, '<br>');

        // Convert URLs to links
        formatted = formatted.replace(
            /(https?:\/\/[^\s<]+)/g,
            '<a href="$1" class="chat-link" target="_blank">$1</a>'
        );

        return formatted;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    loadQuickActions(container) {
        if (!container) return;

        const quickActions = [
            { icon: '🔍', text: 'Search', action: 'Find airports in Paris' },
            { icon: '🛣️', text: 'Route', action: 'Plan a route from EGTF to LFMD with a fuel stop that has AVGAS' },
            { icon: 'ℹ️', text: 'Details', action: 'Tell me about LFPG - runways, facilities, and procedures' },
            { icon: '🛂', text: 'Border', action: 'Show all border crossing airports in Germany' }
        ];

        container.innerHTML = quickActions.map(qa =>
            `<button class="btn btn-sm btn-outline-primary quick-action-btn" data-action="${qa.action}">
                ${qa.icon} ${qa.text}
            </button>`
        ).join('');

        // Add click handlers
        container.querySelectorAll('.quick-action-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.getAttribute('data-action');
                const chatInput = document.getElementById('chat-input-new');
                if (chatInput) {
                    chatInput.value = action;
                    chatInput.focus();
                }
            });
        });
    }

    isChatbotExpanded() {
        return this.chatbotExpanded;
    }

    isRightPanelCollapsed() {
        return this.rightPanelCollapsed;
    }
}

// Global instance
let modeManager;

// Initialize when DOM is ready
function initModeManager() {
    if (!modeManager) {
        modeManager = new ModeManager();
        modeManager.init();

        // Export to window for debugging
        window.modeManager = modeManager;
    }
    return modeManager;
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ModeManager, initModeManager };
}
