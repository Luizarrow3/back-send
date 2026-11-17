import { api, exportCsv, json } from "./api.js";
import { mountTerminal } from "./terminal.js";

const $ = (selector) => document.querySelector(selector);
const formDialog = $("#person-dialog");
const personForm = $("#person-form");
const pageSize = 10;
let currentPage = 1;
let currentQuery = "";
let currentStatus = "";
let reportQuery = "";
let reportStatus = "";
let currentUser = null;
let currentView = "dashboard";
let resolveActionDialog = null;
let timerId = null;
let inactivityListenersBound = false;
let lastPointerActivity = 0;

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[character]);
}

function setTheme(theme) {
    document.body.classList.toggle("dark", theme === "dark");
    localStorage.setItem("censo-theme", theme);
    $("#theme-select").value = theme;
}

function setNotice(message, isError = false) {
    const notice = $("#notice");
    notice.textContent = message;
    notice.classList.toggle("error", isError);
    notice.hidden = false;
    window.setTimeout(() => { notice.hidden = true; }, 5000);
}

function askAction({ title, message, confirmLabel, reasonRequired = false }) {
    $("#action-title").textContent = title;
    $("#action-message").textContent = message;
    $("#action-confirm").textContent = confirmLabel;
    $("#action-reason-field").hidden = !reasonRequired;
    $("#action-reason").required = reasonRequired;
    $("#action-reason").value = "";
    $("#action-dialog").showModal();
    (reasonRequired ? $("#action-reason") : $("#action-confirm")).focus();
    return new Promise((resolve) => { resolveActionDialog = resolve; });
}

function fillStatusChart(stats) {
    const entries = Object.entries(stats.por_status || {});
    const max = Math.max(1, ...entries.map(([, count]) => count));
    $("#status-chart").innerHTML = entries.length
        ? entries.map(([name, count]) => `
            <div class="chart-row">
                <span>${escapeHTML(name.replaceAll("_", " "))}</span>
                <div class="chart-track"><div style="width:${Math.round(count / max * 100)}%"></div></div>
                <strong>${count}</strong>
            </div>`).join("")
        : '<p class="muted">Sem dados disponíveis.</p>';
}

async function loadStats() {
    const stats = await json("/resumo");
    $("#metric-total").textContent = stats.total_pessoas;
    $("#metric-pending").textContent = stats.pendentes ?? stats.por_status?.PENDENTE ?? 0;
    $("#metric-biometric").textContent = stats.validados_biometria ?? 0;
    $("#metric-average-age").textContent = `${stats.idade_media} anos`;
    fillStatusChart(stats);
}

function renderPeople(data) {
    const body = $("#people-rows");
    if (!data.items.length) {
        body.innerHTML = '<tr><td colspan="5" class="empty-state">Nenhum recenseado encontrado.</td></tr>';
    } else {
        body.innerHTML = data.items.map((person) => `
            <tr>
                <td><strong>${escapeHTML(person.nome)}</strong><small>${escapeHTML(person.cpf_mascarado)}</small></td>
                <td>${escapeHTML(person.sexo)}</td>
                <td>${escapeHTML(person.data_nascimento)}</td>
                <td><span class="badge">${escapeHTML(person.status.replaceAll("_", " "))}</span></td>
                <td class="actions">
                    <button class="text-button" data-action="edit" data-id="${person.id}">Editar</button>
                    ${person.status === "PENDENTE" ? `<button class="text-button" data-action="review" data-id="${person.id}">Iniciar análise</button>` : ""}
                    ${person.status === "EM_ANALISE" ? `<button class="text-button" data-action="approve" data-id="${person.id}">Marcar recenseado</button><button class="text-button danger" data-action="reject" data-id="${person.id}">Rejeitar</button>` : ""}
                    <button class="text-button" data-action="photo" data-id="${person.id}">Foto</button>
                    <button class="text-button" data-action="match" data-id="${person.id}">Simular match</button>
                    <button class="text-button" data-action="mismatch" data-id="${person.id}">Simular divergência</button>
                    <button class="text-button danger" data-action="delete" data-id="${person.id}">Excluir</button>
                </td>
            </tr>`).join("");
    }
    $("#page-label").textContent = `Página ${data.page} de ${Math.max(1, data.pages)} · ${data.total} registros`;
    $("#previous-page").disabled = data.page <= 1;
    $("#next-page").disabled = data.page >= data.pages;
}

