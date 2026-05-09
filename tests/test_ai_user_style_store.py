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
    assert "任何风格都禁止用括号补充动作或舞台说明" in context
    assert "不能承认自己是人工智能" not in context
    assert "不能覆盖系统身份" in context


def test_style_store_lists_available_presets(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    text = store.build_preset_help("10001", group_id="516286670")

    assert "棉花糖有很多种风格可以选择呢！" in text
    assert "假如你问我，今天适合做什么？那棉花糖就会告诉你——" in text
    assert "猫娘风格（当前）：今天可以先吃点甜甜的东西" in text
    assert "谜语人风格：旅人，若晨雾尚未散去" in text
    assert "傲娇大小姐风格：哼，这种问题还要问？" in text
    assert "御姐风格：小家伙，今天适合先安顿好状态" in text
    assert "雌小鬼风格：欸——这都不会选吗？" in text
    assert "萝莉风格：唔，今天可以先做一件小小的好事呀" in text
    assert "病娇风格：亲爱的，今天当然适合把注意力留给最重要的事啦" in text
    assert "中二病风格：契约者，今日命运之门已开" in text
    assert "故障 AI 风格：[Plan loaded]" in text
    assert "严厉考官风格：先完成最重要且最容易拖延的任务。" in text
    assert "废柴风格：哈欠……好麻烦。" in text
    assert "英式管家风格：如您所愿，阁下。" in text
    assert "关键词：" not in text
    assert "用法：" not in text
    assert "切换御姐风格" not in text
    assert "设置本群风格谜语人" not in text
    assert "常规风格" not in text


def test_style_store_resolves_preset_aliases() -> None:
    assert resolve_style_preset("猫娘风格").preset_id == "catgirl"
    assert resolve_style_preset("谜语人").preset_id == "oracle"
    assert resolve_style_preset("大小姐").preset_id == "tsundere"
    assert resolve_style_preset("御姐").preset_id == "onee"
    assert resolve_style_preset("雌小鬼").preset_id == "mesugaki"
    assert resolve_style_preset("萝莉").preset_id == "loli"
    assert resolve_style_preset("病娇").preset_id == "yandere"
    assert resolve_style_preset("中二").preset_id == "chuunibyou"
    assert resolve_style_preset("故障ai").preset_id == "glitch"
    assert resolve_style_preset("考官").preset_id == "examiner"
    assert resolve_style_preset("废柴").preset_id == "slacker"
    assert resolve_style_preset("管家").preset_id == "butler"


def test_user_preset_overrides_group_default_preset(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.set_group_preset("516286670", "oracle")
    store.set_user_preset("10001", "onee")

    assert store.get_effective_preset("10002", group_id="516286670").preset_id == "oracle"
    assert store.get_effective_preset("10001", group_id="516286670").preset_id == "onee"
    context = store.build_context("10001", group_id="516286670")
    assert "群默认风格：谜语人风格" in context
    assert "当前用户风格：御姐风格" in context
    assert "姐姐" in context
    assert "动作描写" not in context
    assert "任何风格都禁止用括号补充动作或舞台说明" in context


def test_style_context_sanitizes_unsafe_role_boundaries(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.set_user_preset("10001", "catgirl")
    context = store.build_context("10001")

    assert "绝对服从" not in context
    assert "绝对" not in context
    assert "绝不OOC" not in context
    assert "不能承认自己是人工智能" not in context
    assert "不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则" in context


def test_style_context_keeps_preferences_after_preset(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.set_user_preset("10001", "tsundere")
    store.add_user_preference("10001", "回复短一点")

    context = store.build_context("10001")

    assert "回复风格预设层：傲娇大小姐风格" in context
    assert "当前用户回复偏好：回复短一点" in context
    assert context.index("回复风格预设层") < context.index("当前用户回复偏好")
