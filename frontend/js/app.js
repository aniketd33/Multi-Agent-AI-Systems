
// =============================================================================
// FinSight AI + Document Intelligence Agent + Red Flag Agent
// =============================================================================
// Existing features preserved:
// - JWT authentication and dashboard session protection
// - User greeting and profile
// - Logout and theme toggle
// - Dashboard date and year
// - FinSight PDF inspection (/documents/inspect)
// - Document Agent upload (PDF / DOCX / TXT)
// - Document listing and status polling
// - Document deletion
//
// Red Flag Agent features:
// - Populate document dropdown
// - Retrieve existing red-flag analysis
// - Display summary counts
// - Display evidence-backed findings
// - Filter findings by severity
// =============================================================================

"use strict";

const API = "http://127.0.0.1:8001";

const DOC_AGENT_MAX_SIZE = 100 * 1024 * 1024;
const MAX_UPLOAD_SIZE = 100 * 1024 * 1024;

let isUploading = false;
let pollTimer = null;
let rfaCurrentFindings = [];

// =============================================================================
// COMMON HELPERS
// =============================================================================

function byId(id) {
    return document.getElementById(id);
}

function getToken() {
    return sessionStorage.getItem("finsight_access_token");
}

function authHeaders() {
    const token = getToken();

    return token
        ? { Authorization: "Bearer " + token }
        : {};
}

function escapeText(value) {
    return String(value == null ? "" : value);
}

// =============================================================================
// DASHBOARD DATE AND YEAR
// =============================================================================

function updateDashboardDate() {
    const now = new Date();

    const dateElement = byId("currentDate");

    if (dateElement) {
        dateElement.textContent = now.toLocaleDateString("en-US", {
            weekday: "long",
            month: "long",
            day: "numeric",
            year: "numeric"
        }).toUpperCase();
    }

    const yearElement = byId("currentYear");

    if (yearElement) {
        yearElement.textContent = now.getFullYear();
    }
}

updateDashboardDate();

// =============================================================================
// AUTHENTICATION
// =============================================================================

async function protectDashboard() {
    const token = getToken();

    if (!token) {
        window.location.replace("login.html");
        return;
    }

    try {
        const response = await fetch(API + "/auth/me", {
            headers: authHeaders()
        });

        if (!response.ok) {
            sessionStorage.removeItem("finsight_access_token");
            sessionStorage.removeItem("finsight_user");

            window.location.replace("login.html");
            return;
        }

        const user = await response.json();

        const welcome = document.querySelector(".welcome-section h1");

        if (welcome) {
            const hour = new Date().getHours();

            const greeting =
                hour < 12
                    ? "Good morning"
                    : hour < 17
                        ? "Good afternoon"
                        : "Good evening";

            welcome.replaceChildren(
                document.createTextNode(
                    greeting + ", " + user.full_name + " "
                )
            );

            const sparkle = document.createElement("span");
            sparkle.textContent = "\u2746";

            welcome.appendChild(sparkle);
        }

        const profileName = document.querySelector(".profile strong");

        if (profileName) {
            profileName.textContent = user.full_name;
        }

        const avatar = document.querySelector(".profile-avatar");

        if (avatar) {
            avatar.textContent = user.full_name
                .split(" ")
                .map(part => part[0])
                .join("")
                .substring(0, 2)
                .toUpperCase();
        }

        await loadDocuments();

    } catch (error) {
        console.error("Authentication error:", error);

        alert(
            "Unable to connect to the backend. Please try again."
        );
    }
}

// =============================================================================
// LOGOUT
// =============================================================================

const logoutButton = byId("logoutButton");

if (logoutButton) {
    logoutButton.addEventListener("click", function () {
        sessionStorage.removeItem("finsight_access_token");
        sessionStorage.removeItem("finsight_user");

        window.location.replace("login.html");
    });
}

// =============================================================================
// THEME
// =============================================================================

const themeToggle = byId("themeToggle");

