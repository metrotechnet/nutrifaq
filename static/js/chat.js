// ===================================
// CHAT MESSAGING FUNCTIONALITY
// ===================================

/**
 * Chat module
 * Handles message sending, streaming responses, and message UI
 */

// Global state
let isLoading = false;
let sessionId = null;
let userMessageDiv = document.createElement('div');
let endPadding = 0;
let currentAbortController = null;
let currentReader = null;
let prevMessageContent = null;
// Rate limiting - Debouncing
let lastRequestTime = 0;
const MIN_REQUEST_INTERVAL = 2000; // 2 seconds minimum between requests



// Configure marked.js to open links in new tab
if (typeof marked !== 'undefined') {
    const renderer = new marked.Renderer();
    const linkRenderer = renderer.link;
    renderer.link = (href, title, text) => {
        const html = linkRenderer.call(renderer, href, title, text);
        return html.replace(/^<a /, '<a target="_blank" rel="noopener noreferrer" ');
    };
    marked.setOptions({ renderer: renderer });
}



/**
 * Check if text ends with incomplete markdown URL syntax
 */
function hasIncompleteUrl(text) {
    // Check for incomplete markdown image: ![text](incomplete_url
    // or incomplete markdown link: [text](incomplete_url
    const imagePattern = /!\[[^\]]*\]\([^)]*$/;
    const linkPattern = /\[[^\]]*\]\([^)]*$/;
    
    return imagePattern.test(text) || linkPattern.test(text);
}

/**
 * Remove incomplete markdown URLs from text
 * Removes everything from the last occurrence of [text](incomplete_url
 */
function removeIncompleteUrls(text) {
    // Find the last occurrence of an incomplete markdown image or link
    const lastImageStart = text.lastIndexOf('![');
    const lastLinkStart = text.lastIndexOf('[');
    let lastUrlStart = Math.max(lastImageStart, lastLinkStart);
    
    if (lastUrlStart === -1) {
        return text; // No URL markdown found
    }

    // If this [ is part of an image ![, include the ! in the cut
    if (lastUrlStart > 0 && text[lastUrlStart - 1] === '!') {
        lastUrlStart -= 1;
    }

    // Check if there's a complete URL after this point
    const afterUrl = text.substring(lastUrlStart);
    // Complete URL patterns: ![text](url) or [text](url)
    const completeUrlPattern = /^!?\[[^\]]*\]\([^)]+\)/;
    
    if (!completeUrlPattern.test(afterUrl)) {
        // Incomplete URL, remove from this point
        return text.substring(0, lastUrlStart);
    }
    
    return text;
}

/**
 * Get selected library from selector
 */
function getSelectedLibrary() {
    const selector = document.getElementById('library-selector');
    return selector ? selector.value : 'all';
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Add message to chat
 */
function addMessage(text, role) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.innerHTML = `
        <div class="message-icon">${role === 'user' ? 'U' : 'IMX'}</div>
        <div class="message-content">${escapeHtml(text)}</div>
    `;
    
    const inputBox = document.getElementById('input-box');
    if (inputBox) {
        inputBox.value = '';
        inputBox.style.height = 'auto';
    }
    
    return messageDiv;
}

/**
 * Create assistant message with loading state
 */
function createAssistantMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    messageDiv.innerHTML = `
        <div class="message-icon">IMX</div>
        <div class="message-content">
            <div class="message-text markdown">
                <div class="loading">
                    <div class="loading-dot"></div>
                    <div class="loading-dot"></div>
                    <div class="loading-dot"></div>
                </div>
            </div>
            <div class="message-actions" style="display:none">
                <button class="action-btn copy-btn" title="">
                    <i class="bi bi-clipboard"></i>
                </button>
                <button class="action-btn like-btn" title="Like">
                    <i class="bi bi-hand-thumbs-up"></i>
                </button>
                <button class="action-btn dislike-btn" title="Dislike">
                    <i class="bi bi-hand-thumbs-down"></i>
                </button>

            </div>
        </div>
    `;
    return messageDiv;
}

