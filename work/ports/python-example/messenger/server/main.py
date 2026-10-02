from __future__ import annotations
import asyncio
import logging

import uvicorn

from .config import settings
from .db import init_db
from .api import app
from .ws import start_ws_server


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    init_db()

    http_port = settings.PORT
    ws_port = http_port + 1   # 8001

    print(f"\n  Мессенджер запущен")
    print(f"  ─ HTTP + UI : http://localhost:{http_port}")
    print(f"  ─ WebSocket : ws://localhost:{ws_port}")
    print(f"  ─ SMTP      : {'—' if not settings.SMTP_HOST else settings.SMTP_HOST}")
    print(f"  ─ DB        : {settings.DB_PATH}\n")

    # FastAPI в фоне
    http_task = asyncio.create_task(
        uvicorn.Server(uvicorn.Config(
            app, host=settings.HOST, port=http_port,
            log_level="warning", access_log=False,
        )).serve()
    )

    # WebSocket-сервер в фоне
    ws_task = asyncio.create_task(start_ws_server(settings.HOST, ws_port))

    try:
        await asyncio.gather(http_task, ws_task)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено.")