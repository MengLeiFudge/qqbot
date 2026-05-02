from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.plugin_registry import (
    get_plugin_spec_by_feature_index,
    get_plugin_spec_by_id,
    get_plugin_spec_by_menu_key,
    list_visible_plugin_specs,
)


def test_visible_plugin_specs_are_sorted_and_unique() -> None:
    specs = list_visible_plugin_specs()

    assert [spec.feature_index for spec in specs] == [1, 2, 3, 11, 12, 13, 16]
    assert len({spec.id for spec in specs}) == len(specs)
    assert len({spec.feature_index for spec in specs}) == len(specs)


def test_plugin_lookup_supports_id_index_and_menu_key() -> None:
    assert get_plugin_spec_by_id("arc").name == "Arc"
    assert get_plugin_spec_by_feature_index(13).id == "arc"
    assert get_plugin_spec_by_menu_key("arcaea").id == "arc"
    assert get_plugin_spec_by_menu_key("不存在") is None


def test_ai_capabilities_are_explicitly_declared() -> None:
    arc = get_plugin_spec_by_id("arc")
    group_control = get_plugin_spec_by_id("group_control")
    shapez = get_plugin_spec_by_id("shapez")

    assert get_plugin_spec_by_id("qa") is None
    assert arc is not None
    assert group_control is not None
    assert shapez is not None
    assert arc.ai_capabilities == ("explain",)
    assert shapez.ai_capabilities == ("render",)
    assert group_control.ai_capabilities == ()