/**
 * Setup message action buttons
 */
function setupMessageActions(messageDiv, contentDiv) {
    const { t, BACKEND_URL } = window.ConfigModule;
    const { speakText, stopTTS, getActiveTtsButton } = window.TTSModule || {};
    
    const copyBtn = messageDiv.querySelector('.copy-btn');
    const likeBtn = messageDiv.querySelector('.like-btn');
    const dislikeBtn = messageDiv.querySelector('.dislike-btn');
    const ttsBtn = messageDiv.querySelector('.tts-btn');

    // Set translated titles
    if (ttsBtn) ttsBtn.title = t('messages.listen') || 'Listen';
    if (copyBtn) copyBtn.title = t('messages.copy');

    // TTS button
    if (ttsBtn && speakText && stopTTS && getActiveTtsButton) {
        ttsBtn.addEventListener('click', () => {
            if (getActiveTtsButton() === ttsBtn) {
                stopTTS();
                return;
            }
            
            let textToSpeak;
            const translationResult = contentDiv.querySelector('.translation-result > div:last-child');
            if (translationResult) {
                textToSpeak = translationResult.textContent || translationResult.innerText;
            } else {
                textToSpeak = contentDiv.textContent || contentDiv.innerText;
            }
            
            if (textToSpeak && textToSpeak.trim()) {
                speakText(textToSpeak, ttsBtn);
            }
        });
    }

    // Like/dislike buttons
    if (likeBtn) {
        likeBtn.addEventListener('click', async () => {
            const questionId = likeBtn.dataset.questionId;
            if (!questionId) {
                console.log('Like button clicked but no question_id available');
                return;
            }
            likeBtn.style.background = '#49fc49ff';
            if (dislikeBtn) dislikeBtn.style.background = '#f9e6e6';
            
            fetch(`${BACKEND_URL}/api/like_answer`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_id: questionId, like: true })
            }).then(res => res.json())
              .then(result => {
                  if (result.status !== 'success') {
                      console.log('Like vote failed:', result.message);
                  }
              })
              .catch(e => console.log('Like vote error:', e));
        });
    }
    
    if (dislikeBtn) {
        dislikeBtn.addEventListener('click', () => {
            const questionId = dislikeBtn.dataset.questionId;
            if (!questionId) {
                console.log('Dislike button clicked but no question_id available');
                return;
            }
            dislikeBtn.style.background = '#ff8686';
            if (likeBtn) likeBtn.style.background = '#e6f9e6';
            
            fetch(`${BACKEND_URL}/api/like_answer`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_id: questionId, like: false })
            }).then(res => res.json())
              .then(result => {
                  if (result.status !== 'success') {
                      console.log('Dislike vote failed:', result.message);
                  }
              })
              .catch(e => console.log('Dislike vote error:', e));
        });
    }

    // Copy button - Copy HTML with images
    if (copyBtn) {
        copyBtn.addEventListener('click', async () => {
            try {
                // Copy both HTML and plain text to clipboard
                await navigator.clipboard.write([
                    new ClipboardItem({
                        'text/html': new Blob([contentDiv.innerHTML], { type: 'text/html' }),
                        'text/plain': new Blob([contentDiv.textContent], { type: 'text/plain' })
                    })
                ]);
                
                // Show confirmation feedback
                const originalIcon = copyBtn.innerHTML;
                copyBtn.innerHTML = '<i class="bi bi-check2"></i>';
                copyBtn.style.background = '#4caf50';
                
                setTimeout(() => {
                    copyBtn.innerHTML = originalIcon;
                    copyBtn.style.background = '';
                }, 2000);
                
            } catch (err) {
                // Fallback to text-only if HTML copy fails
                console.log('HTML copy failed, falling back to text:', err);
                try {
                    await navigator.clipboard.writeText(contentDiv.textContent);
                    
                    // Show confirmation feedback for fallback too
                    const originalIcon = copyBtn.innerHTML;
                    copyBtn.innerHTML = '<i class="bi bi-check2"></i>';
                    copyBtn.style.background = '#4caf50';
                    
                    setTimeout(() => {
                        copyBtn.innerHTML = originalIcon;
                        copyBtn.style.background = '';
                    }, 2000);
                } catch (fallbackErr) {
                    console.error('Copy failed:', fallbackErr);
                }
            }

        });
    }

}

