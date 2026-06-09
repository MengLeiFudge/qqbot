from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_export_module():
    module_path = ROOT / "scripts" / "export-astrbot-config-examples.py"
    spec = importlib.util.spec_from_file_location("export_astrbot_config_examples", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sanitize_config_drops_llm_routing_and_masks_secrets() -> None:
    module = load_export_module()

    sanitized = module.sanitize_config(
        {
            "provider_sources": [{"id": "openai", "key": "secret", "api_base": "https://example.invalid"}],
            "provider_settings": {"default_provider_id": "openai/model", "default_personality": "恶魔棉花糖"},
            "platform": [{"id": "棉花糖", "ws_reverse_port": 6200, "ws_reverse_token": "secret"}],
            "plugin_set": {"astrbot_plugin_qqbot_features": True},
            "api_key": "secret",
            "feature_mode": "dual",
            "custom_headers": {"Authorization": "Bearer secret"},
        }
    )

    assert "provider_sources" not in sanitized
    assert "provider_settings" not in sanitized
    assert "custom_headers" not in sanitized
    assert sanitized["platform"][0]["id"] == "棉花糖"
    assert sanitized["platform"][0]["ws_reverse_port"] == 6200
    assert sanitized["platform"][0]["ws_reverse_token"] == ""
    assert sanitized["plugin_set"] == {"astrbot_plugin_qqbot_features": True}
    assert sanitized["api_key"] == ""
    assert sanitized["feature_mode"] == "dual"


def test_export_examples_writes_sanitized_configs_and_personas(tmp_path: Path) -> None:
    module = load_export_module()
    data_root = tmp_path / "data"
    config_root = data_root / "config"
    output_root = tmp_path / "out"
    config_root.mkdir(parents=True)

    (data_root / "cmd_config.json").write_text(
        json.dumps(
            {
                "platform": [{"id": "棉花糖", "ws_reverse_port": 6200, "ws_reverse_token": "secret"}],
                "provider_sources": [{"id": "openai", "key": "secret"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (config_root / "astrbot_plugin_qqbot_features_config.json").write_text(
        json.dumps({"api_key": "secret", "feature_mode": "dual"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (config_root / "abconf_should_skip.json").write_text("{}", encoding="utf-8")

    database_path = data_root / "data_v4.db"
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
        insert into personas (created_at, updated_at, persona_id, system_prompt, begin_dialogs, tools, skills, sort_order)
        values ('now', 'now', '恶魔棉花糖', '只来自 WebUI 的人格', '[]', '[]', '[]', 1)
        """
    )
    connection.commit()
    connection.close()

    module.export_examples(data_root, output_root)

    cmd_config = json.loads((output_root / "cmd_config.example.json").read_text(encoding="utf-8"))
    plugin_config = json.loads(
        (output_root / "plugins" / "astrbot_plugin_qqbot_features.example.json").read_text(encoding="utf-8")
    )
    personas = json.loads((output_root / "personas.example.json").read_text(encoding="utf-8"))

    assert "provider_sources" not in cmd_config
    assert cmd_config["platform"][0]["ws_reverse_token"] == ""
    assert plugin_config == {"api_key": "", "feature_mode": "dual"}
    assert not (output_root / "plugins" / "abconf_should_skip.example.json").exists()
    assert personas[0]["persona_id"] == "恶魔棉花糖"
    assert personas[0]["system_prompt"] == "只来自 WebUI 的人格"
