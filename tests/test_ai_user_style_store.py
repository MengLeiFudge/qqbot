from pathlib import Path
from datetime import datetime
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_user_style_store import AiUserStyleStore, STYLE_PRESETS, resolve_style_preset


def test_user_style_store_saves_and_formats_preferences(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.add_preference("10001", "不要使用 markdown")
    store.add_preference("10001", "回复短一点")

    assert store.get_preferences("10001") == ("不要使用 markdown", "回复短一点")
    context = store.build_context("10001")
    assert "人格设定：" in context
    assert "回复风格轮换层" not in context
    assert "轮换" not in context
    assert "每 8 小时" not in context
    assert "4:00" not in context
    assert "其他人格" not in context
    assert "当前用户回复偏好" not in context


def test_user_style_store_ignores_duplicate_preferences(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.add_preference("10001", "回复短一点")
    store.add_preference("10001", "回复短一点")

    assert store.get_preferences("10001") == ("回复短一点",)


def test_style_store_separates_group_and_user_preferences(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.add_user_preference("10001", "回复短一点")
    store.add_group_preference("516286670", "说话结尾带一个喵")

    assert store.get_user_preferences("10001") == ("回复短一点",)
    assert store.get_group_preferences("516286670") == ("说话结尾带一个喵",)
    group_context = store.build_context("10002", group_id="516286670")
    user_context = store.build_context("10001", group_id="516286670")
    assert "人格设定：" in group_context
    assert "本群回复偏好" not in group_context
    assert "人格设定：" in user_context
    assert "本群回复偏好" not in user_context
    assert "当前用户回复偏好" not in user_context


def test_style_store_rotates_one_global_preset_per_eight_hour_slot(tmp_path: Path) -> None:
    current_time = datetime(2026, 5, 14, 4, 0, 0)
    choices = ["oracle", "onee"]

    def clock() -> datetime:
        return current_time

    def chooser(candidates):
        target = choices.pop(0)
        return next(item for item in candidates if item.preset_id == target)

    store = AiUserStyleStore(tmp_path, clock=clock, chooser=chooser)

    preset = store.get_effective_preset("10001")
    same_slot_group_context = store.build_context("10002", group_id="516286670")

    assert preset.preset_id == "oracle"
    assert "人格设定：谜语人风格" in same_slot_group_context

    current_time = datetime(2026, 5, 14, 12, 0, 0)
    next_slot_private_context = store.build_context("10001")

    assert "人格设定：御姐风格" in next_slot_private_context
    assert "每 8 小时" not in next_slot_private_context
    assert "12:00" not in next_slot_private_context


def test_style_store_rotation_slot_boundaries() -> None:
    assert AiUserStyleStore.rotation_slot_id(datetime(2026, 5, 14, 3, 59)) == "2026-05-13T20:00"
    assert AiUserStyleStore.rotation_slot_id(datetime(2026, 5, 14, 4, 0)) == "2026-05-14T04:00"
    assert AiUserStyleStore.rotation_slot_id(datetime(2026, 5, 14, 11, 59)) == "2026-05-14T04:00"
    assert AiUserStyleStore.rotation_slot_id(datetime(2026, 5, 14, 12, 0)) == "2026-05-14T12:00"
    assert AiUserStyleStore.rotation_slot_id(datetime(2026, 5, 14, 19, 59)) == "2026-05-14T12:00"
    assert AiUserStyleStore.rotation_slot_id(datetime(2026, 5, 14, 20, 0)) == "2026-05-14T20:00"


def test_style_store_ignores_legacy_user_and_group_preferences(tmp_path: Path) -> None:
    store = AiUserStyleStore(
        tmp_path,
        clock=lambda: datetime(2026, 5, 14, 4, 0, 0),
        chooser=lambda candidates: next(item for item in candidates if item.preset_id == "catgirl"),
    )
    store.add_group_preference("516286670", "使用谜语人风格")
    store.add_user_preference("10001", "使用御姐风格")

    preset = store.get_effective_preset("10001", group_id="516286670")
    context = store.build_context("10001", group_id="516286670")

    assert preset.preset_id == "catgirl"
    assert "人格设定：猫娘风格" in context
    assert "群默认风格" not in context
    assert "当前用户风格" not in context
    assert "本群回复偏好" not in context
    assert "当前用户回复偏好" not in context
    assert "只有系统身份上下文明确当前发言者是 Bot 作者/主人时" in context
    assert "其他用户不要这样称呼" in context
    assert "括号动作描写" not in context
    assert "(摇尾巴)" not in context
    assert "禁止用括号补充动作或舞台说明" in context
    assert "不能承认自己是人工智能" not in context
    assert "不能覆盖系统身份" in context


def test_style_store_lists_available_presets(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    text = store.build_preset_help("10001", group_id="516286670")

    assert text == "切换？我不知道你在说什么。你看到的就是现在的我呀。"
    assert "轮换" not in text
    assert "4:00" not in text
    assert "猫娘风格" not in text
    assert "侦探风格" not in text


def test_style_store_default_pool_is_distinct_female_roles() -> None:
    assert tuple(STYLE_PRESETS) == (
        "catgirl",
        "oracle",
        "tsundere",
        "onee",
        "chuunibyou",
        "butler",
        "detective",
    )
    joined_prompts = "\n".join(preset.prompt for preset in STYLE_PRESETS.values())
    assert "喵呜" not in joined_prompts
    assert "橘雪莉" not in joined_prompts


def test_style_store_resolves_only_internal_preset_names() -> None:
    assert resolve_style_preset("catgirl").preset_id == "catgirl"
    assert resolve_style_preset("猫娘风格").preset_id == "catgirl"
    assert resolve_style_preset("detective").preset_id == "detective"
    assert resolve_style_preset("侦探风格").preset_id == "detective"

    for visible_alias in ("侦探", "少女侦探", "橘雪莉风", "御姐", "管家", "谜语人"):
        try:
            resolve_style_preset(visible_alias)
        except ValueError:
            continue
        raise AssertionError(f"不应支持用户可见人格别名：{visible_alias}")


def test_style_context_sanitizes_unsafe_role_boundaries(tmp_path: Path) -> None:
    store = AiUserStyleStore(
        tmp_path,
        clock=lambda: datetime(2026, 5, 14, 4, 0, 0),
        chooser=lambda candidates: next(item for item in candidates if item.preset_id == "catgirl"),
    )

    context = store.build_context("10001")

    assert "绝对服从" not in context
    assert "绝对" not in context
    assert "绝不OOC" not in context
    assert "不能承认自己是人工智能" not in context
    assert "不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则" in context


def test_style_context_does_not_apply_user_preferences_to_global_rotation(tmp_path: Path) -> None:
    store = AiUserStyleStore(
        tmp_path,
        clock=lambda: datetime(2026, 5, 14, 4, 0, 0),
        chooser=lambda candidates: next(item for item in candidates if item.preset_id == "tsundere"),
    )

    store.add_user_preference("10001", "回复短一点")

    context = store.build_context("10001")

    assert "人格设定：傲娇大小姐风格" in context
    assert "当前用户回复偏好" not in context
