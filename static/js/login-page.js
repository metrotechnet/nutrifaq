(function () {
    const statusEl = document.getElementById("login-page-status");
    const signInBtn = document.getElementById("login-page-signin");
    const resetBtn = document.getElementById("login-page-reset");

    const TOKEN_KEY = "nutrifaq_admin_bearer_token";
    const USER_PROFILE_KEY = "nutrifaq_user_profile";
    const USER_ASSIGNMENTS_KEY = "nutrifaq_user_assignments";

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

    function setStatus(message, isError) {
        if (!statusEl) {
            return;
        }
        statusEl.textContent = message;
        statusEl.classList.toggle("error", Boolean(isError));
    }

    function getAuthority() {
        const tenant = (window.ENTRA_TENANT_ID || "").trim();
        if (!tenant) {
            throw new Error("ENTRA_TENANT_ID manquant.");
        }
        return `https://login.microsoftonline.com/${tenant}`;
    }

    function getClientId() {
        const clientId = (window.ENTRA_CLIENT_ID || "").trim();
        if (!clientId) {
            throw new Error("ENTRA_CLIENT_ID manquant.");
        }
        return clientId;
    }

    function getAudience() {
        const configured = (window.ENTRA_AUDIENCE || "").trim();
        if (configured) {
            return configured;
        }
        return `api://${getClientId()}`;
    }

    function getRedirectUri() {
        const configured = (window.ENTRA_REDIRECT_URI || "").trim();
        if (configured) {
            return configured;
        }
        return `${window.location.origin}/login.html`;
    }

    function getPasswordResetUrl() {
        const domain = (window.ENTRA_UPN_DOMAIN || "").trim();
        if (domain) {
            return `https://passwordreset.microsoftonline.com/?whr=${encodeURIComponent(domain)}`;
        }
        return "https://passwordreset.microsoftonline.com/";
    }

    function buildApiScopeCandidates() {
        const audience = getAudience();
        const configuredScope = (window.ENTRA_TOKEN_SCOPE || "").trim();
        return [configuredScope, `${audience}/access_as_user`, `${audience}/.default`].filter(Boolean);
    }

    function buildLoginScopes() {
        // For interactive sign-in, never include .default with resource-specific scopes.
        const audience = getAudience();
        const configuredScope = (window.ENTRA_TOKEN_SCOPE || "").trim();
        const delegatedScope = configuredScope && !configuredScope.endsWith("/.default")
            ? configuredScope
            : `${audience}/access_as_user`;
        return ["openid", "profile", "email", delegatedScope];
    }

    function getMsalInstance() {
        if (!window.msal || !window.msal.PublicClientApplication) {
            throw new Error("MSAL indisponible.");
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

    function formatErrorMessage(error) {
        if (!error) {
            return "Erreur inconnue";
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
        throw new Error("Impossible de récupérer le token API.");
    }

    function goToApp() {
        window.location.href = "/index.html";
    }

    async function fetchCurrentUserProfile(token) {
        const backendUrl = window.BACKEND_URL || "";
        const response = await fetch(`${backendUrl}/api/users/me`, {
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
        const backendUrl = window.BACKEND_URL || "";
        const response = await fetch(`${backendUrl}/api/users`, {
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

    async function signIn(msalApp) {
        setStatus("Connexion en cours...", false);
        let loginResponse;
        try {
            loginResponse = await msalApp.loginPopup({ scopes: buildLoginScopes() });
        } catch (error) {
            // Popup can be blocked in some browser settings. Fall back to redirect flow.
            if (error && (error.errorCode === "popup_window_error" || error.errorCode === "user_cancelled" || error.errorCode === "monitor_window_timeout")) {
                setStatus("Popup bloquée ou annulée. Redirection vers Azure...", false);
                await msalApp.loginRedirect({ scopes: buildLoginScopes() });
                return;
            }
            throw error;
        }
        const account = loginResponse.account;
        if (!account) {
            throw new Error("Connexion réussie mais aucun compte retourné.");
        }

        msalApp.setActiveAccount(account);
        const tokenResponse = await acquireApiToken(msalApp, account);
        const accessToken = tokenResponse.accessToken;
        localStorage.setItem(TOKEN_KEY, accessToken);

        const { profile } = await resolveUserContext(accessToken);

        setStatus(`Connexion réussie (${profile.role || "role inconnu"}). Redirection...`, false);
        setTimeout(goToApp, 200);
    }

    async function init() {
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
            setStatus(`Erreur config auth: ${formatErrorMessage(error)}`, true);
            return;
        }

        const existingAccount = msalApp.getActiveAccount() || msalApp.getAllAccounts()[0];
        if (existingAccount) {
            msalApp.setActiveAccount(existingAccount);
            try {
                const tokenResponse = await acquireApiToken(msalApp, existingAccount);
                const accessToken = tokenResponse.accessToken;
                localStorage.setItem(TOKEN_KEY, accessToken);

                const { profile } = await resolveUserContext(accessToken);
                setStatus(`Session détectée (${profile.role || "role inconnu"}). Redirection...`, false);
                setTimeout(goToApp, 150);
                return;
            } catch (error) {
                setStatus("Session détectée, mais token expiré. Reconnexion requise.", true);
            }
        }

        if (signInBtn) {
            signInBtn.addEventListener("click", async () => {
                try {
                    setStatus("Ouverture de la fenêtre de connexion...", false);
                    await signIn(msalApp);
                } catch (error) {
                    setStatus(`Connexion échouée: ${formatErrorMessage(error)}`, true);
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
