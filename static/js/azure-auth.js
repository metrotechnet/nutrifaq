(function () {
    const statusEl = document.getElementById("azure-auth-status");
    const startupStatusEl = document.getElementById("startup-auth-status");
    const accountInfoEl = document.getElementById("azure-account-info");
    const tokenClaimsEl = document.getElementById("azure-token-claims");
    const meResponseEl = document.getElementById("azure-me-response");
    const loginBtn = document.getElementById("azure-login-btn");
    const refreshBtn = document.getElementById("azure-refresh-token-btn");
    const logoutBtn = document.getElementById("azure-logout-btn");
    const startupLoginBtn = document.getElementById("startup-login-btn");
    const startupForgotPasswordBtn = document.getElementById("startup-forgot-password-btn");
    const authGateOverlay = document.getElementById("auth-gate-overlay");

    const TOKEN_KEY = "nutrifaq_admin_bearer_token";

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
                // Continue with next source.
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

    function hasPanel() {
        return Boolean(document.getElementById("azure-auth-panel") || authGateOverlay);
    }

    function setStatus(message, isError) {
        if (!statusEl) {
            if (startupStatusEl) {
                startupStatusEl.textContent = message;
                startupStatusEl.classList.toggle("error", Boolean(isError));
            }
            return;
        }
        statusEl.textContent = message;
        statusEl.classList.toggle("error", Boolean(isError));
        if (startupStatusEl) {
            startupStatusEl.textContent = message;
            startupStatusEl.classList.toggle("error", Boolean(isError));
        }
    }

    function showLoginGate() {
        if (authGateOverlay) {
            authGateOverlay.style.display = "flex";
        }
    }

    function hideLoginGate() {
        if (authGateOverlay) {
            authGateOverlay.style.display = "none";
        }
    }

    function prettyPrint(el, obj) {
        if (!el) {
            return;
        }
        el.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
    }

    function decodeJwt(token) {
        try {
            const parts = token.split(".");
            if (parts.length < 2) {
                return null;
            }
            const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
            const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
            return JSON.parse(atob(padded));
        } catch (error) {
            return null;
        }
    }

    function getAuthority() {
        const tenant = (window.ENTRA_TENANT_ID || "").trim();
        if (!tenant) {
            throw new Error("ENTRA_TENANT_ID manquant dans la configuration frontend.");
        }
        return `https://login.microsoftonline.com/${tenant}`;
    }

    function getClientId() {
        const clientId = (window.ENTRA_CLIENT_ID || "").trim();
        if (!clientId) {
            throw new Error("ENTRA_CLIENT_ID manquant dans la configuration frontend.");
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

    function buildApiScopeCandidates() {
        const configuredScope = (window.ENTRA_TOKEN_SCOPE || "").trim();
        const audience = getAudience();
        const candidates = [
            configuredScope,
            `${audience}/access_as_user`,
            `${audience}/.default`
        ].filter(Boolean);
        return Array.from(new Set(candidates));
    }

    function getLoginScopes() {
        // For interactive sign-in, never include .default with resource-specific scopes.
        const configuredScope = (window.ENTRA_TOKEN_SCOPE || "").trim();
        const audience = getAudience();
        const delegatedScope = configuredScope && !configuredScope.endsWith("/.default")
            ? configuredScope
            : `${audience}/access_as_user`;
        return ["openid", "profile", "email", delegatedScope];
    }

    function getPasswordResetUrl() {
        const domain = (window.ENTRA_UPN_DOMAIN || "").trim();
        if (domain) {
            return `https://passwordreset.microsoftonline.com/?whr=${encodeURIComponent(domain)}`;
        }
        return "https://passwordreset.microsoftonline.com/";
    }

    function getMsalInstance() {
        if (!window.msal || !window.msal.PublicClientApplication) {
            throw new Error("Bibliothèque MSAL introuvable.");
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

    async function acquireToken(msalApp, account) {
        const scopeCandidates = buildApiScopeCandidates();
        let lastError = null;

        for (const scope of scopeCandidates) {
            const req = { account, scopes: [scope] };
            try {
                return await msalApp.acquireTokenSilent(req);
            } catch (silentErr) {
                try {
                    return await msalApp.acquireTokenPopup(req);
                } catch (popupErr) {
                    lastError = popupErr;
                }
            }
        }

        if (lastError) {
            throw lastError;
        }
        throw new Error("Impossible d'acquérir un token avec les scopes configurés.");
    }

    async function fetchMe(token) {
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

    async function fetchUsers(token) {
        const backendUrl = window.BACKEND_URL || "";
        const response = await fetch(`${backendUrl}/api/users`, {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        const payload = await response.json().catch(() => ({}));
        if (response.status === 403) {
            return { status: "forbidden", detail: "Endpoint réservé aux admins." };
        }
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || response.statusText);
        }
        return payload;
    }

    function pushAdminToken(token) {
        localStorage.setItem(TOKEN_KEY, token);
        window.dispatchEvent(new CustomEvent("nutrifaq:admin-token-updated", { detail: { token } }));
    }

    async function loginAndExtract(msalApp) {
        setStatus("Connexion Azure en cours...", false);

        const loginResponse = await msalApp.loginPopup({ scopes: getLoginScopes() });
        const account = loginResponse.account;
        if (!account) {
            throw new Error("Aucun compte retourné après la connexion.");
        }

        msalApp.setActiveAccount(account);
        const tokenResponse = await acquireToken(msalApp, account);
        const accessToken = tokenResponse.accessToken;
        const claims = decodeJwt(accessToken) || tokenResponse.idTokenClaims || {};

        pushAdminToken(accessToken);
        prettyPrint(accountInfoEl, {
            username: account.username,
            name: account.name,
            tenantId: account.tenantId,
            homeAccountId: account.homeAccountId
        });
        prettyPrint(tokenClaimsEl, claims);

        try {
            const me = await fetchMe(accessToken);
            const usersData = (me && String(me.role || "").toLowerCase() === "admin")
                ? await fetchUsers(accessToken).catch((error) => ({ error: error.message }))
                : { status: "skipped", detail: "Liste utilisateurs reservee aux admins." };
            prettyPrint(meResponseEl, { me, users: usersData });
        } catch (apiError) {
            prettyPrint(meResponseEl, { error: apiError.message });
        }

        setStatus("Connecté. Token extrait et injecté dans la section Télécharger.", false);
        hideLoginGate();
    }

    async function refreshToken(msalApp) {
        const account = msalApp.getActiveAccount() || msalApp.getAllAccounts()[0];
        if (!account) {
            throw new Error("Aucun compte actif. Connectez-vous d'abord.");
        }

        msalApp.setActiveAccount(account);
        setStatus("Rafraîchissement du token en cours...", false);

        const tokenResponse = await acquireToken(msalApp, account);
        const accessToken = tokenResponse.accessToken;
        const claims = decodeJwt(accessToken) || tokenResponse.idTokenClaims || {};

        pushAdminToken(accessToken);
        prettyPrint(tokenClaimsEl, claims);

        try {
            const me = await fetchMe(accessToken);
            const usersData = (me && String(me.role || "").toLowerCase() === "admin")
                ? await fetchUsers(accessToken).catch((error) => ({ error: error.message }))
                : { status: "skipped", detail: "Liste utilisateurs reservee aux admins." };
            prettyPrint(meResponseEl, { me, users: usersData });
        } catch (apiError) {
            prettyPrint(meResponseEl, { error: apiError.message });
        }

        setStatus("Token rafraîchi et informations mises à jour.", false);
    }

    async function logout(msalApp) {
        const account = msalApp.getActiveAccount() || msalApp.getAllAccounts()[0];
        localStorage.removeItem(TOKEN_KEY);
        window.dispatchEvent(new CustomEvent("nutrifaq:admin-token-updated", { detail: { token: "" } }));

        prettyPrint(accountInfoEl, "-");
        prettyPrint(tokenClaimsEl, "-");
        prettyPrint(meResponseEl, "-");

        if (account) {
            await msalApp.logoutPopup({ account });
        }

        setStatus("Déconnecté.", false);
        showLoginGate();
    }

    async function init() {
        if (!hasPanel()) {
            return;
        }

        let msalApp;
        try {
            await ensureMsalLoaded();
            msalApp = getMsalInstance();
            const existingAccount = msalApp.getActiveAccount() || msalApp.getAllAccounts()[0];
            if (existingAccount) {
                msalApp.setActiveAccount(existingAccount);
                prettyPrint(accountInfoEl, {
                    username: existingAccount.username,
                    name: existingAccount.name,
                    tenantId: existingAccount.tenantId,
                    homeAccountId: existingAccount.homeAccountId
                });
                setStatus("Compte détecté. Cliquez sur Rafraîchir le token.", false);
                hideLoginGate();
            } else {
                showLoginGate();
            }
        } catch (error) {
            setStatus(`Erreur initialisation Azure auth: ${error.message}`, true);
            return;
        }

        if (loginBtn) {
            loginBtn.addEventListener("click", async () => {
                try {
                    await loginAndExtract(msalApp);
                } catch (error) {
                    setStatus(`Connexion échouée: ${error.message}`, true);
                }
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener("click", async () => {
                try {
                    await refreshToken(msalApp);
                } catch (error) {
                    setStatus(`Rafraîchissement échoué: ${error.message}`, true);
                }
            });
        }

        if (logoutBtn) {
            logoutBtn.addEventListener("click", async () => {
                try {
                    await logout(msalApp);
                } catch (error) {
                    setStatus(`Déconnexion échouée: ${error.message}`, true);
                }
            });
        }

        if (startupLoginBtn) {
            startupLoginBtn.addEventListener("click", async () => {
                try {
                    await loginAndExtract(msalApp);
                } catch (error) {
                    setStatus(`Connexion échouée: ${error.message}`, true);
                }
            });
        }

        if (startupForgotPasswordBtn) {
            startupForgotPasswordBtn.addEventListener("click", () => {
                window.open(getPasswordResetUrl(), "_blank", "noopener,noreferrer");
            });
        }

        if (msalApp.getActiveAccount()) {
            try {
                await refreshToken(msalApp);
            } catch (error) {
                setStatus(`Rafraîchissement automatique échoué: ${error.message}`, true);
                showLoginGate();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})();
