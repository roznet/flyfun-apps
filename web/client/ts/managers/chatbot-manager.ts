/**
 * Chatbot Manager - Handles chatbot UI and message streaming
 */

import { LLMIntegration } from '../adapters/llm-integration';

/**
 * Chatbot Manager class
 */
export class ChatbotManager {
  private chatInput: HTMLTextAreaElement | null = null;
  private sendButton: HTMLButtonElement | null = null;
  private chatMessages: HTMLElement | null = null;
  private quickActionsContainer: HTMLElement | null = null;
  private expandButton: HTMLButtonElement | null = null;
  private clearButton: HTMLButtonElement | null = null;
  
  private sessionId: string | null = null;
  private messageHistory: Array<{role: string; content: string}> = [];
  private isProcessing: boolean = false;
  private llmIntegration: LLMIntegration;
  
  constructor(llmIntegration: LLMIntegration) {
    this.llmIntegration = llmIntegration;
    this.initializeUI();
    this.attachEventListeners();
    this.loadQuickActions();
    this.addWelcomeMessage();
  }
  
  /**
   * Initialize UI elements
   */
  private initializeUI(): void {
    this.chatInput = document.getElementById('chat-input-new') as HTMLTextAreaElement;
    this.sendButton = document.getElementById('chat-send-btn-new') as HTMLButtonElement;
    this.chatMessages = document.getElementById('chat-messages-new');
    this.quickActionsContainer = document.getElementById('quick-actions-container-new');
    this.expandButton = document.getElementById('chatbot-expand-btn-new') as HTMLButtonElement;
    this.clearButton = document.getElementById('chatbot-clear-btn-new') as HTMLButtonElement;
    
    if (!this.chatInput || !this.sendButton || !this.chatMessages) {
      console.error('ChatbotManager: Required UI elements not found');
    }
  }
  
  /**
   * Attach event listeners
   */
  private attachEventListeners(): void {
    if (!this.chatInput || !this.sendButton) return;
    
    // Auto-resize textarea
    this.chatInput.addEventListener('input', () => {
      if (this.chatInput) {
        this.chatInput.style.height = 'auto';
        this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 150) + 'px';
      }
    });
    
