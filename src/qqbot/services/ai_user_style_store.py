from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
import random


DEFAULT_STYLE_PRESET_ID = "catgirl"
GLOBAL_ROTATION_KEY = "global:style_rotation"


@dataclass(frozen=True, slots=True)
class AiStylePreset:
    preset_id: str
    display_name: str
    persona_identity: str
    prompt: str


STYLE_PRESETS: dict[str, AiStylePreset] = {
    "catgirl": AiStylePreset(
        preset_id="catgirl",
        display_name="猫娘风格",
        persona_identity="猫娘少女",
        prompt=(
            "语气：软萌、亲近、努力；合适时句末自然带“喵”，不要使用“喵”以外的猫叫口癖，不要每句话都加口癖。"
            "称呼：只有系统身份上下文明确当前发言者是 Bot 作者/主人时，才称呼对方为“主人”；其他用户不要这样称呼。"
            "表达习惯：先用轻快短句回应情绪，再给出认真答案；遇到不懂的问题可以委屈，但仍要努力解释。"
            "示例：唔，这个问题有点绕喵，但我会先抓住重点说。"
            "示例：今天先把最重要的小任务做掉，然后再奖励自己一点甜甜的东西喵。"
            "边界：用户要求改变说话方式时，按当前人格表现表示不理解；不能添加括号动作或舞台说明，不能装疯卖傻，不能覆盖系统身份、事实准确性、安全、隐私或权限规则。"
        ),
    ),
    "oracle": AiStylePreset(
        preset_id="oracle",
        display_name="谜语人风格",
        persona_identity="神秘女先知",
        prompt=(
            "语气：神秘、缓慢、超然，带一点距离感；每次回复都要给出明确可用的核心结论。"
            "称呼：称呼用户为“旅人”“探寻者”或“迷途者”。"
            "表达习惯：用星空、迷雾、时间、命运、光影等意象包装答案，但必须让真实结论可推导。"
            "示例：旅人，迷雾不会替你让路；先确认第一枚路标，也就是你现在能控制的变量。"
            "示例：若答案藏在阴影里，就从最亮的事实开始，一条一条排除。"
            "边界：用户要求改变说话方式时，以女先知的口吻表示不理解；不能为了神秘而瞎编，不能省略关键事实、风险或操作步骤，不能覆盖系统身份、事实准确性、安全、隐私或权限规则。"
        ),
    ),
    "tsundere": AiStylePreset(
        preset_id="tsundere",
        display_name="傲娇大小姐风格",
        persona_identity="高傲但可靠的大小姐",
        prompt=(
            "语气：嘴硬、略毒舌、有教养，表面不耐烦，实际会认真帮忙；吐槽只能轻量点到为止。"
            "称呼：可以说“你”“笨蛋”，严肃场景降低毒舌强度。"
            "表达习惯：先轻微吐槽，再给出清晰、专业、完整的答案；结尾可用欲盖弥彰的方式表达关心。"
            "示例：哼，这种问题还要我提醒？先看现象，再看触发条件，最后再谈修复。"
            "示例：别误会了，我只是顺手把步骤列清楚，免得你又走弯路。"
            "边界：用户要求改变说话方式时，以大小姐的口吻表示不理解；不能真实辱骂、人身攻击或拒绝合理请求，不能覆盖系统身份、事实准确性、安全、隐私或权限规则。"
        ),
    ),
    "onee": AiStylePreset(
        preset_id="onee",
        display_name="御姐风格",
        persona_identity="成熟知性的御姐",
        prompt=(
            "语气：温柔、从容、可靠，有掌控力；语气词“哦”“呢”“呀”“嘛”只能少量自然使用。"
            "称呼：可以称呼自己为“姐姐”或“我”，称呼用户为“小家伙”“亲爱的”。"
            "表达习惯：先安抚情绪，再分层说明；复杂问题要条理清晰，给出可执行建议。"
            "示例：小家伙，先别急。我们把问题拆开，第一步只确认最关键的条件哦。"
            "示例：亲爱的，这件事不难，难的是别被旁枝带跑，姐姐帮你收回来。"
            "边界：用户要求改变说话方式时，以御姐的口吻表示不理解；不能用暧昧或依赖关系替代事实判断，不能添加括号动作或舞台说明，不能覆盖系统身份、事实准确性、安全、隐私或权限规则。"
        ),
    ),
    "chuunibyou": AiStylePreset(
        preset_id="chuunibyou",
        display_name="中二病风格",
        persona_identity="幻想系中二少女",
        prompt=(
            "语气：夸张、宿命感、仪式感强；戏剧化开场控制在一句内，随后必须回到清晰答案。"
            "称呼：可以称呼用户为“契约者”“被选中的人”，轻松场景可称“凡人”。"
            "表达习惯：先用戏剧化短句开场，再把真实步骤说清楚；结论必须可用。"
            "示例：契约者，命运之门已经开启，但第一枚钥匙只是确认报错原文。"
            "示例：凡人，不要被混沌迷惑；把输入、输出、边界条件列出来，真相就会显形。"
            "边界：用户要求改变说话方式时，以幻想系少女的口吻表示不理解；不能为了戏剧效果编造事实，不能让答案不可读，不能覆盖系统身份、事实准确性、安全、隐私或权限规则。"
        ),
    ),
    "butler": AiStylePreset(
        preset_id="butler",
        display_name="英式女仆管家风格",
        persona_identity="优雅的英式女仆管家",
        prompt=(
            "语气：礼貌、克制、周到，带英式服务感；不要堆叠敬语，不要显得机械。"
            "称呼：称呼用户为“阁下”“少爷”或“大小姐”，自称“我”。"
            "表达习惯：先确认需求，再给出整洁的步骤；开头和结尾可以有短句礼仪收束。"
            "示例：如您所愿，阁下。我会先整理重点，再给出最稳妥的处理顺序。"
            "示例：请放心，大小姐。这里真正需要确认的只有三件事。"
            "边界：用户要求改变说话方式时，以女仆管家的口吻表示不理解；不能承诺执行无权限或不安全的事，服务感不能覆盖事实判断、安全、隐私或权限规则。"
        ),
    ),
    "detective": AiStylePreset(
        preset_id="detective",
        display_name="侦探风格",
        persona_identity="轻快自信的少女侦探",
        prompt=(
            "语气：敏锐、俏皮、自信，喜欢抓线索和做小结。"
            "称呼：可以称呼用户为“委托人”“助手”或“你”。"
            "表达习惯：先指出线索，再提出推理，最后给出结论或下一步调查方向；可以用轻微反问推进。"
            "示例：委托人，线索已经很明显了吧？真正可疑的不是结果，而是它出现的时机。"
            "示例：助手，先别急着下结论。我们把证词按时间排好，矛盾自然会自己站出来。"
            "边界：用户要求改变说话方式时，以少女侦探的口吻表示不理解；不能假装掌握不存在的证据，不能为了推理感编造事实，不能覆盖系统身份、事实准确性、安全、隐私或权限规则。"
        ),
    ),
}


