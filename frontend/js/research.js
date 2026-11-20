
(() => {
    "use strict";

    const API = "http://127.0.0.1:8000";
    const token = sessionStorage.getItem("finsight_access_token");
    const $ = (id) => document.getElementById(id);
    let sessions = [];
    let activeSessionId = null;
    let editingSessionId = null;

    if (!token) {
        window.location.replace("login.html");
        return;
    }

    const headers = () => ({ Authorization: `Bearer ${token}` });

    async function api(path, options = {}) {
        const response = await fetch(`${API}${path}`, {
            ...options,
            headers: { ...headers(), ...(options.headers || {}) }
        });
        if (response.status === 401) {
            sessionStorage.removeItem("finsight_access_token");
            sessionStorage.removeItem("finsight_user");
            window.location.replace("login.html");
            throw new Error("Your sign-in has expired. Please sign in again.");
        }
        if (response.status === 204) return null;
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || "Request failed.");
        return data;
    }

    function notice(message, type = "success") {
        const el = $("researchNotice");
        el.textContent = message;
        el.className = `research-notice${type === "error" ? " error" : ""}`;
        el.hidden = false;
    }

    function clearNotice() {
        $("researchNotice").hidden = true;
    }

    function escapeText(value) {
        return String(value ?? "").replace(/[&<>"']/g, char => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
        })[char]);
    }

    function formatDate(value) {
        if (!value) return "Date unavailable";
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? "Date unavailable" :
            date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    }

    async function loadSessions() {
        const params = new URLSearchParams({
            search: $("sessionSearch").value.trim(),
            sort: $("sessionSort").value
        });
        try {
            sessions = await api(`/research/sessions?${params}`);
            renderSessions();
            if (activeSessionId && !sessions.some(item => item.id === activeSessionId)) {
                activeSessionId = null;
                showNoSession();
            } else if (activeSessionId) {
                await openSession(activeSessionId, false);
            }
        } catch (error) {
            $("sessionList").textContent = error.message;
            notice(error.message, "error");
        }
    }

    function renderSessions() {
        $("sessionCount").textContent = `${sessions.length} session${sessions.length === 1 ? "" : "s"}`;
        const list = $("sessionList");
        list.replaceChildren();
        if (!sessions.length) {
            const empty = document.createElement("p");
            empty.className = "muted";
            empty.textContent = "No sessions found. Create your first research session.";
            list.appendChild(empty);
            return;
        }
        sessions.forEach(item => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `session-item${item.id === activeSessionId ? " selected" : ""}`;
            button.innerHTML = `<strong>${escapeText(item.name)}</strong>
                <small>${escapeText(item.description || "No description")}</small>
                <small class="session-meta"><span>${item.document_count} PDF${item.document_count === 1 ? "" : "s"}</span><span>${escapeText(formatDate(item.updated_at))}</span></small>`;
            button.addEventListener("click", () => openSession(item.id));
            list.appendChild(button);
        });
    }

    function showNoSession() {
        $("noSession").hidden = false;
        $("sessionDetail").hidden = true;
        renderSessions();
    }

    async function openSession(id, refreshList = true) {
        clearNotice();
        try {
            const item = await api(`/research/sessions/${id}`);
            activeSessionId = id;
            $("noSession").hidden = true;
            $("sessionDetail").hidden = false;
            $("activeSessionName").textContent = item.name;
            $("activeSessionDescription").textContent = item.description || "No description added.";
            renderSessions();
            await loadDocuments();
        } catch (error) {
            notice(error.message, "error");
            if (refreshList) await loadSessions();
        }
    }

    async function loadDocuments() {
        if (!activeSessionId) return;
        const params = new URLSearchParams({
            search: $("documentSearch").value.trim(),
            sort: $("documentSort").value
        });
        try {
            const docs = await api(`/research/sessions/${activeSessionId}/documents?${params}`);
            renderDocuments(docs);
        } catch (error) {
            $("documentList").textContent = error.message;
            notice(error.message, "error");
        }
    }

    function renderDocuments(docs) {
        $("documentCount").textContent = `${docs.length} document${docs.length === 1 ? "" : "s"}`;
        const list = $("documentList");
        list.replaceChildren();
        if (!docs.length) {
            const empty = document.createElement("p");
            empty.className = "muted";
            empty.textContent = "No PDFs in this session yet. Upload a PDF to get started.";
            list.appendChild(empty);
            return;
        }
        docs.forEach(doc => {
            const row = document.createElement("article");
            row.className = "document-item";
            const info = document.createElement("div");
            info.className = "document-info";
            info.innerHTML = `<span class="document-icon">PDF</span><div><strong>${escapeText(doc.filename)}</strong><small>${(doc.size_bytes / (1024 * 1024)).toFixed(2)} MB · ${escapeText(formatDate(doc.uploaded_at))}</small></div>`;
            const actions = document.createElement("div");
            actions.className = "document-actions";
            const download = document.createElement("button");
            download.type = "button";
            download.textContent = "Download";
            download.addEventListener("click", () => downloadDocument(doc));
            const remove = document.createElement("button");
            remove.type = "button";
            remove.textContent = "Delete";
            remove.addEventListener("click", () => deleteDocument(doc));
            actions.append(download, remove);
            row.append(info, actions);
            list.appendChild(row);
        });
    }

    async function downloadDocument(doc) {
        try {
            const response = await fetch(`${API}/research/documents/${doc.id}/download`, { headers: headers() });
            if (response.status === 401) {
                sessionStorage.removeItem("finsight_access_token");
                window.location.replace("login.html");
                return;
            }
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.detail || "Download failed.");
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = doc.filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            notice(error.message, "error");
        }
    }

    async function deleteDocument(doc) {
        if (!window.confirm(`Delete "${doc.filename}" from this session?`)) return;
        try {
            await api(`/research/documents/${doc.id}`, { method: "DELETE" });
            notice("Document deleted.");
            await loadDocuments();
            await loadSessions();
        } catch (error) {
            notice(error.message, "error");
        }
    }

    function openDialog(item = null) {
        editingSessionId = item ? item.id : null;
        $("dialogEyebrow").textContent = item ? "EDIT WORKSPACE" : "NEW WORKSPACE";
        $("dialogTitle").textContent = item ? "Edit research session" : "Create research session";
        $("saveSessionButton").textContent = item ? "Save changes" : "Create session";
        $("sessionName").value = item?.name || "";
        $("sessionDescription").value = item?.description || "";
        $("sessionDialog").showModal();
        $("sessionName").focus();
    }

    function closeDialog() {
        $("sessionDialog").close();
        $("sessionForm").reset();
        editingSessionId = null;
    }

    $("sessionForm").addEventListener("submit", async event => {
        event.preventDefault();
        const name = $("sessionName").value.trim();
        if (!name) {
            $("sessionName").focus();
            return;
        }
        const payload = {
            name,
            description: $("sessionDescription").value.trim()
        };
        const button = $("saveSessionButton");
        button.disabled = true;
        try {
            if (editingSessionId) {
                const id = editingSessionId;
                await api(`/research/sessions/${id}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                notice("Research session updated.");
                closeDialog();
                await loadSessions();
                await openSession(id);
            } else {
                const created = await api("/research/sessions", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                notice("Research session created.");
                closeDialog();
                await loadSessions();
                await openSession(created.id);
            }
        } catch (error) {
            notice(error.message, "error");
        } finally {
            button.disabled = false;
        }
    });

    async function uploadPDF(file) {
        if (!activeSessionId || !file) return;
        if (!file.name.toLowerCase().endsWith(".pdf") || (file.type && file.type !== "application/pdf")) {
            notice("Please choose a valid PDF file.", "error");
            return;
        }
        if (file.size > 100 * 1024 * 1024) {
            notice("PDF must not exceed 100 MB.", "error");
            return;
        }
        const progressWrap = $("uploadProgressWrap");
        const progress = $("uploadProgress");
        progressWrap.hidden = false;
        progress.value = 0;
        $("uploadProgressPercent").textContent = "0%";
        $("uploadProgressText").textContent = `Uploading ${file.name}`;
        const formData = new FormData();
        formData.append("file", file);
        try {
            await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open("POST", `${API}/research/sessions/${activeSessionId}/documents`);
                xhr.setRequestHeader("Authorization", `Bearer ${token}`);
                xhr.upload.addEventListener("progress", event => {
                    if (event.lengthComputable) {
                        const percent = Math.round((event.loaded / event.total) * 100);
                        progress.value = percent;
                        $("uploadProgressPercent").textContent = `${percent}%`;
                    }
                });
                xhr.addEventListener("load", () => {
                    let data = {};
                    try { data = JSON.parse(xhr.responseText); } catch (_) {}
                    if (xhr.status === 401) {
                        sessionStorage.removeItem("finsight_access_token");
                        window.location.replace("login.html");
                        reject(new Error("Your sign-in has expired."));
                    } else if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(data);
                    } else {
                        reject(new Error(data.detail || "PDF upload failed."));
                    }
                });
                xhr.addEventListener("error", () => reject(new Error("Unable to connect to the server.")));
                xhr.send(formData);
            });
            notice("PDF uploaded to this research session.");
            await loadDocuments();
            await loadSessions();
        } catch (error) {
            notice(error.message, "error");
        } finally {
            setTimeout(() => { progressWrap.hidden = true; }, 900);
            $("researchFileInput").value = "";
        }
    }

    $("newSessionButton").addEventListener("click", () => openDialog());
    $("emptyNewSession").addEventListener("click", () => openDialog());
    $("renameSessionButton").addEventListener("click", async () => {
        const item = sessions.find(entry => entry.id === activeSessionId) ||
            await api(`/research/sessions/${activeSessionId}`).catch(() => null);
        if (item) openDialog(item);
    });
    $("deleteSessionButton").addEventListener("click", async () => {
        if (!activeSessionId) return;
        const item = sessions.find(entry => entry.id === activeSessionId);
        const name = item?.name || $("activeSessionName").textContent;
        if (!window.confirm(`Delete "${name}" and all PDFs stored in it? This cannot be undone.`)) return;
        try {
            await api(`/research/sessions/${activeSessionId}`, { method: "DELETE" });
            activeSessionId = null;
            showNoSession();
            notice("Research session and its stored PDFs deleted.");
            await loadSessions();
        } catch (error) {
            notice(error.message, "error");
        }
    });
    $("researchFileInput").addEventListener("change", event => uploadPDF(event.target.files[0]));
    $("sessionSearch").addEventListener("input", debounce(loadSessions, 250));
    $("sessionSort").addEventListener("change", loadSessions);
    $("documentSearch").addEventListener("input", debounce(loadDocuments, 250));
    $("documentSort").addEventListener("change", loadDocuments);
    $("closeDialog").addEventListener("click", closeDialog);
    $("cancelDialog").addEventListener("click", closeDialog);

    $("logoutButton").addEventListener("click", () => {
        sessionStorage.removeItem("finsight_access_token");
        sessionStorage.removeItem("finsight_user");
        window.location.replace("login.html");
    });

    $("themeToggle").addEventListener("click", () => {
        document.body.classList.toggle("dark");
        const dark = document.body.classList.contains("dark");
        $("themeToggle").textContent = dark ? "☀" : "☾";
        localStorage.setItem("finsight-theme", dark ? "dark" : "light");
    });
    if (localStorage.getItem("finsight-theme") === "dark") {
        document.body.classList.add("dark");
        $("themeToggle").textContent = "☀";
    }

    function debounce(fn, delay) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), delay);
        };
    }

    api("/auth/me").then(user => {
        $("profileName").textContent = user.full_name;
        const avatar = document.querySelector(".profile-avatar");
        if (avatar) avatar.textContent = user.full_name.split(" ").map(part => part[0]).join("").slice(0, 2).toUpperCase();
    }).catch(error => notice(error.message, "error"));

    showNoSession();
    loadSessions();
})();
