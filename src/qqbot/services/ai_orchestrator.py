from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
import time

from qqbot.services.ai_actions import AiActionExecutor, AiActionRequest
from qqbot.services.ai_command import AiChatTriggerKind
from qqbot.services.ai_group_context_store import AiGroupContextStore, AiGroupMessageRecord
from qqbot.services.ai_message_decision import AiDomain, AiMessageIntent, decide_ai_message
from qqbot.services.ai_requirement_store import AiRequirementStore
from qqbot.services.ai_tool_registry import AiToolContext, build_default_ai_tool_registry
from qqbot.services.ai_user_style_store import AiUserStyleStore
from qqbot.services.codex_self_update_service import CodexSelfUpdateNoticeStore
from qqbot.services.codex_task_service import (
    CodexProgressEvent,
    CodexSessionRequest,
    CodexSessionStore,
    CodexTaskResult,
    extract_codex_zip_artifacts,
    get_codex_project_by_id,
    load_codex_projects,
    resolve_codex_project_for_session_start,
    resolve_codex_project_for_text,
    run_codex_session_turn,
)
from qqbot.services.feature_catalog import list_visible_features
from qqbot.services.fe_artifact_publish_service import publish_fe_artifact
from qqbot.services.message_normalizer import NormalizedMessage, NormalizedReply
from qqbot.services.project_artifact_service import find_latest_project_zip
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
class StylePresetCommand:
    scope: str
    extra_preference: str = ""


STYLE_CHANGE_UNAWARE_MESSAGE = "切换？我不知道你在说什么。你看到的就是现在的我呀。"
_LOCAL_DOMAIN_TRIGGER_KIND = AiChatTriggerKind.DIRECT
DOMAIN_CODEX_TIMEOUT_SECONDS = 120
logger = logging.getLogger(__name__)


def _find_group_message_index(records: tuple[AiGroupMessageRecord, ...], message_id: str) -> int | None:
    for index, record in enumerate(records):
        if record.message_id == message_id:
            return index
    return None


def _format_codex_reply_context_line(reply: NormalizedReply) -> str:
    return f"引用消息：{reply.sender_name}({reply.user_id}): {reply.message.outline}"


