/*
====================================================
 firebase-config.js – Firebase App Check Configuration
----------------------------------------------------
 Initializes Firebase App Check to protect API endpoints from unauthorized access.
 Handles reCAPTCHA v3, debug tokens, and secure fetch for the Translator Agent UI.
====================================================
*/

// ===================================
// FIREBASE APP CHECK CONFIGURATION
// ===================================

/**
 * Firebase App Check initialization
 * Protects API endpoints from unauthorized access
 *
 * Configuration via environment variables:
 *   - FIREBASE_PROJECT_ID: Your Firebase project ID
 *   - RECAPTCHA_SITE_KEY: reCAPTCHA v3 site key for App Check
 *
 * Exports:
 *   - initialize: Initialize Firebase App Check
 *   - getToken: Get App Check token
 *   - secureFetch: Fetch with App Check token
 *   - isEnabled: Check if App Check is enabled
 */

// Firebase configuration (must match your Firebase project)
const firebaseConfig = {
    // These values are safe to expose in client-side code
    apiKey: window.FIREBASE_API_KEY || "",
    authDomain: window.FIREBASE_AUTH_DOMAIN || "",
    projectId: window.FIREBASE_PROJECT_ID || "",
    storageBucket: window.FIREBASE_STORAGE_BUCKET || "",
    messagingSenderId: window.FIREBASE_MESSAGING_SENDER_ID || "",
    appId: window.FIREBASE_APP_ID || "",
    measurementId: window.FIREBASE_MEASUREMENT_ID || ""
};

// App Check configuration
// Frontend App Check is intentionally disabled.
// const APP_CHECK_ENABLED = true;
const APP_CHECK_ENABLED = false;
const RECAPTCHA_SITE_KEY = window.RECAPTCHA_SITE_KEY || "6LeI834sAAAAAN0tbvdmSeajxCYCj3uarepl_jSh";
const APP_CHECK_DEBUG_TOKEN = window.APP_CHECK_DEBUG_TOKEN || ""; // Debug token for testing


import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { initializeAppCheck, ReCaptchaV3Provider, getToken } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app-check.js";



let appCheck = null;
let appCheckInitialized = false;

/**
 * Initialize Firebase and App Check
 */
async function initializeFirebaseAppCheck() {
    if (!APP_CHECK_ENABLED) {
        console.log('[App Check] Disabled - requests will proceed without verification');
        return null;
    }

    if (appCheckInitialized) {
        return appCheck;
    }

    try {
        // Initialize Firebase
        const app = initializeApp(firebaseConfig);
        console.log('[App Check] Firebase initialized');

        // Enable debug mode for localhost (generates debug token automatically)
        const isLocalhost = location.hostname === "localhost" || location.hostname === "127.0.0.1";
        if (isLocalhost) {
            self.FIREBASE_APPCHECK_DEBUG_TOKEN = true;
            console.log('🔧 [App Check] Debug mode enabled for localhost');
            console.log('⚠️ [App Check] IMPORTANT: Look for a message like "Firebase App Check debug token:" in the console');
            console.log('⚠️ [App Check] Copy that token and add it to Firebase Console:');
            console.log('   → https://console.firebase.google.com/u/0/project/' + firebaseConfig.projectId + '/appcheck/apps');
        }

        // Check for valid reCAPTCHA key
        const hasValidRecaptcha = RECAPTCHA_SITE_KEY && 
                                 RECAPTCHA_SITE_KEY.length > 10 && 
                                 !RECAPTCHA_SITE_KEY.includes('YOUR_');

        if (hasValidRecaptcha) {
            // console.log('[App Check] Using reCAPTCHA v3 with key:', RECAPTCHA_SITE_KEY.substring(0, 20) + '...');
            // console.log('[App Check] App ID:', firebaseConfig.appId);
            // console.log('[App Check] Project ID:', firebaseConfig.projectId);
            
            // ReCaptchaV3Provider automatically handles debug tokens when FIREBASE_APPCHECK_DEBUG_TOKEN is set
            appCheck = initializeAppCheck(app, {
                provider: new ReCaptchaV3Provider(RECAPTCHA_SITE_KEY),
                isTokenAutoRefreshEnabled: true
            });
            appCheckInitialized = true;
            // console.log('[App Check] ✅ Initialized with reCAPTCHA v3' + (isLocalhost ? ' (debug mode)' : ' (production mode)'));
            
            // if (!isLocalhost) {
            //     console.log('[App Check] Production mode - ensure your app is registered in Firebase Console:');
            //     console.log('   → https://console.firebase.google.com/u/0/project/' + firebaseConfig.projectId + '/appcheck');
            // }
        }
        else {
            console.warn('[App Check] No valid reCAPTCHA site key provided');
            console.warn('[App Check] reCAPTCHA key:', RECAPTCHA_SITE_KEY ? 'present but invalid' : 'not provided');
        }

        return appCheck;
    } catch (error) {
        console.error('[App Check] Initialization error:', error);
        return null;
    }
}

