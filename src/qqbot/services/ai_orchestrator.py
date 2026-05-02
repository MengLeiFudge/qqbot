from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
import re

from qqbot.services.ai_actions import AiActionExecutor, AiActionRequest
from qqbot.services.ai_requirement_store import AiRequirementStore
from qqbot.services.ai_tool_registry import AiToolContext, build_default_ai_tool_registry
from qqbot.services.ai_user_style_store import AiUserStyleStore
from qqbot.services.codex_self_update_service import CodexSelfUpdateNoticeStore
from qqbot.services.codex_task_service import (
    CodexSessionRequest,
    CodexSessionStore,
    CodexTaskStore,
    CodexTaskResult,
    extract_codex_zip_artifacts,
    get_codex_project_by_id,
    learn_codex_project_alias,
    load_codex_projects,
    parse_codex_alias_learning_request,
    resolve_codex_project_for_text,
    run_codex_session_turn,
)
from qqbot.services.feature_catalog import list_visible_features
from qqbot.services.message_normalizer import NormalizedMessage
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


class AiOrchestrator:
    def __init__(
        self,
        *,
        data_root: Path,
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
        self.styles = AiUserStyleStore(self.data_root)
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

        codex_result = await self._try_run_codex_fix(text, context, normalized_message)
        if codex_result.handled:
            return codex_result

        group_plugins_result = self._try_list_group_plugins(text, context)
        if group_plugins_result.handled:
            return group_plugins_result

        style_result = self._try_update_style(text, context)
        if style_result.handled:
            return style_result

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

        style_context = self.styles.build_context(context.actor_user_id)
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
            return AiOrchestratorResult(True, "这个问题需要在群聊里问，我才能读取当前群的插件状态。")

        store = SettingsStore(self.data_root, author_qq=0)
        group_id = int(context.group_id)
        enabled_names = [
            feature.name
            for feature in list_visible_features()
            if store.get_group_feature_state(group_id, feature)
        ]
        if not enabled_names:
            return AiOrchestratorResult(True, "本群当前没有启用插件。")
        return AiOrchestratorResult(True, "本群已启用插件：" + "、".join(enabled_names))

    def _try_update_style(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        if not re.search(r"(以后|之后|今后).{0,8}(回复|说话|回答)", text):
            return AiOrchestratorResult(False)
        if any(keyword in text for keyword in ("主动插话", "没人@", "拒绝承认", "伪装")):
            return AiOrchestratorResult(
                True,
                "这类全局行为不能作为个人回复偏好直接生效，需要作者审批。",
            )
        preference = re.sub(r"^(以后|之后|今后)(回复|说话|回答)?", "", text).strip(" ：:，,。")
        if not preference:
            return AiOrchestratorResult(False)
        self.styles.add_preference(context.actor_user_id, preference)
        return AiOrchestratorResult(
            True,
            f"已记住你的回复偏好：{preference}",
            extra_context=(self.styles.build_context(context.actor_user_id),),
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
            if not context.is_admin:
                return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能进入 Codex 模式。")
            project_query = extract_codex_enter_project_query(text)
            if not project_query:
                return AiOrchestratorResult(True, build_codex_project_required_reply())
            project_match = resolve_codex_project_for_text(
                project_query,
                group_id=None,
                data_root=self.data_root,
            )
            if project_match is None:
                return AiOrchestratorResult(True, build_codex_project_not_found_reply(project_query))
            session = store.create_session(
                project=project_match.project,
                actor_user_id=context.actor_user_id,
                group_id=context.group_id,
            )
            return AiOrchestratorResult(
                True,
                (
                    f"已进入 Codex 模式 {session.session_id}：{session.project_display_name}\n"
                    "后续 @ 我的消息会直接转给 Codex，不走普通 AI。\n"
                    "当前是只读讨论；发送“执行”才允许改代码；发送“退出codex”结束。"
                ),
            )

        if active_session is None:
            return AiOrchestratorResult(False)
        if not context.is_admin:
            return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能继续 Codex 模式。")

        mode = "execute" if looks_like_codex_execute_request(text) else "discuss"
        project = get_codex_project_by_id(active_session.project_id)
        if project is None:
            return AiOrchestratorResult(True, f"Codex 会话 {active_session.session_id} 对应的项目不存在。")
        if mode == "execute":
            store.mark_status(active_session.session_id, "running")
        result = await self.codex_session_runner(
            CodexSessionRequest(
                project=project,
                actor_user_id=context.actor_user_id,
                group_id=context.group_id,
                session_id=active_session.session_id,
                prompt=text,
                transcript=active_session.transcript,
                mode=mode,
            )
        )
        updated = store.append_turn(
            active_session.session_id,
            user_message=text,
            codex_message=result.message,
        )
        if mode == "execute":
            store.mark_status(active_session.session_id, "done" if result.ok else "failed")
        message = result.message
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

    async def _try_run_codex_fix(
        self,
        text: str,
        context: AiOrchestratorContext,
        normalized_message: NormalizedMessage,
    ) -> AiOrchestratorResult:
        evidence = build_codex_issue_evidence(normalized_message)
        learning_result = self._try_learn_codex_alias(text, context)
        if learning_result.handled:
            return learning_result

        execute_result = await self._try_execute_codex_draft(text, context)
        if execute_result.handled:
            return execute_result

        followup_result = self._try_append_codex_draft(text, context, evidence)
        if followup_result.handled:
            return followup_result

        project_match = resolve_codex_project_for_text(
            f"{text}\n{evidence}",
            group_id=context.group_id,
            data_root=self.data_root,
        )
        if project_match is None:
            return AiOrchestratorResult(False)
        project = project_match.project

        combined = f"{text}\n{evidence}"
        if not looks_like_codex_fix_request(combined, project_matched=project_match.confidence >= 0.55):
            return AiOrchestratorResult(False)
        if not context.is_admin:
            return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能启动 Codex 修复任务。")

        store = CodexTaskStore(self.data_root)
        task = store.create_draft(
            project=project,
            actor_user_id=context.actor_user_id,
            group_id=context.group_id,
            message=text,
            evidence=evidence,
        )
        return AiOrchestratorResult(
            True,
            build_codex_draft_discussion_reply(task.task_id, project.display_name, task.summary),
        )

    async def _try_execute_codex_draft(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        task_id = parse_codex_task_id(text)
        wants_execute = looks_like_codex_execute_request(text)
        if not wants_execute:
            return AiOrchestratorResult(False)
        if not context.is_admin:
            return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能执行 Codex 草稿。")

        store = CodexTaskStore(self.data_root)
        task = store.get_task(task_id) if task_id else store.find_latest_draft(
            actor_user_id=context.actor_user_id,
            group_id=context.group_id,
        )
        if task is None:
            if task_id is None:
                return AiOrchestratorResult(False)
            return AiOrchestratorResult(True, "没有找到可执行的 Codex 草稿。")
        project = get_codex_project_by_id(task.project_id)
        if project is None:
            return AiOrchestratorResult(True, f"Codex 草稿 {task.task_id} 对应的项目不存在。")
        if self.action_executor is None:
            return AiOrchestratorResult(True, "当前没有可用的 Codex 任务执行器。")

        store.mark_running(task.task_id)
        result = await self.action_executor.execute(
            AiActionRequest(
                action_type="run_codex_task",
                actor_user_id=context.actor_user_id,
                target_group_id=context.group_id,
                codex_project_id=project.project_id,
                codex_task_id=task.task_id,
                codex_prompt="\n".join(task.raw_messages),
                codex_evidence="\n".join(task.evidence),
                is_admin=context.is_admin,
            )
        )
        return AiOrchestratorResult(True, result.message)

    def _try_append_codex_draft(
        self,
        text: str,
        context: AiOrchestratorContext,
        evidence: str,
    ) -> AiOrchestratorResult:
        if not context.is_admin:
            return AiOrchestratorResult(False)
        if not looks_like_codex_followup_request(text):
            return AiOrchestratorResult(False)
        store = CodexTaskStore(self.data_root)
        task = store.find_latest_draft(
            actor_user_id=context.actor_user_id,
            group_id=context.group_id,
        )
        if task is None:
            return AiOrchestratorResult(False)
        updated = store.append_message(task.task_id, text, evidence=evidence)
        return AiOrchestratorResult(
            True,
            f"已补充 Codex 草稿 {updated.task_id}：{updated.summary}",
        )

    def _try_learn_codex_alias(
        self,
        text: str,
        context: AiOrchestratorContext,
    ) -> AiOrchestratorResult:
        parsed = parse_codex_alias_learning_request(text, load_codex_projects())
        if parsed is None:
            return AiOrchestratorResult(False)
        if not context.is_admin:
            return AiOrchestratorResult(True, "只有作者或 Bot 管理员才能调整 Codex 项目别名。")
        alias, project_id = parsed
        learn_codex_project_alias(self.data_root, alias, project_id)
        return AiOrchestratorResult(True, f"已记住：{alias} 属于 {project_id}。")


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


def build_codex_issue_evidence(normalized_message: NormalizedMessage) -> str:
    parts = [normalized_message.outline]
    if normalized_message.reply is not None:
        parts.append(normalized_message.reply.message.outline)
    return "\n".join(part for part in parts if part.strip())


def looks_like_codex_fix_request(text: str, *, project_matched: bool = False) -> bool:
    compact = re.sub(r"\s+", "", text).lower()
    wants_fix = any(
        keyword in compact
        for keyword in (
            "codex",
            "gpt",
            "修一下",
            "修复",
            "看一下这个",
            "处理这个",
            "这个报错",
            "崩溃",
            "bug",
            "改一下",
            "改成",
            "加一个",
            "加个",
            "修改",
            "调整",
            "优化",
            "增加",
            "删除",
            "做一个",
            "计算公式",
            "公式",
            "版本号",
            "修订版本",
            "兼容",
        )
    )
    has_dsp_evidence = any(
        keyword.lower() in compact
        for keyword in (
            "fractionateeverything",
            "FE.Logic",
            "System.IndexOutOfRangeException",
            "Exception",
            "Error report",
        )
    )
    return wants_fix and (has_dsp_evidence or project_matched)


def parse_codex_task_id(text: str) -> str | None:
    match = re.search(r"\bCODEX-\d{4,}\b", text, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.group(0).upper()


def looks_like_codex_enter_request(text: str) -> bool:
    return re.match(r"(?i)^codex(?:\s+|[:：]|$)", text.strip()) is not None


def extract_codex_enter_project_query(text: str) -> str:
    match = re.match(r"(?i)^codex(?:\s+|[:：])(?P<query>.+)$", text.strip())
    if match is None:
        return ""
    return match.group("query").strip(" ：:，,。")


def build_codex_project_required_reply() -> str:
    return (
        "进入 Codex 模式必须在 codex 后面写项目，不能只写 codex。\n"
        "示例：codex qqbot、codex 分馏、codex 异星模组。\n"
        f"可用项目：{format_codex_project_options()}"
    )


def build_codex_project_not_found_reply(query: str) -> str:
    return (
        f"没有找到 Codex 项目：{query}\n"
        "请在 codex 后面写明确项目名或别名。\n"
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


def looks_like_codex_followup_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text).lower()
    return any(
        keyword in compact
        for keyword in (
            "补充",
            "再加",
            "还有",
            "另外",
            "具体",
            "指的是",
            "需求改成",
            "公式具体",
        )
    )


def build_codex_draft_discussion_reply(task_id: str, project_name: str, summary: str) -> str:
    return "\n".join(
        (
            f"已创建 Codex 草稿 {task_id}：{project_name}",
            "当前不会执行，我先把它当成讨论中的代码需求。",
            f"需求摘要：{summary}",
            "先确认：目标行为、兼容边界、版本号格式和验证方式是否还有补充？",
            f"继续补充需求时直接说补充 {task_id} ...",
            f"讨论清楚后再发送：执行 {task_id}",
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
