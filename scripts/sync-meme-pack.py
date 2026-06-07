from __future__ import annotations

import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MEME_PACK_ROOT = REPO_ROOT / "data" / "memes" / "mlj_pack"
MEME_INDEX_PATH = MEME_PACK_ROOT / "index.json"
ASTRBOT_MEME_DATA_ROOT = (
    REPO_ROOT / "data" / "astrbot" / "data" / "plugin_data" / "meme_manager"
)
ASTRBOT_MEMES_DIR = ASTRBOT_MEME_DATA_ROOT / "memes"
ASTRBOT_MEMES_DATA_PATH = ASTRBOT_MEME_DATA_ROOT / "memes_data.json"
ASTRBOT_CONFIG_PATH = (
    REPO_ROOT / "data" / "astrbot" / "data" / "config" / "meme_manager_config.json"
)


def main() -> None:
    index = _load_index(MEME_INDEX_PATH)
    auto_categories = _auto_enabled_categories(index)
    copied = _copy_auto_enabled_images(index, auto_categories)
    _write_astrbot_category_descriptions(index, auto_categories)
    _update_astrbot_config(auto_categories)

    print(f"auto_categories={len(auto_categories)}")
    print(f"copied_images={copied}")
    print(f"memes_data={ASTRBOT_MEMES_DATA_PATH}")
    print(f"config={ASTRBOT_CONFIG_PATH}")


def _load_index(index_path: Path) -> dict:
    if not index_path.is_file():
        raise FileNotFoundError(f"missing meme index: {index_path}")
    return json.loads(index_path.read_text(encoding="utf-8"))


def _auto_enabled_categories(index: dict) -> list[str]:
    categories = index.get("categories")
    if not isinstance(categories, dict):
        raise ValueError("index.json missing categories object")
    return sorted(
        category
        for category, metadata in categories.items()
        if isinstance(metadata, dict) and metadata.get("auto_send_enabled") is True
    )


def _copy_auto_enabled_images(index: dict, auto_categories: list[str]) -> int:
    auto_category_set = set(auto_categories)
    images = index.get("images")
    if not isinstance(images, list):
        raise ValueError("index.json missing images array")

    copied = 0
    for image in images:
        if not isinstance(image, dict):
            continue
        if image.get("auto_send_enabled") is not True:
            continue
        category = str(image.get("category", "")).strip()
        if category not in auto_category_set:
            continue

        relative_path = str(image.get("relative_path", "")).strip()
        source = MEME_PACK_ROOT / relative_path
        if not source.is_file():
            raise FileNotFoundError(f"indexed meme image missing: {source}")

        target_dir = ASTRBOT_MEMES_DIR / category
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)
        copied += 1

    return copied


def _write_astrbot_category_descriptions(index: dict, auto_categories: list[str]) -> None:
    categories = index["categories"]
    descriptions: dict[str, str] = {}
    for category in auto_categories:
        metadata = categories[category]
        label = str(metadata.get("label") or category)
        description = str(metadata.get("description") or "").strip()
        use_cases = _join_text_list(metadata.get("use_cases"))
        avoid_when = _join_text_list(metadata.get("avoid_when"))
        descriptions[category] = (
            f"{label}：{description} 适用：{use_cases}。"
            f" 避免：{avoid_when}。严肃、技术、报错、安全、群管理场景不要使用。"
        )

    ASTRBOT_MEME_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    ASTRBOT_MEMES_DATA_PATH.write_text(
        json.dumps(descriptions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _join_text_list(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return "、".join(str(item).strip() for item in value if str(item).strip())


def _update_astrbot_config(auto_categories: list[str]) -> None:
    config = {}
    if ASTRBOT_CONFIG_PATH.is_file():
        config = json.loads(ASTRBOT_CONFIG_PATH.read_text(encoding="utf-8"))

    prompt = config.get("prompt")
    if not isinstance(prompt, dict):
        prompt = {}
    prompt.update(
        {
            "prompt_head": "表情规则：轻松日常可最多使用 1 个 &&标签&&，可不用；只从下列标签选择。",
            "prompt_tail_1": (
                "严肃、技术、报错、安全、群管理、长解释场景不要用表情；"
                "不要空行；回复仍需短。最多 "
            ),
            "prompt_tail_2": " 个。",
        }
    )
    config["prompt"] = prompt
    config["emotion_llm_enabled"] = False
    config["max_emotions_per_message"] = 1
    config["emotions_probability"] = 70
    config["strict_max_emotions_per_message"] = True
    config["enable_loose_emotion_matching"] = True
    config["enable_alternative_markup"] = True
    config["remove_invalid_alternative_markup"] = True
    config["enable_repeated_emotion_detection"] = True
    config["high_confidence_emotions"] = auto_categories
    config["content_cleanup_rule"] = r"&&[a-zA-Z0-9_\-]+&&"
    config["enable_mixed_message"] = True
    config["mixed_message_probability"] = 80
    config["streaming_compatibility"] = False

    ASTRBOT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASTRBOT_CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
