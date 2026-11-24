"""按真实消息发送者判断未送达的模型请求是否过期。"""
from collections import OrderedDict
from dataclasses import dataclass
from html import escape
from typing import Any

import asyncio

from src.llm_models.model_client.base_client import APIResponse, BaseClient, ResponseRequest


@dataclass
class ReplyTurn:
    source_id: str
    sender: str
    received: dict[str, str]
    proactive_item_id: str = ""
    first_sent: bool = False
    resume_queued: bool = False
    target_id: str = ""

    @property
    def latest_source_id(self) -> str:
        return next((mid for mid in reversed(self.received) if self.received[mid] == self.sender), self.source_id)

    @property
    def stale(self) -> bool:
        return not self.first_sent and self.latest_source_id != self.source_id


class ReplyInterruption:
    """跟踪未送达的规划和正文，原生循环负责处理接收与发送。"""

    def __init__(self) -> None:
        self.received: OrderedDict[str, dict[str, str]] = OrderedDict()
        self.turns: dict[str, ReplyTurn] = {}
        self.reply_turns: dict[str, ReplyTurn] = {}
        self.pending: dict[asyncio.Task[APIResponse], ReplyTurn] = {}
        self.closing = False

    def observe(self, message: dict[str, Any]) -> None:
        session_id, message_id = message.get('session_id'), message.get('message_id')
        info = message.get('message_info') or {}
        sender = (info.get('user_info') or {}).get('user_id')
        if (self.closing or message.get('platform') != 'qq' or message.get('is_command')
                or not all(isinstance(value, str) and value for value in (session_id, message_id, sender))):
            return
        received = self.received.setdefault(session_id, {})
        self.received.move_to_end(session_id)
        if message_id in received:
            return
        received[message_id] = sender
        if len(received) > 128:
            del received[next(iter(received))]
        for task, turn in self.pending.items():
            if turn.received is received and turn.sender == sender and turn.stale:
                task.cancel()
        for old_id in list(self.received)[:-4096]:
            old = self.received[old_id]
            if any(turn.received is old for turn in self.pending.values()):
                continue
            self.received.pop(old_id)
            self.turns.pop(old_id, None)
            self.reply_turns.pop(old_id, None)

    def bind(self, session_id: str, items: list[dict[str, Any]], target_id: str = "") -> None:
        """Planner 暂用最新已读发言者，Replyer 按实际回复目标重新绑定。"""
        received = self.received.get(session_id, {})
        planner = self.turns.get(session_id)
        if target_id and planner is not None and planner.first_sent:
            self.reply_turns[session_id] = planner
            return
        actors = self.reply_turns if target_id else self.turns
        sender = received.get(target_id, "")
        if target_id and not sender:
            actors.pop(session_id, None)
            return
        if not target_id:
            self.reply_turns.pop(session_id, None)
        user_items = [item for item in items if item.get('item_type') == 'UserMessageItem']
        texts = [part['text'] for item in user_items for part in item.get('parts', [])
                 if part.get('type') == 'text' and isinstance(part.get('text'), str)]
        source_id = next((mid for mid in reversed(received)
                          if (not sender or received[mid] == sender)
                          and any(text.startswith(f'<message msg_id="{escape(mid, quote=True)}" ') for text in texts)),
                         target_id)
        if not source_id:
            actors.pop(session_id, None)
            return
        proactive_item_id = next((
            item['meta']['item_id'] for item in reversed(user_items)
            if any(part.get('type') == 'text' and part.get('text', '').startswith('<plugin_proactive_task ')
                   for part in item.get('parts', []))
        ), '')
        current = actors.get(session_id)
        if (current is None or current.source_id != source_id or current.target_id != target_id
                or current.proactive_item_id != proactive_item_id):
            actors[session_id] = ReplyTurn(source_id, received[source_id], received, proactive_item_id, target_id=target_id)

    async def request(
        self, client: BaseClient, request: ResponseRequest, turn: ReplyTurn | None,
    ) -> APIResponse | None:
        """过期请求不发起或立即取消，外部卸载和超时继续向调用方传播。"""
        if turn is not None and turn.stale:
            return None
        task = asyncio.create_task(client.get_response(request))
        if turn is not None:
            self.pending[task] = turn
        try:
            response = await task
            return None if turn is not None and turn.stale else response
        except asyncio.CancelledError:
            if not self.closing and turn is not None and turn.stale:
                return None
            raise
        finally:
            self.pending.pop(task, None)

    async def close(self) -> None:
        """卸载时取消并收束本插件请求，清除瞬时关联。"""
        self.closing = True
        tasks = list(self.pending)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.pending.clear()
        self.received.clear()
        self.turns.clear()
        self.reply_turns.clear()
