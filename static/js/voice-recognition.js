// ===================================
// VOICE RECOGNITION MODULE
// ===================================

/**
 * Voice recognition module
 * Supports both Web Speech API and Whisper transcription
 */

// State
let recognition = null;
let isRecording = false;
let useWhisper = true;
let mediaRecorder = null;
let audioChunks = [];
let whisperStream = null;
let recordingAnimationInterval = null;
let maxDurationTimer = null;
let warningTimer = null;

/**
 * Convert language code to speech recognition locale
 */
function getRecognitionLocale(langCode) {
    const localeMap = {
        'fr': 'fr-FR', 'en': 'en-US', 'es': 'es-ES', 'de': 'de-DE',
        'it': 'it-IT', 'pt': 'pt-PT', 'nl': 'nl-NL', 'ru': 'ru-RU',
        'zh': 'zh-CN', 'ja': 'ja-JP', 'ko': 'ko-KR', 'ar': 'ar-SA',
        'hi': 'hi-IN', 'pl': 'pl-PL', 'tr': 'tr-TR', 'sv': 'sv-SE',
        'da': 'da-DK', 'no': 'no-NO', 'fi': 'fi-FI', 'uk': 'uk-UA',
        'cs': 'cs-CZ', 'ro': 'ro-RO', 'el': 'el-GR', 'he': 'he-IL',
        'th': 'th-TH', 'vi': 'vi-VN', 'id': 'id-ID'
    };
    return localeMap[langCode] || 'en-US';
}

/**
 * Initialize Web Speech API recognition
 */
function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    if (!SpeechRecognition) {
        console.warn('Speech recognition not supported in this browser');
        const voiceButton = document.getElementById('voice-button');
        if (voiceButton) voiceButton.style.display = 'none';
        return;
    }
    
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    const { getCurrentLanguage } = window.ConfigModule;
    recognition.lang = getCurrentLanguage() === 'en' ? 'en-US': 'fr-FR';
    
    let finalTranscript = '';
    
    recognition.onstart = function() {
        isRecording = true;
        const voiceButton = document.getElementById('n');
        if (voiceButton) voiceButton.classList.add('recording');
        finalTranscript = '';
        console.log('Voice recording onstart');
    };
    
    recognition.onresult = function(event) {
        let interimTranscript = '';
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript + ' ';
            } else {
                interimTranscript += transcript;
            }
        }
        
        const inputBox = document.getElementById('input-box');
        if (isRecording && inputBox) {
            inputBox.value = finalTranscript + interimTranscript;
            inputBox.style.height = 'auto';
            inputBox.style.height = Math.min(inputBox.scrollHeight, 200) + 'px';
        }
    };
    
    recognition.onerror = function(event) {
        if (event.error === "no-speech") {
            console.log("Restarting...");
            setTimeout(() => recognition.start(), 1000);
        } else {
            console.error('Speech recognition error:', event.error);
            stopRecording();
        }
    };
    
    recognition.onend = function() {
        if (isRecording) {
            try {
                recognition.start();
            } catch (error) {
                console.log('Recognition restart error:', error);
            }
        }
    };
}

/**
 * Start Web Speech API recording
 */
function startRecording() {
    if (!recognition) return;
    
    try {
        const { getCurrentLanguage } = window.ConfigModule;
        const { getCurrentAgent } = window.AgentsModule || {};
        const { componentRegistry } = window.ComponentsModule || {};
        
        if (getCurrentAgent && getCurrentAgent() === 'translator') {
            const langValues = componentRegistry?.languageSelector?.getValue();
            const sourceLang = langValues?.source || (getCurrentLanguage() || 'fr');
            
            recognition.lang = getRecognitionLocale(sourceLang);
            console.log(`Voice recording in translator mode: ${sourceLang} -> ${langValues?.target} (${recognition.lang})`);
        } else {
            recognition.lang = getCurrentLanguage() === 'en' ? 'en-US' : 'fr-FR';
            console.log(`Voice recording in interface language: ${getCurrentLanguage()} (${recognition.lang})`);
        }
        recognition.start();
        console.log('Voice recording started');
    } catch (error) {
        console.error('Failed to start recording:', error);
    }
}

/**
 * Stop Web Speech API recording
 */
function stopRecording() {
    if (recognition && isRecording) {
        isRecording = false;
        const voiceButton = document.getElementById('voice-button');
        if (voiceButton) {
            voiceButton.classList.remove('recording');
            voiceButton.disabled = false;
        }
        recognition.stop();
        console.log('Voice recording stopped');
    }
}

/**
 * Initialize Whisper recording
 */
