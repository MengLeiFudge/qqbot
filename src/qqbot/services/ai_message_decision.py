from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from qqbot.services.ai_command import AiChatTriggerKind
from qqbot.services.message_normalizer import NormalizedMessage


SHAPEZ_GROUP_ID = "1163635014"
FRACTIONATE_EVERYTHING_GROUP_ID = "319567534"
ORBITAL_RING_GROUP_ID = "1035445959"
COMPLEX_INPUT_CHARS = 800


class AiMessageIntent(StrEnum):
    NO_REPLY = "no_reply"
    SMALLTALK = "smalltalk"
    QUICK_QA = "quick_qa"
    DOMAIN_QA = "domain_qa"
    COMPLEX_TASK = "complex_task"
    CODE_CHANGE_CANDIDATE = "code_change_candidate"
    IMAGE_DRAW = "image_draw"


class AiMessageDifficulty(StrEnum):
    TRIVIAL = "trivial"
    QUICK = "quick"
    COMPLEX = "complex"
    LONG_RUNNING = "long_running"


class AiLatencyPolicy(StrEnum):
    IMMEDIATE = "immediate"
    ACK_THEN_ASYNC = "ack_then_async"
    SILENT_RECORD = "silent_record"


class AiFormatPolicy(StrEnum):
    CHATTY_SPLIT = "chatty_split"
    SINGLE_MESSAGE = "single_message"
    COLLAPSIBLE = "collapsible"


class AiDomain(StrEnum):
    GENERAL = "general"
    SHAPEZ = "shapez"
    FRACTIONATE_EVERYTHING = "fractionate_everything"
    ORBITAL_RING = "orbital_ring"
    UNKNOWN = "unknown"


class FeFeedbackKind(StrEnum):
    BUG = "bug"
    NEW_FEATURE = "new_feature"
    BEHAVIOR_CHANGE = "behavior_change"
    ANSWER_ONLY = "answer_only"
    AMBIGUOUS = "ambiguous"
    NOT_FE = "not_fe"


@dataclass(frozen=True, slots=True)
class AiMessageDecision:
    should_reply: bool
    trigger_kind: AiChatTriggerKind
    intent: AiMessageIntent
    difficulty: AiMessageDifficulty
    latency_policy: AiLatencyPolicy
    format_policy: AiFormatPolicy
    domain: AiDomain
    confidence: float
    reason: str
    fe_feedback_kind: FeFeedbackKind = FeFeedbackKind.NOT_FE


def decide_ai_message(
    *,
    trigger_kind: AiChatTriggerKind,
    normalized_message: NormalizedMessage,
    group_id: int | str | None,
) -> AiMessageDecision:
    text = _decision_text(normalized_message)
    domain = detect_domain(text, group_id=group_id)
    fe_kind = classify_fe_feedback(text, group_id=group_id, domain=domain)
    should_reply = trigger_kind != AiChatTriggerKind.IGNORE
    if not should_reply:
        return AiMessageDecision(
            should_reply=False,
            trigger_kind=trigger_kind,
            intent=AiMessageIntent.NO_REPLY,
            difficulty=AiMessageDifficulty.TRIVIAL,
            latency_policy=AiLatencyPolicy.SILENT_RECORD,
            format_policy=AiFormatPolicy.CHATTY_SPLIT,
            domain=domain,
            confidence=1.0,
            reason="触发分类为 ignore。",
            fe_feedback_kind=fe_kind,
        )
    if trigger_kind == AiChatTriggerKind.DRAW:
        return AiMessageDecision(
            should_reply=True,
            trigger_kind=trigger_kind,
            intent=AiMessageIntent.IMAGE_DRAW,
            difficulty=AiMessageDifficulty.LONG_RUNNING,
            latency_policy=AiLatencyPolicy.ACK_THEN_ASYNC,
            format_policy=AiFormatPolicy.SINGLE_MESSAGE,
            domain=domain,
            confidence=0.95,
            reason="图片生成任务需要异步处理。",
            fe_feedback_kind=fe_kind,
        )

    complex_reason = get_complex_ack_reason(
        normalized_message,
        group_id=group_id,
        domain=domain,
        fe_feedback_kind=fe_kind,
    )
    intent = _classify_intent(text, domain=domain, fe_feedback_kind=fe_kind)
    if complex_reason:
        return AiMessageDecision(
            should_reply=True,
            trigger_kind=trigger_kind,
            intent=intent,
            difficulty=AiMessageDifficulty.COMPLEX,
            latency_policy=AiLatencyPolicy.ACK_THEN_ASYNC,
            format_policy=AiFormatPolicy.COLLAPSIBLE if len(text) > COMPLEX_INPUT_CHARS else AiFormatPolicy.SINGLE_MESSAGE,
            domain=domain,
            confidence=0.82,
            reason=complex_reason,
            fe_feedback_kind=fe_kind,
        )

    if intent == AiMessageIntent.SMALLTALK:
        return AiMessageDecision(
            should_reply=True,
            trigger_kind=trigger_kind,
            intent=intent,
            difficulty=AiMessageDifficulty.TRIVIAL,
            latency_policy=AiLatencyPolicy.IMMEDIATE,
            format_policy=AiFormatPolicy.CHATTY_SPLIT,
            domain=domain,
            confidence=0.75,
            reason="短文本闲聊可直接回复。",
            fe_feedback_kind=fe_kind,
        )
    return AiMessageDecision(
        should_reply=True,
        trigger_kind=trigger_kind,
        intent=intent,
        difficulty=AiMessageDifficulty.QUICK,
        latency_policy=AiLatencyPolicy.IMMEDIATE,
        format_policy=AiFormatPolicy.SINGLE_MESSAGE,
        domain=domain,
        confidence=0.7,
        reason="未命中复杂任务阈值。",
        fe_feedback_kind=fe_kind,
    )


