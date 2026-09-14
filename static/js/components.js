// ===================================
// COMPONENT REGISTRY SYSTEM
// ===================================

/**
 * Component Registry - manages UI components for different agents
 */

// Translation state
let translationReversed = false;

/**
 * Component Registry - manages UI components for different agents
 */
const componentRegistry = {
    /**
     * Language Selector Component
     * Supports single, pair (source/target), or multi-select modes
     */
    languageSelector: {
        render(config) {
            const container = document. getElementById('translate-options');
            if (!container) return;
            
            const type = config.type || 'pair';
            
            if (type === 'pair') {
                // Show the translate options bar
                container.style.display = 'flex';
                
                // Get source and target select elements
                const sourceSelect = document.getElementById('source-language');
                const targetSelect = document.getElementById('target-language');
                
                // Populate source language options
                if (sourceSelect && config.languages) {
                    this.populateLanguages(sourceSelect, config.languages, config.source?.default);
                }
                
                // Populate target language options
                if (targetSelect && config.languages) {
                    this.populateLanguages(targetSelect, config.languages, config.target?.default);
                }
            } else {
                // Hide for other types (single/multi not implemented yet)
                container.style.display = 'none';
            }
        },
        
        hide() {
            const container = document.getElementById('translate-options');
            if (container) {
                container.style.display = 'none';
            }
        },
        
        populateLanguages(select, languages, defaultValue) {
            if (!select || !languages) return;
            
            select.innerHTML = '';
            for (const [code, label] of Object.entries(languages)) {
                const option = document.createElement('option');
                option.value = code;
                option.textContent = label;
                select.appendChild(option);
            }
            
            if (defaultValue && languages[defaultValue]) {
                select.value = defaultValue;
            }
        },
        
        getValue() {
            const sourceSelect = document.getElementById('source-language');
            const targetSelect = document.getElementById('target-language');
            return {
                source: sourceSelect ? sourceSelect.value : 'auto',
                target: targetSelect ? targetSelect.value : 'fr',
                reversed: translationReversed
            };
        },
        
        swap() {
            const sourceSelect = document.getElementById('source-language');
            const targetSelect = document.getElementById('target-language');
            
            if (sourceSelect && targetSelect) {
                // Swap the values
                const tempSource = sourceSelect.value;
                sourceSelect.value = targetSelect.value;
                targetSelect.value = tempSource;
                console.log(`Languages swapped: ${sourceSelect.value} -> ${targetSelect.value}`);
            }
        },
        
        reset() {
            translationReversed = false;
        }
    },
    
    /**
     * Input Area Component
     * Manages input area visibility and configuration
     */
    inputArea: {
        render(config) {
            const inputArea = document.querySelector('.input-area');
            const inputBox = document.getElementById('input-box');
            const disclaimerEl = document.querySelector('.input-disclaimer');
            
            if (inputArea && config.showInputOnLoad !== undefined) {
                inputArea.style.display = config.showInputOnLoad ? '' : 'none';
            }
            
            if (inputBox && config.placeholder) {
                inputBox.placeholder = config.placeholder;
            }
            
            if (disclaimerEl && config.disclaimer) {
                disclaimerEl.textContent = config.disclaimer;
            }
        },
        
        show() {
            const inputArea = document.querySelector('.input-area');
            if (inputArea) {
                inputArea.style.display = '';
            }
        },
        
        hide() {
            const inputArea = document.querySelector('.input-area');
            if (inputArea) {
                inputArea.style.display = 'none';
            }
        }
    }
};

/**
 * Get/set translation reversed state
 */
function isTranslationReversed() {
    return translationReversed;
}

function setTranslationReversed(value) {
    translationReversed = value;
}

// Export for use in other modules
window.ComponentsModule = {
    componentRegistry,
    isTranslationReversed,
    setTranslationReversed
};
