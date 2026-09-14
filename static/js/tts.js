// ===================================
// TEXT-TO-SPEECH MODULE
// ===================================

/**
 * Text-to-speech module
 * Handles TTS via OpenAI API
 */

// State
let ttsAudio = null;
let activeTtsButton = null;

/**
 * Stop TTS playback
 */
function stopTTS() {
    if (ttsAudio) {
        ttsAudio.pause();
        ttsAudio.currentTime = 0;
        ttsAudio = null;
    }
    
    if (activeTtsButton) {
        activeTtsButton.innerHTML = '<i class="bi bi-volume-up" style="font-size:1.3em;"></i>';
        activeTtsButton.disabled = false;
        activeTtsButton = null;
    }
}

/**
 * Speak text using OpenAI TTS
 */
async function speakText(text, button = null) {
    if (!text || text.trim().length === 0) {
        console.log('TTS skipped: empty text');
        return;
    }
    
    stopTTS();
    
    if (button) {
        activeTtsButton = button;
        button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" style="color: #1976d2; border-right-color: transparent;"></span>';
        button.disabled = true;
    }
    
    // Clean text for speech
    const cleanText = text
        .replace(/<[^>]*>/g, '')
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\*(.+?)\*/g, '$1')
        .replace(/#{1,6}\s/g, '')
        .replace(/```[\s\S]*?```/g, '')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/PMID:\s*\d+/gi, '')
        .replace(/\[\d+\]/g, '')
        .replace(/Références?\s*PubMed\s*:.*$/gim, '')
        .replace(/References?\s*:.*$/gim, '')
        .replace(/Sources?\s*:.*$/gim, '')
        .replace(/\n{2,}/g, '. ')
        .replace(/\n/g, ' ')
        .replace(/\s{2,}/g, ' ')
        .trim();
    
    if (!cleanText) return;
    
    const { BACKEND_URL, getCurrentLanguage } = window.ConfigModule;
    console.log('TTS: speaking', cleanText.length, 'chars, language:', getCurrentLanguage());

    try {
        const response = await fetch(`${BACKEND_URL}/api/tts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: cleanText,
                language: getCurrentLanguage()
            })
        });
        
        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`TTS error: ${response.status} - ${errText}`);
        }
        
        const audioBlob = await response.blob();
        console.log('TTS audio blob size:', audioBlob.size, 'type:', audioBlob.type);
        const audioUrl = URL.createObjectURL(audioBlob);
        ttsAudio = new Audio(audioUrl);
        
        if (button) {
            button.innerHTML = '<i class="bi bi-stop-fill" style="font-size:1.3em;"></i>';
            button.disabled = false;
        }
        
        ttsAudio.addEventListener('ended', () => {
            URL.revokeObjectURL(audioUrl);
            ttsAudio = null;
            if (activeTtsButton) {
                activeTtsButton.innerHTML = '<i class="bi bi-volume-up" style="font-size:1.3em;"></i>';
                activeTtsButton = null;
            }
        });
        
        ttsAudio.addEventListener('error', () => {
            console.error('TTS audio playback error');
            URL.revokeObjectURL(audioUrl);
            ttsAudio = null;
            if (activeTtsButton) {
                activeTtsButton.innerHTML = '<i class="bi bi-volume-up" style="font-size:1.3em;"></i>';
                activeTtsButton = null;
            }
        });
        
        await ttsAudio.play();
    } catch (error) {
        console.error('TTS error:', error);
        if (activeTtsButton) {
            activeTtsButton.innerHTML = '<i class="bi bi-volume-up" style="font-size:1.3em;"></i>';
            activeTtsButton.disabled = false;
            activeTtsButton = null;
        }
        if (ttsAudio) {
            ttsAudio = null;
        }
    }
}

/**
 * Get active TTS button
 */
function getActiveTtsButton() {
    return activeTtsButton;
}

// Export for use in other modules
window.TTSModule = {
    speakText,
    stopTTS,
    getActiveTtsButton
};
