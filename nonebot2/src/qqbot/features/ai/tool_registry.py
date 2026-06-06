from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qqbot.services.shapez_service import render_shape_code


class AiToolPermissionError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class AiToolContext:
    data_root: Path
    actor_user_id: str
    group_id: str | None = None
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class AiToolResult:
    ok: bool
    message: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class AiToolSpec:
    name: str
    plugin_id: str
    description: str
    permission: str
    handler: Callable[[dict[str, object], AiToolContext], AiToolResult]


class AiToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AiToolSpec] = {}

    def register(self, spec: AiToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"AI 工具重复注册：{spec.name}")
        self._tools[spec.name] = spec

    def list_tools(self) -> tuple[AiToolSpec, ...]:
        return tuple(self._tools.values())

    def invoke(
        self,
        name: str,
        arguments: dict[str, object],
        context: AiToolContext,
    ) -> AiToolResult:
        spec = self._tools[name]
        if spec.permission == "admin" and not context.is_admin:
            raise AiToolPermissionError(f"AI 工具 {name} 需要作者权限。")
        return spec.handler(arguments, context)


def build_default_ai_tool_registry() -> AiToolRegistry:
    registry = AiToolRegistry()
    registry.register(
        AiToolSpec(
            name="shapez.render_code",
            plugin_id="shapez",
            description="渲染 shapez 短代码图片",
            permission="user",
            handler=_handle_shapez_render_code,
        )
    )
    registry.register(
        AiToolSpec(
            name="bot.schedule_private_message",
            plugin_id="ai",
            description="安排稍后向用户发送私聊消息",
            permission="user",
            handler=_handle_deferred_action_tool,
        )
    )
    registry.register(
        AiToolSpec(
            name="proposal.create",
            plugin_id="ai",
            description="把聊天内容记录为待审批需求提案",
            permission="admin",
            handler=_handle_deferred_action_tool,
        )
    )
    return registry


def _handle_shapez_render_code(
    arguments: dict[str, object],
    context: AiToolContext,
) -> AiToolResult:
    code = str(arguments.get("code", "")).strip()
    if not code:
        return AiToolResult(False, "缺少 shapez 短代码。", {})
    shape, output = render_shape_code(context.data_root, code)
    return AiToolResult(
        True,
        f"已渲染短代码：{shape.short_key}",
        {
            "short_code": shape.short_key,
            "image_path": output.as_posix(),
        },
    )


def _handle_deferred_action_tool(
    arguments: dict[str, object],
    context: AiToolContext,
) -> AiToolResult:
    return AiToolResult(True, "工具已声明，具体执行由 AI 编排器处理。", dict(arguments))
