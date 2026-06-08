from __future__ import annotations

import json
from pathlib import Path

from qqbot.features.ai.reply_pipeline import append_ai_reply_meme
from qqbot.features.ai.meme_selector import load_meme_pack, select_meme_for_reply


class FirstRng:
    def random(self) -> float:
        return 0.0

    def choice(self, values):
        return list(values)[0]


def test_meme_pack_filters_disabled_categories(tmp_path: Path) -> None:
    pack_root = _write_pack(
        tmp_path,
        {
            "funny_laugh": True,
            "suggestive_warning": False,
            "sensitive_payment_do_not_send": False,
            "misc_review": False,
        },
    )

    pack = load_meme_pack(pack_root)

    assert "funny_laugh" in pack.images_by_category
    assert "suggestive_warning" not in pack.images_by_category
    assert "sensitive_payment_do_not_send" not in pack.images_by_category
    assert "misc_review" not in pack.images_by_category


def test_selects_matching_casual_categories(tmp_path: Path) -> None:
    pack_root = _write_pack(
        tmp_path,
        {
            "awkward_silence": True,
            "boss_worship": True,
            "sad_cry": True,
            "funny_laugh": True,
        },
    )

    assert (
        select_meme_for_reply(
            "这也太无语了",
            group_id=1001,
            pack_root=pack_root,
            rng=FirstRng(),
            probability=1.0,
            cooldown_seconds=0,
            now=1.0,
            cooldowns={},
        ).category
        == "awkward_silence"
    )
    assert (
        select_meme_for_reply(
            "大佬太强了",
            group_id=1001,
            pack_root=pack_root,
            rng=FirstRng(),
            probability=1.0,
            cooldown_seconds=0,
            now=2.0,
            cooldowns={},
        ).category
        == "boss_worship"
    )
    assert (
        select_meme_for_reply(
            "哭哭，顶不住了",
            group_id=1001,
            pack_root=pack_root,
            rng=FirstRng(),
            probability=1.0,
            cooldown_seconds=0,
            now=3.0,
            cooldowns={},
        ).category
        == "sad_cry"
    )


def test_technical_and_credential_contexts_do_not_select(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path, {"funny_laugh": True, "awkward_silence": True})

    assert (
        select_meme_for_reply(
            "这个 Traceback 是配置路径错了，先按日志定位。",
            prompt="帮我看一下报错",
            group_id=1001,
            pack_root=pack_root,
            rng=FirstRng(),
            probability=1.0,
            now=1.0,
            cooldowns={},
        )
        is None
    )
    assert (
        select_meme_for_reply(
            "不要把 API key 和 token 发群里，先撤回再轮换。",
            group_id=1001,
            pack_root=pack_root,
            rng=FirstRng(),
            probability=1.0,
            now=2.0,
            cooldowns={},
        )
        is None
    )


def test_group_cooldown_limits_repeated_memes(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path, {"funny_laugh": True})
    cooldowns: dict[str, float] = {}

    first = select_meme_for_reply(
        "哈哈笑死",
        group_id=1001,
        pack_root=pack_root,
        rng=FirstRng(),
        probability=1.0,
        cooldown_seconds=45,
        now=10.0,
        cooldowns=cooldowns,
    )
    second = select_meme_for_reply(
        "哈哈笑死",
        group_id=1001,
        pack_root=pack_root,
        rng=FirstRng(),
        probability=1.0,
        cooldown_seconds=45,
        now=20.0,
        cooldowns=cooldowns,
    )
    third = select_meme_for_reply(
        "哈哈笑死",
        group_id=1001,
        pack_root=pack_root,
        rng=FirstRng(),
        probability=1.0,
        cooldown_seconds=45,
        now=56.0,
        cooldowns=cooldowns,
    )

    assert first is not None
    assert second is None
    assert third is not None


def test_short_keyword_reply_can_be_meme_only(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path, {"funny_laugh": True})

    selection = select_meme_for_reply(
        "哈哈笑死",
        group_id=1001,
        pack_root=pack_root,
        rng=FirstRng(),
        probability=1.0,
        meme_only_probability=1.0,
        cooldown_seconds=0,
        now=1.0,
        cooldowns={},
    )

    assert selection is not None
    assert selection.category == "funny_laugh"
    assert selection.meme_only


def test_fallback_category_does_not_replace_text_with_meme_only(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path, {"funny_laugh": True})

    selection = select_meme_for_reply(
        "收到啦",
        group_id=1001,
        pack_root=pack_root,
        rng=FirstRng(),
        probability=1.0,
        meme_only_probability=1.0,
        cooldown_seconds=0,
        now=1.0,
        cooldowns={},
    )

    assert selection is not None
    assert selection.category == "funny_laugh"
    assert not selection.meme_only


def test_append_ai_reply_meme_preserves_text_and_adds_image(tmp_path: Path) -> None:
    image_path = tmp_path / "meme.jpg"
    image_path.write_bytes(b"fake image")

    message = append_ai_reply_meme("哈哈笑死", image_path)

    message_text = str(message)
    assert "哈哈笑死" in message_text
    assert "CQ:image" in message_text
    assert image_path.as_posix() in message_text


def test_append_ai_reply_meme_can_build_image_only_message(tmp_path: Path) -> None:
    image_path = tmp_path / "meme.jpg"
    image_path.write_bytes(b"fake image")

    message = append_ai_reply_meme("", image_path)

    message_text = str(message)
    assert "CQ:image" in message_text
    assert image_path.as_posix() in message_text
    assert "text" not in message_text


def _write_pack(tmp_path: Path, categories: dict[str, bool]) -> Path:
    pack_root = tmp_path / "mlj_pack"
    images_root = pack_root / "images"
    index_categories = {}
    index_images = []
    for category, auto_enabled in categories.items():
        category_dir = images_root / category
        category_dir.mkdir(parents=True, exist_ok=True)
        image_path = category_dir / f"{category}001.jpg"
        image_path.write_bytes(b"fake image")
        index_categories[category] = {
            "label": category,
            "description": category,
            "use_cases": [category],
            "emotion_tags": [category],
            "avoid_when": [],
            "auto_send_enabled": auto_enabled,
            "count": 1,
        }
        index_images.append(
            {
                "id": f"{category}-001",
                "category": category,
                "title": f"{category}001",
                "relative_path": f"images/{category}/{category}001.jpg",
                "auto_send_enabled": auto_enabled,
            }
        )

    (pack_root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "total_images": len(index_images),
                "categories": index_categories,
                "images": index_images,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pack_root
