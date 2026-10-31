(function () {
    const TOKEN_KEY = "nutrifaq_admin_bearer_token";
    const BACKEND_URL = (window.BACKEND_URL || "").replace(/\/$/, "");

    const statusEl = document.getElementById("users-admin-status");
    const refreshBtn = document.getElementById("users-admin-refresh-btn");
    const addBtn = document.getElementById("users-admin-add-btn");
    const tableBody = document.getElementById("users-admin-table-body");
    const gateEl = document.getElementById("users-admin-gate");
    const shellEl = document.getElementById("users-admin-shell");

    let currentUserId = "";

    function redirectToApp() {
        window.location.replace("/index.html");
    }

    function setStatus(message, isError) {
        if (!statusEl) {
            return;
        }
        statusEl.textContent = message;
        statusEl.classList.toggle("error", Boolean(isError));
    }

    function setPageReady(ready) {
        if (gateEl) {
            gateEl.hidden = Boolean(ready);
        }
        if (shellEl) {
            shellEl.classList.toggle("users-admin-shell-hidden", !ready);
            shellEl.setAttribute("aria-hidden", ready ? "false" : "true");
        }
    }

    function hasSwal() {
        return Boolean(window.Swal && typeof window.Swal.fire === "function");
    }

    async function showPopup(icon, title, text) {
        if (!hasSwal()) {
            return;
        }
        await window.Swal.fire({
            icon,
            title,
            text,
            confirmButtonColor: "#1d75c2",
        });
    }

    async function confirmPopup(title, text, confirmText) {
        if (!hasSwal()) {
            return window.confirm(text);
        }
        const result = await window.Swal.fire({
            icon: "warning",
            title,
            text,
            showCancelButton: true,
            confirmButtonText: confirmText,
            cancelButtonText: "Annuler",
            confirmButtonColor: "#d33",
        });
        return Boolean(result.isConfirmed);
    }

    function getTokenOrRedirect() {
        const token = localStorage.getItem(TOKEN_KEY) || "";
        if (!token) {
            window.location.replace("/login.html");
            return "";
        }
        return token;
    }

    async function apiRequest(path, options) {
        const token = getTokenOrRedirect();
        if (!token) {
            throw new Error("Missing session token.");
        }
        const response = await fetch(`${BACKEND_URL}${path}`, {
            ...options,
            headers: {
                Authorization: `Bearer ${token}`,
                ...(options && options.headers ? options.headers : {}),
            },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || response.statusText || "Request failed.");
        }
        return payload;
    }

    function createIconButton(iconClass, title, onClick) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "users-admin-icon-btn";
        btn.title = title;
        btn.setAttribute("aria-label", title);
        btn.innerHTML = `<i class="${iconClass}"></i>`;
        btn.addEventListener("click", onClick);
        return btn;
    }

    function renderUsers(users) {
        tableBody.innerHTML = "";
        if (!Array.isArray(users) || users.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 4;
            cell.textContent = "Aucun utilisateur trouvé.";
            row.appendChild(cell);
            tableBody.appendChild(row);
            return;
        }

        users.forEach((user) => {
            const row = document.createElement("tr");

            const emailCell = document.createElement("td");
            emailCell.textContent = user.email || user.object_id;
            if (user.object_id === currentUserId) {
                const selfTag = document.createElement("div");
                selfTag.className = "users-admin-row-self";
                selfTag.textContent = "Vous";
                emailCell.appendChild(selfTag);
            }

            const roleCell = document.createElement("td");
            const roleSelect = document.createElement("select");
            ["client", "collaborator", "admin"].forEach((role) => {
                const option = document.createElement("option");
                option.value = role;
                option.textContent = role;
                roleSelect.appendChild(option);
            });
            roleSelect.value = String(user.role || "client").toLowerCase();
            roleSelect.disabled = true;
            roleSelect.classList.add("users-admin-field-readonly");
            roleCell.appendChild(roleSelect);

            const passwordCell = document.createElement("td");
            const passwordField = document.createElement("div");
            passwordField.className = "users-admin-password-field";
            const passwordInput = document.createElement("input");
            passwordInput.type = "password";
            passwordInput.minLength = 8;
            passwordInput.placeholder = "********";
            passwordInput.disabled = true;
            passwordInput.classList.add("users-admin-field-readonly");
            let passwordDraft = "";
            passwordInput.addEventListener("input", () => {
                passwordDraft = String(passwordInput.value || "");
            });
            const passwordToggleBtn = createIconButton("bi bi-eye", "Afficher le mot de passe", () => {
                const showing = passwordInput.type === "text";
                passwordInput.type = showing ? "password" : "text";
                passwordToggleBtn.innerHTML = showing ? '<i class="bi bi-eye"></i>' : '<i class="bi bi-eye-slash"></i>';
                passwordToggleBtn.title = showing ? "Afficher le mot de passe" : "Masquer le mot de passe";
                passwordToggleBtn.setAttribute("aria-label", passwordToggleBtn.title);
            });
            passwordToggleBtn.classList.add("users-admin-password-toggle");
            passwordToggleBtn.disabled = true;
            passwordField.appendChild(passwordInput);
            passwordField.appendChild(passwordToggleBtn);
            passwordCell.appendChild(passwordField);

            const actionsCell = document.createElement("td");
            const actionsWrap = document.createElement("div");
            actionsWrap.className = "users-admin-row-actions";
            const inlineStatus = document.createElement("div");
            inlineStatus.className = "users-admin-status-inline";

            let roleEditing = false;
            let passwordEditing = false;
            let savedRoleValue = String(user.role || "client").toLowerCase();

            const refreshCancelVisibility = () => {
                if (roleEditing || passwordEditing) {
                    cancelEditBtn.classList.remove("is-hidden");
                } else {
                    cancelEditBtn.classList.add("is-hidden");
                }
            };

            const setRoleEditMode = (editing) => {
                roleEditing = editing;
                roleSelect.disabled = !editing;
                roleSelect.classList.toggle("users-admin-field-readonly", !editing);
                editRoleBtn.classList.toggle("is-saving", editing);
                editRoleBtn.title = editing ? "Enregistrer le rôle" : "Modifier le rôle";
                editRoleBtn.setAttribute("aria-label", editRoleBtn.title);
                editRoleBtn.innerHTML = editing ? '<i class="bi bi-check2"></i>' : '<i class="bi bi-person-gear"></i>';
                refreshCancelVisibility();
            };

            const setPasswordEditMode = (editing) => {
                passwordEditing = editing;
                passwordInput.disabled = !editing;
                passwordToggleBtn.disabled = !editing;
                passwordInput.classList.toggle("users-admin-field-readonly", !editing);
                passwordInput.placeholder = editing ? "Nouveau mot de passe" : "********";
                editPasswordBtn.classList.toggle("is-saving", editing);
                editPasswordBtn.title = editing ? "Enregistrer le mot de passe" : "Modifier le mot de passe";
                editPasswordBtn.setAttribute("aria-label", editPasswordBtn.title);
                editPasswordBtn.innerHTML = editing ? '<i class="bi bi-check2"></i>' : '<i class="bi bi-key"></i>';

                if (editing) {
                    passwordInput.value = passwordDraft;
                    passwordInput.focus();
                } else {
                    passwordInput.type = "password";
                    passwordToggleBtn.innerHTML = '<i class="bi bi-eye"></i>';
                    passwordToggleBtn.title = "Afficher le mot de passe";
                    passwordToggleBtn.setAttribute("aria-label", "Afficher le mot de passe");
                }
                refreshCancelVisibility();
            };

            const editRoleBtn = createIconButton("bi bi-person-gear", "Modifier le rôle", async () => {
                if (!roleEditing) {
                    if (passwordEditing) {
                        inlineStatus.textContent = "Enregistrez ou annulez le mot de passe avant de modifier le rôle.";
                        await showPopup("warning", "Action en cours", "Terminez d'abord l'édition du mot de passe.");
                        return;
                    }
                    setRoleEditMode(true);
                    inlineStatus.textContent = "Mode édition du rôle activé.";
                    roleSelect.focus();
                    return;
                }

                inlineStatus.textContent = "Mise à jour du rôle...";
                try {
                    const nextRole = String(roleSelect.value || "client").toLowerCase();
                    await apiRequest(`/api/users/${encodeURIComponent(user.object_id)}/role`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ role: nextRole }),
                    });
                    savedRoleValue = nextRole;
                    setRoleEditMode(false);
                    inlineStatus.textContent = "Rôle mis à jour.";
                    await showPopup("success", "Rôle mis à jour", `Le rôle de ${user.email || user.object_id} a été mis à jour.`);
                    await loadUsers();
                } catch (error) {
                    inlineStatus.textContent = `Erreur: ${error.message}`;
                    await showPopup("error", "Échec de mise à jour", error.message || "Une erreur est survenue.");
                }
            });

            const editPasswordBtn = createIconButton("bi bi-key", "Modifier le mot de passe", async () => {
                if (!passwordEditing) {
                    if (roleEditing) {
                        inlineStatus.textContent = "Enregistrez ou annulez le rôle avant de modifier le mot de passe.";
                        await showPopup("warning", "Action en cours", "Terminez d'abord l'édition du rôle.");
                        return;
                    }
                    setPasswordEditMode(true);
                    inlineStatus.textContent = "Mode édition du mot de passe activé.";
                    return;
                }

                const nextPassword = String(passwordInput.value || "");
                if (nextPassword.length < 8) {
                    inlineStatus.textContent = "Le mot de passe doit contenir au moins 8 caractères.";
                    await showPopup("warning", "Mot de passe invalide", "Le mot de passe doit contenir au moins 8 caractères.");
                    return;
                }

                inlineStatus.textContent = "Mise à jour du mot de passe...";
                try {
                    await apiRequest(`/api/users/${encodeURIComponent(user.object_id)}/password`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ password: nextPassword }),
                    });
                    passwordDraft = "";
                    passwordInput.value = "";
                    setPasswordEditMode(false);
                    inlineStatus.textContent = "Mot de passe mis à jour.";
                    await showPopup("success", "Mot de passe mis à jour", `Le mot de passe de ${user.email || user.object_id} a été modifié.`);
                } catch (error) {
                    inlineStatus.textContent = `Erreur: ${error.message}`;
                    await showPopup("error", "Échec du changement", error.message || "Une erreur est survenue.");
                }
            });

            const cancelEditBtn = createIconButton("bi bi-x-lg", "Annuler", async () => {
                if (roleEditing) {
                    roleSelect.value = savedRoleValue;
                    setRoleEditMode(false);
                }
                if (passwordEditing) {
                    passwordDraft = "";
                    passwordInput.value = "";
                    setPasswordEditMode(false);
                }
                inlineStatus.textContent = "Modification annulée.";
            });
            cancelEditBtn.classList.add("is-cancel", "is-hidden");

            const deleteBtn = createIconButton("bi bi-trash", "Supprimer l'utilisateur", async () => {
                if (user.object_id === currentUserId) {
                    inlineStatus.textContent = "Vous ne pouvez pas supprimer votre propre compte.";
                    await showPopup("warning", "Action refusée", "Vous ne pouvez pas supprimer votre propre compte.");
                    return;
                }
                const confirmed = await confirmPopup(
                    "Supprimer l'utilisateur",
                    `Supprimer ${user.email || user.object_id} ? Cette action est irréversible.`,
                    "Supprimer"
                );
                if (!confirmed) {
                    return;
                }
                inlineStatus.textContent = "Suppression...";
                try {
                    await apiRequest(`/api/users/${encodeURIComponent(user.object_id)}`, {
                        method: "DELETE",
                    });
                    inlineStatus.textContent = "Utilisateur supprimé.";
                    await showPopup("success", "Utilisateur supprimé", `${user.email || user.object_id} a été supprimé.`);
                    await loadUsers();
                } catch (error) {
                    inlineStatus.textContent = `Erreur: ${error.message}`;
                    await showPopup("error", "Échec de suppression", error.message || "Une erreur est survenue.");
                }
            });

            actionsWrap.appendChild(editRoleBtn);
            actionsWrap.appendChild(cancelEditBtn);
            actionsWrap.appendChild(editPasswordBtn);
            actionsWrap.appendChild(deleteBtn);
            actionsCell.appendChild(actionsWrap);
            actionsCell.appendChild(inlineStatus);

            row.appendChild(emailCell);
            row.appendChild(roleCell);
            row.appendChild(passwordCell);
            row.appendChild(actionsCell);
            tableBody.appendChild(row);
        });
    }

    async function loadUsers() {
        setPageReady(false);
        setStatus("Chargement des utilisateurs...", false);
        const me = await apiRequest("/api/users/me", { method: "GET" });
        currentUserId = String(me.object_id || "");
        if (String(me.role || "").toLowerCase() !== "admin") {
            setStatus("Accès refusé: cette page est réservée aux administrateurs.", true);
            tableBody.innerHTML = "";
            await showPopup("error", "Accès refusé", "Cette page est réservée aux administrateurs.");
            setTimeout(redirectToApp, 800);
            return;
        }
        const payload = await apiRequest("/api/users", { method: "GET" });
        renderUsers(payload.users || []);
        const usersCount = Array.isArray(payload.users) ? payload.users.length : 0;
        setStatus(`${usersCount} utilisateur(s) chargé(s).`, false);
        setPageReady(true);
    }

    async function openCreateUserPopup() {
        if (!hasSwal()) {
            setStatus("SweetAlert2 est requis pour ajouter un utilisateur.", true);
            return;
        }

        const result = await window.Swal.fire({
            title: "Ajouter un utilisateur",
            html: `
                <div style="display:flex; flex-direction:column; gap:0.55rem; text-align:left;">
                    <label for="swal-user-email">Courriel</label>
                    <input id="swal-user-email" class="swal2-input" type="email" placeholder="user@exemple.com" style="margin:0;" />
                    <label for="swal-user-password">Mot de passe initial</label>
                    <input id="swal-user-password" class="swal2-input" type="password" placeholder="Au moins 8 caractères" style="margin:0;" />
                    <label for="swal-user-role">Rôle</label>
                    <select id="swal-user-role" class="swal2-select" style="margin:0;">
                        <option value="client">Client</option>
                        <option value="collaborator">Collaborateur</option>
                        <option value="admin">Admin</option>
                    </select>
                </div>
            `,
            showCancelButton: true,
            confirmButtonText: "Créer",
            cancelButtonText: "Annuler",
            confirmButtonColor: "#1d75c2",
            focusConfirm: false,
            preConfirm: () => {
                const email = String(document.getElementById("swal-user-email")?.value || "").trim();
                const password = String(document.getElementById("swal-user-password")?.value || "");
                const role = String(document.getElementById("swal-user-role")?.value || "client");

                if (!email || !password) {
                    window.Swal.showValidationMessage("Le courriel et le mot de passe sont requis.");
                    return null;
                }
                if (password.length < 8) {
                    window.Swal.showValidationMessage("Le mot de passe doit contenir au moins 8 caractères.");
                    return null;
                }
                return { email, password, role };
            },
        });

        if (!result.isConfirmed || !result.value) {
            return;
        }

        const { email, password, role } = result.value;
        setStatus("Création de l'utilisateur...", false);
        try {
            await apiRequest("/api/users", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password, role }),
            });
            setStatus("Utilisateur créé avec succès.", false);
            await showPopup("success", "Utilisateur créé", `${email} a été ajouté avec succès.`);
            await loadUsers();
        } catch (error) {
            setStatus(`Création échouée: ${error.message}`, true);
            await showPopup("error", "Création échouée", error.message || "Une erreur est survenue.");
        }
    }

    function init() {
        if (!tableBody || !refreshBtn || !addBtn) {
            return;
        }
        setPageReady(false);
        addBtn.addEventListener("click", () => {
            openCreateUserPopup().catch((error) => setStatus(`Erreur: ${error.message}`, true));
        });
        refreshBtn.addEventListener("click", () => {
            loadUsers().catch((error) => {
                setStatus(`Erreur: ${error.message}`, true);
                setPageReady(false);
            });
        });
        loadUsers().catch((error) => {
            setStatus(`Erreur: ${error.message}`, true);
            setPageReady(false);
        });
    }

    document.addEventListener("DOMContentLoaded", init);
})();
