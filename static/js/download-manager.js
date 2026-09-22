(function () {
    const BACKEND_URL = window.BACKEND_URL || "";
    const DEBUG_BLOB_CONTAINER = window.DEBUG_BLOB_CONTAINER || "nutrifaq-knowledge-base-debug";
    const DEBUG_BLOB_ROOT_FOLDER = window.DEBUG_BLOB_ROOT_FOLDER || "nutrifaq-dbase-debug";
    const DOCUMENTS_PREFIX = `${DEBUG_BLOB_ROOT_FOLDER}/documents/`;
    const STORAGE_DOCUMENTS_PREFIX = `${DEBUG_BLOB_ROOT_FOLDER}/documents/`;
    const MODEL_STORAGE_KEY = "nutrifaq_selected_model";

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

    function currentLanguage() {
        try {
            if (window.ConfigModule && typeof window.ConfigModule.getCurrentLanguage === "function") {
                return window.ConfigModule.getCurrentLanguage() || "fr";
            }
        } catch (_) {
            // Ignore and use default.
        }
        return "fr";
    }

    function withContainerQuery(url) {
        const separator = url.includes("?") ? "&" : "?";
        const params = new URLSearchParams({
            container: DEBUG_BLOB_CONTAINER,
            root_folder: DEBUG_BLOB_ROOT_FOLDER,
        });
        return `${url}${separator}${params.toString()}`;
    }

    const els = {
        downloadSection: document.getElementById("download-section"),
        publishSection: document.getElementById("publish-section"),
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
        statusMessage: document.getElementById("status-message"),
        publishModelSelector: document.getElementById("publish-model-selector"),
        publishDatetime: document.getElementById("publish-datetime"),
        publishSubmit: document.getElementById("publish-submit"),
        publishStatus: document.getElementById("publish-status"),
        publishLogsList: document.getElementById("publish-logs-list"),
        publishRefreshLogs: document.getElementById("publish-refresh-logs"),
        publishExportLogs: document.getElementById("publish-export-logs")
    };

    function hydratePublishElements() {
        els.publishSection = document.getElementById("publish-section");
        els.publishModelSelector = document.getElementById("publish-model-selector");
        els.publishDatetime = document.getElementById("publish-datetime");
        els.publishSubmit = document.getElementById("publish-submit");
        els.publishStatus = document.getElementById("publish-status");
        els.publishLogsList = document.getElementById("publish-logs-list");
        els.publishRefreshLogs = document.getElementById("publish-refresh-logs");
        els.publishExportLogs = document.getElementById("publish-export-logs");
    }

    function ensurePublishRefreshControl() {
        if (!els.publishSection) {
            return;
        }

        const logsCard = els.publishSection.querySelector(".publish-logs-card");
        if (!logsCard) {
            return;
        }

        let logsHeader = logsCard.querySelector(".publish-logs-header");
        const heading = logsCard.querySelector("h3");

        if (!logsHeader) {
            logsHeader = document.createElement("div");
            logsHeader.className = "publish-logs-header";
            if (heading) {
                logsCard.insertBefore(logsHeader, heading);
                logsHeader.appendChild(heading);
            } else {
                const fallbackHeading = document.createElement("h3");
                fallbackHeading.textContent = tr("publish.ui.logsTitle", "Logs de questions");
                logsHeader.appendChild(fallbackHeading);
                logsCard.insertBefore(logsHeader, logsCard.firstChild);
            }
        }

        let headerActions = logsHeader.querySelector(".publish-logs-actions");
        if (!headerActions) {
            headerActions = document.createElement("div");
            headerActions.className = "publish-logs-actions";
            logsHeader.appendChild(headerActions);
        }

        if (!headerActions.querySelector("#publish-refresh-logs")) {
            const refreshBtn = document.createElement("button");
            refreshBtn.id = "publish-refresh-logs";
            refreshBtn.type = "button";
            refreshBtn.className = "dm-btn secondary publish-refresh-logs-btn";
            refreshBtn.textContent = tr("publish.logs.refresh", "Refresh");
            headerActions.appendChild(refreshBtn);
        }

        if (!headerActions.querySelector("#publish-export-logs")) {
            const exportBtn = document.createElement("button");
            exportBtn.id = "publish-export-logs";
            exportBtn.type = "button";
            exportBtn.className = "dm-btn secondary publish-export-logs-btn";
            exportBtn.textContent = tr("publish.logs.export", "Export");
            headerActions.appendChild(exportBtn);
        }

        hydratePublishElements();
        applyPublishTranslations();
    }

    function applyPublishTranslations() {
        if (!els.publishSection) {
            return;
        }

        const sectionTitle = els.publishSection.querySelector(".publish-controls-card h2");
        if (sectionTitle) {
            sectionTitle.textContent = tr("publish.ui.sectionTitle", "Publier");
        }

        const modelLabel = els.publishSection.querySelector('label[for="publish-model-selector"]');
        if (modelLabel) {
            modelLabel.textContent = tr("publish.ui.modelLabel", "Modele");
        }

        const datetimeLabel = els.publishSection.querySelector('label[for="publish-datetime"]');
        if (datetimeLabel) {
            datetimeLabel.textContent = tr("publish.ui.datetimeLabel", "Date et heure de publication");
        }

        if (els.publishSubmit) {
            els.publishSubmit.textContent = tr("publish.confirm.action", "Publier");
        }

        const logsTitle = els.publishSection.querySelector(".publish-logs-header h3");
        if (logsTitle) {
            logsTitle.textContent = tr("publish.ui.logsTitle", "Logs de questions");
        }

        if (els.publishRefreshLogs) {
            els.publishRefreshLogs.textContent = tr("publish.logs.refresh", "Refresh");
        }

        if (els.publishExportLogs) {
            els.publishExportLogs.textContent = tr("publish.logs.export", "Export");
        }

        const emptyState = els.publishSection.querySelector(".publish-log-empty");
        if (emptyState && !els.publishSection.querySelector(".publish-log-item")) {
            emptyState.textContent = tr("publish.logs.loading", "Chargement des logs...");
        }
    }

    function bindPublishRefreshButton() {
        if (!els.publishRefreshLogs || els.publishRefreshLogs.dataset.bound === "1") {
            return;
        }
        els.publishRefreshLogs.dataset.bound = "1";
        els.publishRefreshLogs.addEventListener("click", async () => {
            await loadPublishLogs();
        });
    }

    function buildPublishLogsExportElement() {
        const title = tr("publish.logs.exportTitle", "Export des logs");
        const now = new Date().toLocaleString(currentLanguage() === "en" ? "en-CA" : "fr-CA");

        const exportRoot = document.createElement("div");
        exportRoot.className = "publish-export-root";
        exportRoot.style.fontFamily = '"Segoe UI", Arial, sans-serif';
        exportRoot.style.color = "#1f2937";
        exportRoot.style.padding = "10mm";
        exportRoot.style.background = "#ffffff";
        exportRoot.style.width = "190mm";

        const heading = document.createElement("h1");
        heading.textContent = title;
        heading.style.margin = "0 0 6px";
        heading.style.fontSize = "24px";

        const meta = document.createElement("p");
        meta.textContent = now;
        meta.style.margin = "0 0 16px";
        meta.style.color = "#4b5563";
        meta.style.fontSize = "13px";

        const logsClone = els.publishLogsList.cloneNode(true);
        logsClone.style.maxHeight = "none";
        logsClone.style.height = "auto";
        logsClone.style.overflow = "visible";
        logsClone.style.display = "block";
        logsClone.style.gap = "0";

        logsClone.querySelectorAll("*").forEach((node) => {
            if (node && node.style) {
                node.style.maxHeight = "none";
            }
        });

        logsClone.querySelectorAll(".publish-log-item").forEach((item) => {
            item.style.border = "1px solid #d1e2dd";
            item.style.borderRadius = "10px";
            item.style.padding = "10px";
            item.style.marginBottom = "10px";
            item.style.breakInside = "avoid";
            item.style.pageBreakInside = "avoid";
        });
        logsClone.querySelectorAll(".publish-log-block").forEach((item) => {
            item.style.border = "1px solid #e5ece9";
            item.style.borderRadius = "8px";
            item.style.padding = "8px";
            item.style.marginTop = "6px";
        });

        exportRoot.appendChild(heading);
        exportRoot.appendChild(meta);
        exportRoot.appendChild(logsClone);
        return exportRoot;
    }

    function slugifyFilePart(value) {
        return String(value || "")
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "")
            || "logs";
    }

    function buildExportFilename() {
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, "0");
        const dd = String(now.getDate()).padStart(2, "0");
        const hh = String(now.getHours()).padStart(2, "0");
        const min = String(now.getMinutes()).padStart(2, "0");
        const titlePart = slugifyFilePart(tr("publish.logs.exportTitle", "Export des logs"));
        return `${titlePart}-${yyyy}${mm}${dd}-${hh}${min}.pdf`;
    }

    function loadHtml2PdfLibrary() {
        if (window.html2pdf) {
            return Promise.resolve();
        }

        const existing = document.querySelector('script[data-lib="html2pdf"]');
        if (existing) {
            return new Promise((resolve, reject) => {
                existing.addEventListener("load", () => resolve(), { once: true });
                existing.addEventListener("error", () => reject(new Error("html2pdf load failed")), { once: true });
            });
        }

        return new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
            script.async = true;
            script.dataset.lib = "html2pdf";
            script.addEventListener("load", () => resolve(), { once: true });
            script.addEventListener("error", () => reject(new Error("html2pdf load failed")), { once: true });
            document.head.appendChild(script);
        });
    }

    function addPdfFooter(pdf) {
        if (!pdf || !pdf.internal || !pdf.internal.getNumberOfPages) {
            return;
        }

        const totalPages = pdf.internal.getNumberOfPages();
        const footerText = "IMX Technologie Copyright © 2026";

        for (let page = 1; page <= totalPages; page += 1) {
            pdf.setPage(page);

            const pageWidth = pdf.internal.pageSize.getWidth();
            const pageHeight = pdf.internal.pageSize.getHeight();
            const centerX = pageWidth / 2;
            const rightX = pageWidth - 8;
            const footerY = pageHeight - 5;

            pdf.setFontSize(9);
            pdf.setTextColor(110, 118, 123);
            pdf.text(footerText, centerX, footerY, { align: "center" });
            pdf.text(`(${page}/${totalPages})`, rightX, footerY, { align: "right" });
        }
    }

    async function downloadPublishLogsPdf() {
        await loadHtml2PdfLibrary();

        if (!window.html2pdf || typeof window.html2pdf !== "function") {
            throw new Error(tr("publish.logs.pdfLibUnavailable", "Librairie PDF indisponible."));
        }

        const wrapper = document.createElement("div");
        wrapper.style.position = "fixed";
        wrapper.style.left = "0";
        wrapper.style.top = "0";
        wrapper.style.width = "210mm";
        wrapper.style.opacity = "0";
        wrapper.style.pointerEvents = "none";
        wrapper.style.zIndex = "-1";
        const exportNode = buildPublishLogsExportElement();
        wrapper.appendChild(exportNode);
        document.body.appendChild(wrapper);

        try {
            const filename = buildExportFilename();
            const sourceNode = exportNode;
            const options = {
                margin: [8, 8, 14, 8],
                filename,
                image: { type: "jpeg", quality: 0.98 },
                html2canvas: { scale: 2, useCORS: true },
                jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
                pagebreak: { mode: ["css", "legacy"] }
            };

            const worker = window.html2pdf().set(options).from(sourceNode).toPdf();
            await worker.get("pdf").then((pdf) => {
                addPdfFooter(pdf);
            });
            await worker.save();
        } finally {
            wrapper.remove();
        }
    }

    async function exportPublishLogsToPdf() {
        if (!els.publishLogsList) {
            return;
        }

        const hasLogs = els.publishLogsList.querySelector(".publish-log-item");
        if (!hasLogs) {
            setPublishStatus(tr("publish.logs.nothingToExport", "Aucun log a exporter."), true);
            return;
        }

        try {
            setPublishStatus(tr("publish.logs.exportInProgress", "Generation du PDF en cours..."), false);
            await downloadPublishLogsPdf();
            setPublishStatus(tr("publish.logs.exportDone", "PDF telecharge."), false);
        } catch (error) {
            const message = error && error.message ? error.message : tr("publish.logs.exportFailed", "Echec de l'export PDF.");
            setPublishStatus(tr("publish.logs.exportFailedWithError", "Echec de l'export PDF: {error}", { error: message }), true);
        }
    }

    function bindPublishExportButton() {
        if (!els.publishExportLogs || els.publishExportLogs.dataset.bound === "1") {
            return;
        }
        els.publishExportLogs.dataset.bound = "1";
        els.publishExportLogs.addEventListener("click", async () => {
            await exportPublishLogsToPdf();
        });
    }

    function ensurePublishSectionMounted() {
        if (document.getElementById("publish-section")) {
            hydratePublishElements();
            applyPublishTranslations();
            return;
        }

        const panel = document.getElementById("download-manager-panel");
        if (!panel) {
            return;
        }

        const publishSection = document.createElement("section");
        publishSection.id = "publish-section";
        publishSection.className = "publish-section";
        publishSection.setAttribute("aria-label", "Publication");
        publishSection.style.display = "none";
        publishSection.innerHTML = `
            <div class="publish-controls-card">
                <h2>${escapeHtml(tr("publish.ui.sectionTitle", "Publier"))}</h2>
                <div class="publish-controls-grid">
                    <div class="download-control-group wide">
                        <label for="publish-model-selector">${escapeHtml(tr("publish.ui.modelLabel", "Modele"))}</label>
                        <select id="publish-model-selector" class="publish-model-selector">
                            <option value="">${escapeHtml(tr("main.models.loading", "Chargement des modèles..."))}</option>
                        </select>
                    </div>
                    <div class="download-control-group wide">
                        <label for="publish-datetime">${escapeHtml(tr("publish.ui.datetimeLabel", "Date et heure de publication"))}</label>
                        <input id="publish-datetime" type="datetime-local">
                    </div>
                    <div class="download-control-group actions">
                        <button id="publish-submit" class="dm-btn primary" type="button">${escapeHtml(tr("publish.confirm.action", "Publier"))}</button>
                    </div>
                </div>
                <p id="publish-status" class="status-message">${escapeHtml(tr("publish.status.ready", "Pret."))}</p>
            </div>

            <div class="publish-logs-card" aria-live="polite">
                <div class="publish-logs-header">
                    <h3>${escapeHtml(tr("publish.ui.logsTitle", "Logs de questions"))}</h3>
                    <div class="publish-logs-actions">
                        <button id="publish-refresh-logs" class="dm-btn secondary publish-refresh-logs-btn" type="button">${escapeHtml(tr("publish.logs.refresh", "Refresh"))}</button>
                        <button id="publish-export-logs" class="dm-btn secondary publish-export-logs-btn" type="button">${escapeHtml(tr("publish.logs.export", "Export"))}</button>
                    </div>
                </div>
                <div id="publish-logs-list" class="publish-logs-list">
                    <p class="publish-log-empty">${escapeHtml(tr("publish.logs.loading", "Chargement des logs..."))}</p>
                </div>
            </div>
        `;

        panel.appendChild(publishSection);
        hydratePublishElements();

        if (els.publishSubmit) {
            els.publishSubmit.addEventListener("click", onPublishSubmit);
        }
        ensurePublishRefreshControl();
        bindPublishRefreshButton();
        bindPublishExportButton();
    }

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
        extract_docx: "downloadManager.steps.extract_docx",
        extract_references: "downloadManager.steps.extract_references",
        generate_transcripts_json: "downloadManager.steps.generate_transcripts_json",
        generate_questions: "downloadManager.steps.generate_questions",
        index_chromadb_json: "downloadManager.steps.index_chromadb_json"
    };

    function getStepLabel(stepKey) {
        const fallbacks = {
            extract_docx: "Extraction des documents",
            extract_references: "Extraction des references",
            generate_transcripts_json: "Generation des transcripts",
            generate_questions: "Generation des questions",
            index_chromadb_json: "Indexation ChromaDB"
        };
        const key = STEP_LABELS[stepKey];
        return key ? tr(key, fallbacks[stepKey] || stepKey) : (fallbacks[stepKey] || stepKey);
    }

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
                confirmButtonText: confirmText || tr("downloadManager.confirm.default", "Confirmer"),
                cancelButtonText: tr("downloadManager.confirm.cancel", "Annuler"),
                reverseButtons: true,
            });
            return Boolean(result.isConfirmed);
        }
        return confirm(text || title);
    }

    function showAlertMessage(message, isError) {
        if (hasSweetAlert()) {
            window.Swal.fire({
                title: isError
                    ? tr("downloadManager.alert.errorTitle", "Erreur")
                    : tr("downloadManager.alert.infoTitle", "Information"),
                text: message,
                icon: isError ? "error" : "info",
                confirmButtonText: tr("downloadManager.alert.ok", "OK"),
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
            els.resetDebugFiles.textContent = tr("downloadManager.buttons.resetInProgress", "Reset en cours...");
        }

        let progress = 8;
        setResetProgress(progress, tr("downloadManager.progress.preparing", "Préparation..."));
        resetProgressTimer = window.setInterval(() => {
            progress = Math.min(progress + 6, 90);
            setResetProgress(progress, tr("downloadManager.progress.syncing", "Synchronisation... {progress}%", { progress }));
        }, 350);
    }

    function finishResetProgress(success) {
        if (resetProgressTimer) {
            window.clearInterval(resetProgressTimer);
            resetProgressTimer = null;
        }

        setResetProgress(100, success
            ? tr("downloadManager.progress.completed", "Terminé")
            : tr("downloadManager.progress.interrupted", "Interrompu"));

        if (els.resetDebugFiles) {
            els.resetDebugFiles.disabled = false;
            els.resetDebugFiles.textContent = tr("downloadManager.buttons.resetFiles", "Réinitialiser les fichiers");
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
            els.startIndexing.textContent = tr("downloadManager.buttons.indexingInProgress", "Indexage en cours...");
        }
        if (els.cancelIndexing) {
            els.cancelIndexing.style.display = "inline-flex";
            els.cancelIndexing.disabled = false;
        }
        if (els.indexingProgressWrap) {
            els.indexingProgressWrap.style.display = "block";
        }

        let progress = 5;
        setIndexingProgress(progress, tr("downloadManager.progress.preparing", "Préparation..."));
        indexingProgressTimer = window.setInterval(() => {
            if (hasLiveStepStatus) {
                return;
            }
            progress = Math.min(progress + 1, 14);
            setIndexingProgress(progress, tr("downloadManager.progress.preparing", "Préparation..."));
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

        setIndexingProgress(100, success
            ? tr("downloadManager.progress.completed", "Terminé")
            : tr("downloadManager.progress.interrupted", "Interrompu"));

        if (els.startIndexing) {
            els.startIndexing.disabled = false;
            els.startIndexing.textContent = tr("downloadManager.buttons.startIndexing", "Démarrer un indexage");
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

            const label = regen.current_step_label || getStepLabel(stepKey);
            const stepIndex = Number(regen.step_index || 0);
            const totalSteps = Number(regen.total_steps || 0);

            if (isStepTransitioning) {
                return;
            }

            if (currentStepKey !== stepKey) {
                if (currentStepKey) {
                    const previousLabel = getStepLabel(currentStepKey);
                    const previousStepIndex = Math.max(1, stepIndex - 1);
                    const previousCountText = previousStepIndex > 0 && totalSteps > 0
                        ? ` (${previousStepIndex}/${totalSteps})`
                        : "";
                    setIndexingProgress(100, tr(
                        "downloadManager.progress.step",
                        `Etape${previousCountText}: ${previousLabel} (100%)`,
                        {
                            countText: previousCountText,
                            label: previousLabel,
                            percent: 100
                        }
                    ));
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
                        setIndexingProgress(0, tr(
                            "downloadManager.progress.step",
                            `Etape${countText}: ${label} (0%)`,
                            {
                                countText,
                                label,
                                percent: 0
                            }
                        ));
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
                tr(
                    "downloadManager.progress.step",
                    `Etape${countText}: ${label} (${Math.round(currentStepPercent)}%)`,
                    {
                        countText,
                        label,
                        percent: Math.round(currentStepPercent)
                    }
                )
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
            setStatus(tr("downloadManager.status.cancelRequested", "Annulation de l'indexage demandée..."), false);

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
            setStatus(tr("downloadManager.status.cancelError", "Erreur annulation: {error}", { error: error.message }), true);
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

    function setPublishStatus(message, isError) {
        if (!els.publishStatus) {
            return;
        }
        els.publishStatus.textContent = message;
        els.publishStatus.classList.toggle("error", Boolean(isError));
    }

    function activateDownloadView() {
        const panel = document.getElementById("download-manager-panel");
        const chatContainer = document.getElementById("chat-container");
        const chatInputArea = document.querySelector("footer .input-area");
        const emptyState = document.getElementById("empty-state");
        const chatTopSpacer = document.getElementById("chat-top-spacer");

        hideIntegratedPanels();

        ensurePublishSectionMounted();

        if (els.downloadSection) {
            els.downloadSection.style.display = "flex";
        }
        if (els.publishSection) {
            els.publishSection.style.display = "none";
        }
        if (!els.downloadSection) {
            document.querySelectorAll("#download-manager-panel > section:not(#publish-section)").forEach((section) => {
                section.style.display = "";
            });
        }

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

    function activatePublishView() {
        const chatContainer = document.getElementById("chat-container");
        const chatInputArea = document.querySelector("footer .input-area");
        const emptyState = document.getElementById("empty-state");

        hideIntegratedPanels();

        ensurePublishSectionMounted();

        if (els.downloadSection) {
            els.downloadSection.style.display = "none";
        }
        if (els.publishSection) {
            els.publishSection.style.display = "flex";
        }
        if (!els.downloadSection) {
            document.querySelectorAll("#download-manager-panel > section:not(#publish-section)").forEach((section) => {
                section.style.display = "none";
            });
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
        const validateLink = document.getElementById("validate-link");

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

        if (validateLink) {
            validateLink.addEventListener("click", async (event) => {
                event.preventDefault();
                activatePublishView();
                await Promise.allSettled([loadPublishModels(), loadPublishLogs()]);
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

    function toDatetimeLocalValue(date = new Date()) {
        const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
        return local.toISOString().slice(0, 16);
    }

    function ensurePublishDefaults() {
        if (els.publishDatetime && !els.publishDatetime.value) {
            els.publishDatetime.value = toDatetimeLocalValue(new Date());
        }
        setPublishStatus(tr("publish.status.ready", "Pret."), false);
    }

    async function loadPublishModels() {
        if (!els.publishModelSelector) {
            return;
        }

        els.publishModelSelector.innerHTML = `<option value="">${escapeHtml(tr("main.models.loading", "Chargement des modèles..."))}</option>`;
        els.publishModelSelector.disabled = true;

        try {
            const response = await fetch(`${BACKEND_URL}/api/models`);
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.message || payload.detail || response.statusText);
            }

            const models = Array.isArray(payload.models) ? payload.models : [];
            if (!models.length) {
                els.publishModelSelector.innerHTML = `<option value="">${escapeHtml(tr("main.models.noneAvailable", "Aucun modèle disponible"))}</option>`;
                return;
            }

            els.publishModelSelector.innerHTML = "";
            models.forEach((model) => {
                const option = document.createElement("option");
                option.value = model.id || "";
                option.textContent = model.label || model.id || "Model";
                els.publishModelSelector.appendChild(option);
            });

            const selectedByUser = localStorage.getItem(MODEL_STORAGE_KEY) || "";
            const defaultModel = payload.default_model || "";
            const candidate = selectedByUser || defaultModel;

            if (candidate && models.some((m) => m.id === candidate)) {
                els.publishModelSelector.value = candidate;
            }
            if (!els.publishModelSelector.value && models[0] && models[0].id) {
                els.publishModelSelector.value = models[0].id;
            }
            els.publishModelSelector.disabled = false;
        } catch (error) {
            els.publishModelSelector.innerHTML = `<option value="">${escapeHtml(tr("main.models.loadError", "Erreur chargement modèles"))}</option>`;
            els.publishModelSelector.disabled = true;
        }
    }

    function renderPublishLogs(logs) {
        if (!els.publishLogsList) {
            return;
        }

        const renderMarkdownHtml = (rawText) => {
            const text = String(rawText || "");

            // Preferred rendering path: markdown -> sanitized HTML.
            try {
                if (window.marked && typeof window.marked.parse === "function") {
                    const markdownHtml = window.marked.parse(text);
                    if (window.DOMPurify && typeof window.DOMPurify.sanitize === "function") {
                        return window.DOMPurify.sanitize(markdownHtml);
                    }
                    return markdownHtml;
                }
            } catch (_) {
                // Fallback below.
            }

            // Safe plain-text fallback when markdown libraries are unavailable.
            return escapeHtml(text).replace(/\n/g, "<br>");
        };

        if (!Array.isArray(logs) || !logs.length) {
            els.publishLogsList.innerHTML = `<p class="publish-log-empty">${escapeHtml(tr("publish.logs.empty", "Aucun log disponible."))}</p>`;
            return;
        }

        const rows = logs.slice().reverse().map((entry, index) => {
            const questionIdRaw = String(entry.question_id || `#${index + 1}`);
            const timestampRaw = String(entry.timestamp || "-");
            const modelRaw = String(entry.model_used || tr("publish.logs.modelUnknown", "inconnu"));
            const questionRaw = String(entry.question || "-");
            const responseRaw = String(entry.response || "-");

            const ts = escapeHtml(formatDate(timestampRaw));
            const model = escapeHtml(modelRaw);
            const questionHtml = renderMarkdownHtml(questionRaw);
            const responseHtml = renderMarkdownHtml(responseRaw);

            const likes = entry && typeof entry.likes === "object" ? entry.likes : null;
            const voteLabel = likes ? (likes.like ? "👍 Like" : "👎 Dislike") : "-";
            const commentsCount = Array.isArray(entry.comments) ? entry.comments.length : 0;

            return `
                <article class="publish-log-item">
                    <div class="publish-log-header">
                        <span class="publish-log-index">#${index + 1}</span>
                        <span class="publish-log-model">${model}</span>
                    </div>
                    <div class="publish-log-meta">
                        <span><strong>Date:</strong> ${ts}</span>
                        <span><strong>Vote:</strong> ${escapeHtml(voteLabel)}</span>
                        <span><strong>Commentaires:</strong> ${commentsCount}</span>
                    </div>
                    <div class="publish-log-block">
                        <p class="publish-log-label">Question</p>
                        <div class="publish-log-question publish-log-markdown">${questionHtml}</div>
                    </div>
                    <div class="publish-log-block publish-log-answer-block">
                        <div class="message-text markdown publish-log-response">${responseHtml}</div>
                    </div>
                </article>
            `;
        });

        els.publishLogsList.innerHTML = rows.join("");
    }

    async function loadPublishLogs() {
        if (!els.publishLogsList) {
            return;
        }
        els.publishLogsList.innerHTML = `<p class="publish-log-empty">${escapeHtml(tr("publish.logs.loading", "Chargement des logs..."))}</p>`;

        try {
            const data = await fetchJson(`${BACKEND_URL}/api/download_log`, {
                headers: {
                    ...authHeaders()
                }
            });
            renderPublishLogs(Array.isArray(data) ? data : []);
        } catch (error) {
            els.publishLogsList.innerHTML = `<p class="publish-log-empty">${escapeHtml(tr("publish.logs.error", "Erreur chargement logs: {error}", { error: error.message }))}</p>`;
        }
    }

    async function onPublishSubmit() {
        const selectedModel = els.publishModelSelector ? String(els.publishModelSelector.value || "").trim() : "";
        const publishAt = els.publishDatetime ? String(els.publishDatetime.value || "").trim() : "";

        if (!selectedModel) {
            setPublishStatus(tr("publish.status.modelRequired", "Veuillez selectionner un modele."), true);
            return;
        }
        if (!publishAt) {
            setPublishStatus(tr("publish.status.datetimeRequired", "Veuillez selectionner une date et heure."), true);
            return;
        }

        const confirmed = await confirmAction({
            title: tr("publish.confirm.title", "Confirmer la publication ?"),
            text: tr("publish.confirm.text", "Modele: {model} - Date: {date}", { model: selectedModel, date: publishAt }),
            confirmText: tr("publish.confirm.action", "Publier"),
        });

        if (!confirmed) {
            return;
        }

        // Endpoint intentionally deferred per requirement.
        setPublishStatus(tr("publish.status.endpointPending", "Publication confirmee. Endpoint a creer ensuite."), false);
        await loadPublishLogs();
    }

    function getToken() {
        return localStorage.getItem(TOKEN_KEY) || "";
    }

    function authHeaders() {
        const token = getToken();
        if (!token) {
            throw new Error(tr("downloadManager.errors.tokenRequired", "Token admin requis."));
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
        const locale = currentLanguage() === "en" ? "en-CA" : "fr-CA";
        return date.toLocaleString(locale);
    }

    function renderRows(files) {
        if (!els.filesTbody) {
            return;
        }

        if (!files.length) {
            els.filesTbody.innerHTML = `<tr><td colspan="4">${escapeHtml(tr("downloadManager.table.noFiles", "Aucun fichier trouvé pour ce filtre."))}</td></tr>`;
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
                        <button class="dm-btn table-action" data-action="download" data-name="${encodeURIComponent(blobName)}">${escapeHtml(tr("downloadManager.table.download", "Télécharger"))}</button>
                        <button class="dm-btn table-action danger" data-action="delete" data-name="${encodeURIComponent(blobName)}">${escapeHtml(tr("downloadManager.table.delete", "Supprimer"))}</button>
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
            setStatus(tr("downloadManager.status.loadingFiles", "Chargement des fichiers Azure..."), false);
            if (els.filesTbody) {
                els.filesTbody.innerHTML = `<tr><td colspan="4">${escapeHtml(tr("downloadManager.table.loading", "Chargement..."))}</td></tr>`;
            }
            const prefix = DOCUMENTS_PREFIX;
            const query = prefix ? `?prefix=${encodeURIComponent(prefix)}` : "";
            const data = await fetchJson(withContainerQuery(`${BACKEND_URL}/api/blob/files${query}`), {
                headers: {
                    ...authHeaders()
                }
            });
            renderRows(Array.isArray(data.files) ? data.files : []);
            setStatus(tr("downloadManager.status.filesFound", "{count} fichier(s) trouvé(s) dans {container}.", {
                count: data.count || 0,
                container: data.container || tr("downloadManager.status.defaultContainer", "le conteneur")
            }), false);
        } catch (error) {
            if (els.filesTbody) {
                els.filesTbody.innerHTML = `<tr><td colspan="4">${escapeHtml(tr("downloadManager.table.errorPrefix", "Erreur: "))}${escapeHtml(error.message)}</td></tr>`;
            }
            setStatus(tr("downloadManager.status.loadError", "Erreur de chargement: {error}", { error: error.message }), true);
        }
    }

    async function deleteFile(blobName) {
        if (!blobName) {
            return;
        }
        const confirmed = await confirmAction({
            title: tr("downloadManager.confirm.deleteTitle", "Supprimer ce fichier ?"),
            text: blobName,
            confirmText: tr("downloadManager.confirm.delete", "Supprimer"),
        });
        if (!confirmed) {
            return;
        }

        try {
            setStatus(tr("downloadManager.status.deleting", "Suppression de {name}...", { name: blobName }), false);
            await fetchJson(withContainerQuery(`${BACKEND_URL}/api/blob/files/${encodeURI(blobName)}`), {
                method: "DELETE",
                headers: {
                    ...authHeaders()
                }
            });
            setStatus(tr("downloadManager.status.deleted", "Fichier supprimé: {name}", { name: blobName }), false);
            await loadFiles();
        } catch (error) {
            setStatus(tr("downloadManager.status.deleteError", "Erreur suppression: {error}", { error: error.message }), true);
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

            setStatus(tr("downloadManager.status.downloadStarted", "Téléchargement lancé: {name}", { name: blobName }), false);
            await loadFiles();
        } catch (error) {
            setStatus(tr("downloadManager.status.downloadError", "Erreur téléchargement: {error}", { error: error.message }), true);
        }
    }

    async function uploadFile(inputFile) {
        if (!inputFile) {
            setStatus(tr("downloadManager.status.selectLocalFile", "Sélectionnez un fichier local."), true);
            return;
        }

        const safeFileName = (inputFile.name || "").split(/[\\/]/).pop() || "upload.bin";
        const blobName = `${STORAGE_DOCUMENTS_PREFIX}${safeFileName}`;

        try {
            setStatus(tr("downloadManager.status.uploading", "Téléversement en cours..."), false);
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

            setStatus(tr("downloadManager.status.uploaded", "Fichier téléversé: {name}", { name: payload.blob_name || blobName }), false);
            await loadFiles();
        } catch (error) {
            setStatus(tr("downloadManager.status.uploadError", "Erreur upload: {error}", { error: error.message }), true);
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
                els.fileName.textContent = tr("downloadManager.status.fileSelected", "Fichier sélectionné: {name}", { name: file.name });
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
            title: tr("downloadManager.confirm.startIndexingTitle", "Démarrer l'indexage ?"),
            text: tr("downloadManager.confirm.startIndexingText", "La régénération et l'indexation peuvent prendre plusieurs minutes."),
            confirmText: tr("downloadManager.confirm.start", "Démarrer"),
        });
        if (!confirmed) {
            return;
        }

        try {
            beginIndexingProgress();
            indexingAbortController = new AbortController();
            setStatus(tr("downloadManager.status.indexingInProgress", "Indexage en cours... cela peut prendre plusieurs minutes."), false);
            const result = await fetchJson(`${BACKEND_URL}/api/database/regenerate`, {
                method: "POST",
                headers: {
                    ...authHeaders()
                },
                signal: indexingAbortController.signal
            });

            const finalStatus = result.status || "ok";
            if (finalStatus === "cancelled") {
                setStatus(tr("downloadManager.status.indexingCancelled", "Indexage annulé."), true);
                finishIndexingProgress(false);
                showAlertMessage(tr("downloadManager.status.indexingCancelled", "Indexage annulé."), false);
            } else {
                setStatus(tr("downloadManager.status.indexingCompleted", "Indexage terminé. Statut: {status}", { status: finalStatus }), false);
                finishIndexingProgress(true);
                showAlertMessage(tr("downloadManager.status.indexingDone", "Indexage terminé."), false);
            }
        } catch (error) {
            if (error && error.name === "AbortError") {
                setStatus(tr("downloadManager.status.indexingCancelled", "Indexage annulé."), true);
            } else {
                setStatus(tr("downloadManager.status.indexingError", "Erreur indexage: {error}", { error: error.message }), true);
                showAlertMessage(tr("downloadManager.status.indexingError", "Erreur indexage: {error}", { error: error.message }), true);
            }
            finishIndexingProgress(false);
        } finally {
            indexingAbortController = null;
        }
    }

    async function resetDebugFilesFromBlob() {
        const confirmed = await confirmAction({
            title: tr("downloadManager.confirm.resetTitle", "Réinitialiser les fichiers ?"),
            text: tr("downloadManager.confirm.resetText", "Cette action va rétablir les fichiers précédents."),
            confirmText: tr("downloadManager.confirm.reset", "Réinitialiser"),
        });
        if (!confirmed) {
            return;
        }

        try {
            beginResetProgress();
            setStatus(tr("downloadManager.status.resetInProgress", "Réinitialisation depuis le blob en cours..."), false);

            const result = await fetchJson(withContainerQuery(`${BACKEND_URL}/api/blob/debug/reset-local`), {
                method: "POST",
                headers: {
                    ...authHeaders()
                }
            });

            const docsCount = Number(result.documents_count || 0);
            setStatus(tr("downloadManager.status.resetDone", "Reset terminé. {count} fichier(s) dans documents/.", { count: docsCount }), false);
            finishResetProgress(true);
            await loadFiles();
        } catch (error) {
            setStatus(tr("downloadManager.status.resetError", "Erreur reset: {error}", { error: error.message }), true);
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
        ensurePublishSectionMounted();
        ensurePublishRefreshControl();
        bindNavigationToggles();
        bindTokenSync();

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
        if (els.publishSubmit) {
            els.publishSubmit.addEventListener("click", onPublishSubmit);
        }
        bindPublishRefreshButton();
        bindPublishExportButton();

        bindDragAndDrop();
        bindTableActions();
        ensurePublishDefaults();
        loadFiles();
    }

    document.addEventListener("DOMContentLoaded", init);
})();
