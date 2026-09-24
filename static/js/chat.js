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
const CLIENT_QUERY_KEY = (window.CLIENT_QUERY_KEY || '').trim();
const ADMIN_BEARER_TOKEN_KEY = 'nutrifaq_admin_bearer_token';

function tr(key, fallback, params) {
    let template = fallback;
    try {
        const translator = window.ConfigModule && typeof window.ConfigModule.t === 'function'
            ? window.ConfigModule.t
            : null;
        if (translator) {
            const translated = translator(key);
            if (translated && translated !== key) {
                template = translated;
            }
        }
    } catch (_) {
        template = fallback;
    }

    if (!params || typeof template !== 'string') {
        return template;
    }
    return template.replace(/\{([^}]+)\}/g, (match, name) => {
        if (!Object.prototype.hasOwnProperty.call(params, name)) {
            return match;
        }
        return String(params[name]);
    });
}

function getAdminBearerToken() {
    try {
        const token = localStorage.getItem(ADMIN_BEARER_TOKEN_KEY);
        return typeof token === 'string' ? token.trim() : '';
    } catch (_) {
        return '';
    }
}

function getQueryEndpoint() {
    // Route admin sessions to the debug KB endpoint when a bearer token exists.
    return getAdminBearerToken() ? '/query_debug' : '/query';
}



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

function getSelectedModel() {
    const selector = document.getElementById('model-selector');
    const value = selector ? String(selector.value || '').trim() : '';
    if (value) {
        return value;
    }
    const savedModel = String(localStorage.getItem('nutrifaq_selected_model') || '').trim();
    return savedModel || null;
}

function getSelectedModelLabel() {
    const selector = document.getElementById('model-selector');
    if (!selector) {
        return String(localStorage.getItem('nutrifaq_selected_model') || '').trim();
    }
    const selectedOption = selector.options[selector.selectedIndex];
    if (!selectedOption) {
        return String(localStorage.getItem('nutrifaq_selected_model') || '').trim();
    }
    const label = String(selectedOption.textContent || '').trim();
    if (label) {
        return label;
    }
    return String(localStorage.getItem('nutrifaq_selected_model') || '').trim();
}

function setMessageModelBadge(actionsDiv, modelId, modelLabel) {
    if (!actionsDiv) {
        return;
    }
    const badge = actionsDiv.querySelector('.message-model-name');
    if (!badge) {
        return;
    }

    const label = String(modelLabel || '').trim();
    const id = String(modelId || '').trim();
    const value = label || id;
    if (!value) {
        badge.textContent = '';
        badge.style.display = 'none';
        return;
    }

    const template = String(tr('chat.modelBadge', 'Modèle: {value}') || 'Modèle: {value}');
    const withValue = template.includes('{value}')
        ? template.replace(/\{\s*value\s*\}/gi, value)
        : `${template} ${value}`;

    badge.textContent = withValue;
    badge.style.display = 'inline-flex';
}

function buildApiHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (CLIENT_QUERY_KEY) {
        headers['X-Client-Key'] = CLIENT_QUERY_KEY;
    }
    const adminBearerToken = getAdminBearerToken();
    if (adminBearerToken) {
        headers.Authorization = `Bearer ${adminBearerToken}`;
    }
    return headers;
}

function truncateTitle(value, maxLength = 72) {
    const text = String(value || '').trim();
    if (!text) {
        return tr('chat.suggested.documentFallback', 'Document');
    }
    if (text.length <= maxLength) {
        return text;
    }
    return `${text.slice(0, maxLength - 1)}…`;
}

function setSuggestedQuestionsState({ metaText, emptyText, isError = false }) {
    const meta = document.getElementById('suggested-questions-meta');
    const list = document.getElementById('suggested-questions-list');
    if (meta) {
        meta.textContent = metaText || '';
    }
    if (list) {
        list.innerHTML = `<p class="suggested-questions-empty${isError ? ' error' : ''}">${escapeHtml(emptyText || '')}</p>`;
    }
}

