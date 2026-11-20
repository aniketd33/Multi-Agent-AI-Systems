// =============================================================================
// FinSight AI + Document Intelligence Agent - app.js
// Merged from HEAD (FinSight) and Document Agent branch.
//
// FinSight features preserved:
//   - JWT authentication, session protection, user greeting & profile
//   - Logout, theme toggle, dashboard date/year
//   - /documents/inspect helpers (kept intact for FinSight PDF extraction)
//
// Document Agent features integrated:
//   - POST /api/documents/upload  (PDF / DOCX / TXT, 20 MB limit)
//   - GET  /api/documents/        (populates Recent Documents table)
//   - DELETE /api/documents/{id}  (delete with confirmation)
//
// HTML element IDs used (all present in resolved index.html):
//   uploadButton, browseButton, fileInput, dropZone,
//   logoutButton, themeToggle, currentDate, currentYear
// =============================================================================

const API = "http://127.0.0.1:8000";

// ---------------------------------------------------------------------------
// DASHBOARD DATE & YEAR
// ---------------------------------------------------------------------------

function updateDashboardDate() {
    const now = new Date();

    const dateEl = document.getElementById("currentDate");
    if (dateEl) {
        dateEl.textContent = now.toLocaleDateString("en-US", {
            weekday: "long", month: "long", day: "numeric", year: "numeric"
        }).toUpperCase();
    }

    const yearEl = document.getElementById("currentYear");
    if (yearEl) { yearEl.textContent = now.getFullYear(); }
}

updateDashboardDate();

// ---------------------------------------------------------------------------
// AUTHENTICATION
// ---------------------------------------------------------------------------

async function protectDashboard() {
    const token = sessionStorage.getItem("finsight_access_token");
    if (!token) { window.location.replace("login.html"); return; }

    try {
        const res = await fetch(API + "/auth/me", {
            headers: { "Authorization": "Bearer " + token }
        });

        if (!res.ok) {
            sessionStorage.removeItem("finsight_access_token");
            sessionStorage.removeItem("finsight_user");
            window.location.replace("login.html");
            return;
        }

        const user = await res.json();

        const welcome = document.querySelector(".welcome-section h1");
        if (welcome) {
            const h = new Date().getHours();
            const greeting = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
            welcome.replaceChildren(document.createTextNode(greeting + ", " + user.full_name + " "));
            const sparkle = document.createElement("span");
            sparkle.textContent = "\u2746";
            welcome.appendChild(sparkle);
        }

        const profileName = document.querySelector(".profile strong");
        if (profileName) { profileName.textContent = user.full_name; }

        const avatar = document.querySelector(".profile-avatar");
        if (avatar) {
            avatar.textContent = user.full_name
                .split(" ").map(function(p) { return p[0]; })
                .join("").substring(0, 2).toUpperCase();
        }

        // After authentication succeeds load the Document Agent table
        loadDocuments();

    } catch (err) {
        console.error("Authentication error:", err);
        alert("Unable to connect to the backend. Please try again.");
        window.location.replace("login.html");
    }
}

protectDashboard();

// ---------------------------------------------------------------------------
// LOGOUT
// ---------------------------------------------------------------------------

var logoutButton = document.getElementById("logoutButton");
if (logoutButton) {
    logoutButton.addEventListener("click", function () {
        sessionStorage.removeItem("finsight_access_token");
        sessionStorage.removeItem("finsight_user");
        window.location.replace("login.html");
    });
}

// ---------------------------------------------------------------------------
// THEME
// ---------------------------------------------------------------------------

var themeToggle = document.getElementById("themeToggle");
if (themeToggle) {
    themeToggle.addEventListener("click", function () {
        document.body.classList.toggle("dark");
        var isDark = document.body.classList.contains("dark");
        themeToggle.textContent = isDark ? "\u2600" : "\u263e";
        localStorage.setItem("finsight-theme", isDark ? "dark" : "light");
    });
    if (localStorage.getItem("finsight-theme") === "dark") {
        document.body.classList.add("dark");
        themeToggle.textContent = "\u2600";
    }
}

// ---------------------------------------------------------------------------
// UPLOAD ELEMENTS
// ---------------------------------------------------------------------------

var fileInput    = document.getElementById("fileInput");
var browseButton = document.getElementById("browseButton");
var uploadButton = document.getElementById("uploadButton");
var dropZone     = document.getElementById("dropZone");

