(() => {
    const API_BASE = (window.EVENT_API_BASE || "").replace(/\/+$/, "");
    const page = document.body.dataset.page;

    async function api(path, options = {}) {
        const response = await fetch(`${API_BASE}${path}`, {
            credentials: "include",
            ...options,
            headers: {
                ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
                ...(options.headers || {})
            }
        });
        let body = {};
        try {
            body = await response.json();
        } catch {
            body = {};
        }
        if (!response.ok) {
            throw new Error(body.error || `Request failed (${response.status}).`);
        }
        return body;
    }

    function showMessage(message, isError = false) {
        let output = document.querySelector("[data-message]");
        if (!output) {
            output = document.createElement("div");
            output.dataset.message = "";
            output.setAttribute("role", "status");
            output.className = "fixed top-5 right-5 text-white px-6 py-3 rounded shadow-lg z-50";
            document.body.append(output);
        }
        output.textContent = message;
        output.classList.remove("hidden", "bg-green-500", "bg-red-500");
        output.classList.add(isError ? "bg-red-500" : "bg-green-500");
        if (output.id === "popup") {
            window.setTimeout(() => output.classList.add("hidden"), 3000);
        }
    }

    function handleError(error) {
        showMessage(error.message || "The request could not be completed.", true);
    }

    function jsonBody(form) {
        return JSON.stringify(Object.fromEntries(new FormData(form).entries()));
    }

    function fileUrl(path) {
        if (!path) return "/static/default.png";
        return new URL(path, API_BASE).href;
    }

    function textNode(tag, text, className) {
        const node = document.createElement(tag);
        node.textContent = text == null ? "" : String(text);
        if (className) node.className = className;
        return node;
    }

    function eventIdFromPath() {
        const match = window.location.pathname.match(/\/(?:register_form|payment|view_registrations)\/(\d+)/);
        return match ? match[1] : null;
    }

    function ticketIdFromPath() {
        const match = window.location.pathname.match(/\/scan\/([^/]+)/);
        return match ? decodeURIComponent(match[1]) : null;
    }

    function bindForm(id, endpoint, method = "POST", useFormData = false, onSuccess) {
        const form = document.getElementById(id);
        if (!form) return;
        form.addEventListener("submit", async event => {
            event.preventDefault();
            try {
                const body = useFormData ? new FormData(form) : jsonBody(form);
                const result = await api(endpoint, {
                    method,
                    body
                });
                if (onSuccess) {
                    await onSuccess(result);
                } else if (result.redirect) {
                    window.location.assign(result.redirect);
                } else {
                    showMessage(result.message || "Done.");
                }
            } catch (error) {
                handleError(error);
            }
        });
    }

    function bindLogout() {
        const link = document.getElementById("logoutLink");
        if (!link) return;
        link.addEventListener("click", async event => {
            event.preventDefault();
            try {
                const result = await api("/api/auth/logout", { method: "POST", body: "{}" });
                window.location.assign(result.redirect || "/");
            } catch (error) {
                handleError(error);
            }
        });
    }

    function bindAuthForms() {
        bindForm("sendOtpForm", "/api/auth/send-otp", "POST", false, result => {
            sessionStorage.setItem("signup_email", result.email);
            window.location.assign("/verify");
        });
        bindForm("loginForm", "/api/auth/login");
        bindForm("adminLoginForm", "/api/auth/admin-login");
        bindForm("verifyForm", "/api/auth/verify", "POST", false, result => {
            sessionStorage.setItem("verified_email", result.email);
            window.location.assign("/signup");
        });
        bindForm("resendOtpForm", "/api/auth/resend-otp", "POST", false, result => {
            showMessage(result.message || "OTP resent.");
        });
        bindForm("signupForm", "/api/auth/signup", "POST", false, result => {
            sessionStorage.removeItem("signup_email");
            sessionStorage.removeItem("verified_email");
            window.location.assign(result.redirect || "/login_page");
        });
        const signupEmail = document.getElementById("signupEmail");
        const verifyEmail = document.getElementById("verifyEmail");
        const resendEmail = document.getElementById("resendEmail");
        if (signupEmail) signupEmail.value = sessionStorage.getItem("verified_email") || "";
        const email = sessionStorage.getItem("signup_email") || sessionStorage.getItem("verified_email") || "";
        if (verifyEmail) verifyEmail.value = email;
        if (resendEmail) resendEmail.value = email;
    }

    async function loadDashboard() {
        const result = await api("/api/events");
        document.getElementById("userName").textContent = result.user?.name || "User";
        const profileImage = document.getElementById("profileImage");
        if (profileImage && result.user?.image) profileImage.src = fileUrl(result.user.image);
        const list = document.getElementById("eventsList");
        for (const event of result.events) {
            const card = textNode("div", "", "card p-4 w-full");
            const image = document.createElement("img");
            image.src = event.image ? fileUrl(event.image) : "/";
            image.alt = event.title;
            image.className = "rounded-xl mb-4 h-40 w-full object-cover";
            card.append(image, textNode("h3", event.title, "text-xl font-bold mb-2"));
            card.append(textNode("p", event.description, "text-gray-300 text-sm mb-2"));
            card.append(textNode("p", `📅 ${event.date}`, "text-xs text-gray-400 mb-3"));
            card.append(textNode(
                "p",
                event.type === "paid" ? `💰 ₹${event.price}` : "🆓 Free Event",
                `${event.type === "paid" ? "text-yellow-400" : "text-green-400"} font-semibold mb-2`
            ));
            const link = textNode("a", event.type === "paid" ? "Pay & Register" : "Register Now",
                `block text-center mt-3 p-2 rounded-lg ${event.type === "paid" ? "bg-yellow-500 hover:bg-yellow-700" : "bg-green-500 hover:bg-green-700"}`);
            link.href = `/register_form/${event.id}`;
            card.append(link);
            list.append(card);
        }
    }

    async function loadAdmin() {
        const result = await api("/api/admin");
        const list = document.getElementById("adminEvents");
        for (const event of result.events) {
            const card = textNode("div", "", "bg-white/10 p-4 rounded mb-3");
            card.append(textNode("h3", event.title, "text-lg font-bold"));
            card.append(textNode("p", event.description));
            card.append(textNode("p", `Type: ${event.type} | ₹${event.price}`));
            const actions = textNode("div", "", "mt-3 flex gap-3");
            const remove = textNode("button", "Delete", "bg-red-500 px-3 py-1 rounded");
            remove.type = "button";
            remove.addEventListener("click", async () => {
                try {
                    await api(`/api/admin/events/${event.id}`, { method: "DELETE" });
                    window.location.reload();
                } catch (error) {
                    handleError(error);
                }
            });
            const users = textNode("a", "Users", "bg-blue-500 px-3 py-1 rounded");
            users.href = `/view_registrations/${event.id}`;
            actions.append(remove, users);
            card.append(actions);
            list.append(card);
        }
        bindForm("createEventForm", "/api/admin/events", "POST", true, result => {
            window.location.assign(result.redirect || "/admin");
        });
    }

    async function loadHistory() {
        const result = await api("/api/history");
        const rows = document.getElementById("historyRows");
        for (const item of result.history) {
            const row = document.createElement("tr");
            row.className = "border-b";
            row.append(textNode("td", item.event, "p-2"));
            const type = textNode("td", item.type === "paid" ? "Paid" : "Free", "p-2");
            type.classList.add(item.type === "paid" ? "text-yellow-400" : "text-green-400");
            row.append(type);
            row.append(textNode("td", item.type === "paid" ? `₹${item.price}` : "-", "p-2"));
            const status = textNode("td", item.payment_status === "done" ? "Done" : "Pending", "p-2");
            status.classList.add(item.payment_status === "done" ? "text-green-400" : "text-red-400");
            row.append(status, textNode("td", item.created_at, "p-2 text-blue-300"));
            rows.append(row);
        }
    }

    async function loadProfile() {
        const result = await api("/api/profile");
        const user = result.user || {};
        document.getElementById("profileName").textContent = user.name || "";
        document.getElementById("profileEmail").textContent = `Email: ${user.email || ""}`;
        document.getElementById("profileMobile").textContent = `Mobile: ${user.mobile || ""}`;
        if (user.image) {
            document.getElementById("profileImage").src = fileUrl(user.image);
            document.getElementById("largeProfileImage").src = fileUrl(user.image);
        }
        bindForm("updateProfileForm", "/api/profile", "PUT");
        bindForm("uploadProfileForm", "/api/profile/image", "POST", true, result => {
            if (result.image) {
                document.getElementById("profileImage").src = fileUrl(result.image);
                document.getElementById("largeProfileImage").src = fileUrl(result.image);
            }
            showMessage(result.message);
        });
    }

    async function loadRegistrationForm() {
        const id = eventIdFromPath();
        if (!id) throw new Error("Missing event ID.");
        const result = await api(`/api/events/${id}`);
        const event = result.event;
        document.getElementById("eventTitle").textContent = event.title || "Event Registration";
        const button = document.getElementById("registrationSubmit");
        button.textContent = event.type === "paid" ? "Pay Now" : "Register";
        button.className = `${event.type === "paid" ? "bg-yellow-500 hover:bg-yellow-700" : "bg-green-500 hover:bg-green-700"} w-full p-3 rounded`;
        bindForm("registrationForm", `/api/events/${id}/registrations`);
    }

    async function loadPayment() {
        const id = eventIdFromPath();
        if (!id) throw new Error("Missing event ID.");
        const result = await api(`/api/events/${id}/payment`);
        document.getElementById("paymentEventName").textContent = result.event_name;
        document.getElementById("paymentPrice").textContent = result.price;
        document.getElementById("paymentUpiId").textContent = result.upi_id;
        document.getElementById("paymentQr").src = fileUrl(result.qr);
        document.getElementById("confirmPaymentLink").addEventListener("click", async event => {
            event.preventDefault();
            try {
                const confirmed = await api(`/api/events/${id}/payment/confirm`, { method: "POST", body: "{}" });
                window.location.assign(confirmed.redirect || "/dashboard");
            } catch (error) {
                handleError(error);
            }
        });
    }

    async function loadRegistrations() {
        const id = eventIdFromPath();
        if (!id) throw new Error("Missing event ID.");
        const result = await api(`/api/events/${id}/registrations`);
        const list = document.getElementById("registrationsList");
        for (const registration of result.registrations) {
            const card = textNode("div", "", "card p-5");
            card.append(textNode("h2", registration.name, "text-lg font-bold mb-2"));
            card.append(textNode("p", `📧 ${registration.email}`, "text-sm text-gray-300 mb-1"));
            card.append(textNode("p", `📱 ${registration.mobile}`, "text-sm text-gray-300 mb-1"));
            card.append(textNode("p", `🎂 Age: ${registration.age}`, "text-sm text-gray-300 mb-1"));
            card.append(textNode("p", `📍 ${registration.address}`, "text-sm text-gray-300 mb-2"));
            card.append(textNode(
                "p",
                registration.payment_status === "done" ? "✔ Paid" : "⏳ Pending",
                `mb-2 font-semibold ${registration.payment_status === "done" ? "bg-green-500" : "bg-yellow-500"} px-3 py-1 rounded`
            ));
            card.append(textNode("p", `🎟 ${registration.event}`, "text-blue-300 text-sm"));
            list.append(card);
        }
    }

    async function loadTicket() {
        const id = ticketIdFromPath();
        if (!id) throw new Error("Missing ticket ID.");
        const result = await api(`/api/tickets/${encodeURIComponent(id)}`);
        const ticket = result.ticket;
        const fields = {
            ticketEvent: ticket.event_name,
            ticketId: ticket.ticket_id,
            ticketName: ticket.name,
            ticketEmail: ticket.email,
            ticketMobile: ticket.mobile,
            ticketAge: ticket.age,
            ticketAddress: ticket.address
        };
        for (const [fieldId, value] of Object.entries(fields)) {
            document.getElementById(fieldId).textContent = value == null ? "" : value;
        }
        document.getElementById("ticketCard").classList.remove("hidden");
    }

    bindAuthForms();
    bindLogout();

    const loaders = {
        dashboard: loadDashboard,
        admin: loadAdmin,
        history: loadHistory,
        profile: loadProfile,
        "register-form": loadRegistrationForm,
        payment: loadPayment,
        registrations: loadRegistrations,
        "scan-result": loadTicket
    };
    if (loaders[page]) {
        loaders[page]().catch(error => {
            handleError(error);
            if (error.message.includes("Authentication required")) {
                window.location.assign("/login_page");
            } else if (error.message.includes("Administrator authentication required")) {
                window.location.assign("/admin_login");
            }
        });
    }

    bindForm("contactForm", "/api/contact", "POST", false, result => {
        showMessage(result.message);
        if (result.redirect) window.setTimeout(() => window.location.assign(result.redirect), 800);
    });
})();
