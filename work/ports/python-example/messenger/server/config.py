import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    DB_PATH: Path = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "chat.db")))
    WEB_DIR: Path = BASE_DIR / "web"

    TOKEN_SECRET: str = os.getenv("TOKEN_SECRET", "dev-secret-change-me")
    TOKEN_TTL: int = 60 * 60 * 24 * 30  # 30 дней

    CODE_TTL: int = 60 * 15             # 15 минут
    RESEND_DELAY: int = 60              # 1 минута

    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@messenger.local")
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "true").lower() in ("1", "true", "yes")

    APP_URL: str = os.getenv("APP_URL", "http://localhost:8000")

    PING_INTERVAL: int = 30
    PONG_TIMEOUT: int = 90

    ALLOWED_EMOJI: set[str] = {"👍","❤️","😂","😮","😢","🔥","🎉","👀"}

settings = Settings()
settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)