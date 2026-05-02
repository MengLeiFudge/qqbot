from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.feature_catalog import get_feature_by_index
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


def test_group_feature_state_defaults_to_closed_and_can_be_saved(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    feature = get_feature_by_index(2)
    assert feature is not None

    assert store.get_group_feature_state(123456789, feature) is False

    store.set_group_feature_state(123456789, feature, True)
    assert store.get_group_feature_state(123456789, feature) is True


def test_arc_feature_reads_legacy_arc_keys(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    feature = get_feature_by_index(13)
    assert feature is not None
    path = tmp_path / "settings" / "func_state" / "123456789.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"Arc狼人杀": true}', encoding="utf-8")

    assert store.get_group_feature_state(123456789, feature) is True


def test_arc_feature_write_overrides_legacy_keys(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    feature = get_feature_by_index(13)
    assert feature is not None
    path = tmp_path / "settings" / "func_state" / "123456789.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"Arc查询": true, "Arc狼人杀": true}', encoding="utf-8")

    store.set_group_feature_state(123456789, feature, False)

    payload = path.read_text(encoding="utf-8")
    assert '"Arc": false' in payload
    assert "Arc查询" not in payload
    assert "Arc狼人杀" not in payload
    assert store.get_group_feature_state(123456789, feature) is False


def test_plugin_global_state_defaults_to_enabled(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.get_plugin_enabled("arc") is True
    assert store.list_plugin_states()["arc"] is True


def test_disabled_plugin_makes_group_feature_effectively_closed(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    feature = get_feature_by_index(13)
    assert feature is not None

    store.set_group_feature_state(123456789, feature, True)
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
