(function () {
    const TOKEN_KEY = "nutrifaq_admin_bearer_token";
    const BACKEND_URL = (window.BACKEND_URL || "").replace(/\/$/, "");

    const statusEl = document.getElementById("users-admin-status");
    const refreshBtn = document.getElementById("users-admin-refresh-btn");
    const addBtn = document.getElementById("users-admin-add-btn");
    const tableBody = document.getElementById("users-admin-table-body");
    const gateEl = document.getElementById("users-admin-gate");
    const shellEl = document.getElementById("users-admin-shell");
    const gateMessageEl = gateEl ? gateEl.querySelector("p") : null;

    let currentUserId = "";
    const EDITABLE_ROLES = ["collaborator", "admin"];

    function normalizeManagedRole(role) {
        const normalized = String(role || "").trim().toLowerCase();
        if (normalized === "client") {
            return "collaborator";
        }
        if (EDITABLE_ROLES.includes(normalized)) {
            return normalized;
        }
        return "collaborator";
    }

    function applyResetStateBadge(element, isRequired) {
        element.className = "users-admin-reset-badge";
        element.classList.add(isRequired ? "is-required" : "is-clear");
        element.textContent = isRequired ? "Requis au prochain login" : "Non requis";
    }

    function redirectToApp() {
        window.location.replace("/index.html");
    }

    function getTokenFromQuery() {
        const url = new URL(window.location.href);
        const token = String(url.searchParams.get("token") || "").trim();
        if (!token) {
            return "";
        }
        url.searchParams.delete("token");
        window.history.replaceState({}, "", url.toString());
        return token;
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

    function setGateMessage(message) {
        if (!gateMessageEl) {
            return;
        }
        gateMessageEl.textContent = message;
    }

    function hasSwal() {
        return Boolean(window.Swal && typeof window.Swal.fire === "function");
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
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
        let token = getTokenFromQuery();
        if (token) {
            localStorage.setItem(TOKEN_KEY, token);
        } else {
            token = localStorage.getItem(TOKEN_KEY) || "";
        }
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
            const error = new Error(payload.detail || payload.message || response.statusText || "Request failed.");
            error.status = response.status;
            throw error;
        }
        return payload;
    }

    function handleAccessError(error) {
        const status = Number(error && error.status ? error.status : 0);
        if (status === 401) {
            setGateMessage("Session expirée. Redirection vers la connexion...");
            window.location.replace("/login.html");
            return true;
        }
        if (status === 403) {
            setGateMessage("Accès réservé aux administrateurs. Redirection...");
            window.location.replace("/index.html");
            return true;
        }
        return false;
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
            EDITABLE_ROLES.forEach((role) => {
                const option = document.createElement("option");
                option.value = role;
                option.textContent = role;
                roleSelect.appendChild(option);
            });
            roleSelect.value = normalizeManagedRole(user.role);
            roleSelect.disabled = true;
            roleSelect.classList.add("users-admin-field-readonly");
            roleCell.appendChild(roleSelect);

            const passwordCell = document.createElement("td");
            const resetStateLabel = document.createElement("span");
            const isResetRequired = Boolean(user.must_change_password);
            applyResetStateBadge(resetStateLabel, isResetRequired);
            passwordCell.appendChild(resetStateLabel);

            const actionsCell = document.createElement("td");
            actionsCell.className = "users-admin-actions-cell";
            const actionsWrap = document.createElement("div");
            actionsWrap.className = "users-admin-row-actions";
            const inlineStatus = document.createElement("div");
            inlineStatus.className = "users-admin-status-inline";

            let roleEditing = false;
            let savedRoleValue = normalizeManagedRole(user.role);

            const refreshCancelVisibility = () => {
                if (roleEditing) {
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

            const editRoleBtn = createIconButton("bi bi-person-gear", "Modifier le rôle", async () => {
                if (!roleEditing) {
                    setRoleEditMode(true);
                    inlineStatus.textContent = "Mode édition du rôle activé.";
                    roleSelect.focus();
                    return;
                }

                inlineStatus.textContent = "Mise à jour du rôle...";
                try {
                    const nextRole = normalizeManagedRole(roleSelect.value);
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
            editRoleBtn.classList.add("users-admin-btn-role");

            const forceResetBtn = createIconButton("bi bi-key-fill", "Forcer la réinitialisation du mot de passe", async () => {
                inlineStatus.textContent = "Activation de la réinitialisation du mot de passe...";
                try {
                    const payload = await apiRequest(`/api/users/${encodeURIComponent(user.object_id)}/password/reset-required`, {
                        method: "PUT",
                    });
                    user.must_change_password = true;
                    applyResetStateBadge(resetStateLabel, true);
                    inlineStatus.textContent = "Réinitialisation requise au prochain login.";
                    const temporaryPassword = String(payload.temporary_password || "");
                    const targetUser = escapeHtml(user.email || user.object_id);
                    await window.Swal.fire({
                        icon: "success",
                        title: "Réinitialisation activée",
                        html: `Mot de passe temporaire: <br><br><strong>${escapeHtml(temporaryPassword)}</strong><br><br>Transmettez-le à ${targetUser}. L'utilisateur devra le changer à sa prochaine connexion.`,
                        confirmButtonColor: "#1d75c2",
                    });
                } catch (error) {
                    inlineStatus.textContent = `Erreur: ${error.message}`;
                    await showPopup("error", "Échec de l'opération", error.message || "Une erreur est survenue.");
                }
            });
            forceResetBtn.classList.add("users-admin-btn-reset");

            const cancelEditBtn = createIconButton("bi bi-x-lg", "Annuler", async () => {
                if (roleEditing) {
                    roleSelect.value = savedRoleValue;
                    setRoleEditMode(false);
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
                    deleteBtn.classList.add("users-admin-btn-delete");
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
            actionsWrap.appendChild(forceResetBtn);
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
                    <label for="swal-user-role">Rôle</label>
                    <select id="swal-user-role" class="swal2-select" style="margin:0;">
                        <option value="collaborator">Collaborateur</option>
                        <option value="admin" selected>Admin</option>
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
                const role = normalizeManagedRole(document.getElementById("swal-user-role")?.value || "admin");

                if (!email) {
                    window.Swal.showValidationMessage("Le courriel est requis.");
                    return null;
                }
                return { email, role };
            },
        });

        if (!result.isConfirmed || !result.value) {
            return;
        }

        const { email, role } = result.value;
        setStatus("Création de l'utilisateur...", false);
        try {
            const payload = await apiRequest("/api/users", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, role }),
            });
            setStatus("Utilisateur créé avec succès.", false);
            const temporaryPassword = String(payload.temporary_password || "");
            await window.Swal.fire({
                icon: "success",
                title: "Utilisateur créé",
                html: `${escapeHtml(email)} a été ajouté avec succès.<br><br>Mot de passe temporaire: <strong>${escapeHtml(temporaryPassword)}</strong><br>Transmettez-le à l'utilisateur.`,
                confirmButtonColor: "#1d75c2",
            });
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
                if (handleAccessError(error)) {
                    return;
                }
                setStatus(`Erreur: ${error.message}`, true);
                setGateMessage(`Erreur: ${error.message}`);
                setPageReady(false);
            });
        });
        loadUsers().catch((error) => {
            if (handleAccessError(error)) {
                return;
            }
            setStatus(`Erreur: ${error.message}`, true);
            setGateMessage(`Erreur: ${error.message}`);
            setPageReady(false);
        });
    }

    document.addEventListener("DOMContentLoaded", init);
})();