function collapseSuggestedPanelOnMobileAfterCopy() {
    const isMobile = typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 768px)').matches;
    if (!isMobile) {
        return;
    }

    const mainPane = document.querySelector('.main-pane');
    if (!mainPane || mainPane.classList.contains('suggested-panel-collapsed')) {
        return;
    }

    const toggleButton = document.getElementById('toggle-suggested-panel-btn');
    if (toggleButton && typeof toggleButton.click === 'function') {
        toggleButton.click();
    }
}

function copyQuestionToInput(question, button) {
    const inputBox = document.getElementById('input-box');
    if (!inputBox) {
        return;
    }

    inputBox.value = question;
    inputBox.focus();
    inputBox.dispatchEvent(new Event('input', { bubbles: true }));

    // Reuse the same UI path as a manual send-button click (including blur/scroll behavior).
    const sendButton = document.getElementById('send-button');
    if (sendButton && typeof sendButton.click === 'function') {
        sendButton.click();
    } else if (typeof window.ChatModule?.sendMessage === 'function') {
        window.ChatModule.sendMessage();
    } else if (typeof sendMessage === 'function') {
        sendMessage();
    }

    collapseSuggestedPanelOnMobileAfterCopy();

    if (!button) {
        return;
    }
    const icon = button.querySelector('i');
    const sendTitle = tr('messages.send', 'Send');
    const sentTitle = tr('chat.copyDone', 'Sent');

    if (icon) {
        icon.className = 'bi bi-check2';
    }
    button.title = sentTitle;
    button.setAttribute('aria-label', sentTitle);
    button.classList.add('copied');

    window.setTimeout(() => {
        if (icon) {
            icon.className = 'bi bi-send';
        }
        button.title = sendTitle;
        button.setAttribute('aria-label', sendTitle);
        button.classList.remove('copied');
    }, 1000);
}

function renderSuggestedQuestions(documents) {
    const list = document.getElementById('suggested-questions-list');
    const meta = document.getElementById('suggested-questions-meta');
    if (!list || !meta) {
        return;
    }

    if (!Array.isArray(documents) || documents.length === 0) {
        setSuggestedQuestionsState({
            metaText: tr('chat.suggested.questionCount', '{questions} question(s)', { questions: 0 }),
            emptyText: tr('chat.suggested.noGeneratedQuestions', 'No generated questions available.'),
        });
        return;
    }

    const totalQuestions = documents.reduce((count, doc) => {
        return count + (Array.isArray(doc.questions) ? doc.questions.length : 0);
    }, 0);
    const summaryTemplate = String(
        tr('chat.suggested.questionCount', '{questions} question(s)', {
            questions: totalQuestions,
        }) || ''
    );
    meta.textContent = summaryTemplate
        .replace(/\{\s*questions\s*\}/gi, String(totalQuestions));

    list.innerHTML = '';
    documents.forEach((doc) => {
        const questions = Array.isArray(doc.questions) ? doc.questions : [];
        if (questions.length === 0) {
            return;
        }

        const group = document.createElement('section');
        group.className = 'suggested-question-group';

        const title = document.createElement('h4');
        title.className = 'suggested-question-group-title';
        title.textContent = truncateTitle(doc.document_title || doc.document_id || tr('chat.suggested.documentFallback', 'Document'));
        group.appendChild(title);

        questions.forEach((question) => {
            const item = document.createElement('div');
            item.className = 'suggested-question-item';

            const questionText = typeof question === 'string' ? question : question?.question || '';
            const questionSource = typeof question === 'string' ? '' : (question?.source || '');

            const textWrap = document.createElement('div');
            textWrap.className = 'suggested-question-copy';

            const text = document.createElement('p');
            text.className = 'suggested-question-text';
            text.textContent = questionText;
            textWrap.appendChild(text);

            if (questionSource) {
                const source = document.createElement('p');
                source.className = 'suggested-question-source';
                source.textContent = questionSource;
                textWrap.appendChild(source);
            }

            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'copy-question-btn';
            const sendLabel = tr('messages.send', 'Send');
            button.title = sendLabel;
            button.setAttribute('aria-label', sendLabel);
            button.innerHTML = '<i class="bi bi-send" aria-hidden="true"></i>';
            button.addEventListener('click', () => copyQuestionToInput(questionText, button));

            item.appendChild(textWrap);
            item.appendChild(button);
            group.appendChild(item);
        });

        list.appendChild(group);
    });

    if (!list.children.length) {
        const questionCountTemplate = String(
            tr('chat.suggested.questionCount', '{questions} question(s)', { questions: totalQuestions }) || ''
        );
        setSuggestedQuestionsState({
            metaText: questionCountTemplate.replace(/\{\s*questions\s*\}/gi, String(totalQuestions)),
            emptyText: tr('chat.suggested.noUsableQuestions', 'No usable questions found.'),
        });
    }
}

