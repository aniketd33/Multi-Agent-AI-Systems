
const API = "http://127.0.0.1:8000";
// ---------------- DASHBOARD DATE & YEAR ----------------

function updateDashboardDate() {
    const now = new Date();

    const dateElement = document.getElementById("currentDate");
    if (dateElement) {
        dateElement.textContent = now.toLocaleDateString("en-US", {
            weekday: "long",
            month: "long",
            day: "numeric",
            year: "numeric"
        }).toUpperCase();
    }

    const yearElement = document.getElementById("currentYear");
    if (yearElement) {
        yearElement.textContent = now.getFullYear();
    }
}

updateDashboardDate();

// Maximum PDF upload size: 100 MB
const MAX_UPLOAD_SIZE = 100 * 1024 * 1024;

// ---------------- AUTHENTICATION ----------------

async function protectDashboard() {
    const token = sessionStorage.getItem("finsight_access_token");

    if (!token) {
        window.location.replace("login.html");
        return;
    }

    try {
        const response = await fetch(`${API}/auth/me`, {
            headers: {
                Authorization: `Bearer ${token}`
            }
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

            let greeting;

            if (hour < 12) {
                greeting = "Good morning";
            } else if (hour < 17) {
                greeting = "Good afternoon";
            } else {
                greeting = "Good evening";
            }

            welcome.replaceChildren(
                document.createTextNode(`${greeting}, ${user.full_name} `)
            );

            const sparkle = document.createElement("span");
            sparkle.textContent = "✦";
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

    } catch (error) {
        console.error("Authentication error:", error);
        alert("Unable to connect to the backend. Please try again.");
        window.location.replace("login.html");
    }
}

protectDashboard();


// ---------------- LOGOUT ----------------

const logoutButton = document.getElementById("logoutButton");

if (logoutButton) {
    logoutButton.addEventListener("click", () => {
        sessionStorage.removeItem("finsight_access_token");
        sessionStorage.removeItem("finsight_user");
        window.location.replace("login.html");
    });
}


// ---------------- THEME ----------------

const themeToggle = document.getElementById("themeToggle");

if (themeToggle) {
    themeToggle.addEventListener("click", () => {
        document.body.classList.toggle("dark");

        const isDark = document.body.classList.contains("dark");
        themeToggle.textContent = isDark ? "☀" : "☾";

        localStorage.setItem(
            "finsight-theme",
            isDark ? "dark" : "light"
        );
    });

    if (localStorage.getItem("finsight-theme") === "dark") {
        document.body.classList.add("dark");
        themeToggle.textContent = "☀";
    }
}


// ---------------- PDF ELEMENTS ----------------

const fileInput = document.getElementById("fileInput");
const browseButton = document.getElementById("browseButton");
const uploadButton = document.getElementById("uploadButton");
const dropZone = document.getElementById("dropZone");

let isUploading = false;


// ---------------- RESULT PANEL ----------------

function getResultPanel() {
    let panel = document.getElementById("documentResult");

    if (!panel && dropZone) {
        panel = document.createElement("div");
        panel.id = "documentResult";

        panel.style.cssText = `
            margin-top: 20px;
            padding: 18px;
            border: 1px solid #dce8e2;
            border-radius: 12px;
            background: #f8fcf9;
            color: #263b31;
            display: none;
            line-height: 1.6;
        `;

        dropZone.insertAdjacentElement("afterend", panel);
    }

    return panel;
}


function showStatus(message, type = "info") {
    const panel = getResultPanel();

    if (!panel) return;

    panel.style.display = "block";
    panel.replaceChildren();

    const colors = {
        info: "#2563eb",
        success: "#16865c",
        error: "#dc2626"
    };

    const heading = document.createElement("strong");
    heading.textContent = message;
    heading.style.color = colors[type];

    panel.appendChild(heading);
}


// ---------------- DISPLAY DOCUMENT RESULT ----------------

function showDocumentResult(data) {
    const panel = getResultPanel();

    if (!panel) return;

    panel.style.display = "block";
    panel.replaceChildren();

    const heading = document.createElement("h3");
    heading.textContent = "Document processed successfully";
    heading.style.color = "#16865c";

    const filename = document.createElement("p");
    filename.textContent = `File: ${data.filename || "Uploaded PDF"}`;

    const pageInfo = document.createElement("p");
    pageInfo.textContent = `Total Pages: ${data.pages}`;

    const characterInfo = document.createElement("p");
    characterInfo.textContent =
        `Extracted Characters: ${data.characters_extracted}`;

    const status = document.createElement("p");
    status.textContent = data.message || "Text extraction completed.";

    const previewTitle = document.createElement("h4");
    previewTitle.textContent = "Extracted Text Preview";

    const preview = document.createElement("pre");
    preview.textContent =
        data.text_preview || "No readable text found in this PDF.";

    preview.style.cssText = `
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        max-height: 350px;
        overflow-y: auto;
        padding: 14px;
        background: #ffffff;
        border: 1px solid #dce8e2;
        border-radius: 8px;
        font-size: 13px;
        color: #263b31;
    `;

    panel.append(
        heading,
        filename,
        pageInfo,
        characterInfo,
        status,
        previewTitle,
        preview
    );

    panel.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
    });
}