async function initWhisperRecording() {
    try {
        const inputBox = document.getElementById('input-box');
        const sendButton = document.getElementById('send-button');
        
        if (inputBox) {
            inputBox.value = '';
            inputBox.style.height = 'auto';
            inputBox.disabled = true;
        }
        if (sendButton) sendButton.disabled = true;


        
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        whisperStream = stream;
        
        const options = { mimeType: 'audio/webm' };
        if (!MediaRecorder.isTypeSupported(options.mimeType)) {
            options.mimeType = 'audio/ogg; codecs=opus';
        }
        if (!MediaRecorder.isTypeSupported(options.mimeType)) {
            options.mimeType = '';
        }
        
        mediaRecorder = new MediaRecorder(stream, options);
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            if (audioChunks.length === 0) {
                console.warn('No audio data recorded');
                if (inputBox) inputBox.disabled = false;
                if (sendButton) sendButton.disabled = false;
                const voiceButton = document.getElementById('voice-button');
                if (voiceButton) voiceButton.disabled = false;
                return;
            }
            
            const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
            audioChunks = [];
            
            const MIN_AUDIO_SIZE = 10000;
            if (audioBlob.size < MIN_AUDIO_SIZE) {
                console.log('Audio too small, likely no speech detected');
                if (inputBox) inputBox.disabled = false;
                if (sendButton) sendButton.disabled = false;
                const voiceButton = document.getElementById('voice-button');
                if (voiceButton) voiceButton.disabled = false;
                restorePlaceholder();
                return;
            }
            
            if (recordingAnimationInterval) {
                clearInterval(recordingAnimationInterval);
                recordingAnimationInterval = null;
            }
            
            const { getCurrentLanguage } = window.ConfigModule;
            if (inputBox) {
                inputBox.placeholder = getCurrentLanguage() === 'en' 
                    ? '⏳ Processing audio...' 
                    : '⏳ Traitement audio...';
            }
            
            await transcribeWithWhisper(audioBlob);
            const voiceButton = document.getElementById('voice-button');
            if (voiceButton) voiceButton.disabled = false;
            restorePlaceholder();
        };
        
        mediaRecorder.onerror = (event) => {
            console.error('MediaRecorder error:', event.error);
            stopWhisperRecording();
        };
        
        mediaRecorder.start();
        
        const MAX_RECORDING_DURATION = 30000;
        const WARNING_TIME = 25000;
        
        warningTimer = setTimeout(() => {
            if (isRecording && inputBox) {
                const { getCurrentLanguage } = window.ConfigModule;
                inputBox.placeholder = getCurrentLanguage() === 'en' 
                    ? '⏱️ Recording (5s remaining...)' 
                    : '⏱️ Enregistrement (5s restantes...)';
            }
        }, WARNING_TIME);
        
        maxDurationTimer = setTimeout(() => {
            if (isRecording) {
                console.log('Maximum recording duration reached (30s) - auto-stopping');
                stopWhisperRecording();
            }
        }, MAX_RECORDING_DURATION);
        
        let dots = 0;
        const { getCurrentLanguage } = window.ConfigModule;
        const baseText = getCurrentLanguage() === 'en' ? '🎤 Recording' : '🎤 Enregistrement';
        
        recordingAnimationInterval = setInterval(() => {
            if (!isRecording) {
                if (recordingAnimationInterval) {
                    clearInterval(recordingAnimationInterval);
                    recordingAnimationInterval = null;
                }
                return;
            }
            dots = (dots + 1) % 4;
            if (inputBox) inputBox.placeholder = baseText + '.'.repeat(dots);
        }, 500);
        
        console.log('Whisper recording started with', mediaRecorder.mimeType);
        
    } catch (error) {
        console.error('Failed to initialize Whisper recording:', error);
        const { getCurrentLanguage } = window.ConfigModule;
        alert(getCurrentLanguage() === 'en' 
            ? 'Could not access microphone. Please check permissions.' 
            : 'Impossible d\'accéder au microphone. Vérifiez les permissions.');
        
        isRecording = false;
        const voiceButton = document.getElementById('voice-button');
        if (voiceButton) voiceButton.classList.remove('recording');
        if (voiceButton) voiceButton.disabled = false;
        
        if (maxDurationTimer) clearTimeout(maxDurationTimer);
        if (warningTimer) clearTimeout(warningTimer);
        if (recordingAnimationInterval) clearInterval(recordingAnimationInterval);
        
        const inputBox = document.getElementById('input-box');
        const sendButton = document.getElementById('send-button');
        if (inputBox) inputBox.disabled = false;
        if (sendButton) sendButton.disabled = false;
    }
}

/**
 * Stop Whisper recording
 */
function stopWhisperRecording() {
    isRecording = false;
    const voiceButton = document.getElementById('voice-button');
    if (voiceButton) voiceButton.classList.remove('recording');
    if (voiceButton) voiceButton.disabled = true;

    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        console.log('Whisper recording stopped');
    }
    
    if (whisperStream) {
        whisperStream.getTracks().forEach(track => track.stop());
        whisperStream = null;
    }
    
    if (maxDurationTimer) {
        clearTimeout(maxDurationTimer);
        maxDurationTimer = null;
    }
    if (warningTimer) {
        clearTimeout(warningTimer);
        warningTimer = null;
    }
    if (recordingAnimationInterval) {
        clearInterval(recordingAnimationInterval);
        recordingAnimationInterval = null;
    }
}

/**
 * Restore input placeholder
 */