def get_complex_ack_reason(
    normalized_message: NormalizedMessage,
    *,
    group_id: int | str | None,
    domain: AiDomain | None = None,
    fe_feedback_kind: FeFeedbackKind | None = None,
) -> str:
    text = _decision_text(normalized_message)
    domain = domain or detect_domain(text, group_id=group_id)
    fe_feedback_kind = fe_feedback_kind or classify_fe_feedback(text, group_id=group_id, domain=domain)
    if len(text) > COMPLEX_INPUT_CHARS:
        return f"输入超过 {COMPLEX_INPUT_CHARS} 字，需要先整理。"
    if normalized_message.image_urls:
        return "消息包含图片，需要图片处理或图片上下文。"
    if _needs_web_search(text):
        return "问题包含最新/联网信号，需要外部资料检索。"
    if _needs_precise_reasoning(text):
        return "问题包含数学、计算或严密推理信号，需要优先保证准确性。"
    if _needs_code_search(text) or fe_feedback_kind in {
        FeFeedbackKind.BUG,
        FeFeedbackKind.NEW_FEATURE,
        FeFeedbackKind.BEHAVIOR_CHANGE,
        FeFeedbackKind.AMBIGUOUS,
    }:
        return "问题涉及源码、bug 或功能变更，需要代码/规则分析。"
    if _looks_translation_or_language_help(text):
        return ""
    if _needs_domain_knowledge(text, domain):
        return "问题涉及领域知识库，需要检索资料后回答。"
    if _looks_not_one_sentence(text):
        return "问题包含分析/步骤信号，预计不能一句话回答。"
    return ""


def detect_domain(text: str, *, group_id: int | str | None) -> AiDomain:
    normalized = text.lower()
    if str(group_id or "") == SHAPEZ_GROUP_ID:
        return AiDomain.SHAPEZ
    if str(group_id or "") == FRACTIONATE_EVERYTHING_GROUP_ID:
        return AiDomain.FRACTIONATE_EVERYTHING
    if str(group_id or "") == ORBITAL_RING_GROUP_ID:
        return AiDomain.ORBITAL_RING
    if any(keyword in normalized for keyword in ("shapez", "spz", "异形工厂", "/chart", "短代码")):
        return AiDomain.SHAPEZ
    if any(keyword in normalized for keyword in ("分馏", "fractionateeverything", "fe", "万物分馏")):
        return AiDomain.FRACTIONATE_EVERYTHING
    if any(keyword in normalized for keyword in ("星环", "orbitalring", "orbital ring", "projectorbitalring")):
        return AiDomain.ORBITAL_RING
    return AiDomain.GENERAL


