(function () {
    const statusEl = document.getElementById("azure-auth-status");
    const startupStatusEl = document.getElementById("startup-auth-status");
    const accountInfoEl = document.getElementById("azure-account-info");
    const tokenClaimsEl = document.getElementById("azure-token-claims");
    const meResponseEl = document.getElementById("azure-me-response");
    const loginBtn = document.getElementById("azure-login-btn");
    const refreshBtn = document.getElementById("azure-refresh-token-btn");
    const logoutBtn = document.getElementById("azure-logout-btn");
    const sidebarLogoutLink = document.getElementById("sidebar-logout-link");
    const startupLoginBtn = document.getElementById("startup-login-btn");
    const startupForgotPasswordBtn = document.getElementById("startup-forgot-password-btn");
    const authGateOverlay = document.getElementById("auth-gate-overlay");
    const sidebarUserEmailEl = document.getElementById("sidebar-user-email");

    const TOKEN_KEY = "nutrifaq_admin_bearer_token";

    function tr(key, fallback, params) {
        let template = fallback;
        try {
            const translator = window.ConfigModule && typeof window.ConfigModule.t === "function"
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

        if (!params || typeof template !== "string") {
            return template;
        }

        return Object.keys(params).reduce((acc, name) => {
            return acc.replaceAll(`{${name}}`, String(params[name]));
        }, template);
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
                // Continue with next source.
            }
        }

        throw new Error(tr("azureAuth.msalUnavailable", "MSAL unavailable: unable to load authentication library."));
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

    function hasAuthUi() {
        return Boolean(
            document.getElementById("azure-auth-panel") ||
            authGateOverlay ||
            sidebarLogoutLink ||
            sidebarUserEmailEl ||
            logoutBtn
        );
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

    function setSidebarUserEmail(email) {
        if (!sidebarUserEmailEl) {
            return;
        }
        const safeEmail = typeof email === "string" ? email.trim() : "";
        const tokenEmail = getEmailFromStoredToken();
        const fallbackAccount = tr("azureAuth.accountDefault", "Account");
        const displayEmail = safeEmail || tokenEmail || fallbackAccount;
        sidebarUserEmailEl.textContent = displayEmail;
        sidebarUserEmailEl.title = displayEmail;
    }

    function getEmailFromStoredToken() {
        try {
            const token = localStorage.getItem(TOKEN_KEY) || "";
            if (!token) {
                return "";
            }

            const claims = decodeJwt(token) || {};
            const candidates = [
                claims.preferred_username,
                claims.upn,
                claims.email,
                claims.unique_name
            ];

            for (const value of candidates) {
                const text = typeof value === "string" ? value.trim() : "";
                if (text) {
                    return text;
                }
            }
        } catch (_) {
            // Ignore token parsing errors and fallback to default label.
        }

        return "";
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
            throw new Error(tr("azureAuth.missingTenantFrontend", "Missing ENTRA_TENANT_ID in frontend configuration."));
        }
        return `https://login.microsoftonline.com/${tenant}`;
    }

    function getClientId() {
        const clientId = (window.ENTRA_CLIENT_ID || "").trim();
        if (!clientId) {
            throw new Error(tr("azureAuth.missingClientIdFrontend", "Missing ENTRA_CLIENT_ID in frontend configuration."));
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
        return `${window.location.origin}/`;
    }

    function redirectToLogin() {
        const loginPath = "/";
        if (window.location.pathname !== loginPath) {
            window.location.assign(loginPath);
        }
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
            throw new Error(tr("azureAuth.msalLibraryNotFound", "MSAL library not found."));
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
        throw new Error(tr("azureAuth.tokenScopesFailed", "Unable to acquire a token with configured scopes."));
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
            return { status: "forbidden", detail: tr("azureAuth.usersAdminOnly", "Users endpoint is restricted to admins.") };
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

    async function resetQuestionLog(token) {
        const backendUrl = window.BACKEND_URL || "";
        const response = await fetch(`${backendUrl}/api/reset_question_log`, {
            method: "POST",
            headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
            },
        });

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || response.statusText || tr("azureAuth.unableResetLog", "Unable to reset the log."));
        }
        return payload;
    }

    async function loginAndExtract(msalApp) {
        setStatus(tr("azureAuth.statusConnecting", "Signing in with Azure..."), false);

        const loginResponse = await msalApp.loginPopup({ scopes: getLoginScopes() });
        const account = loginResponse.account;
        if (!account) {
            throw new Error(tr("azureAuth.noAccountAfterLogin", "No account returned after sign-in."));
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
        setSidebarUserEmail(account.username || account.name || "");
        prettyPrint(tokenClaimsEl, claims);

        try {
            const me = await fetchMe(accessToken);
            const usersData = (me && String(me.role || "").toLowerCase() === "admin")
                ? await fetchUsers(accessToken).catch((error) => ({ error: error.message }))
                : { status: "skipped", detail: tr("azureAuth.usersAdminOnly", "Users endpoint is restricted to admins.") };
            prettyPrint(meResponseEl, { me, users: usersData });
        } catch (apiError) {
            prettyPrint(meResponseEl, { error: apiError.message });
        }

        setStatus(tr("azureAuth.statusConnected", "Connected. Token extracted and injected into the Download section."), false);
        hideLoginGate();
    }

    async function refreshToken(msalApp) {
        const account = msalApp.getActiveAccount() || msalApp.getAllAccounts()[0];
        if (!account) {
            throw new Error(tr("azureAuth.noActiveAccount", "No active account. Please sign in first."));
        }

        msalApp.setActiveAccount(account);
        setStatus(tr("azureAuth.statusRefreshing", "Refreshing token..."), false);

        const tokenResponse = await acquireToken(msalApp, account);
        const accessToken = tokenResponse.accessToken;
        const claims = decodeJwt(accessToken) || tokenResponse.idTokenClaims || {};

        pushAdminToken(accessToken);
        setSidebarUserEmail(account.username || account.name || "");
        prettyPrint(tokenClaimsEl, claims);

        try {
            const me = await fetchMe(accessToken);
            const usersData = (me && String(me.role || "").toLowerCase() === "admin")
                ? await fetchUsers(accessToken).catch((error) => ({ error: error.message }))
                : { status: "skipped", detail: tr("azureAuth.usersAdminOnly", "Users endpoint is restricted to admins.") };
            prettyPrint(meResponseEl, { me, users: usersData });
        } catch (apiError) {
            prettyPrint(meResponseEl, { error: apiError.message });
        }

        setStatus(tr("azureAuth.statusRefreshed", "Token refreshed and information updated."), false);
    }

    async function logout(msalApp) {
        const account = msalApp ? (msalApp.getActiveAccount() || msalApp.getAllAccounts()[0]) : null;
        localStorage.removeItem(TOKEN_KEY);
        window.dispatchEvent(new CustomEvent("nutrifaq:admin-token-updated", { detail: { token: "" } }));

        prettyPrint(accountInfoEl, "-");
        prettyPrint(tokenClaimsEl, "-");
        prettyPrint(meResponseEl, "-");
        setSidebarUserEmail("");

        if (msalApp && account) {
            await msalApp.logoutPopup({ account });
        }

        setStatus(tr("azureAuth.statusDisconnected", "Signed out."), false);
        redirectToLogin();
    }

    async function init() {
        if (!hasAuthUi()) {
            return;
        }

        // Always hydrate the sidebar from local token claims when available.
        setSidebarUserEmail("");

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
                setSidebarUserEmail(existingAccount.username || existingAccount.name || "");
                setStatus(tr("azureAuth.statusAccountDetectedRefresh", "Account detected. Click Refresh token."), false);
                hideLoginGate();
            } else {
                setStatus(tr("azureAuth.statusNoActiveAccount", "No active Azure session detected."), false);
            }
        } catch (error) {
            // Keep sidebar token/logout behavior available even when MSAL bootstrap fails.
            setStatus(tr("azureAuth.statusInitError", "Azure auth initialization error: {error}", { error: error.message }), true);
        }

        if (loginBtn) {
            loginBtn.addEventListener("click", async () => {
                try {
                    await loginAndExtract(msalApp);
                } catch (error) {
                    setStatus(tr("azureAuth.statusLoginFailed", "Sign-in failed: {error}", { error: error.message }), true);
                }
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener("click", async () => {
                try {
                    await refreshToken(msalApp);
                } catch (error) {
                    setStatus(tr("azureAuth.statusRefreshFailed", "Refresh failed: {error}", { error: error.message }), true);
                }
            });
        }

        if (logoutBtn) {
            logoutBtn.addEventListener("click", async () => {
                try {
                    await logout(msalApp);
                } catch (error) {
                    setStatus(tr("azureAuth.statusLogoutFailed", "Sign-out failed: {error}", { error: error.message }), true);
                }
            });
        }

        if (sidebarLogoutLink) {
            sidebarLogoutLink.addEventListener("click", async (event) => {
                event.preventDefault();
                try {
                    await logout(msalApp);
                } catch (error) {
                    setStatus(tr("azureAuth.statusLogoutFailed", "Sign-out failed: {error}", { error: error.message }), true);
                }
            });
        }

        if (startupLoginBtn) {
            startupLoginBtn.addEventListener("click", async () => {
                try {
                    await loginAndExtract(msalApp);
                } catch (error) {
                    setStatus(tr("azureAuth.statusLoginFailed", "Sign-in failed: {error}", { error: error.message }), true);
                }
            });
        }

        if (startupForgotPasswordBtn) {
            startupForgotPasswordBtn.addEventListener("click", () => {
                window.open(getPasswordResetUrl(), "_blank", "noopener,noreferrer");
            });
        }

        if (msalApp && msalApp.getActiveAccount()) {
            try {
                await refreshToken(msalApp);
            } catch (error) {
                setStatus(tr("azureAuth.statusAutoRefreshFailed", "Automatic refresh failed: {error}", { error: error.message }), true);
                redirectToLogin();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})();