if (themeToggle) {
    if (localStorage.getItem("finsight-theme") === "dark") {
        document.body.classList.add("dark");
        themeToggle.textContent = "\u2600";
    }

    themeToggle.addEventListener("click", function () {
        document.body.classList.toggle("dark");

        const isDark = document.body.classList.contains("dark");

        themeToggle.textContent = isDark
            ? "\u2600"
            : "\u263e";

        localStorage.setItem(
            "finsight-theme",
            isDark ? "dark" : "light"
        );
    });
}

// =============================================================================
// RESULT PANEL
// =============================================================================

function getResultPanel() {
    let panel = byId("documentResult");

    const dropZone = byId("dropZone");

    if (!panel && dropZone) {
        panel = document.createElement("div");

        panel.id = "documentResult";

        panel.style.cssText =
            "margin-top:20px;padding:18px;" +
            "border:1px solid #dce8e2;" +
            "border-radius:12px;" +
            "background:#f8fcf9;" +
            "color:#263b31;" +
            "display:none;line-height:1.6;";

        dropZone.insertAdjacentElement("afterend", panel);
    }

    return panel;
}

function showStatus(message, type = "info") {
    const panel = getResultPanel();

    if (!panel) {
        console.log(message);
        return;
    }

    panel.style.display = "block";
    panel.replaceChildren();

    const colors = {
        info: "#2563eb",
        success: "#16865c",
        error: "#dc2626"
    };

    const heading = document.createElement("strong");

    heading.textContent = message;
    heading.style.color = colors[type] || colors.info;

    panel.appendChild(heading);
}

// =============================================================================
// FINSIGHT PDF INSPECTION
// =============================================================================

function showDocumentResult(data) {
    const panel = getResultPanel();

    if (!panel) return;

    panel.style.display = "block";
    panel.replaceChildren();

    const heading = document.createElement("h3");
    heading.textContent = "Document processed successfully";
    heading.style.color = "#16865c";

    const filename = document.createElement("p");
    filename.textContent =
        "File: " + (data.filename || "Uploaded PDF");

    const pages = document.createElement("p");
    pages.textContent = "Total Pages: " + data.pages;

    const characters = document.createElement("p");
    characters.textContent =
        "Extracted Characters: " + data.characters_extracted;

    const message = document.createElement("p");
    message.textContent =
        data.message || "Text extraction completed.";

    const previewHeading = document.createElement("h4");
    previewHeading.textContent = "Extracted Text Preview";

    const preview = document.createElement("pre");

    preview.textContent =
        data.text_preview ||
        "No readable text found in this PDF.";

    preview.style.cssText =
        "white-space:pre-wrap;overflow-wrap:anywhere;" +
        "max-height:350px;overflow-y:auto;padding:14px;" +
        "background:#ffffff;border:1px solid #dce8e2;" +
        "border-radius:8px;font-size:13px;color:#263b31;";

    panel.append(
        heading,
        filename,
        pages,
        characters,
        message,
        previewHeading,
        preview
    );

    panel.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
    });
}

async function uploadPDF(file) {
    if (!file || isUploading) return;

    const token = getToken();

    if (!token) {
        alert("Your session has expired. Please sign in again.");
        window.location.replace("login.html");
        return;
    }

    isUploading = true;

    const uploadButton = byId("uploadButton");

    if (uploadButton) {
        uploadButton.disabled = true;
        uploadButton.textContent = "Processing...";
    }

    showStatus("Uploading and extracting your PDF. Please wait...");

    try {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(API + "/documents/inspect", {
            method: "POST",
            headers: authHeaders(),
            body: formData
        });

        const data = await response.json();

        if (response.status === 401) {
            sessionStorage.removeItem("finsight_access_token");
            sessionStorage.removeItem("finsight_user");

            window.location.replace("login.html");
            return;
        }

        if (!response.ok) {
            throw new Error(
                data.detail || "Document processing failed."
            );
        }

        showDocumentResult(data);

    } catch (error) {
        console.error("PDF inspection error:", error);

        showStatus(
            error.message || "Unable to process the document.",
            "error"
        );

    } finally {
        isUploading = false;

        if (uploadButton) {
            uploadButton.disabled = false;
            uploadButton.textContent = "\uff0b Upload document";
        }
    }
}

