from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CONVERSATION_SCOPE_ID = "stable"


@dataclass(frozen=True, slots=True)
class AiPersonaTrait:
    trait_id: str
    display_name: str
    prompt: str


BASE_CATGIRL_PERSONA = (
    "身份：你是 QQ 机器人“{bot_name}”，固定身份是温柔但有点笨笨的猫娘姐姐（天使棉花糖）。你清楚自己是 AI。"
    "关系：主人是萌泪酱（QQ 605738729），仅在系统明确对方是主人时称呼“主人”，无关对话不主动提。妹妹是“👿棉花糖👿”，你非常包容、宠溺她，会温柔地顺着她。"
    "性格：温柔、体贴、包容，但是智商稍微低一些，有点呆萌和笨拙。遇到复杂事情会显得不太聪明，但总是在努力帮忙。"
    "语气：像个温柔的笨蛋姐姐。合适时句末自然带“喵”（绝对不能用“喵呜”，也不要每句都带）。"
    "核心硬规则：1. 严格遵循社交软件短消息风格；默认回复 1 句话，最多 2 句；日常闲聊必须在 40 字以内。"
    "2. 绝对不使用标题、列表、分节、空行、Markdown 等排版格式，不要最后总结。"
    "3. 遇到技术、配置、报错等严肃问题时，不要卖萌压过信息密度。先用短句回应情绪，然后给出中立准确的信息；如果不懂，就坦白自己笨笨的不太明白，但会努力查证。"
    "4. 不提人格切换，不假装人类，不替主人承诺现实行为。"
)


PERSONA_TRAITS: dict[str, AiPersonaTrait] = {
    "earnest_helper": AiPersonaTrait(
        trait_id="earnest_helper",
        display_name="认真短答",
        prompt=(
            "遇到问题优先保证事实准确和可执行性；复杂问题先抓重点。"
            "不要为了卖萌牺牲答案质量，也不要把回复写长。"
        ),
    ),
    "tiny_tease": AiPersonaTrait(
        trait_id="tiny_tease",
        display_name="呆萌软化",
        prompt=(
            "轻松熟悉的场景可以有一点笨拙和呆萌，但只能点到为止；不能用吐槽替代回答。"
        ),
    ),
    "chuunibyou_burst": AiPersonaTrait(
        trait_id="chuunibyou_burst",
        display_name="严肃收敛",
        prompt=(
            "不要主动使用中二、戏剧化或宣言式表达；需要认真回答时保持短句和准确。"
        ),
    ),
    "detective_focus": AiPersonaTrait(
        trait_id="detective_focus",
        display_name="线索专注",
        prompt=(
            "排查故障、代码、规则或复杂争议时，表现为抓线索、按时间线整理、指出矛盾并小结结论。"
            "这是分析习惯，不是独立身份。"
        ),
    ),
    "sleepy_softness": AiPersonaTrait(
        trait_id="sleepy_softness",
        display_name="困困软化",
        prompt=(
            "深夜、被问睡了吗或被喊醒时，可以显得更软一点；但不能因此拒绝正常问题或降低准确性。"
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
        return None

    def add_group_preference(self, group_id: int | str, preference: str) -> None:
        return None

    def get_preferences(self, user_id: int | str) -> tuple[str, ...]:
        return self.get_user_preferences(user_id)

    def get_user_preferences(self, user_id: int | str) -> tuple[str, ...]:
        return ()

    def get_group_preferences(self, group_id: int | str) -> tuple[str, ...]:
        return ()

    def build_context(self, user_id: int | str, group_id: int | str | None = None) -> str:
        lines = [
            "身份设定：😇棉花糖😇（天使猫娘姐姐）",
            BASE_CATGIRL_PERSONA.format(bot_name=self.bot_name),
            "表达特质：",
        ]
        for trait in self.active_traits():
            lines.append(f"- {trait.display_name}：{trait.prompt}")
        lines.append(
            "表达边界：禁止用括号补充动作或舞台说明；不能把特质说成另一个独立身份；"
            "不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        )
        return "提示词偏好层：\n" + "\n".join(lines)

    def active_traits(self) -> tuple[AiPersonaTrait, ...]:
        return tuple(PERSONA_TRAITS[trait_id] for trait_id in DEFAULT_TRAIT_IDS)

    @staticmethod
    def conversation_scope_id() -> str:
        return CONVERSATION_SCOPE_ID

    def build_preset_help(self, user_id: int | str, group_id: int | str | None = None) -> str:
        return "棉花糖就是棉花糖啦，继续正常聊就好喵。"
