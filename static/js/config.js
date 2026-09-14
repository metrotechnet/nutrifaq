// ===================================
// CONFIGURATION & INTERNATIONALIZATION
// ===================================

/**
 * Configuration and internationalization module
 * Handles config loading, language switching, and translations
 */

// Backend URL - can be overridden by window.BACKEND_URL from config.js
const BACKEND_URL = window.BACKEND_URL || '';
console.log('Using BACKEND_URL:', BACKEND_URL);

// Global state
let mainConfig = {};
let currentLanguage = 'fr';

/**
 * Get URL parameter by name
 */
function getUrlParameter(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

/**
 * Load agent configuration 
 */
async function loadConfig(agent) {
    try {
        // Single-agent setup - always load agent config
        const configResponse = await fetch(`${BACKEND_URL}/api/get_config`);
        mainConfig = await configResponse.json();
        
        // Check for errors
        if (mainConfig.error) {
            console.error('Config load error:', mainConfig.error);
            return;
        }
        
        // Language detection priority: URL parameter > browser language > stored preference
        const urlLang = getUrlParameter('lang');
        const browserLang = navigator.language || navigator.userLanguage;
        const langCode = browserLang.startsWith('en') ? 'en' : 'fr';
        const storedLang = localStorage.getItem('preferredLanguage');
        
        // Validate URL language parameter
        if (urlLang && (urlLang === 'en' || urlLang === 'fr')) {
            currentLanguage = urlLang;
            localStorage.setItem('preferredLanguage', urlLang);
        } else {
            currentLanguage = langCode || storedLang;
            const url = new URL(window.location);
            url.searchParams.set('lang', currentLanguage);
            window.history.replaceState({}, '', url);
        }
        
        // Apply translations
        applyConfig(currentLanguage);

    } catch (error) {
        console.error('Failed to load config:', error);
        currentLanguage = 'fr';
    }
}

/**
 * Apply translations to all elements with data-i18n attributes
 */
function applyConfig(lang) {
    const langData = mainConfig[lang] || mainConfig['fr'];
    
    document.querySelectorAll('[data-i18n]').forEach(element => {
        const key = element.getAttribute('data-i18n');
        const translation = getNestedValue(langData, key);
        if (translation) {
            element.textContent = translation;
        }
    });
    
    // Update placeholder attributes
    document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
        const key = element.getAttribute('data-i18n-placeholder');
        const translation = getNestedValue(langData, key);
        if (translation) {
            element.placeholder = translation;
        }
    });
    
    // Update title attributes
    document.querySelectorAll('[data-i18n-title]').forEach(element => {
        const key = element.getAttribute('data-i18n-title');
        const translation = getNestedValue(langData, key);
        if (translation) {
            element.title = translation;
        }
    });
    // Update input disclaimer if present
    const inputDisclaimer = document.querySelector('.input-disclaimer');
    if (inputDisclaimer && langData.components && langData.components.inputArea && langData.components.inputArea.disclaimer) {
        inputDisclaimer.textContent = langData.components.inputArea.disclaimer;
    }
    
    // Update alt attributes
    document.querySelectorAll('[data-i18n-alt]').forEach(element => {
        const key = element.getAttribute('data-i18n-alt');
        const translation = getNestedValue(langData, key);
        if (translation) {
            element.alt = translation;
        }
    });
    
    // Update src attributes
    document.querySelectorAll('[data-i18n-src]').forEach(element => {
        const key = element.getAttribute('data-i18n-src');
        const translation = getNestedValue(langData, key);
        if (translation) {
            element.src = translation;
        }
    });
    
    // Update document title
    const titleElement = document.querySelector('title[data-i18n]');
    if (titleElement) {
        const key = titleElement.getAttribute('data-i18n');
        const translation = getNestedValue(langData, key);
        if (translation) {
            document.title = translation;
        }
    }
    
    // Update language selector value
    const langSelector = document.getElementById('language-selector');
    if (langSelector) {
        langSelector.value = lang;
    }
}