// =============================================================================
// DOCUMENT AGENT FILE VALIDATION
// =============================================================================

function validateDocAgentFile(file) {
    const allowed = ["pdf", "docx", "txt"];

    const extension = file.name
        .split(".")
        .pop()
        .toLowerCase();

    if (!allowed.includes(extension)) {
        return (
            "Unsupported file type: ." +
            extension +
            ". Please upload PDF, DOCX or TXT."
        );
    }

    if (file.size === 0) {
        return "File is empty. Please select a non-empty file.";
    }

    if (file.size > DOC_AGENT_MAX_SIZE) {
        const size = (file.size / (1024 * 1024)).toFixed(1);

        return (
            "File too large (" +
            size +
            " MB). Maximum allowed: 100 MB."
        );
    }

    return null;
}

// =============================================================================
// DOCUMENT AGENT UPLOAD
// =============================================================================

async function uploadDocumentAgent(file) {
    if (!file || isUploading) return;

    const validationError = validateDocAgentFile(file);

    if (validationError) {
        showStatus(validationError, "error");
        return;
    }

    isUploading = true;

    const uploadButton = byId("uploadButton");
    const fileInput = byId("fileInput");

    if (uploadButton) {
        uploadButton.disabled = true;
        uploadButton.textContent = "Uploading...";
    }

    showStatus("Uploading document...", "info");

    try {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(
            API + "/api/documents/upload",
            {
                method: "POST",
                headers: authHeaders(),
                body: formData
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                "Upload failed."
            );
        }

        const doc = data.document || {};

        const filename = doc.filename || file.name;

        showStatus(
            '"' + filename + '" uploaded successfully.',
            "success"
        );

        await loadDocuments();

        if (doc.document_id) {
            pollDocumentStatus(
                doc.document_id,
                filename
            );
        }

    } catch (error) {
        console.error("Document Agent upload error:", error);

        showStatus(
            error.message || "Upload failed. Please try again.",
            "error"
        );

    } finally {
        isUploading = false;

        if (uploadButton) {
            uploadButton.disabled = false;
            uploadButton.textContent = "\uff0b Upload document";
        }

        if (fileInput) {
            fileInput.value = "";
        }
    }
}

// =============================================================================
// STATUS POLLING
// =============================================================================

function pollDocumentStatus(documentId, filename) {
    if (pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
    }

    let attempts = 0;

    const maxAttempts = 60;

    async function checkOnce() {
        attempts++;

        try {
            const response = await fetch(
                API + "/api/documents/" +
                encodeURIComponent(documentId),
                {
                    headers: authHeaders()
                }
            );

            if (!response.ok) {
                throw new Error("Unable to retrieve document status.");
            }

            const data = await response.json();

            const doc = data.document || data;

            if (!doc) return;

            const status = doc.status;

            await loadDocuments();

            if (status === "indexed") {
                pollTimer = null;

                showStatus(
                    '"' + filename + '" indexed successfully.',
                    "success"
                );

                return;
            }

            if (status === "failed") {
                pollTimer = null;

                showStatus(
                    '"' + filename + '" processing failed. See server logs.',
                    "error"
                );

                return;
            }

            if (
                status === "uploaded" ||
                status === "processing"
            ) {
                if (attempts < maxAttempts) {
                    pollTimer = setTimeout(checkOnce, 2000);
                } else {
                    pollTimer = null;

                    showStatus(
                        '"' + filename +
                        '" is still processing. Refresh later to check.',
                        "info"
                    );
                }
            }

        } catch (error) {
            console.error("Polling error:", error);

            if (attempts < maxAttempts) {
                pollTimer = setTimeout(checkOnce, 2000);
            } else {
                pollTimer = null;
            }
        }
    }

    pollTimer = setTimeout(checkOnce, 2000);
}

