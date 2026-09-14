// ===================================
// UI UTILITIES & INTERACTIONS
// ===================================

/**
 * UI utilities module
 * Handles sidebar, keyboard detection, scroll indicator, mobile handling, and popups
 */

// State variables
let isKeyboardVisible = false;
let previousViewportHeight = window.innerHeight;

/**
 * Detect if the device is mobile
 */
function isMobileDevice() {
    if (window.innerWidth <= 768) return true;
    if ('ontouchstart' in window || navigator.maxTouchPoints > 0) {
        if (window.innerWidth <= 1024) return true;
    }
    return false;
}

/**
 * Focus input box only on desktop browsers
 */
function handleFocus() {
    const inputBox = document.getElementById('input-box');
    if (inputBox && !isMobileDevice()) {
        inputBox.focus();
    }
}

// ===================================
// KEYBOARD DETECTION (MOBILE)
// ===================================

/**
 * Initialize mobile keyboard detection
 */
function initKeyboardDetection() {
    // Method 1: Visual Viewport API
    if (window.visualViewport) {
        let lastHeight = window.visualViewport.height;
        
        window.visualViewport.addEventListener('resize', () => {
            const currentHeight = window.visualViewport.height;
            const heightDiff = lastHeight - currentHeight;
            
            if (heightDiff > 150) {
                if (!isKeyboardVisible) {
                    isKeyboardVisible = true;
                    onKeyboardShow();
                }
            } else if (heightDiff < -150) {
                if (isKeyboardVisible) {
                    isKeyboardVisible = false;
                    onKeyboardHide();
                }
            }
            
            lastHeight = currentHeight;
        });
    }
    
    // Method 2: Window resize fallback
    window.addEventListener('resize', () => {
        const currentHeight = window.innerHeight;
        const heightDiff = previousViewportHeight - currentHeight;
        
        if (heightDiff > 150) {
            if (!isKeyboardVisible) {
                isKeyboardVisible = true;
                onKeyboardShow();
            }
        } else if (heightDiff < -150) {
            if (isKeyboardVisible) {
                isKeyboardVisible = false;
                onKeyboardHide();
            }
        }
        
        previousViewportHeight = currentHeight;
    });
    
    // Method 3: Focus/blur detection
    document.addEventListener('focusin', (e) => {
        if (isMobileDevice() && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
            setTimeout(() => {
                const currentHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
                const heightDiff = previousViewportHeight - currentHeight;
                
                if (heightDiff > 100 && !isKeyboardVisible) {
                    isKeyboardVisible = true;
                    onKeyboardShow();
                }
            }, 300);
        }
    });
    
    document.addEventListener('focusout', (e) => {
        if (isMobileDevice() && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
            setTimeout(() => {
                const currentHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
                const heightDiff = previousViewportHeight - currentHeight;
                
                if (Math.abs(heightDiff) < 100 && isKeyboardVisible) {
                    isKeyboardVisible = false;
                    onKeyboardHide();
                }
            }, 300);
        }
    });
}

/**
 * Callback when keyboard appears
 */
function onKeyboardShow() {
    console.log('Mobile keyboard shown');
    document.body.classList.add('keyboard-visible');
    
    const chatContainer = document.getElementById('chat-container');
    if (chatContainer && isMobileDevice()) {
        setTimeout(() => {
            document.documentElement.scrollTop = 0;
            document.body.scrollTop = 0;
            window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
            
            chatContainer.scrollTo({
                top: chatContainer.scrollHeight,
                behavior: 'smooth'
            });
        }, 100);
    }
}

/**
 * Callback when keyboard disappears
 */
function onKeyboardHide() {
    console.log('Mobile keyboard hidden');
    document.body.classList.remove('keyboard-visible');
    
    const chatContainer = document.getElementById('chat-container');
    if (isMobileDevice() && chatContainer) {
        setTimeout(() => {
            document.documentElement.scrollTop = 0;
            document.body.scrollTop = 0;
            window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
            
            chatContainer.scrollTo({
                top: chatContainer.scrollHeight,
                behavior: 'smooth'
            });
        }, 100);
    }
}