/**
 * Position message at bottom of viewport
 */
function positionMessageAtBottom(chatContainer, userMessageDiv, messageDiv) {
    if (!chatContainer || !userMessageDiv || !messageDiv) return;
    
    // Calculate needed padding to position message at bottom
    requestAnimationFrame(() => {
        
        const userMessageHeight = userMessageDiv.offsetHeight;      
        const messageDivHeight = messageDiv.offsetHeight;
        const containerHeight = chatContainer.clientHeight;
        
        // Calculate padding needed to push content to bottom
        const endPadding = containerHeight - userMessageHeight - messageDivHeight - 50;
        // console.log('Needed padding to position message at bottom:', endPadding);

        if (endPadding > 0) {
            const messageContent = messageDiv.querySelector('.message-content');
            if (messageContent) {
                const currentHeight = messageContent.offsetHeight;
                messageContent.style.marginBottom = (endPadding) + 'px';
            }
        }
        
        // Scroll to bottom
        requestAnimationFrame(() => {
            chatContainer.scrollTo({
                top: chatContainer.scrollHeight,
                behavior: 'smooth'
            });
        });
    });
}

/**
 * Prepare UI for loading
 */
function prepareUIForLoading() {
    isLoading = true;
    const sendButton = document.getElementById('send-button');
    const stopButton = document.getElementById('stop-button');
    const inputBox = document.getElementById('input-box');
    const voiceButton = document.getElementById('voice-button');
    
    // Toggle send/stop buttons
    if (sendButton) sendButton.style.display = 'none';
    if (stopButton) stopButton.style.display = '';
    if (inputBox) inputBox.disabled = true;
    if (voiceButton) voiceButton.disabled = true;
}

/**
 * Cancel ongoing message
 */
function cancelMessage() {
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }
    if (currentReader) {
        currentReader.cancel().catch(() => {});
        currentReader = null;
    }
}

/**
 * Cleanup after message
 */
function cleanupAfterMessage(messageDiv) {
    isLoading = false;
    currentAbortController = null;
    currentReader = null;
    const sendButton = document.getElementById('send-button');
    const stopButton = document.getElementById('stop-button');
    const inputBox = document.getElementById('input-box');
    const voiceButton = document.getElementById('voice-button');
    
    // Toggle stop/send buttons
    if (stopButton) stopButton.style.display = 'none';
    if (sendButton) sendButton.style.display = '';
    if (inputBox) inputBox.disabled = false;
    if (voiceButton) voiceButton.disabled = false;
    
    const { updateScrollIndicator } = window.UIUtilsModule || {};
    if (updateScrollIndicator) updateScrollIndicator();
}

/**
 * Display links/PMIDs
 */
function displayLinks(container, links) {
    if (!links || links.length === 0) return;
    
    const refsDiv = document.createElement('div');
    refsDiv.className = 'link-refs';
    refsDiv.innerHTML = `<strong>Références :</strong> ` +
        links.map(link => {
            const url = `https://google.com/search?q=${link}`;
            return `<a href="${url}" target="_blank" rel="noopener">${link}</a>`;
        }).join(', ');
    container.appendChild(refsDiv);
}

/**
 * Handle streaming response
 */
