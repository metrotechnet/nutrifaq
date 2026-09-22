// ===================================
// MAIN INITIALIZATION & EVENT HANDLERS
// ===================================

/**
 * Main module
 * Initializes the application and sets up event handlers
 */

/**
 * Keep startup overlay visible until app initialization finishes.
 */
const MODEL_STORAGE_KEY = 'nutrifaq_selected_model';

function tr(key, fallback) {
    try {
        const translator = window.ConfigModule && typeof window.ConfigModule.t === 'function'
            ? window.ConfigModule.t
            : null;
        if (translator) {
            const translated = translator(key);
            if (translated && translated !== key) {
                return translated;
            }
        }
    } catch (_) {
        // Ignore and use fallback.
    }
    return fallback;
}

async function loadModelSelectorOptions() {
    const modelSelector = document.getElementById('model-selector');
    if (!modelSelector) {
        return;
    }

    modelSelector.innerHTML = `<option value="">${tr('main.models.loading', 'Loading models...')}</option>`;
    modelSelector.disabled = true;

    try {
        const { BACKEND_URL } = window.ConfigModule;
        const response = await fetch(`${BACKEND_URL}/api/models`);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.message || payload.detail || response.statusText);
        }

        const models = Array.isArray(payload.models) ? payload.models : [];
        if (!models.length) {
            modelSelector.innerHTML = `<option value="">${tr('main.models.noneAvailable', 'No model available')}</option>`;
            return;
        }

        modelSelector.innerHTML = '';
        models.forEach((model) => {
            const option = document.createElement('option');
            option.value = model.id || '';
            option.textContent = model.label || model.id || 'Model';
            modelSelector.appendChild(option);
        });

        const savedModel = localStorage.getItem(MODEL_STORAGE_KEY) || '';
        const defaultModel = payload.default_model || '';
        const candidate = savedModel || defaultModel;

        if (candidate && models.some((m) => m.id === candidate)) {
            modelSelector.value = candidate;
        }

        if (!modelSelector.value && models[0] && models[0].id) {
            modelSelector.value = models[0].id;
        }

        if (modelSelector.value) {
            localStorage.setItem(MODEL_STORAGE_KEY, modelSelector.value);
        }

        modelSelector.disabled = false;
    } catch (error) {
        modelSelector.innerHTML = `<option value="">${tr('main.models.loadError', 'Error loading models')}</option>`;
        modelSelector.disabled = true;
        console.error('Failed to load model catalog:', error);
    }
}

function bindModelSelector() {
    const modelSelector = document.getElementById('model-selector');
    if (!modelSelector) {
        return;
    }

    modelSelector.addEventListener('change', function() {
        const selected = (this.value || '').trim();
        if (selected) {
            localStorage.setItem(MODEL_STORAGE_KEY, selected);
        } else {
            localStorage.removeItem(MODEL_STORAGE_KEY);
        }
    });
}

function warmupBackend() {
    const overlay = document.getElementById('initial-loading-overlay');
    const minDelayPromise = new Promise((resolve) => setTimeout(resolve, 350));

    return async function finishWarmup() {
        await minDelayPromise;

        if (!overlay) {
            return;
        }

        overlay.classList.add('hidden');
        setTimeout(() => {
            if (overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
            }
        }, 500);
    };
}

/**
 * Initialize all modules and event handlers
 */
document.addEventListener('DOMContentLoaded', async function() {
    // Keep loading overlay until config + i18n are fully initialized.
    const finishWarmup = warmupBackend();
    // Get modules
    const { loadConfig, switchLanguage, getCurrentLanguage, getMainConfig, populateSuggestionCards } = window.ConfigModule;
    const { isMobileDevice, initKeyboardDetection, createScrollIndicator, updateScrollIndicator, getChatScrollContainer,
            initSidebar, initCookieConsent, initLegalLinks } = window.UIUtilsModule;
    const { sendMessage, loadSuggestedQuestions } = window.ChatModule;
    const { initSpeechRecognition, toggleRecording, toggleRecognitionMethod, useWhisper } = window.VoiceRecognitionModule;
    const { switchAgent, updateAgentSelectorLabels } = window.AgentsModule;
    const { componentRegistry } = window.ComponentsModule;
    
    // DOM elements
    const inputBox = document.getElementById('input-box');
    const sendButton = document.getElementById('send-button');
    const voiceButton = document.getElementById('voice-button');
    const languageSelector = document.getElementById('language-selector');
    const modelSelector = document.getElementById('model-selector');
    const chatContainer = document.getElementById('chat-container');
    const emptyState = document.getElementById('empty-state');
    

    
    try {
        // Load agent configuration first.
        await loadConfig();

        // Display agent intro (creates library selector dynamically)
        const { displayAgentIntro } = window.AgentsModule;
        if (displayAgentIntro) displayAgentIntro();

        // Render initial components using loaded language/config.
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
        await loadModelSelectorOptions();
    } finally {
        await finishWarmup();
    }

    // Show body after config and language setup
    document.body.style.display = '';
    
    // Initialize UI components
    initSidebar();
    initCookieConsent();
    initLegalLinks();
    initSpeechRecognition();
    if (loadSuggestedQuestions) {
        loadSuggestedQuestions();
    }
    
    // Create scroll indicator
    const scrollIndicator = createScrollIndicator();
    const chatScrollContainer = getChatScrollContainer ? getChatScrollContainer() : chatContainer;
    if (chatScrollContainer && scrollIndicator) {
        chatScrollContainer.addEventListener('scroll', updateScrollIndicator);
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

    if (modelSelector) {
        bindModelSelector();
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