function normalizeQuestionItems(items) {
    if (!Array.isArray(items)) {
        return [];
    }

    return items
        .map((item) => {
            if (typeof item === 'string') {
                const text = item.trim();
                return text || null;
            }
            if (item && typeof item.question === 'string') {
                const questionText = item.question.trim();
                const sourceText = item.source ? String(item.source).trim() : '';
                if (!questionText) {
                    return null;
                }
                return {
                    question: questionText,
                    source: sourceText || null,
                };
            }
            return null;
        })
        .filter(Boolean);
}

function getSuggestedQuestionsAssetUrl() {
    const currentLanguage = (() => {
        try {
            const { getCurrentLanguage } = window.ConfigModule || {};
            if (typeof getCurrentLanguage === 'function') {
                const language = String(getCurrentLanguage() || '').trim();
                if (language === 'en' || language === 'fr') {
                    return language;
                }
            }
        } catch (_) {
            // Ignore and fall back to default language.
        }
        return 'fr';
    })();

    const normalizedLanguage = currentLanguage === 'en' ? 'en' : 'fr';
    return `/static/assets/test_questions_${normalizedLanguage}.json`;
}

function buildQuestionSections(staticQuestions = {}, generatedDocuments = []) {
    const sections = [];

    const addSection = (titleKey, fallbackTitle, items) => {
        const cleanItems = normalizeQuestionItems(items);
        if (!cleanItems.length) {
            return;
        }
        sections.push({
            document_title: tr(titleKey, fallbackTitle),
            document_id: titleKey,
            questions: cleanItems,
        });
    };

    addSection('chat.suggested.commonQuestions', 'Questions courantes', staticQuestions.common_questions);
    addSection('chat.suggested.trapQuestions', 'Questions de vigilance', staticQuestions.trap_questions);

    const customQuestions = [];
    if (Array.isArray(generatedDocuments)) {
        generatedDocuments.forEach((document) => {
            if (!document || !Array.isArray(document.questions)) {
                return;
            }
            const sourceLabel = document.document_title || document.document_id || 'Document';
            document.questions.forEach((question) => {
                if (typeof question === 'string' && question.trim()) {
                    customQuestions.push({
                        question: question.trim(),
                        source: sourceLabel,
                    });
                }
                if (question && typeof question === 'object' && typeof question.question === 'string' && question.question.trim()) {
                    customQuestions.push({
                        question: question.question.trim(),
                        source: question.source ? String(question.source).trim() : sourceLabel,
                    });
                }
            });
        });
    }

    if (customQuestions.length === 0) {
        addSection('chat.suggested.customQuestions', 'Questions personnalisées', staticQuestions.custom_questions);
    } else {
        addSection('chat.suggested.customQuestions', 'Questions personnalisées', customQuestions);
    }

    return sections;
}

