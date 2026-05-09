from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_output_style import sanitize_ai_output_text


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