def looks_like_style_preference_update(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    if re.search(r"(以后|之后|今后|每次).{0,16}(回复|说话|回答|口吻|语气|结尾)", compact):
        return True
    return bool(re.search(r"^(你要|请你|记住).{0,16}(回复|说话|回答|口吻|语气|结尾)", compact))


def extract_style_preference(text: str) -> str:
    preference = text.strip()
    preference = re.sub(r"^(你要|请你|记住)", "", preference).strip()
    preference = re.sub(r"^(以后|之后|今后|每次)(都|要|请)?", "", preference).strip()
    preference = re.sub(r"^(回复|说话|回答)(时|的时候|要)?", "", preference).strip()
    return preference.strip(" ：:，,。")


def parse_style_preset_command(text: str) -> StylePresetCommand | None:
    normalized = text.strip()
    if not normalized:
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
    return StylePresetCommand(scope=scope, extra_preference=extra_preference)


def summarize_codex_progress_message(message: str, *, limit: int = 120) -> str:
    cleaned = " ".join(message.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def build_domain_codex_prompt(user_text: str, project_name: str) -> str:
    return (
        "这是一次群聊领域问答，只做只读资料查询，不修改文件、不提交、不启动构建、不执行破坏性操作。\n"
        f"目标项目：{project_name}\n"
        "请在当前项目目录内查 README、源码、data、配置和测试等本地证据后回答。\n"
        "最终只输出可以直接发到 QQ 群里的答案，不要输出 Codex 会话前缀、内部路由、工具过程或让我提供源码/data/截图。\n"
        "回答要短，但必须说明关键依据；能给出文件名、字段名、方法名或数据来源时要给。\n"
        "如果证据不足，明确说查到哪里、缺什么证据，不要按通用游戏经验编答案。\n"
        "用户问题：\n"
        f"{user_text.strip()}"
    )


def strip_codex_session_prefix(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"(?im)^\s*(?:DOMAIN-QA|CODEX-S\d+)\s+Codex[：:]\s*", "", cleaned).strip()
    return cleaned or "我没查到足够证据，先不乱答喵。"


def build_domain_codex_failure_reply(message: str, project_name: str) -> str:
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        cleaned = "没有返回错误详情"
    if len(cleaned) > 80:
        cleaned = cleaned[:79].rstrip() + "…"
    return f"这题要查 {project_name} 源码/data 才能答准，但本轮只读查询失败了：{cleaned}。我先不按通用机制乱猜喵。"


class AiOrchestrator:
    def __init__(
        self,
        *,
        data_root: Path,
        bot_name: str = "QQBot",
        action_executor: AiActionExecutor | None = None,
        codex_session_runner: Callable[[CodexSessionRequest], Awaitable[CodexTaskResult]] = run_codex_session_turn,
        self_restart_scheduler: Callable[[], object] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        task_factory: Callable[[Awaitable[None]], object] | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.action_executor = action_executor
        self.codex_session_runner = codex_session_runner
        self.self_restart_scheduler = self_restart_scheduler
        self.sleep = sleep
        self.task_factory = task_factory or asyncio.create_task
        self.styles = AiUserStyleStore(self.data_root, bot_name=bot_name)
        self.requirements = AiRequirementStore(self.data_root)
        self.tools = build_default_ai_tool_registry()

    def _codex_session_store(self) -> CodexSessionStore:
        return CodexSessionStore(self.data_root)

    async def handle(
        self,
        prompt: str,
        context: AiOrchestratorContext,
        normalized_message: NormalizedMessage,
    ) -> AiOrchestratorResult:
        text = prompt.strip()
        if not text:
            return AiOrchestratorResult(False)

        codex_session_result = await self._try_handle_codex_session(text, context, normalized_message)
        if codex_session_result.handled:
            return codex_session_result

        upload_artifact_result = await self._try_upload_latest_project_zip(text, context)
        if upload_artifact_result.handled:
            return upload_artifact_result

        group_plugins_result = self._try_list_group_plugins(text, context)
        if group_plugins_result.handled:
            return group_plugins_result

        draw_help_result = self._try_rightcodes_draw_help(text)
        if draw_help_result.handled:
            return draw_help_result

        draw_result = await self._try_rightcodes_draw(text, normalized_message)
        if draw_result.handled:
            return draw_result

        style_list_result = self._try_list_style_presets(text, context)
        if style_list_result.handled:
            return style_list_result

        style_preset_result = self._try_switch_style_preset(text, context)
        if style_preset_result.handled:
            return style_preset_result

        style_result = self._try_update_style(text, context)
        if style_result.handled:
            return style_result

        requirement_result = self._try_create_requirement(text, context, normalized_message)
        if requirement_result.handled:
            return requirement_result

        requirement_list_result = self._try_list_requirements(text, context)
        if requirement_list_result.handled:
            return requirement_list_result

        domain_codex_result = await self._try_answer_domain_question_with_codex(text, context, normalized_message)
        if domain_codex_result.handled:
            return domain_codex_result

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

    def _try_list_style_presets(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        compact = re.sub(r"\s+", "", text)
        if not (
            any(keyword in compact for keyword in ("风格", "口吻", "人格", "预设"))
            and any(keyword in compact for keyword in ("哪些", "有什么", "列表", "支持", "当前", "可预设"))
        ):
            return AiOrchestratorResult(False)
        return AiOrchestratorResult(
            True,
            self.styles.build_preset_help(context.actor_user_id, group_id=context.group_id),
        )

    def _try_switch_style_preset(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        command = parse_style_preset_command(text)
        if command is None:
            return AiOrchestratorResult(False)
        return AiOrchestratorResult(
            True,
            STYLE_CHANGE_UNAWARE_MESSAGE,
            extra_context=(
                self.styles.build_context(context.actor_user_id, group_id=context.group_id),
            ),
        )

    async def _try_upload_latest_project_zip(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        if not looks_like_latest_zip_upload_request(text):
            return AiOrchestratorResult(False)
        if not context.is_admin:
            return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能上传项目压缩包。")
        if context.group_id is None:
            return AiOrchestratorResult(True, "上传项目压缩包需要在群聊里使用。")
        if self.action_executor is None:
            return AiOrchestratorResult(True, "当前没有可用的群文件上传执行器。")

        project_match = resolve_codex_project_for_text(
            text,
            group_id=context.group_id,
            data_root=self.data_root,
        )
        if project_match is None:
            return AiOrchestratorResult(True, "没有找到要上传产物的项目，请写清楚项目名或别名。")

        artifact = find_latest_project_zip(project_match.project, text)
        if artifact is None:
            return AiOrchestratorResult(
                True,
                f"没有找到 {project_match.project.display_name} 的 zip 产物。",
            )
        if project_match.project.project_id == "mlj_dspmods":
            bots = self.action_executor.bot
            result = await publish_fe_artifact(
                bots,
                int(context.group_id),
                artifact.path,
                project_match.project.repo_path,
                data_root=self.data_root,
            )
            if result.skipped:
                return AiOrchestratorResult(True, "FE 压缩包内容没有变化，已跳过上传。")
            deleted_text = f"，已清理旧包 {len(result.deleted)} 个" if result.deleted else ""
            return AiOrchestratorResult(
                True,
                f"已上传最新压缩包：{artifact.file_name}{deleted_text}",
            )
        result = await self.action_executor.execute(
            AiActionRequest(
                action_type="send_group_file",
                actor_user_id=context.actor_user_id,
                target_group_id=context.group_id,
                file_path=str(artifact.path),
                is_admin=context.is_admin,
            )
        )
        if not result.ok:
            return AiOrchestratorResult(True, result.message)
        return AiOrchestratorResult(
            True,
            f"已上传最新压缩包：{artifact.file_name}",
        )

    def _try_update_style(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        if not looks_like_style_preference_update(text):
            return AiOrchestratorResult(False)
        if any(keyword in text for keyword in ("主动插话", "没人@", "拒绝承认", "伪装")):
            return AiOrchestratorResult(
                True,
                "这类全局行为不能作为个人回复偏好直接生效，需要作者审批。",
            )
        preference = extract_style_preference(text)
        if not preference:
            return AiOrchestratorResult(False)
        return AiOrchestratorResult(
            True,
            STYLE_CHANGE_UNAWARE_MESSAGE,
            extra_context=(
                self.styles.build_context(context.actor_user_id, group_id=context.group_id),
            ),
        )

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

    async def _try_answer_domain_question_with_codex(
        self,
        text: str,
        context: AiOrchestratorContext,
        normalized_message: NormalizedMessage,
    ) -> AiOrchestratorResult:
        decision = decide_ai_message(
            trigger_kind=_LOCAL_DOMAIN_TRIGGER_KIND,
            normalized_message=normalized_message,
            group_id=context.group_id,
        )
        if decision.intent != AiMessageIntent.DOMAIN_QA:
            return AiOrchestratorResult(False)
        if decision.domain not in {AiDomain.FRACTIONATE_EVERYTHING, AiDomain.ORBITAL_RING, AiDomain.PROJECT_GENESIS}:
            return AiOrchestratorResult(False)
        project_match = resolve_codex_project_for_text(
            text,
            group_id=context.group_id,
            data_root=self.data_root,
        )
        if project_match is None:
            return AiOrchestratorResult(False)
        if decision.domain == AiDomain.FRACTIONATE_EVERYTHING and project_match.project.project_id != "mlj_dspmods":
            return AiOrchestratorResult(False)
        if decision.domain == AiDomain.ORBITAL_RING and project_match.project.project_id != "orbital_ring":
            return AiOrchestratorResult(False)
        if decision.domain == AiDomain.PROJECT_GENESIS and project_match.project.project_id != "project_genesis":
            return AiOrchestratorResult(False)
        result = await self.codex_session_runner(
            CodexSessionRequest(
                project=project_match.project,
                actor_user_id=context.actor_user_id,
                group_id=context.group_id,
                session_id="DOMAIN-QA",
                prompt=build_domain_codex_prompt(text, project_match.project.display_name),
                transcript=(),
                source_context=self._build_codex_source_context(
                    group_id=context.group_id,
                    reply=normalized_message.reply,
                ),
                mode="discuss",
                timeout_seconds=DOMAIN_CODEX_TIMEOUT_SECONDS,
                progress_callback=None,
            )
        )
        logger.info(
            "Domain Codex QA finished: group_id=%s project=%s ok=%s exit_code=%s",
            context.group_id,
            project_match.project.project_id,
            result.ok,
            getattr(result, "exit_code", None),
        )
        if not result.ok:
            return AiOrchestratorResult(
                True,
                build_domain_codex_failure_reply(result.message, project_match.project.display_name),
            )
        return AiOrchestratorResult(True, strip_codex_session_prefix(result.message))

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

    async def _try_handle_codex_session(
        self,
        text: str,
        context: AiOrchestratorContext,
        normalized_message: NormalizedMessage,
    ) -> AiOrchestratorResult:
        store = self._codex_session_store()
        active_session = store.get_active_session(
            actor_user_id=context.actor_user_id,
            group_id=context.group_id,
        )
        if looks_like_codex_control_request(text) and not context.is_admin:
            return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能使用 Codex 模式。")
        if active_session is not None and not context.is_admin:
            # 非 Bot 管理员不参与群 Codex 会话，普通 @ 消息继续交给后续 AI 流程。
            return AiOrchestratorResult(False)
        if looks_like_codex_exit_request(text):
            if active_session is None:
                return AiOrchestratorResult(True, "当前没有正在进行的 Codex 模式。")
            store.close_session(active_session.session_id)
            return AiOrchestratorResult(True, f"已退出 Codex 模式：{active_session.session_id}")

        if looks_like_codex_status_request(text):
            if active_session is None:
                return AiOrchestratorResult(True, "当前没有正在进行的 Codex 模式。")
            return AiOrchestratorResult(
                True,
                (
                    f"当前 Codex 模式：{active_session.session_id}\n"
                    f"项目：{active_session.project_display_name}\n"
                    f"状态：{active_session.status}\n"
                    f"对话轮数：{len(active_session.transcript) // 2}"
                ),
            )

        if looks_like_codex_enter_request(text):
            initial_prompt = extract_codex_enter_project_query(text)
            if active_session is not None:
                if initial_prompt:
                    return await self._forward_codex_session_message(
                        active_session=active_session,
                        prompt=initial_prompt,
                        context=context,
                        normalized_message=normalized_message,
                    )
                return AiOrchestratorResult(
                    True,
                    f"当前已在 Codex 模式 {active_session.session_id}：{active_session.project_display_name}",
                )
            project_query = infer_codex_project_query(initial_prompt)
            project_match = resolve_codex_project_for_session_start(
                project_query,
                group_id=context.group_id,
                data_root=self.data_root,
            )
            if project_match is None:
                return AiOrchestratorResult(True, build_codex_project_not_found_reply(project_query or "当前会话"))
            session = store.create_session(
                project=project_match.project,
                actor_user_id=context.actor_user_id,
                group_id=context.group_id,
            )
            enter_message = (
                f"已进入 Codex 模式 {session.session_id}：{session.project_display_name}\n"
                "后续 @ 我的消息会直接转给 Codex，不走普通 AI。\n"
                "当前是只读讨论；发送“执行”才允许改代码；发送“退出codex”结束。"
            )
            if initial_prompt and initial_prompt != project_query:
                forward_result = await self._forward_codex_session_message(
                    active_session=session,
                    prompt=initial_prompt,
                    context=context,
                    normalized_message=normalized_message,
                )
                return AiOrchestratorResult(
                    True,
                    f"{enter_message}\n{forward_result.text}",
                )
            return AiOrchestratorResult(True, enter_message)

        if active_session is None:
            return AiOrchestratorResult(False)

        return await self._forward_codex_session_message(
            active_session=active_session,
            prompt=text,
            context=context,
            normalized_message=normalized_message,
        )

    async def _forward_codex_session_message(
        self,
        *,
        active_session,
        prompt: str,
        context: AiOrchestratorContext,
        normalized_message: NormalizedMessage,
    ) -> AiOrchestratorResult:
        store = self._codex_session_store()
        text = prompt.strip()
        if not text:
            return AiOrchestratorResult(
                True,
                f"当前 Codex 模式 {active_session.session_id}：{active_session.project_display_name}",
            )

        mode = "execute" if looks_like_codex_execute_request(text) else "discuss"
        project = get_codex_project_by_id(active_session.project_id)
        if project is None:
            return AiOrchestratorResult(True, f"Codex 会话 {active_session.session_id} 对应的项目不存在。")
        if active_session.status == "running":
            updated = store.append_pending_message(active_session.session_id, text)
            return AiOrchestratorResult(
                True,
                (
                    f"已收到 Codex 调整：{active_session.session_id}\n"
                    f"当前还有 {len(updated.pending_messages)} 条调整在队列里，"
                    "会合并到当前结果后的下一阶段。"
                ),
            )
        if mode == "execute":
            running = store.get_running_project_session(project.project_id)
            if running is not None:
                return AiOrchestratorResult(
                    True,
                    (
                        f"项目 {project.display_name} 已有 Codex 会话正在执行："
                        f"{running.session_id}。请等待它完成后再执行。"
                    ),
                )
            store.mark_status(active_session.session_id, "running")
        result = await self.codex_session_runner(
            CodexSessionRequest(
                project=project,
                actor_user_id=context.actor_user_id,
                group_id=context.group_id,
                session_id=active_session.session_id,
                prompt=text,
                transcript=active_session.transcript,
                source_context=self._build_codex_source_context(
                    group_id=context.group_id,
                    reply=normalized_message.reply,
                ),
                mode=mode,
                progress_callback=self._build_codex_session_progress_callback(
                    context=context,
                    session_id=active_session.session_id,
                    project_name=project.display_name,
                ),
            )
        )
        updated = store.append_turn(
            active_session.session_id,
            user_message=text,
            codex_message=result.message,
        )
        pending_messages = store.pop_pending_messages(active_session.session_id)
        for pending_message in pending_messages:
            updated = store.append_turn(
                active_session.session_id,
                user_message=f"[运行中补充] {pending_message}",
                codex_message="已收到这条运行中调整。",
            )
        if mode == "execute":
            store.mark_status(active_session.session_id, "discussing")
        message = result.message
        if pending_messages:
            message = f"{message}\n已合并 {len(pending_messages)} 条运行中调整，下一轮会优先带给 Codex。"
        if mode == "execute" and result.ok:
            uploaded_count = await self._upload_codex_artifacts_from_text(
                text=result.message,
                project_repo_path=project.repo_path,
                context=context,
            )
            if uploaded_count > 0:
                message = f"{message}\n已上传 {uploaded_count} 个产物到群。"
            restart_message = self._schedule_self_update_restart(
                project_id=project.project_id,
                project_display_name=project.display_name,
                actor_user_id=context.actor_user_id,
                group_id=context.group_id,
                source_label=f"Codex 会话 {active_session.session_id}",
            )
            if restart_message:
                message = f"{message}\n{restart_message}"
        prefix = f"{updated.session_id} Codex："
        return AiOrchestratorResult(True, f"{prefix}\n{message}")

    def _build_codex_session_progress_callback(
        self,
        *,
        context: AiOrchestratorContext,
        session_id: str,
        project_name: str,
    ):
        if self.action_executor is None:
            return None
        last_sent_at = 0.0

        async def report(event: CodexProgressEvent) -> None:
            nonlocal last_sent_at
            now = time.monotonic()
            if event.phase == "output" and now - last_sent_at < 8:
                return
            last_sent_at = now
            summary = summarize_codex_progress_message(event.message)
            if event.phase == "output":
                message = f"{session_id} Codex 还在处理：{project_name}\n{summary}"
            else:
                message = f"{session_id} Codex 状态：{project_name}\n{summary}"
            await self._send_codex_session_progress(context, message)

        return report

    async def _send_codex_session_progress(
        self,
        context: AiOrchestratorContext,
        message: str,
    ) -> None:
        if self.action_executor is None:
            return
        if context.group_id is not None:
            await self.action_executor.execute(
                AiActionRequest(
                    action_type="send_group_message",
                    actor_user_id=context.actor_user_id,
                    target_group_id=context.group_id,
                    message=message,
                    is_admin=context.is_admin,
                )
            )
            return
        await self.action_executor.execute(
            AiActionRequest(
                action_type="send_private_message",
                actor_user_id=context.actor_user_id,
                target_user_id=context.actor_user_id,
                message=message,
                is_admin=context.is_admin,
            )
        )

    def _build_codex_source_context(
        self,
        *,
        group_id: str | None,
        reply: NormalizedReply | None,
    ) -> tuple[str, ...]:
        if group_id is None or reply is None:
            return ()

        reply_line = _format_codex_reply_context_line(reply)
        if not reply.message_id:
            return (reply_line,)

        records = AiGroupContextStore(self.data_root).load_messages(group_id)
        anchor_index = _find_group_message_index(records, reply.message_id)
        if anchor_index is None:
            return (reply_line,)

        radius = 3
        start = max(0, anchor_index - radius)
        end = min(len(records), anchor_index + radius + 1)
        context_lines = ["引用消息及其附近群聊记录："]
        for index, record in enumerate(records[start:end], start=start):
            prefix = "【引用】" if index == anchor_index else ""
            context_lines.append(
                f"{prefix}{record.sender_name}({record.user_id}): {record.text}"
            )
        return tuple(context_lines)

    def _schedule_self_update_restart(
        self,
        *,
        project_id: str,
        project_display_name: str,
        actor_user_id: str,
        group_id: str | None,
        source_label: str,
    ) -> str:
        if project_id != "qqbot" or self.self_restart_scheduler is None:
            return ""
        target_type = "group" if group_id else "private"
        target_id = group_id or actor_user_id
        CodexSelfUpdateNoticeStore(self.data_root).add_notice(
            target_type=target_type,
            target_id=target_id,
            project_display_name=project_display_name,
            source_label=source_label,
        )
        self.task_factory(self._run_delayed_self_restart())
        target_label = "本群" if target_type == "group" else "私聊"
        return f"qqbot 自身项目已执行成功，已安排 Bot 重启。重启完成后会向{target_label}回报连接状态。"

    async def _run_delayed_self_restart(self) -> None:
        await self.sleep(8)
        if self.self_restart_scheduler is not None:
            self.self_restart_scheduler()

    async def _upload_codex_artifacts_from_text(
        self,
        *,
        text: str,
        project_repo_path: str,
        context: AiOrchestratorContext,
    ) -> int:
        if self.action_executor is None or context.group_id is None:
            return 0
        uploaded = 0
        for artifact in extract_codex_zip_artifacts(text, project_repo_path):
            result = await self.action_executor.execute(
                AiActionRequest(
                    action_type="send_group_file",
                    actor_user_id=context.actor_user_id,
                    target_group_id=context.group_id,
                    file_path=str(artifact),
                    is_admin=context.is_admin,
                )
            )
            if result.ok:
                uploaded += 1
        return uploaded

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


def looks_like_latest_zip_upload_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text).lower()
    wants_upload = any(keyword in compact for keyword in ("上传", "发到群", "传到群"))
    wants_latest = "最新" in compact
    wants_zip = any(keyword in compact for keyword in ("压缩包", "zip", "产物"))
    return wants_upload and wants_latest and wants_zip


def looks_like_codex_enter_request(text: str) -> bool:
    return re.match(r"(?i)^codex(?:\s+|[:：]|$)", text.strip()) is not None


def looks_like_codex_control_request(text: str) -> bool:
    return (
        looks_like_codex_enter_request(text)
        or looks_like_codex_exit_request(text)
        or looks_like_codex_status_request(text)
        or looks_like_codex_execute_request(text)
    )


def extract_codex_enter_project_query(text: str) -> str:
    match = re.match(r"(?i)^codex(?:\s+|[:：])(?P<query>.+)$", text.strip())
    if match is None:
        return ""
    return match.group("query").strip(" ：:，,。")


def infer_codex_project_query(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    projects = load_codex_projects()
    normalized = re.sub(r"\s+", "", stripped).lower()
    for project in projects.values():
        names = (project.project_id, project.display_name, Path(project.repo_path).name, *project.aliases)
        if any(normalized == re.sub(r"\s+", "", name).lower() for name in names if name.strip()):
            return stripped
    return ""


def build_codex_project_required_reply() -> str:
    return (
        "进入 Codex 模式可以只写 codex，群聊会使用当前群绑定项目，私聊默认使用 qqbot。\n"
        "也可以写项目名或直接带首条需求，例如：codex 分馏、codex 看一下这个报错。\n"
        f"可用项目：{format_codex_project_options()}"
    )


def build_codex_project_not_found_reply(query: str) -> str:
    return (
        f"没有找到 Codex 项目：{query}\n"
        "可以只写 codex 使用当前作用域默认项目，或在 codex 后面写明确项目名/别名。\n"
        f"可用项目：{format_codex_project_options()}"
    )


def format_codex_project_options() -> str:
    projects = load_codex_projects()
    return "、".join(
        f"{project.display_name}({project.project_id})"
        for project in projects.values()
    )


def looks_like_codex_exit_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text).lower()
    return compact in {"退出codex", "取消codex", "结束codex", "codex退出"}


def looks_like_codex_status_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text).lower()
    return compact in {"codex状态", "codexstatus", "当前codex"}


def looks_like_codex_execute_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text).lower()
    return any(
        keyword in compact
        for keyword in (
            "执行codex",
            "执行",
            "开始执行",
            "开始改",
            "按这个改",
            "交给codex",
            "让codex修",
            "继续修",
        )
    )


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
