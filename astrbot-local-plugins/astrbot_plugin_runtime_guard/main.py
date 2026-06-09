from __future__ import annotations

from astrbot.api import logger
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


INTERNAL_ERROR_PREFIXES = (
    "Error occurred while processing agent request:",
)


def _plain_text(message_chain) -> str:
    parts: list[str] = []
    for segment in getattr(message_chain, "chain", []):
        if isinstance(segment, Plain):
            parts.append(segment.text)
    return "".join(parts).strip()


@register(
    "astrbot_plugin_runtime_guard",
    "MengLei",
    "拦截 AstrBot 内部错误文本，避免原始 Agent/LLM 异常发到 QQ。",
    "0.1.1",
)
class RuntimeGuardPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._install_aiocqhttp_error_guard()

    def _install_aiocqhttp_error_guard(self) -> None:
        if getattr(AiocqhttpMessageEvent, "_runtime_guard_installed", False):
            logger.info("[RuntimeGuard] aiocqhttp error guard already installed")
            return

        original_send_message = AiocqhttpMessageEvent.send_message

        async def guarded_send_message(
            cls,
            bot,
            message_chain,
            event=None,
            is_group: bool = False,
            session_id: str | None = None,
        ) -> None:
            text = _plain_text(message_chain)
            if any(text.startswith(prefix) for prefix in INTERNAL_ERROR_PREFIXES):
                logger.error(
                    "[RuntimeGuard] suppressed internal agent error from user output: "
                    "session_id=%s is_group=%s message=%s",
                    session_id,
                    is_group,
                    text,
                )
                return
            await original_send_message.__func__(
                cls,
                bot,
                message_chain,
                event=event,
                is_group=is_group,
                session_id=session_id,
            )

        AiocqhttpMessageEvent.send_message = classmethod(guarded_send_message)
        AiocqhttpMessageEvent._runtime_guard_installed = True
        logger.info("[RuntimeGuard] aiocqhttp internal error guard installed")
