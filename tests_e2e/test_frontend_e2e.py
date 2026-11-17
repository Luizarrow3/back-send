import re

from playwright.sync_api import Page, expect

FRONTEND_URL = "http://127.0.0.1:3000/painel"
MOCK_PERSON = {
    "id": 7,
    "nome": "Maria de Exemplo",
    "cpf_mascarado": "***.***.123-**",
    "sexo": "FEMININO",
    "data_nascimento": "1990-01-01",
    "status": "PENDENTE",
}


def _mock_panel_api(page: Page) -> None:
    page.add_init_script("localStorage.setItem('censo-token', 'e2e-token')")
    page.route(
        "**/auth/me",
        lambda route: route.fulfill(
            status=200,
            json={"id": 1, "email": "admin@local.test", "nome": "Admin", "perfil": "ADMIN"},
        ),
    )
    page.route(
        "**/auth/config",
        lambda route: route.fulfill(
            status=200,
            json={"session_idle_minutes": 15, "redis_sessions_enabled": True},
        ),
    )
    page.route(
        "**/pessoas/paginado*",
        lambda route: route.fulfill(
            status=200,
            json={"items": [MOCK_PERSON], "total": 1, "page": 1, "page_size": 10, "pages": 1},
        ),
    )
    page.route(
        "**/resumo",
        lambda route: route.fulfill(
            status=200,
            json={
                "total_pessoas": 1,
                "pendentes": 1,
                "validados_biometria": 0,
                "idade_media": 36,
                "por_status": {"PENDENTE": 1},
            },
        ),
    )


def test_panel_displays_separate_dashboard_and_people_views(page: Page) -> None:
    _mock_panel_api(page)
    page.goto(FRONTEND_URL)

    expect(page).to_have_title(re.compile("Censo Previdenciário"))
    expect(page.locator("#page-title")).to_have_text("Dashboard")
    expect(page.locator("#view-people")).to_be_hidden()
    expect(page.locator("#metric-total")).to_have_text("1")
    page.get_by_role("button", name="Recenseados").click()
    expect(page.locator("#page-title")).to_have_text("Recenseados")
    expect(page.locator("#people-rows")).to_contain_text("Maria de Exemplo")
    expect(page.locator("#view-dashboard")).to_be_hidden()


def test_theme_preference_persists_and_terminal_runs_help(page: Page) -> None:
    _mock_panel_api(page)
    page.goto(FRONTEND_URL)
    page.get_by_role("button", name="Configurações").click()
    page.select_option("#theme-select", "dark")
    expect(page.locator("body")).to_have_class(re.compile("dark"))
    page.reload()
    expect(page.locator("body")).to_have_class(re.compile("dark"))

    page.get_by_role("button", name="Dashboard").click()
    page.locator("details summary").click()
    page.fill("#terminal-input", "ajuda")
    page.click("#terminal-form button[type=submit]")
    expect(page.locator("#terminal-output")).to_contain_text("Comandos:")


def test_locked_screen_requires_reauthentication(page: Page) -> None:
    _mock_panel_api(page)
    page.add_init_script(
        "if (!sessionStorage.getItem('e2e-lock-set')) {"
        "localStorage.setItem('censo-locked', 'true');"
        "sessionStorage.setItem('e2e-lock-set', 'true');}"
    )
    page.route(
        "**/auth/login",
        lambda route: route.fulfill(status=200, json={"access_token": "unlocked-token", "token_type": "bearer"}),
    )
    page.goto(FRONTEND_URL)
    expect(page.locator("#lock-overlay")).to_be_visible()
    page.fill("#lock-email", "admin@local.test")
    page.fill("#lock-password", "correct-password")
    page.click("#lock-form button[type=submit]")

    expect(page.locator("#lock-overlay")).to_be_hidden()
    expect(page.locator("#metric-total")).to_have_text("1")