/**
 * Get App Check token
 */
async function getAppCheckToken() {
    if (!APP_CHECK_ENABLED) {
        console.log('[App Check] Skipped - disabled');
        return null;
    }

    if (!appCheckInitialized) {
        console.warn('[App Check] Not initialized, initializing...');
        await initializeFirebaseAppCheck();

        if (!appCheckInitialized) {
            console.error('[App Check] Initialization failed');
            return null;
        }
    }

    try {
        // console.log('[App Check] Requesting token...');
        
        let token = null;
        try {
            const result = await getToken(appCheck);
            token = result?.token;
        } catch (tokenError) {
            // Handle specific App Check errors
            console.error('[App Check] Error details:', {
                code: tokenError?.code,
                message: tokenError?.message,
                customData: tokenError?.customData,
                appId: firebaseConfig.appId,
                projectId: firebaseConfig.projectId
            });
            
            if (tokenError?.code === 'appCheck/throttled') {
                console.error('[App Check] THROTTLED - Too many failed attempts');
                console.error('→ This usually means reCAPTCHA is not properly configured');
                console.error('→ Go to: https://console.firebase.google.com/u/0/project/' + firebaseConfig.projectId + '/appcheck');
                console.error('→ Register your web app (' + firebaseConfig.appId + ') with reCAPTCHA v3');
                console.error('→ Use site key: ' + RECAPTCHA_SITE_KEY);
                return null;
            } else if (tokenError?.code === 'appCheck/fetch-status-error') {
                console.error('[App Check] CONFIGURATION ERROR');
                console.error('→ Status:', tokenError?.customData?.httpStatus);
                console.error('→ Check Firebase Console App Check settings');
                console.error('→ URL: https://console.firebase.google.com/u/0/project/' + firebaseConfig.projectId + '/appcheck');
                return null;
            } else {
                throw tokenError; // Re-throw other errors
            }
        }

        if (!token) {
            console.error('[App Check] Token missing in response');
            return null;
        }

        // console.log('[App Check] Token obtained',token.substring(0, 20) + '...');
        return token;

    } catch (error) {
        console.error('[App Check] Error retrieving token:', {
            name: error?.name,
            message: error?.message,
            code: error?.code
        });
        return null;
    }
}

/**
 * Enhanced fetch with App Check token
 * Use this instead of native fetch for API calls
 */
async function secureFetch(url, options = {}) {
    // Initialize App Check if not already done
    if (!appCheckInitialized && APP_CHECK_ENABLED) {
        await initializeFirebaseAppCheck();
    }

    // Get App Check token
    const token = await getAppCheckToken();

    // Add App Check token to headers
    const headers = {
        ...options.headers
    };

    if (token) {
        headers['X-Firebase-AppCheck'] = token;
    }

    // Make the request
    return fetch(url, {
        ...options,
        headers
    });
}

// Auto-initialize on page load
// Frontend App Check is disabled; leaving these calls commented for reference.
// if (document.readyState === 'loading') {
//     document.addEventListener('DOMContentLoaded', initializeFirebaseAppCheck);
// } else {
//     initializeFirebaseAppCheck();
// }

// Intercept fetch to automatically add App Check tokens
// const originalFetch = window.fetch;
// window.fetch = async function(...args) {
//     let [url, options = {}] = args;
//     
//     // Check if this is an API call to our backend
//     const isBackendCall = typeof url === 'string' && (
//         url.includes('/api/') || 
//         url.includes('/query') ||
//         (window.BACKEND_URL && url.startsWith(window.BACKEND_URL))
//     );
//     
//     if (isBackendCall && APP_CHECK_ENABLED) {
//         // Ensure App Check is initialized
//         if (!appCheckInitialized) {
//             await initializeFirebaseAppCheck();
//         }
//         
//         // Get App Check token
//         const token = await getAppCheckToken();
//         
//         // Add token to headers
//         if (token) {
//             options.headers = {
//                 ...options.headers,
//                 'X-Firebase-AppCheck': token
//             };
//         }
//     }
//     
//     // Call original fetch
//     return originalFetch(url, options);
// };

// Export for use in other modules
window.FirebaseAppCheck = {
    initialize: initializeFirebaseAppCheck,
    getToken: getAppCheckToken,
    secureFetch: secureFetch,
    isEnabled: () => APP_CHECK_ENABLED && appCheckInitialized
};