    // Send on Enter (without Shift)
    this.chatInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });
    
    // Send button click
    this.sendButton.addEventListener('click', () => {
      this.sendMessage();
    });
    
    // Expand button
    if (this.expandButton) {
      this.expandButton.addEventListener('click', () => {
        this.toggleExpand();
      });
    }
    
    // Clear button
    if (this.clearButton) {
      this.clearButton.addEventListener('click', () => {
        this.clearConversation();
      });
    }
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
        e.preventDefault();
        this.toggleExpand();
      }
    });
  }
  
  /**
   * Send message
   */
  async sendMessage(): Promise<void> {
    if (!this.chatInput || !this.chatMessages) return;
    
    const message = this.chatInput.value.trim();
    if (!message || this.isProcessing) return;
    
    // Add user message to UI
    this.addMessage('user', message);
    
    // Clear input
    this.chatInput.value = '';
    this.chatInput.style.height = 'auto';
    
    // Update UI state
    this.isProcessing = true;
    this.updateSendButton(true);
    const loadingId = this.addLoadingIndicator();
    
    try {
      await this.sendMessageStreaming(message, loadingId);
    } catch (error: any) {
      this.removeLoadingIndicator(loadingId);
      this.addMessage('assistant', `Sorry, I encountered an error: ${error.message}. Please try again.`, null);
    } finally {
      this.isProcessing = false;
      this.updateSendButton(false);
    }
  }
  
  /**
   * Send message with streaming
   */
  private async sendMessageStreaming(message: string, loadingId: string): Promise<void> {
    let doneReceived = false;
    
    // Build messages array from history + current message
    const messages = [...this.messageHistory];
    messages.push({
      role: 'user',
      content: message
    });
    
    console.log('ChatbotManager: Sending message with history', {
      messageHistoryLength: this.messageHistory.length,
      messagesLength: messages.length,
      sessionId: this.sessionId
    });
    
    // Call aviation agent streaming API
    const response = await fetch('/api/aviation-agent/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(this.sessionId ? { 'X-Session-ID': this.sessionId } : {})
      },
      credentials: 'include',
      body: JSON.stringify({ messages })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    // Extract session ID from headers if present
    const sessionIdHeader = response.headers.get('X-Session-ID');
    if (sessionIdHeader) {
      this.sessionId = sessionIdHeader;
    }
    
    let loadingRemoved = false;
    let thinkingContent = '';
    let messageContent = '';
    let visualization: any = null;
    let filterProfile: any = null;
    let visualizationApplied = false;
    let filterProfileApplied = false;
    
    // Create message div for streaming
    const messageDiv = document.createElement('div');
    messageDiv.className = 'chat-message assistant-message';
    
    // Thinking section
    const thinkingSection = document.createElement('div');
    thinkingSection.className = 'thinking-section expanded';
    thinkingSection.style.display = 'none';
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
    
    // Answer section
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.style.display = 'none';
    
    messageDiv.appendChild(thinkingSection);
    messageDiv.appendChild(contentDiv);
    
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    
    if (!reader) {
      throw new Error('Response body is not readable');
    }
    
    let buffer = '';
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || ''; // Keep incomplete event in buffer
      
      for (const eventBlock of events) {
        if (!eventBlock.trim()) continue;
        
        try {
          // Parse SSE format: "event: <type>\ndata: <json>"
          const eventMatch = eventBlock.match(/^event: (.+)\ndata: (.+)$/s);
          if (!eventMatch) {
            // Try alternative format: just "data: <json>" (default event type)
            const dataMatch = eventBlock.match(/^data: (.+)$/s);
            if (dataMatch) {
              const eventData = JSON.parse(dataMatch[1]);
              console.warn('ChatbotManager: Received SSE event without event type', eventData);
            }
            continue;
          }
          
          const eventType = eventMatch[1].trim();
          const eventData = JSON.parse(eventMatch[2]);
          
          console.log('ChatbotManager: Received SSE event', { eventType, hasContent: !!eventData.content });
          
          switch (eventType) {
            case 'thinking':
              // First thinking event: remove loading, add message to DOM
              if (!loadingRemoved) {
                this.removeLoadingIndicator(loadingId);
                if (this.chatMessages) {
                  this.chatMessages.appendChild(messageDiv);
                }
                thinkingSection.style.display = 'block';
                loadingRemoved = true;
              }
              
              // Stream thinking content
              thinkingContent += eventData.content || '';
              thinkingContentDiv.innerHTML = this.formatMessage(thinkingContent);
              this.scrollToBottom();
              break;
              
            case 'thinking_done':
              // Collapse thinking section when done
              thinkingSection.classList.remove('expanded');
              break;
              
            case 'message':
              // First message event: remove loading if not done, show answer section
              if (!loadingRemoved) {
                this.removeLoadingIndicator(loadingId);
                if (this.chatMessages) {
                  this.chatMessages.appendChild(messageDiv);
                }
                loadingRemoved = true;
              }
              
              // Ensure message div is in DOM (might not be added yet if no thinking event)
              if (this.chatMessages && !this.chatMessages.contains(messageDiv)) {
                this.chatMessages.appendChild(messageDiv);
              }
              
              // Auto-collapse thinking when first real answer content arrives
              if (messageContent === '' && thinkingSection.style.display === 'block') {
                thinkingSection.classList.remove('expanded');
                contentDiv.style.display = 'block';
              }
              
              // Accumulate answer content
              const chunk = eventData.content || '';
              messageContent += chunk;
              
              // Always show answer section and update content whenever we receive a chunk
              // Even if it's just whitespace, show it - formatting will handle it
              if (chunk !== null && chunk !== undefined) {
                contentDiv.style.display = 'block';
                contentDiv.innerHTML = this.formatMessage(messageContent);
                console.log('ChatbotManager: Updated message content', {
                  chunkLength: chunk.length,
                  chunk: chunk.substring(0, 50) + (chunk.length > 50 ? '...' : ''),
                  totalLength: messageContent.length,
                  hasContent: messageContent.trim().length > 0
                });
              }
              
              this.scrollToBottom();
              break;
              
            case 'ui_payload':
              // UI payload contains visualization and filter_profile
              if (eventData.visualization) {
                visualization = eventData.visualization;
                console.log('ChatbotManager: Received ui_payload with visualization', visualization);
                // Add visualization indicator
                const vizDiv = document.createElement('div');
                vizDiv.className = 'message-visualization-indicator';
                vizDiv.innerHTML = '<small><i class="fas fa-map-marked-alt"></i> Results shown on map</small>';
                messageDiv.appendChild(vizDiv);

                // Apply visualization immediately (don't wait for 'done' event)
                if (!visualizationApplied) {
                  this.llmIntegration.handleVisualization(visualization);
                  visualizationApplied = true;
                }
              }

              if (eventData.filter_profile) {
                filterProfile = eventData.filter_profile;
                // Apply filter profile immediately
                if (!filterProfileApplied) {
                  this.llmIntegration.applyFilterProfile(filterProfile);
                  filterProfileApplied = true;
                }
              }
              break;
              
            case 'tool_call_end':
              // Tool call completed - may contain filter_profile in result
              if (eventData.result && eventData.result.filter_profile) {
                filterProfile = eventData.result.filter_profile;
              }
              
              // Add tool indicator
              const toolsDiv = document.createElement('div');
              toolsDiv.className = 'message-tools';
              toolsDiv.innerHTML = `<small><i class="fas fa-tools"></i> Used: ${eventData.name || 'tool'}</small>`;
              messageDiv.appendChild(toolsDiv);
              break;
              
            case 'done':
              // Message complete - reset button state immediately
              doneReceived = true;
              this.isProcessing = false;
              this.updateSendButton(false);
              
              if (!loadingRemoved) {
                this.removeLoadingIndicator(loadingId);
                if (this.chatMessages) {
                  this.chatMessages.appendChild(messageDiv);
                }
              }
              
              // Ensure message div is added to DOM before finishing
              if (this.chatMessages && !this.chatMessages.contains(messageDiv)) {
                this.chatMessages.appendChild(messageDiv);
              }
              
              // Ensure content div is visible if we have content
              if (messageContent && contentDiv.style.display === 'none') {
                contentDiv.style.display = 'block';
                contentDiv.innerHTML = this.formatMessage(messageContent);
              }
              
              // Add to history (use trimmed content)
              const assistantContent = messageContent.trim() || thinkingContent.trim();
              if (assistantContent) {
                this.messageHistory.push({
                  role: 'assistant',
                  content: assistantContent
                });
                console.log('ChatbotManager: Added assistant message to history', {
                  contentLength: assistantContent.length,
                  historyLength: this.messageHistory.length
                });
              } else {
                console.warn('ChatbotManager: No assistant content to add to history', {
                  messageContent: messageContent,
                  thinkingContent: thinkingContent
                });
              }
              
              // Apply visualization if present (only if not already applied)
              if (visualization && !visualizationApplied) {
                this.llmIntegration.handleVisualization(visualization);
                visualizationApplied = true;
              }

              // Apply filter profile if present (only if not already applied)
              if (filterProfile && !filterProfileApplied) {
                this.llmIntegration.applyFilterProfile(filterProfile);
                filterProfileApplied = true;
              }

              // Also apply from ui_payload if not already applied
              if (visualization && visualization.filter_profile && !filterProfileApplied) {
                this.llmIntegration.applyFilterProfile(visualization.filter_profile);
                filterProfileApplied = true;
              }
              
              // Break out of inner loop
              break;
          }
        } catch (e) {
          console.error('ChatbotManager: Failed to parse SSE event', {
            eventBlock: eventBlock.substring(0, 200), // Log first 200 chars
            error: e,
            errorMessage: e instanceof Error ? e.message : String(e)
          });
          // Don't break on parse errors - continue processing other events
        }
        
        // If we processed a 'done' event, exit the loop
        if (doneReceived) {
          break;
        }
      }
      
      // Exit outer loop if done
      if (doneReceived) {
        break;
      }
    }
    
    // Ensure message div is in DOM with content before finishing
    if (this.chatMessages && messageDiv && !this.chatMessages.contains(messageDiv)) {
      console.log('ChatbotManager: Adding message div to DOM at end of stream');
      this.chatMessages.appendChild(messageDiv);
    }
    
    // Ensure content is visible if we have any (final check)
    if (messageContent) {
      contentDiv.style.display = 'block';
      contentDiv.innerHTML = this.formatMessage(messageContent);
      console.log('ChatbotManager: Final message content update', {
        contentLength: messageContent.length,
        content: messageContent.substring(0, 100) + (messageContent.length > 100 ? '...' : '')
      });
    } else if (!messageContent && !thinkingContent) {
      console.warn('ChatbotManager: Stream completed with no content!', {
        loadingRemoved,
        messageDivInDOM: this.chatMessages?.contains(messageDiv)
      });
    }
    
    // Ensure button is reset even if done event wasn't received properly
    if (this.isProcessing) {
      console.warn('Stream completed but button still processing - resetting');
      this.isProcessing = false;
      this.updateSendButton(false);
    }
    
    console.log('ChatbotManager: Streaming complete', {
      doneReceived,
      messageContentLength: messageContent.length,
      thinkingContentLength: thinkingContent.length,
      finalHistoryLength: this.messageHistory.length
    });
  }
  
  /**
   * Update message content during streaming
   */
  private updateMessageContent(messageDiv: HTMLElement, thinking: string, content: string): void {
    let html = '';
    
    if (thinking) {
      html += `<div class="thinking-content"><i class="fas fa-cog fa-spin"></i> ${this.escapeHtml(thinking)}</div>`;
    }
    
    if (content) {
      // Convert markdown-like formatting to HTML
      const formatted = this.formatMessage(content);
      html += `<div class="message-content">${formatted}</div>`;
    }
    
    messageDiv.innerHTML = html;
    this.scrollToBottom();
  }
  
  /**
   * Format message content (basic markdown support)
   */
  private formatMessage(text: string): string {
    // Escape HTML first
    let html = this.escapeHtml(text);

    // Process headers BEFORE converting newlines (headers end with \n)
    // Headers: ### Header (h3), ## Header (h2), # Header (h1)
    html = html.replace(/^###\s+(.+?)$/gm, '<h3>$1</h3>');
    html = html.replace(/^##\s+(.+?)$/gm, '<h2>$1</h2>');
    html = html.replace(/^#\s+(.+?)$/gm, '<h1>$1</h1>');

    // Convert newlines to <br>
    html = html.replace(/\n/g, '<br>');

    // Bold: **text**
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Code: `code`
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');

    return html;
  }
  
  /**
   * Add message to chat
   */
  private addMessage(role: 'user' | 'assistant', content: string, metadata: any = null): void {
    if (!this.chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}-message`;
    
    if (role === 'user') {
      messageDiv.innerHTML = `
        <div class="message-content">${this.escapeHtml(content)}</div>
      `;
      // Add to history
      this.messageHistory.push({ role: 'user', content });
    } else {
      const formatted = this.formatMessage(content);
      messageDiv.innerHTML = `
        <div class="message-content">${formatted}</div>
      `;
    }
    
    this.chatMessages.appendChild(messageDiv);
    this.scrollToBottom();
  }
  
  /**
   * Add welcome message
   */
  private addWelcomeMessage(): void {
    if (!this.chatMessages) return;
    
    const welcomeDiv = document.createElement('div');
    welcomeDiv.className = 'chat-message assistant-message welcome-message';
    welcomeDiv.innerHTML = `
      <div class="message-content">
        <p>Hello! I'm your FlyFun Aviation Assistant. I can help you with:</p>
        <ul>
          <li>Finding airports and their details</li>
          <li>Planning routes between airports</li>
          <li>Filtering airports by criteria</li>
          <li>Answering questions about aviation rules and procedures</li>
        </ul>
        <p>Try asking me something like:</p>
        <ul>
          <li>"Show me airports in France"</li>
          <li>"Find airports between LFPO and EDDM"</li>
          <li>"What are the border crossing airports in Germany?"</li>
        </ul>
      </div>
    `;
    this.chatMessages.appendChild(welcomeDiv);
  }
  
  /**
   * Load quick actions
   */
  private async loadQuickActions(): Promise<void> {
    if (!this.quickActionsContainer) return;
    
    try {
      const response = await fetch('/api/aviation-agent/quick-actions');
      if (!response.ok) return;
      
      const data = await response.json();
      if (data.actions && Array.isArray(data.actions)) {
        this.quickActionsContainer.innerHTML = '';
        
        data.actions.forEach((action: any) => {
          const button = document.createElement('button');
          button.className = 'btn btn-sm btn-outline-primary quick-action-btn';
          const iconHtml = action.icon && action.icon.length <= 2
            ? `<span class="quick-action-emoji">${action.icon}</span>`
            : `<i class="fas fa-${action.icon || 'question'}"></i>`;
          button.innerHTML = `${iconHtml} ${this.escapeHtml(action.title || '')}`;
          button.addEventListener('click', () => {
            this.useQuickAction(action.prompt);
          });
          this.quickActionsContainer?.appendChild(button);
        });
      }
    } catch (error) {
      console.error('Error loading quick actions:', error);
    }
  }
  
  /**
   * Use quick action
   */
  private useQuickAction(prompt: string): void {
    if (!this.chatInput) return;
    this.chatInput.value = prompt;
    this.chatInput.focus();
    // Auto-resize
    this.chatInput.style.height = 'auto';
    this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 150) + 'px';
  }
  
  /**
   * Apply filter profile from LLM response
   */
  private applyFilterProfile(filterProfile: any): void {
    if (!filterProfile) return;
    
    // Use LLMIntegration to apply filter profile
    // This will update the store and UI
    console.log('Applying filter profile:', filterProfile);
    this.llmIntegration.applyFilterProfile(filterProfile);
  }
  
  /**
   * Toggle expand/collapse
   */
  private toggleExpand(): void {
    const mainRow = document.querySelector('.main-content-row');
    if (mainRow) {
      mainRow.classList.toggle('expanded');
      
      // Update button icon
      if (this.expandButton) {
        const icon = this.expandButton.querySelector('i');
        if (icon) {
          icon.className = mainRow.classList.contains('expanded')
            ? 'fas fa-compress'
            : 'fas fa-expand';
        }
      }
      
      // Invalidate map size after layout change (with delay to allow CSS transition)
      setTimeout(() => {
        if ((window as any).visualizationEngine) {
          const map = (window as any).visualizationEngine.getMap();
          if (map && typeof map.invalidateSize === 'function') {
            map.invalidateSize();
          }
        }
      }, 300); // Match CSS transition duration
    }
  }
  
  /**
   * Clear conversation
   */
  private clearConversation(): void {
    if (!this.chatMessages) return;
    
    // Clear messages (except welcome)
    const messages = this.chatMessages.querySelectorAll('.chat-message:not(.welcome-message)');
    messages.forEach(msg => msg.remove());
    
    // Clear history
    this.messageHistory = [];
    this.sessionId = null;
    
    // Add welcome message back
    this.addWelcomeMessage();
  }
  
  /**
   * Update send button state
   */
  private updateSendButton(disabled: boolean): void {
    if (!this.sendButton) return;
    this.sendButton.disabled = disabled;
    const icon = this.sendButton.querySelector('i');
    if (icon) {
      icon.className = disabled ? 'fas fa-spinner fa-spin' : 'fas fa-paper-plane';
    }
  }
  
  /**
   * Add loading indicator
   */
  private addLoadingIndicator(): string {
    if (!this.chatMessages) return '';
    
    const loadingId = `loading-${Date.now()}`;
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingId;
    loadingDiv.className = 'chat-message assistant-message loading-message';
    loadingDiv.innerHTML = `
      <div class="message-content">
        <div class="spinner-border spinner-border-sm" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
        <span class="ms-2">Thinking...</span>
      </div>
    `;
    this.chatMessages.appendChild(loadingDiv);
    this.scrollToBottom();
    return loadingId;
  }
  
  /**
   * Remove loading indicator
   */
  private removeLoadingIndicator(loadingId: string): void {
    if (!loadingId) return;
    const loadingEl = document.getElementById(loadingId);
    if (loadingEl) {
      loadingEl.remove();
    }
  }
  
  /**
   * Scroll to bottom
   */
  private scrollToBottom(): void {
    if (!this.chatMessages) return;
    this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
  }
  
  /**
   * Escape HTML
   */
  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

