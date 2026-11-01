(function () {
    const statusEl = document.getElementById("login-page-status");
    const loginForm = document.getElementById("login-page-form");
    const emailInput = document.getElementById("login-page-email");
    const passwordInput = document.getElementById("login-page-password");
    const signInBtn = document.getElementById("login-page-signin");
    const BACKEND_URL = window.BACKEND_URL || "";
    const LOCALES_BASE_URL = `${window.location.origin}/static/locales`;

    const TOKEN_KEY = "nutrifaq_admin_bearer_token";
    const USER_PROFILE_KEY = "nutrifaq_user_profile";
    const USER_ASSIGNMENTS_KEY = "nutrifaq_user_assignments";
    let i18nConfig = null;
    let currentLang = "fr";

    function getUrlParameter(name) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(name);
    }

    function getLoginTranslation(lang) {
        const root = i18nConfig || {};
        const scoped = root[lang] && root[lang].loginPage ? root[lang].loginPage : null;
        const fallback = root.fr && root.fr.loginPage ? root.fr.loginPage : null;
        return scoped || fallback || {};
    }

    function getNestedTranslation(dict, key) {
        return String(key || "")
            .split(".")
            .reduce((value, segment) => {
                if (!value || typeof value !== "object") {
                    return undefined;
                }
                return value[segment];
            }, dict);
    }

    function tr(key, params) {
        const dict = getLoginTranslation(currentLang);
        const fallbackDict = getLoginTranslation("fr");
        const template = getNestedTranslation(dict, key) || getNestedTranslation(fallbackDict, key) || key;
        if (!params || typeof template !== "string") {
            return template;
        }
        return Object.keys(params).reduce((acc, name) => {
            return acc.replaceAll(`{${name}}`, String(params[name]));
        }, template);
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

        if (emailInput) {
            emailInput.placeholder = tr("emailPlaceholder");
        }
        if (passwordInput) {
            passwordInput.placeholder = tr("passwordPlaceholder");
        }
    }

    function setStatus(message, isError) {
        if (!statusEl) {
            return;
        }
        statusEl.textContent = message;
        statusEl.classList.toggle("error", Boolean(isError));
    }

    function hasSwal() {
        return Boolean(window.Swal && typeof window.Swal.fire === "function");
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
        } catch (_) {
            return null;
        }
    }

    function tokenLooksValid(token) {
        if (!token) {
            return false;
        }
        const claims = decodeJwt(token) || {};
        const exp = Number(claims.exp || 0);
        if (!Number.isFinite(exp) || exp <= 0) {
            return false;
        }
        return exp > Math.floor(Date.now() / 1000);
    }

    function goToApp() {
        window.location.replace("/index.html");
    }

    function clearStaleSessionState() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_PROFILE_KEY);
        localStorage.removeItem(USER_ASSIGNMENTS_KEY);
    }

    async function fetchCurrentUserProfile(token) {
        const response = await fetch(`${BACKEND_URL}/api/users/me`, {
            headers: {
                Authorization: `Bearer ${token}`,
            },
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
                Authorization: `Bearer ${token}`,
            },
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

    async function updateOwnPassword(token, temporaryPassword, newPassword) {
        const response = await fetch(`${BACKEND_URL}/api/users/me/password`, {
            method: "PUT",
            headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                temporary_password: temporaryPassword,
                new_password: newPassword,
            }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || response.statusText || tr("statusPasswordChangeFailed"));
        }
        return payload;
    }

    async function enforceFirstLoginPasswordChange(token, profile) {
        if (!profile || !profile.must_change_password) {
            return;
        }
        if (!hasSwal()) {
            throw new Error(tr("statusPasswordPopupUnavailable"));
        }

        setStatus(tr("statusPasswordChangeRequired"), false);
        const result = await window.Swal.fire({
            title: tr("firstLoginPassword.title"),
            html: `
                <div style="display:flex; flex-direction:column; gap:0.6rem; text-align:left;">
                    <p style="margin:0;">${tr("firstLoginPassword.description")}</p>
                    <label for="first-login-temporary-password">${tr("firstLoginPassword.temporaryPasswordLabel")}</label>
                    <input id="first-login-temporary-password" class="swal2-input" type="password" placeholder="${tr("firstLoginPassword.temporaryPasswordPlaceholder")}" style="margin:0;" />
                    <label for="first-login-password">${tr("firstLoginPassword.newPasswordLabel")}</label>
                    <input id="first-login-password" class="swal2-input" type="password" placeholder="${tr("firstLoginPassword.newPasswordPlaceholder")}" style="margin:0;" />
                    <label for="first-login-password-confirm">${tr("firstLoginPassword.confirmPasswordLabel")}</label>
                    <input id="first-login-password-confirm" class="swal2-input" type="password" placeholder="${tr("firstLoginPassword.confirmPasswordPlaceholder")}" style="margin:0;" />
                </div>
            `,
            allowOutsideClick: false,
            allowEscapeKey: false,
            showCancelButton: false,
            confirmButtonText: tr("firstLoginPassword.confirmAction"),
            confirmButtonColor: "#1d75c2",
            preConfirm: () => {
                const temporaryPassword = String(document.getElementById("first-login-temporary-password")?.value || "");
                const nextPassword = String(document.getElementById("first-login-password")?.value || "");
                const confirmPassword = String(document.getElementById("first-login-password-confirm")?.value || "");
                if (!temporaryPassword) {
                    window.Swal.showValidationMessage(tr("firstLoginPassword.temporaryPasswordRequired"));
                    return null;
                }
                if (nextPassword.length < 8) {
                    window.Swal.showValidationMessage(tr("firstLoginPassword.passwordTooShort"));
                    return null;
                }
                if (nextPassword !== confirmPassword) {
                    window.Swal.showValidationMessage(tr("firstLoginPassword.passwordMismatch"));
                    return null;
                }
                return { temporaryPassword, newPassword: nextPassword };
            },
        });

        const temporaryPassword = result && result.value ? String(result.value.temporaryPassword || "") : "";
        const newPassword = result && result.value ? String(result.value.newPassword || "") : "";
        if (!temporaryPassword || !newPassword) {
            throw new Error(tr("statusPasswordChangeRequired"));
        }

        await updateOwnPassword(token, temporaryPassword, newPassword);
        profile.must_change_password = false;
        localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(profile));
        setStatus(tr("statusPasswordChanged"), false);
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
        return { profile };
    }

    async function loginWithPassword(email, password) {
        const body = new URLSearchParams();
        body.set("username", email);
        body.set("password", password);
        const response = await fetch(`${BACKEND_URL}/auth/jwt/login`, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: body.toString(),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || response.statusText || tr("statusLoginFailedSimple"));
        }
        const token = String(payload.access_token || "").trim();
        if (!token) {
            throw new Error(tr("statusTokenMissing"));
        }
        return token;
    }

    async function init() {
        try {
            resolveLanguage();
            await loadI18nConfig();
            applyLoginTranslations();
        } catch (error) {
            console.error("Unable to initialize login i18n:", error);
        }

        const existingToken = localStorage.getItem(TOKEN_KEY) || "";
        if (tokenLooksValid(existingToken)) {
            try {
                const { profile } = await resolveUserContext(existingToken);
                if (profile && profile.must_change_password) {
                    clearStaleSessionState();
                    setStatus(tr("statusCredentialsRequired"), false);
                    return;
                }
                setStatus(tr("statusSessionDetected", { role: profile.role || tr("unknownRole") }), false);
                setTimeout(goToApp, 150);
                return;
            } catch (_) {
                clearStaleSessionState();
            }
        }

        if (!loginForm || !emailInput || !passwordInput) {
            setStatus(tr("statusFormMissing"), true);
            return;
        }

        loginForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const email = String(emailInput.value || "").trim();
            const password = String(passwordInput.value || "");
            if (!email || !password) {
                setStatus(tr("statusCredentialsRequired"), true);
                return;
            }

            if (signInBtn) {
                signInBtn.disabled = true;
            }
            setStatus(tr("statusSigningIn"), false);

            try {
                const token = await loginWithPassword(email, password);
                localStorage.setItem(TOKEN_KEY, token);
                const { profile } = await resolveUserContext(token);
                await enforceFirstLoginPasswordChange(token, profile);
                setStatus(tr("statusSessionDetected", { role: profile.role || tr("unknownRole") }), false);
                setTimeout(goToApp, 150);
            } catch (error) {
                clearStaleSessionState();
                setStatus(tr("statusLoginFailed", { error: error.message || tr("unknownError") }), true);
            } finally {
                if (signInBtn) {
                    signInBtn.disabled = false;
                }
            }
        });
    }

    document.addEventListener("DOMContentLoaded", init);
})();
