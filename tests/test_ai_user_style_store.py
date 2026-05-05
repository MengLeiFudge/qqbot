from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_user_style_store import AiUserStyleStore


def test_user_style_store_saves_and_formats_preferences(tmp_path: Path) -> None:
    store = AiUserStyleStore(tmp_path)

    store.add_preference("10001", "不要使用 markdown")
    store.add_preference("10001", "回复短一点")

    assert store.get_preferences("10001") == ("不要使用 markdown", "回复短一点")
    assert store.build_context("10001") == "当前用户的回复偏好：不要使用 markdown；回复短一点"


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
    assert store.build_context("10002", group_id="516286670") == (
        "提示词偏好层：\n"
        "本群回复偏好：说话结尾带一个喵"
    )
    assert store.build_context("10001", group_id="516286670") == (
        "提示词偏好层：\n"
        "本群回复偏好：说话结尾带一个喵\n"
        "当前用户回复偏好：回复短一点"
    )
