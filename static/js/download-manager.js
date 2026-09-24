(function () {
    const BACKEND_URL = window.BACKEND_URL || "";
    const DEBUG_BLOB_CONTAINER = window.DEBUG_BLOB_CONTAINER || "nutrifaq-knowledge-base-debug";
    const DEBUG_BLOB_ROOT_FOLDER = window.DEBUG_BLOB_ROOT_FOLDER || "nutrifaq-dbase-main";
    const DOCUMENTS_PREFIX = `${DEBUG_BLOB_ROOT_FOLDER}/documents/`;
    const STORAGE_DOCUMENTS_PREFIX = `${DEBUG_BLOB_ROOT_FOLDER}/documents/`;
    const MODEL_STORAGE_KEY = "nutrifaq_selected_model";
    const LOGS_TAB_QUESTIONS = "questions";
    const LOGS_TAB_PUBLISH = "publish";
    let activePublishLogsTab = LOGS_TAB_QUESTIONS;

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
        instructionsSection: document.getElementById("instructions-section"),
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
        publishSubmit: document.getElementById("publish-submit"),
        publishRevert: document.getElementById("publish-revert"),
        publishStatus: document.getElementById("publish-status"),
        publishFinishMessage: document.getElementById("publish-finish-message"),
        publishProgressWrap: document.getElementById("publish-progress-wrap"),
        publishProgressBar: document.getElementById("publish-progress-bar"),
        publishProgressText: document.getElementById("publish-progress-text"),
        publishLogsList: document.getElementById("publish-logs-list"),
        publishRefreshLogs: document.getElementById("publish-refresh-logs"),
        publishResetLogs: document.getElementById("publish-reset-logs"),
        publishExportLogs: document.getElementById("publish-export-logs")
    };

    function hydratePublishElements() {
        els.instructionsSection = document.getElementById("instructions-section");
        els.publishSection = document.getElementById("publish-section");
        els.publishModelSelector = document.getElementById("publish-model-selector");
        els.publishSubmit = document.getElementById("publish-submit");
        els.publishRevert = document.getElementById("publish-revert");
        els.publishStatus = document.getElementById("publish-status");
        els.publishFinishMessage = document.getElementById("publish-finish-message");
        els.publishProgressWrap = document.getElementById("publish-progress-wrap");
        els.publishProgressBar = document.getElementById("publish-progress-bar");
        els.publishProgressText = document.getElementById("publish-progress-text");
        els.publishLogsList = document.getElementById("publish-logs-list");
        els.publishRefreshLogs = document.getElementById("publish-refresh-logs");
        els.publishResetLogs = document.getElementById("publish-reset-logs");
        els.publishExportLogs = document.getElementById("publish-export-logs");
    }

    function setPublishProgress(value, text) {
        const progressValue = Math.max(0, Math.min(100, Number(value) || 0));
        if (els.publishProgressWrap) {
            els.publishProgressWrap.style.display = "block";
        }
        if (els.publishProgressBar) {
            els.publishProgressBar.style.width = `${progressValue}%`;
        }
        if (els.publishProgressText) {
            els.publishProgressText.textContent = text || `${progressValue}%`;
        }
    }

    function hidePublishProgress() {
        if (els.publishProgressWrap) {
            els.publishProgressWrap.style.display = "none";
        }
        if (els.publishProgressBar) {
            els.publishProgressBar.style.width = "0%";
        }
        if (els.publishProgressText) {
            els.publishProgressText.textContent = "0%";
        }
    }

    function setPublishFinishMessage(message) {
        if (!els.publishFinishMessage) {
            return;
        }
        els.publishFinishMessage.textContent = message || "";
        els.publishFinishMessage.hidden = !message;
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
                fallbackHeading.textContent = tr("publish.ui.logsTitle", "Historique d'activite");
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

        if (!headerActions.querySelector("#publish-reset-logs")) {
            const resetBtn = document.createElement("button");
            resetBtn.id = "publish-reset-logs";
            resetBtn.type = "button";
            resetBtn.className = "dm-btn secondary publish-reset-logs-btn";
            resetBtn.textContent = tr("publish.logs.reset", "Reinit");
            headerActions.appendChild(resetBtn);
        }

        if (!headerActions.querySelector("#publish-export-logs")) {
            const exportBtn = document.createElement("button");
            exportBtn.id = "publish-export-logs";
            exportBtn.type = "button";
            exportBtn.className = "dm-btn primary publish-export-logs-btn";
            exportBtn.textContent = tr("publish.logs.export", "Export");
            headerActions.appendChild(exportBtn);
        }

        if (!logsCard.querySelector("#publish-logs-tabs")) {
            const tabs = document.createElement("div");
            tabs.id = "publish-logs-tabs";
            tabs.className = "publish-logs-tabs";
            tabs.innerHTML = `
                <button id="publish-logs-tab-questions" class="publish-logs-tab" type="button" data-tab="${LOGS_TAB_QUESTIONS}">${escapeHtml(tr("publish.logs.tabs.questions", "Conversations"))}</button>
                <button id="publish-logs-tab-publish" class="publish-logs-tab" type="button" data-tab="${LOGS_TAB_PUBLISH}">${escapeHtml(tr("publish.logs.tabs.publish", "Publications"))}</button>
            `;
            logsHeader.insertAdjacentElement("afterend", tabs);
        }

        hydratePublishElements();
        applyPublishTranslations();
    }

    function updateLogsActionsVisibility() {
        if (els.publishResetLogs) {
            const isQuestionsTab = activePublishLogsTab === LOGS_TAB_QUESTIONS;
            els.publishResetLogs.style.display = "inline-flex";
            els.publishResetLogs.disabled = !isQuestionsTab;
            els.publishResetLogs.setAttribute("aria-disabled", String(!isQuestionsTab));
        }
    }

    function syncPublishLogsTabButtons() {
        if (!els.publishSection) {
            return;
        }
        const questionTab = els.publishSection.querySelector("#publish-logs-tab-questions");
        const publishTab = els.publishSection.querySelector("#publish-logs-tab-publish");

        const isQuestions = activePublishLogsTab === LOGS_TAB_QUESTIONS;
        if (questionTab) {
            questionTab.classList.toggle("active", isQuestions);
            questionTab.setAttribute("aria-selected", String(isQuestions));
        }
        if (publishTab) {
            publishTab.classList.toggle("active", !isQuestions);
            publishTab.setAttribute("aria-selected", String(!isQuestions));
        }

        updateLogsActionsVisibility();
    }

    async function setActivePublishLogsTab(tabKey) {
        activePublishLogsTab = tabKey === LOGS_TAB_PUBLISH ? LOGS_TAB_PUBLISH : LOGS_TAB_QUESTIONS;
        syncPublishLogsTabButtons();
        await loadActivePublishLogs();
    }

    function bindPublishLogsTabButtons() {
        if (!els.publishSection) {
            return;
        }

        const questionTab = els.publishSection.querySelector("#publish-logs-tab-questions");
        const publishTab = els.publishSection.querySelector("#publish-logs-tab-publish");

        if (questionTab && questionTab.dataset.bound !== "1") {
            questionTab.dataset.bound = "1";
            questionTab.addEventListener("click", async () => {
                if (activePublishLogsTab !== LOGS_TAB_QUESTIONS) {
                    await setActivePublishLogsTab(LOGS_TAB_QUESTIONS);
                }
            });
        }

        if (publishTab && publishTab.dataset.bound !== "1") {
            publishTab.dataset.bound = "1";
            publishTab.addEventListener("click", async () => {
                if (activePublishLogsTab !== LOGS_TAB_PUBLISH) {
                    await setActivePublishLogsTab(LOGS_TAB_PUBLISH);
                }
            });
        }

        syncPublishLogsTabButtons();
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
            modelLabel.textContent = tr("publish.ui.modelLabel", "Modèle IA final utilisé");
        }

        if (els.publishSubmit) {
            els.publishSubmit.textContent = tr("publish.confirm.action", "Publier");
        }

        if (els.publishRevert) {
            els.publishRevert.textContent = tr("publish.revert.action", "Rétablir");
        }

        const logsTitle = els.publishSection.querySelector(".publish-logs-header h3");
        if (logsTitle) {
            logsTitle.textContent = tr("publish.ui.logsTitle", "Historique d'activite");
        }

        if (els.publishRefreshLogs) {
            els.publishRefreshLogs.textContent = tr("publish.logs.refresh", "Refresh");
        }

        if (els.publishExportLogs) {
            els.publishExportLogs.textContent = tr("publish.logs.export", "Export");
        }

        if (els.publishResetLogs) {
            els.publishResetLogs.textContent = tr("publish.logs.reset", "Reinit");
        }

        const questionTab = els.publishSection.querySelector("#publish-logs-tab-questions");
        if (questionTab) {
            questionTab.textContent = tr("publish.logs.tabs.questions", "Conversations");
        }
        const publishTab = els.publishSection.querySelector("#publish-logs-tab-publish");
        if (publishTab) {
            publishTab.textContent = tr("publish.logs.tabs.publish", "Publications");
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
            await loadActivePublishLogs();
        });
    }

    async function resetQuestionLogs() {
        const confirmed = await confirmAction({
            title: tr("publish.logs.questionsResetTitle", "Reset question logs?"),
            text: tr("publish.logs.questionsResetConfirm", "Voulez-vous vraiment reinitialiser le journal des questions ?"),
            confirmText: tr("publish.logs.questionsResetAction", "Reset")
        });

        if (!confirmed) {
            return;
        }

        try {
            setPublishStatus(tr("publish.logs.reset", "Reset"), false);
            const response = await fetch(`${BACKEND_URL}/api/reset_question_log`, {
                method: "POST",
                headers: {
                    ...authHeaders(),
                    "Content-Type": "application/json",
                }
            });

            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || payload.message || response.statusText || tr("publish.logs.questionsResetError", "Erreur lors de la reinitialisation du journal des questions: {error}", { error: response.statusText }));
            }

            await loadQuestionLogs();
            setPublishStatus(tr("publish.logs.questionsResetSuccess", "Le journal des questions a ete reinitialise."), false);
        } catch (error) {
            const message = error && error.message ? error.message : tr("publish.logs.questionsResetError", "Erreur lors de la reinitialisation du journal des questions: {error}", { error: "inconnu" });
            setPublishStatus(message, true);
        }
    }

    function bindPublishResetButton() {
        if (!els.publishResetLogs || els.publishResetLogs.dataset.bound === "1") {
            return;
        }
        els.publishResetLogs.dataset.bound = "1";
        els.publishResetLogs.addEventListener("click", async () => {
            if (activePublishLogsTab === LOGS_TAB_QUESTIONS) {
                await resetQuestionLogs();
            }
        });
    }

    function getCurrentExportTitle() {
        if (activePublishLogsTab === LOGS_TAB_PUBLISH) {
            return tr("publish.logs.exportTitlePublish", "Rapport d'activite : Publications");
        }
        return tr("publish.logs.exportTitleQuestions", "Rapport d'activite : Discussions");
    }

    function buildPublishLogsExportElement() {
        const title = getCurrentExportTitle();
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
        const titlePart = slugifyFilePart(getCurrentExportTitle());
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
        const footerText = tr("publish.logs.footerText", "IMX Technologie Copyright © 2026");

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
            ensurePublishRefreshControl();
            bindPublishLogsTabButtons();
            bindPublishRefreshButton();
            bindPublishResetButton();
            bindPublishExportButton();
            syncPublishLogsTabButtons();
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
                        <label for="publish-model-selector">${escapeHtml(tr("publish.ui.modelLabel", "Modèle final utilisé"))}</label>
                        <select id="publish-model-selector" class="publish-model-selector">
                            <option value="">${escapeHtml(tr("main.models.loading", "Chargement des modèles..."))}</option>
                        </select>
                    </div>
                    <div class="download-control-group actions">
                        <button id="publish-revert" class="dm-btn secondary" type="button">${escapeHtml(tr("publish.revert.action", "Rétablir"))}</button>
                        <button id="publish-submit" class="dm-btn primary" type="button">${escapeHtml(tr("publish.confirm.action", "Publier"))}</button>
                    </div>
                </div>

                <div id="publish-progress-wrap" class="publish-progress-wrap" style="display:none;">
                    <div class="publish-progress-track">
                        <div id="publish-progress-bar" class="publish-progress-bar" style="width:0%;"></div>
                    </div>
                    <div id="publish-progress-text" class="publish-progress-text">0%</div>
                </div>

                <p id="publish-status" class="status-message">${escapeHtml(tr("publish.status.ready", "Prêt."))}</p>
                <p id="publish-finish-message" class="publish-finish-message" hidden></p>
            </div>

            <div class="publish-logs-card" aria-live="polite">
                <div class="publish-logs-header">
                    <h3>${escapeHtml(tr("publish.ui.logsTitle", "Historique d'activite"))}</h3>
                    <div class="publish-logs-actions">
                        <button id="publish-refresh-logs" class="dm-btn secondary publish-refresh-logs-btn" type="button">${escapeHtml(tr("publish.logs.refresh", "Refresh"))}</button>
                        <button id="publish-reset-logs" class="dm-btn secondary publish-reset-logs-btn" type="button">${escapeHtml(tr("publish.logs.reset", "Reinit"))}</button>
                        <button id="publish-export-logs" class="dm-btn primary publish-export-logs-btn" type="button">${escapeHtml(tr("publish.logs.export", "Export"))}</button>
                    </div>
                </div>
                <div id="publish-logs-tabs" class="publish-logs-tabs">
                    <button id="publish-logs-tab-questions" class="publish-logs-tab" type="button" data-tab="${LOGS_TAB_QUESTIONS}">${escapeHtml(tr("publish.logs.tabs.questions", "Conversations"))}</button>
                    <button id="publish-logs-tab-publish" class="publish-logs-tab" type="button" data-tab="${LOGS_TAB_PUBLISH}">${escapeHtml(tr("publish.logs.tabs.publish", "Publications"))}</button>
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
        if (els.publishRevert) {
            els.publishRevert.addEventListener("click", onRevertSubmit);
        }
        ensurePublishRefreshControl();
        bindPublishLogsTabButtons();
        bindPublishRefreshButton();
        bindPublishResetButton();
        bindPublishExportButton();
        syncPublishLogsTabButtons();
    }

    const TOKEN_KEY = "nutrifaq_admin_bearer_token";
    let indexingStatusTimer = null;
    let indexingAbortController = null;
    let resetProgressTimer = null;
    let isIndexingRunning = false;
    let currentStepKey = null;
    let currentStepPercent = 0;
    let isStepTransitioning = false;
    let stepSwitchTimer = null;
    let currentFiles = [];

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
        // Use a single shared progress UI in the download panel.
        setIndexingProgress(value, text);
    }

    function beginResetProgress() {
        if (els.indexingProgressWrap) {
            els.indexingProgressWrap.classList.add("is-visible");
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
            if (els.indexingProgressWrap) {
                els.indexingProgressWrap.classList.remove("is-visible");
            }
            setResetProgress(0, "0%");
        }, success ? 1200 : 1800);
    }

    function setDownloadStatusRowDisabled(isDisabled) {
        const row = document.querySelector("#download-section .download-status-row");
        if (!row) {
            return;
        }

        const disabled = Boolean(isDisabled);
        row.classList.toggle("is-disabled", disabled);
        row.setAttribute("aria-disabled", String(disabled));
    }

    function beginIndexingProgress() {
        isIndexingRunning = true;
        setDownloadStatusRowDisabled(true);
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
            els.indexingProgressWrap.classList.add("is-visible");
        }

        setIndexingProgress(0, tr("downloadManager.progress.preparing", "Préparation..."));

        startRegenerationStatusPolling();
    }

    function finishIndexingProgress(success) {
        isIndexingRunning = false;
        setDownloadStatusRowDisabled(false);
        currentStepKey = null;
        currentStepPercent = 0;
        isStepTransitioning = false;
        if (stepSwitchTimer) {
            window.clearTimeout(stepSwitchTimer);
            stepSwitchTimer = null;
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
                els.indexingProgressWrap.classList.remove("is-visible");
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

            const label = regen.current_step_label || getStepLabel(stepKey);
            const stepIndex = Number(regen.step_index || 0);
            const totalSteps = Number(regen.total_steps || 0);
            const liveProgressPercent = Number.isFinite(Number(regen.progress_percent))
                ? Number(regen.progress_percent)
                : null;
            const liveProgressValue = Number.isFinite(Number(regen.progress_value))
                ? Number(regen.progress_value)
                : null;
            const liveProgressTotal = Number.isFinite(Number(regen.progress_total))
                ? Number(regen.progress_total)
                : null;
            const liveProgressKind = regen.progress_kind || "";

            if (isStepTransitioning) {
                return;
            }

            currentStepKey = stepKey;
            if (liveProgressPercent !== null) {
                currentStepPercent = Math.max(0, Math.min(100, liveProgressPercent));
            } else if (liveProgressTotal && liveProgressValue !== null) {
                currentStepPercent = Math.max(0, Math.min(100, (liveProgressValue / liveProgressTotal) * 100));
            } else {
                return;
            }

            const countText = stepIndex > 0 && totalSteps > 0
                ? ` (${stepIndex}/${totalSteps})`
                : "";
            const metricText = liveProgressTotal && liveProgressValue !== null
                ? ` (${Math.round(liveProgressValue)}/${Math.round(liveProgressTotal)} ${liveProgressKind === "tokens" ? "tokens" : "questions"})`
                : "";
            setIndexingProgress(
                currentStepPercent,
                tr(
                    "downloadManager.progress.step",
                    `Etape${countText}: ${label}${metricText} (${Math.round(currentStepPercent)}%)`,
                    {
                        countText,
                        label,
                        metricText,
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
        indexingStatusTimer = window.setInterval(refreshRegenerationStatus, 250);
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

    function localizeMessageWithKey(messageKey, fallbackText, params) {
        if (!messageKey || typeof messageKey !== "string") {
            return tr("publish.status.error", fallbackText, params);
        }
        return tr(messageKey, fallbackText, params);
    }

    function setPublishStatus(message, isError) {
        if (!els.publishStatus) {
            return;
        }
        els.publishStatus.textContent = message;
        els.publishStatus.classList.toggle("error", Boolean(isError));
    }

    function setPublishControlsDisabled(isDisabled) {
        const disabled = Boolean(isDisabled);
        if (!els.publishSection) {
            return;
        }

        const grid = els.publishSection.querySelector(".publish-controls-grid");
        if (!grid) {
            return;
        }

        grid.classList.toggle("is-disabled", disabled);
        grid.setAttribute("aria-disabled", String(disabled));

        const controls = grid.querySelectorAll("button, select, input, textarea");
        controls.forEach((control) => {
            control.disabled = disabled;
        });
    }

    function setSuggestedPanelEmpty(isEmpty) {
        const panel = document.getElementById("suggested-questions-panel");
        if (!panel) {
            return;
        }
        panel.classList.toggle("panel-empty", Boolean(isEmpty));
    }

    function getDownloadViewSections() {
        const activeDownloadSection = document.getElementById("download-section");
        if (activeDownloadSection) {
            return activeDownloadSection.querySelectorAll("section");
        }

        return [];
    }

    function activateInstructionsView() {
        const panel = document.getElementById("download-manager-panel");
        const chatContainer = document.getElementById("chat-container");
        const chatMainLayout = document.getElementById("chat-main-layout");
        const chatInputArea = document.getElementById("chat-input-area");
        const emptyState = document.getElementById("empty-state");
        const chatTopSpacer = document.getElementById("chat-top-spacer");
        const mainPane = document.querySelector(".main-pane");
        const chatSection = document.getElementById("chat-section");
        const downloadSection = document.getElementById("download-section");

        hideIntegratedPanels();

        if (mainPane) {
            mainPane.classList.add("non-chat-mode");
        }

        if (chatMainLayout) {
            chatMainLayout.style.display = "none";
        }
        if (chatInputArea) {
            chatInputArea.style.display = "none";
        }

        const panelSections = panel ? panel.querySelectorAll("section") : [];
        panelSections.forEach((section) => {
            section.style.display = (section.id === "instructions-section") ? "flex" : "none";
        });

        if (chatSection) {
            chatSection.style.display = "none";
        }
        if (downloadSection) {
            downloadSection.style.display = "none";
        }
        if (els.instructionsSection) {
            els.instructionsSection.style.display = "flex";
        }
        if (els.downloadSection) {
            els.downloadSection.style.display = "none";
        }
        if (els.publishSection) {
            els.publishSection.style.display = "none";
        }
        if (panel) {
            panel.style.display = "flex";
        }
        if (chatContainer) {
            chatContainer.classList.add("download-mode");
            chatContainer.scrollTo({ top: 0, behavior: "smooth" });
        }
        setSuggestedPanelEmpty(true);
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

    function activateDownloadView() {
        const panel = document.getElementById("download-manager-panel");
        const chatContainer = document.getElementById("chat-container");
        const chatInputArea = document.getElementById("chat-input-area");
        const emptyState = document.getElementById("empty-state");
        const chatTopSpacer = document.getElementById("chat-top-spacer");
        const mainPane = document.querySelector(".main-pane");
        const chatSection = document.getElementById("chat-section");
        const instructionsSection = document.getElementById("instructions-section");

        hideIntegratedPanels();

        if (mainPane) {
            mainPane.classList.add("non-chat-mode");
        }

        if (chatInputArea) {
            chatInputArea.style.display = "none";
        }

        if (chatSection) {
            chatSection.style.display = "none";
        }
        if (instructionsSection) {
            instructionsSection.style.display = "none";
        }

        ensurePublishSectionMounted();

        const panelSections = getDownloadViewSections();
        panelSections.forEach((section) => {
            const shouldShow = section.id === "download-section" ||
                section.classList.contains("download-dropzone-section") ||
                section.classList.contains("download-status-row") ||
                section.classList.contains("download-files-list") ||
                section.id === "indexing-progress-wrap";
            section.style.display = shouldShow ? "" : "none";
        });

        if (els.instructionsSection) {
            els.instructionsSection.style.display = "none";
        }
        if (els.downloadSection) {
            els.downloadSection.style.display = "flex";
        }
        if (els.publishSection) {
            els.publishSection.style.display = "none";
        }

        if (panel) {
            panel.style.display = "flex";
        }
        if (chatContainer) {
            chatContainer.classList.add("download-mode");
            chatContainer.scrollTo({ top: 0, behavior: "smooth" });
        }
        setSuggestedPanelEmpty(true);
        if (chatInputArea) {
            chatInputArea.style.display = "none";
        }
        if (emptyState) {
            emptyState.style.display = "none";
        }
        if (chatTopSpacer) {
            chatTopSpacer.style.display = "none";
        }
        refreshFilesForDownloadView();
    }

    function refreshFilesForDownloadView() {
        loadFiles().catch(() => {
            // Errors are already handled inside loadFiles.
        });
    }

    function activatePublishView() {
        const panel = document.getElementById("download-manager-panel");
        const chatContainer = document.getElementById("chat-container");
        const chatInputArea = document.getElementById("chat-input-area");
        const emptyState = document.getElementById("empty-state");
        const mainPane = document.querySelector(".main-pane");
        const chatSection = document.getElementById("chat-section");
        const instructionsSection = document.getElementById("instructions-section");
        const downloadSection = document.getElementById("download-section");

        hideIntegratedPanels();

        if (mainPane) {
            mainPane.classList.add("non-chat-mode");
        }

        if (chatInputArea) {
            chatInputArea.style.display = "none";
        }

        ensurePublishSectionMounted();

        if (panel) {
            const panelSections = panel.querySelectorAll("section");
            panelSections.forEach((section) => {
                section.style.display = (section.id === "publish-section") ? "flex" : "none";
            });
        }

        if (chatSection) {
            chatSection.style.display = "none";
        }
        if (instructionsSection) {
            instructionsSection.style.display = "none";
        }
        if (downloadSection) {
            downloadSection.style.display = "none";
        }

        if (els.instructionsSection) {
            els.instructionsSection.style.display = "none";
        }
        if (els.downloadSection) {
            els.downloadSection.style.display = "none";
        }
        if (els.publishSection) {
            els.publishSection.style.display = "flex";
        }
        if (chatContainer) {
            chatContainer.classList.add("download-mode");
            chatContainer.scrollTo({ top: 0, behavior: "smooth" });
        }
        setSuggestedPanelEmpty(true);
        if (chatInputArea) {
            chatInputArea.style.display = "none";
        }
        if (emptyState) {
            emptyState.style.display = "none";
        }
    }

    function syncSuggestedPanelToggleButton() {
        const button = document.getElementById("toggle-suggested-panel-btn");
        const mainPane = document.querySelector(".main-pane");
        if (!button || !mainPane) {
            return;
        }

        const isCollapsed = mainPane.classList.contains("suggested-panel-collapsed");
        button.setAttribute("aria-label", isCollapsed ? "Afficher la liste des questions" : "Masquer la liste des questions");
        button.title = isCollapsed ? "Afficher la liste des questions" : "Masquer la liste des questions";
        button.innerHTML = isCollapsed
            ? '<i class="bi bi-question-circle"></i>'
            : '<i class="bi bi-question-circle-fill"></i>';
        button.style.display = "inline-flex";
    }

    function toggleSuggestedQuestionsPanel() {
        const mainPane = document.querySelector(".main-pane");
        if (!mainPane) {
            return;
        }
        mainPane.classList.toggle("suggested-panel-collapsed");
        syncSuggestedPanelToggleButton();
    }

    function refreshSuggestedQuestionsForChatView() {
        const loader = window.ChatModule && window.ChatModule.loadSuggestedQuestions;
        if (typeof loader !== "function") {
            return;
        }

        loader().catch(() => {
            // Keep navigation responsive even if refresh fails.
        });
    }

    function activateTesterView() {
        const chatContainer = document.getElementById("chat-container");
        const chatMainLayout = document.getElementById("chat-main-layout");
        const chatInputArea = document.getElementById("chat-input-area");
        const emptyState = document.getElementById("empty-state");
        const mainPane = document.querySelector(".main-pane");
        const chatSection = document.getElementById("chat-section");
        const instructionsSection = document.getElementById("instructions-section");
        const downloadSection = document.getElementById("download-section");
        const publishSection = document.getElementById("publish-section");

        hideIntegratedPanels();
        if (mainPane) {
            mainPane.classList.remove("non-chat-mode");
            const isMobile = typeof window.matchMedia === "function" && window.matchMedia("(max-width: 768px)").matches;
            mainPane.classList.toggle("suggested-panel-collapsed", isMobile);
        }
        if (chatSection) {
            chatSection.style.display = "grid";
        }
        if (instructionsSection) {
            instructionsSection.style.display = "none";
        }
        if (downloadSection) {
            downloadSection.style.display = "none";
        }
        if (publishSection) {
            publishSection.style.display = "none";
        }
        if (chatContainer) {
            chatContainer.classList.remove("download-mode");
            chatContainer.scrollTo({ top: 0, behavior: "smooth" });
        }
        if (chatMainLayout) {
            chatMainLayout.style.display = "grid";
        }
        setSuggestedPanelEmpty(false);
        if (chatInputArea) {
            chatInputArea.style.display = "flex";
        }
        if (emptyState && !document.querySelector("#chat-container .message")) {
            emptyState.style.display = "";
        }
        syncSuggestedPanelToggleButton();
        refreshSuggestedQuestionsForChatView();
    }

    function activateAuthView() {
        const authPanel = document.getElementById("azure-auth-panel");
        const chatContainer = document.getElementById("chat-container");
        const chatInputArea = document.getElementById("chat-input-area");
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
        setSuggestedPanelEmpty(true);
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
        const instructionsLink = document.getElementById("instructions-link");
        const downloadLink = document.getElementById("download-link");
        const testerLink = document.getElementById("tester-link");
        const authLink = document.getElementById("auth-link");
        const validateLink = document.getElementById("validate-link");
        const toggleSuggestedPanelButton = document.getElementById("toggle-suggested-panel-btn");
        const closeSuggestedPanelButton = document.getElementById("close-suggested-panel-btn");
        const chatContainer = document.getElementById("chat-container");

        if (toggleSuggestedPanelButton) {
            toggleSuggestedPanelButton.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                toggleSuggestedQuestionsPanel();
            });
        }

        if (chatContainer) {
            chatContainer.addEventListener("click", (event) => {
                const isMobile = typeof window.matchMedia === "function" && window.matchMedia("(max-width: 768px)").matches;
                if (!isMobile) {
                    return;
                }

                if (event.target && event.target.closest("#toggle-suggested-panel-btn")) {
                    return;
                }

                const mainPane = document.querySelector(".main-pane");
                if (!mainPane || mainPane.classList.contains("suggested-panel-collapsed")) {
                    return;
                }

                mainPane.classList.add("suggested-panel-collapsed");
                syncSuggestedPanelToggleButton();
            });
        }

        if (closeSuggestedPanelButton) {
            closeSuggestedPanelButton.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                const isMobile = typeof window.matchMedia === "function" && window.matchMedia("(max-width: 768px)").matches;
                if (!isMobile) {
                    return;
                }
                const mainPane = document.querySelector(".main-pane");
                if (!mainPane) {
                    return;
                }
                mainPane.classList.add("suggested-panel-collapsed");
                syncSuggestedPanelToggleButton();
            });
        }

        if (instructionsLink) {
            instructionsLink.addEventListener("click", (event) => {
                event.preventDefault();
                activateInstructionsView();
            });
        }

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
                await Promise.allSettled([loadPublishModels(), loadActivePublishLogs()]);
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

    function initializeLandingView() {
        const hasAnyExplicitView = window.location.hash && window.location.hash !== "#";
        if (hasAnyExplicitView) {
            return;
        }
        activateInstructionsView();
    }

    function setStatus(message, isError) {
        if (!els.statusMessage) {
            return;
        }
        els.statusMessage.textContent = message;
        els.statusMessage.classList.toggle("error", Boolean(isError));
    }

    function syncPublishReadyLabelWithTranslations() {
        if (!els.publishStatus) {
            return;
        }
        const current = String(els.publishStatus.textContent || "").trim();
        if (current === "" || current === "Pret." || current === "Prêt." || current === "Ready.") {
            setPublishStatus(tr("publish.status.ready", "Prêt."), false);
        }
    }

    function bindConfigLanguageSync() {
        window.addEventListener("nutrifaq:language-updated", () => {
            applyPublishTranslations();
            syncPublishReadyLabelWithTranslations();
        });
    }

    function ensurePublishDefaults() {
        setPublishStatus(tr("publish.status.ready", "Prêt."), false);
        setPublishControlsDisabled(false);
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
                option.dataset.provider = String(model.provider || "azure");
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

    function renderQuestionLogs(entries) {
        if (!els.publishLogsList) {
            return;
        }

        const renderLogMarkdown = (value) => {
            const text = String(value || "").trim();
            if (!text) {
                return `<p>${escapeHtml(tr("publish.logs.responseMissing", "Reponse non disponible."))}</p>`;
            }
            if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
                return DOMPurify.sanitize(marked.parse(text), { ADD_ATTR: ["target"] });
            }
            const escaped = escapeHtml(text).replace(/\n/g, "<br>");
            return `<p>${escaped}</p>`;
        };

        if (!Array.isArray(entries) || !entries.length) {
            els.publishLogsList.innerHTML = `<p class="publish-log-empty">${escapeHtml(tr("publish.logs.questionsEmpty", "Aucun log de questions disponible."))}</p>`;
            return;
        }

        const rows = entries.slice().reverse().map((entry) => {
            const timestampRaw = String(entry.timestamp || "-");
            const modelRaw = String(entry.model_used || entry.model || tr("publish.logs.modelUnknown", "inconnu"));
            const questionText = String(entry.question || "").trim();
            const responseText = String(entry.response || "").trim();
            const comments = Array.isArray(entry.comments)
                ? entry.comments
                    .map((item) => (item && typeof item.comment === "string" ? item.comment.trim() : ""))
                    .filter(Boolean)
                : [];
            const likeValue = entry.likes && typeof entry.likes.like === "boolean" ? entry.likes.like : null;

            const likeLabel = likeValue === true
                ? tr("messages.like", "Like")
                : likeValue === false
                    ? tr("messages.dislike", "Dislike")
                    : tr("publish.logs.noVote", "Aucun vote");

            const questionHtml = questionText ? escapeHtml(questionText) : escapeHtml(tr("publish.logs.questionMissing", "Question non disponible."));
            const responseFullText = responseText || tr("publish.logs.responseMissing", "Reponse non disponible.");
            const responseFullHtml = renderLogMarkdown(responseFullText);
            const commentsHtml = comments.map((commentText) => {
                return `
                    <div class="publish-log-block">
                        <p class="publish-log-label">${escapeHtml(tr("messages.comment", "Commentaire"))}</p>
                        <div class="publish-log-response markdown">${renderLogMarkdown(commentText)}</div>
                    </div>
                `;
            }).join("");

            return `
                <article class="publish-log-item">
                    <div class="publish-log-meta">
                        <span><strong>${escapeHtml(tr("publish.logs.dateLabel", "Date"))}:</strong> ${escapeHtml(formatDate(timestampRaw))}</span>
                        <span><strong>${escapeHtml(tr("publish.logs.modelLabel", "Modèle"))}:</strong> ${escapeHtml(modelRaw)}</span>
                        <span><strong>${escapeHtml(tr("publish.logs.voteLabel", "Vote"))}:</strong> ${escapeHtml(likeLabel)}</span>
                    </div>
                    <div class="publish-log-block">
                        <p class="publish-log-label">${escapeHtml(tr("publish.logs.questionLabel", "Question"))}</p>
                        <p class="publish-log-question">${questionHtml}</p>
                    </div>
                    <div class="publish-log-block publish-log-answer-block">
                        <p class="publish-log-label">${escapeHtml(tr("publish.logs.responseLabel", "Réponse"))}</p>
                        <div class="publish-log-response markdown">${responseFullHtml}</div>
                    </div>
                    ${commentsHtml}
                </article>
            `;
        });

        els.publishLogsList.innerHTML = rows.join("");
    }

    async function loadQuestionLogs() {
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
            const entries = Array.isArray(data) ? data : [];
            renderQuestionLogs(entries);
        } catch (error) {
            els.publishLogsList.innerHTML = `<p class="publish-log-empty">${escapeHtml(tr("publish.logs.questionsError", "Erreur de chargement des logs de questions : {error}", { error: error.message }))}</p>`;
        }
    }

    function renderPublishLogs(logs) {
        if (!els.publishLogsList) {
            return;
        }

        if (!Array.isArray(logs) || !logs.length) {
            els.publishLogsList.innerHTML = `<p class="publish-log-empty">${escapeHtml(tr("publish.logs.publishEmpty", "Aucun log de publication disponible."))}</p>`;
            return;
        }

        const rows = logs.slice().reverse().map((entry, index) => {
            const timestampRaw = String(entry.timestamp || "-");
            const modelRaw = String(entry.model_used || entry.model || tr("publish.logs.modelUnknown", "inconnu"));
            const providerRaw = String(entry.provider_used || entry.provider || tr("publish.logs.providerUnknown", "inconnu"));
            const filesCountRaw = Number(entry.files_count || 0);

            const ts = escapeHtml(formatDate(timestampRaw));
            const model = escapeHtml(modelRaw);
            const provider = escapeHtml(providerRaw);
            const filesCount = Number.isFinite(filesCountRaw) ? filesCountRaw : 0;

            return `
                <article class="publish-log-item">
                    <div class="publish-log-meta">
                        <span><strong>${escapeHtml(tr("publish.logs.dateLabel", "Date"))}:</strong> ${ts}</span>
                        <span><strong>${escapeHtml(tr("publish.logs.providerLabel", "Fournisseur"))}:</strong> ${provider}</span>
                        <span><strong>${escapeHtml(tr("publish.logs.modelLabel", "Modèle"))}:</strong> ${model}</span>
                        <span><strong>${escapeHtml(tr("publish.logs.filesLabel", "Fichiers"))}:</strong> ${filesCount}</span>
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
            const data = await fetchJson(`${BACKEND_URL}/api/publish/log`, {
                headers: {
                    ...authHeaders()
                }
            });
            const entries = data && Array.isArray(data.entries) ? data.entries : [];
            renderPublishLogs(entries);
        } catch (error) {
            els.publishLogsList.innerHTML = `<p class="publish-log-empty">${escapeHtml(tr("publish.logs.publishError", "Erreur de chargement des logs de publication : {error}", { error: error.message }))}</p>`;
        }
    }

    async function loadActivePublishLogs() {
        if (activePublishLogsTab === LOGS_TAB_PUBLISH) {
            await loadPublishLogs();
            return;
        }
        await loadQuestionLogs();
    }

    let publishStatusTimer = null;

    function startPublishStatusPolling() {
        if (publishStatusTimer) {
            window.clearInterval(publishStatusTimer);
        }

        const poll = async () => {
            try {
                const data = await fetchJson(`${BACKEND_URL}/api/publish/status`, {
                    headers: {
                        ...authHeaders()
                    }
                });
                const progress = Number(data.progress || 0);
                const running = Boolean(data.running);
                const message = data.message || "";
                const messageKey = typeof data.message_key === "string" && data.message_key.trim() ? data.message_key : null;

                setPublishControlsDisabled(running);

                if (running || progress > 0) {
                    setPublishProgress(progress, `${Math.round(progress)}%`);
                    if (message || messageKey) {
                        setPublishStatus(localizeMessageWithKey(messageKey, message || tr("publish.status.inProgress", "Publication en cours...")), false);
                    }
                }

                if (!running && data.status === "completed") {
                    setPublishControlsDisabled(false);
                    const filesCount = Number(data.uploaded_files_count || 0);
                    const timestamp = new Date().toLocaleString();
                    const operation = String(data.operation || "publish");
                    if (operation === "revert") {
                        const finishedText = localizeMessageWithKey(
                            "publish.revert.done",
                            "Restore completed ({count} files): {timestamp}",
                            { count: filesCount, timestamp }
                        );
                        setPublishStatus(finishedText, false);
                    } else {
                        const finishedText = localizeMessageWithKey(
                            "publish.status.completed",
                            "Publication completed ({count} files): {timestamp}",
                            { count: filesCount, timestamp }
                        );
                        setPublishStatus(finishedText, false);
                        showAlertMessage(
                            tr(
                                "publish.popup.completedText",
                                "Publication terminee avec succes ({count} fichiers).",
                                { count: filesCount }
                            ),
                            false
                        );
                    }
                    setPublishProgress(100, "100%");
                    setPublishFinishMessage("");
                    window.clearInterval(publishStatusTimer);
                    publishStatusTimer = null;
                    await loadActivePublishLogs();
                    return;
                }

                if (!running && data.status === "error") {
                    setPublishControlsDisabled(false);
                    const operation = String(data.operation || "publish");
                    const defaultError = operation === "revert" ? tr("publish.revert.error", "Restore failed.") : tr("publish.status.error", "Publication failed.");
                    const errorKey = typeof data.error_key === "string" && data.error_key.trim() ? data.error_key : (operation === "revert" ? "publish.revert.error" : "publish.status.error");
                    setPublishStatus(localizeMessageWithKey(errorKey, data.error || defaultError), true);
                    setPublishFinishMessage("");
                    setPublishProgress(100, "100%");
                    window.clearInterval(publishStatusTimer);
                    publishStatusTimer = null;
                    await loadActivePublishLogs();
                    return;
                }
            } catch (_) {
                // Ignore transient polling errors while publish is running.
            }
        };

        poll();
        publishStatusTimer = window.setInterval(poll, 1500);
    }

    async function onPublishSubmit() {
        const selectedModel = els.publishModelSelector ? String(els.publishModelSelector.value || "").trim() : "";
        const selectedOption = els.publishModelSelector && els.publishModelSelector.selectedOptions
            ? els.publishModelSelector.selectedOptions[0]
            : null;
        const selectedProvider = selectedOption ? String(selectedOption.dataset.provider || "azure") : "azure";

        if (!selectedModel) {
            setPublishStatus(tr("publish.status.modelRequired", "Veuillez selectionner un modele."), true);
            return;
        }

        const confirmed = await confirmAction({
            title: tr("publish.confirm.title", "Confirmer la publication ?"),
            text: tr("publish.confirm.warning", "Attention: une fois lancee, la publication ne peut pas etre annulee pendant son execution."),
            confirmText: tr("publish.confirm.action", "Publier"),
        });

        if (!confirmed) {
            return;
        }

        setPublishProgress(5, "5%")
        setPublishStatus(tr("publish.status.inProgress", "Publication en cours..."), false);
        setPublishFinishMessage("");
        setPublishControlsDisabled(true);

        try {
            const body = {
                model: selectedModel,
                provider: selectedProvider,
            };

            const response = await fetch(`${BACKEND_URL}/api/publish`, {
                method: "POST",
                headers: {
                    ...authHeaders(),
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(body),
            });

            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                const defaultError = tr("publish.status.error", "Publication failed.");
                const messageKey = typeof payload.message_key === "string" && payload.message_key.trim() ? payload.message_key : "publish.status.error";
                throw new Error(localizeMessageWithKey(messageKey, payload.detail || payload.message || response.statusText || defaultError));
            }

            startPublishStatusPolling();
        } catch (error) {
            const message = error && error.message ? error.message : tr("publish.status.error", "Publication failed.");
            setPublishStatus(message, true);
            setPublishFinishMessage("");
            hidePublishProgress();
            setPublishControlsDisabled(false);
        }
    }

    async function onRevertSubmit() {
        const confirmed = await confirmAction({
            title: tr("publish.revert.title", "Confirmer la restauration ?"),
            text: tr("publish.revert.warning", "Attention : la restauration remplacera la base principale par la version precedente."),
            confirmText: tr("publish.revert.action", "Rétablir"),
        });

        if (!confirmed) {
            return;
        }

        setPublishProgress(5, "5%");
        setPublishStatus(tr("publish.revert.inProgress", "Restauration en cours..."), false);
        setPublishFinishMessage("");
        setPublishControlsDisabled(true);

        try {
            const response = await fetch(`${BACKEND_URL}/api/publish/revert`, {
                method: "POST",
                headers: {
                    ...authHeaders(),
                    "Content-Type": "application/json",
                },
            });

            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                const defaultError = tr("publish.revert.error", "Restore failed.");
                const messageKey = typeof payload.message_key === "string" && payload.message_key.trim() ? payload.message_key : "publish.revert.error";
                throw new Error(localizeMessageWithKey(messageKey, payload.detail || payload.message || response.statusText || defaultError));
            }

            startPublishStatusPolling();
        } catch (error) {
            const message = error && error.message ? error.message : tr("publish.revert.error", "Restore failed.");
            setPublishStatus(message, true);
            setPublishFinishMessage("");
            hidePublishProgress();
            setPublishControlsDisabled(false);
        }
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
                        <button class="dm-btn table-action" data-action="download" data-name="${encodeURIComponent(blobName)}">${escapeHtml(tr("downloadManager.table.download", "Indexer"))}</button>
                        <button class="dm-btn table-action danger" data-action="delete" data-name="${encodeURIComponent(blobName)}">${escapeHtml(tr("downloadManager.table.delete", "Supprimer"))}</button>
                    </td>
                </tr>
            `;
        });

        els.filesTbody.innerHTML = rows.join("");
    }

    function setFilesFoundStatus(count) {
        setStatus(tr("downloadManager.status.filesFound", "{count} fichier(s) trouvé(s).", {
            count: Number(count || 0),
            container: tr("downloadManager.status.defaultContainer", "le conteneur")
        }), false);
    }

    function upsertLocalFileEntry(file) {
        if (!file) {
            return;
        }

        const blobName = file.blob_name || file.name || "";
        if (!blobName) {
            return;
        }

        const normalized = {
            ...file,
            name: blobName,
            blob_name: blobName,
            filename: file.filename || blobName.split("/").pop() || "-",
            size: Number(file.size_bytes ?? file.size ?? 0),
            last_modified: file.last_modified || new Date().toISOString(),
        };

        const index = currentFiles.findIndex((entry) => {
            const entryName = entry.blob_name || entry.name || "";
            return entryName === blobName;
        });

        if (index >= 0) {
            currentFiles[index] = normalized;
        } else {
            currentFiles.push(normalized);
        }
    }

    function removeLocalFileEntry(blobName) {
        if (!blobName) {
            return false;
        }

        const before = currentFiles.length;
        currentFiles = currentFiles.filter((entry) => {
            const entryName = entry.blob_name || entry.name || "";
            return entryName !== blobName;
        });
        return currentFiles.length < before;
    }

    function refreshLocalFilesTable() {
        renderRows(currentFiles);
        setFilesFoundStatus(currentFiles.length);
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
            currentFiles = Array.isArray(data.files) ? data.files : [];
            refreshLocalFilesTable();
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
            const removed = removeLocalFileEntry(blobName);
            if (removed) {
                refreshLocalFilesTable();
            } else {
                await loadFiles();
            }
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

            const resolvedBlobName = payload.blob_name || blobName;
            upsertLocalFileEntry({
                blob_name: resolvedBlobName,
                name: resolvedBlobName,
                filename: safeFileName,
                size: Number(inputFile.size || 0),
                last_modified: new Date().toISOString(),
            });
            refreshLocalFilesTable();

            setStatus(tr("downloadManager.status.uploaded", "Fichier téléversé: {name}", { name: resolvedBlobName }), false);
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

        const handleSelectedFiles = async (files) => {
            const selectedFiles = Array.from(files || []).filter(Boolean);
            if (selectedFiles.length === 0) {
                return;
            }

            if (els.fileName) {
                if (selectedFiles.length === 1) {
                    els.fileName.textContent = tr("downloadManager.status.fileSelected", "Fichier sélectionné: {name}", { name: selectedFiles[0].name });
                } else {
                    els.fileName.textContent = tr(
                        "downloadManager.status.filesSelected",
                        "{count} fichiers sélectionnés.",
                        { count: selectedFiles.length }
                    );
                }
            }

            for (const file of selectedFiles) {
                await uploadFile(file);
            }

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
            const files = event.dataTransfer && event.dataTransfer.files ? event.dataTransfer.files : [];
            await handleSelectedFiles(files);
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
            const files = event.target && event.target.files ? event.target.files : [];
            await handleSelectedFiles(files);
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
        bindConfigLanguageSync();
        initializeLandingView();

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
