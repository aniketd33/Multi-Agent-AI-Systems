
const API = "http://127.0.0.1:8000";

const message = document.getElementById("message");

async function post(path, body) {
    let response;

    try {
        response = await fetch(`${API}${path}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(body)
        });
    } catch (error) {
        throw new Error(
            "Cannot connect to the backend. Please check that the FastAPI server is running."
        );
    }

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(
            typeof data.detail === "string"
                ? data.detail
                : "Request failed. Please try again."
        );
    }

    return data;
}

// Registration
const registerForm = document.getElementById("registerForm");

if (registerForm) {
    registerForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        const button = document.getElementById("submitButton");
        button.disabled = true;
        message.textContent = "";
        message.style.color = "#bd5148";

        try {
            await post("/auth/register", {
                full_name: document.getElementById("fullName").value.trim(),
                email: document.getElementById("email").value.trim(),
                password: document.getElementById("password").value
            });

            message.style.color = "#16865c";
            message.textContent =
                "Account created successfully! Redirecting to sign in...";

            setTimeout(() => {
                window.location.href = "login.html";
            }, 1000);

        } catch (error) {
            message.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });
}

// Login
const loginForm = document.getElementById("loginForm");

if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        const button = document.getElementById("submitButton");
        button.disabled = true;
        message.textContent = "";
        message.style.color = "#bd5148";

        try {
            const data = await post("/auth/login", {
                email: document.getElementById("email").value.trim(),
                password: document.getElementById("password").value
            });

            sessionStorage.setItem(
                "finsight_access_token",
                data.access_token
            );

            sessionStorage.setItem(
                "finsight_user",
                JSON.stringify(data.user)
            );

            message.style.color = "#16865c";
            message.textContent = "Login successful! Opening dashboard...";

            setTimeout(() => {
                window.location.href = "index.html";
            }, 500);

        } catch (error) {
            message.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });
}
