from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_user_style_store import (
    CONVERSATION_SCOPE_ID,
    DEFAULT_TRAIT_IDS,
    PERSONA_TRAITS,
    AiPersonaTrait,
    AiUserStyleStore,
)


def test_user_style_store_saves_preferences_but_does_not_apply_them_to_persona(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path, bot_name="萌萌棉花糖♪")

    store.add_preference("10001", "不要使用 markdown")
    store.add_preference("10001", "回复短一点")

    assert store.get_preferences("10001") == ("不要使用 markdown", "回复短一点")
    context = store.build_context("10001")
    assert "人格设定：猫娘棉花糖" in context
    assert "你是 QQ 机器人“萌萌棉花糖♪”" in context
    assert "稳定人格是猫娘棉花糖" in context
    assert "当前用户回复偏好" not in context
    assert "不要使用 markdown" not in context
    assert "回复短一点" not in context


def test_style_context_uses_single_catgirl_persona_with_traits(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path, bot_name="萌萌棉花糖♪")

    context = store.build_context("10001")

    assert "你是 QQ 机器人“萌萌棉花糖♪”" in context
    assert "人格结构：这是一个稳定人格" in context
    assert "保留特质：" in context
    assert "认真帮忙" in context
    assert "轻量吐槽" in context
    assert "中二爆发" in context
    assert "线索专注" in context
    assert "困困软化" in context
    assert "少女侦探" not in context
    assert "傲娇大小姐" not in context
    assert "御姐" not in context
    assert "女仆" not in context
    assert "管家" not in context


def test_style_store_separates_group_and_user_preferences(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.add_user_preference("10001", "回复短一点")
    store.add_group_preference("516286670", "说话结尾带一个喵")

    assert store.get_user_preferences("10001") == ("回复短一点",)
    assert store.get_group_preferences("516286670") == ("说话结尾带一个喵",)
    group_context = store.build_context("10002", group_id="516286670")
    user_context = store.build_context("10001", group_id="516286670")
    assert "人格设定：猫娘棉花糖" in group_context
    assert "本群回复偏好" not in group_context
    assert "说话结尾带一个喵" not in group_context
    assert "人格设定：猫娘棉花糖" in user_context
    assert "当前用户回复偏好" not in user_context
    assert "回复短一点" not in user_context


def test_style_store_ignores_duplicate_preferences(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.add_preference("10001", "回复短一点")
    store.add_preference("10001", "回复短一点")

    assert store.get_preferences("10001") == ("回复短一点",)


def test_style_store_uses_stable_conversation_scope() -> None:
    assert AiUserStyleStore.conversation_scope_id() == CONVERSATION_SCOPE_ID
    assert CONVERSATION_SCOPE_ID == "stable"


def test_style_store_lists_no_switchable_presets(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    text = store.build_preset_help("10001", group_id="516286670")

    assert text == "切换？我不知道你在说什么。你看到的就是现在的我呀。"
    assert "轮换" not in text
    assert "4:00" not in text
    assert "猫娘风格" not in text
    assert "侦探风格" not in text


def test_persona_traits_are_trait_layer_not_independent_roles() -> None:
    assert tuple(PERSONA_TRAITS) == DEFAULT_TRAIT_IDS
    assert all(isinstance(trait, AiPersonaTrait) for trait in PERSONA_TRAITS.values())
    joined_prompts = "\n".join(trait.prompt for trait in PERSONA_TRAITS.values())

    assert "喵呜" not in joined_prompts
    assert "橘雪莉" not in joined_prompts
    assert "谜语人风格" not in joined_prompts
    assert "这是分析习惯，不是侦探人格" in joined_prompts
    assert "不能称呼用户为固定身份" in joined_prompts


def test_style_context_sanitizes_unsafe_role_boundaries(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path, bot_name="萌萌棉花糖♪")

    context = store.build_context("10001")

    assert "绝对服从" not in context
    assert "绝不OOC" not in context
    assert "不能承认自己是人工智能" not in context
    assert "你是名叫" not in context
    assert "禁止用括号补充动作或舞台说明" in context
    assert "不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则" in context
    assert "只有系统身份上下文明确当前发言者是 Bot 作者/主人时" in context
    assert "其他用户不要这样称呼" in context