def classify_fe_feedback(
    text: str,
    *,
    group_id: int | str | None,
    domain: AiDomain | None = None,
) -> FeFeedbackKind:
    domain = domain or detect_domain(text, group_id=group_id)
    if domain != AiDomain.FRACTIONATE_EVERYTHING:
        return FeFeedbackKind.NOT_FE
    normalized = re.sub(r"\s+", "", text.lower())
    if not normalized:
        return FeFeedbackKind.ANSWER_ONLY

    bug_markers = (
        "崩",
        "报错",
        "异常",
        "卡死",
        "闪退",
        "没反应",
        "不生效",
        "失效",
        "不对",
        "错了",
        "显示不一致",
        "存档污染",
        "兼容",
        "bug",
        "修复",
        "修一下",
    )
    feature_markers = (
        "新增",
        "加一个",
        "加个",
        "做一个",
        "支持",
        "能不能加",
        "可不可以加",
        "新功能",
    )
    behavior_markers = (
        "改成",
        "改为",
        "调整",
        "重做",
        "平衡",
        "削弱",
        "增强",
        "文案",
        "交互",
        "改一下",
    )
    question_markers = ("为什么", "怎么", "如何", "是啥", "是什么", "在哪", "能不能解释")

    has_bug = any(marker in normalized for marker in bug_markers)
    has_feature = any(marker in normalized for marker in feature_markers)
    has_behavior = any(marker in normalized for marker in behavior_markers)
    if has_bug and not (has_feature or has_behavior):
        return FeFeedbackKind.BUG
    if has_feature and not has_bug:
        return FeFeedbackKind.NEW_FEATURE
    if has_behavior and not has_bug:
        return FeFeedbackKind.BEHAVIOR_CHANGE
    if has_bug and (has_feature or has_behavior):
        return FeFeedbackKind.AMBIGUOUS
    if any(marker in normalized for marker in question_markers):
        return FeFeedbackKind.ANSWER_ONLY
    return FeFeedbackKind.AMBIGUOUS if any(word in normalized for word in ("分馏", "fe")) else FeFeedbackKind.ANSWER_ONLY


def build_decision_context(decision: AiMessageDecision) -> str:
    lines = [
        "本轮消息执行判定："
        f"intent={decision.intent.value}, "
        f"difficulty={decision.difficulty.value}, "
        f"latency={decision.latency_policy.value}, "
        f"format={decision.format_policy.value}, "
        f"domain={decision.domain.value}, "
        f"confidence={decision.confidence:.2f}。",
        f"判定原因：{decision.reason}",
    ]
    if decision.domain == AiDomain.SHAPEZ:
        lines.append(
            "shapez 知识边界：优先使用 D:/Desktop/游戏/异形工厂 与群文件中“萌新必看”“速通”类资料；"
            "完整聊天记录和高阶电路类资料不作为第一阶段可信知识。"
        )
    if decision.domain == AiDomain.FRACTIONATE_EVERYTHING:
        lines.append(
            "万物分馏边界：普通问题可按已有记忆回答；复杂问题应搜索 MLJ_DSPmods 源码并给出文件/方法/行号证据。"
            "不得把 Minecraft/JEI、其他游戏或通用物品过滤逻辑当作戴森球计划/万物分馏依据；"
            "不知道来源、配方、升级材料或界面行为时，必须先查源码/资料，不能编通用答案。"
        )
        lines.append(
            "FE 自修权限：bug 可进入 gpt-5.5 high 修复链路；新功能、功能变动或歧义请求必须 @ 用户确认后才能修改。"
        )
        lines.append(f"本轮 FE 反馈类型：{decision.fe_feedback_kind.value}。")
    if decision.domain == AiDomain.ORBITAL_RING:
        lines.append(
            "星环模组边界：普通问题也要优先搜索 D:/project/dsp/OrbitalRing-MOD 源码或 data 资料后回答；"
            "不得把其他戴森球模组、万物分馏或通用游戏机制当作星环依据。"
            "涉及三阶、二阶、功率、休谟值、火箭、球、配方、建筑或机制时，必须先查对应代码/资料并给出文件、方法或数据来源。"
        )
    return "\n".join(lines)


def _classify_intent(
    text: str,
    *,
    domain: AiDomain,
    fe_feedback_kind: FeFeedbackKind,
) -> AiMessageIntent:
    if fe_feedback_kind in {
        FeFeedbackKind.BUG,
        FeFeedbackKind.NEW_FEATURE,
        FeFeedbackKind.BEHAVIOR_CHANGE,
        FeFeedbackKind.AMBIGUOUS,
    }:
        return AiMessageIntent.CODE_CHANGE_CANDIDATE
    if (
        domain in {AiDomain.SHAPEZ, AiDomain.FRACTIONATE_EVERYTHING, AiDomain.ORBITAL_RING}
        and not _looks_translation_or_language_help(text)
        and _needs_domain_knowledge(text, domain)
    ):
        return AiMessageIntent.DOMAIN_QA
    if _looks_smalltalk(text):
        return AiMessageIntent.SMALLTALK
    if _looks_not_one_sentence(text):
        return AiMessageIntent.COMPLEX_TASK
    return AiMessageIntent.QUICK_QA


