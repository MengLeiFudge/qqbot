from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_array(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8")
    try:
        raw_records = json.loads(text)
    except json.JSONDecodeError:
        raw_records = _load_recoverable_json_array(text)
    return raw_records if isinstance(raw_records, list) else []


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _load_recoverable_json_array(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    raw_records, _end = decoder.raw_decode(text)
    return raw_records if isinstance(raw_records, list) else []
