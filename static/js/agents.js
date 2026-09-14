// ===================================
// AGENTS MODULE
// ===================================

/**
 * Agents module
 * Handles agent switching and translation
 */


/**
 * Display agent intro
 */
function displayAgentIntro(agent) {
    const emptyState = document.getElementById('empty-state');
    if (!emptyState) return;
    
    const { getMainConfig, getCurrentLanguage } = window.ConfigModule;
    const mainConfig = getMainConfig();
    const langData = mainConfig[getCurrentLanguage()] || mainConfig['fr'];
    const intro = langData.intro || {};
    
    // Update profile image
    const profileImg = emptyState.querySelector('.profile-photo');
    if (profileImg) {
        if (intro.profileImage) {
            profileImg.src = intro.profileImage;
        }
        if (intro.profileAlt) {
            profileImg.alt = intro.profileAlt;
        }
    }
    
    const titleEl = emptyState.querySelector('h2[data-i18n="intro.title"]');
    if (titleEl && intro.title) {
        titleEl.textContent = intro.title;
    }
    
    const descEl = emptyState.querySelector('p[data-i18n="intro.description"]');
    if (descEl && intro.description) {
        descEl.textContent = intro.description;
    }
    
    const disclaimerEl = emptyState.querySelector('strong[data-i18n="intro.disclaimer"]');
    if (disclaimerEl && intro.disclaimer) {
        disclaimerEl.textContent = intro.disclaimer;
    }
    
    emptyState.style.display = '';
}

/**
 * Render agent components
 */
function renderAgentComponents(langData) {
    const { componentRegistry } = window.ComponentsModule;
    const { populateSuggestionCards, getCurrentLanguage } = window.ConfigModule;
    
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
    
    if (populateSuggestionCards) {
        populateSuggestionCards(getCurrentLanguage());
    }
}



/**
 * Update agent selector labels
 */
function updateAgentSelectorLabels() {
    const agentSelector = document.getElementById('agent-selector');
    if (!agentSelector) return;
    
    const { t } = window.ConfigModule;
    const options = agentSelector.querySelectorAll('option');
    options.forEach(opt => {
        const key = opt.getAttribute('data-i18n-option');
        if (key) {
            const label = t(key);
            if (label && label !== key) {
                opt.textContent = label;
            }
        }
    });
}

/**
 * Send translation
 */
