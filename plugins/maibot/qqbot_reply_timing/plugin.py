from __future__ import annotations

from asyncio import CancelledError, create_task
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, cast

import asyncio
import time

from maibot_sdk import Field, HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder

from .reply_split import split_reply

MAX_PENDING_REPLIES = 128
FIRST_SEGMENT_STORE_TIMEOUT = 3.0


class PluginSection(PluginConfigBase):
    """回复分段、等待与引用的启用状态。"""

    enabled: bool = Field(default=False, description="处理回复分段、首条等待和引用")
    config_version: str = Field(default="0.1.0", description="配置版本")


class TimingConfig(PluginConfigBase):
    """只管理插件启用；发送速度继续使用框架现有配置。"""

    plugin: PluginSection = Field(default_factory=PluginSection)


@dataclass
class ReplyTurn:
    """仅保存本轮源消息标识和时钟，不保存聊天正文。"""

    source_id: str
    started_at: float
    author_id: str = ""
    target_id: str = ""
    first_delivery_id: str = ""
    wait_task: asyncio.Task[None] | None = None


@dataclass
class PendingReply:
    target_id: str
    segments: tuple[str, ...]
    first_timestamp: str = ""


def normal_delay(text: str, speed: float, is_emoji: bool = False) -> float:
    """沿用原生发送器的字符计时，包括单汉字和表情的特殊规则。"""
    chinese = sum("\u4e00" <= char <= "\u9fff" for char in text)
    if chinese == 1 and len(text.strip()) == 1:
        return 1.2
    if speed <= 0:
        return 0.0
    return (1.0 if is_emoji else chinese * 0.3 + (len(text) - chinese) * 0.15) * speed