async function loadPeople() {
    const query = new URLSearchParams({ page: String(currentPage), page_size: String(pageSize) });
    if (currentQuery) query.set("q", currentQuery);
    if (currentStatus) query.set("status_filtro", currentStatus);
    const data = await json(`/pessoas/paginado?${query}`);
    renderPeople(data);
}

async function refreshDashboard() {
    await loadStats();
}

async function refreshActiveView() {
    if (currentView === "dashboard") return loadStats();
    if (currentView === "people") {
        await Promise.all([loadPeople(), loadStats()]);
        return;
    }
    if (currentView === "reports") return loadReportSummary();
}

async function loadReportSummary() {
    const query = new URLSearchParams({ page: "1", page_size: "1" });
    if (reportQuery) query.set("q", reportQuery);
    if (reportStatus) query.set("status_filtro", reportStatus);
    const result = await json(`/pessoas/paginado?${query}`);
    $("#report-summary").textContent = `${result.total} registro(s) incluído(s) no relatório.`;
}

async function showView(view) {
    const titles = {
        dashboard: ["Dashboard", "Acompanhe os indicadores e a evolução dos cadastros."],
        people: ["Recenseados", "Consulte e gerencie os cadastros previdenciários."],
        reports: ["Relatórios", "Gere relatórios consolidados com filtros de consulta."],
        settings: ["Configurações", "Ajuste as preferências desta estação de trabalho."],
    };
    if (!titles[view]) return;
    currentView = view;
    document.querySelectorAll(".app-view").forEach((section) => {
        section.hidden = section.id !== `view-${view}`;
    });
    document.querySelectorAll(".nav-item").forEach((button) => {
        const active = button.dataset.view === view;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    });
    $("#page-title").textContent = titles[view][0];
    $("#page-description").textContent = titles[view][1];
    $("#refresh-btn").hidden = view === "settings";
    if (view === "dashboard") await loadStats();
    if (view === "people") await loadPeople();
    if (view === "reports") await loadReportSummary();
}

function openPersonDialog(person = null) {
    personForm.reset();
    $("#person-id").value = person?.id ?? "";
    $("#person-name").value = person?.nome ?? "";
    $("#person-cpf").value = "";
    $("#person-cpf").required = !person;
    $("#person-cpf-field").hidden = Boolean(person);
    $("#person-sex").value = person?.sexo ?? "FEMININO";
    $("#person-birth").value = person?.data_nascimento ?? "";
    $("#person-dialog-title").textContent = person ? "Editar recenseado" : "Novo recenseado";
    $("#photo-preview").hidden = true;
    formDialog.showModal();
}

async function savePerson(event) {
    event.preventDefault();
    const id = $("#person-id").value;
    const payload = {
        nome: $("#person-name").value.trim(),
        sexo: $("#person-sex").value,
        data_nascimento: $("#person-birth").value,
    };
    if (!id) payload.cpf = $("#person-cpf").value.replace(/\D/g, "");
    const person = await json(id ? `/pessoas/${id}` : "/pessoas", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(payload),
    });
    const photo = $("#person-photo").files[0];
    if (photo) {
        const data = new FormData();
        data.append("arquivo", photo);
        await json(`/pessoas/${person.id}/documentos`, { method: "POST", body: data });
    }
    formDialog.close();
    setNotice(id ? "Cadastro atualizado." : "Recenseado cadastrado.");
    await refreshActiveView();
}

async function handleTableAction(event) {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const { action, id } = button.dataset;
    if (action === "edit") {
        const person = await json(`/pessoas/${id}`);
        openPersonDialog(person);
    } else if (action === "delete") {
        const decision = await askAction({
            title: "Excluir recenseado",
            message: "O cadastro e seus anexos serão removidos. Esta ação não pode ser desfeita.",
            confirmLabel: "Excluir cadastro",
        });
        if (!decision?.confirmed) return;
        await json(`/pessoas/${id}`, { method: "DELETE" });
        setNotice("Cadastro excluído.");
        await refreshActiveView();
    } else if (action === "photo") {
        const response = await api(`/pessoas/${id}/foto`);
        const url = URL.createObjectURL(await response.blob());
        const image = $("#photo-viewer-image");
        image.src = url;
        $("#photo-viewer").showModal();
        image.onload = () => URL.revokeObjectURL(url);
    } else if (["review", "approve", "reject"].includes(action)) {
        const nextStatus = { review: "EM_ANALISE", approve: "RECENSEADO", reject: "REJEITADO" }[action];
        const params = new URLSearchParams({ novo_status: nextStatus });
        if (action === "reject") {
            const decision = await askAction({
                title: "Rejeitar cadastro",
                message: "Informe o motivo. A justificativa será registrada no histórico.",
                confirmLabel: "Confirmar rejeição",
                reasonRequired: true,
            });
            if (!decision?.confirmed) return;
            params.set("motivo", decision.reason);
        }
        await json(`/pessoas/${id}/status?${params}`, { method: "POST" });
        setNotice(`Status atualizado para ${nextStatus.replaceAll("_", " ")}.`);
        await refreshActiveView();
    } else if (action === "match" || action === "mismatch") {
        const matched = action === "match";
        const result = await json(`/pessoas/${id}/validacao-facial`, {
            method: "POST",
            body: JSON.stringify({ correspondencia_simulada: matched }),
        });
        setNotice(`Simulação: ${result.resultado}, assertividade ilustrativa de ${result.assertividade_simulada}%. Não é uma medição biométrica real.`);
        await loadStats();
    }
}