var DOC_AGENT_MAX_SIZE = 100 * 1024 * 1024;  // 100 MB - Document Agent limit
var MAX_UPLOAD_SIZE    = 100 * 1024 * 1024;  // 100 MB - FinSight inspect limit

var isUploading = false;

// ---------------------------------------------------------------------------
// FINSIGHT RESULT PANEL  (kept intact for /documents/inspect)
// ---------------------------------------------------------------------------

function getResultPanel() {
    var panel = document.getElementById("documentResult");
    if (!panel && dropZone) {
        panel = document.createElement("div");
        panel.id = "documentResult";
        panel.style.cssText =
            "margin-top:20px;padding:18px;border:1px solid #dce8e2;" +
            "border-radius:12px;background:#f8fcf9;color:#263b31;" +
            "display:none;line-height:1.6;";
        dropZone.insertAdjacentElement("afterend", panel);
    }
    return panel;
}

function showStatus(message, type) {
    type = type || "info";
    var panel = getResultPanel();
    if (!panel) { return; }
    panel.style.display = "block";
    panel.replaceChildren();
    var colors = { info: "#2563eb", success: "#16865c", error: "#dc2626" };
    var h = document.createElement("strong");
    h.textContent = message;
    h.style.color  = colors[type] || colors.info;
    panel.appendChild(h);
}

