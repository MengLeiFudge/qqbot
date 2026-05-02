from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.feature_catalog import (
    build_feature_menu_text,
    build_group_menu_text,
    get_feature_by_index,
    get_feature_by_menu_key,
    list_visible_features,
)


def test_visible_features_are_sorted_by_index() -> None:
    features = list_visible_features()

    assert features[0].index == 1
    assert features[0].name == "随机复读"
    assert [feature.index for feature in features] == [1, 2, 3, 11, 12, 13, 16]
    assert features[-2].index == 13
    assert features[-2].name == "Arc"
    assert features[-1].index == 16
    assert features[-1].name == "异形工厂"


def test_get_feature_by_index_returns_expected_feature() -> None:
    feature = get_feature_by_index(3)

    assert feature is not None
    assert feature.name == "Lolicon美图"


def test_get_feature_by_menu_key_returns_arc_aliases() -> None:
    assert get_feature_by_menu_key("13").name == "Arc"
    assert get_feature_by_menu_key("arc").name == "Arc"
    assert get_feature_by_menu_key("arcaea").name == "Arc"
    assert get_feature_by_menu_key("不存在") is None


def test_build_group_menu_text_contains_status_lines() -> None:
    menu_text = build_group_menu_text(
        {
            1: True,
            2: False,
            3: True,
        }
    )

    assert "本群功能开启情况如下：" in menu_text
    assert "1.随机复读：开启" in menu_text
    assert "2.随机禁言：关闭" in menu_text
    assert "3.Lolicon美图：开启" in menu_text
    assert "4.智能问答" not in menu_text
    assert "13.Arc：关闭" in menu_text
    assert "tips：【菜单+功能序号】获得对应功能菜单" in menu_text


def test_build_feature_menu_text_returns_arc_commands() -> None:
    menu_text = build_feature_menu_text(13)

    assert menu_text is not None
    assert "Arc 功能菜单" in menu_text
    assert "arctj10.5" in menu_text
    assert "zm" in menu_text
    assert "开*" in menu_text
    assert "archd" in menu_text
    assert "xz / arcxz" in menu_text


def test_build_feature_menu_text_returns_kun_commands() -> None:
    menu_text = build_feature_menu_text(11)

    assert menu_text is not None
    assert "养鲲 功能菜单" in menu_text
    assert "摸鲲" in menu_text
    assert "属性" in menu_text
    assert "洗练攻击10" in menu_text
    assert "等级排行" in menu_text
    assert "赠送 @对方 100" in menu_text
