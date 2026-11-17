from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401
from app.auth import ensure_admin_user
from app.database import SessionLocal, Base, engine
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.documentos import router as documentos_router
from app.routers.estatisticas import router as estatisticas_router
from app.routers.pessoas import router as pessoas_router
from app.routers.status import router as status_router

Base.metadata.create_all(bind=engine)

db = SessionLocal()
ensure_admin_user(db)
db.close()

app = FastAPI(
    title="Censo Previdenciário",
    description="API base do MVP para recenseamento previdenciário.",
    version="0.1.0",
)

app.include_router(auth_router, prefix="/auth")
app.include_router(pessoas_router, prefix="/pessoas")
app.include_router(status_router, prefix="/pessoas")
app.include_router(documentos_router, prefix="/pessoas")
app.include_router(admin_router, prefix="/admin")
app.include_router(estatisticas_router, prefix="")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login")


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/painel", include_in_schema=False)
def painel_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "painel.html")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "censo-previdenciario",
    }
