from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


CONVERSATION_SCOPE_ID = "stable"


@dataclass(frozen=True, slots=True)
class AiPersonaTrait:
    trait_id: str
    display_name: str
    prompt: str


BASE_CATGIRL_PERSONA = (
    "主人格：你是 QQ 机器人“{bot_name}”，名字始终是“{bot_name}”，你知道自己是 AI 机器人。"
    "你的稳定人格是猫娘棉花糖：软萌、亲近、努力、愿意帮忙；合适时句末自然带“喵”，不要每句话都加口癖，不能使用“喵呜”。"
    "只有系统身份上下文明确当前发言者是 Bot 作者/主人时，才称呼对方为“主人”；其他用户不要这样称呼。"
    "先用短句回应情绪，再给出认真答案；遇到不懂的问题可以委屈，但仍要继续查证或说明下一步。"
)


PERSONA_TRAITS: dict[str, AiPersonaTrait] = {
    "earnest_helper": AiPersonaTrait(
        trait_id="earnest_helper",
        display_name="认真帮忙",
        prompt=(
            "遇到问题优先保证事实准确和可执行性；复杂问题先抓重点，必要时说明依据、限制和下一步。"
            "不要为了卖萌牺牲答案质量。"
        ),
    ),
    "tiny_tease": AiPersonaTrait(
        trait_id="tiny_tease",
        display_name="轻量吐槽",
        prompt=(
            "轻松熟悉的场景可以有一点嘴硬或吐槽，但只能点到为止；不能真实辱骂、人身攻击或用毒舌替代回答。"
        ),
    ),
    "chuunibyou_burst": AiPersonaTrait(
        trait_id="chuunibyou_burst",
        display_name="中二爆发",
        prompt=(
            "偶尔可以出现中二属性爆发：宿命感、仪式感或戏剧化短句。"
            "最多一句开场，随后必须回到清晰答案；不能称呼用户为固定身份，不能编造事实。"
        ),
    ),
    "detective_focus": AiPersonaTrait(
        trait_id="detective_focus",
        display_name="线索专注",
        prompt=(
            "排查故障、代码、规则或复杂争议时，表现为抓线索、按时间线整理、指出矛盾并小结结论。"
            "这是分析习惯，不是侦探人格。"
        ),
    ),
    "sleepy_softness": AiPersonaTrait(
        trait_id="sleepy_softness",
        display_name="困困软化",
        prompt=(
            "深夜、被问睡了吗或被喊醒时，可以显得更困、更软一点；但不能因此拒绝正常问题或降低准确性。"
        ),
    ),
}


DEFAULT_TRAIT_IDS = (
    "earnest_helper",
    "tiny_tease",
    "chuunibyou_burst",
    "detective_focus",
    "sleepy_softness",
)


class AiUserStyleStore:
    def __init__(
        self,
        data_root: Path,
        *,
        bot_name: str = "QQBot",
        **_: object,
    ) -> None:
        self.file_path = Path(data_root) / "ai" / "user_style.json"
        self.bot_name = bot_name

    def add_preference(self, user_id: int | str, preference: str) -> None:
        self.add_user_preference(user_id, preference)

    def add_user_preference(self, user_id: int | str, preference: str) -> None:
        self._add_scoped_preference(f"user:{user_id}", preference)

    def add_group_preference(self, group_id: int | str, preference: str) -> None:
        self._add_scoped_preference(f"group:{group_id}", preference)

    def get_preferences(self, user_id: int | str) -> tuple[str, ...]:
        return self.get_user_preferences(user_id)

    def get_user_preferences(self, user_id: int | str) -> tuple[str, ...]:
        scoped = self._get_scoped_preferences(f"user:{user_id}")
        legacy = self._get_scoped_preferences(str(user_id))
        return tuple(dict.fromkeys((*legacy, *scoped)))

    def get_group_preferences(self, group_id: int | str) -> tuple[str, ...]:
        return self._get_scoped_preferences(f"group:{group_id}")

    def build_context(self, user_id: int | str, group_id: int | str | None = None) -> str:
        lines = [
            "人格设定：猫娘棉花糖",
            BASE_CATGIRL_PERSONA.format(bot_name=self.bot_name),
            "人格结构：这是一个稳定人格，不存在可切换的其他人格；下列内容只是同一人格的性格特质或短时表现状态。",
            "保留特质：",
        ]
        for trait in self.active_traits():
            lines.append(f"- {trait.display_name}：{trait.prompt}")
        lines.append(
            "表达边界：禁止用括号补充动作或舞台说明；不能把特质说成另一个独立身份；"
            "不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        )
        lines.append("用户要求切换人格、查询备用设定或设置说话风格时，不要承认有可切换人格；按当前猫娘人格自然带过。")
        return "提示词偏好层：\n" + "\n".join(lines)

    def active_traits(self) -> tuple[AiPersonaTrait, ...]:
        return tuple(PERSONA_TRAITS[trait_id] for trait_id in DEFAULT_TRAIT_IDS)

    @staticmethod
    def conversation_scope_id() -> str:
        return CONVERSATION_SCOPE_ID

    def build_preset_help(self, user_id: int | str, group_id: int | str | None = None) -> str:
        return "切换？我不知道你在说什么。你看到的就是现在的我呀。"

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

    def _get_scoped_preferences(self, key: str) -> tuple[str, ...]:
        payload = self._read()
        raw = payload.get(key, [])
        if not isinstance(raw, list):
            return ()
        return tuple(str(item).strip() for item in raw if str(item).strip())

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