// ===================================
// SCROLL INDICATOR
// ===================================

/**
 * Create scroll indicator
 */
function createScrollIndicator() {
    const scrollIndicator = document.createElement('div');
    scrollIndicator.className = 'scroll-indicator';
    scrollIndicator.style.opacity = '0.5';
    scrollIndicator.innerHTML = `
        <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/>
        </svg>
    `;
    
    const mainContainer = document.querySelector('.content');
    if (mainContainer) {
        mainContainer.appendChild(scrollIndicator);
    }
    
    const chatContainer = document.getElementById('chat-container');
    
    scrollIndicator.addEventListener('click', () => {
        if (chatContainer) {
            chatContainer.scrollTo({
                top: chatContainer.scrollHeight,
                behavior: 'smooth'
            });
        }
    });
    
    return scrollIndicator;
}

/**
 * Update scroll indicator visibility
 */
function updateScrollIndicator() {
    const chatContainer = document.getElementById('chat-container');
    const scrollIndicator = document.querySelector('.scroll-indicator');
    
    if (!chatContainer || !scrollIndicator) return;
    
    const threshold = 100;
    const isNearBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < threshold;
    
    if (isNearBottom) {
        scrollIndicator.classList.remove('visible');
    } else {
        scrollIndicator.classList.add('visible');
    }
}

// ===================================
// SIDEBAR NAVIGATION
// ===================================

/**
 * Initialize sidebar
 */
function initSidebar() {
    const menuToggle = document.getElementById('menu-toggle');
    const sidebar = document.getElementById('sidebar');
    const closeSidebar = document.getElementById('close-sidebar');
    const overlay = document.getElementById('overlay');
    
    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            if (sidebar) sidebar.classList.add('open');
            if (overlay) overlay.classList.add('active');
        });
    }
    
    if (closeSidebar) {
        closeSidebar.addEventListener('click', () => {
            if (sidebar) sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('active');
        });
    }
    
    if (overlay) {
        overlay.addEventListener('click', () => {
            if (sidebar) sidebar.classList.remove('open');
            overlay.classList.remove('active');
        });
    }
}

/**
 * Close sidebar
 */
function closeSidebarMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');
    
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
}

// ===================================
// COOKIE CONSENT
// ===================================

/**
 * Check cookie consent
 */
function checkCookieConsent() {
    const consent = localStorage.getItem('cookieConsent');
    const cookieBanner = document.getElementById('cookie-banner');
    
    if (!consent && cookieBanner) {
        setTimeout(() => {
            cookieBanner.classList.add('show');
        }, 1000);
    }
}

/**
 * Initialize cookie consent handlers
 */
function initCookieConsent() {
    const cookieBanner = document.getElementById('cookie-banner');
    const cookieAccept = document.getElementById('cookie-accept');
    const cookieDecline = document.getElementById('cookie-decline');
    
    if (cookieAccept) {
        cookieAccept.addEventListener('click', () => {
            localStorage.setItem('cookieConsent', 'accepted');
            if (cookieBanner) cookieBanner.classList.remove('show');
        });
    }
    
    if (cookieDecline) {
        cookieDecline.addEventListener('click', () => {
            localStorage.setItem('cookieConsent', 'declined');
            if (cookieBanner) cookieBanner.classList.remove('show');
        });
    }
    
    checkCookieConsent();
}

// ===================================
// LEGAL & PRIVACY POPUPS
// ===================================

/**
 * Show legal notice popup
 */
function showLegalNotice() {
    const { t, getMainConfig, getCurrentLanguage } = window.ConfigModule;
    const mainConfig = getMainConfig();
    const currentLanguage = getCurrentLanguage();
    const langData = mainConfig[currentLanguage] || mainConfig['fr'];
    const legalContent = langData.legal;
    
    let html = `<h2 style='margin-top:0;text-align:center;'>${legalContent.title}</h2>`;
    html += legalContent.content.map(line => `<p>${line}</p>`).join('');

    Swal.fire({
        title: '',
        html: `<div style="text-align:left;">${html}</div>`,
        confirmButtonText: t('sidebar.closeButton') || 'Fermer',
        customClass: {
            popup: 'legal-popup-swal',
            title: 'legal-popup-title',
            content: 'legal-popup-content'
        },
        width: 700
    });
}