async function sendTranslation() {
    const inputBox = document.getElementById('input-box');
    const emptyState = document.getElementById('empty-state');
    const chatContainer = document.getElementById('chat-container');
    
    const text = inputBox ? inputBox.value.trim() : '';
    if (!text || (window.ChatModule && window.ChatModule.isMessageLoading && window.ChatModule.isMessageLoading())) return;
    
    const { stopRecording } = window.VoiceRecognitionModule || {};
    if (stopRecording) stopRecording();
    
    if (emptyState) emptyState.style.display = 'none';
    
    const {
        addMessage,
        createAssistantMessage,
        setupMessageActions,
        removePreviousSpacer,
        createBottomSpacer,
        scrollToMessageBottom,
        prepareUIForLoading,
        cleanupAfterMessage
    } = window.ChatModule;
    
    removePreviousSpacer();
    
    const userMessageDiv = addMessage(text, 'user');
    const messageDiv = createAssistantMessage();
    
    const iconDiv = messageDiv.querySelector('.message-icon');
    if (iconDiv) iconDiv.textContent = 'IMX';
    
    if (chatContainer) {
        chatContainer.appendChild(userMessageDiv);
        chatContainer.appendChild(messageDiv);
        
        const spacerDiv = createBottomSpacer(userMessageDiv, messageDiv);
        chatContainer.appendChild(spacerDiv);
    }
    
    const contentDiv = messageDiv.querySelector('.message-text');
    const actionsDiv = messageDiv.querySelector('.message-actions');
    
    setupMessageActions(messageDiv, contentDiv);
    prepareUIForLoading();
    scrollToMessageBottom(contentDiv.closest('.message'));

    const { getCurrentLanguage, getMainConfig, t, BACKEND_URL } = window.ConfigModule;
    const { updateScrollIndicator } = window.UIUtilsModule || {};
    const { handleFocus } = window.UIUtilsModule || {};
    
    const sourceLanguageSelect = document.getElementById('source-language');
    const targetLanguageSelect = document.getElementById('target-language');
    const translationDirectionBtn = document.getElementById('translation-direction-btn');
    
    // Read directly from the select elements
    const actualSourceLang = sourceLanguageSelect ? sourceLanguageSelect.value : (getCurrentLanguage() || 'fr');
    const actualTargetLang = targetLanguageSelect ? targetLanguageSelect.value : 'en';
    
    console.log(`Translating from ${actualSourceLang} to ${actualTargetLang}`);
    
    const mainConfig = getMainConfig();
    const langData = mainConfig[getCurrentLanguage()] || mainConfig['fr'];
    const languages = langData.languages || {};
    const sourceLangName = languages[actualSourceLang] || actualSourceLang.toUpperCase();
    const targetLangName = languages[actualTargetLang] || actualTargetLang.toUpperCase();
    
    let questionId = null;
    
    try {
        const response = await fetch(`${BACKEND_URL}/api/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                target_language: actualTargetLang,
                source_language: actualSourceLang
            })
        });
        
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullText = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                contentDiv.innerHTML = `
                    <div class="translation-result">
                        <div class="translation-label">
                            <span style="color: #718096; font-size: 0.85em;">${sourceLangName} → ${targetLangName}</span>
                        </div>
                        <div>${fullText}</div>
                    </div>
                `;
                actionsDiv.style.display = '';
                
                if (questionId) {
                    const likeBtn = actionsDiv.querySelector('.like-btn');
                    const dislikeBtn = actionsDiv.querySelector('.dislike-btn');
                    if (likeBtn) likeBtn.dataset.questionId = questionId;
                    if (dislikeBtn) dislikeBtn.dataset.questionId = questionId;
                }
                break;
            }
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';
            
            for (const message of lines) {
                if (!message.trim()) continue;
                const dataMatch = message.match(/^data: (.+)$/m);
                if (dataMatch) {
                    try {
                        const data = JSON.parse(dataMatch[1]);
                        
                        if (data.question_id && !questionId) {
                            questionId = data.question_id;
                            console.log('Translation question_id received:', questionId);
                        }
                        
                        if (data.chunk) {
                            const loadingDiv = contentDiv.querySelector('.loading');
                            if (loadingDiv) contentDiv.textContent = '';
                            fullText += data.chunk;
                            contentDiv.textContent = fullText;
                            scrollToMessageBottom(contentDiv.closest('.message'));
                        }
                    } catch (e) {
                        console.error('Parse error:', e);
                    }
                }
            }
            if (updateScrollIndicator) updateScrollIndicator();
        }
    } catch (error) {
        console.error('Translation error:', error);
        contentDiv.textContent = t('messages.error');
    } finally {
        cleanupAfterMessage(messageDiv);
        
        if (handleFocus) handleFocus();
        scrollToMessageBottom(contentDiv.closest('.message'));
        
        // Auto-reverse translation direction
        const { setTranslationReversed } = window.ComponentsModule;
        if (setTranslationReversed) {
            const newReversed = !(isTranslationReversed());
            setTranslationReversed(newReversed);
        }
        
    }
}


/**
 * Check if translation is reversed
 */
function isTranslationReversed() {
    const { isTranslationReversed } = window.ComponentsModule;
    return isTranslationReversed ? isTranslationReversed() : false;
}

/**
 * Update source language display (swap languages)
 */
function updateSourceLanguageDisplay() {
    const { componentRegistry } = window.ComponentsModule || {};
    
    // Swap source and target language selections
    if (componentRegistry?.languageSelector) {
        componentRegistry.languageSelector.swap();
    }
}

/**
 * Get current agent (for single-agent deployment)
 */
function getCurrentAgent() {
    return 'agent';
}

// Export for use in other modules
window.AgentsModule = {
    displayAgentIntro,
    sendTranslation,
    isTranslationReversed,
    updateAgentSelectorLabels,
    updateSourceLanguageDisplay,
    getCurrentAgent
};