class QQBotReplyTimingPlugin(MaiBotPlugin):
    """统一 QQ 回复分段、首条引用和发送等待。"""

    config_model: ClassVar[type[PluginConfigBase] | None] = TimingConfig

    def __init__(self) -> None:
        """创建有界瞬时状态，支持加载失败后的安全卸载。"""
        super().__init__()
        self._received: OrderedDict[str, tuple[str, float, str]] = OrderedDict()
        self._group_received: OrderedDict[tuple[str, str], tuple[str, float, str]] = OrderedDict()
        self._sources: OrderedDict[tuple[str, str], tuple[str, float, str]] = OrderedDict()
        self._turns: OrderedDict[str, ReplyTurn] = OrderedDict()
        self._reply_quotes: OrderedDict[str, tuple[str, str]] = OrderedDict()
        self._pending_segments: dict[str, PendingReply] = {}
        self._segment_tasks: dict[str, asyncio.Task[None]] = {}
        self._active = False

    async def on_load(self) -> None:
        """启用回复发送规则，不执行外部请求。"""
        self._active = True
        self.ctx.logger.info("回复分段、等待与引用规则已加载，启用=%s", cast(TimingConfig, self.config).plugin.enabled)

    async def on_unload(self) -> None:
        """停止接纳新修正并释放瞬时状态。"""
        self._active = False
        self._received.clear()
        self._group_received.clear()
        self._sources.clear()
        self._turns.clear()
        self._reply_quotes.clear()
        self._pending_segments.clear()
        tasks = tuple(self._segment_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._segment_tasks.clear()

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """配置更新后放弃旧轮次，下一条真实消息重新建立时钟。"""
        del scope, config_data, version
        self._received.clear()
        self._group_received.clear()
        self._sources.clear()
        self._turns.clear()
        self._reply_quotes.clear()
        self._pending_segments.clear()

    def _enabled(self) -> bool:
        return self._active and cast(TimingConfig, self.config).plugin.enabled

    @HookHandler(
        "chat.receive.before_process", name="qqbot_reply_timing_receive",
        description="记录真实接收消息的处理起点，不保存正文",
        mode=HookMode.BLOCKING, order=HookOrder.EARLY, timeout_ms=1000, error_policy=ErrorPolicy.SKIP,
    )
    async def receive(self, message: object = None, **kwargs: Any) -> dict[str, object]:
        """只有结构化 QQ 消息才能成为可抵扣的起点。"""
        del kwargs
        if (self._enabled() and isinstance(message, Mapping) and message.get("platform") == "qq"
                and not message.get("is_command")):
            session_id, message_id = message.get("session_id"), message.get("message_id")
            if isinstance(session_id, str) and session_id and isinstance(message_id, str) and message_id:
                info = message.get("message_info")
                user = info.get("user_info") if isinstance(info, Mapping) else None
                author_id = str(user.get("user_id") or "") if isinstance(info, Mapping) and isinstance(user, Mapping) and info.get("group_info") else ""
                source = (message_id, time.monotonic(), author_id)
                source_key = (session_id, message_id)
                if source_key in self._sources:
                    return {"action": "continue"}
                self._sources[source_key] = source
                if len(self._sources) > 4096:
                    self._sources.popitem(last=False)
                self._received[session_id] = source
                self._received.move_to_end(session_id)
                if len(self._received) > 128:
                    self._received.popitem(last=False)
                if author_id:
                    key = (session_id, author_id)
                    self._group_received[key] = source
                    self._group_received.move_to_end(key)
                    if len(self._group_received) > 4096:
                        self._group_received.popitem(last=False)
                turn = self._turns.get(session_id)
                if (turn is not None and turn.source_id != message_id and turn.author_id == author_id
                        and turn.wait_task is not None):
                    turn.wait_task.cancel()
        return {"action": "continue"}

    @HookHandler(
        "maisaka.replyer.before_model_request", name="qqbot_reply_timing_turn",
        description="按实际回复目标关联本次首条计时",
        mode=HookMode.BLOCKING, order=HookOrder.EARLY, timeout_ms=1000, error_policy=ErrorPolicy.SKIP,
    )
    async def prepare(
        self, session_id: str = "", items: object = None, item_schema_version: int = 0,
        reply_message_id: str = "", **kwargs: Any,
    ) -> dict[str, object]:
        """把计时绑定到实际回复对象在快照中的最新消息。"""
        del kwargs
        if (not self._enabled() or item_schema_version != 1 or not isinstance(items, list)
                or not session_id or not reply_message_id):
            return {"action": "continue"}
        self._reply_quotes[session_id] = (reply_message_id, "")
        self._reply_quotes.move_to_end(session_id)
        if len(self._reply_quotes) > 128:
            self._reply_quotes.popitem(last=False)
        target = self._sources.get((session_id, reply_message_id))
        if target is None:
            self._turns.pop(session_id, None)
            return {"action": "continue"}
        source = target
        for item in items:
            if not isinstance(item, Mapping) or item.get("item_type") != "UserMessageItem":
                continue
            for part in item.get("parts", []):
                text = part.get("text") if isinstance(part, Mapping) and part.get("type") == "text" else None
                if not isinstance(text, str) or not text.startswith('<message msg_id="'):
                    continue
                message_id = text.split('"', 2)[1]
                candidate = self._sources.get((session_id, message_id))
                if candidate is not None and candidate[2] == target[2] and candidate[1] > source[1]:
                    source = candidate
        turn = self._turns.get(session_id)
        if turn is None or turn.source_id != source[0] or turn.target_id != reply_message_id:
            self._turns[session_id] = ReplyTurn(*source, target_id=reply_message_id)
            self._turns.move_to_end(session_id)
            if len(self._turns) > 128:
                self._turns.popitem(last=False)
        return {"action": "continue"}

    @HookHandler(
        "maisaka.reply.before_post_process", name="qqbot_reply_timing_breaks",
        description="短回复整条发送，长回复在自然停顿处分段",
        mode=HookMode.BLOCKING, order=HookOrder.NORMAL, timeout_ms=180000, error_policy=ErrorPolicy.SKIP,
    )
    async def prepare_reply_breaks(
        self, session_id: str = "", reply_message_id: str = "", response: str = "",
        skip_post_process: bool = False, enable_splitter: bool = True, **kwargs: Any,
    ) -> dict[str, object]:
        if (not self._enabled() or not session_id or not reply_message_id or not response.strip()
                or skip_post_process or not enable_splitter):
            return {"action": "continue"}
        if (session_id, reply_message_id) not in self._sources:
            async with asyncio.timeout(1):
                source = await self.ctx.message.get_by_id(reply_message_id, chat_id=session_id, include_binary_data=False)
            if (not isinstance(source, Mapping) or source.get("platform") != "qq"
                    or source.get("session_id") != session_id or source.get("message_id") != reply_message_id):
                return {"action": "continue"}
        task = self._segment_tasks.get(session_id)
        if task is not None:
            await asyncio.shield(task)
        if not self._enabled():
            return {"action": "continue"}
        self._pending_segments.pop(session_id, None)
        args = kwargs.get("reply_tool_args")
        has_attachments = isinstance(args, Mapping) and any(args.get(key) for key in ("attach_at", "attach_pic", "attach_emoji"))
        first = response
        if not has_attachments and len(self._pending_segments) + len(self._segment_tasks) < MAX_PENDING_REPLIES:
            segments = split_reply(response)
            if len(segments) > 1:
                self._pending_segments[session_id] = PendingReply(reply_message_id, segments)
                first = segments[0]
        return {"action": "continue", "modified_kwargs": {
            **kwargs, "session_id": session_id, "reply_message_id": reply_message_id, "response": first,
            "skip_post_process": True, "enable_splitter": False,
        }}

    @HookHandler(
        "send_service.after_build_message", name="qqbot_reply_timing_native",
        description="识别原生回复首段并接入统一发送计时",
        mode=HookMode.BLOCKING, order=HookOrder.LATE, timeout_ms=1000, error_policy=ErrorPolicy.SKIP,
    )
    async def prepare_segment(
        self, message: object = None, processed_plain_text: str = "", typing: bool = False, **kwargs: Any,
    ) -> dict[str, object]:
        """原生回复首段默认关闭 typing；分段已完成时统一由首条抵扣决定补等。"""
        if (not self._enabled() or typing or not isinstance(message, Mapping)
                or message.get("platform") != "qq"):
            return {"action": "continue"}
        session_id, target_id, delivery_id = message.get("session_id"), message.get("reply_to"), message.get("message_id")
        if not isinstance(session_id, str):
            return {"action": "continue"}
        if (isinstance(target_id, str) and isinstance(delivery_id, str) and delivery_id
                and self._reply_quotes.get(session_id) == (target_id, "")):
            self._reply_quotes[session_id] = (target_id, delivery_id)
        pending = self._pending_segments.get(session_id)
        if (pending is not None and pending.target_id == target_id
                and pending.segments[0] == processed_plain_text):
            timestamp = message.get("timestamp")
            if isinstance(timestamp, str):
                pending.first_timestamp = timestamp
        turn = self._turns.get(session_id)
        if processed_plain_text and turn is not None and target_id == turn.target_id:
            return {"action": "continue", "modified_kwargs": {
                **kwargs, "message": message, "processed_plain_text": processed_plain_text, "typing": True,
            }}
        return {"action": "continue"}

    @HookHandler(
        "send_service.before_send", name="qqbot_reply_route",
        description="为本实例缺少连接标识的 QQ 出站消息补齐 NapCat 路由",
        mode=HookMode.BLOCKING, order=HookOrder.EARLY, timeout_ms=5000, error_policy=ErrorPolicy.ABORT,
    )
    async def prepare_route(self, message: object = None, **kwargs: Any) -> dict[str, object]:
        """只补本账号缺失的 scope，已有路由、目标与消息内容保持原样。"""
        if not self._enabled() or not isinstance(message, Mapping) or message.get("platform") != "qq":
            return {"action": "continue"}
        info = message.get("message_info")
        if not isinstance(info, Mapping):
            return {"action": "continue"}
        sender = info.get("user_info")
        extra = info.get("additional_config") or {}
        if not isinstance(sender, Mapping) or not isinstance(extra, Mapping):
            return {"action": "continue"}
        if any(extra.get(key) for key in ("platform_io_scope", "route_scope", "adapter_scope", "connection_id")):
            return {"action": "continue"}
        account = str(await self.ctx.config.get("bot.qq_account", ""))
        if not account or str(sender.get("user_id", "")) != account:
            return {"action": "continue"}
        accounts = [extra.get(key) for key in ("platform_io_account_id", "account_id", "self_id", "bot_account") if extra.get(key)]
        if any(str(value) != account for value in accounts):
            return {"action": "continue"}
        adapter = await self.ctx.config.get_plugin("maibot-team.napcat-adapter")
        server = adapter.get("napcat_server")
        scope = server.get("connection_id") if isinstance(server, Mapping) else None
        if not isinstance(scope, str) or not scope.strip():
            return {"action": "continue"}
        routed = {**message, "message_info": {**info, "additional_config": {
            **extra, "platform_io_account_id": account, "platform_io_scope": scope.strip(),
        }}}
        self.ctx.logger.info("已为本账号出站消息补齐 NapCat 连接标识")
        return {"action": "continue", "modified_kwargs": {**kwargs, "message": routed}}

    def _latest_source(self, session_id: str, turn: ReplyTurn) -> tuple[str, float, str] | None:
        """群聊只让本轮发送者的补充取代首段，其他成员不撤销当前发送。"""
        if turn.author_id:
            return self._group_received.get((session_id, turn.author_id))
        return self._received.get(session_id)

    @HookHandler(
        "send_service.before_send", name="qqbot_reply_timing_send",
        description="扣除首条已耗时，并在打字等待结束后判断是否引用",
        mode=HookMode.BLOCKING, order=HookOrder.LATE, timeout_ms=180000, error_policy=ErrorPolicy.ABORT,
    )
    async def before_send(
        self, message: object = None, typing: bool = False, reply_message_id: str = "", **kwargs: Any,
    ) -> dict[str, object]:
        result = await self._wait_before_send(message, typing, reply_message_id, **kwargs)
        if result["action"] == "abort" or not self._enabled() or not isinstance(message, Mapping):
            return result
        session_id, delivery_id = message.get("session_id"), message.get("message_id")
        if (not isinstance(session_id, str) or not delivery_id
                or self._reply_quotes.get(session_id) != (reply_message_id, delivery_id)):
            return result
        modified = {
            **kwargs, "message": message, "typing": typing, "reply_message_id": reply_message_id,
            **result.get("modified_kwargs", {}),
        }
        if modified["typing"]:
            speed = float(await self.ctx.config.get("response_post_process.typing_speed", 1.0))
            text = message.get("processed_plain_text")
            await asyncio.sleep(normal_delay(text if isinstance(text, str) else "", speed, message.get("is_emoji") is True))
            modified["typing"] = False
        modified["set_reply"] = await self._should_quote(session_id, reply_message_id)
        return {"action": "continue", "modified_kwargs": modified}

    async def _should_quote(self, session_id: str, target_id: str) -> bool:
        try:
            async with asyncio.timeout(1):
                target = await self.ctx.message.get_by_id(target_id, chat_id=session_id, include_binary_data=False)
                if (not isinstance(target, Mapping) or target.get("platform") != "qq"
                        or target.get("session_id") != session_id or target.get("message_id") != target_id):
                    return False
                timestamp = float(target.get("timestamp") or 0)
                if not 0 < timestamp <= time.time() - 30:
                    return False
                count = await self.ctx.message.count_new(session_id, since=str(timestamp))
                return type(count) is int and count > 5
        except (TypeError, ValueError):
            return False
        except Exception as exc:
            self.ctx.logger.warning("无法核对首条回复的引用条件: %s", exc)
            return False

    async def _wait_before_send(
        self, message: object, typing: bool, reply_message_id: str, **kwargs: Any,
    ) -> dict[str, Any]:
        """原子占用首条资格；取消或未知发送结果不会让另一条消息重复抵扣。"""
        if not self._enabled() or not typing or not isinstance(message, Mapping) or message.get("platform") != "qq":
            return {"action": "continue"}
        session_id, delivery_id = message.get("session_id"), message.get("message_id")
        turn = self._turns.get(session_id) if isinstance(session_id, str) else None
        if (turn is None or turn.first_delivery_id or turn.target_id != reply_message_id
                or not isinstance(delivery_id, str) or not delivery_id):
            return {"action": "continue"}
        # 先读取配置，再检查并占用，避免 RPC 让两个并发发送都取得首条资格。
        speed = float(await self.ctx.config.get("response_post_process.typing_speed", 1.0))
        if turn is not self._turns.get(session_id) or turn.first_delivery_id:
            return {"action": "continue"}
        turn.first_delivery_id = delivery_id
        text = message.get("processed_plain_text")
        delay = normal_delay(text if isinstance(text, str) else "", speed, message.get("is_emoji") is True)
        elapsed = max(0.0, time.monotonic() - turn.started_at)
        wait = max(0.0, delay - elapsed)
        received = self._latest_source(cast(str, session_id), turn)
        if wait and (received is None or received[0] == turn.source_id):
            turn.wait_task = create_task(asyncio.sleep(wait))
            try:
                await turn.wait_task
            except CancelledError:
                received = self._latest_source(cast(str, session_id), turn)
                if received is None or received[0] == turn.source_id:
                    raise
            finally:
                turn.wait_task = None
        if not self._enabled():
            return {"action": "abort"}
        received = self._latest_source(cast(str, session_id), turn)
        if received is not None and received[0] != turn.source_id:
            try:
                async with asyncio.timeout(5):
                    result = await self.ctx.api.call(
                        "mlj.cpa-session.resume_cancelled_reply", version="1", session_id=session_id,
                        reply_message_id=reply_message_id,
                    )
                if not isinstance(result, dict):
                    raise RuntimeError("会话插件返回了无效的重新排队结果")
                if result.get("stale") is True:
                    turn.first_delivery_id = ""
                    if result.get("queued") is not True:
                        self.ctx.logger.error("过期首段重新排队失败: session_id=%s", session_id)
                    return {"action": "abort"}
            except Exception as exc:
                self.ctx.logger.error("无法确认首段是否过期: session_id=%s error=%s", session_id, exc)
                turn.first_delivery_id = ""
                return {"action": "abort"}
        self.ctx.logger.info("首条回复等待: 原等待=%.3fs 已处理=%.3fs 补等=%.3fs", delay, elapsed, wait)
        return {"action": "continue", "modified_kwargs": {**kwargs, "message": message, "typing": False}}

    @HookHandler(
        "send_service.after_send", name="qqbot_reply_timing_receipt",
        description="失败时释放首条资格，成功后发送剩余段落",
        mode=HookMode.BLOCKING, order=HookOrder.LATE, timeout_ms=1000, error_policy=ErrorPolicy.SKIP,
    )
    async def after_send(
        self, message: object = None, sent: bool = False, reply_message_id: str = "", **kwargs: Any,
    ) -> dict[str, object]:
        del kwargs
        if not isinstance(message, Mapping):
            return {"action": "continue"}
        session_id = message.get("session_id")
        if not isinstance(session_id, str):
            return {"action": "continue"}
        message_id = message.get("message_id")
        turn = self._turns.get(session_id)
        if turn is not None and not sent and turn.first_delivery_id == message_id:
            turn.first_delivery_id = ""
        pending = self._pending_segments.get(session_id)
        if (pending is not None and pending.target_id == reply_message_id and pending.first_timestamp
                and pending.first_timestamp == message.get("timestamp") and message.get("platform") == "qq"):
            self._pending_segments.pop(session_id)
            if sent and self._enabled() and isinstance(message_id, str) and message_id:
                self._segment_tasks[session_id] = create_task(self._send_segments(session_id, message_id, pending.segments[1:]))
        return {"action": "continue"}

    async def _send_segments(self, session_id: str, first_id: str, segments: tuple[str, ...]) -> None:
        try:
            # 回执 Hook 早于入库，先等首段可查，保持会话历史顺序。
            async with asyncio.timeout(FIRST_SEGMENT_STORE_TIMEOUT):
                while not await self.ctx.message.get_by_id(first_id, chat_id=session_id, include_binary_data=False):
                    await asyncio.sleep(0.05)
            for segment in segments:
                result = await self.ctx.send.text(
                    segment, session_id, typing=True, return_details=True,
                    sync_to_maisaka_history=True, maisaka_source_kind="guided_reply",
                )
                if not isinstance(result, dict) or result.get("sent") is not True:
                    raise RuntimeError("后续段未收到成功回执")
        except Exception as exc:
            self.ctx.logger.warning("分段发送提前结束: session=%s first_id=%s error=%s", session_id, first_id, exc)
        finally:
            self._segment_tasks.pop(session_id, None)


def create_plugin() -> QQBotReplyTimingPlugin:
    """由公开 Runner 创建插件。"""
    return QQBotReplyTimingPlugin()