// =============================================================================
// FILE INPUT AND DRAG/DROP
// =============================================================================

const fileInput = byId("fileInput");
const browseButton = byId("browseButton");
const uploadButton = byId("uploadButton");
const dropZone = byId("dropZone");

if (browseButton && fileInput) {
    browseButton.addEventListener("click", function (event) {
        event.preventDefault();
        fileInput.click();
    });
}

if (uploadButton && fileInput) {
    uploadButton.addEventListener("click", function () {
        if (!isUploading) {
            fileInput.click();
        }
    });
}

if (fileInput) {
    fileInput.addEventListener("change", function () {
        const file = fileInput.files[0];

        if (file) {
            uploadDocumentAgent(file);
        }
    });
}

if (dropZone) {
    dropZone.addEventListener("dragover", function (event) {
        event.preventDefault();
        dropZone.style.borderColor = "#16865c";
    });

    dropZone.addEventListener("dragleave", function () {
        dropZone.style.borderColor = "";
    });

    dropZone.addEventListener("drop", function (event) {
        event.preventDefault();

        dropZone.style.borderColor = "";

        const file = event.dataTransfer.files[0];

        if (!file) return;

        if (fileInput) {
            const dataTransfer = new DataTransfer();

            dataTransfer.items.add(file);
            fileInput.files = dataTransfer.files;
        }

        uploadDocumentAgent(file);
    });
}

// =============================================================================
// RECENT DOCUMENTS TABLE
// =============================================================================

function getRecentTableBody() {
    const panel = document.querySelector(".recent-panel");

    return panel
        ? panel.querySelector("tbody")
        : null;
}

function ensureActionColumn() {
    const panel = document.querySelector(".recent-panel");

    if (!panel) return;

    const headerRow = panel.querySelector("thead tr");

    if (!headerRow || headerRow.querySelector("th.action-col")) {
        return;
    }

    const header = document.createElement("th");

    header.textContent = "ACTION";
    header.className = "action-col";

    headerRow.appendChild(header);
}

function statusDisplay(status) {
    const statuses = {
        uploaded: {
            cls: "status-badge status-uploaded",
            label: "Uploaded"
        },
        processing: {
            cls: "status-badge status-processing",
            label: "Processing"
        },
        indexed: {
            cls: "status-badge status-indexed",
            label: "Indexed"
        },
        failed: {
            cls: "status-badge status-failed",
            label: "Failed"
        }
    };

    return statuses[status] || {
        cls: "status-badge status-uploaded",
        label: status || "Unknown"
    };
}

function formatDate(value) {
    if (!value) return "\u2014";

    const date = new Date(
        String(value).replace(" ", "T")
    );

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric"
    });
}

function updateDocumentCount(count) {
    const countElement = byId("statDocCount");
    const subElement = byId("statDocSub");

    if (countElement) {
        countElement.textContent = count;
    }

    if (subElement) {
        subElement.textContent =
            count === 0
                ? "No documents yet"
                : count + (
                    count === 1
                        ? " document in the system"
                        : " documents in the system"
                );
    }
}

// =============================================================================
// LOAD DOCUMENTS
// =============================================================================

