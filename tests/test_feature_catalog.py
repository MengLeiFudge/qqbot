from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.feature_catalog import (
    build_feature_menu_text,
    build_group_menu_text,
    get_feature_by_menu_key,
    list_visible_features,
)


def test_visible_features_are_sorted_by_name() -> None:
    features = list_visible_features()

    assert [feature.name for feature in features] == sorted(feature.name for feature in features)
    assert any(feature.name == "群管助手" for feature in features)


def test_get_feature_by_menu_key_returns_group_assistant_aliases() -> None:
    feature = get_feature_by_menu_key("群管")

    assert feature is not None
    assert feature.plugin_id == "group_assistant"
    assert feature.name == "群管助手"
    assert feature.admin_only is True


def test_get_feature_by_menu_key_returns_arc_aliases() -> None:
    assert get_feature_by_menu_key("13") is None
    assert get_feature_by_menu_key("arc").name == "Arc"
    assert get_feature_by_menu_key("arcaea").name == "Arc"
    assert get_feature_by_menu_key("不存在") is None


def test_get_feature_by_menu_key_returns_factorio_aliases() -> None:
    assert get_feature_by_menu_key("factorio").name == "Factorio"
    assert get_feature_by_menu_key("太空时代").name == "Factorio"


def test_build_group_menu_text_contains_status_lines() -> None:
    menu_text = build_group_menu_text(
        {
            "arc": True,
            "group_assistant": False,
            "lolicon": True,
        }
    )

    assert "当前插件模块如下：" in menu_text
    assert "Arc：开启" in menu_text
    assert "群管助手：关闭" in menu_text
    assert "Lolicon美图：开启" in menu_text
    assert "4.智能问答" not in menu_text
    assert "tips：【菜单+模块名称】获得对应功能菜单" in menu_text
    assert "13.Arc" not in menu_text


def test_build_feature_menu_text_returns_arc_commands() -> None:
    menu_text = build_feature_menu_text("Arc")

    assert menu_text is not None
    assert "Arc 功能菜单" in menu_text
    assert "arctj10.5" in menu_text
    assert "zm" in menu_text
    assert "开*" in menu_text
    assert "archd" in menu_text
    assert "xz / arcxz" in menu_text


def test_build_feature_menu_text_returns_factorio_commands() -> None:
    menu_text = build_feature_menu_text("Factorio")

    assert menu_text is not None
    assert "Factorio 功能菜单" in menu_text
    assert "Factorio: Space Age Windows" in menu_text


def test_build_feature_menu_text_returns_kun_commands() -> None:
    menu_text = build_feature_menu_text("养鲲")

    assert menu_text is not None
    assert "养鲲 功能菜单" in menu_text
    assert "摸鲲" in menu_text
    assert "属性" in menu_text
    assert "洗练攻击10" in menu_text
    assert "等级排行" in menu_text
    assert "赠送 @对方 100" in menu_text
