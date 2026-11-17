import os

structure = {
    "frontend": {
        "index.html": """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gestão de Itens - Microserviço</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen transition-colors duration-200" id="app-body">
    <header class="bg-blue-700 text-white shadow-md">
        <div class="max-w-4xl mx-auto px-6 py-4 flex justify-between items-center">
            <h1 class="text-xl font-bold tracking-tight">Painel de Gestão de Itens</h1>
            <button id="theme-toggle" class="px-3 py-1.5 bg-blue-800 hover:bg-blue-900 rounded text-sm font-medium">
                Alternar Tema
            </button>
        </div>
    </header>

    <main class="max-w-4xl mx-auto px-6 py-8 space-y-8">
        <!-- Formulário de Cadastro -->
        <section class="bg-white p-6 rounded-lg shadow-sm border border-slate-200" id="form-section">
            <h2 class="text-lg font-semibold text-blue-900 mb-4">Cadastrar Novo Item</h2>
            <form id="item-form" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                    <label for="item-id" class="block text-sm font-medium text-slate-700 mb-1">ID</label>
                    <input type="number" id="item-id" required placeholder="Ex: 3"
                        class="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-600">
                </div>
                <div>
                    <label for="item-name" class="block text-sm font-medium text-slate-700 mb-1">Nome</label>
                    <input type="text" id="item-name" required placeholder="Nome do item"
                        class="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-600">
                </div>
                <div>
                    <label for="item-desc" class="block text-sm font-medium text-slate-700 mb-1">Descrição</label>
                    <input type="text" id="item-desc" placeholder="Opcional"
                        class="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-600">
                </div>
                <div class="md:col-span-3 flex justify-end">
                    <button type="submit" id="submit-btn"
                        class="bg-blue-700 hover:bg-blue-800 text-white font-medium px-5 py-2 rounded transition">
                        Adicionar Item
                    </button>
                </div>
            </form>
            <p id="feedback-msg" class="mt-3 text-sm font-medium hidden"></p>
        </section>

        <!-- Listagem de Itens -->
        <section class="bg-white p-6 rounded-lg shadow-sm border border-slate-200" id="list-section">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-lg font-semibold text-blue-900">Itens Cadastrados</h2>
                <button id="refresh-btn" class="text-sm text-blue-700 hover:underline font-medium">
                    Atualizar Lista
                </button>
            </div>
            <ul id="items-list" class="divide-y divide-slate-200">
                <!-- Preenchido dinamicamente via JS -->
            </ul>
        </section>
    </main>

    <script src="app.js"></script>
</body>
</html>
""",
        "app.js": """const API_URL = "http://127.0.0.1:8000/api/v1/items";

const form = document.getElementById("item-form");
const itemsList = document.getElementById("items-list");
const feedbackMsg = document.getElementById("feedback-msg");
const refreshBtn = document.getElementById("refresh-btn");
const themeToggle = document.getElementById("theme-toggle");

// Alternância de tema claro/escuro
themeToggle.addEventListener("click", () => {
    const body = document.getElementById("app-body");
    body.classList.toggle("bg-slate-900");
    body.classList.toggle("text-slate-100");
});

function showFeedback(text, isError = false) {
    feedbackMsg.textContent = text;
    feedbackMsg.className = `mt-3 text-sm font-medium ${isError ? "text-red-600" : "text-green-600"}`;
    feedbackMsg.classList.remove("hidden");
}

async function fetchItems() {
    itemsList.innerHTML = "<li class='py-3 text-slate-500 text-sm'>Carregando itens...</li>";
    try {
        const res = await fetch(API_URL);
        if (!res.ok) throw new Error("Falha ao buscar itens");
        const data = await res.json();
        renderItems(data);
    } catch (err) {
        itemsList.innerHTML = `<li class='py-3 text-red-600 text-sm'>Erro de conexão com a API: ${err.message}</li>`;
    }
}

function renderItems(items) {
    if (!items.length) {
        itemsList.innerHTML = "<li class='py-3 text-slate-500 text-sm'>Nenhum item encontrado.</li>";
        return;
    }
    itemsList.innerHTML = items.map(item => `
        <li class="py-3 flex justify-between items-center" data-testid="item-row">
            <div>
                <span class="font-semibold text-blue-800">#${item.id} - ${item.name}</span>
                <p class="text-sm text-slate-500">${item.description || "Sem descrição"}</p>
            </div>
        </li>
    `).join("");
}

form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
        id: Number(document.getElementById("item-id").value),
        name: document.getElementById("item-name").value.trim(),
        description: document.getElementById("item-desc").value.trim() || null
    };

    try {
        const res = await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "Erro ao cadastrar");
        }
        showFeedback("Item cadastrado com sucesso!");
        form.reset();
        await fetchItems();
    } catch (err) {
        showFeedback(err.message, true);
    }
});

refreshBtn.addEventListener("click", fetchItems);
document.addEventListener("DOMContentLoaded", fetchItems);
"""
    },
    "tests_e2e": {
        "__init__.py": "",
        "conftest.py": """import pytest
import subprocess
import time
import urllib.request

@pytest.fixture(scope="session", autouse=True)
def start_frontend_server():
    # Sobe um servidor HTTP estático na porta 3000 para os testes E2E
    proc = subprocess.Popen(
        ["python", "-m", "http.server", "3000", "--directory", "frontend"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(1.5)
    yield
    proc.terminate()
    proc.wait()
""",
        "test_frontend_e2e.py": """import re
from playwright.sync_api import Page, expect

FRONTEND_URL = "http://127.0.0.1:3000"

def test_page_title_and_structure(page: Page):
    page.goto(FRONTEND_URL)
    expect(page).to_have_title(re.compile("Gestão de Itens"))
    expect(page.locator("h1")).to_have_text("Painel de Gestão de Itens")
    expect(page.locator("#item-form")).to_be_visible()

def test_theme_toggle(page: Page):
    page.goto(FRONTEND_URL)
    body = page.locator("#app-body")
    expect(body).not_to_have_class(re.compile("bg-slate-900"))
    page.click("#theme-toggle")
    expect(body).to_have_class(re.compile("bg-slate-900"))

def test_create_item_flow_with_mocked_api(page: Page):
    # Intercepta chamadas à API para testar o frontend de forma isolada e determinística
    mock_items = [{"id": 1, "name": "Item Inicial", "description": "Mock"}]

    def handle_route(route):
        if route.request.method == "GET":
            route.fulfill(status=200, json=mock_items)
        elif route.request.method == "POST":
            new_item = route.request.post_data_json
            mock_items.append(new_item)
            route.fulfill(status=201, json=new_item)

    page.route("**/api/v1/items", handle_route)
    page.goto(FRONTEND_URL)

    # Verifica carregamento inicial
    expect(page.get_by_test_id("item-row")).to_have_count(1)

    # Preenche e submete o formulário
    page.fill("#item-id", "10")
    page.fill("#item-name", "Novo Item Playwright")
    page.fill("#item-desc", "Teste automatizado E2E")
    page.click("#submit-btn")

    # Valida feedback e atualização da lista na tela
    expect(page.locator("#feedback-msg")).to_have_text("Item cadastrado com sucesso!")
    expect(page.get_by_test_id("item-row")).to_have_count(2)
    expect(page.locator("#items-list")).to_contain_text("#10 - Novo Item Playwright")
"""
    },
    "requirements-e2e.txt": """pytest>=8.0.0
playwright>=1.42.0
pytest-playwright>=0.4.4
"""
}

def create_structure(base_path, blueprint):
    for name, content in blueprint.items():
        current_path = os.path.join(base_path, name)
        if isinstance(content, dict):
            os.makedirs(current_path, exist_ok=True)
            create_structure(current_path, content)
        else:
            with open(current_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Criado arquivo: {current_path}")

if __name__ == "__main__":
    print("Gerando estrutura Frontend + Testes E2E com Playwright...")
    create_structure(".", structure)
    print("Estrutura criada com sucesso!")