async function handleStreamingResponse(question, contentDiv, actionsDiv) {
    const { BACKEND_URL, getCurrentLanguage } = window.ConfigModule;
    const { updateScrollIndicator } = window.UIUtilsModule || {};
    const { getCurrentAgent } = window.AgentsModule || {};
    
    const requestData = {
        question: question,
        agent: 'agent',
        language: getCurrentLanguage(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        locale: navigator.language || (getCurrentLanguage() === 'en' ? 'en-US' : 'fr-FR'),
        session_id: sessionId,
        bibliotheque: getSelectedLibrary()
    };

    console.log('[Frontend][query] backend URL:', BACKEND_URL);
    console.log('[Frontend][query] request payload:', requestData);

    // Create abort controller for cancellation
    currentAbortController = new AbortController();

    const response = await fetch(`${BACKEND_URL}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData),
        signal: currentAbortController.signal
    });

    console.log('[Frontend][query] response status:', response.status, response.statusText);

    if (!response.ok) {
        if (response.status === 429) {
            const lang = getCurrentLanguage();
            const rateLimitMsg = lang === 'fr' 
                ? 'Limite de requêtes atteinte. Vous avez dépassé le nombre maximum de questions autorisées (10 par heure). Veuillez réessayer plus tard.'
                : 'Rate limit reached. You have exceeded the maximum number of allowed questions (10 per hour). Please try again later.';
            throw new Error(rateLimitMsg);
        }
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    currentReader = reader;
    const decoder = new TextDecoder();
    let buffer = '';
    let questionId = null;
    let fullText = '';
    let linksReceived = null;
    let textToDisplay='';
  
    while (true) {
        const { done, value } = await reader.read();

        if (done) {
            
            actionsDiv.style.display = '';
            if (questionId) {
                const likeBtn = actionsDiv.querySelector('.like-btn');
                const dislikeBtn = actionsDiv.querySelector('.dislike-btn');
                if (likeBtn) likeBtn.dataset.questionId = questionId;
                if (dislikeBtn) dislikeBtn.dataset.questionId = questionId;
            }
            if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                contentDiv.innerHTML = DOMPurify.sanitize(marked.parse(fullText), { ADD_ATTR: ['target'] });
            } else {
                contentDiv.textContent = fullText;
            }
            if (linksReceived !== null) {
                displayLinks(contentDiv, linksReceived);
            }
            return { fullText };
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const message of lines) {
            if (!message.trim()) continue;

            const dataMatch = message.match(/^data: (.+)$/m);
            if (dataMatch) {
                const rawData = dataMatch[1];
                
                // Check for [DONE] marker
                if (rawData === '[DONE]') {

                    actionsDiv.style.display = '';
                    if (questionId) {
                        const likeBtn = actionsDiv.querySelector('.like-btn');
                        const dislikeBtn = actionsDiv.querySelector('.dislike-btn');
                        if (likeBtn) likeBtn.dataset.questionId = questionId;
                        if (dislikeBtn) dislikeBtn.dataset.questionId = questionId;
                    }
                    if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                        contentDiv.innerHTML = DOMPurify.sanitize(marked.parse(fullText), { ADD_ATTR: ['target'] });
                    } else {
                        contentDiv.textContent = fullText;
                    }
                    if (linksReceived !== null) {
                        displayLinks(contentDiv, linksReceived);
                    }
                    return { fullText };
                }
                
                try {
                    const data = JSON.parse(rawData);

                    // Handle errors
                    if (data.error) {
                        console.error('Stream error:', data.error);
                        throw new Error(data.error);
                    }

                    if (data.session_id && !sessionId) {
                        sessionId = data.session_id;
                        window.sessionId = sessionId;
                        // console.log('Session ID received:', sessionId);
                    }
                    
                    if (data.question_id && !questionId) {
                        questionId = data.question_id;
                        window.questionId = questionId;
                    }

                    if (data.links !== undefined) {
                        linksReceived = data.links;
                        // console.log('Links received via stream:', linksReceived);
                    }

                    if (data.chunk) {
                        textToDisplay += data.chunk;
                        fullText = textToDisplay; // Keep fullText synchronized
                        // Remove incomplete URLs before displaying
                        const cleanText = removeIncompleteUrls(textToDisplay);
                        // console.log('Full text so far:', cleanText);

                        // Only parse markdown if we don't have an incomplete URL
                        // This prevents showing broken image/link URLs during streaming
                        if (!hasIncompleteUrl(cleanText)) {
                            if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                                contentDiv.innerHTML = DOMPurify.sanitize(marked.parse(cleanText), { ADD_ATTR: ['target'] });
                            } else {
                                contentDiv.textContent = cleanText;
                            }
                        } 
                    }
                  
                    if (updateScrollIndicator) updateScrollIndicator();
                } catch (parseError) {
                    console.error('JSON parsing error:', parseError);
                    throw parseError;
                }
            }
        }
    }
}

/**
 * Main send message function
 */
async function sendMessage() {
    const inputBox = document.getElementById('input-box');
    const emptyState = document.getElementById('empty-state');
    const chatContainer = document.getElementById('chat-container');
    
    const question = inputBox ? inputBox.value.trim() : '';
    if (!question || isLoading) return;
    
    // Rate limiting - Check minimum interval between requests
    const now = Date.now();
    if (now - lastRequestTime < MIN_REQUEST_INTERVAL) {
        console.log('Please wait before sending another message');
        // Optional: Show a brief visual feedback
        if (inputBox) {
            inputBox.style.borderColor = '#ff9800';
            setTimeout(() => {
                inputBox.style.borderColor = '';
            }, 500);
        }
        return;
    }
    lastRequestTime = now;
    
    // Stop voice recording
    if (window.VoiceRecognitionModule && window.VoiceRecognitionModule.stopRecording) {
        window.VoiceRecognitionModule.stopRecording();
    }
    
    if (emptyState) {
        emptyState.style.display = 'none';
    }
    
    userMessageDiv = addMessage(question, 'user');
    const messageDiv = createAssistantMessage();
    if (prevMessageContent) {
        prevMessageContent.style.marginBottom =  '0';
    }
    prevMessageContent = messageDiv.querySelector('.message-content');

    chatContainer.appendChild(userMessageDiv);
    chatContainer.appendChild(messageDiv);

    const contentDiv = messageDiv.querySelector('.message-text');
    const actionsDiv = messageDiv.querySelector('.message-actions');
    
    setupMessageActions(messageDiv, contentDiv);
    prepareUIForLoading();

    setTimeout(() => {
        positionMessageAtBottom(chatContainer, userMessageDiv, messageDiv);
    }, 100);

    try {
        await handleStreamingResponse(question, contentDiv, actionsDiv);
    } catch (error) {
        // Check if request was cancelled
        if (error.name === 'AbortError') {
            // console.log('Request cancelled by user');
            // contentDiv.innerHTML = '<em style="color: #666;">Request cancelled</em>';
            return;
        }
        
        console.error('Message sending error:', error);
        const { t, getCurrentLanguage } = window.ConfigModule;
        
        // Check if it's a rate limit error
        if (error.message && (error.message.includes('Limite de requêtes') || error.message.includes('Rate limit'))) {
            contentDiv.innerHTML = `<div style="color: #d32f2f; padding: 10px; background: #ffebee; border-radius: 4px; border-left: 4px solid #d32f2f;">
                <strong>⚠️ ${error.message}</strong>
            </div>`;
        } else {
            contentDiv.textContent = t('messages.error');
        }
    } finally {
        cleanupAfterMessage(messageDiv);
        const { handleFocus } = window.UIUtilsModule || {};
        if (handleFocus) handleFocus();
    }
}

/**
 * Get loading state
 */
function isMessageLoading() {
    return isLoading;
}

// Export for use in other modules
window.ChatModule = {
    sendMessage,
    createAssistantMessage,
    setupMessageActions,
    addMessage,
    positionMessageAtBottom,
    prepareUIForLoading,
    cleanupAfterMessage,
    cancelMessage,
    handleStreamingResponse,
    isMessageLoading
};