/**
 * Populate suggestion cards dynamically from config
 */
function populateSuggestionCards(lang) {
    const suggestionsContainer = document.querySelector('.suggestions');
    if (!suggestionsContainer) return;
    
    const langData = mainConfig[lang] || mainConfig['fr'];
    
    // Clear existing cards
    suggestionsContainer.innerHTML = '';
    
    if (langData && langData.suggestions) {
        const suggestions = langData.suggestions;
        
        // Handle both array and object formats
        const suggestionsList = Array.isArray(suggestions) 
            ? suggestions 
            : Object.entries(suggestions).map(([key, value]) => ({ id: key, ...value }));
        
        suggestionsList.forEach((suggestion) => {
            const card = document.createElement('div');
            card.className = 'suggestion-card';
            
            if (suggestion.color) {
                card.style.backgroundColor = suggestion.color;
            }
            
            const title = document.createElement('h3');
            title.textContent = suggestion.icon ? `${suggestion.icon} ${suggestion.title}` : suggestion.title;
            
            const description = document.createElement('p');
            description.textContent = suggestion.description;
            
            card.appendChild(title);
            card.appendChild(description);
            
            // Add click event listener
            card.addEventListener('click', async function() {
                console.log('Suggestion clicked:', suggestion);
                if (suggestion.event && suggestion.event.startsWith('display:')) {
                    const displayText = suggestion.event.split(':')[1] || suggestion.event.replace('display:', '').trim();
                    const inputBox = document.getElementById('input-box');
                    if (inputBox && displayText) {
                        inputBox.value = displayText;
                        console.log(`Displaying text: ${displayText}`);
                        // Trigger input event to adjust textarea height
                        inputBox.dispatchEvent(new Event('input', { bubbles: true }));
                        inputBox.focus();
                    }
                } else if (suggestion.event && suggestion.event.startsWith('switch:')) {
                    const agentName = suggestion.event.split(':')[1] || suggestion.event.replace('switch:', '').trim();
                    if (agentName && typeof switchAgent === 'function') {
                        const agentSelector = document.getElementById('agent-selector');
                        if (agentSelector) {
                            agentSelector.value = agentName;
                        }
                        console.log(`Switching agent to: ${agentName}`);
                        await switchAgent(agentName, true);
                    }
                } else {
                    console.log('No action for suggestion event:', suggestion.event);
                }
            });
            
            suggestionsContainer.appendChild(card);
        });
    }
}

/**
 * Get nested value from object using dot notation
 */
function getNestedValue(obj, path) {
    return path.split('.').reduce((current, key) => {
        return current && current[key] !== undefined ? current[key] : null;
    }, obj);
}

/**
 * Switch language
 */
function switchLanguage(lang) {
    currentLanguage = lang;
    localStorage.setItem('preferredLanguage', lang);
    
    // Update URL parameter
    const url = new URL(window.location);
    url.searchParams.set('lang', lang);
    window.history.replaceState({}, '', url);
    
    applyConfig(lang);
    populateSuggestionCards(lang);
    
    // Update language selector value
    const langSelector = document.getElementById('language-selector');
    if (langSelector) {
        langSelector.value = lang;
    }
}

/**
 * Get translation for a key
 */
function t(key) {
    const langData = mainConfig[currentLanguage] || mainConfig['fr'];
    return getNestedValue(langData, key) || key;
}

/**
 * Get current language
 */
function getCurrentLanguage() {
    return currentLanguage;
}

/**
 * Get main config
 */
function getMainConfig() {
    return mainConfig;
}

// Export functions for use in other modules
window.ConfigModule = {
    BACKEND_URL,
    loadConfig,
    applyConfig,
    populateSuggestionCards,
    switchLanguage,
    t,
    getCurrentLanguage,
    getMainConfig
};