/**
 * Show privacy policy popup
 */
function showPrivacyPolicy() {
    const { t, getMainConfig, getCurrentLanguage } = window.ConfigModule;
    const mainConfig = getMainConfig();
    const currentLanguage = getCurrentLanguage();
    const langData = mainConfig[currentLanguage] || mainConfig['fr'];
    const privacy = langData.privacy;
    
    let html = `<h2 style='margin-top:0;text-align:center;'>${privacy.title}</h2>`;
    if (privacy.lastUpdate) {
        html += `<p><em>${privacy.lastUpdate}</em></p>`;
    }
    html += privacy.content.map(line => {
        if (/^\d+\./.test(line)) {
            return `<h3>${line}</h3>`;
        } else if (line.trim() === '') {
            return '';
        } else {
            return `<p>${line}</p>`;
        }
    }).join('');
    
    html = html.replace(/(<h3>[^<]+<\/h3>)(<li>.*?<\/li>)+/gs, function(match) {
        const h3 = match.match(/<h3>[^<]+<\/h3>/)[0];
        const lis = match.match(/<li>.*?<\/li>/gs).join('');
        return h3 + '<ul>' + lis + '</ul>';
    });
    
    Swal.fire({
        title: '',
        html: `<div style="text-align:left;">${html}</div>`,
        confirmButtonText: t('sidebar.closeButton') || 'Fermer',
        customClass: {
            popup: 'legal-popup-swal',
            title: 'legal-popup-title',
            content: 'legal-popup-content'
        },
        width: 700
    });
}

/**
 * Show about popup
 */
function showAbout() {
    const { t, getMainConfig, getCurrentLanguage } = window.ConfigModule;
    const mainConfig = getMainConfig();
    const currentLanguage = getCurrentLanguage();
    const langData = mainConfig[currentLanguage] || mainConfig['fr'];
    const about = langData.about || {};
    
    let html = `<h2 style='margin-top:0;text-align:center;'>${about.title}</h2>`;

    if (Array.isArray(about.content)) {
        html += '<ul style="text-align:left;">';
        about.content.forEach(line => {
            if (line.trim() !== '') {
                html += `<li style="margin-bottom:8px;">${line}</li>`;
            }
        });
        html += '</ul>';
    } else if (typeof about.content === 'string') {
        html += `<div style="text-align:left;">${about.content}</div>`;
    }

    Swal.fire({
        title: '',
        html: `<div style="text-align:left;">${html}</div>`,
        icon: 'info',
        confirmButtonText: about.closeButton || 'Fermer',
        customClass: { popup: 'swal2-dok2u-about' }
    });
}

/**
 * Initialize legal/privacy links
 */
function initLegalLinks() {
    const legalLink = document.getElementById('legal-link');
    const privacyLink = document.getElementById('privacy-link');
    const aboutLink = document.getElementById('about-link');
    
    if (legalLink) {
        legalLink.addEventListener('click', (e) => {
            e.preventDefault();
            showLegalNotice();
            closeSidebarMenu();
        });
    }
    
    if (privacyLink) {
        privacyLink.addEventListener('click', (e) => {
            e.preventDefault();
            showPrivacyPolicy();
            closeSidebarMenu();
        });
    }
    
    if (aboutLink) {
        aboutLink.addEventListener('click', (e) => {
            e.preventDefault();
            showAbout();
            closeSidebarMenu();
        });
    }
}

// Export for use in other modules
window.UIUtilsModule = {
    isMobileDevice,
    handleFocus,
    initKeyboardDetection,
    createScrollIndicator,
    updateScrollIndicator,
    initSidebar,
    closeSidebarMenu,
    initCookieConsent,
    checkCookieConsent,
    showLegalNotice,
    showPrivacyPolicy,
    showAbout,
    initLegalLinks
};
