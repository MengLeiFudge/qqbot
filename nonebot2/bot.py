from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import nonebot
import uvicorn

from qqbot.bootstrap import bootstrap
from qqbot.config import load_settings

ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / ".env", override=False)
settings = load_settings()
settings.data_root.mkdir(parents=True, exist_ok=True)
(settings.data_root / "qqbot.pid").write_text(str(os.getpid()), encoding="utf-8")
bootstrap(settings)
app = nonebot.get_asgi()


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