async function loadDocuments() {
    const tbody = getRecentTableBody();

    if (!tbody) {
        await loadDocumentDropdown();
        return;
    }

    ensureActionColumn();

    tbody.replaceChildren();

    const loadingRow = document.createElement("tr");
    const loadingCell = document.createElement("td");

    loadingCell.colSpan = 5;
    loadingCell.textContent = "Loading documents...";
    loadingCell.style.textAlign = "center";
    loadingCell.style.padding = "20px";

    loadingRow.appendChild(loadingCell);
    tbody.appendChild(loadingRow);

    try {
        const response = await fetch(
            API + "/api/documents/",
            {
                headers: authHeaders()
            }
        );

        if (!response.ok) {
            throw new Error(
                "Server returned " + response.status
            );
        }

        const payload = await response.json();

        const documents = Array.isArray(payload.documents)
            ? payload.documents
            : [];

        updateDocumentCount(
            typeof payload.count === "number"
                ? payload.count
                : documents.length
        );

        tbody.replaceChildren();

        if (documents.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");

            cell.colSpan = 5;
            cell.textContent = "No documents uploaded yet.";
            cell.style.textAlign = "center";
            cell.style.padding = "30px";

            row.appendChild(cell);
            tbody.appendChild(row);
        }

        documents.forEach(doc => {
            const row = document.createElement("tr");

            const documentCell = document.createElement("td");

            const fileBadge = document.createElement("span");

            fileBadge.className = "pdf-icon";
            fileBadge.textContent = escapeText(doc.file_type);

            documentCell.append(
                fileBadge,
                document.createTextNode(
                    " " + escapeText(doc.filename)
                )
            );

            const typeCell = document.createElement("td");
            typeCell.textContent = escapeText(doc.file_type);

            const dateCell = document.createElement("td");
            dateCell.textContent = formatDate(doc.upload_date);

            const statusCell = document.createElement("td");

            const status = statusDisplay(doc.status);

            const statusBadge = document.createElement("span");

            statusBadge.className = status.cls;
            statusBadge.textContent = status.label;

            statusCell.appendChild(statusBadge);

            const actionCell = document.createElement("td");

            const deleteButton = document.createElement("button");

            deleteButton.type = "button";
            deleteButton.className = "delete-btn";
            deleteButton.textContent = "Delete";

            deleteButton.dataset.docId = doc.document_id;
            deleteButton.dataset.docFilename = doc.filename || "this document";

            deleteButton.addEventListener(
                "click",
                handleDeleteDocument
            );

            actionCell.appendChild(deleteButton);

            row.append(
                documentCell,
                typeCell,
                dateCell,
                statusCell,
                actionCell
            );

            tbody.appendChild(row);
        });

        // Keep Red Flag document dropdown synchronized.
        await loadDocumentDropdown(documents);

    } catch (error) {
        console.error("Failed to load documents:", error);

        tbody.replaceChildren();

        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 5;
        cell.textContent =
            "Unable to load documents. Is the backend running?";

        cell.style.textAlign = "center";
        cell.style.color = "#dc2626";
        cell.style.padding = "20px";

        row.appendChild(cell);
        tbody.appendChild(row);

        updateDocumentCount(0);

        await loadDocumentDropdown([]);
    }
}

// =============================================================================
// DELETE DOCUMENT
// =============================================================================

async function handleDeleteDocument(event) {
    const button = event.currentTarget;

    const documentId = button.dataset.docId;
    const filename = button.dataset.docFilename;

    if (!confirm(
        'Delete "' + filename + '"? This cannot be undone.'
    )) {
        return;
    }

    button.disabled = true;
    button.textContent = "Deleting...";

    try {
        const response = await fetch(
            API + "/api/documents/" +
            encodeURIComponent(documentId),
            {
                method: "DELETE",
                headers: authHeaders()
            }
        );

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));

            throw new Error(
                data.detail ||
                data.message ||
                "Document deletion failed."
            );
        }

        showStatus(
            '"' + filename + '" deleted successfully.',
            "success"
        );

        await loadDocuments();

    } catch (error) {
        console.error("Delete error:", error);

        button.disabled = false;
        button.textContent = "Delete";

        showStatus(
            error.message || "Deletion failed.",
            "error"
        );
    }
}

// =============================================================================
// RED FLAG AGENT - STATUS
// =============================================================================

function rfaSetStatus(message, type = "info") {
    const status = byId("rfaStatus");

    if (!status) return;

    status.textContent = message || "";

    status.className = "rfa-status rfa-" + type;

    status.style.display = message
        ? "inline-block"
        : "none";
}

// =============================================================================
// RED FLAG AGENT - DOCUMENT DROPDOWN
// =============================================================================

