(function () {
    const BACKEND_URL = window.BACKEND_URL || "";
    const DEBUG_BLOB_CONTAINER = window.DEBUG_BLOB_CONTAINER || "nutrifaq-knowledge-base-debug";
    const DEBUG_BLOB_ROOT_FOLDER = window.DEBUG_BLOB_ROOT_FOLDER || "nutrifaq-dbase-debug";
    const DOCUMENTS_PREFIX = `${DEBUG_BLOB_ROOT_FOLDER}/documents/`;
    const STORAGE_DOCUMENTS_PREFIX = `${DEBUG_BLOB_ROOT_FOLDER}/documents/`;

    function withContainerQuery(url) {
        const separator = url.includes("?") ? "&" : "?";
        const params = new URLSearchParams({
            container: DEBUG_BLOB_CONTAINER,
            root_folder: DEBUG_BLOB_ROOT_FOLDER,
        });
        return `${url}${separator}${params.toString()}`;
    }

    const els = {
        refreshFiles: document.getElementById("refresh-files"),
        uploadFile: document.getElementById("upload-file"),
        dropZone: document.getElementById("dnd-upload-area"),
        browseBtn: document.getElementById("dnd-browse-btn"),
        fileName: document.getElementById("dnd-file-name"),
        resetDebugFiles: document.getElementById("reset-debug-files"),
        startIndexing: document.getElementById("start-indexing"),
        cancelIndexing: document.getElementById("cancel-indexing"),
        resetProgressWrap: document.getElementById("reset-progress-wrap"),
        resetProgressBar: document.getElementById("reset-progress-bar"),
        resetProgressText: document.getElementById("reset-progress-text"),
        indexingProgressWrap: document.getElementById("indexing-progress-wrap"),
        indexingProgressBar: document.getElementById("indexing-progress-bar"),
        indexingProgressText: document.getElementById("indexing-progress-text"),
        filesTbody: document.getElementById("files-tbody"),
        statusMessage: document.getElementById("status-message")
    };

    const TOKEN_KEY = "nutrifaq_admin_bearer_token";
    let indexingProgressTimer = null;
    let indexingStatusTimer = null;
    let indexingAbortController = null;
    let resetProgressTimer = null;
    let isIndexingRunning = false;
    let hasLiveStepStatus = false;
    let currentStepKey = null;
    let currentStepPercent = 0;
    let isStepTransitioning = false;
    let stepSwitchTimer = null;

    const STEP_LABELS = {
        extract_docx: "Extraction des documents",
        extract_references: "Extraction des references",
        generate_transcripts_json: "Generation des transcripts",
        generate_questions: "Generation des questions",
        index_chromadb_json: "Indexation ChromaDB"
    };

    const STEP_PROGRESS = {
        extract_docx: 18,
        extract_references: 34,
        generate_transcripts_json: 52,
        generate_questions: 74,
        index_chromadb_json: 92
    };

    function hasSweetAlert() {
        return Boolean(window.Swal && typeof window.Swal.fire === "function");
    }

    async function confirmAction({ title, text, confirmText }) {
        if (hasSweetAlert()) {
            const result = await window.Swal.fire({
                title,
                text,
                icon: "warning",
                showCancelButton: true,
                confirmButtonText: confirmText || "Confirmer",
                cancelButtonText: "Annuler",
                reverseButtons: true,
            });
            return Boolean(result.isConfirmed);
        }
        return confirm(text || title);
    }

    function showAlertMessage(message, isError) {
        if (hasSweetAlert()) {
            window.Swal.fire({
                title: isError ? "Erreur" : "Information",
                text: message,
                icon: isError ? "error" : "info",
                confirmButtonText: "OK",
            });
            return;
        }
        alert(message);
    }

    function setIndexingProgress(value, text) {
        const clamped = Math.max(0, Math.min(100, Number(value) || 0));
        if (els.indexingProgressBar) {
            els.indexingProgressBar.style.width = `${clamped}%`;
        }
        if (els.indexingProgressText) {
            els.indexingProgressText.textContent = text || `${clamped}%`;
        }
    }

    function setResetProgress(value, text) {
        const clamped = Math.max(0, Math.min(100, Number(value) || 0));
        if (els.resetProgressBar) {
            els.resetProgressBar.style.width = `${clamped}%`;
        }
        if (els.resetProgressText) {
            els.resetProgressText.textContent = text || `${clamped}%`;
        }
    }

    function beginResetProgress() {
        if (els.resetProgressWrap) {
            els.resetProgressWrap.style.display = "block";
        }
        if (els.resetDebugFiles) {
            els.resetDebugFiles.disabled = true;
            els.resetDebugFiles.textContent = "Reset en cours...";
        }

        let progress = 8;
        setResetProgress(progress, "Préparation...");
        resetProgressTimer = window.setInterval(() => {
            progress = Math.min(progress + 6, 90);
            setResetProgress(progress, `Synchronisation... ${progress}%`);
        }, 350);
    }

    function finishResetProgress(success) {
        if (resetProgressTimer) {
            window.clearInterval(resetProgressTimer);
            resetProgressTimer = null;
        }

        setResetProgress(100, success ? "Terminé" : "Interrompu");

        if (els.resetDebugFiles) {
            els.resetDebugFiles.disabled = false;
            els.resetDebugFiles.textContent = "Réinitialiser les fichiers";
        }

        window.setTimeout(() => {
            if (els.resetProgressWrap) {
                els.resetProgressWrap.style.display = "none";
            }
            setResetProgress(0, "0%");
        }, success ? 1200 : 1800);
    }

    function beginIndexingProgress() {
        isIndexingRunning = true;
        hasLiveStepStatus = false;
        currentStepKey = null;
        currentStepPercent = 0;
        isStepTransitioning = false;
        if (stepSwitchTimer) {
            window.clearTimeout(stepSwitchTimer);
            stepSwitchTimer = null;
        }
        if (els.startIndexing) {
            els.startIndexing.disabled = true;
            els.startIndexing.textContent = "Indexage en cours...";
        }
        if (els.cancelIndexing) {
            els.cancelIndexing.style.display = "inline-flex";
            els.cancelIndexing.disabled = false;
        }
        if (els.indexingProgressWrap) {
            els.indexingProgressWrap.style.display = "block";
        }

        let progress = 5;
        setIndexingProgress(progress, "Préparation...");
        indexingProgressTimer = window.setInterval(() => {
            if (hasLiveStepStatus) {
                return;
            }
            progress = Math.min(progress + 1, 14);
            setIndexingProgress(progress, "Préparation...");
        }, 1000);

        startRegenerationStatusPolling();
    }

    function finishIndexingProgress(success) {
        isIndexingRunning = false;
        hasLiveStepStatus = false;
        currentStepKey = null;
        currentStepPercent = 0;
        isStepTransitioning = false;
        if (stepSwitchTimer) {
            window.clearTimeout(stepSwitchTimer);
            stepSwitchTimer = null;
        }
        if (indexingProgressTimer) {
            window.clearInterval(indexingProgressTimer);
            indexingProgressTimer = null;
        }
        stopRegenerationStatusPolling();

        setIndexingProgress(100, success ? "Terminé" : "Interrompu");

        if (els.startIndexing) {
            els.startIndexing.disabled = false;
            els.startIndexing.textContent = "Démarrer un indexage";
        }
        if (els.cancelIndexing) {
            els.cancelIndexing.disabled = true;
        }

        window.setTimeout(() => {
            if (els.indexingProgressWrap) {
                els.indexingProgressWrap.style.display = "none";
            }
            if (els.cancelIndexing) {
                els.cancelIndexing.style.display = "none";
            }
            setIndexingProgress(0, "0%");
        }, success ? 1200 : 2000);
    }

    function stopRegenerationStatusPolling() {
        if (indexingStatusTimer) {
            window.clearInterval(indexingStatusTimer);
            indexingStatusTimer = null;
        }
    }

    async function refreshRegenerationStatus() {
        if (!isIndexingRunning) {
            return;
        }
        try {
            const payload = await fetchJson(`${BACKEND_URL}/api/database/regenerate/status`, {
                headers: {
                    ...authHeaders()
                }
            });

            const regen = payload && payload.regeneration ? payload.regeneration : {};
            const stepKey = regen.current_step || null;
            if (!stepKey) {
                return;
            }

            hasLiveStepStatus = true;
            if (indexingProgressTimer) {
                window.clearInterval(indexingProgressTimer);
                indexingProgressTimer = null;
            }

            const label = regen.current_step_label || STEP_LABELS[stepKey] || stepKey;
            const stepIndex = Number(regen.step_index || 0);
            const totalSteps = Number(regen.total_steps || 0);

            if (isStepTransitioning) {
                return;
            }

            if (currentStepKey !== stepKey) {
                if (currentStepKey) {
                    const previousLabel = STEP_LABELS[currentStepKey] || currentStepKey;
                    const previousStepIndex = Math.max(1, stepIndex - 1);
                    const previousCountText = previousStepIndex > 0 && totalSteps > 0
                        ? ` (${previousStepIndex}/${totalSteps})`
                        : "";
                    setIndexingProgress(
                        100,
                        `Etape${previousCountText}: ${previousLabel} (100%)`
                    );
                    isStepTransitioning = true;
                    if (stepSwitchTimer) {
                        window.clearTimeout(stepSwitchTimer);
                    }
                    stepSwitchTimer = window.setTimeout(() => {
                        currentStepKey = stepKey;
                        currentStepPercent = 0;
                        const countText = stepIndex > 0 && totalSteps > 0
                            ? ` (${stepIndex}/${totalSteps})`
                            : "";
                        setIndexingProgress(0, `Etape${countText}: ${label} (0%)`);
                        isStepTransitioning = false;
                        stepSwitchTimer = null;
                    }, 260);
                    return;
                }

                currentStepKey = stepKey;
                currentStepPercent = 0;
            } else {
                // Smooth normalized progression within the current step.
                currentStepPercent = Math.min(currentStepPercent + 12, 96);
            }

            const countText = stepIndex > 0 && totalSteps > 0
                ? ` (${stepIndex}/${totalSteps})`
                : "";
            setIndexingProgress(
                currentStepPercent,
                `Etape${countText}: ${label} (${Math.round(currentStepPercent)}%)`
            );
        } catch (_) {
            // Ignore transient status polling errors while regeneration is running.
        }
    }

    function startRegenerationStatusPolling() {
        stopRegenerationStatusPolling();
        refreshRegenerationStatus();
        indexingStatusTimer = window.setInterval(refreshRegenerationStatus, 1500);
    }

    async function requestCancelIndexing() {
        if (!isIndexingRunning) {
            return;
        }

        try {
            if (els.cancelIndexing) {
                els.cancelIndexing.disabled = true;
            }
            setStatus("Annulation de l'indexage demandée...", false);

            if (indexingAbortController) {
                indexingAbortController.abort();
            }

            await fetchJson(`${BACKEND_URL}/api/database/regenerate/cancel`, {
                method: "POST",
                headers: {
                    ...authHeaders()
                }
            });
        } catch (error) {
            setStatus(`Erreur annulation: ${error.message}`, true);
        }
    }

    function hideIntegratedPanels() {
        const downloadPanel = document.getElementById("download-manager-panel");
        const authPanel = document.getElementById("azure-auth-panel");
        if (downloadPanel) {
            downloadPanel.style.display = "none";
        }
        if (authPanel) {
            authPanel.style.display = "none";
        }
    }

    function activateDownloadView() {
        const panel = document.getElementById("download-manager-panel");
        const chatContainer = document.getElementById("chat-container");
        const chatInputArea = document.querySelector("footer .input-area");
        const emptyState = document.getElementById("empty-state");
        const chatTopSpacer = document.getElementById("chat-top-spacer");

        hideIntegratedPanels();

        if (panel) {
            panel.style.display = "flex";
        }
        if (chatContainer) {
            chatContainer.classList.add("download-mode");
            chatContainer.scrollTo({ top: 0, behavior: "smooth" });
        }
        if (chatInputArea) {
            chatInputArea.style.display = "none";
        }
        if (emptyState) {
            emptyState.style.display = "none";
        }
        if (chatTopSpacer) {
            chatTopSpacer.style.display = "none";
        }
    }

    function activateTesterView() {
        const chatContainer = document.getElementById("chat-container");
        const chatInputArea = document.querySelector("footer .input-area");
        const emptyState = document.getElementById("empty-state");

        hideIntegratedPanels();
        if (chatContainer) {
            chatContainer.classList.remove("download-mode");
            chatContainer.scrollTo({ top: 0, behavior: "smooth" });
        }
        if (chatInputArea) {
            chatInputArea.style.display = "";
        }
        if (emptyState && !document.querySelector("#chat-container .message")) {
            emptyState.style.display = "";
        }
    }

    function activateAuthView() {
        const authPanel = document.getElementById("azure-auth-panel");
        const chatContainer = document.getElementById("chat-container");
        const chatInputArea = document.querySelector("footer .input-area");
        const emptyState = document.getElementById("empty-state");
        const chatTopSpacer = document.getElementById("chat-top-spacer");

        hideIntegratedPanels();

        if (authPanel) {
            authPanel.style.display = "block";
        }
        if (chatContainer) {
            chatContainer.classList.add("download-mode");
            chatContainer.scrollTo({ top: 0, behavior: "smooth" });
        }
        if (chatInputArea) {
            chatInputArea.style.display = "none";
        }
        if (emptyState) {
            emptyState.style.display = "none";
        }
        if (chatTopSpacer) {
            chatTopSpacer.style.display = "none";
        }
    }

    function bindNavigationToggles() {
        const downloadLink = document.getElementById("download-link");
        const testerLink = document.getElementById("tester-link");
        const authLink = document.getElementById("auth-link");

        if (downloadLink) {
            downloadLink.addEventListener("click", (event) => {
                event.preventDefault();
                activateDownloadView();
            });
        }

        if (testerLink) {
            testerLink.addEventListener("click", (event) => {
                event.preventDefault();
                activateTesterView();
            });
        }

        if (authLink) {
            authLink.addEventListener("click", (event) => {
                event.preventDefault();
                activateAuthView();
            });
        }
    }

    function bindTokenSync() {
        window.addEventListener("nutrifaq:admin-token-updated", (event) => {
            const token = (event.detail && event.detail.token) || "";
            if (token) {
                localStorage.setItem(TOKEN_KEY, token);
            }
        });
    }

    function setStatus(message, isError) {
        if (!els.statusMessage) {
            return;
        }
        els.statusMessage.textContent = message;
        els.statusMessage.classList.toggle("error", Boolean(isError));
    }

    function getToken() {
        return localStorage.getItem(TOKEN_KEY) || "";
    }

    function authHeaders() {
        const token = getToken();
        if (!token) {
            throw new Error("Token admin requis.");
        }
        return {
            Authorization: `Bearer ${token}`
        };
    }

    async function fetchJson(url, options) {
        const response = await fetch(url, options);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = payload.detail || payload.message || JSON.stringify(payload) || response.statusText;
            throw new Error(detail);
        }
        return payload;
    }

    function formatBytes(size) {
        const value = Number(size || 0);
        if (!Number.isFinite(value) || value < 1024) {
            return `${value} o`;
        }
        const units = ["Ko", "Mo", "Go", "To"];
        let unitIndex = -1;
        let current = value;
        while (current >= 1024 && unitIndex < units.length - 1) {
            current /= 1024;
            unitIndex += 1;
        }
        return `${current.toFixed(1)} ${units[unitIndex]}`;
    }

    function formatDate(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleString("fr-CA");
    }

    function renderRows(files) {
        if (!els.filesTbody) {
            return;
        }

        if (!files.length) {
            els.filesTbody.innerHTML = "<tr><td colspan=\"4\">Aucun fichier trouvé pour ce filtre.</td></tr>";
            return;
        }

        const rows = files.map((file) => {
            const blobName = file.blob_name || file.name || "";
            const fileName = file.filename || (blobName ? blobName.split("/").pop() : "") || "-";
            const lastModified = formatDate(file.last_modified);
            const size = formatBytes(file.size_bytes ?? file.size);
            return `
                <tr>
                    <td>${escapeHtml(fileName)}</td>
                    <td>${escapeHtml(size)}</td>
                    <td>${escapeHtml(lastModified)}</td>
                    <td>
                        <button class="dm-btn table-action" data-action="download" data-name="${encodeURIComponent(blobName)}">Télécharger</button>
                        <button class="dm-btn table-action danger" data-action="delete" data-name="${encodeURIComponent(blobName)}">Supprimer</button>
                    </td>
                </tr>
            `;
        });

        els.filesTbody.innerHTML = rows.join("");
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    async function loadFiles() {
        try {
            setStatus("Chargement des fichiers Azure...", false);
            if (els.filesTbody) {
                els.filesTbody.innerHTML = "<tr><td colspan=\"4\">Chargement...</td></tr>";
            }
            const prefix = DOCUMENTS_PREFIX;
            const query = prefix ? `?prefix=${encodeURIComponent(prefix)}` : "";
            const data = await fetchJson(withContainerQuery(`${BACKEND_URL}/api/blob/files${query}`), {
                headers: {
                    ...authHeaders()
                }
            });
            renderRows(Array.isArray(data.files) ? data.files : []);
            setStatus(`${data.count || 0} fichier(s) trouvé(s) dans ${data.container || "le conteneur"}.`, false);
        } catch (error) {
            if (els.filesTbody) {
                els.filesTbody.innerHTML = `<tr><td colspan="4">Erreur: ${escapeHtml(error.message)}</td></tr>`;
            }
            setStatus(`Erreur de chargement: ${error.message}`, true);
        }
    }

    async function deleteFile(blobName) {
        if (!blobName) {
            return;
        }
        const confirmed = await confirmAction({
            title: "Supprimer ce fichier ?",
            text: blobName,
            confirmText: "Supprimer",
        });
        if (!confirmed) {
            return;
        }

        try {
            setStatus(`Suppression de ${blobName}...`, false);
            await fetchJson(withContainerQuery(`${BACKEND_URL}/api/blob/files/${encodeURI(blobName)}`), {
                method: "DELETE",
                headers: {
                    ...authHeaders()
                }
            });
            setStatus(`Fichier supprimé: ${blobName}`, false);
            await loadFiles();
        } catch (error) {
            setStatus(`Erreur suppression: ${error.message}`, true);
        }
    }

    async function downloadFile(blobName) {
        if (!blobName) {
            return;
        }

        try {
            const headers = authHeaders();
            const url = withContainerQuery(`${BACKEND_URL}/api/blob/files/${encodeURI(blobName)}/download`);
            const response = await fetch(url, { headers });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.detail || response.statusText);
            }

            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = objectUrl;
            anchor.download = blobName.split("/").pop() || "download";
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(objectUrl);

            setStatus(`Téléchargement lancé: ${blobName}`, false);
            await loadFiles();
        } catch (error) {
            setStatus(`Erreur téléchargement: ${error.message}`, true);
        }
    }

    async function uploadFile(inputFile) {
        if (!inputFile) {
            setStatus("Sélectionnez un fichier local.", true);
            return;
        }

        const safeFileName = (inputFile.name || "").split(/[\\/]/).pop() || "upload.bin";
        const blobName = `${STORAGE_DOCUMENTS_PREFIX}${safeFileName}`;

        try {
            setStatus("Téléversement en cours...", false);
            const form = new FormData();
            form.append("file", inputFile);
            const response = await fetch(withContainerQuery(`${BACKEND_URL}/api/blob/files/${encodeURI(blobName)}`), {
                method: "POST",
                headers: {
                    ...authHeaders()
                },
                body: form
            });

            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || payload.message || response.statusText);
            }

            setStatus(`Fichier téléversé: ${payload.blob_name || blobName}`, false);
            await loadFiles();
        } catch (error) {
            setStatus(`Erreur upload: ${error.message}`, true);
        }
    }

    function bindDragAndDrop() {
        const zone = els.dropZone;
        const fileInput = els.uploadFile;
        const browseBtn = els.browseBtn;

        if (!zone || !fileInput) {
            return;
        }

        const setDragState = (active) => {
            zone.classList.toggle("is-dragover", Boolean(active));
        };

        const preventDefaults = (event) => {
            event.preventDefault();
            event.stopPropagation();
        };

        const handleSelectedFile = async (file) => {
            if (!file) {
                return;
            }
            if (els.fileName) {
                els.fileName.textContent = `Fichier sélectionné: ${file.name}`;
            }
            await uploadFile(file);
            fileInput.value = "";
        };

        ["dragenter", "dragover"].forEach((eventName) => {
            zone.addEventListener(eventName, (event) => {
                preventDefaults(event);
                setDragState(true);
            });
        });

        ["dragleave", "dragend", "drop"].forEach((eventName) => {
            zone.addEventListener(eventName, (event) => {
                preventDefaults(event);
                setDragState(false);
            });
        });

        zone.addEventListener("drop", async (event) => {
            const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
            await handleSelectedFile(file);
        });

        const openPicker = () => fileInput.click();

        zone.addEventListener("click", openPicker);
        zone.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openPicker();
            }
        });

        if (browseBtn) {
            browseBtn.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                openPicker();
            });
        }

        fileInput.addEventListener("change", async (event) => {
            const file = event.target && event.target.files && event.target.files[0];
            await handleSelectedFile(file);
        });
    }

    async function startIndexing() {
        const confirmed = await confirmAction({
            title: "Démarrer l'indexage ?",
            text: "La régénération et l'indexation peuvent prendre plusieurs minutes.",
            confirmText: "Démarrer",
        });
        if (!confirmed) {
            return;
        }

        try {
            beginIndexingProgress();
            indexingAbortController = new AbortController();
            setStatus("Indexage en cours... cela peut prendre plusieurs minutes.", false);
            const result = await fetchJson(`${BACKEND_URL}/api/database/regenerate`, {
                method: "POST",
                headers: {
                    ...authHeaders()
                },
                signal: indexingAbortController.signal
            });

            const finalStatus = result.status || "ok";
            if (finalStatus === "cancelled") {
                setStatus("Indexage annulé.", true);
                finishIndexingProgress(false);
                showAlertMessage("Indexage annulé.", false);
            } else {
                setStatus(`Indexage terminé. Statut: ${finalStatus}`, false);
                finishIndexingProgress(true);
                showAlertMessage("Indexage terminé.", false);
            }
        } catch (error) {
            if (error && error.name === "AbortError") {
                setStatus("Indexage annulé.", true);
            } else {
                setStatus(`Erreur indexage: ${error.message}`, true);
                showAlertMessage(`Erreur indexage: ${error.message}`, true);
            }
            finishIndexingProgress(false);
        } finally {
            indexingAbortController = null;
        }
    }

    async function resetDebugFilesFromBlob() {
        const confirmed = await confirmAction({
            title: "Réinitialiser les fichiers ?",
            text: "Cette action va rétablir les fichiers précédents.",
            confirmText: "Réinitialiser",
        });
        if (!confirmed) {
            return;
        }

        try {
            beginResetProgress();
            setStatus("Réinitialisation depuis le blob en cours...", false);

            const result = await fetchJson(withContainerQuery(`${BACKEND_URL}/api/blob/debug/reset-local`), {
                method: "POST",
                headers: {
                    ...authHeaders()
                }
            });

            const docsCount = Number(result.documents_count || 0);
            setStatus(`Reset terminé. ${docsCount} fichier(s) dans documents/.`, false);
            finishResetProgress(true);
            await loadFiles();
        } catch (error) {
            setStatus(`Erreur reset: ${error.message}`, true);
            finishResetProgress(false);
        }
    }

    function bindTableActions() {
        if (!els.filesTbody) {
            return;
        }

        els.filesTbody.addEventListener("click", (event) => {
            const button = event.target.closest("button[data-action]");
            if (!button) {
                return;
            }
            const action = button.getAttribute("data-action");
            const blobName = decodeURIComponent(button.getAttribute("data-name") || "");
            if (action === "download") {
                downloadFile(blobName);
            } else if (action === "delete") {
                deleteFile(blobName);
            }
        });
    }

    function init() {
        const panel = document.getElementById("download-manager-panel");
        bindNavigationToggles();
        bindTokenSync();

        if (!panel) {
            return;
        }

        if (els.refreshFiles) {
            els.refreshFiles.addEventListener("click", loadFiles);
        }
        if (els.startIndexing) {
            els.startIndexing.addEventListener("click", startIndexing);
        }
        if (els.resetDebugFiles) {
            els.resetDebugFiles.addEventListener("click", resetDebugFilesFromBlob);
        }
        if (els.cancelIndexing) {
            els.cancelIndexing.addEventListener("click", requestCancelIndexing);
        }

        bindDragAndDrop();
        bindTableActions();
        loadFiles();
    }

    document.addEventListener("DOMContentLoaded", init);
})();
