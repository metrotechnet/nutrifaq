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
        // Purpose: Renders computed content into the DOM for the current view state.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
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
        
        // Purpose: Implements a focused frontend behavior used by this module.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
        hide() {
            const container = document.getElementById('translate-options');
            if (container) {
                container.style.display = 'none';
            }
        },
        
        // Purpose: Implements a focused frontend behavior used by this module.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
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
        
        // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
        getValue() {
            const sourceSelect = document.getElementById('source-language');
            const targetSelect = document.getElementById('target-language');
            return {
                source: sourceSelect ? sourceSelect.value : 'auto',
                target: targetSelect ? targetSelect.value : 'fr',
                reversed: translationReversed
            };
        },
        
        // Purpose: Implements a focused frontend behavior used by this module.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
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
        
        // Purpose: Implements a focused frontend behavior used by this module.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
        reset() {
            translationReversed = false;
        }
    },
    
    /**
     * Input Area Component
     * Manages input area visibility and configuration
     */
    inputArea: {
        // Purpose: Renders computed content into the DOM for the current view state.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
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
        
        // Purpose: Implements a focused frontend behavior used by this module.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
        show() {
            const inputArea = document.querySelector('.input-area');
            if (inputArea) {
                inputArea.style.display = '';
            }
        },
        
        // Purpose: Implements a focused frontend behavior used by this module.
        // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
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
// Purpose: Implements a focused frontend behavior used by this module.
// Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
function isTranslationReversed() {
    return translationReversed;
}

// Purpose: Updates UI or local state so downstream interactions stay consistent.
// Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
function setTranslationReversed(value) {
    translationReversed = value;
}

// Export for use in other modules
window.ComponentsModule = {
    componentRegistry,
    isTranslationReversed,
    setTranslationReversed
};