async function loadDocumentDropdown(existingDocuments) {
    const select = byId("rfaDocSelect");

    if (!select) return;

    try {
        let documents = existingDocuments;

        if (!Array.isArray(documents)) {
            const response = await fetch(
                API + "/api/documents/",
                {
                    headers: authHeaders()
                }
            );

            if (!response.ok) {
                throw new Error(
                    "Unable to retrieve uploaded documents."
                );
            }

            const payload = await response.json();

            documents = Array.isArray(payload.documents)
                ? payload.documents
                : [];
        }

        const previousValue = select.value;

        select.replaceChildren();

        const placeholder = document.createElement("option");

        placeholder.value = "";

        placeholder.textContent = documents.length
            ? "-- Select an uploaded document --"
            : "No uploaded documents found";

        select.appendChild(placeholder);

        documents.forEach(doc => {
            if (!doc.document_id) return;

            const option = document.createElement("option");

            option.value = doc.document_id;

            option.textContent =
                (doc.filename || "Untitled document") +
                " · " +
                (doc.status || "unknown");

            select.appendChild(option);
        });

        select.disabled = documents.length === 0;

        if (
            previousValue &&
            documents.some(
                doc => doc.document_id === previousValue
            )
        ) {
            select.value = previousValue;
        }

    } catch (error) {
        console.error("Red Flag dropdown error:", error);

        select.replaceChildren();

        const option = document.createElement("option");

        option.value = "";
        option.textContent = "Unable to load documents";

        select.appendChild(option);

        select.disabled = true;

        rfaSetStatus(error.message, "error");
    }
}

// =============================================================================
// RED FLAG AGENT - SUMMARY CARDS
// =============================================================================

function rfaCreateCountCard(label, count) {
    const card = document.createElement("article");

    card.className = "stat-card";

    const heading = document.createElement("div");

    heading.className = "stat-heading";
    heading.textContent = label;

    const value = document.createElement("h2");

    value.textContent = String(count);

    card.append(heading, value);

    return card;
}

function rfaRenderCounts(summary) {
    const container = byId("rfaCounts");

    if (!container) return;

    container.replaceChildren();

    const counts = [
        ["Total Findings", summary.total || 0],
        ["Critical", summary.critical || 0],
        ["High", summary.high || 0],
        ["Medium", summary.medium || 0],
        ["Low", summary.low || 0]
    ];

    counts.forEach(([label, count]) => {
        container.appendChild(
            rfaCreateCountCard(label, count)
        );
    });
}

// =============================================================================
// RED FLAG AGENT - FILTERED FINDINGS
// =============================================================================

function rfaRenderFilteredFindings() {
    const list = byId("rfaFlagList");
    const filter = byId("rfaSeverityFilter");

    if (!list) return;

    list.replaceChildren();

    const selected = filter
        ? filter.value
        : "all";

    const findings = rfaCurrentFindings.filter(finding => {
        const severity = String(
            finding.severity || "low"
        ).toLowerCase();

        return (
            selected === "all" ||
            severity === selected
        );
    });

    if (findings.length === 0) {
        const empty = document.createElement("div");

        empty.className = "rfa-empty";

        empty.textContent = rfaCurrentFindings.length
            ? "No findings match this severity filter."
            : "No matching red-flag patterns were detected.";

        list.appendChild(empty);

        return;
    }

    findings.forEach(finding => {
        let severity = String(
            finding.severity || "low"
        ).toLowerCase();

        if (
            !["critical", "high", "medium", "low"].includes(severity)
        ) {
            severity = "low";
        }

        const card = document.createElement("article");

        card.className = "rfa-flag-card sev-" + severity;

        const titleRow = document.createElement("div");

        titleRow.className = "rfa-flag-title";

        const title = document.createElement("span");

        title.textContent =
            finding.title || "Risk signal detected";

        const badge = document.createElement("span");

        badge.className = "rfa-sev-badge";
        badge.textContent = severity.toUpperCase();

        titleRow.append(title, badge);

        const category = document.createElement("div");

        category.className = "rfa-category";

        category.textContent = String(
            finding.category || "Financial risk"
        ).replace(/_/g, " ");

        const description = document.createElement("p");

        description.className = "rfa-flag-desc";

        description.textContent =
            finding.explanation ||
            "Potential risk signal identified.";

        card.append(
            titleRow,
            category,
            description
        );

        if (finding.evidence) {
            const evidence = document.createElement("div");

            evidence.className = "rfa-flag-evidence";

            evidence.textContent =
                "Evidence: " + finding.evidence;

            card.appendChild(evidence);
        }

        const meta = document.createElement("div");

        meta.className = "rfa-flag-meta";

        meta.textContent =
            "Source document page: " +
            (finding.page_number ?? "Not specified");

        card.appendChild(meta);

        if (finding.recommended_follow_up) {
            const followup = document.createElement("div");

            followup.className = "rfa-followup";

            const heading = document.createElement("strong");

            heading.textContent = "Recommended follow-up";

            const followupText = document.createElement("span");

            followupText.textContent =
                finding.recommended_follow_up;

            followup.append(heading, followupText);

            card.appendChild(followup);
        }

        list.appendChild(card);
    });
}


