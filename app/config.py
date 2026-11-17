import os
import tempfile
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "Censo Previdenciário")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./censo.db")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    SESSION_IDLE_MINUTES: int = int(os.getenv("SESSION_IDLE_MINUTES", "15"))
    UPLOAD_DIR: Path = Path(
        os.getenv("UPLOAD_DIR", str(Path(tempfile.gettempdir()) / "censo_uploads"))
    )
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@local.test")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123456")

    def __init__(self) -> None:
        if self.SESSION_IDLE_MINUTES < 1:
            raise ValueError("SESSION_IDLE_MINUTES deve ser maior que zero")
        if self.APP_ENV == "production" and self.JWT_SECRET_KEY == "dev-secret-key":
            raise ValueError("JWT_SECRET_KEY deve ser configurada em produção")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
