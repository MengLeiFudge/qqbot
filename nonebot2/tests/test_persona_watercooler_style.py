from __future__ import annotations

import sqlite3
from pathlib import Path

from qqbot.features.ai.user_style_store import AiUserStyleStore
from qqbot.plugins.ai import build_ai_system_context
from qqbot.config import RuntimeSettings


def test_astrbot_personas_are_exported_from_database_not_sync_script(tmp_path: Path) -> None:
    database_path = tmp_path / "data_v4.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        create table personas (
            created_at text,
            updated_at text,
            id integer primary key,
            persona_id text unique not null,
            system_prompt text not null,
            begin_dialogs text,
            tools text,
            skills text,
            custom_error_message text,
            folder_id text,
            sort_order integer not null
        )
        """
    )
    connection.execute(
        """
        insert into personas (created_at, updated_at, persona_id, system_prompt, sort_order)
        values ('now', 'now', '天使棉花糖', ?, 1)
        """,
        (
            "QQ 水群语气；这个月一顿饭都没吃按玩梗处理；"
            "技术、代码、报错和配置问题也保持当前人格；频繁艾特和深夜修仙短句接梗。",
        ),
    )
    connection.commit()
    connection.close()

    from test_export_astrbot_config_examples import load_export_module

    personas = load_export_module().export_personas(database_path)
    combined = "\n".join(persona["system_prompt"] for persona in personas)

    assert "严肃模式" not in combined
    assert "哼...喵" not in combined
    assert "QQ 水群语气" in combined
    assert "这个月一顿饭都没吃" in combined
    assert "技术、代码、报错和配置问题也保持" in combined
    assert "频繁艾特" in combined
    assert "深夜" in combined


def test_astrbot_plugins_do_not_embed_persona_prompt_text() -> None:
    root = Path(__file__).resolve().parents[2]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "astrbot-local-plugins" / "astrbot_plugin_qqbot_features" / "main.py",
            root / "astrbot-local-plugins" / "astrbot_plugin_qqbot_features" / "twin_interaction_logic.py",
        )
    )

    assert "严肃模式" not in combined
    assert "哼...喵" not in combined
    assert "平时不要主动说“喵”" not in combined
    assert "QQ 水群语气" not in combined
    assert "技术、代码、报错和配置问题也要保留当前 bot 人设" not in combined


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
