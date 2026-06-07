from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import random
import re
import time
from typing import Any


DEFAULT_GROUP_MEME_PROBABILITY = 0.72
DEFAULT_MEME_COOLDOWN_SECONDS = 45.0
MAX_MEME_REPLY_CHARS = 180
_GROUP_LAST_MEME_AT: dict[str, float] = {}

_DISABLED_CONTEXT_PATTERN = re.compile(
    r"("
    r"traceback|exception|error|failed|报错|错误|异常|失败|崩溃|日志|堆栈|"
    r"token|api\s*key|secret|password|passwd|凭据|密钥|密码|\.kube/config|"
    r"数据库|sql|http|端口|配置|路径|依赖|pytest|python|git|powershell|"
    r"禁言|踢人|封禁|权限|群管理|群文件|撤回|管理员|"
    r"安全|漏洞|盗版|破解|违规"
    r")",
    re.IGNORECASE,
)

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "funny_laugh": ("哈哈", "笑死", "绷不住", "好笑", "乐", "草", "乐了"),
    "awkward_silence": ("无语", "沉默", "冷场", "啊这", "离谱", "没话说", "无法交流"),
    "polite_awkward_smile": ("尴尬", "礼貌", "勉强", "难办"),
    "confused_question": ("什么", "啥", "问号", "看不懂", "不懂", "迷惑", "怎么回事", "为啥"),
    "shocked_surprise": ("震惊", "居然", "竟然", "吓", "惊", "啊？", "啊?"),
    "boss_worship": ("大佬", "太强", "厉害", "膜拜", "牛", "神", "高手"),
    "boss_feed": ("递茶", "投喂大佬", "伺候大佬"),
    "sad_cry": ("哭", "哭哭", "呜", "难过", "委屈", "悲", "遗憾"),
    "hug_comfort": ("抱抱", "摸头", "安慰", "别难过"),
    "tired_defeated": ("累", "破防", "自闭", "倒了", "顶不住", "寄了"),
    "happy_cheer": ("好耶", "太好了", "开心", "加油", "成功", "完成", "赢"),
    "agreement_yes": ("对", "嗯嗯", "同意", "认可", "没错"),
    "reject_no": ("不要", "不行", "走开", "拒绝", "别过来"),
    "no_need": ("没必要", "不值得", "不用", "算了"),
    "apology_sorry": ("对不起", "抱歉", "不好意思", "错了"),
    "affection_kiss": ("亲", "亲亲", "贴贴", "喜欢", "爱你", "mua"),
    "touch_rua": ("rua", "摸", "戳", "贴"),
    "cute_begging_trade": ("求求", "给我", "拜托", "可爱", "卖萌", "撒娇"),
    "shy_flirt": ("害羞", "脸红", "夸我", "不好意思"),
    "angry_dislike": ("生气", "嫌弃", "讨厌", "气死", "不满"),
    "slap_warning": ("打你", "敲", "警告", "揍"),
    "troll_funny": ("滑稽", "玩梗", "整活", "乐子"),
    "fear_panic": ("害怕", "慌", "救命", "求饶", "怕"),
    "rhythm_game_pressure": ("音游", "arc", "arcaea", "推分", "谱面", "ap", "pm"),
    "game_invite": ("打游戏", "开黑", "来玩", "一起玩"),
    "food_eat": ("吃", "饭", "夜宵", "零食", "投喂"),
    "sleep_rest": ("睡", "晚安", "早安", "困", "起床", "休息"),
    "work_progress": ("进度", "干活", "工作", "处理中"),
    "watching_observe": ("看看", "围观", "盯", "观察"),
    "self_noob": ("我菜", "菜鸡", "太菜", "打不过"),
}
_DEFAULT_CASUAL_CATEGORIES = (
    "funny_laugh",
    "awkward_silence",
    "happy_cheer",
    "confused_question",
    "troll_funny",
)


@dataclass(frozen=True, slots=True)
class MemeImage:
    id: str
    category: str
    title: str
    path: Path


@dataclass(frozen=True, slots=True)
class MemeSelection:
    category: str
    title: str
    path: Path


@dataclass(frozen=True, slots=True)
class MemePack:
    root: Path
    images_by_category: dict[str, tuple[MemeImage, ...]]

    def has_category(self, category: str) -> bool:
        return bool(self.images_by_category.get(category))