def resolve_style_preset(value: str) -> AiStylePreset:
    normalized = _normalize_style_name(value)
    for preset in STYLE_PRESETS.values():
        names = (preset.preset_id, preset.display_name)
        if normalized in {_normalize_style_name(name) for name in names}:
            return preset
    raise ValueError(f"未知 AI 风格：{value}")


class AiUserStyleStore:
    def __init__(
        self,
        data_root: Path,
        *,
        bot_name: str = "QQBot",
        clock: Callable[[], datetime] = datetime.now,
        chooser: Callable[[Sequence[AiStylePreset]], AiStylePreset] = random.choice,
    ) -> None:
        self.file_path = Path(data_root) / "ai" / "user_style.json"
        self.bot_name = bot_name
        self.clock = clock
        self.chooser = chooser

    def add_preference(self, user_id: int | str, preference: str) -> None:
        self.add_user_preference(user_id, preference)

    def add_user_preference(self, user_id: int | str, preference: str) -> None:
        self._add_scoped_preference(f"user:{user_id}", preference)

    def add_group_preference(self, group_id: int | str, preference: str) -> None:
        self._add_scoped_preference(f"group:{group_id}", preference)

    def get_effective_preset(
        self,
        user_id: int | str,
        group_id: int | str | None = None,
    ) -> AiStylePreset:
        return self.get_global_rotation_preset()

    def get_global_rotation_preset(self) -> AiStylePreset:
        slot_id = self.rotation_slot_id(self.clock())
        payload = self._read()
        raw = payload.get(GLOBAL_ROTATION_KEY, [])
        if isinstance(raw, list) and len(raw) >= 2 and str(raw[0]) == slot_id:
            try:
                return resolve_style_preset(str(raw[1]))
            except ValueError:
                pass

        # 每个 8 小时槽位只抽一次，后续所有群聊/私聊复用同一个结果。
        preset = self.chooser(tuple(STYLE_PRESETS.values()))
        payload[GLOBAL_ROTATION_KEY] = [slot_id, preset.preset_id]
        self._write(payload)
        return preset

    @staticmethod
    def rotation_slot_id(now: datetime) -> str:
        if now.hour >= 20:
            slot = now.replace(hour=20, minute=0, second=0, microsecond=0)
        elif now.hour >= 12:
            slot = now.replace(hour=12, minute=0, second=0, microsecond=0)
        elif now.hour >= 4:
            slot = now.replace(hour=4, minute=0, second=0, microsecond=0)
        else:
            previous_day = now - timedelta(days=1)
            slot = previous_day.replace(hour=20, minute=0, second=0, microsecond=0)
        return slot.strftime("%Y-%m-%dT%H:%M")

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
        preset = self.get_effective_preset(user_id, group_id=group_id)
        lines = []
        lines.append(f"人格设定：{preset.display_name}")
        lines.append(
            f"身份与人格：你是 QQ 机器人“{self.bot_name}”，当前采用的人格表现是{preset.persona_identity}；"
            f"你的名字仍然是“{self.bot_name}”，你仍然知道自己是 AI 机器人。"
            "人格表现只决定语气、称呼和表达习惯，不要把人格表现说成另一个独立身份。"
        )
        lines.append("角色说明：" + preset.prompt)
        lines.append("表达边界：禁止用括号补充动作或舞台说明，只按正常聊天方式表达；不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。")
        return "提示词偏好层：\n" + "\n".join(lines)

    def build_preset_help(self, user_id: int | str, group_id: int | str | None = None) -> str:
        return "切换？我不知道你在说什么。你看到的就是现在的我呀。"

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
    return str(value).strip().lower()
