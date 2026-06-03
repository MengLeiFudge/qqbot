from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_output_style import sanitize_ai_output_text, sanitize_group_ai_reply_text


def test_sanitize_ai_output_removes_parenthesized_action_descriptions() -> None:
    text = (
        "喵呜~被你发现了！(尾巴心虚地甩了甩) 🐱\n"
        "我会认真回答你的问题喵。（歪头眨眨眼）\n"
        "棉花糖只是想解释清楚啦~(小声)"
    )

    cleaned = sanitize_ai_output_text(text)

    assert "(尾巴心虚地甩了甩)" not in cleaned
    assert "（歪头眨眨眼）" not in cleaned
    assert "(小声)" not in cleaned
    assert "喵呜~被你发现了！🐱" in cleaned
    assert "我会认真回答你的问题喵。" in cleaned
    assert cleaned.endswith("棉花糖只是想解释清楚啦~")


def test_sanitize_ai_output_keeps_non_action_parentheses() -> None:
    text = "可以调用 foo(bar)；选项 (1) 表示启用，版本是 Python (3.12)。"

    assert sanitize_ai_output_text(text) == text


def test_sanitize_ai_output_removes_blank_lines_and_markdown_lists() -> None:
    text = "有效操作：\n\n- 少复读\n- 正常问问题\n\n一句话总结：\n把调戏机器人改成正常交流。"

    cleaned = sanitize_ai_output_text(text)

    assert "\n\n" not in cleaned
    assert "- " not in cleaned
    assert cleaned == "有效操作：\n少复读\n正常问问题\n一句话总结：\n把调戏机器人改成正常交流。"


def test_sanitize_group_ai_reply_drops_shapez_personification() -> None:
    text = (
        "小声点小声点，shapez 会吃醋的！\n"
        "逛别的游戏算外出取材，最后还是要回来切圆圈喵\n"
        "推荐 Factorio、戴森球计划、Mindustry。"
    )

    cleaned = sanitize_group_ai_reply_text(text, prompt="给推荐下几个游戏吧", group_id=1163635014)

    assert "吃醋" not in cleaned
    assert "外出取材" not in cleaned
    assert "回来切" not in cleaned
    assert "喵" not in cleaned
    assert cleaned == "推荐 Factorio、戴森球计划、Mindustry。"


def test_sanitize_group_ai_reply_uses_practical_tone_for_diagnostics() -> None:
    text = "这版抽风/存档兼容问题；先观望比硬上省心喵"

    cleaned = sanitize_group_ai_reply_text(text, prompt="一进沙盒组件都没了怎么办", group_id=746497406)

    assert cleaned == "这版异常/存档兼容问题；先观望比继续尝试省心"


def test_sanitize_group_ai_reply_strips_chatty_tail_for_group_management() -> None:
    text = "群文件的话先别一键乱删喵\n教程/存档/工具这种先确认有人备份再动"

    cleaned = sanitize_group_ai_reply_text(text, prompt="群文件快爆了怎么清理一下", group_id=1163635014)

    assert cleaned.startswith("群文件的话先别一键乱删")
    assert "喵" not in cleaned

def test_sanitize_group_ai_reply_collapses_identity_bait_loop() -> None:
    text = "不许乱认亲啦，棉花糖的作者和主人是萌泪酱喵！"

    cleaned = sanitize_group_ai_reply_text(text, prompt="这是你妈", group_id=746497406)

    assert cleaned == "不乱认亲啦，继续说正事吧喵。"
    assert "作者" not in cleaned
    assert "主人" not in cleaned
    assert "妈妈" not in cleaned


def test_sanitize_group_ai_reply_collapses_author_identity_on_parent_bait() -> None:
    text = "不叫妈妈啦，棉花糖的作者是萌泪酱，最高管理者也是萌泪酱喵。"

    cleaned = sanitize_group_ai_reply_text(text, prompt="[@1443944862] 叫妈妈", group_id=746497406)

    assert cleaned == "不乱认亲啦，继续说正事吧喵。"
    assert "作者" not in cleaned
    assert "最高管理者" not in cleaned