// ---------------- PDF UPLOAD ----------------

async function uploadPDF(file) {
    if (!file || isUploading) return;

    const token = sessionStorage.getItem("finsight_access_token");

    if (!token) {
        alert("Your session has expired. Please sign in again.");
        window.location.replace("login.html");
        return;
    }

    isUploading = true;

    if (uploadButton) {
        uploadButton.disabled = true;
        uploadButton.textContent = "Processing...";
    }

    showStatus("Uploading and extracting your PDF. Please wait...");

    try {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(`${API}/documents/inspect`, {
            method: "POST",
            headers: {
                Authorization: `Bearer ${token}`
            },
            body: formData
        });

        const data = await response.json();

        if (response.status === 401) {
            sessionStorage.removeItem("finsight_access_token");
            sessionStorage.removeItem("finsight_user");

            alert("Session expired. Please sign in again.");
            window.location.replace("login.html");
            return;
        }

        if (!response.ok) {
            throw new Error(data.detail || "Document processing failed.");
        }

        showDocumentResult(data);

    } catch (error) {
        console.error("Document upload error:", error);

        showStatus(
            error.message || "Unable to process the document.",
            "error"
        );

    } finally {
        isUploading = false;

        if (uploadButton) {
            uploadButton.disabled = false;
            uploadButton.textContent = "＋ Upload document";
        }
    }
}


// ---------------- FILE SELECTION ----------------

function handlePDF(file) {
    if (!file) return;

    if (
        file.type !== "application/pdf" &&
        !file.name.toLowerCase().endsWith(".pdf")
    ) {
        alert("Please select a PDF file.");
        return;
    }

    if (file.size > MAX_UPLOAD_SIZE) {
        alert("File size must not exceed 100 MB.");
        return;
    }

    if (dropZone) {
        const heading = dropZone.querySelector("strong");
        const details = dropZone.querySelector("small");

        if (heading) {
            heading.textContent = "Selected: " + file.name;
        }

        if (details) {
            details.textContent =
                "PDF selected successfully · " +
                (file.size / (1024 * 1024)).toFixed(2) +
                " MB · Maximum 100 MB";
        }
    }

    uploadPDF(file);
}


// ---------------- BROWSE BUTTON ----------------

if (browseButton && fileInput) {
    browseButton.addEventListener("click", () => {
        fileInput.click();
    });
}


// ---------------- UPLOAD BUTTON ----------------

if (uploadButton && fileInput) {
    uploadButton.addEventListener("click", () => {
        if (!isUploading) {
            fileInput.click();
        }
    });
}


// ---------------- FILE INPUT ----------------

if (fileInput) {
    fileInput.addEventListener("change", () => {
        handlePDF(fileInput.files[0]);
    });
}


// ---------------- DRAG AND DROP ----------------

if (dropZone) {
    dropZone.addEventListener("dragover", (event) => {
        event.preventDefault();
        dropZone.style.borderColor = "#16865c";
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.style.borderColor = "";
    });

    dropZone.addEventListener("drop", (event) => {
        event.preventDefault();
        dropZone.style.borderColor = "";

        const file = event.dataTransfer.files[0];

        if (fileInput && file) {
            const transfer = new DataTransfer();
            transfer.items.add(file);
            fileInput.files = transfer.files;
        }

        handlePDF(file);
    });
}

console.log("FinSight AI frontend initialized successfully.");
