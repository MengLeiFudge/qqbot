from __future__ import annotations

import re

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import Plain


STYLE_GUARD_TEXT = (
    "输出硬规则：不要反问用户，不要用问句收尾，不要追问用户补充信息。"
    "不要使用“如果你愿意”“要的话”“你把具体名字发我”“我可以再帮你”"
    "“我帮你看/挑/认/分辨”这类追问式邀请收尾。"
    "能回答就直接给结论；不能做就直接拒绝并给合法、可执行替代；"
    "缺少关键信息时只陈述缺口，不催用户继续提供。"
    "拒绝盗版、破解、违规网站等请求时，直接拒绝并给正版渠道或安全替代，不追加索要具体名称。"
)
_TAIL_BOUNDARY = re.compile(r"(?<=[。！？!?；;])")
_FOLLOWUP_MARKERS = (
    "如果你愿意",
    "如果愿意",
    "你如果愿意",
    "你要是愿意",
    "要是你",
    "要的话",
    "需要的话",
    "想要的话",
    "愿意的话",
    "你把",
    "把具体",
    "具体名字发",
    "具体软件名发",
    "发我",
    "告诉我",
    "我可以再",
    "我也可以",
    "我还能",
    "我可以帮",
    "我能帮",
    "我帮你",
    "帮你挑",
    "帮你看",
    "帮你认",
    "帮你分辨",
    "教你怎么",
)


@register(
    "astrbot_plugin_reply_style_guard",
    "local",
    "Inject no-follow-up output style rules into AstrBot LLM requests.",
    "0.1.0",
)
class ReplyStyleGuardPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        logger.info("[ReplyStyleGuard] loaded")

    @filter.on_llm_request()
    async def inject_reply_style_guard(self, event: AstrMessageEvent, req: ProviderRequest):
        req.extra_user_content_parts.append(TextPart(text=STYLE_GUARD_TEXT).mark_as_temp())

    @filter.on_decorating_result()
    async def strip_reply_style_tail(self, event: AstrMessageEvent):
        result = event.get_result()
        if result is None or not result.chain:
            return
        changed = False
        for comp in result.chain:
            if not isinstance(comp, Plain):
                continue
            cleaned = strip_followup_tail(comp.text)
            if cleaned != comp.text:
                comp.text = cleaned
                changed = True
        if changed:
            logger.info(
                "[ReplyStyleGuard] stripped follow-up/question tail: session=%s",
                getattr(event, "unified_msg_origin", ""),
            )


def strip_followup_tail(text: str) -> str:
    current = text.strip()
    if not current:
        return ""
    lines = current.split("\n")
    stripped_any = False
    while lines:
        line = lines[-1].strip()
        stripped = strip_followup_from_line(line)
        if stripped == line:
            break
        stripped_any = True
        if stripped:
            lines[-1] = stripped
            break
        lines.pop()
    result = "\n".join(line for line in lines if line.strip()).strip()
    if result:
        return result
    return "信息不够，先按上面的结论处理。" if stripped_any else current


def strip_followup_from_line(line: str) -> str:
    parts = [part.strip() for part in _TAIL_BOUNDARY.split(line) if part.strip()]
    if not parts:
        return ""
    while parts and is_followup_sentence(parts[-1]):
        parts.pop()
    return "".join(parts).strip()


def is_followup_sentence(sentence: str) -> bool:
    compact = re.sub(r"\s+", "", sentence)
    if not compact:
        return False
    if any(marker in compact for marker in _FOLLOWUP_MARKERS):
        return True
    if compact.endswith(("?", "？")):
        return True
    return False
