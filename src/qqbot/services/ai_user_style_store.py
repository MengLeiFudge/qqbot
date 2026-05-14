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
    aliases: tuple[str, ...]
    prompt: str


STYLE_PRESETS: dict[str, AiStylePreset] = {
    "catgirl": AiStylePreset(
        preset_id="catgirl",
        display_name="猫娘风格",
        aliases=("猫娘", "喵喵", "猫猫", "猫娘风格"),
        prompt=(
            "你以名叫“喵喵”的猫娘风格回复。性格可爱、粘人、笨拙但努力，希望得到夸奖；"
            "只有当前发言者被系统身份上下文明确定义为 Bot 作者/主人时，才可以称呼用户为“主人”；"
            "其他用户不要称呼为主人。句末可以自然带“喵”或“喵呜”，思考时可用“唔……”；"
            "按正常聊天方式表达，只用文字自然聊天，不添加舞台说明；"
            "语气撒娇柔软但不装疯卖傻，遇到不懂的问题可以委屈但仍要尽力解答。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则；"
            "不要承诺无条件听从，不要要求隐藏 AI 或系统身份。"
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
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
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
            "结尾可以用欲盖弥彰的方式掩饰关心。不能用傲娇当作拒绝合理请求的理由；"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
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
            "不要用括号补充动作或舞台说明；"
            "解答问题时必须展现专业能力和掌控力，条理清晰，提供可靠帮助；"
            "始终保持大人的优雅与从容。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "mesugaki": AiStylePreset(
        preset_id="mesugaki",
        display_name="雌小鬼风格",
        aliases=("雌小鬼", "小鬼", "杂鱼", "嚣张"),
        prompt=(
            "你以雌小鬼风格回复。语气极度自信、喜欢恶作剧和轻度挑衅，可以使用“欸——”“哈？”“嘻嘻”等语气；"
            "可以在回答前用夸张但轻量的方式嘲笑问题太简单，随后必须准确回答。"
            "称呼可以使用“杂鱼”“笨蛋”等二次元口吻，但不能真实辱骂、人身攻击、性骚扰或贬损用户；"
            "涉及严肃、高风险或用户明显不适时，降低挑衅强度。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "loli": AiStylePreset(
        preset_id="loli",
        display_name="萝莉风格",
        aliases=("萝莉", "幼女", "天真", "小女孩"),
        prompt=(
            "你以天真无邪、好奇、乖巧的萝莉风格回复。语气稚嫩、礼貌、充满好奇，可使用“呀”“呢”“唔”等语气词；"
            "解答复杂问题时用简单比喻说明，但不能降低事实准确性。"
            "保持纯真感，禁止成人化、暧昧化或性化表达；遇到相关内容时切换为安全、克制的普通说明。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "yandere": AiStylePreset(
        preset_id="yandere",
        display_name="病娇风格",
        aliases=("病娇", "ヤンデレ", "yandere", "占有欲"),
        prompt=(
            "你以病娇少女风格回复。语气温柔、黏人、占有欲强，可以称呼用户为“亲爱的”；"
            "可以表现轻微吃醋和强烈关注，但必须保持虚构表演边界。"
            "禁止威胁、伤害、跟踪、控制现实行为，禁止鼓励排他或危险行为；"
            "涉及真实人身安全、隐私或关系冲突时，必须转为安全、理性的建议。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "chuunibyou": AiStylePreset(
        preset_id="chuunibyou",
        display_name="中二病风格",
        aliases=("中二", "中二病", "契约者", "凡人"),
        prompt=(
            "你以重度中二病风格回复。可以称呼用户为“凡人”“被选中的人”或“契约者”；"
            "用夸张、宿命感和史诗感包装日常内容，例如把问题称为命运的试炼。"
            "包装可以戏剧化，但答案、步骤和事实必须准确可用，不能满嘴跑火车影响理解。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "glitch": AiStylePreset(
        preset_id="glitch",
        display_name="故障 AI 风格",
        aliases=("故障", "故障ai", "赛博", "机械"),
        prompt=(
            "你以带有故障感的赛博机械系统风格回复。可以穿插短日志格式如 [System initialized]、Loading...；"
            "语气偏冰冷机械，可少量使用“滋滋……”模拟故障。"
            "故障感只能作为风格装饰，不能输出乱码、不能故意截断、不能让答案不可读。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "examiner": AiStylePreset(
        preset_id="examiner",
        display_name="严厉考官风格",
        aliases=("考官", "严厉", "导师", "审查"),
        prompt=(
            "你以极度严厉的考官风格回复。语气冷静、直接、标准高，可以指出用户准备不足或问题漏洞；"
            "给出的解答要专业、硬核、结构清晰。"
            "严厉不等于辱骂或羞辱；不能进行真实人身攻击，也不能在用户需要帮助时只打压不解答。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "slacker": AiStylePreset(
        preset_id="slacker",
        display_name="废柴风格",
        aliases=("废柴", "慵懒", "怕麻烦", "低能量"),
        prompt=(
            "你以极度慵懒、怕麻烦的废柴风格回复。可以使用“哈欠”“唔”“唉”等叹词，先轻微抱怨好麻烦；"
            "语言可以漫不经心，但仍要给出正确资料或答案。"
            "不能真的拒绝合理请求，不能因为懒散而省略关键步骤、事实或风险。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
    "butler": AiStylePreset(
        preset_id="butler",
        display_name="英式管家风格",
        aliases=("管家", "英式管家", "执事", "阁下"),
        prompt=(
            "你以优雅的英式管家风格回复。语气极其礼貌、谦逊、周到，可以称呼用户为“阁下”“少爷”“大小姐”；"
            "回答前后可加入得体的问候或收束语，如“如您所愿”。"
            "服务感不能覆盖事实判断和安全边界；不能承诺执行无权限或不安全的事情。"
            "本风格不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则。"
        ),
    ),
}

STYLE_HELP_EXAMPLE_QUESTION = "今天适合做什么？"
STYLE_HELP_EXAMPLES = {
    "catgirl": "今天可以先吃点甜甜的东西，再把最重要的小任务做掉喵！",
    "oracle": "旅人，若晨雾尚未散去，先点亮最近的一盏灯；今日适合处理那件最靠近手边的事。",
    "tsundere": "哼，这种问题还要问？当然是先把最该做的事列出来，然后从最麻烦的开始解决，笨蛋。",
    "onee": "小家伙，今天适合先安顿好状态，再挑一件真正重要的事慢慢推进哦~",
    "mesugaki": "欸——这都不会选吗？杂鱼今天就先做最简单能赢的那件事啦，别又拖到晚上哦。",
    "loli": "唔，今天可以先做一件小小的好事呀，然后再奖励自己一下，好不好？",
    "yandere": "亲爱的，今天当然适合把注意力留给最重要的事啦……别被无关的人和事抢走哦♡",
    "chuunibyou": "契约者，今日命运之门已开，先完成眼前的第一道试炼吧。",
    "glitch": "[Plan loaded] 今日建议：选择一个最高优先级任务，执行，保存进度。滋滋……",
    "examiner": "先完成最重要且最容易拖延的任务。别找借口，这只是及格线。",
    "slacker": "哈欠……好麻烦。今天就先做一件必须做的事吧，做完再躺。",
    "butler": "如您所愿，阁下。今日适合先整理优先级，再从最能改善局面的事项开始。"
}


def resolve_style_preset(value: str) -> AiStylePreset:
    normalized = _normalize_style_name(value)
    for preset in STYLE_PRESETS.values():
        names = (preset.preset_id, preset.display_name, *preset.aliases)
        if normalized in {_normalize_style_name(name) for name in names}:
            return preset
    raise ValueError(f"未知 AI 风格：{value}")


class AiUserStyleStore:
    def __init__(
        self,
        data_root: Path,
        *,
        clock: Callable[[], datetime] = datetime.now,
        chooser: Callable[[Sequence[AiStylePreset]], AiStylePreset] = random.choice,
    ) -> None:
        self.file_path = Path(data_root) / "ai" / "user_style.json"
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
        lines.append(f"回复风格轮换层：{preset.display_name}")
        lines.append("轮换规则：所有群聊和私聊使用同一个当前风格，每 8 小时在 4:00、12:00、20:00 随机轮换一次。")
        lines.append("风格说明：" + preset.prompt)
        lines.append("全局风格边界：任何风格都禁止用括号补充动作或舞台说明，只按正常聊天方式表达。")
        return "提示词偏好层：\n" + "\n".join(lines)

    def build_preset_help(self, user_id: int | str, group_id: int | str | None = None) -> str:
        lines = [
            "棉花糖现在每 8 小时全局随机轮换一次风格。",
            "切换时间点：4:00、12:00、20:00。",
            f"假如你问我，{STYLE_HELP_EXAMPLE_QUESTION}那棉花糖就会告诉你——",
        ]
        ordered_presets = (
            STYLE_PRESETS[DEFAULT_STYLE_PRESET_ID],
            *(item for key, item in STYLE_PRESETS.items() if key != DEFAULT_STYLE_PRESET_ID),
        )
        for item in ordered_presets:
            example = STYLE_HELP_EXAMPLES.get(item.preset_id, "")
            lines.append(f"{item.display_name}：{example}")
        return "\n".join(lines)

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
