// ===================================
// MAIN INITIALIZATION & EVENT HANDLERS
// ===================================

/**
 * Main module
 * Initializes the application and sets up event handlers
 */

/**
 * Warm up the backend to avoid cold start delay on first user query
 */
async function warmupBackend() {
    const overlay = document.getElementById('initial-loading-overlay');
    
    const startTime = Date.now();
    const timeout = 30000; // 30 seconds total timeout
    const retryDelay = 1000; // 1 second between retries
    let connectionSucceeded = false;
    
    while (Date.now() - startTime < timeout) {
        try {
            const controller = new AbortController();
            const attemptTimeout = setTimeout(() => controller.abort(), 5000); // 5 second per attempt
            
            const response = await fetch(`${window.BACKEND_URL}/health`, {
                method: 'GET',
                signal: controller.signal
            });
            
            clearTimeout(attemptTimeout);
            
            if (response.ok) {
                console.log('Backend server reached successfully');
                connectionSucceeded = true;
                break; // Success - exit loop
            } else {
                console.warn('Backend health check returned non-OK status:', response.status);
            }
        } catch (error) {
            const elapsed = Date.now() - startTime;
            if (elapsed >= timeout) {
                console.warn('Backend warmup failed after 30s timeout:', error.message);
                break;
            }
            console.log(`Retrying backend connection... (${Math.round(elapsed/1000)}s elapsed)`);
            // Wait before next retry
            await new Promise(resolve => setTimeout(resolve, retryDelay));
        }
    }
    
    // Hide loading overlay after warmup attempt
    if (overlay) {
        overlay.classList.add('hidden');
        // Remove from DOM after fade out
        setTimeout(() => {
            if (overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
            }
        }, 500);
    }
    
    // Show error message if connection failed
    if (!connectionSucceeded) {
        setTimeout(() => {
            const emptyState = document.getElementById('empty-state');
            if (emptyState) {
                const errorDiv = document.createElement('div');
                errorDiv.style.cssText = 'color: #d32f2f; padding: 1rem; background: #ffebee; border-radius: 8px; border-left: 4px solid #d32f2f; margin: 1rem 0; max-width: 600px;';
                errorDiv.innerHTML = '<strong>⚠️ Connection Error</strong><br><small style="color: #c62828;">The server could not be reached. Please refresh the page or try again later.</small>';
                
                // Insert after the disclaimer paragraph
                const disclaimer = emptyState.querySelector('p strong[data-i18n="intro.disclaimer"]');
                if (disclaimer && disclaimer.parentElement) {
                    disclaimer.parentElement.insertAdjacentElement('afterend', errorDiv);
                } else {
                    emptyState.appendChild(errorDiv);
                }
            }
            
            // Hide input area if connection failed
            const inputArea = document.getElementById('input-area');
            if (inputArea) {
                inputArea.style.display = 'none';
            }
        }, 600); // Wait for overlay fade out
    }
}

/**
 * Initialize all modules and event handlers
 */
