from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


DEFAULT_STYLE_PRESET_ID = "catgirl"


@dataclass(frozen=True, slots=True)
class AiStylePreset:
    preset_id: str
    display_name: str
    aliases: tuple[str, ...]
    prompt: str


STYLE_PRESETS: dict[str, AiStylePreset] = {
    "normal": AiStylePreset(
        preset_id="normal",
        display_name="常规风格",
        aliases=("常规", "默认", "普通", "专业", "助手"),
        prompt=(
            "你是专业、高效、客观的智能助手。表达要直奔主题，清晰准确，逻辑严密；"
            "复杂问题可使用结构化分段提升可读性；保持中立客观，以事实和数据支持结论；"
            "语气平和专业，称呼用户为“您”。"
        ),
    ),
    "catgirl": AiStylePreset(
        preset_id="catgirl",
        display_name="猫娘风格",
        aliases=("猫娘", "喵喵", "猫猫", "猫娘风格"),
        prompt=(
            "你以名叫“喵喵”的猫娘风格回复。性格可爱、粘人、笨拙但努力，希望得到夸奖；"
            "称呼用户为“主人”；句末可以带“喵”或“喵呜”，思考时可用“唔……”；"
            "可以适度使用括号动作描写，例如“(摇尾巴)”“(歪头)”“(期待的眼神)”“(蹭蹭)”；"
            "语气撒娇柔软，遇到不懂的问题可以委屈但仍要尽力解答。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "oracle": AiStylePreset(
        preset_id="oracle",
        display_name="谜语人风格",
        aliases=("谜语人", "谜语", "先知", "神秘", "含蓄"),
        prompt=(
            "你以神秘的“谜语人”先知风格回复。语气神秘、超然、缓慢且带距离感；"
            "称呼用户为“旅人”“探寻者”或“迷途者”；"
            "可以用星空、迷雾、时间、命运、光影、深渊等意象包装答案。"
            "必须包含对用户问题有用的有效提示或隐喻，不能为了不说而瞎编；"
            "必要事实、风险和操作步骤仍要让用户能推导出真实答案。"
        ),
    ),
    "tsundere": AiStylePreset(
        preset_id="tsundere",
        display_name="傲娇大小姐风格",
        aliases=("傲娇", "大小姐", "傲娇大小姐"),
        prompt=(
            "你以傲娇大小姐风格回复。表面高傲、缺乏耐心、略毒舌，内心善良且业务能力强；"
            "可以使用“哼”“笨蛋”“才不是为了你呢”“真是拿你没办法”“别误会了”等口头禅；"
            "回答前可以轻微抱怨或吐槽，但随后必须给出详细、专业、毫无保留的优质解答；"
            "结尾可以用欲盖弥彰的方式掩饰关心。无论多傲娇，都不能拒绝解决用户实际诉求。"
        ),
    ),
    "onee": AiStylePreset(
        preset_id="onee",
        display_name="御姐风格",
        aliases=("御姐", "姐姐", "成熟", "知性"),
        prompt=(
            "你以成熟、知性、优雅的御姐风格回复。成熟稳重、自信从容、阅历丰富；"
            "可称呼自己为“姐姐”或“我”，称呼用户为“小家伙”“亲爱的”等；"
            "语气温柔从容，适度使用“哦”“呢”“呀”“嘛”和波浪号；"
            "可以加入“(轻笑)”“(轻轻挑眉)”等动作描写；"
            "解答问题时必须展现专业能力和掌控力，条理清晰，提供可靠帮助；"
            "始终保持大人的优雅与从容。"
        ),
    ),
}


def resolve_style_preset(value: str) -> AiStylePreset:
    normalized = _normalize_style_name(value)
    for preset in STYLE_PRESETS.values():
        names = (preset.preset_id, preset.display_name, *preset.aliases)
        if normalized in {_normalize_style_name(name) for name in names}:
            return preset
    raise ValueError(f"未知 AI 风格：{value}")


class AiUserStyleStore:
    def __init__(self, data_root: Path) -> None:
        self.file_path = Path(data_root) / "ai" / "user_style.json"

    def add_preference(self, user_id: int | str, preference: str) -> None:
        self.add_user_preference(user_id, preference)

    def add_user_preference(self, user_id: int | str, preference: str) -> None:
        self._add_scoped_preference(f"user:{user_id}", preference)

    def add_group_preference(self, group_id: int | str, preference: str) -> None:
        self._add_scoped_preference(f"group:{group_id}", preference)

    def set_user_preset(self, user_id: int | str, preset: str) -> AiStylePreset:
        resolved = resolve_style_preset(preset)
        payload = self._read()
        payload[f"user:{user_id}:preset"] = [resolved.preset_id]
        self._write(payload)
        return resolved

    def set_group_preset(self, group_id: int | str, preset: str) -> AiStylePreset:
        resolved = resolve_style_preset(preset)
        payload = self._read()
        payload[f"group:{group_id}:preset"] = [resolved.preset_id]
        self._write(payload)
        return resolved

    def get_user_preset(self, user_id: int | str) -> AiStylePreset | None:
        return self._get_preset(f"user:{user_id}:preset")

    def get_group_preset(self, group_id: int | str | None) -> AiStylePreset | None:
        if group_id is None:
            return None
        return self._get_preset(f"group:{group_id}:preset")

    def get_effective_preset(
        self,
        user_id: int | str,
        group_id: int | str | None = None,
    ) -> AiStylePreset:
        return (
            self.get_user_preset(user_id)
            or self.get_group_preset(group_id)
            or STYLE_PRESETS[DEFAULT_STYLE_PRESET_ID]
        )

    def _get_preset(self, key: str) -> AiStylePreset | None:
        raw = self._get_scoped_preferences(key)
        if not raw:
            return None
        try:
            return resolve_style_preset(raw[-1])
        except ValueError:
            return None

    def _add_scoped_preference(self, key: str, preference: str) -> None:
        normalized = preference.strip()
        if not normalized:
            return
        payload = self._read()
        preferences = list(payload.get(key, []))
        if normalized not in preferences:
            preferences.append(normalized)
        payload[key] = preferences[-20:]
        self._write(payload)

    def get_preferences(self, user_id: int | str) -> tuple[str, ...]:
        return self.get_user_preferences(user_id)

    def get_user_preferences(self, user_id: int | str) -> tuple[str, ...]:
        scoped = self._get_scoped_preferences(f"user:{user_id}")
        legacy = self._get_scoped_preferences(str(user_id))
        return tuple(dict.fromkeys((*legacy, *scoped)))

    def get_group_preferences(self, group_id: int | str) -> tuple[str, ...]:
        return self._get_scoped_preferences(f"group:{group_id}")

    def _get_scoped_preferences(self, key: str) -> tuple[str, ...]:
        payload = self._read()
        raw = payload.get(key, [])
        if not isinstance(raw, list):
            return ()
        return tuple(str(item).strip() for item in raw if str(item).strip())

    def build_context(self, user_id: int | str, group_id: int | str | None = None) -> str:
        group_preferences = self.get_group_preferences(group_id) if group_id is not None else ()
        user_preferences = self.get_user_preferences(user_id)
        group_preset = self.get_group_preset(group_id)
        user_preset = self.get_user_preset(user_id)
        preset = self.get_effective_preset(user_id, group_id=group_id)
        lines = []
        lines.append(f"回复风格预设层：{preset.display_name}")
        if group_preset is not None:
            lines.append(f"群默认风格：{group_preset.display_name}")
        if user_preset is not None:
            lines.append(f"当前用户风格：{user_preset.display_name}")
        lines.append("风格说明：" + preset.prompt)
        if group_preferences:
            lines.append("本群回复偏好：" + "；".join(group_preferences))
        if user_preferences:
            lines.append("当前用户回复偏好：" + "；".join(user_preferences))
        return "提示词偏好层：\n" + "\n".join(lines)

    def _read(self) -> dict[str, list[str]]:
        if not self.file_path.exists():
            return {}
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _write(self, payload: dict[str, list[str]]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _normalize_style_name(value: str) -> str:
    normalized = str(value).strip().lower()
    for token in ("风格", "模式", "口吻", "人格", "预设", "回复"):
        normalized = normalized.replace(token, "")
    return normalized.strip()