function restorePlaceholder() {
    const inputBox = document.getElementById('input-box');
    if (!inputBox) return;
    
    const { t } = window.ConfigModule;
    const { getCurrentAgent } = window.AgentsModule || {};
    
    if (getCurrentAgent && getCurrentAgent() === 'translator') {
        inputBox.placeholder = t('translator.placeholder') || 'Entrez le texte à traduire...';
    } else {
        inputBox.placeholder = t('input.placeholder') || 'Pose-moi une question...';
    }
}

/**
 * Transcribe audio with Whisper
 */
async function transcribeWithWhisper(audioBlob) {
    try {
        const { BACKEND_URL, getCurrentLanguage } = window.ConfigModule;
        const { getCurrentAgent } = window.AgentsModule || {};
        const { componentRegistry } = window.ComponentsModule || {};
        
        let sourceLang;
        if (getCurrentAgent && getCurrentAgent() === 'translator') {
            const langValues = componentRegistry?.languageSelector?.getValue();
            sourceLang = langValues?.source || (getCurrentLanguage() || 'fr');
            console.log(`Whisper transcription: ${sourceLang} -> ${langValues?.target}`);
        } else {
            sourceLang = getCurrentLanguage() || 'en';
        }
        
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');
        formData.append('language', sourceLang);
        
        const response = await fetch(`${BACKEND_URL}/api/transcribe_audio`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.text) {
            const hallucinations = [
                'thank you for watching', 'thanks for watching',
                'thank you', 'bye', 'bye bye', 'goodbye'
            ];
            
            const lowerText = result.text.toLowerCase().trim();
            const isHallucination = hallucinations.some(phrase => 
                lowerText === phrase || lowerText === phrase + '.'
            );
            
            if (isHallucination) {
                console.log('Whisper hallucination detected, ignoring:', result.text);
                const inputBox = document.getElementById('input-box');
                const sendButton = document.getElementById('send-button');
                if (inputBox) inputBox.disabled = false;
                if (sendButton) sendButton.disabled = false;
                const voiceButton = document.getElementById('voice-button');
                if (voiceButton) voiceButton.disabled = false;

                return;
            }
            
            const inputBox = document.getElementById('input-box');
            if (inputBox) {
                const currentText = inputBox.value.trim();
                inputBox.value = currentText ? currentText + ' ' + result.text : result.text;
                inputBox.style.height = 'auto';
                inputBox.style.height = Math.min(inputBox.scrollHeight, 200) + 'px';
                inputBox.disabled = false;
            }
            
            const sendButton = document.getElementById('send-button');
            if (sendButton) sendButton.disabled = false;
            const voiceButton = document.getElementById('voice-button');
            if (voiceButton) voiceButton.disabled = false;
            
            console.log('Whisper transcription:', result.text);
            
            // Automatically send the message
            // if (window.ChatModule && window.ChatModule.sendMessage) {
            //     window.ChatModule.sendMessage();
            // }
        } else if (result.error) {
            console.error('Whisper transcription error:', result.error);
            const inputBox = document.getElementById('input-box');
            const sendButton = document.getElementById('send-button');
            const voiceButton = document.getElementById('voice-button');
            if (inputBox) inputBox.disabled = false;
            if (sendButton) sendButton.disabled = false;
            if (voiceButton) voiceButton.disabled = false;
        }
        
    } catch (error) {
        console.error('Failed to transcribe with Whisper:', error);
        const { getCurrentLanguage } = window.ConfigModule;
        alert(getCurrentLanguage() === 'en' 
            ? 'Failed to transcribe audio. Please try again.' 
            : 'Échec de la transcription. Veuillez réessayer.');
        
        const inputBox = document.getElementById('input-box');
        const sendButton = document.getElementById('send-button');
        const voiceButton = document.getElementById('voice-button');
        if (inputBox) inputBox.disabled = false;
        if (sendButton) sendButton.disabled = false;
        if (voiceButton) voiceButton.disabled = false;
    }
}

/**
 * Toggle recording
 */
function toggleRecording() {
    if (useWhisper) {
        if (isRecording) {
            stopWhisperRecording();
        } else {
            isRecording = true;
            const voiceButton = document.getElementById('voice-button');
            if (voiceButton) voiceButton.classList.add('recording');
            initWhisperRecording();
        }
        return;
    }
    
    if (!recognition) {
        const { getCurrentLanguage } = window.ConfigModule;
        alert(getCurrentLanguage() === 'en' 
            ? 'Speech recognition is not supported in your browser.' 
            : 'La reconnaissance vocale n\'est pas supportée par votre navigateur.');
        return;
    }
    
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
}

/**
 * Toggle recognition method
 */
function toggleRecognitionMethod() {
    useWhisper = !useWhisper;
    console.log('Recognition method switched to:', useWhisper ? 'Whisper' : 'Web Speech API');
}

// Export for use in other modules
window.VoiceRecognitionModule = {
    initSpeechRecognition,
    toggleRecording,
    stopRecording,
    toggleRecognitionMethod,
    isRecording: () => isRecording,
    useWhisper: () => useWhisper
};