async function loadSuggestedQuestions() {
    const panel = document.getElementById('suggested-questions-panel');
    if (!panel) {
        return;
    }

    setSuggestedQuestionsState({
        metaText: tr('messages.loading', 'Loading...'),
        emptyText: tr('chat.suggested.loadingQuestions', 'Loading questions...'),
    });

    let staticQuestions = {};
    let generatedDocuments = [];

    try {
        const questionAssetUrl = getSuggestedQuestionsAssetUrl();
        const staticResponse = await fetch(questionAssetUrl, { method: 'GET' });

        if (!staticResponse.ok) {
            const legacyResponse = await fetch('/static/assets/test_questions.json', { method: 'GET' });
            if (legacyResponse.ok) {
                const staticPayload = await legacyResponse.json().catch(() => ({}));
                if (staticPayload && typeof staticPayload === 'object') {
                    staticQuestions = staticPayload;
                }
            }
        } else {
            const staticPayload = await staticResponse.json().catch(() => ({}));
            if (staticPayload && typeof staticPayload === 'object') {
                staticQuestions = staticPayload;
            }
        }
    } catch (error) {
        staticQuestions = {};
    }

    try {
        const { BACKEND_URL } = window.ConfigModule;
        const response = await fetch(`${BACKEND_URL}/api/generated-questions`, {
            method: 'GET',
            headers: buildApiHeaders(),
        });

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            const errorDetail = payload.detail || payload.message || response.statusText;
            throw new Error(errorDetail);
        }

        generatedDocuments = Array.isArray(payload.documents) ? payload.documents : [];
    } catch (error) {
        generatedDocuments = [];
    }

    const sections = buildQuestionSections(staticQuestions, generatedDocuments);
    if (sections.length === 0) {
        setSuggestedQuestionsState({
            metaText: tr('chat.errorTitle', 'Error'),
            emptyText: tr('chat.suggested.loadQuestionsError', 'Unable to load questions: {error}', { error: 'No question data available' }),
            isError: true,
        });
        return;
    }

    renderSuggestedQuestions(sections);
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
                <span class="message-model-name" style="display:none"></span>
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
    if (copyBtn) {
        const commentTitle = t('messages.comment') || 'Comment';
        copyBtn.title = commentTitle;
        copyBtn.setAttribute('aria-label', commentTitle);
    }
    if (likeBtn) {
        const likeTitle = t('messages.like') || 'Like';
        likeBtn.title = likeTitle;
        likeBtn.setAttribute('aria-label', likeTitle);
    }
    if (dislikeBtn) {
        const dislikeTitle = t('messages.dislike') || 'Dislike';
        dislikeBtn.title = dislikeTitle;
        dislikeBtn.setAttribute('aria-label', dislikeTitle);
    }

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

    // Copy button repurposed as a comment action popup
    if (copyBtn) {
        copyBtn.addEventListener('click', async () => {
            const questionId = copyBtn.dataset.questionId;
            if (!questionId) {
                console.log('Comment button clicked but no question_id available');
                return;
            }

            const placeholder = t('messages.comment_placeholder') || 'Your comment...';
            let trimmedComment = '';

            if (window.Swal && typeof window.Swal.fire === 'function') {
                const result = await window.Swal.fire({
                    title: t('messages.comment') || 'Comment',
                    input: 'textarea',
                    inputPlaceholder: placeholder,
                    inputAttributes: {
                        'aria-label': placeholder,
                    },
                    showCancelButton: true,
                    confirmButtonText: t('messages.save') || 'Save',
                    cancelButtonText: t('messages.cancel') || 'Cancel',
                    reverseButtons: true,
                    focusConfirm: false,
                    preConfirm: (value) => {
                        const cleaned = String(value || '').trim();
                        if (!cleaned) {
                            window.Swal.showValidationMessage(t('messages.comment_required') || 'Please enter a comment.');
                            return false;
                        }
                        return cleaned;
                    },
                });

                if (!result.isConfirmed) {
                    return;
                }
                trimmedComment = String(result.value || '').trim();
            } else {
                const commentText = window.prompt(placeholder, '');
                if (commentText === null) {
                    return;
                }
                trimmedComment = String(commentText).trim();
                if (!trimmedComment) {
                    window.alert(t('messages.comment_required') || 'Please enter a comment.');
                    return;
                }
            }

            try {
                const response = await fetch(`${BACKEND_URL}/api/add_comment`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        question_id: questionId,
                        comment: trimmedComment,
                    }),
                });

                const result = await response.json();
                if (result.status !== 'success') {
                    throw new Error(result.message || 'Comment save failed');
                }

                const originalIcon = copyBtn.innerHTML;
                copyBtn.innerHTML = '<i class="bi bi-check2"></i>';
                copyBtn.style.background = '#4caf50';
                setTimeout(() => {
                    copyBtn.innerHTML = originalIcon;
                    copyBtn.style.background = '';
                }, 2000);
            } catch (err) {
                console.error('Comment save failed:', err);
                if (window.Swal && typeof window.Swal.fire === 'function') {
                    window.Swal.fire({
                        icon: 'error',
                        title: t('chat.errorTitle', 'Error'),
                        text: t('messages.comment_error') || 'Error adding comment.',
                    });
                } else {
                    window.alert(t('messages.comment_error') || 'Error adding comment.');
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
        llm_model: getSelectedModel(),
        session_id: sessionId,
        bibliotheque: getSelectedLibrary()
    };

    // console.log('[Frontend][query] backend URL:', BACKEND_URL);
    // console.log('[Frontend][query] request payload:', requestData);

    // Create abort controller for cancellation
    currentAbortController = new AbortController();

    const requestHeaders = buildApiHeaders();
    const selectedModel = getSelectedModel();
    if (selectedModel) {
        requestHeaders['X-Selected-Model'] = selectedModel;
    }

    const endpointPath = getQueryEndpoint();

    const response = await fetch(`${BACKEND_URL}${endpointPath}`, {
        method: 'POST',
        headers: requestHeaders,
        body: JSON.stringify(requestData),
        signal: currentAbortController.signal
    });

    // console.log('[Frontend][query] response status:', response.status, response.statusText);

    if (!response.ok) {
        // if (response.status === 429) {
        //     const lang = getCurrentLanguage();
        //     const rateLimitMsg = lang === 'fr' 
        //         ? 'Limite de requêtes atteinte. Vous avez dépassé le nombre maximum de questions autorisées (10 par heure). Veuillez réessayer plus tard.'
        //         : 'Rate limit reached. You have exceeded the maximum number of allowed questions (10 per hour). Please try again later.';
        //     throw new Error(rateLimitMsg);
        // }
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
                const copyBtn = actionsDiv.querySelector('.copy-btn');
                if (likeBtn) likeBtn.dataset.questionId = questionId;
                if (dislikeBtn) dislikeBtn.dataset.questionId = questionId;
                if (copyBtn) copyBtn.dataset.questionId = questionId;
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
                        const copyBtn = actionsDiv.querySelector('.copy-btn');
                        if (likeBtn) likeBtn.dataset.questionId = questionId;
                        if (dislikeBtn) dislikeBtn.dataset.questionId = questionId;
                        if (copyBtn) copyBtn.dataset.questionId = questionId;
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

                    // Handle errors. Prefer a translation key when the backend sends one
                    // so the frontend can localize the final message based on the active UI language.
                    if (data.error) {
                        const errorKey = typeof data.error_key === 'string' && data.error_key.trim()
                            ? data.error_key.trim()
                            : 'messages.error';
                        const localizedError = tr(errorKey, data.error || tr('messages.error', 'Sorry, an error occurred. Please try again in a few moments.'));
                        console.error('Stream error:', data.error);
                        throw new Error(localizedError);
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
    const { getChatScrollContainer } = window.UIUtilsModule || {};
    const chatStream = document.getElementById('chat-stream') || chatContainer;
    const chatScrollContainer = getChatScrollContainer ? getChatScrollContainer() : chatContainer;
    
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

    chatStream.appendChild(userMessageDiv);
    chatStream.appendChild(messageDiv);

    const contentDiv = messageDiv.querySelector('.message-text');
    const actionsDiv = messageDiv.querySelector('.message-actions');
    
    setupMessageActions(messageDiv, contentDiv);
    setMessageModelBadge(actionsDiv, getSelectedModel(), getSelectedModelLabel());
    prepareUIForLoading();

    setTimeout(() => {
        // Keep old behavior semantics: scroll the effective scroll container
        // right after inserting the user and assistant messages.
        positionMessageAtBottom(chatScrollContainer || chatContainer, userMessageDiv, messageDiv);
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
        const translatedError = error && typeof error.message === 'string' ? error.message : t('messages.error');

        // Check if it's a rate limit error
        if (error && error.message && (error.message.includes('Limite de requêtes') || error.message.includes('Rate limit'))) {
            contentDiv.innerHTML = `<div style="color: #d32f2f; padding: 10px; background: #ffebee; border-radius: 4px; border-left: 4px solid #d32f2f;">
                <strong>⚠️ ${translatedError}</strong>
            </div>`;
        } else {
            contentDiv.textContent = translatedError || t('messages.error');
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
    loadSuggestedQuestions,
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