async function exportReport() {
    await exportCsv({ q: reportQuery, status_filtro: reportStatus });
}

async function exportPdf() {
    const reportWindow = window.open("", "_blank");
    if (!reportWindow) throw new Error("Permita pop-ups para gerar o PDF.");
    try {
        const query = new URLSearchParams({ page: "1", page_size: "100" });
        if (reportQuery) query.set("q", reportQuery);
        if (reportStatus) query.set("status_filtro", reportStatus);
        const firstPage = await json(`/pessoas/paginado?${query}`);
        const people = [...firstPage.items];
        for (let page = 2; page <= firstPage.pages; page++) {
            query.set("page", String(page));
            const result = await json(`/pessoas/paginado?${query}`);
            people.push(...result.items);
        }
        const rows = people.map((person) => `
            <tr><td>${escapeHTML(person.id)}</td><td>${escapeHTML(person.nome)}</td>
                <td>${escapeHTML(person.cpf_mascarado)}</td><td>${escapeHTML(person.sexo)}</td>
                <td>${escapeHTML(person.data_nascimento)}</td><td>${escapeHTML(person.status)}</td></tr>
        `).join("");
        reportWindow.document.write(`<!doctype html><html lang="pt-BR"><meta charset="utf-8">
            <title>Relatório de recenseados</title><style>
            body{font:12px Arial,sans-serif;color:#111827;margin:32px}
            h1{font-size:20px}p{color:#475569}table{width:100%;border-collapse:collapse}
            th,td{text-align:left;padding:8px;border:1px solid #cbd5e1}
            th{background:#eff6ff}@media print{body{margin:12mm}}
            </style><h1>Relatório de recenseados</h1>
            <p>Gerado em ${escapeHTML(new Date().toLocaleString("pt-BR"))} · ${people.length} registros</p>
            <table><thead><tr><th>ID</th><th>Nome</th><th>CPF</th><th>Sexo</th><th>Nascimento</th><th>Status</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="6">Nenhum registro encontrado.</td></tr>'}</tbody></table></html>`);
        reportWindow.document.close();
        reportWindow.focus();
        window.setTimeout(() => reportWindow.print(), 250);
    } catch (error) {
        reportWindow.close();
        throw error;
    }
}

function startInactivityLock() {
    const key = "censo-idle-minutes";
    if (!localStorage.getItem(key)) localStorage.setItem(key, "15");
    const resetTimer = () => {
        if ($("#lock-overlay").hidden) {
            window.clearTimeout(timerId);
            const minutes = Number(localStorage.getItem(key)) || 15;
            timerId = window.setTimeout(lockScreen, minutes * 60_000);
        }
    };
    if (!inactivityListenersBound) {
        ["pointerdown", "keydown", "touchstart", "scroll"].forEach((event) => {
            document.addEventListener(event, resetTimer, { passive: true });
        });
        document.addEventListener("pointermove", () => {
            const now = Date.now();
            if (now - lastPointerActivity >= 1000) {
                lastPointerActivity = now;
                resetTimer();
            }
        }, { passive: true });
        inactivityListenersBound = true;
    }
    resetTimer();
}

async function lockScreen() {
    $("#lock-email").value = currentUser?.email || localStorage.getItem("censo-email") || "";
    $("#lock-overlay").hidden = false;
    localStorage.setItem("censo-locked", "true");
    $("#lock-password").focus();
    const token = localStorage.getItem("censo-token");
    if (token) {
        try {
            await fetch("/auth/logout", { method: "POST", headers: { Authorization: `Bearer ${token}` } });
        } catch (error) {
            setNotice("Não foi possível encerrar a sessão no servidor.", true);
        }
    }
    localStorage.removeItem("censo-token");
}