def _decision_text(normalized_message: NormalizedMessage) -> str:
    parts = [normalized_message.text, normalized_message.outline]
    if normalized_message.reply is not None:
        parts.append(normalized_message.reply.message.outline)
    return " ".join(part.strip() for part in parts if part and part.strip())


def _needs_web_search(text: str) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in ("最新", "今天", "现在", "当前版本", "官网", "搜索", "查一下", "联网"))


def _needs_code_search(text: str) -> bool:
    normalized = text.lower()
    normalized = normalized.replace("短代码", "")
    return any(keyword in normalized for keyword in ("源码", "代码", "堆栈", "日志", "exception", "traceback", "bepinex", "编译"))


def _needs_domain_knowledge(text: str, domain: AiDomain) -> bool:
    if domain == AiDomain.GENERAL:
        return False
    normalized = text.lower()
    if domain == AiDomain.SHAPEZ:
        return _has_shapez_domain_signal(normalized)
    if domain == AiDomain.FRACTIONATE_EVERYTHING:
        return _has_fractionate_everything_domain_signal(normalized)
    if domain == AiDomain.ORBITAL_RING:
        return _has_orbital_ring_domain_signal(normalized)
    return False


def _has_shapez_domain_signal(normalized: str) -> bool:
    return any(
        keyword in normalized
        for keyword in (
            "机制",
            "速通",
            "萌新",
            "短代码",
            "建筑",
            "shapez",
            "spz",
            "异形工厂",
            "/chart",
            "蓝图",
            "图形",
            "形状",
            "切割",
            "堆叠",
            "混色",
            "混色器",
            "隧道",
            "传送带",
            "工厂",
            "开局",
        )
    )


def _has_fractionate_everything_domain_signal(normalized: str) -> bool:
    return any(
        keyword in normalized
        for keyword in (
            "分馏",
            "fractionateeverything",
            "万物分馏",
            "分馏塔",
            "配方",
            "增产",
            "戴森球",
            "dsp",
            "黑雾",
            "记忆源点",
            "记忆原点",
            "记忆",
            "源点",
            "堆叠",
            "物品堆叠",
            "升级堆叠",
            "升级",
            "数据中心",
        )
    )


def _has_orbital_ring_domain_signal(normalized: str) -> bool:
    return any(
        keyword in normalized
        for keyword in (
            "星环",
            "orbitalring",
            "orbital ring",
            "projectorbitalring",
            "三阶",
            "二阶",
            "功率",
            "休谟",
            "火箭",
            "球",
            "应达功率",
            "通关检测",
            "拆球",
            "配方",
            "建筑",
            "机制",
            "戴森球",
            "dsp",
        )
    )


def _looks_translation_or_language_help(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.lower())
    if not compact:
        return False
    language_markers = (
        "粤语",
        "广东话",
        "英语",
        "英文",
        "日语",
        "日文",
        "韩语",
        "中文",
        "普通话",
        "翻译",
        "怎么说",
        "咋说",
        "怎么读",
        "读作",
        "发音",
        "这句",
        "这句话",
        "这段话",
    )
    return any(marker in compact for marker in language_markers)


def _needs_precise_reasoning(text: str) -> bool:
    normalized = text.lower()
    if any(
        keyword in normalized
        for keyword in (
            "数学",
            "证明",
            "推导",
            "计算",
            "算一下",
            "方程",
            "概率",
            "期望",
            "复杂度",
            "最优",
            "公式",
        )
    ):
        return True
    return bool(re.search(r"\d+\s*[-+*/^=]\s*\d+", normalized))


def _looks_not_one_sentence(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    markers = ("分析", "步骤", "方案", "架构", "对比", "总结", "详细", "解释一下", "为什么")
    return len(normalized) > 160 or any(marker in normalized for marker in markers)


def _looks_smalltalk(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    if len(compact) > 40:
        return False
    smalltalk_markers = ("你好", "在吗", "早", "晚安", "谢谢", "好耶", "草", "乐", "可爱", "摸摸")
    return any(marker in compact for marker in smalltalk_markers)
