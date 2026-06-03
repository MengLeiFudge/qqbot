from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.plugin_registry import (
    get_plugin_spec_by_id,
    get_plugin_spec_by_menu_key,
    list_visible_plugin_specs,
)


def test_visible_plugin_specs_are_sorted_by_name_and_unique() -> None:
    specs = list_visible_plugin_specs()

    assert [spec.name for spec in specs] == sorted(spec.name for spec in specs)
    assert "群管助手" in [spec.name for spec in specs]
    assert len({spec.id for spec in specs}) == len(specs)


def test_plugin_lookup_supports_name_alias_and_rejects_index() -> None:
    assert get_plugin_spec_by_id("arc").name == "Arc"
    assert get_plugin_spec_by_menu_key("arcaea").id == "arc"
    assert get_plugin_spec_by_menu_key("factorio").id == "factorio"
    assert get_plugin_spec_by_menu_key("太空时代").id == "factorio"
    assert get_plugin_spec_by_menu_key("群管").id == "group_assistant"
    assert get_plugin_spec_by_menu_key("11") is None
    assert get_plugin_spec_by_menu_key("不存在") is None


def test_ai_capabilities_are_explicitly_declared() -> None:
    arc = get_plugin_spec_by_id("arc")
    group_assistant = get_plugin_spec_by_id("group_assistant")
    shapez = get_plugin_spec_by_id("shapez")

    assert get_plugin_spec_by_id("qa") is None
    assert arc is not None
    assert group_assistant is not None
    assert shapez is not None
    assert arc.ai_capabilities == ("explain",)
    assert shapez.ai_capabilities == ("render",)
    assert {"i", "view", "chart", "chart1", "chart2", "p"} <= set(shapez.commands)
    assert group_assistant.ai_capabilities == ()
    assert group_assistant.admin_only is True
