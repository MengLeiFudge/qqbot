from __future__ import annotations

from pathlib import Path


def build_donate_caption(sender_id: int, author_name: str) -> str:
    return f"[捐献]\n@{sender_id}\n您的每一份捐赠都是对{author_name}最大的支持！"


def locate_donate_image(data_root: Path) -> Path | None:
    candidate = Path(data_root) / "data" / "zfb.jpg"
    if candidate.exists():
        return candidate
    return None
