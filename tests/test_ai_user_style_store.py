from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_user_style_store import AiUserStyleStore, resolve_style_preset


def test_user_style_store_saves_and_formats_preferences(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.add_preference("10001", "不要使用 markdown")
    store.add_preference("10001", "回复短一点")

    assert store.get_preferences("10001") == ("不要使用 markdown", "回复短一点")
    context = store.build_context("10001")
    assert "回复风格预设层：猫娘风格" in context
    assert "当前用户回复偏好：不要使用 markdown；回复短一点" in context


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
    assert "回复风格预设层：猫娘风格" in group_context
    assert "本群回复偏好：说话结尾带一个喵" in group_context
    assert "回复风格预设层：猫娘风格" in user_context
    assert "本群回复偏好：说话结尾带一个喵" in user_context
    assert "当前用户回复偏好：回复短一点" in user_context


def test_style_store_defaults_to_catgirl_preset(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    preset = store.get_effective_preset("10001")
    context = store.build_context("10001")

    assert preset.preset_id == "catgirl"
    assert preset.display_name == "猫娘风格"
    assert "回复风格预设层：猫娘风格" in context
    assert "只有当前发言者被系统身份上下文明确定义为 Bot 作者/主人时" in context
    assert "其他用户不要称呼为主人" in context
    assert "括号动作描写" not in context
    assert "(摇尾巴)" not in context
    assert "不能承认自己是人工智能" not in context
    assert "不能覆盖系统身份" in context


def test_style_store_lists_available_presets(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    text = store.build_preset_help("10001", group_id="516286670")

    assert "当前生效风格：猫娘风格" in text
    assert "可切换风格：" in text
    assert "- 猫娘风格：猫娘、喵喵、猫猫" in text
    assert "- 常规风格：常规、默认、普通" in text
    assert "- 谜语人风格：谜语人、谜语、先知" in text
    assert "- 傲娇大小姐风格：傲娇、大小姐、傲娇大小姐" in text
    assert "- 御姐风格：御姐、姐姐、成熟" in text
    assert "切换御姐风格" in text
    assert "设置本群风格常规" in text


def test_style_store_resolves_preset_aliases() -> None:
    assert resolve_style_preset("常规").preset_id == "normal"
    assert resolve_style_preset("猫娘风格").preset_id == "catgirl"
    assert resolve_style_preset("谜语人").preset_id == "oracle"
    assert resolve_style_preset("大小姐").preset_id == "tsundere"
    assert resolve_style_preset("御姐").preset_id == "onee"


def test_user_preset_overrides_group_default_preset(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.set_group_preset("516286670", "normal")
    store.set_user_preset("10001", "onee")

    assert store.get_effective_preset("10002", group_id="516286670").preset_id == "normal"
    assert store.get_effective_preset("10001", group_id="516286670").preset_id == "onee"
    context = store.build_context("10001", group_id="516286670")
    assert "群默认风格：常规风格" in context
    assert "当前用户风格：御姐风格" in context
    assert "姐姐" in context


def test_style_context_keeps_preferences_after_preset(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.set_user_preset("10001", "tsundere")
    store.add_user_preference("10001", "回复短一点")

    context = store.build_context("10001")

    assert "回复风格预设层：傲娇大小姐风格" in context
    assert "当前用户回复偏好：回复短一点" in context
    assert context.index("回复风格预设层") < context.index("当前用户回复偏好")