document.addEventListener('DOMContentLoaded', async function() {
    // Warm up backend before initializing UI
    await warmupBackend();
    // Get modules
    const { loadConfig, switchLanguage, getCurrentLanguage, getMainConfig, populateSuggestionCards } = window.ConfigModule;
    const { isMobileDevice, initKeyboardDetection, createScrollIndicator, updateScrollIndicator, 
            initSidebar, initCookieConsent, initLegalLinks } = window.UIUtilsModule;
    const { sendMessage } = window.ChatModule;
    const { initSpeechRecognition, toggleRecording, toggleRecognitionMethod, useWhisper } = window.VoiceRecognitionModule;
    const { switchAgent, updateAgentSelectorLabels } = window.AgentsModule;
    const { componentRegistry } = window.ComponentsModule;
    
    // DOM elements
    const inputBox = document.getElementById('input-box');
    const sendButton = document.getElementById('send-button');
    const voiceButton = document.getElementById('voice-button');
    const languageSelector = document.getElementById('language-selector');
    const chatContainer = document.getElementById('chat-container');
    const emptyState = document.getElementById('empty-state');
    

    
    // Load  agent directly (single-agent setup)
    await loadConfig();
    
    // Display agent intro (creates library selector dynamically)
    const { displayAgentIntro } = window.AgentsModule;
    if (displayAgentIntro) displayAgentIntro();
    
    // Render initial components
    const mainConfig = getMainConfig();
    const langData = mainConfig[getCurrentLanguage()] || mainConfig['fr'];
    
    // Render agent components
    if (langData.components) {
        if (langData.components.languageSelector) {
            componentRegistry.languageSelector.render(langData.components.languageSelector);
        } else {
            componentRegistry.languageSelector.hide();
        }
        
        if (langData.components.inputArea) {
            componentRegistry.inputArea.render(langData.components.inputArea);
        } else if (langData.input) {
            componentRegistry.inputArea.render(langData.input);
        }
    } else {
        componentRegistry.languageSelector.hide();
        if (langData.input) {
            componentRegistry.inputArea.render(langData.input);
        }
    }
    
    populateSuggestionCards(getCurrentLanguage());
    updateSourceLanguageDisplay();
    
    // Show body after config loads
    document.body.style.display = '';
    
    // Initialize UI components
    initSidebar();
    initCookieConsent();
    initLegalLinks();
    initSpeechRecognition();
    
    // Create scroll indicator
    const scrollIndicator = createScrollIndicator();
    if (chatContainer && scrollIndicator) {
        chatContainer.addEventListener('scroll', updateScrollIndicator);
        updateScrollIndicator();
    }
    
    // Initialize mobile keyboard detection
    if (isMobileDevice()) {
        initKeyboardDetection();
    }
    
    // ===================================
    // INPUT BOX EVENT HANDLERS
    // ===================================
    
    if (inputBox) {
        // Auto-resize textarea
        inputBox.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 200) + 'px';
        });
        
        // Handle Enter key
        inputBox.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
                this.blur();
            }
        });
        
        // Handle focus for mobile
        inputBox.addEventListener('focus', function() {
            setTimeout(() => {
                try {
                    this.scrollIntoView({ 
                        behavior: 'smooth', 
                        block: 'nearest',
                        inline: 'nearest'
                    });
                    
                    const rect = this.getBoundingClientRect();
                    const viewportHeight = window.innerHeight;
                    const estimatedKeyboardHeight = viewportHeight * 0.4;
                    
                    if (rect.bottom > viewportHeight - estimatedKeyboardHeight) {
                        const scrollAmount = rect.bottom - (viewportHeight - estimatedKeyboardHeight) + 20;
                        window.scrollBy(0, scrollAmount);
                    }
                } catch (error) {
                    console.log('Input focus scroll failed:', error);
                }
            }, 300);
        });
    }
    
    // ===================================
    // BUTTON EVENT HANDLERS
    // ===================================
    
    if (sendButton) {
        sendButton.addEventListener('click', () => {
            const isKeyboardVisible = document.activeElement === inputBox;
            sendMessage();
            if (isKeyboardVisible && inputBox) {
                inputBox.blur();
            }
        });
    }
    
    const stopButton = document.getElementById('stop-button');
    if (stopButton) {
        stopButton.addEventListener('click', () => {
            const { cancelMessage, cleanupAfterMessage } = window.ChatModule;
            if (cancelMessage) {
                cancelMessage();
                if (cleanupAfterMessage) cleanupAfterMessage();
            }
        });
    }
    
    if (voiceButton) {
        voiceButton.addEventListener('click', toggleRecording);
    }
    
    // ===================================
    // LANGUAGE SELECTOR
    // ===================================
    
    if (languageSelector) {
        languageSelector.addEventListener('change', function() {
            switchLanguage(this.value);
        });
    }
    
    // ===================================
    // AGENT SELECTOR - Removed (single-agent setup)
    // ===================================
    
    // ===================================
    // SPEECH METHOD INDICATOR
    // ===================================
    
    const speechMethodIndicator = document.getElementById('speech-method-indicator');
    if (speechMethodIndicator) {
        function updateIndicator() {
            if (useWhisper()) {
                speechMethodIndicator.textContent = '🎤 Whisper';
                speechMethodIndicator.style.background = '#4CAF50';
            } else {
                speechMethodIndicator.textContent = '🎤 Web Speech';
                speechMethodIndicator.style.background = '#2196F3';
            }
        }
        
        speechMethodIndicator.addEventListener('click', () => {
            toggleRecognitionMethod();
            updateIndicator();
        });
        
        updateIndicator();
    }
    
    console.log('Application initialized successfully');
});