function showDocumentResult(data) {
    var panel = getResultPanel();
    if (!panel) { return; }
    panel.style.display = "block";
    panel.replaceChildren();

    var heading = document.createElement("h3");
    heading.textContent = "Document processed successfully";
    heading.style.color = "#16865c";

    var fp = document.createElement("p");
    fp.textContent = "File: " + (data.filename || "Uploaded PDF");

    var pp = document.createElement("p");
    pp.textContent = "Total Pages: " + data.pages;

    var cp = document.createElement("p");
    cp.textContent = "Extracted Characters: " + data.characters_extracted;

    var sp = document.createElement("p");
    sp.textContent = data.message || "Text extraction completed.";

    var pt = document.createElement("h4");
    pt.textContent = "Extracted Text Preview";

    var pre = document.createElement("pre");
    pre.textContent = data.text_preview || "No readable text found in this PDF.";
    pre.style.cssText =
        "white-space:pre-wrap;overflow-wrap:anywhere;max-height:350px;" +
        "overflow-y:auto;padding:14px;background:#ffffff;" +
        "border:1px solid #dce8e2;border-radius:8px;font-size:13px;color:#263b31;";

    panel.append(heading, fp, pp, cp, sp, pt, pre);
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---------------------------------------------------------------------------
// FINSIGHT PDF INSPECTION  (kept intact, posts to /documents/inspect)
// ---------------------------------------------------------------------------

async function uploadPDF(file) {
    if (!file || isUploading) { return; }

    var token = sessionStorage.getItem("finsight_access_token");
    if (!token) {
        alert("Your session has expired. Please sign in again.");
        window.location.replace("login.html");
        return;
    }

    isUploading = true;
    if (uploadButton) { uploadButton.disabled = true; uploadButton.textContent = "Processing..."; }
    showStatus("Uploading and extracting your PDF. Please wait...");

    try {
        var fd = new FormData();
        fd.append("file", file);

        var res = await fetch(API + "/documents/inspect", {
            method: "POST",
            headers: { "Authorization": "Bearer " + token },
            body: fd
        });

        var data = await res.json();

        if (res.status === 401) {
            sessionStorage.removeItem("finsight_access_token");
            sessionStorage.removeItem("finsight_user");
            alert("Session expired. Please sign in again.");
            window.location.replace("login.html");
            return;
        }
        if (!res.ok) { throw new Error(data.detail || "Document processing failed."); }
        showDocumentResult(data);

    } catch (err) {
        console.error("Document upload error:", err);
        showStatus(err.message || "Unable to process the document.", "error");
    } finally {
        isUploading = false;
        if (uploadButton) { uploadButton.disabled = false; uploadButton.textContent = "\uff0b Upload document"; }
    }
}

// ---------------------------------------------------------------------------
// DOCUMENT AGENT UPLOAD  (posts to /api/documents/upload)
// ---------------------------------------------------------------------------

function validateDocAgentFile(file) {
    var allowed = ["pdf", "docx", "txt"];
    var ext = file.name.split(".").pop().toLowerCase();
    if (allowed.indexOf(ext) === -1) {
        return "Unsupported file type: ." + ext + ". Please upload PDF, DOCX or TXT.";
    }
    if (file.size === 0) { return "File is empty. Please select a non-empty file."; }
    if (file.size > DOC_AGENT_MAX_SIZE) {
        var mb = (file.size / (1024 * 1024)).toFixed(1);
        return "File too large (" + mb + " MB). Maximum allowed: 100 MB.";
    }
    return null;
}

async function uploadDocumentAgent(file) {
    if (!file || isUploading) { return; }

    var err = validateDocAgentFile(file);
    if (err) { showStatus(err, "error"); return; }

    isUploading = true;
    if (uploadButton) { uploadButton.disabled = true; uploadButton.textContent = "Uploading..."; }
    showStatus("Uploading document...", "info");

    try {
        // Do NOT set Content-Type manually - browser sets the multipart boundary.
        var fd = new FormData();
        fd.append("file", file);

        var res = await fetch(API + "/api/documents/upload", {
            method: "POST",
            body: fd
        });

        var data = await res.json();
        if (!res.ok) {
            throw new Error((data.detail || data.message) || "Upload failed.");
        }

        // Response: { status, message, document: { document_id, filename,
        //             file_type, file_size, upload_date, status } }
        var doc = data.document;
        showStatus('"' + doc.filename + '" uploaded successfully (' + doc.file_type + ').', "success");
        await loadDocuments();

    } catch (e) {
        console.error("Document Agent upload error:", e);
        showStatus(e.message || "Upload failed. Please try again.", "error");
    } finally {
        isUploading = false;
        if (uploadButton) { uploadButton.disabled = false; uploadButton.textContent = "\uff0b Upload document"; }
        if (fileInput) { fileInput.value = ""; }
    }
}

// ---------------------------------------------------------------------------
// FILE SELECTION  (browseButton / uploadButton -> fileInput -> uploadDocumentAgent)
// ---------------------------------------------------------------------------

if (browseButton && fileInput) {
    browseButton.addEventListener("click", function () { fileInput.click(); });
}

if (uploadButton && fileInput) {
    uploadButton.addEventListener("click", function () {
        if (!isUploading) { fileInput.click(); }
    });
}

if (fileInput) {
    fileInput.addEventListener("change", function () {
        var file = fileInput.files[0];
        if (file) { uploadDocumentAgent(file); }
    });
}

// ---------------------------------------------------------------------------
// DRAG AND DROP
// ---------------------------------------------------------------------------

if (dropZone) {
    dropZone.addEventListener("dragover", function (e) {
        e.preventDefault();
        dropZone.style.borderColor = "#16865c";
    });

    dropZone.addEventListener("dragleave", function () {
        dropZone.style.borderColor = "";
    });

    dropZone.addEventListener("drop", function (e) {
        e.preventDefault();
        dropZone.style.borderColor = "";
        var file = e.dataTransfer.files[0];
        if (!file) { return; }
        if (fileInput) {
            var dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;
        }
        uploadDocumentAgent(file);
    });
}

// ---------------------------------------------------------------------------
// DOCUMENT AGENT - LOAD DOCUMENTS INTO RECENT TABLE
// ---------------------------------------------------------------------------

function getRecentTableBody() {
    var panel = document.querySelector(".recent-panel");
    return panel ? panel.querySelector("tbody") : null;
}

function ensureActionColumn() {
    var panel = document.querySelector(".recent-panel");
    if (!panel) { return; }
    var tr = panel.querySelector("thead tr");
    if (!tr || tr.querySelector("th.action-col")) { return; }
    var th = document.createElement("th");
    th.textContent = "ACTION";
    th.className   = "action-col";
    tr.appendChild(th);
}

function statusDisplay(status) {
    var map = {
        "uploaded":   { cls: "status-badge status-uploaded",   label: "Uploaded"   },
        "processing": { cls: "status-badge status-processing", label: "Processing" },
        "indexed":    { cls: "status-badge status-indexed",    label: "Indexed"    },
        "failed":     { cls: "status-badge status-failed",     label: "Failed"     }
    };
    return map[status] || { cls: "status-badge status-uploaded", label: status };
}

function formatDate(ds) {
    if (!ds) { return "\u2014"; }
    try {
        return new Date(ds.replace(" ", "T")).toLocaleDateString("en-US", {
            month: "short", day: "numeric", year: "numeric"
        });
    } catch (e) { return ds; }
}

function escapeText(v) { return String(v == null ? "" : v); }

async function loadDocuments() {
    var tbody = getRecentTableBody();
    if (!tbody) { return; }

    ensureActionColumn();
    tbody.innerHTML =
        "<tr><td colspan=\"5\" style=\"text-align:center;color:#718096;padding:20px;\">Loading documents\u2026</td></tr>";

    try {
        var res = await fetch(API + "/api/documents/");
        if (!res.ok) { throw new Error("Server returned " + res.status); }

        // Response: { status, count, documents: [...] }
        var data  = await res.json();
        var docs  = data.documents || [];

        tbody.innerHTML = "";

        if (docs.length === 0) {
            tbody.innerHTML =
                "<tr><td colspan=\"5\" style=\"text-align:center;color:#718096;padding:30px;\">No documents uploaded yet.</td></tr>";
            return;
        }

        for (var i = 0; i < docs.length; i++) {
            var doc = docs[i];
            var sd  = statusDisplay(doc.status);
            var row = document.createElement("tr");

            var tdDoc = document.createElement("td");
            var typeSpan = document.createElement("span");
            typeSpan.className   = "pdf-icon";
            typeSpan.textContent = escapeText(doc.file_type);
            tdDoc.appendChild(typeSpan);
            tdDoc.appendChild(document.createTextNode(" " + escapeText(doc.filename)));

            var tdType = document.createElement("td");
            tdType.textContent = escapeText(doc.file_type);

            var tdDate = document.createElement("td");
            tdDate.textContent = formatDate(doc.upload_date);

            var tdStatus = document.createElement("td");
            var ssSpan   = document.createElement("span");
            ssSpan.className   = sd.cls;
            ssSpan.textContent = sd.label;
            tdStatus.appendChild(ssSpan);

            var tdAction = document.createElement("td");
            var delBtn   = document.createElement("button");
            delBtn.className             = "delete-btn";
            delBtn.textContent           = "Delete";
            delBtn.dataset.docId         = doc.document_id;
            delBtn.dataset.docFilename   = doc.filename;
            delBtn.addEventListener("click", handleDeleteDocument);
            tdAction.appendChild(delBtn);

            row.appendChild(tdDoc);
            row.appendChild(tdType);
            row.appendChild(tdDate);
            row.appendChild(tdStatus);
            row.appendChild(tdAction);
            tbody.appendChild(row);
        }

    } catch (e) {
        console.error("Failed to load documents:", e);
        tbody.innerHTML =
            "<tr><td colspan=\"5\" style=\"text-align:center;color:#dc2626;padding:20px;\">Unable to load documents. Is the backend running?</td></tr>";
    }
}

// ---------------------------------------------------------------------------
// DOCUMENT AGENT - DELETE
// ---------------------------------------------------------------------------

async function handleDeleteDocument(event) {
    var btn      = event.currentTarget;
    var docId    = btn.dataset.docId;
    var filename = btn.dataset.docFilename;

    if (!confirm("Delete \"" + filename + "\"? This cannot be undone.")) { return; }

    btn.disabled    = true;
    btn.textContent = "Deleting\u2026";

    try {
        var res = await fetch(API + "/api/documents/" + encodeURIComponent(docId), {
            method: "DELETE"
        });

        if (!res.ok) {
            var ed = {};
            try { ed = await res.json(); } catch (e) {}
            throw new Error(ed.detail || ed.message || ("Server error " + res.status));
        }

        var row = btn.closest("tr");
        if (row) { row.remove(); }

        var tb = getRecentTableBody();
        if (tb && tb.querySelectorAll("tr").length === 0) {
            tb.innerHTML =
                "<tr><td colspan=\"5\" style=\"text-align:center;color:#718096;padding:30px;\">No documents uploaded yet.</td></tr>";
        }

        showStatus("\"" + filename + "\" deleted successfully.", "success");

    } catch (e) {
        console.error("Delete error:", e);
        btn.disabled    = false;
        btn.textContent = "Delete";
        showStatus(e.message || "Deletion failed. Please try again.", "error");
    }
}

// ---------------------------------------------------------------------------

console.log("FinSight AI + Document Intelligence Agent initialised.");