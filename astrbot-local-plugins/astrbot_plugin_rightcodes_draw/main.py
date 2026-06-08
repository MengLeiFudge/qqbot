from __future__ import annotations

import asyncio
import socket

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.event_message_type import EventMessageType

from .logic import (
    FEATURE_MODE_FULL,
    NONEBOT2_HOST,
    NONEBOT2_PORT,
    RightCodesDrawClient,
    RightCodesDrawQuotaStore,
    format_draw_quota_exceeded_message,
    format_draw_start_message,
    format_rightcodes_draw_failure,
    format_rightcodes_draw_model_help,
    format_rightcodes_draw_points_mutation_denied,
    format_rightcodes_draw_points_status,
    format_rightcodes_draw_success,
    load_api_key,
    load_rightcodes_config,
    looks_like_rightcodes_draw_help_command,
    looks_like_rightcodes_draw_points_mutation_request,
    looks_like_rightcodes_draw_points_query,
    parse_rightcodes_draw_command,
    should_record_passive_group_points,
)


@register(
    "astrbot_plugin_rightcodes_draw",
    "local",
    "Migrate qqbot RightCodes image generation and draw point commands to AstrBot.",
    "0.1.0",
)
class RightCodesDrawPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self._config = load_rightcodes_config(config)
        self._draw_lock = asyncio.Semaphore(2)
        logger.info(
            "[RightCodesDraw] loaded: mode=%s data_root=%s api_key_env=%s multiplier=%s",
            self._config.feature_mode,
            self._config.data_root,
            self._config.api_key_env,
            self._config.point_multiplier,
        )

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def record_group_message_points(self, event: AstrMessageEvent):
        if not should_record_passive_group_points(
            feature_mode=self._config.feature_mode,
            nonebot2_online=is_nonebot2_online(),
        ):
            return
        if str(event.get_sender_id() or "") == str(event.get_self_id() or ""):
            return
        if not str(event.get_message_str() or "").strip():
            return
        store = RightCodesDrawQuotaStore(
            self._config.data_root,
            multiplier=self._config.point_multiplier,
        )
        await asyncio.to_thread(store.record_group_message, event.get_sender_id())

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_rightcodes_draw(self, event: AstrMessageEvent):
        text = str(event.get_message_str() or "").strip()
        if not text:
            return
        if not self._should_handle_command(event):
            return
        store = RightCodesDrawQuotaStore(
            self._config.data_root,
            multiplier=self._config.point_multiplier,
        )
        user_id = str(event.get_sender_id() or "")

        if looks_like_rightcodes_draw_points_mutation_request(text):
            yield event.plain_result(format_rightcodes_draw_points_mutation_denied())
            event.stop_event()
            return
        if looks_like_rightcodes_draw_points_query(text):
            balance = await asyncio.to_thread(store.get_balance, user_id)
            yield event.plain_result(format_rightcodes_draw_points_status(balance))
            event.stop_event()
            return
        if looks_like_rightcodes_draw_help_command(text):
            yield event.plain_result(format_rightcodes_draw_model_help())
            event.stop_event()
            return

        draw_request = parse_rightcodes_draw_command(text)
        if draw_request is None:
            return
        quota = await asyncio.to_thread(store.reserve, user_id, model=draw_request.model)
        if not quota.allowed:
            yield event.plain_result(format_draw_quota_exceeded_message(quota))
            event.stop_event()
            return

        yield event.plain_result(format_draw_start_message(quota))
        api_key = load_api_key(self._config.api_key_env)
        if not api_key:
            await asyncio.to_thread(store.refund, quota)
            yield event.plain_result("RightCodes 生图 API Key 还没配置。")
            event.stop_event()
            return

        async with self._draw_lock:
            try:
                result = await RightCodesDrawClient(api_key=api_key).draw(draw_request)
            except Exception as exc:
                await asyncio.to_thread(store.refund, quota)
                yield event.plain_result(format_rightcodes_draw_failure(exc))
                event.stop_event()
                return

        message = format_rightcodes_draw_success(result, model=draw_request.model)
        if result.image_url.startswith(("http://", "https://")):
            yield event.chain_result([Plain(message), Image.fromURL(result.image_url)])
        else:
            yield event.plain_result(f"{message}\n{result.image_url}")
        event.stop_event()

    def _should_handle_command(self, event: AstrMessageEvent) -> bool:
        if event.is_private_chat():
            return True
        if bool(getattr(event, "is_at_or_wake_command", False)):
            return True
        return self._config.feature_mode == FEATURE_MODE_FULL


def is_nonebot2_online() -> bool:
    try:
        with socket.create_connection((NONEBOT2_HOST, NONEBOT2_PORT), timeout=0.5):
            return True
    except OSError:
        return False