def select_meme_for_reply(
    reply_text: str,
    *,
    prompt: str = "",
    group_id: int | str | None = None,
    data_root: Path | str | None = None,
    pack_root: Path | str | None = None,
    now: float | None = None,
    rng: Any | None = None,
    probability: float | None = None,
    cooldown_seconds: float = DEFAULT_MEME_COOLDOWN_SECONDS,
    cooldowns: dict[str, float] | None = None,
) -> MemeSelection | None:
    if group_id is None:
        return None

    text = str(reply_text or "").strip()
    if not text or _is_meme_disabled_context(text, prompt=prompt):
        return None

    pack = load_meme_pack(resolve_meme_pack_root(data_root=data_root, pack_root=pack_root))
    if not pack.images_by_category:
        return None

    current_time = now if now is not None else time.time()
    group_key = str(group_id)
    cooldown_store = _GROUP_LAST_MEME_AT if cooldowns is None else cooldowns
    last_sent_at = cooldown_store.get(group_key)
    if last_sent_at is not None and current_time - last_sent_at < cooldown_seconds:
        return None

    random_source = rng or random
    threshold = DEFAULT_GROUP_MEME_PROBABILITY if probability is None else probability
    if random_source.random() >= threshold:
        return None

    category = _select_category(pack, f"{prompt}\n{text}", random_source)
    if category is None:
        return None
    image = random_source.choice(pack.images_by_category[category])

    cooldown_store[group_key] = current_time
    return MemeSelection(category=image.category, title=image.title, path=image.path)


def resolve_meme_pack_root(
    *,
    data_root: Path | str | None = None,
    pack_root: Path | str | None = None,
) -> Path:
    if pack_root is not None:
        return Path(pack_root)

    env_pack_root = os.environ.get("QQBOT_MEME_PACK_ROOT")
    if env_pack_root:
        return Path(env_pack_root)

    candidates: list[Path] = []
    if data_root is not None:
        root = Path(data_root)
        candidates.extend(parent / "memes" / "mlj_pack" for parent in (root, *root.parents))

    module_path = Path(__file__).resolve()
    candidates.append(module_path.parents[5] / "data" / "memes" / "mlj_pack")

    for candidate in candidates:
        if (candidate / "index.json").is_file():
            return candidate
    return candidates[-1]


def load_meme_pack(pack_root: Path | str) -> MemePack:
    root = Path(pack_root)
    index_path = root / "index.json"
    try:
        stat = index_path.stat()
    except FileNotFoundError:
        return MemePack(root=root, images_by_category={})
    return _load_meme_pack_cached(str(root.resolve()), stat.st_mtime_ns)


@lru_cache(maxsize=8)
def _load_meme_pack_cached(root_text: str, mtime_ns: int) -> MemePack:
    del mtime_ns
    root = Path(root_text)
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    images_by_category: dict[str, list[MemeImage]] = {}
    for item in index.get("images", []):
        if not isinstance(item, dict) or item.get("auto_send_enabled") is not True:
            continue
        category = str(item.get("category") or "").strip()
        relative_path = str(item.get("relative_path") or "").strip()
        path = root / relative_path
        if not category or not path.is_file():
            continue
        images_by_category.setdefault(category, []).append(
            MemeImage(
                id=str(item.get("id") or path.stem),
                category=category,
                title=str(item.get("title") or path.stem),
                path=path,
            )
        )
    frozen = {
        category: tuple(images)
        for category, images in sorted(images_by_category.items())
        if images
    }
    return MemePack(root=root, images_by_category=frozen)


def _is_meme_disabled_context(reply_text: str, *, prompt: str = "") -> bool:
    text = f"{prompt}\n{reply_text}".strip()
    if len(reply_text) > MAX_MEME_REPLY_CHARS:
        return True
    return bool(_DISABLED_CONTEXT_PATTERN.search(text))


def _select_category(pack: MemePack, text: str, rng: Any) -> str | None:
    normalized = _normalize_text(text)
    scores: dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if not pack.has_category(category):
            continue
        score = sum(1 for keyword in keywords if _normalize_text(keyword) in normalized)
        if score:
            scores[category] = score

    if scores:
        max_score = max(scores.values())
        return rng.choice(sorted(category for category, score in scores.items() if score == max_score))

    fallback_categories = [
        category for category in _DEFAULT_CASUAL_CATEGORIES if pack.has_category(category)
    ]
    if not fallback_categories:
        return None
    return rng.choice(fallback_categories)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text).lower())
