from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
import json
import time
from pathlib import Path
from typing import Any

from qqbot.services.message_delivery import (
    call_split_text_api,
    wait_for_group_message_interval,
)


@dataclass(frozen=True, slots=True)
class AiActionRequest:
    action_type: str
    actor_user_id: str
    message: str = ""
    target_user_id: str | None = None
    target_group_id: str | None = None
    file_path: str = ""
    delay_seconds: float | None = None
    nested_action: "AiActionRequest | None" = None
    is_admin: bool = False
    source: str = "ai"


@dataclass(frozen=True, slots=True)
class AiActionResult:
    ok: bool
    message: str
    action_type: str


class AiActionExecutor:
    def __init__(
        self,
        *,
        bot: Any,
        data_root: Path,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        task_factory: Callable[[Awaitable[None]], Any] | None = None,
        self_restart_scheduler: Callable[[], object] | None = None,
    ) -> None:
        self.bot = bot
        self.data_root = Path(data_root)
        self.audit_path = Path(data_root) / "ai" / "actions" / "audit.jsonl"
        self.sleep = sleep
        self.task_factory = task_factory or asyncio.create_task
        self.self_restart_scheduler = self_restart_scheduler

    async def execute(self, request: AiActionRequest) -> AiActionResult:
        if request.action_type == "send_private_message":
            result = await self._send_private_message(request)
        elif request.action_type == "send_group_message":
            result = await self._send_group_message(request)
        elif request.action_type == "send_group_file":
            result = await self._send_group_file(request)
        elif request.action_type == "schedule_once":
            result = self._schedule_once(request)
        else:
            result = AiActionResult(False, f"未知机器人动作：{request.action_type}", request.action_type)
        self._append_audit(request, result)
        return result

    async def _send_private_message(self, request: AiActionRequest) -> AiActionResult:
        target_user_id = (request.target_user_id or request.actor_user_id).strip()
        if not request.is_admin and target_user_id != request.actor_user_id:
            return AiActionResult(False, "普通用户只能私聊自己。", request.action_type)
        if not target_user_id.isdigit():
            return AiActionResult(False, "私聊目标 QQ 无效。", request.action_type)
        message = request.message.strip()
        if not message:
            return AiActionResult(False, "私聊消息不能为空。", request.action_type)
        await call_split_text_api(
            self.bot,
            "send_private_msg",
            user_id=int(target_user_id),
            message=message,
        )
        return AiActionResult(True, "已发送私聊消息。", request.action_type)

    async def _send_group_message(self, request: AiActionRequest) -> AiActionResult:
        if not request.is_admin:
            return AiActionResult(False, "只有作者才能让 AI 主动向群发送消息。", request.action_type)
        target_group_id = (request.target_group_id or "").strip()
        if not target_group_id.isdigit():
            return AiActionResult(False, "群聊目标无效。", request.action_type)
        message = request.message.strip()
        if not message:
            return AiActionResult(False, "群聊消息不能为空。", request.action_type)
        await call_split_text_api(
            self.bot,
            "send_group_msg",
            group_id=int(target_group_id),
            message=message,
        )
        return AiActionResult(True, "已发送群聊消息。", request.action_type)

    async def _send_group_file(self, request: AiActionRequest) -> AiActionResult:
        if not request.is_admin:
            return AiActionResult(False, "只有作者才能向群上传文件。", request.action_type)
        target_group_id = (request.target_group_id or "").strip()
        if not target_group_id.isdigit():
            return AiActionResult(False, "群聊目标无效。", request.action_type)
        file_path = Path(request.file_path.strip())
        if file_path.suffix.lower() != ".zip":
            return AiActionResult(False, "当前只允许上传 zip 产物。", request.action_type)
        if not file_path.is_file():
            return AiActionResult(False, "要上传的文件不存在。", request.action_type)
        await wait_for_group_message_interval(target_group_id)
        await self.bot.call_api(
            "upload_group_file",
            group_id=int(target_group_id),
            file=str(file_path),
            name=file_path.name,
        )
        return AiActionResult(True, "已上传群文件。", request.action_type)

    def _schedule_once(self, request: AiActionRequest) -> AiActionResult:
        if request.nested_action is None:
            return AiActionResult(False, "延迟任务缺少要执行的动作。", request.action_type)
        delay_seconds = float(request.delay_seconds or 0)
        if delay_seconds < 1 or delay_seconds > 24 * 60 * 60:
            return AiActionResult(False, "延迟时间必须在 1 秒到 24 小时之间。", request.action_type)
        self.task_factory(self._run_delayed(delay_seconds, request.nested_action))
        return AiActionResult(True, "已安排延迟任务。", request.action_type)

    async def _run_delayed(self, delay_seconds: float, nested_action: AiActionRequest) -> None:
        await self.sleep(delay_seconds)
        await self.execute(nested_action)

    def _append_audit(self, request: AiActionRequest, result: AiActionResult) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": int(time.time()),
            "action_type": request.action_type,
            "request": _serialize_action(request),
            "result": asdict(result),
        }
        with self.audit_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _serialize_action(request: AiActionRequest) -> dict[str, object]:
    payload = asdict(request)
    nested = request.nested_action
    if nested is not None:
        payload["nested_action"] = _serialize_action(nested)
    return payload
