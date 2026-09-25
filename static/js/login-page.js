(function () {
    const statusEl = document.getElementById("login-page-status");
    const signInBtn = document.getElementById("login-page-signin");
    const resetBtn = document.getElementById("login-page-reset");
    const BACKEND_URL = window.BACKEND_URL || "";
    const LOCALES_BASE_URL = `${window.location.origin}/static/locales`;

    const TOKEN_KEY = "nutrifaq_admin_bearer_token";
    const USER_PROFILE_KEY = "nutrifaq_user_profile";
    const USER_ASSIGNMENTS_KEY = "nutrifaq_user_assignments";
    const AUTO_RELOGIN_ONCE_KEY = "nutrifaq_auto_relogin_once";
    let i18nConfig = null;
    let currentLang = "fr";

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function getUrlParameter(name) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(name);
    }

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function getLoginTranslation(lang) {
        const root = i18nConfig || {};
        const scoped = root[lang] && root[lang].loginPage ? root[lang].loginPage : null;
        const fallback = root.fr && root.fr.loginPage ? root.fr.loginPage : null;
        return scoped || fallback || {};
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function tr(key, params) {
        const dict = getLoginTranslation(currentLang);
        const fallbackDict = getLoginTranslation("fr");
        const template = dict[key] || fallbackDict[key] || key;
        if (!params || typeof template !== "string") {
            return template;
        }
        return Object.keys(params).reduce((acc, name) => {
            return acc.replaceAll(`{${name}}`, String(params[name]));
        }, template);
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function deepMerge(baseConfig, overrideConfig) {
        const result = { ...(baseConfig || {}) };
        Object.entries(overrideConfig || {}).forEach(([key, value]) => {
            const baseValue = result[key];
            if (
                baseValue &&
                typeof baseValue === "object" &&
                !Array.isArray(baseValue) &&
                value &&
                typeof value === "object" &&
                !Array.isArray(value)
            ) {
                result[key] = deepMerge(baseValue, value);
            } else {
                result[key] = value;
            }
        });
        return result;
    }

    async function fetchJsonOrThrow(url) {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Config endpoint returned ${response.status}`);
        }
        return response.json();
    }

    async function loadI18nConfig() {
        const supportedLanguages = ["fr", "en"];

        const localeEntries = await Promise.all(
            supportedLanguages.map(async (lang) => {
                const normalizedLang = String(lang).trim();
                try {
                    const localeConfig = await fetchJsonOrThrow(`${LOCALES_BASE_URL}/${normalizedLang}.json`);
                    return [normalizedLang, localeConfig || {}];
                } catch (error) {
                    if (normalizedLang === "fr") {
                        throw error;
                    }
                    return [normalizedLang, {}];
                }
            })
        );

        i18nConfig = Object.fromEntries(localeEntries);
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function resolveLanguage() {
        const urlLang = getUrlParameter("lang");
        if (urlLang === "fr" || urlLang === "en") {
            currentLang = urlLang;
            localStorage.setItem("preferredLanguage", urlLang);
            return;
        }
        currentLang = "fr";
        localStorage.setItem("preferredLanguage", "fr");
        const url = new URL(window.location);
        url.searchParams.set("lang", currentLang);
        window.history.replaceState({}, "", url);
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function applyLoginTranslations() {
        document.querySelectorAll("[data-i18n]").forEach((element) => {
            const key = element.getAttribute("data-i18n");
            const translated = key ? tr(key.replace("loginPage.", "")) : "";
            if (translated) {
                element.textContent = translated;
            }
        });

        const titleEl = document.querySelector("title[data-i18n]");
        if (titleEl) {
            const titleText = tr("title");
            if (titleText) {
                document.title = titleText;
            }
        }

        const htmlEl = document.documentElement;
        if (htmlEl) {
            htmlEl.lang = currentLang;
        }
    }

    async function ensureMsalLoaded() {
        if (window.msal && window.msal.PublicClientApplication) {
            return;
        }

        const candidates = [
            "https://cdn.jsdelivr.net/npm/@azure/msal-browser@2.38.4/lib/msal-browser.min.js",
            "https://unpkg.com/@azure/msal-browser@2.38.4/lib/msal-browser.min.js"
        ];

        for (const src of candidates) {
            try {
                await loadScript(src);
                if (window.msal && window.msal.PublicClientApplication) {
                    return;
                }
            } catch (_) {
                // Try next source.
                console.warn(`Failed to load MSAL script from ${src}, trying next source.`);
            }
        }

        throw new Error("MSAL indisponible: impossible de charger la bibliothèque d'authentification.");
    }

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function loadScript(src) {
        return new Promise((resolve, reject) => {
            if (window.msal && window.msal.PublicClientApplication) {
                resolve();
                return;
            }

            // Remove stale script tags to avoid hanging on already-settled elements.
            document.querySelectorAll("script[src]").forEach((existing) => {
                if (existing.src === src) {
                    existing.remove();
                }
            });

            const timeoutMs = 8000;
            const script = document.createElement("script");
            script.src = src;
            script.async = true;
            script.crossOrigin = "anonymous";

            const timer = setTimeout(() => {
                reject(new Error(`Timeout loading ${src}`));
            }, timeoutMs);

            script.onload = () => {
                clearTimeout(timer);
                if (window.msal && window.msal.PublicClientApplication) {
                    resolve();
                    return;
                }
                reject(new Error(`Loaded ${src} but MSAL not available`));
            };
            script.onerror = () => {
                clearTimeout(timer);
                reject(new Error(`Failed to load ${src}`));
            };

            document.head.appendChild(script);
        });
    }

    // Purpose: Updates UI or local state so downstream interactions stay consistent.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function setStatus(message, isError) {
        if (!statusEl) {
            return;
        }
        statusEl.textContent = message;
        statusEl.classList.toggle("error", Boolean(isError));
    }

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function getAuthority() {
        const tenant = (window.ENTRA_TENANT_ID || "").trim();
        if (!tenant) {
            throw new Error(tr("missingTenant"));
        }
        return `https://login.microsoftonline.com/${tenant}`;
    }

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function getClientId() {
        const clientId = (window.ENTRA_CLIENT_ID || "").trim();
        if (!clientId) {
            throw new Error(tr("missingClientId"));
        }
        return clientId;
    }

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function getAudience() {
        const configured = (window.ENTRA_AUDIENCE || "").trim();
        if (configured) {
            return configured;
        }
        return `api://${getClientId()}`;
    }

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function getRedirectUri() {
        const configured = (window.ENTRA_REDIRECT_URI || "").trim();
        if (configured) {
            return configured;
        }
        return `${window.location.origin}/`;
    }

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function getPasswordResetUrl() {
        const domain = (window.ENTRA_UPN_DOMAIN || "").trim();
        if (domain) {
            return `https://passwordreset.microsoftonline.com/?whr=${encodeURIComponent(domain)}`;
        }
        return "https://passwordreset.microsoftonline.com/";
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function buildApiScopeCandidates() {
        const audience = getAudience();
        const configuredScope = (window.ENTRA_TOKEN_SCOPE || "").trim();
        return [configuredScope, `${audience}/access_as_user`, `${audience}/.default`].filter(Boolean);
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function buildLoginScopes() {
        // For interactive sign-in, never include .default with resource-specific scopes.
        const audience = getAudience();
        const configuredScope = (window.ENTRA_TOKEN_SCOPE || "").trim();
        const delegatedScope = configuredScope && !configuredScope.endsWith("/.default")
            ? configuredScope
            : `${audience}/access_as_user`;
        return ["openid", "profile", "email", delegatedScope];
    }

    // Purpose: Fetches and prepares data needed by the UI flow that calls this function.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function getMsalInstance() {
        if (!window.msal || !window.msal.PublicClientApplication) {
            throw new Error(tr("msalNotFound"));
        }

        return new window.msal.PublicClientApplication({
            auth: {
                clientId: getClientId(),
                authority: getAuthority(),
                redirectUri: getRedirectUri()
            },
            cache: {
                cacheLocation: "localStorage",
                storeAuthStateInCookie: false
            }
        });
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function formatErrorMessage(error) {
        if (!error) {
            return tr("unknownError");
        }
        const code = error.errorCode || error.code || "";
        const message = error.errorMessage || error.message || String(error);
        return code ? `${code}: ${message}` : message;
    }

    async function acquireApiToken(msalApp, account) {
        const scopes = buildApiScopeCandidates();
        let lastError = null;

        for (const scope of scopes) {
            const req = { account, scopes: [scope] };
            try {
                return await msalApp.acquireTokenSilent(req);
            } catch (silentError) {
                try {
                    return await msalApp.acquireTokenPopup(req);
                } catch (popupError) {
                    lastError = popupError;
                }
            }
        }

        if (lastError) {
            throw lastError;
        }
        throw new Error(tr("tokenAcquireFailed"));
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function goToApp() {
        window.location.href = "/index.html";
    }

    // Purpose: Implements a focused frontend behavior used by this module.
    // Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
    function clearStaleSessionState() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_PROFILE_KEY);
        localStorage.removeItem(USER_ASSIGNMENTS_KEY);
    }

    async function fetchCurrentUserProfile(token) {
        const response = await fetch(`${BACKEND_URL}/api/users/me`, {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || response.statusText);
        }
        return payload;
    }

    async function fetchUserAssignments(token) {
        const response = await fetch(`${BACKEND_URL}/api/users`, {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        const payload = await response.json().catch(() => ({}));
        if (response.status === 403) {
            return null;
        }
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || response.statusText);
        }
        return payload;
    }

    async function resolveUserContext(token) {
        const profile = await fetchCurrentUserProfile(token);
        let assignments = null;
        if (profile && String(profile.role || "").toLowerCase() === "admin") {
            try {
                assignments = await fetchUserAssignments(token);
            } catch (_) {
                assignments = null;
            }
        }

        localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(profile));
        if (assignments) {
            localStorage.setItem(USER_ASSIGNMENTS_KEY, JSON.stringify(assignments));
        } else {
            localStorage.removeItem(USER_ASSIGNMENTS_KEY);
        }

        return { profile, assignments };
    }

    async function resetUserLog(token) {
        const response = await fetch(`${BACKEND_URL}/api/reset_question_log`, {
            method: "POST",
            headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
            },
        });

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || response.statusText || "Unable to reset the log.");
        }
        return payload;
    }

    async function signIn(msalApp) {
        setStatus(tr("statusRedirectIdentity"), false);
        await msalApp.loginRedirect({ scopes: buildLoginScopes() });
    }

    async function init() {
        try {
            resolveLanguage();
            await loadI18nConfig();
            applyLoginTranslations();
        } catch (error) {
            console.error("Unable to initialize login i18n:", error);
        }

        let msalApp;
        try {
            await ensureMsalLoaded();
            msalApp = getMsalInstance();
            if (typeof msalApp.initialize === "function") {
                await msalApp.initialize();
            }

            if (typeof msalApp.handleRedirectPromise === "function") {
                const redirectResult = await msalApp.handleRedirectPromise();
                if (redirectResult && redirectResult.account) {
                    msalApp.setActiveAccount(redirectResult.account);
                }
            }
        } catch (error) {
            setStatus(tr("statusConfigError", { error: formatErrorMessage(error) }), true);
            return;
        }

        const existingAccount = msalApp.getActiveAccount() || msalApp.getAllAccounts()[0];
        if (existingAccount) {
            msalApp.setActiveAccount(existingAccount);
            try {
                const tokenResponse = await acquireApiToken(msalApp, existingAccount);
                const accessToken = tokenResponse.accessToken;
                sessionStorage.removeItem(AUTO_RELOGIN_ONCE_KEY);
                localStorage.setItem(TOKEN_KEY, accessToken);

                const { profile } = await resolveUserContext(accessToken);
                setStatus(tr("statusSessionDetected", { role: profile.role || tr("unknownRole") }), false);
                setTimeout(goToApp, 150);
                return;
            } catch (error) {
                setStatus(tr("statusSessionExpired"), true);
                clearStaleSessionState();

                // Retry once with interactive sign-in to recover from stale cached sessions.
                if (!sessionStorage.getItem(AUTO_RELOGIN_ONCE_KEY)) {
                    sessionStorage.setItem(AUTO_RELOGIN_ONCE_KEY, "1");
                    try {
                        await signIn(msalApp);
                        return;
                    } catch (retryError) {
                        setStatus(tr("statusLoginFailed", { error: formatErrorMessage(retryError) }), true);
                    }
                }
            }
        }

        if (signInBtn) {
            signInBtn.addEventListener("click", async () => {
                try {
                    setStatus(tr("statusRedirectLogin"), false);
                    await signIn(msalApp);
                } catch (error) {
                    setStatus(tr("statusLoginFailed", { error: formatErrorMessage(error) }), true);
                }
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener("click", () => {
                window.open(getPasswordResetUrl(), "_blank", "noopener,noreferrer");
            });
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})();