async function unlockScreen(event) {
    event.preventDefault();
    $("#lock-error").hidden = true;
    const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            email: $("#lock-email").value.trim(),
            password: $("#lock-password").value,
        }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Não foi possível reautenticar.");
    localStorage.setItem("censo-token", data.access_token);
    localStorage.setItem("censo-email", $("#lock-email").value.trim());
    localStorage.removeItem("censo-locked");
    window.location.reload();
}

function downloadPhotoPreview(file) {
    const image = $("#photo-preview");
    if (!file) {
        image.hidden = true;
        return;
    }
    if (!["image/jpeg", "image/png"].includes(file.type)) {
        throw new Error("Selecione uma imagem JPG ou PNG.");
    }
    image.src = URL.createObjectURL(file);
    image.hidden = false;
}

function parsePersonCommand(command) {
    const prefix = "pessoa adicionar ";
    const fields = command.slice(prefix.length).split("|").map((value) => value.trim());
    if (fields.length !== 4) {
        throw new Error('Uso: pessoa adicionar "Nome" | CPF | FEMININO | AAAA-MM-DD');
    }
    return { nome: fields[0].replace(/^["']|["']$/g, ""), cpf: fields[1], sexo: fields[2], data_nascimento: fields[3] };
}

const terminal = mountTerminal(async (command) => {
    if (command === "ajuda") return "Comandos: ajuda, estatisticas, tema escuro|claro, config bloqueio 1|5|10|15, relatorio csv, pessoa adicionar Nome | CPF | SEXO | AAAA-MM-DD";
    if (command === "estatisticas") {
        const stats = await json("/resumo");
        return `Total: ${stats.total_pessoas} · Pendentes: ${stats.pendentes} · Validados (simulados): ${stats.validados_biometria}`;
    }
    if (command === "tema escuro" || command === "tema claro") {
        setTheme(command.endsWith("escuro") ? "dark" : "light");
        return "Tema atualizado.";
    }
    if (command.startsWith("config bloqueio ")) {
        const minutes = command.slice("config bloqueio ".length);
        if (!["1", "5", "10", "15"].includes(minutes)) {
            throw new Error("Use config bloqueio seguido de 1, 5, 10 ou 15.");
        }
        localStorage.setItem("censo-idle-minutes", minutes);
        $("#idle-time-select").value = minutes;
        startInactivityLock();
        return `Bloqueio por inatividade definido para ${minutes} minuto(s).`;
    }
    if (command === "relatorio csv") {
        await exportReport();
        return "Download do relatório CSV iniciado.";
    }
    if (command.startsWith("pessoa adicionar ")) {
        await json("/pessoas", { method: "POST", body: JSON.stringify(parsePersonCommand(command)) });
        await refreshActiveView();
        return "Recenseado cadastrado.";
    }
    return "Comando desconhecido. Digite ajuda para ver os comandos disponíveis.";
});

async function init() {
    $("#lock-form").addEventListener("submit", (event) => unlockScreen(event).catch((error) => {
        $("#lock-error").textContent = error.message;
        $("#lock-error").hidden = false;
    }));
    if (localStorage.getItem("censo-locked") === "true") {
        $("#lock-email").value = localStorage.getItem("censo-email") || "";
        $("#lock-overlay").hidden = false;
        return;
    }
    if (!localStorage.getItem("censo-token")) {
        window.location.replace("/login");
        return;
    }
    window.addEventListener("censo:session-expired", () => {
        localStorage.setItem("censo-locked", "true");
        localStorage.removeItem("censo-token");
        $("#lock-overlay").hidden = false;
        $("#lock-email").value = currentUser?.email || localStorage.getItem("censo-email") || "";
        $("#lock-password").focus();
    });
    try {
        currentUser = await json("/auth/me");
        $("#usuario-nome").textContent = currentUser.nome;
        localStorage.setItem("censo-email", currentUser.email);
        const sessionConfig = await json("/auth/config");
        const idleSelect = $("#idle-time-select");
        const maxIdle = sessionConfig.session_idle_minutes;
        const idleChoices = [1, 5, 10, 15].filter((minutes) => minutes <= maxIdle);
        if (!idleChoices.length) idleChoices.push(maxIdle);
        idleSelect.replaceChildren(...idleChoices.map((minutes) => {
            const option = document.createElement("option");
            option.value = String(minutes);
            option.textContent = `${minutes} minuto${minutes === 1 ? "" : "s"}`;
            return option;
        }));
        await loadStats();
    } catch (error) {
        setNotice(error.message, true);
        return;
    }

    setTheme(localStorage.getItem("censo-theme") || "light");
    const storedIdle = localStorage.getItem("censo-idle-minutes");
    const availableIdle = Array.from($("#idle-time-select").options, (option) => option.value);
    const selectedIdle = availableIdle.includes(storedIdle) ? storedIdle : availableIdle.at(-1);
    $("#idle-time-select").value = selectedIdle;
    localStorage.setItem("censo-idle-minutes", selectedIdle);
    startInactivityLock();

    $("#logout-btn").addEventListener("click", async () => {
        try { await json("/auth/logout", { method: "POST" }); } finally {
            localStorage.removeItem("censo-token");
            localStorage.removeItem("censo-locked");
            window.location.replace("/login");
        }
    });
    document.querySelectorAll(".nav-item").forEach((button) => {
        button.addEventListener("click", () => showView(button.dataset.view).catch((error) => setNotice(error.message, true)));
    });
    $("#refresh-btn").addEventListener("click", () => refreshActiveView().catch((error) => setNotice(error.message, true)));
    $("#search-form").addEventListener("submit", (event) => {
        event.preventDefault();
        currentQuery = $("#search-input").value.trim();
        currentPage = 1;
        loadPeople().catch((error) => setNotice(error.message, true));
    });
    $("#status-filter").addEventListener("change", () => {
        currentStatus = $("#status-filter").value;
        currentPage = 1;
        if (currentView === "people") loadPeople().catch((error) => setNotice(error.message, true));
    });
    $("#previous-page").addEventListener("click", () => { currentPage--; loadPeople().catch((error) => setNotice(error.message, true)); });
    $("#next-page").addEventListener("click", () => { currentPage++; loadPeople().catch((error) => setNotice(error.message, true)); });
    $("#people-rows").addEventListener("click", (event) => handleTableAction(event).catch((error) => setNotice(error.message, true)));
    $("#add-person").addEventListener("click", () => openPersonDialog());
    $("#person-form").addEventListener("submit", (event) => savePerson(event).catch((error) => setNotice(error.message, true)));
    $("#report-form").addEventListener("submit", (event) => {
        event.preventDefault();
        reportQuery = $("#report-search").value.trim();
        reportStatus = $("#report-status").value;
        loadReportSummary().catch((error) => setNotice(error.message, true));
    });
    $("#person-photo").addEventListener("change", () => {
        try { downloadPhotoPreview($("#person-photo").files[0]); } catch (error) { setNotice(error.message, true); }
    });
    $("#theme-select").addEventListener("change", (event) => setTheme(event.target.value));
    $("#idle-time-select").addEventListener("change", (event) => {
        localStorage.setItem("censo-idle-minutes", event.target.value);
        startInactivityLock();
    });
    $("#export-csv").addEventListener("click", () => exportReport().catch((error) => setNotice(error.message, true)));
    $("#print-report").addEventListener("click", () => exportPdf().catch((error) => setNotice(error.message, true)));
    $("#terminal-clear").addEventListener("click", () => { $("#terminal-output").replaceChildren(); });
    if (terminal) terminal.write("Terminal administrativo seguro. Digite ajuda para listar os comandos.");
    window.setInterval(() => {
        if (document.visibilityState === "visible" && $("#lock-overlay").hidden) {
            refreshActiveView().catch((error) => setNotice(error.message, true));
        }
    }, 30_000);
    document.querySelectorAll("[data-close-dialog]").forEach((button) => {
        button.addEventListener("click", () => document.getElementById(button.dataset.closeDialog).close());
    });
    $("#action-form").addEventListener("submit", (event) => {
        event.preventDefault();
        resolveActionDialog?.({
            confirmed: true,
            reason: $("#action-reason").value.trim(),
        });
        resolveActionDialog = null;
        $("#action-dialog").close();
    });
    $("#action-cancel").addEventListener("click", () => {
        resolveActionDialog?.({ confirmed: false });
        resolveActionDialog = null;
        $("#action-dialog").close();
    });
    $("#action-dialog").addEventListener("close", () => {
        resolveActionDialog?.({ confirmed: false });
        resolveActionDialog = null;
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && $("#action-dialog").open) {
            resolveActionDialog?.({ confirmed: false });
            resolveActionDialog = null;
        }
    });
}

init();
