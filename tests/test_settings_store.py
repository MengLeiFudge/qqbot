from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.settings_store import SettingsStore


def test_author_is_always_bot_admin(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.is_bot_admin(605738729) is True
    assert store.is_bot_admin(123456) is False


def test_bot_admin_can_be_added_and_removed(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    store.set_bot_admin(10001, True)
    assert store.is_bot_admin(10001) is True

    store.set_bot_admin(10001, False)
    assert store.is_bot_admin(10001) is False


def test_bot_admin_or_self_allows_bot_self_id(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.is_bot_admin_or_self(114514, "114514") is True
    assert store.is_bot_admin_or_self(10001, "114514") is False


def test_group_feature_state_defaults_to_global_enabled(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    feature = get_feature_by_menu_key("群管助手")
    assert feature is not None

    assert store.get_group_feature_state(123456789, feature) is True


def test_group_feature_state_ignores_legacy_per_group_files(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    feature = get_feature_by_menu_key("Arc")
    assert feature is not None
    path = tmp_path / "settings" / "func_state" / "123456789.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"Arc狼人杀": false}', encoding="utf-8")

    assert store.get_group_feature_state(123456789, feature) is True


def test_set_group_feature_state_writes_global_plugin_state(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    feature = get_feature_by_menu_key("Arc")
    assert feature is not None

    store.set_group_feature_state(123456789, feature, False)

    assert store.get_plugin_enabled("arc") is False
    assert store.get_group_feature_state(123456789, feature) is False


def test_plugin_global_state_defaults_to_enabled(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.get_plugin_enabled("arc") is True
    assert store.list_plugin_states()["arc"] is True


def test_disabled_plugin_makes_group_feature_effectively_closed(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    feature = get_feature_by_menu_key("Arc")
    assert feature is not None

    assert store.get_group_feature_state(123456789, feature) is True

    store.set_plugin_enabled("arc", False)
    assert store.get_group_feature_state(123456789, feature) is False

    store.set_plugin_enabled("arc", True)
    assert store.get_group_feature_state(123456789, feature) is True


def test_ai_provider_defaults_and_can_be_saved(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.get_ai_provider("xiaomi") == "xiaomi"

    store.set_ai_provider("hicode")

    assert store.get_ai_provider("xiaomi") == "hicode"


def test_ai_output_mode_defaults_to_text_and_saves_group_private_preferences(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.get_ai_output_mode(group_id=516286670, user_id="605738729") == "text"
    assert store.get_ai_output_mode(group_id=None, user_id="605738729") == "text"

    store.set_group_ai_output_mode(516286670, "voice")
    store.set_user_ai_output_mode("605738729", "voice")

    assert store.get_ai_output_mode(group_id=516286670, user_id="10001") == "voice"
    assert store.get_ai_output_mode(group_id=None, user_id="605738729") == "voice"
    assert store.get_ai_output_mode(group_id=None, user_id="10001") == "text"

    store.set_group_ai_output_mode(516286670, "bad")
    assert store.get_ai_output_mode(group_id=516286670, user_id="10001") == "text"

    assert store.list_group_ai_output_modes() == {"516286670": "text"}


def test_set_group_ai_output_modes_writes_groups_in_one_file_update(tmp_path: Path, monkeypatch) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    store.set_group_ai_output_mode(10001, "voice")
    store.set_user_ai_output_mode("605738729", "voice")
    write_paths: list[Path] = []
    original_write_json = store._write_json

    def capture_write(path: Path, payload: dict[str, object]) -> None:
        write_paths.append(path)
        original_write_json(path, payload)

    monkeypatch.setattr(store, "_write_json", capture_write)

    store.set_group_ai_output_modes([10001, 10002, "10003"], "text")

    assert write_paths == [tmp_path / "settings" / "ai_output_mode.json"]
    assert store.list_group_ai_output_modes() == {
        "10001": "text",
        "10002": "text",
        "10003": "text",
    }
    assert store.get_ai_output_mode(group_id=None, user_id="605738729") == "voice"


def test_remove_group_scoped_settings_deletes_group_specific_entries(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    func_state = tmp_path / "settings" / "func_state" / "10001.json"
    func_state.parent.mkdir(parents=True)
    func_state.write_text('{"Arc": true}', encoding="utf-8")
    store.set_lolicon_config(10001, True, False)
    store.set_codex_group_binding(10001, "qqbot")
    proactive = tmp_path / "settings" / "ai_proactive.json"
    proactive.write_text('{"groups": {"10001": true, "10002": true}}', encoding="utf-8")

    removed = store.remove_group_scoped_settings(10001)

    assert str(func_state) in removed
    assert not func_state.exists()
    assert store.get_lolicon_config(10001) == (False, False)
    assert store.list_codex_group_bindings() == {}
    proactive_text = proactive.read_text(encoding="utf-8")
    assert '"10001"' not in proactive_text
    assert '"10002"' in proactive_text
