from __future__ import annotations

import importlib.util
from pathlib import Path

from qqbot.features.ai.user_style_store import AiUserStyleStore
from qqbot.plugins.ai import build_ai_system_context
from qqbot.config import RuntimeSettings


ROOT = Path(__file__).resolve().parents[2]


def _load_persona_sync_module():
    module_path = ROOT / "scripts" / "sync-astrbot-personas.py"
    spec = importlib.util.spec_from_file_location("sync_astrbot_personas", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_astrbot_personas_remove_serious_mode_and_keep_watercooler_style() -> None:
    module = _load_persona_sync_module()
    combined = "\n".join(module.PERSONAS.values())

    assert "严肃模式" not in combined
    assert "哼...喵" not in combined
    assert "QQ 水群语气" in combined
    assert "这个月一顿饭都没吃" in combined
    assert "技术、代码、报错和配置问题也保持" in combined
    assert "频繁艾特" in combined
    assert "深夜" in combined


def test_astrbot_reply_style_guard_keeps_persona_for_technical_help() -> None:
    combined = (ROOT / "astrbot-local-plugins" / "astrbot_plugin_reply_style_guard" / "main.py").read_text(
        encoding="utf-8"
    )

    assert "严肃模式" not in combined
    assert "哼...喵" not in combined
    assert "QQ 水群" in combined
    assert "技术、代码、报错和配置问题也要保留当前 bot 人设" in combined
    assert "群聊吹水处理" in combined
    assert "平时不要主动说“喵”" in combined


def test_nonebot_persona_keeps_watercooler_style_for_technical_help(tmp_path: Path) -> None:
    settings = RuntimeSettings(data_root=tmp_path, ai_bot_name="😇棉花糖😇")
    system_context = build_ai_system_context(settings)
    style_context = AiUserStyleStore(tmp_path, bot_name="😇棉花糖😇").build_context("1001")
    combined = f"{system_context}\n{style_context}"

    assert "严肃模式" not in combined
    assert "严肃收敛" not in combined
    assert "水群" in combined
    assert "技术、配置、报错和代码求助也保持呆萌姐姐人设" in combined
    assert "复读、频繁艾特、怪图/表情包和深夜修仙" in combined
