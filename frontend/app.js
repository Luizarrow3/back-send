const page = document.body.dataset.page;

function getToken() {
    return localStorage.getItem("censo-token");
}

function setError(message) {
    const errorEl = document.getElementById("login-error");
    if (errorEl) {
        errorEl.textContent = message;
    }
}

function redirectToPainel() {
    window.location.href = "/painel";
}

async function login(usuario, senha) {
    const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: usuario, password: senha }),
    });

    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.detail || "Credenciais inválidas");
    }

    localStorage.setItem("censo-token", data.access_token);
    localStorage.setItem("censo-email", usuario);
    redirectToPainel();
}

function renderPessoas(pessoas) {
    const lista = document.getElementById("lista-pessoas");
    if (!lista) return;

    if (!pessoas.length) {
        lista.innerHTML = '<div class="card"><p class="muted">Nenhuma pessoa encontrada.</p></div>';
        return;
    }

    lista.innerHTML = pessoas.map((pessoa) => `
        <article class="pessoa">
            <div class="row">
                <div>
                    <h3>${pessoa.nome}</h3>
                    <div class="muted">CPF: ${pessoa.cpf_mascarado || pessoa.cpf}</div>
                </div>
                <span class="badge">${pessoa.status}</span>
            </div>
            <p class="muted">Sexo: ${pessoa.sexo} | Nascimento: ${pessoa.data_nascimento}</p>
        </article>
    `).join("");
}

async function carregarPainel() {
    const token = getToken();
    const usuarioNome = document.getElementById("usuario-nome");
    const lista = document.getElementById("lista-pessoas");

    if (!token) {
        window.location.href = "/login";
        return;
    }

    try {
        const meResponse = await fetch("/auth/me", {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!meResponse.ok) {
            throw new Error("Sessão inválida");
        }
        const user = await meResponse.json();
        if (usuarioNome) {
            usuarioNome.textContent = user.nome || user.email;
        }
    } catch (error) {
        localStorage.removeItem("censo-token");
        window.location.href = "/login";
        return;
    }

    try {
        const response = await fetch("/pessoas", {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
            throw new Error("Falha ao carregar pessoas");
        }
        const data = await response.json();
        renderPessoas(data);
    } catch (error) {
        if (lista) {
            lista.innerHTML = `<div class="card"><p class="error">${error.message}</p></div>`;
        }
    }
}

async function buscarPessoas(termo) {
    const token = getToken();
    if (!token) {
        window.location.href = "/login";
        return;
    }

    const params = new URLSearchParams();
    if (termo.trim()) {
        params.set("nome", termo.trim());
    }

    const url = params.toString() ? `/pessoas/search?${params}` : "/pessoas";
    const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
        throw new Error("Busca falhou");
    }

    const data = await response.json();
    renderPessoas(data);
}

if (page === "login") {
    const form = document.getElementById("login-form");
    if (form) {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const email = document.getElementById("email").value.trim();
            const password = document.getElementById("password").value;
            setError("");

            try {
                await login(email, password);
            } catch (error) {
                setError(error.message);
            }
        });
    }
}

if (page === "painel") {
    const logoutBtn = document.getElementById("logout-btn");
    const refreshBtn = document.getElementById("refresh-btn");
    const searchForm = document.getElementById("search-form");

    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            localStorage.removeItem("censo-token");
            window.location.href = "/login";
        });
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", carregarPainel);
    }

    if (searchForm) {
        searchForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const input = document.getElementById("search-input");
            try {
                await buscarPessoas(input.value || "");
            } catch (error) {
                const lista = document.getElementById("lista-pessoas");
                if (lista) {
                    lista.innerHTML = `<div class="card"><p class="error">${error.message}</p></div>`;
                }
            }
        });
    }

    carregarPainel();
}