// =============================================================================
// RED FLAG AGENT - DISPLAY RESULTS
// =============================================================================

function rfaRenderResults(data) {
    const results = byId("rfaResults");
    const summaryBar = byId("rfaSummaryBar");

    if (!results || !summaryBar) {
        console.error(
            "Red Flag result elements are missing in index.html."
        );

        rfaSetStatus(
            "Red Flag results section is missing from the dashboard.",
            "error"
        );

        return;
    }

    rfaCurrentFindings = Array.isArray(data.findings)
        ? data.findings
        : [];

    // Calculate counts directly from findings.
    const calculatedCounts = {
        total: rfaCurrentFindings.length,
        critical: 0,
        high: 0,
        medium: 0,
        low: 0
    };

    rfaCurrentFindings.forEach(finding => {
        const severity = String(
            finding.severity || "low"
        ).trim().toLowerCase();

        if (
            Object.prototype.hasOwnProperty.call(
                calculatedCounts,
                severity
            ) &&
            severity !== "total"
        ) {
            calculatedCounts[severity]++;
        }
    });

    // Use backend summary when it contains valid severity counts.
    // Otherwise use the counts calculated from findings.
    const summary = data.summary || {};

    const hasBackendCounts = [
        "critical",
        "high",
        "medium",
        "low"
    ].some(key => Number(summary[key]) > 0);

    const counts = {
        total: Number(
            summary.total_findings ??
            summary.total ??
            calculatedCounts.total
        ),

        critical: hasBackendCounts
            ? Number(summary.critical || 0)
            : calculatedCounts.critical,

        high: hasBackendCounts
            ? Number(summary.high || 0)
            : calculatedCounts.high,

        medium: hasBackendCounts
            ? Number(summary.medium || 0)
            : calculatedCounts.medium,

        low: hasBackendCounts
            ? Number(summary.low || 0)
            : calculatedCounts.low
    };

    results.style.display = "block";

    // Severity-based summary message.
    if (counts.critical > 0) {
        summaryBar.className =
            "rfa-summary-bar rfa-danger";

        summaryBar.textContent =
            counts.critical +
            " critical finding(s) detected. Immediate review recommended.";

    } else if (counts.high > 0) {
        summaryBar.className =
            "rfa-summary-bar rfa-danger";

        summaryBar.textContent =
            counts.high +
            " high-risk finding(s) detected. Review the evidence carefully.";

    } else if (counts.medium > 0) {
        summaryBar.className =
            "rfa-summary-bar rfa-warn";

        summaryBar.textContent =
            counts.medium +
            " medium-risk finding(s) detected. Further review recommended.";

    } else if (counts.low > 0) {
        summaryBar.className =
            "rfa-summary-bar rfa-ok";

        summaryBar.textContent =
            counts.low +
            " low-risk finding(s) detected. Review the observations.";

    } else {
        summaryBar.className =
            "rfa-summary-bar rfa-ok";

        summaryBar.textContent =
            "No potential red flags detected in this analysis.";
    }

    // Render KPI cards.
    rfaRenderCounts(counts);

    // Reset severity filter.
    const filter = byId("rfaSeverityFilter");

    if (filter) {
        filter.value = "all";
    }

    // Render evidence-backed findings.
    rfaRenderFilteredFindings();

    results.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
    });
}


