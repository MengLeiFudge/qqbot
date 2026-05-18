from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

_WRITE_LOCKS: dict[Path, threading.Lock] = {}
_WRITE_LOCKS_GUARD = threading.Lock()


def load_json_array(path: Path) -> list[Any]:
    with get_file_lock(path):
        text = path.read_text(encoding="utf-8")
    try:
        raw_records = json.loads(text)
    except json.JSONDecodeError:
        raw_records = _load_recoverable_json_array(text)
    return raw_records if isinstance(raw_records, list) else []


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with get_file_lock(path):
        temp_path = path.with_name(f".{path.name}.{threading.get_ident()}.{uuid4().hex}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


def get_file_lock(path: Path) -> threading.Lock:
    key = path.resolve()
    with _WRITE_LOCKS_GUARD:
        return _WRITE_LOCKS.setdefault(key, threading.Lock())


def _load_recoverable_json_array(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    raw_records, _end = decoder.raw_decode(text)
    return raw_records if isinstance(raw_records, list) else []
