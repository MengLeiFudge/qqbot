from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re

from qqbot.services.ai_actions import AiActionExecutor, AiActionRequest
from qqbot.services.ai_message_decision import AiMessageIntent, decide_ai_message
from qqbot.services.ai_requirement_store import AiRequirementStore
from qqbot.services.ai_tool_registry import AiToolContext, build_default_ai_tool_registry
from qqbot.services.ai_user_style_store import AiUserStyleStore
from qqbot.services.feature_catalog import list_visible_features
from qqbot.services.message_normalizer import NormalizedMessage, NormalizedReply
from qqbot.services.rightcodes_draw_client import (
    RightCodesDrawClient,
    RightCodesDrawRequest,
    format_rightcodes_draw_failure,
    format_rightcodes_draw_model_help,
    format_rightcodes_draw_success,
    looks_like_rightcodes_draw_help_command,
    parse_rightcodes_draw_command,
)
from qqbot.services.settings_store import SettingsStore
from qqbot.services.shapez_service import SHAPE_PATTERN


@dataclass(frozen=True, slots=True)
class AiOrchestratorContext:
    actor_user_id: str
    group_id: str | None = None
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class AiOrchestratorResult:
    handled: bool
    text: str = ""
    image_path: str | None = None
    extra_context: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StyleControlCommand:
    scope: str
    extra_preference: str = ""


STYLE_CONTROL_REPLY_MESSAGE = "棉花糖就是棉花糖啦，继续正常聊就好喵。"
logger = logging.getLogger(__name__)