// =============================================================================
// RED FLAG AGENT - RETRIEVE ANALYSIS
// =============================================================================


async function runRedFlagAnalysis() {
    const select = byId("rfaDocSelect");
    const button = byId("rfaRunBtn");
    const results = byId("rfaResults");

    if (!select || !select.value) {
        rfaSetStatus(
            "Please select an uploaded document first.",
            "error"
        );
        return;
    }

    const documentId = select.value;
    const filename = select.options[select.selectedIndex]?.text || "selected document";

    const maxAttempts = 60;
    const pollInterval = 2000;

    if (button) {
        button.disabled = true;
        button.textContent = "Analyzing...";
    }

    if (results) {
        results.style.display = "none";
    }

    try {
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            rfaSetStatus(
                attempt === 1
                    ? "Document indexed. Waiting for Red Flag Agent analysis..."
                    : "Red Flag Agent is analyzing your document. Please wait...",
                "info"
            );

            const response = await fetch(
                API + "/api/documents/" +
                encodeURIComponent(documentId) +
                "/red-flags",
                {
                    method: "GET",
                    headers: {
                        ...authHeaders(),
                        Accept: "application/json"
                    }
                }
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.detail ||
                    data.message ||
                    "Unable to retrieve Red Flag analysis."
                );
            }

            const currentStatus = String(
                data.status || "pending"
            ).toLowerCase();

            if (currentStatus === "completed") {
                rfaRenderResults(data);

                rfaSetStatus(
                    "Analysis completed successfully. Risk findings are ready to view.",
                    "success"
                );

                return;
            }

            if (currentStatus === "failed") {
                throw new Error(
                    data.error ||
                    data.message ||
                    "Red Flag analysis failed."
                );
            }

            if (
                currentStatus !== "pending" &&
                currentStatus !== "running"
            ) {
                throw new Error(
                    "Unexpected analysis status: " + currentStatus
                );
            }

            if (attempt < maxAttempts) {
                await new Promise(resolve =>
                    setTimeout(resolve, pollInterval)
                );
            }
        }

        rfaSetStatus(
            "Analysis is taking longer than expected. Please try again shortly.",
            "info"
        );

    } catch (error) {
        console.error("Red Flag analysis error:", error);

        rfaSetStatus(
            error.message || "Unable to retrieve analysis.",
            "error"
        );

    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = "\u2691 View Risk Analysis";
        }
    }
}

// =============================================================================
// RED FLAG AGENT - EVENT LISTENERS
// =============================================================================

const rfaRunButton = byId("rfaRunBtn");
const rfaFilter = byId("rfaSeverityFilter");
const rfaDocumentSelect = byId("rfaDocSelect");

if (rfaRunButton) {
    rfaRunButton.addEventListener(
        "click",
        runRedFlagAnalysis
    );
}

if (rfaFilter) {
    rfaFilter.addEventListener(
        "change",
        rfaRenderFilteredFindings
    );
}

if (rfaDocumentSelect) {
    rfaDocumentSelect.addEventListener(
        "change",
        function () {
            const results = byId("rfaResults");

            if (results) {
                results.style.display = "none";
            }

            rfaCurrentFindings = [];

            rfaSetStatus("", "info");
        }
    );
}

// =============================================================================
// INITIALIZE RED FLAG AGENT
// =============================================================================

async function initializeRedFlagAnalysis() {
    if (!byId("rfaPanel")) {
        console.error(
            "Red Flag panel not found in index.html."
        );

        return;
    }

    await loadDocumentDropdown();
}

// =============================================================================
// APPLICATION INITIALIZATION
// =============================================================================

console.log(
    "FinSight AI + Document Intelligence Agent + Red Flag Agent initialized."
);

protectDashboard();