def looks_like_style_preference_update(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    if re.search(r"(以后|之后|今后|每次).{0,16}(回复|说话|回答|口吻|语气|结尾)", compact):
        return True
    return bool(re.search(r"^(你要|请你|记住).{0,16}(回复|说话|回答|口吻|语气|结尾)", compact))


def _looks_self_style_subject(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    self_markers = ("你", "棉花糖", "机器人", "bot", "Bot", "ai", "AI", "本群", "这个群", "群默认", "回复", "说话", "回答")
    return any(marker in compact for marker in self_markers)


def _looks_style_control_action(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    action_markers = ("设置", "切换", "改成", "换成", "使用", "启用", "修改")
    return any(marker in compact for marker in action_markers)


def _looks_creative_style_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact or "风格" not in compact:
        return False
    creative_markers = ("生成", "起名", "取名", "写", "作", "画", "润色", "改写")
    creative_objects = ("名字", "昵称", "文案", "标题", "说法", "句子", "图片", "图", "诗", "故事")
    return any(marker in compact for marker in creative_markers) and any(marker in compact for marker in creative_objects)


def extract_style_preference(text: str) -> str:
    preference = text.strip()
    preference = re.sub(r"^(你要|请你|记住)", "", preference).strip()
    preference = re.sub(r"^(以后|之后|今后|每次)(都|要|请)?", "", preference).strip()
    preference = re.sub(r"^(回复|说话|回答)(时|的时候|要)?", "", preference).strip()
    return preference.strip(" ：:，,。")


def parse_style_control_command(text: str) -> StyleControlCommand | None:
    normalized = text.strip()
    if not normalized:
        return None
    if _looks_creative_style_request(normalized):
        return None
    if not (_looks_self_style_subject(normalized) or _looks_style_control_action(normalized)):
        return None
    scope = "group" if any(marker in normalized for marker in ("本群", "这个群", "群默认")) else "user"
    cleaned = re.sub(r"^(请|麻烦|帮我)?", "", normalized).strip()
    cleaned = re.sub(r"^(设置|切换|改成|换成|使用|启用)", "", cleaned).strip()
    cleaned = re.sub(r"^(我的|个人|本群|这个群|群默认)", "", cleaned).strip()
    cleaned = re.sub(r"^(回复|说话|回答)?(风格|模式|口吻|人格)", "", cleaned).strip()
    if not any(marker in normalized for marker in ("风格", "模式", "口吻", "人格")):
        return None

    parts = re.split(r"(?:，|,|。|\s)+(?:但是|但|不过|并且|而且)", cleaned, maxsplit=1)
    style_part = parts[0].strip(" ：:，,。")
    extra_preference = parts[1].strip(" ：:，,。") if len(parts) > 1 else ""
    if not style_part:
        return None
    return StyleControlCommand(scope=scope, extra_preference=extra_preference)


class AiOrchestrator:
    def __init__(
        self,
        *,
        data_root: Path,
        bot_name: str = "QQBot",
        action_executor: AiActionExecutor | None = None,
        self_restart_scheduler: Callable[[], object] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        task_factory: Callable[[Awaitable[None]], object] | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.action_executor = action_executor
        self.self_restart_scheduler = self_restart_scheduler
        self.sleep = sleep
        self.task_factory = task_factory or asyncio.create_task
        self.styles = AiUserStyleStore(self.data_root, bot_name=bot_name)
        self.requirements = AiRequirementStore(self.data_root)
        self.tools = build_default_ai_tool_registry()

    async def handle(
        self,
        prompt: str,
        context: AiOrchestratorContext,
        normalized_message: NormalizedMessage,
    ) -> AiOrchestratorResult:
        text = prompt.strip()
        if not text:
            return AiOrchestratorResult(False)

        group_plugins_result = self._try_list_group_plugins(text, context)
        if group_plugins_result.handled:
            return group_plugins_result

        draw_help_result = self._try_rightcodes_draw_help(text)
        if draw_help_result.handled:
            return draw_help_result

        draw_result = await self._try_rightcodes_draw(text, normalized_message)
        if draw_result.handled:
            return draw_result

        style_control_result = self._try_reject_style_control(text, context)
        if style_control_result.handled:
            return style_control_result

        requirement_result = self._try_create_requirement(text, context, normalized_message)
        if requirement_result.handled:
            return requirement_result

        requirement_list_result = self._try_list_requirements(text, context)
        if requirement_list_result.handled:
            return requirement_list_result

        shapez_result = self._try_render_shapez(text, context)
        if shapez_result.handled:
            return shapez_result

        schedule_result = await self._try_schedule_private_message(text, context)
        if schedule_result.handled:
            return schedule_result

        style_context = self.styles.build_context(context.actor_user_id, group_id=context.group_id)
        return AiOrchestratorResult(
            False,
            extra_context=(style_context,) if style_context else (),
        )

    def _try_list_group_plugins(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        compact = re.sub(r"\s+", "", text)
        if not (
            ("本群" in compact or "这个群" in compact)
            and ("插件" in compact or "功能" in compact)
            and any(keyword in compact for keyword in ("启用", "开启", "开了", "哪些", "有什么"))
        ):
            return AiOrchestratorResult(False)
        if context.group_id is None:
            return AiOrchestratorResult(True, "当前插件状态由全局开关决定，可以在管理端查看。")

        store = SettingsStore(self.data_root, author_qq=0)
        group_id = int(context.group_id)
        enabled_names = [
            feature.name
            for feature in list_visible_features()
            if store.get_group_feature_state(group_id, feature)
        ]
        if not enabled_names:
            return AiOrchestratorResult(True, "当前没有启用插件。")
        return AiOrchestratorResult(True, "当前启用插件：" + "、".join(enabled_names))

    def _try_reject_style_control(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        if looks_like_style_preference_update(text):
            return AiOrchestratorResult(
                True,
                STYLE_CONTROL_REPLY_MESSAGE,
                extra_context=(
                    self.styles.build_context(context.actor_user_id, group_id=context.group_id),
                ),
            )
        if parse_style_control_command(text) is not None:
            return AiOrchestratorResult(
                True,
                STYLE_CONTROL_REPLY_MESSAGE,
                extra_context=(
                    self.styles.build_context(context.actor_user_id, group_id=context.group_id),
                ),
            )
        compact = re.sub(r"\s+", "", text)
        if (
            not _looks_creative_style_request(text)
            and (_looks_self_style_subject(text) or _looks_style_control_action(text))
            and any(keyword in compact for keyword in ("风格", "口吻", "人格", "预设", "人设"))
            and any(
            keyword in compact for keyword in ("哪些", "有什么", "列表", "支持", "当前", "可预设", "切换", "修改", "设置")
            )
        ):
            return AiOrchestratorResult(
                True,
                STYLE_CONTROL_REPLY_MESSAGE,
                extra_context=(
                    self.styles.build_context(context.actor_user_id, group_id=context.group_id),
                ),
            )
        return AiOrchestratorResult(False)

    def _try_create_requirement(
        self,
        text: str,
        context: AiOrchestratorContext,
        normalized_message: NormalizedMessage,
    ) -> AiOrchestratorResult:
        if not any(keyword in text for keyword in ("记一下这个需求", "记录需求", "生成需求提案")):
            return AiOrchestratorResult(False)
        if not context.is_admin:
            return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能记录功能需求。")
        summary = re.sub(r"^(记一下这个需求|记录需求|生成需求提案)[：:，,\s]*", "", text).strip()
        if not summary:
            summary = normalized_message.outline or text
        plugin_id = infer_plugin_id(summary)
        proposal = self.requirements.create_proposal(
            plugin_id=plugin_id,
            summary=summary,
            evidence=(normalized_message.outline or text,),
            created_by=context.actor_user_id,
            group_id=context.group_id,
        )
        return AiOrchestratorResult(
            True,
            f"已记录需求提案 {proposal.id}（{proposal.plugin_id}）：{proposal.summary}",
        )

    def _try_list_requirements(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        if text.strip() not in {"需求列表", "查看需求", "待处理需求"}:
            return AiOrchestratorResult(False)
        if not context.is_admin:
            return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能查看需求列表。")
        proposals = self.requirements.list_proposals()
        if not proposals:
            return AiOrchestratorResult(True, "当前没有待处理需求。")
        lines = [
            f"{proposal.id} [{proposal.plugin_id}] {proposal.summary}（{proposal.status}）"
            for proposal in proposals[-10:]
        ]
        return AiOrchestratorResult(True, "待处理需求：\n" + "\n".join(lines))

    def _try_rightcodes_draw_help(self, text: str) -> AiOrchestratorResult:
        if not looks_like_rightcodes_draw_help_command(text):
            return AiOrchestratorResult(False)
        return AiOrchestratorResult(True, format_rightcodes_draw_model_help())

    async def _try_rightcodes_draw(
        self,
        text: str,
        normalized_message: NormalizedMessage,
    ) -> AiOrchestratorResult:
        request = parse_rightcodes_draw_command(text)
        if request is None:
            return AiOrchestratorResult(False)
        api_key = os.environ.get("QQBOT_AI_KEY_RIGHTCODES", "").strip()
        if not api_key:
            return AiOrchestratorResult(True, "RightCodes 生图 API Key 还没配置。")
        client = RightCodesDrawClient(api_key=api_key)
        try:
            result = await client.draw(
                RightCodesDrawRequest(
                    prompt=request.prompt,
                    model=request.model,
                    image_urls=normalized_message.image_urls,
                )
            )
        except Exception as exc:
            return AiOrchestratorResult(True, format_rightcodes_draw_failure(exc))
        return AiOrchestratorResult(
            True,
            format_rightcodes_draw_success(result, model=request.model),
            image_path=result.image_url,
        )

    def _try_render_shapez(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        match = SHAPE_PATTERN.search(text)
        if match is None:
            return AiOrchestratorResult(False)
        if not any(keyword in text.lower() for keyword in ("shapez", "异形", "短代码", "chart", "画", "渲染")):
            return AiOrchestratorResult(False)
        result = self.tools.invoke(
            "shapez.render_code",
            {"code": match.group(0)},
            AiToolContext(
                data_root=self.data_root,
                actor_user_id=context.actor_user_id,
                group_id=context.group_id,
                is_admin=context.is_admin,
            ),
        )
        return AiOrchestratorResult(
            True,
            str(result.message),
            image_path=str(result.payload.get("image_path", "")) or None,
        )

    async def _try_schedule_private_message(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        if "私聊" not in text and "私信" not in text:
            return AiOrchestratorResult(False)
        delay = parse_delay_seconds(text)
        if delay is None:
            return AiOrchestratorResult(False)
        message = extract_quoted_message(text)
        if not message:
            return AiOrchestratorResult(True, "要安排私聊的话，需要写清楚要发送的消息内容。")
        if self.action_executor is None:
            return AiOrchestratorResult(True, "当前没有可用的机器人动作执行器。")
        result = await self.action_executor.execute(
            AiActionRequest(
                action_type="schedule_once",
                actor_user_id=context.actor_user_id,
                delay_seconds=delay,
                nested_action=AiActionRequest(
                    action_type="send_private_message",
                    actor_user_id=context.actor_user_id,
                    target_user_id=context.actor_user_id,
                    message=message,
                    is_admin=context.is_admin,
                ),
                is_admin=context.is_admin,
            )
        )
        if not result.ok:
            return AiOrchestratorResult(True, result.message)
        return AiOrchestratorResult(True, f"已安排，约 {format_delay(delay)} 后私聊你。")


def parse_delay_seconds(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(秒|分钟|分|小时|时)后", text)
    if match is None:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "秒":
        return value
    if unit in {"分钟", "分"}:
        return value * 60
    return value * 3600


def extract_quoted_message(text: str) -> str:
    match = re.search(r"[“\"「『](.+?)[”\"」』]", text)
    if match is not None:
        return match.group(1).strip()
    tail = re.split(r"(?:私聊|私信)", text, maxsplit=1)
    if len(tail) == 2:
        return tail[1].strip(" ：:，,。")
    return ""


def format_delay(seconds: float) -> str:
    if seconds % 3600 == 0:
        return f"{int(seconds // 3600)}小时"
    if seconds % 60 == 0:
        return f"{int(seconds // 60)}分钟"
    return f"{int(seconds)}秒"


def infer_plugin_id(text: str) -> str:
    lowered = text.lower()
    if "shapez" in lowered or "异形" in text or "短代码" in text or "chart" in lowered:
        return "shapez"
    if "arc" in lowered or "arcaea" in lowered:
        return "arc"
    if "美图" in text or "色图" in text:
        return "lolicon"
    return "ai"
